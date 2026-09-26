"""
Unit tests for core/suppression.py testing trigger deduplication, opt-outs, TTL expiry,
and context update persistence.
"""

import unittest
from datetime import datetime, timedelta, timezone
from core.suppression import SuppressionEngine


class TestSuppressionEngine(unittest.TestCase):
    def setUp(self):
        self.supp = SuppressionEngine()

    def test_trigger_suppression_key_deduplication(self):
        trg1 = {"kind": "research_digest", "merchant_id": "m_001", "suppression_key": "supp_r_001"}
        key = self.supp.get_trigger_suppression_key(trg1)
        self.assertEqual(key, "supp_r_001")

        self.assertFalse(self.supp.is_suppressed(key))
        self.supp.suppress(key)
        self.assertTrue(self.supp.is_suppressed(key))

    def test_synthesized_suppression_key_fallback(self):
        trg2 = {"kind": "perf_dip", "merchant_id": "m_002", "customer_id": None}
        key = self.supp.get_trigger_suppression_key(trg2)
        self.assertEqual(key, "perf_dip:m_002:merchant")

    def test_two_distinct_triggers_for_one_merchant(self):
        key1 = "research:m_001"
        key2 = "perf_dip:m_001"

        self.supp.suppress(key1)
        self.assertTrue(self.supp.is_suppressed(key1))
        self.assertFalse(self.supp.is_suppressed(key2))

    def test_same_trigger_across_different_scopes(self):
        m_trg = {"kind": "recall", "merchant_id": "m_001", "customer_id": None}
        c_trg = {"kind": "recall", "merchant_id": "m_001", "customer_id": "c_001"}

        m_key = self.supp.get_trigger_suppression_key(m_trg)
        c_key = self.supp.get_trigger_suppression_key(c_trg)

        self.assertNotEqual(m_key, c_key)
        self.supp.suppress(m_key)
        self.assertTrue(self.supp.is_suppressed(m_key))
        self.assertFalse(self.supp.is_suppressed(c_key))

    def test_expired_suppression_key(self):
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        self.supp.suppress("exp_key", past_iso)
        self.assertFalse(self.supp.is_suppressed("exp_key"))

        self.supp.suppress("valid_key", future_iso)
        self.assertTrue(self.supp.is_suppressed("valid_key"))

    def test_opt_out_persistence_across_context_updates(self):
        self.supp.opt_out_merchant("m_001")
        self.assertTrue(self.supp.is_merchant_opted_out("m_001"))

        # Simulating context update (opt out must persist)
        self.supp.suppress("some_random_key")
        self.assertTrue(self.supp.is_merchant_opted_out("m_001"))


if __name__ == "__main__":
    unittest.main()
