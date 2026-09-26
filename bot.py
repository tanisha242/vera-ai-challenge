"""
Standard challenge submission module exporting compose() and respond() functions,
plus re-exporting FastAPI app for server launch.
"""

from typing import Any, Dict, Optional
from datetime import datetime

from main import app
from engine.decision import Decision, DecisionEngine
from composer.composer import MessageComposer
from core.store import ContextStore
from core.suppression import SuppressionEngine


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Standalone composition function matching challenge-brief.md §7.1:
    compose(category, merchant, trigger, customer?) -> dict

    Returns dict with keys: body, cta, send_as, suppression_key, rationale.
    Deterministic, completes in < 30s.
    """
    supp_key = trigger.get("suppression_key") or f"{trigger.get('kind', 'gen')}:{merchant.get('merchant_id', '')}"
    kind = trigger.get("kind", "generic")

    decision = Decision(
        action_type="proactive_send",
        trigger=trigger,
        merchant=merchant,
        category=category,
        customer=customer,
        reason=f"Direct compose call for trigger '{trigger.get('id', 'T01')}' (kind={kind}).",
        suppression_key=supp_key,
        template_name=f"vera_{kind}_v1",
        template_params=[
            merchant.get("identity", {}).get("owner_first_name")
            or merchant.get("identity", {}).get("name", "Merchant"),
            trigger.get("id", ""),
        ],
    )

    composer = MessageComposer()
    return composer.compose_proactive_message(decision)


def respond(state: Dict[str, Any], merchant_message: str) -> Dict[str, Any]:
    """
    Optional multi-turn conversation response handler matching challenge-brief.md §7.4:
    respond(state, merchant_message) -> dict
    """
    from engine.state_machine import ConversationStateMachine

    sm = ConversationStateMachine()
    dummy_store = ContextStore()
    dummy_supp = SuppressionEngine()

    conv_id = state.get("conversation_id", "conv_standalone")
    turn_num = state.get("turn_number", 2)
    merchant_id = state.get("merchant_id")

    return sm.handle_reply(
        conversation_id=conv_id,
        merchant_id=merchant_id,
        customer_id=None,
        from_role="merchant",
        message=merchant_message,
        received_at=datetime.utcnow().isoformat() + "Z",
        turn_number=turn_num,
        store=dummy_store,
        suppression=dummy_supp,
    )
