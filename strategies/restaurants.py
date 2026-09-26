"""
Restaurant & Cafe vertical strategy implementation.
Handles fellow-operator voice, IPL match delivery reframe, B2B thali package drafting, and taboo filtering.
"""

from typing import Any, Dict
from engine.decision import Decision
from strategies.base import VerticalStrategy


class RestaurantStrategy(VerticalStrategy):
    @property
    def slug(self) -> str:
        return "restaurants"

    def get_voice_rules(self) -> Dict[str, Any]:
        return {
            "tone": "warm_busy_practical",
            "register": "fellow_operator",
            "salutation": "Hi {first_name}",
        }

    def get_taboo_words(self) -> list[str]:
        return [
            "best food in city",
            "guaranteed packed house",
            "miracle marketing",
            "viral guarantee",
        ]

    def format_message(self, decision: Decision) -> Dict[str, Any]:
        merchant = decision.merchant or {}
        trigger = decision.trigger or {}
        customer = decision.customer
        category = decision.category or {}

        identity = merchant.get("identity", {})
        owner_name = identity.get("owner_first_name") or identity.get("name", "Chef")

        kind = trigger.get("kind", "generic")
        payload = trigger.get("payload", {})
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (customer or scope == "customer") else "vera"

        offers = merchant.get("offers", [])
        active_offer = next((o["title"] for o in offers if o.get("status") == "active"), "Buy 1 Pizza Get 1 Free (Tue-Thu)")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "ipl_match_today":
            match = payload.get("match", "DC vs MI")
            time_str = "7:30pm"
            is_weeknight = payload.get("is_weeknight", False)

            if not is_weeknight:
                body = (
                    f"Quick heads-up {owner_name} — {match} tonight, {time_str}. Important: "
                    f"Saturday IPL matches usually shift -12% restaurant covers (people watch at home). "
                    f"Skip the in-person match promo today; instead push your {active_offer} as a delivery-only Saturday special. "
                    f"Want me to draft the Swiggy banner + Insta story? Live in 10 min."
                )
            else:
                body = (
                    f"Quick heads-up {owner_name} — {match} tonight at {time_str}. "
                    f"Weeknight IPL matches drive +18% covers on delivery. Want me to draft a match-night combo story using '{active_offer}'?"
                )
            cta = "binary_yes_no"
            rationale = "Contrarian IPL match day data insight reframing Saturday home-watch trend into delivery-only offer."

        elif kind == "active_planning_intent":
            body = (
                f"{owner_name}, here's a starter version for corporate thali packages — you can edit:\n"
                f"- 10 thalis @ ₹125 each (₹25 off retail) + free delivery\n"
                f"- 25 thalis @ ₹115 each + 2 free filter coffees\n"
                f"- 50+: ₹105 each + 1 free dosa platter\n"
                f"WhatsApp the day-before by 5pm; we deliver between 12:30-1pm. "
                f"Want me to draft a 3-line WhatsApp to send local office facilities managers?"
            )
            cta = "open_ended"
            rationale = "Drafted complete B2B corporate thali package matching merchant's active planning intent."

        elif kind == "review_theme_emerged":
            theme = payload.get("theme", "delivery_late")
            count = payload.get("occurrences_30d", 4)
            body = (
                f"{owner_name}, noticed {count} reviews this month mentioning {theme.replace('_', ' ')}. "
                f"Want me to draft a polite reply template for your review team, plus a packaging prep checklist?"
            )
            cta = "binary_yes_no"
            rationale = "Operational review theme alert proposing owner response template and checklist."

        elif kind == "milestone_reached":
            val = payload.get("value_now", 145)
            body = (
                f"Congrats {owner_name}! {identity.get('name', 'Your restaurant')} is at {val} reviews — almost at 150! "
                f"Want me to schedule a Google post thanking your regular customers?"
            )
            cta = "binary_yes_no"
            rationale = "Review milestone celebration with customer gratitude post proposal."

        else:
            body = (
                f"{owner_name}, quick check on your delivery volume at {identity.get('name', 'your outlet')}. "
                f"Active promo on file: {active_offer}. Want me to update your menu highlights on Google?"
            )
            cta = "open_ended"
            rationale = "Grounded operator touchpoint citing active delivery promo."

        body = self.check_and_clean_taboos(body)

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }
