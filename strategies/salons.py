"""
Salon & Beauty vertical strategy implementation.
Handles warm practical voice, service+price mapping, bridal prep timing, and taboo filtering.
"""

from typing import Any, Dict
from engine.decision import Decision
from strategies.base import VerticalStrategy


class SalonStrategy(VerticalStrategy):
    @property
    def slug(self) -> str:
        return "salons"

    def get_voice_rules(self) -> Dict[str, Any]:
        return {
            "tone": "warm_practical",
            "register": "approachable_expert",
            "salutation": "Hi {first_name}",
        }

    def get_taboo_words(self) -> list[str]:
        return [
            "guaranteed glow",
            "permanent results",
            "instant transformation",
            "miracle",
            "best in city",
            "cheap",
        ]

    def format_message(self, decision: Decision) -> Dict[str, Any]:
        merchant = decision.merchant or {}
        trigger = decision.trigger or {}
        customer = decision.customer
        category = decision.category or {}

        identity = merchant.get("identity", {})
        owner_name = identity.get("owner_first_name") or identity.get("name", "Team")
        locality = identity.get("locality", "")

        kind = trigger.get("kind", "generic")
        payload = trigger.get("payload", {})
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (customer or scope == "customer") else "vera"

        offers = merchant.get("offers", [])
        active_offer = next((o["title"] for o in offers if o.get("status") == "active"), "Haircut @ ₹99")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "curious_ask_due":
            body = (
                f"Hi {owner_name}! Quick check — what service has been most asked-for this week at {identity.get('name', 'your salon')}? "
                f"I'll turn the answer into a Google post + a 4-line WhatsApp reply you can use for customer pricing questions. Takes 2 min."
            )
            cta = "open_ended"
            rationale = "Operator curiosity ask with reciprocity offer (drafting Google post + WhatsApp reply)."

        elif kind in ("wedding_package_followup", "bridal_followup") and customer:
            cust_identity = customer.get("identity", {})
            cust_name = cust_identity.get("name", "Customer")
            days_to_wedding = payload.get("days_to_wedding", 196)
            body = (
                f"Hi {cust_name} 💍 {owner_name} from {identity.get('name', 'Studio11')} here. "
                f"{days_to_wedding} days to your wedding — perfect window to start the 30-day skin-prep program. "
                f"{active_offer}. Want me to block your preferred Saturday 4pm slot for your first session next week?"
            )
            cta = "binary_yes_no"
            rationale = "Customer-scoped bridal follow-up anchoring on days-to-wedding countdown and Saturday slot proposal."

        elif kind == "festival_upcoming":
            fest = payload.get("festival", "Diwali")
            body = (
                f"Hi {owner_name}! {fest} is coming up. "
                f"Bridal & festive prep searches in {locality} usually double in the next 4 weeks. "
                f"Want me to set up a festive promo post featuring '{active_offer}'?"
            )
            cta = "binary_yes_no"
            rationale = "Festive planning nudge matching sublocality demand trends and active catalog offer."

        elif kind == "winback_eligible":
            days_since = payload.get("days_since_expiry", 38)
            body = (
                f"Hi {owner_name}, your Pro subscription ended {days_since} days ago. "
                f"Profile updates are paused, but your locality search volume is up. Want me to reactivate your listing with {active_offer}?"
            )
            cta = "binary_yes_no"
            rationale = "Winback outreach linking post-expiry days to active catalog offer."

        else:
            body = (
                f"Hi {owner_name}! Noticed good activity on your listing in {locality}. "
                f"Your offer '{active_offer}' is live. Want me to draft a weekend special post to boost walk-ins?"
            )
            cta = "open_ended"
            rationale = "Grounded salon nudge leveraging locality and active catalog offer."

        body = self.check_and_clean_taboos(body)

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }
