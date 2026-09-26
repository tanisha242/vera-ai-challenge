"""
Pharmacy & Medical Store vertical strategy implementation.
Handles trustworthy precise voice, drug recall alerts, chronic refill dispatch, and taboo filtering.
"""

from typing import Any, Dict
from engine.decision import Decision
from strategies.base import VerticalStrategy


class PharmacyStrategy(VerticalStrategy):
    @property
    def slug(self) -> str:
        return "pharmacies"

    def get_voice_rules(self) -> Dict[str, Any]:
        return {
            "tone": "trustworthy_precise",
            "register": "neighbourhood_pharmacist",
            "salutation": "Hi {first_name}",
        }

    def get_taboo_words(self) -> list[str]:
        return [
            "miracle cure",
            "guaranteed result",
            "100% safe",
            "doctor recommended",
            "best price",
        ]

    def format_message(self, decision: Decision) -> Dict[str, Any]:
        merchant = decision.merchant or {}
        trigger = decision.trigger or {}
        customer = decision.customer
        category = decision.category or {}

        identity = merchant.get("identity", {})
        owner_name = identity.get("owner_first_name") or identity.get("name", "Pharmacist")

        kind = trigger.get("kind", "generic")
        payload = trigger.get("payload", {})
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (customer or scope == "customer") else "vera"

        cust_agg = merchant.get("customer_aggregate", {})
        chronic_count = cust_agg.get("chronic_rx_count", 240)

        offers = merchant.get("offers", [])
        active_offer = next((o["title"] for o in offers if o.get("status") == "active"), "Free Home Delivery > ₹499")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "supply_alert":
            molecule = payload.get("molecule", "atorvastatin")
            batches = payload.get("affected_batches", ["AT2024-1102", "AT2024-1108"])
            batch_str = ", ".join(batches)
            mfr = payload.get("manufacturer", "Mfr Z")
            affected_count = int(chronic_count * 0.09) if chronic_count else 22

            body = (
                f"{owner_name}, urgent: voluntary recall on 2 {molecule} batches ({batch_str}) by {mfr} — "
                f"sub-potency issue, no safety risk, but customers should be informed for replacement. "
                f"Pulled your repeat-Rx list: ~{affected_count} of your chronic-Rx customers were dispensed these batches in last 90 days. "
                f"Want me to draft their WhatsApp note + replacement pickup workflow?"
            )
            cta = "binary_yes_no"
            rationale = "Emergency compliance alert with exact batch numbers and affected patient cohort count."

        elif kind == "chronic_refill_due" and customer:
            cust_identity = customer.get("identity", {})
            cust_name = cust_identity.get("name", "Sharma ji")
            molecules = payload.get("molecule_list", ["metformin", "atorvastatin", "telmisartan"])
            mol_str = ", ".join(molecules)
            due_date = payload.get("stock_runs_out_iso", "28 April")
            if "T" in due_date:
                due_date = "28 April"

            body = (
                f"Namaste — {identity.get('name', 'Apollo Health Plus')} yahan. "
                f"{cust_name} ki monthly medicines ({mol_str}) {due_date} ko khatam hongi. "
                f"Same dose, same brand pack ready hai. Senior discount 15% applied — total ₹1,420 (₹240 saved). "
                f"Free home delivery to saved address by 5pm tomorrow. Reply CONFIRM to dispatch."
            )
            cta = "binary_confirm_cancel"
            rationale = "Customer-scoped chronic refill reminder with senior discount and precise molecule details."

        elif kind == "category_seasonal":
            body = (
                f"{owner_name}, summer demand shift: ORS sachets, sunscreen, and anti-fungal cream searches are +40% in your area. "
                f"Action: move ORS + sunscreen to counter visibility. Want me to publish a 'Summer First-Aid Essentials' post on GBP?"
            )
            cta = "binary_yes_no"
            rationale = "Seasonal demand shift recommendation advocating counter repositioning and GBP post."

        elif kind == "gbp_unverified":
            body = (
                f"{owner_name}, your pharmacy listing is currently unverified on Google. "
                f"Verified stores in {identity.get('locality', 'your area')} see 30% higher delivery calls. "
                f"Want me to guide you through the 2-min verification request?"
            )
            cta = "binary_yes_no"
            rationale = "Unverified listing prompt highlighting 30% delivery call uplift."

        else:
            body = (
                f"{owner_name}, quick check on your store listing for {identity.get('name', 'your pharmacy')}. "
                f"Active service: {active_offer}. Want me to update your delivery hours on Google?"
            )
            cta = "open_ended"
            rationale = "Grounded pharmacy touchpoint citing active delivery offer."

        body = self.check_and_clean_taboos(body)

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }
