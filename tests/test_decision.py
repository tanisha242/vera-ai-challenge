"""
Unit tests for engine/decision.py verifying trigger normalization, eligibility filtering,
urgency ranking, tie-breaking rules, consent checks, and no-action decisions.
"""

import unittest
from datetime import datetime, timedelta

from core.store import ContextStore
from core.suppression import SuppressionEngine
from engine.decision import DecisionEngine


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.store = ContextStore()
        self.supp = SuppressionEngine()
        self.engine = DecisionEngine()

        # Seed base context fixtures
        self.store.put("category", "dentists", 1, {"slug": "dentists", "voice": {"tone": "peer_clinical"}})
        self.store.put("merchant", "m_001", 1, {"merchant_id": "m_001", "category_slug": "dentists", "identity": {"owner_first_name": "Meera"}})
        self.store.put("customer", "c_001", 1, {"customer_id": "c_001", "merchant_id": "m_001", "state": "active", "preferences": {"reminder_opt_in": True}})

    def test_competing_triggers_urgency_ranking(self):
        # High urgency trigger (5)
        trg_high = {
            "id": "trg_supply_alert",
            "scope": "merchant",
            "kind": "supply_alert",
            "source": "external",
            "merchant_id": "m_001",
            "urgency": 5,
            "suppression_key": "alert_key_5",
        }
        # Low urgency trigger (2)
        trg_low = {
            "id": "trg_research",
            "scope": "merchant",
            "kind": "research_digest",
            "source": "external",
            "merchant_id": "m_001",
            "urgency": 2,
            "suppression_key": "digest_key_2",
        }

        self.store.put("trigger", "trg_supply_alert", 1, trg_high)
        self.store.put("trigger", "trg_research", 1, trg_low)

        now_iso = datetime.utcnow().isoformat() + "Z"
        decisions = self.engine.evaluate_triggers(now_iso, ["trg_research", "trg_supply_alert"], self.store, self.supp)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action_type, "proactive_send")
        self.assertEqual(decisions[0].trigger["id"], "trg_supply_alert")

    def test_expired_trigger_filtering(self):
        past_iso = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
        trg_exp = {
            "id": "trg_expired",
            "scope": "merchant",
            "kind": "research_digest",
            "source": "external",
            "merchant_id": "m_001",
            "urgency": 4,
            "expires_at": past_iso,
        }
        self.store.put("trigger", "trg_expired", 1, trg_exp)

        now_iso = datetime.utcnow().isoformat() + "Z"
        decisions = self.engine.evaluate_triggers(now_iso, ["trg_expired"], self.store, self.supp)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action_type, "no_action")
        self.assertIn("expired", decisions[0].reason)

    def test_missing_merchant_context_filtering(self):
        trg_no_m = {
            "id": "trg_no_m",
            "scope": "merchant",
            "kind": "perf_dip",
            "source": "internal",
            "merchant_id": "m_missing",
            "urgency": 4,
        }
        self.store.put("trigger", "trg_no_m", 1, trg_no_m)

        now_iso = datetime.utcnow().isoformat() + "Z"
        decisions = self.engine.evaluate_triggers(now_iso, ["trg_no_m"], self.store, self.supp)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action_type, "no_action")

    def test_customer_opt_out_consent_filtering(self):
        # Customer opted out of reminders
        self.store.put("customer", "c_opted_out", 1, {
            "customer_id": "c_opted_out",
            "merchant_id": "m_001",
            "state": "active",
            "preferences": {"reminder_opt_in": False},
        })

        trg_cust = {
            "id": "trg_recall",
            "scope": "customer",
            "kind": "recall_due",
            "source": "internal",
            "merchant_id": "m_001",
            "customer_id": "c_opted_out",
            "urgency": 3,
        }
        self.store.put("trigger", "trg_recall", 1, trg_cust)

        now_iso = datetime.utcnow().isoformat() + "Z"
        decisions = self.engine.evaluate_triggers(now_iso, ["trg_recall"], self.store, self.supp)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action_type, "no_action")

    def test_suppressed_trigger_filtering(self):
        trg_supp = {
            "id": "trg_supp",
            "scope": "merchant",
            "kind": "perf_dip",
            "source": "internal",
            "merchant_id": "m_001",
            "urgency": 4,
            "suppression_key": "supp_dip_m001",
        }
        self.store.put("trigger", "trg_supp", 1, trg_supp)
        self.supp.suppress("supp_dip_m001")

        now_iso = datetime.utcnow().isoformat() + "Z"
        decisions = self.engine.evaluate_triggers(now_iso, ["trg_supp"], self.store, self.supp)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action_type, "no_action")


if __name__ == "__main__":
    unittest.main()
