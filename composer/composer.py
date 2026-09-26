"""
Deterministic MessageComposer for magicpin AI Challenge (Vera).
Assembles factually-grounded proactive messages using vertical strategies,
sanitizes outputs, enforces CTA constraints, and formats rationales.
"""

import re
from typing import Any, Dict, Optional, Set
from engine.decision import Decision
from strategies import get_strategy
from composer.llm_composer import LLMComposer


ALLOWED_CTAS: Set[str] = {
    "open_ended",
    "binary_yes_no",
    "binary_confirm_cancel",
    "multi_choice_slot",
    "none",
}


class MessageComposer:
    """
    Message composer supporting deterministic vertical strategies with an optional
    LLM-assisted composition pathway.
    """

    def __init__(self, llm_composer: Optional[LLMComposer] = None):
        self.llm_composer = llm_composer or LLMComposer()

    def compose_proactive_message(self, decision: Decision) -> Dict[str, Any]:
        """
        Main entry point for proactive message composition.

        Returns dictionary matching official schema:
        {
            "body": str,
            "cta": str,
            "send_as": "vera" | "merchant_on_behalf",
            "suppression_key": str,
            "rationale": str
        }
        """
        if decision.action_type == "no_action" or not decision.merchant or not decision.trigger:
            return {
                "body": "",
                "cta": "none",
                "send_as": "vera",
                "suppression_key": decision.suppression_key or "",
                "rationale": decision.reason or "No action required.",
            }

        # 1. Try optional LLM composition if enabled and available
        if self.llm_composer and self.llm_composer.is_available():
            llm_result = self.llm_composer.compose(decision)
            if llm_result:
                return llm_result

        # 2. Fallback to deterministic vertical strategy composition
        merchant = decision.merchant
        category = decision.category or {}
        cat_slug = category.get("slug") or merchant.get("category_slug", "dentists")

        # Fetch vertical strategy
        strategy = get_strategy(cat_slug)

        # Format message via vertical strategy
        formatted = strategy.format_message(decision)

        # Sanitize body (strip bare http/https URLs per WhatsApp compliance)
        body = formatted.get("body", "")
        body_clean = re.sub(r"https?://\S+", "", body).strip()

        # Validate CTA
        cta = formatted.get("cta", "open_ended")
        if cta not in ALLOWED_CTAS:
            cta = "open_ended"

        # Validate send_as
        send_as = formatted.get("send_as", "vera")
        if send_as not in ("vera", "merchant_on_behalf"):
            send_as = "vera"

        return {
            "body": body_clean,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": formatted.get("suppression_key") or decision.suppression_key,
            "rationale": formatted.get("rationale") or decision.reason,
        }


def compose_proactive_message(decision: Decision) -> Dict[str, Any]:
    """Standalone module function helper."""
    composer = MessageComposer()
    return composer.compose_proactive_message(decision)
