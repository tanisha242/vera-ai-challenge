"""
Deterministic ConversationStateMachine for magicpin AI Challenge (Vera).
Handles turn tracking, auto-reply detection, affirmative intent transitions,
hostile opt-outs, off-topic redirects, and send/wait/end action responses.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from core.store import ContextStore
from core.suppression import SuppressionEngine


# Keywords for message intent classification
CANNED_AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"our team will respond",
    r"automated assistant",
    r"automated reply",
    r"auto-reply",
    r"out of office",
    r"aapki jaankari ke liye",
    r"shukriya.*team tak pahuncha",
    r"main ek automated assistant hoon",
]

STOP_HOSTILE_PATTERNS = [
    r"\bstop\b",
    r"not interested",
    r"useless spam",
    r"bothering me",
    r"unsubscribe",
    r"don't message",
    r"dont message",
    r"leave me alone",
    r"spam",
    r"abuse",
]

AFFIRMATIVE_PATTERNS = [
    r"\byes\b",
    r"lets do it",
    r"let's do it",
    r"go ahead",
    r"proceed",
    r"send me",
    r"send the",
    r"\bconfirm\b",
    r"\bokay\b",
    r"\bok\b",
    r"\bsure\b",
    r"whats next",
    r"what's next",
]

OFF_TOPIC_PATTERNS = [
    r"\bgst\b",
    r"tax filing",
    r"income tax",
    r"weather today",
    r"cricket score",
]

OBJECTION_PATTERNS = [
    r"too busy",
    r"not right now",
    r"maybe next week",
    r"too expensive",
]


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    turn_number: int = 1
    state: str = "pitch"  # pitch, action_execution, auto_reply_waiting, terminated
    canned_auto_reply_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    last_action: str | None = None


class ConversationStateMachine:
    """
    Stateful multi-turn conversation manager.
    Tracks conversations per conversation_id and executes deterministic turn transitions.
    """

    def __init__(self):
        self._conversations: dict[str, ConversationState] = {}
        self._merchant_canned_counts: dict[str, int] = {}

    def get_or_create_state(
        self, conversation_id: str, merchant_id: str | None = None, customer_id: str | None = None
    ) -> ConversationState:
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = ConversationState(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
            )
        return self._conversations[conversation_id]

    def handle_reply(
        self,
        conversation_id: str,
        merchant_id: str | None,
        customer_id: str | None,
        from_role: str,
        message: str,
        received_at: str,
        turn_number: int,
        store: ContextStore,
        suppression: SuppressionEngine,
    ) -> dict[str, Any]:
        """
        Processes an incoming turn reply and returns the official response dict:
        {"action": "send"|"wait"|"end", "body": ..., "cta": ..., "wait_seconds": ..., "rationale": ...}
        """
        conv = self.get_or_create_state(conversation_id, merchant_id, customer_id)
        conv.turn_number = turn_number
        conv.history.append({"from": from_role, "msg": message, "ts": received_at})

        msg_lower = message.lower().strip()

        # 1. Check Canned Auto-Reply Pattern
        is_canned = any(re.search(pat, msg_lower) for pat in CANNED_AUTO_REPLY_PATTERNS)
        if not is_canned and len(conv.history) >= 2:
            # Check if merchant repeated the exact same message body twice
            last_merchant_msgs = [
                h["msg"].strip() for h in conv.history if h["from"] == from_role
            ]
            if len(last_merchant_msgs) >= 2 and last_merchant_msgs[-1] == last_merchant_msgs[-2]:
                is_canned = True

        m_key = merchant_id or conversation_id

        if is_canned:
            canned_count = self._merchant_canned_counts.get(m_key, 0) + 1
            self._merchant_canned_counts[m_key] = canned_count
            conv.canned_auto_reply_count = canned_count

            if canned_count == 1:
                conv.state = "pitch"
                conv.last_action = "send"
                return {
                    "action": "send",
                    "body": "Looks like an auto-reply. When the owner sees this, just reply 'Yes' for the details.",
                    "cta": "binary_yes_no",
                    "rationale": "Detected merchant auto-reply once; sent explicit prompt for owner review.",
                }
            elif canned_count == 2:
                conv.state = "auto_reply_waiting"
                conv.last_action = "wait"
                return {
                    "action": "wait",
                    "wait_seconds": 14400,
                    "rationale": "Detected merchant auto-reply twice; backing off 4 hours to wait for owner.",
                }
            else:
                conv.state = "terminated"
                conv.last_action = "end"
                return {
                    "action": "end",
                    "rationale": "Detected auto-reply 3+ times in a row; closing conversation to prevent burning turns.",
                }

        # Reset canned count if a real message arrived
        self._merchant_canned_counts[m_key] = 0
        conv.canned_auto_reply_count = 0

        # 2. Check STOP / Hostile / Opt-Out Pattern
        is_stop = any(re.search(pat, msg_lower) for pat in STOP_HOSTILE_PATTERNS)
        if is_stop:
            conv.state = "terminated"
            conv.last_action = "end"
            if merchant_id:
                suppression.opt_out_merchant(merchant_id)
            if customer_id:
                suppression.opt_out_customer(customer_id)
            return {
                "action": "end",
                "rationale": "Merchant/customer explicitly requested opt-out or expressed hostility; closing conversation and applying suppression.",
            }

        # 3. Check Off-Topic Question
        is_off_topic = any(re.search(pat, msg_lower) for pat in OFF_TOPIC_PATTERNS)
        if is_off_topic:
            conv.last_action = "send"
            return {
                "action": "send",
                "body": "I'll have to leave GST filing to your CA — that's outside what I can help with directly. Coming back to our discussion — want me to proceed with the draft?",
                "cta": "open_ended",
                "rationale": "Out-of-scope ask politely declined; redirected back to core trigger thread without losing context.",
            }

        # 4. Check Affirmative Response ("Yes", "Lets do it")
        is_affirmative = any(re.search(pat, msg_lower) for pat in AFFIRMATIVE_PATTERNS)
        if is_affirmative or conv.state == "action_execution":
            conv.state = "action_execution"
            conv.last_action = "send"
            return {
                "action": "send",
                "body": "Sending the details now. Draft prepared for review — reply CONFIRM to publish.",
                "cta": "binary_confirm_cancel",
                "rationale": "Honoring merchant commitment; proceeding directly to action execution without re-qualifying.",
            }

        # 5. Check Specific Objection / Timing Request
        is_objection = any(re.search(pat, msg_lower) for pat in OBJECTION_PATTERNS)
        if is_objection:
            conv.last_action = "wait"
            return {
                "action": "wait",
                "wait_seconds": 86400,
                "rationale": "Merchant requested timing delay; backing off 24 hours.",
            }

        # 6. Default engaged response fallback
        conv.last_action = "send"
        return {
            "action": "send",
            "body": "Got it! Here is the next step for your review. Want me to proceed?",
            "cta": "open_ended",
            "rationale": "Acknowledged incoming turn; advancing conversation towards resolution.",
        }

    def reset_conversation(self, conversation_id: str):
        """Clear state for a specific conversation_id."""
        conv = self._conversations.pop(conversation_id, None)
        if conv and conv.merchant_id:
            self._merchant_canned_counts.pop(conv.merchant_id, None)
        self._merchant_canned_counts.pop(conversation_id, None)


    def clear_all(self):
        """Clear all conversation states and merchant canned counts."""
        self._conversations.clear()
        self._merchant_canned_counts.clear()
