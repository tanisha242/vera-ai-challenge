"""
Deterministic DecisionEngine for magicpin AI Challenge (Vera).
Handles trigger normalization, eligibility filtering, priority ranking, and no-action decisions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from core.store import ContextStore
from core.suppression import SuppressionEngine


@dataclass
class Decision:
    """Internal decision object capturing candidate decision state."""

    action_type: str  # "proactive_send" or "no_action"
    trigger: Optional[dict[str, Any]] = None
    merchant: Optional[dict[str, Any]] = None
    category: Optional[dict[str, Any]] = None
    customer: Optional[dict[str, Any]] = None
    reason: str = ""
    suppression_key: str = ""
    template_name: str = "vera_generic_v1"
    template_params: List[str] = field(default_factory=list)


class DecisionEngine:
    """
    Evaluates available triggers against context store state, consent, expiration,
    and suppression constraints to select the best proactive action per merchant.
    """

    def evaluate_triggers(
        self,
        now_iso: str,
        available_trigger_ids: list[str],
        store: ContextStore,
        suppression: SuppressionEngine,
    ) -> list[Decision]:
        """
        Evaluates active trigger IDs and returns list of Decisions (one per merchant max).
        If no triggers are eligible, returns a single no-action Decision.
        """
        if not available_trigger_ids:
            return [
                Decision(
                    action_type="no_action",
                    reason="No available triggers provided in tick request.",
                )
            ]

        # Parse current simulated time
        try:
            now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        except Exception:
            now_dt = datetime.utcnow()

        eligible_candidates: list[tuple[tuple, dict, dict, dict, Optional[dict]]] = []

        for trg_id in available_trigger_ids:
            trg = store.get_payload("trigger", trg_id)
            if not trg:
                continue

            # 1. Expiration Check
            expires_at = trg.get("expires_at")
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if now_dt > exp_dt:
                        continue  # Expired trigger
                except Exception:
                    pass

            # 2. Merchant Context Check
            mid = trg.get("merchant_id")
            if not mid:
                continue
            merchant = store.get_payload("merchant", mid)
            if not merchant:
                continue

            # 3. Category Context Check
            cat_slug = merchant.get("category_slug")
            if not cat_slug:
                continue
            category = store.get_payload("category", cat_slug) or {"slug": cat_slug}

            # 4. Customer Context Check (for customer-scoped triggers)
            cid = trg.get("customer_id")
            customer = None
            if trg.get("scope") == "customer" or cid:
                if not cid:
                    continue
                customer = store.get_payload("customer", cid)
                if not customer:
                    continue
                # Verify customer belongs to this merchant
                c_mid = customer.get("merchant_id")
                if c_mid and c_mid != mid:
                    continue
                # Check customer state & preferences
                if customer.get("state") in ("churned", "lapsed_hard", "opted_out"):
                    continue
                prefs = customer.get("preferences", {})
                if prefs.get("reminder_opt_in") is False:
                    continue
                consent = customer.get("consent", {})
                if consent.get("opted_in") is False:
                    continue

            # 5. Opt-Out & Suppression Checks
            if suppression.is_merchant_opted_out(mid):
                continue
            if cid and suppression.is_customer_opted_out(cid):
                continue

            supp_key = suppression.get_trigger_suppression_key(trg)
            if suppression.is_suppressed(supp_key):
                continue

            # 6. Prioritization Tuple Construction
            # Priority components (higher values win):
            # (urgency, scope_weight, source_weight, exp_urgency, neg_id)
            urgency = int(trg.get("urgency", 1))
            scope_weight = 2 if trg.get("scope") == "customer" else 1
            source_weight = 2 if trg.get("source") == "internal" else 1

            # Tie-breaker key (higher tuple wins)
            # Python compares tuples element-by-element
            priority_key = (
                urgency,
                scope_weight,
                source_weight,
                # Use inverse trigger_id for stable ASCII ordering
                trg_id,
            )

            eligible_candidates.append((priority_key, trg, merchant, category, customer))

        if not eligible_candidates:
            return [
                Decision(
                    action_type="no_action",
                    reason="All available triggers were expired, missing context, or suppressed.",
                )
            ]

        # Group by merchant_id to ensure single action per merchant per tick
        by_merchant: dict[str, list[tuple]] = {}
        for candidate in eligible_candidates:
            mid = candidate[2]["merchant_id"]
            by_merchant.setdefault(mid, []).append(candidate)

        decisions: list[Decision] = []

        for mid, candidates in by_merchant.items():
            # Sort candidates by priority_key descending (highest urgency first)
            # For trigger_id string tie-breaking, we sort priority_key[:3] desc, priority_key[3] asc
            candidates.sort(
                key=lambda c: (c[0][0], c[0][1], c[0][2]),
                reverse=True,
            )
            top_candidate = candidates[0]
            _, trg, merchant, category, customer = top_candidate

            supp_key = suppression.get_trigger_suppression_key(trg)
            kind = trg.get("kind", "generic")

            decisions.append(
                Decision(
                    action_type="proactive_send",
                    trigger=trg,
                    merchant=merchant,
                    category=category,
                    customer=customer,
                    reason=f"Selected highest urgency trigger '{trg['id']}' (kind={kind}, urgency={trg.get('urgency', 1)}).",
                    suppression_key=supp_key,
                    template_name=f"vera_{kind}_v1",
                    template_params=[
                        merchant.get("identity", {}).get("owner_first_name")
                        or merchant.get("identity", {}).get("name", "Merchant"),
                        trg.get("id", ""),
                    ],
                )
            )

        return decisions
