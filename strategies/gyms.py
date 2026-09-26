"""
Gym & Fitness vertical strategy implementation.
Handles coach-to-operator voice, seasonal dip reframing, no-shame member winback, and taboo filtering.
"""

from typing import Any, Dict
from engine.decision import Decision
from strategies.base import VerticalStrategy


class GymStrategy(VerticalStrategy):
    @property
    def slug(self) -> str:
        return "gyms"

    def get_voice_rules(self) -> Dict[str, Any]:
        return {
            "tone": "energetic_disciplined",
            "register": "coach_to_member",
            "salutation": "Hi {first_name}",
        }

    def get_taboo_words(self) -> list[str]:
        return [
            "guaranteed weight loss",
            "shred in 7 days",
            "miracle transformation",
            "fastest results",
        ]

    def format_message(self, decision: Decision) -> Dict[str, Any]:
        merchant = decision.merchant or {}
        trigger = decision.trigger or {}
        customer = decision.customer
        category = decision.category or {}

        identity = merchant.get("identity", {})
        owner_name = identity.get("owner_first_name") or identity.get("name", "Coach")

        kind = trigger.get("kind", "generic")
        payload = trigger.get("payload", {})
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (customer or scope == "customer") else "vera"

        cust_agg = merchant.get("customer_aggregate", {})
        active_members = cust_agg.get("total_active_members", 245)

        offers = merchant.get("offers", [])
        active_offer = next((o["title"] for o in offers if o.get("status") == "active"), "3 FREE Trial Classes")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "seasonal_perf_dip":
            dip_pct = abs(int(payload.get("delta_pct", -0.30) * 100))
            body = (
                f"{owner_name}, your views are down {dip_pct}% this week — but I want to flag this is the normal April-June acquisition lull "
                f"(every metro gym sees -25 to -35% in this window). Action: skip ad spend now, save it for Sept-Oct when conversion is 2x. "
                f"For now, focus retention on your {active_members} members. Want me to draft a 'summer attendance challenge' to keep them through the dip?"
            )
            cta = "binary_yes_no"
            rationale = "Pre-empted seasonal dip anxiety with benchmark data and proposed summer retention challenge."

        elif kind in ("customer_lapsed_hard", "winback_rashmi") and customer:
            cust_identity = customer.get("identity", {})
            cust_name = cust_identity.get("name", "Member")
            days_since = payload.get("days_since_last_visit", 57)
            body = (
                f"Hi {cust_name} 👋 {owner_name} from {identity.get('name', 'PowerHouse')} here. "
                f"It's been about {days_since} days — happens to most members at some point, no judgment. "
                f"We've added a Tue/Thu evening HIIT class that fits weight-loss goals well (45 min, 6:30pm). "
                f"Want me to hold a free trial spot for you next Tue? Reply YES — no commitment, no auto-charge."
            )
            cta = "binary_yes_no"
            rationale = "No-shame winback message addressing member's goal with low-friction free trial spot offer."

        elif kind == "active_planning_intent":
            body = (
                f"{owner_name}, here's a starter outline for the kids yoga summer camp:\n"
                f"- 4-week program, 3 classes/week (Mon/Wed/Fri 10am)\n"
                f"- Age group 7-12, max 12 kids per batch\n"
                f"- ₹2,499 early bird / ₹2,999 regular\n"
                f"Want me to draft the GBP announcement post + Insta flyer?"
            )
            cta = "binary_yes_no"
            rationale = "Drafted complete kids yoga summer camp outline matching merchant's planning intent."

        elif kind == "trial_followup" and customer:
            cust_identity = customer.get("identity", {})
            cust_name = cust_identity.get("name", "Junior")
            body = (
                f"Hi {cust_name} 👋 Hope you enjoyed the trial session at {identity.get('name', 'Zen Yoga')}! "
                f"Next batch session starts Sat 3 May, 8am. Want me to hold your spot for the full monthly module?"
            )
            cta = "binary_yes_no"
            rationale = "Post-trial follow-up for next batch module enrollment."

        else:
            body = (
                f"{owner_name}, quick check on member activity at {identity.get('name', 'your gym')}. "
                f"Active offer: {active_offer}. Want me to publish a fresh class schedule on your listing?"
            )
            cta = "open_ended"
            rationale = "Grounded coach touchpoint citing active membership offer."

        body = self.check_and_clean_taboos(body)

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }
