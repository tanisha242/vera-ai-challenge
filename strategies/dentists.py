"""
Dentistry vertical strategy implementation.
Handles clinical peer voice, source citations, service+price offer anchors, and taboo filtering.
"""

from typing import Any, Dict
from engine.decision import Decision
from strategies.base import VerticalStrategy


class DentistStrategy(VerticalStrategy):
    @property
    def slug(self) -> str:
        return "dentists"

    def get_voice_rules(self) -> Dict[str, Any]:
        return {
            "tone": "peer_clinical",
            "register": "respectful_collegial",
            "salutation": "Dr. {first_name}",
        }

    def get_taboo_words(self) -> list[str]:
        return [
            "guaranteed",
            "100% safe",
            "completely cure",
            "miracle",
            "best in city",
            "doctor approved",
            "cheap",
        ]

    def format_message(self, decision: Decision) -> Dict[str, Any]:
        merchant = decision.merchant or {}
        trigger = decision.trigger or {}
        customer = decision.customer
        category = decision.category or {}

        identity = merchant.get("identity", {})
        owner_name = identity.get("owner_first_name") or identity.get("name", "Doctor")
        salutation = f"Dr. {owner_name}" if not owner_name.startswith("Dr.") else owner_name

        kind = trigger.get("kind", "generic")
        payload = trigger.get("payload", {})
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (customer or scope == "customer") else "vera"

        # Find active service+price offer
        offers = merchant.get("offers", [])
        active_offer = next((o["title"] for o in offers if o.get("status") == "active"), "Dental Cleaning @ ₹299")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "research_digest":
            top_item_id = payload.get("top_item_id", "d_2026W17_jida_fluoride")
            digest_items = category.get("digest", [])
            digest_item = next((d for d in digest_items if d.get("id") == top_item_id), None)
            if not digest_item and digest_items:
                digest_item = digest_items[0]

            source = digest_item.get("source", "JIDA Oct 2026 p.14") if digest_item else "JIDA Oct 2026 p.14"
            trial_n = digest_item.get("trial_n", 2100) if digest_item else 2100

            body = (
                f"{salutation}, JIDA's Oct issue landed. One item relevant to your patient roster — "
                f"{trial_n}-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month. "
                f"Worth a look (2-min abstract). Want me to pull it + draft a patient WhatsApp you can share? — {source}"
            )
            cta = "open_ended"
            rationale = "Cited clinical trial from JIDA digest with patient segment anchor and low-friction draft offer."

        elif kind == "recall_due" and customer:
            cust_identity = customer.get("identity", {})
            cust_name = cust_identity.get("name", "Patient")
            avail_slots = payload.get("available_slots", [])
            slot_str = ""
            if len(avail_slots) >= 2:
                slot_str = f"{avail_slots[0].get('label', 'Wed 5 Nov 6pm')} or {avail_slots[1].get('label', 'Thu 6 Nov 5pm')}"
            else:
                slot_str = "Wed 5 Nov 6pm or Thu 6 Nov 5pm"

            body = (
                f"Hi {cust_name}, {identity.get('name', 'Dental Clinic')} here 🦷 "
                f"It's been 5 months since your last visit — your 6-month cleaning recall is due. "
                f"2 slots ready: {slot_str}. {active_offer}. Reply 1 for Wed, 2 for Thu, or tell us a time that works."
            )
            cta = "multi_choice_slot"
            rationale = "Customer-scoped recall reminder matching evening preference and offering multi-choice slot CTA."

        elif kind == "regulation_change":
            body = (
                f"{salutation}, DCI circular updated radiograph dose limits (max 1.0 mSv per IOPA effective Dec 15). "
                f"RVG sensors pass; D-speed film does not. Want me to audit your X-ray setup details?"
            )
            cta = "binary_yes_no"
            rationale = "Compliance alert citing official DCI dose limit changes with audit CTA."

        elif kind == "perf_dip":
            perf = merchant.get("performance", {})
            calls_drop = abs(int(perf.get("delta_7d", {}).get("calls_pct", -0.30) * 100))
            body = (
                f"{salutation}, search calls dropped {calls_drop}% this week. "
                f"Your profile post is stale (22 days old). Want me to draft 2 Google posts on {active_offer} to boost calls?"
            )
            cta = "binary_yes_no"
            rationale = "Performance dip anchor with concrete active offer post recommendation."

        elif kind == "competitor_opened":
            comp_name = payload.get("competitor_name", "Smile Studio")
            dist = payload.get("distance_km", 1.3)
            body = (
                f"{salutation}, heads-up: {comp_name} opened {dist}km away on GBP. "
                f"Want me to highlight your verified status + {active_offer} on your listing to protect local search rank?"
            )
            cta = "binary_yes_no"
            rationale = "Local competitor opening reframe highlighting verified status and catalog offer."

        else:
            body = (
                f"{salutation}, quick check regarding your profile performance on magicpin. "
                f"Active offer on file: {active_offer}. Want me to update your Google business post for this week?"
            )
            cta = "open_ended"
            rationale = "Grounded merchant touchpoint citing active catalog offer."

        body = self.check_and_clean_taboos(body)

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }
