"""
VeraEngine orchestration controller linking ContextStore, SuppressionEngine,
DecisionEngine, ConversationStateMachine, and MessageComposer.
Provides clean internal interfaces for tick and reply processing.
"""

from typing import Any, List

from core.store import ContextStore, store as global_store
from core.suppression import SuppressionEngine, suppression_engine as global_suppression
from engine.decision import DecisionEngine, Decision
from engine.state_machine import ConversationStateMachine
from composer.composer import MessageComposer


class VeraEngine:
    """
    Central orchestration engine for Vera.
    Keeps engine components decoupled from HTTP frameworks for standalone unit testing.
    """

    def __init__(
        self,
        store: ContextStore | None = None,
        suppression: SuppressionEngine | None = None,
    ):
        self.store = store or global_store
        self.suppression = suppression or global_suppression
        self.decision_engine = DecisionEngine()
        self.state_machine = ConversationStateMachine()
        self.composer = MessageComposer()

    def teardown(self):
        """Wipe all stored contexts, suppression records, and conversation states."""
        self.store.clear()
        self.suppression.clear()
        self.state_machine.clear_all()

    def process_tick(
        self, now_iso: str, available_trigger_ids: list[str]
    ) -> list[dict[str, Any]]:
        """
        Process a /v1/tick request and return list of official action dicts.
        If no action is appropriate, returns an empty list.
        """
        decisions: list[Decision] = self.decision_engine.evaluate_triggers(
            now_iso=now_iso,
            available_trigger_ids=available_trigger_ids,
            store=self.store,
            suppression=self.suppression,
        )

        actions: list[dict[str, Any]] = []

        for dec in decisions:
            if dec.action_type != "proactive_send" or not dec.trigger or not dec.merchant:
                continue

            # Compose message via MessageComposer
            composed = self.composer.compose_proactive_message(dec)
            if not composed.get("body"):
                continue

            trg = dec.trigger
            merchant = dec.merchant
            mid = merchant["merchant_id"]
            cid = dec.customer.get("customer_id") if dec.customer else trg.get("customer_id")

            action_dict = {
                "conversation_id": f"conv_{mid}_{trg['id']}",
                "merchant_id": mid,
                "customer_id": cid,
                "send_as": composed["send_as"],
                "trigger_id": trg["id"],
                "template_name": dec.template_name,
                "template_params": dec.template_params,
                "body": composed["body"],
                "cta": composed["cta"],
                "suppression_key": composed["suppression_key"],
                "rationale": composed["rationale"],
            }

            # Mark suppression key active
            self.suppression.suppress(composed["suppression_key"], trg.get("expires_at"))
            actions.append(action_dict)

        return actions

    def process_reply(
        self,
        conversation_id: str,
        merchant_id: str | None,
        customer_id: str | None,
        from_role: str,
        message: str,
        received_at: str,
        turn_number: int,
    ) -> dict[str, Any]:
        """
        Process an incoming turn reply and return official reply response dict.
        """
        return self.state_machine.handle_reply(
            conversation_id=conversation_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            from_role=from_role,
            message=message,
            received_at=received_at,
            turn_number=turn_number,
            store=self.store,
            suppression=self.suppression,
        )
