"""
Unit tests for vertical strategies verifying category-specific rules, taboos,
voice constraints, and factual grounding across all 5 categories.
"""

import unittest
from engine.decision import Decision
from strategies import get_strategy
from strategies.dentists import DentistStrategy
from strategies.salons import SalonStrategy
from strategies.restaurants import RestaurantStrategy
from strategies.gyms import GymStrategy
from strategies.pharmacies import PharmacyStrategy


class TestVerticalStrategies(unittest.TestCase):
    def test_strategy_factory_selection(self):
        """Verify correct strategy class is returned for each category slug."""
        self.assertIsInstance(get_strategy("dentists"), DentistStrategy)
        self.assertIsInstance(get_strategy("salons"), SalonStrategy)
        self.assertIsInstance(get_strategy("restaurants"), RestaurantStrategy)
        self.assertIsInstance(get_strategy("gyms"), GymStrategy)
        self.assertIsInstance(get_strategy("pharmacies"), PharmacyStrategy)
        # Fallback test
        self.assertIsInstance(get_strategy("unknown_category"), DentistStrategy)

    def test_dentist_taboo_and_citation_enforcement(self):
        """Verify dentist strategy uses Dr. prefix, cites JIDA source, and cleans taboos."""
        strategy = DentistStrategy()

        # Check taboos list
        taboos = strategy.get_taboo_words()
        self.assertIn("guaranteed", taboos)
        self.assertIn("completely cure", taboos)

        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "research_digest", "scope": "merchant"},
            merchant={"merchant_id": "m_001", "identity": {"owner_first_name": "Meera"}},
            category={"slug": "dentists", "digest": [{"id": "d_2026W17_jida_fluoride", "source": "JIDA Oct 2026 p.14", "trial_n": 2100}]},
            suppression_key="supp_001",
        )

        res = strategy.format_message(decision)
        self.assertIn("Dr. Meera", res["body"])
        self.assertIn("JIDA Oct 2026 p.14", res["body"])
        self.assertIn("38%", res["body"])
        self.assertEqual(res["send_as"], "vera")

    def test_salon_bridal_timing_and_offer(self):
        """Verify salon strategy handles customer bridal prep and active offers."""
        strategy = SalonStrategy()

        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_007", "kind": "bridal_followup", "scope": "customer", "payload": {"days_to_wedding": 196}},
            merchant={"merchant_id": "m_003", "identity": {"name": "Studio11", "owner_first_name": "Lakshmi"}, "offers": [{"title": "Haircut @ ₹99", "status": "active"}]},
            customer={"customer_id": "c_005", "identity": {"name": "Kavya"}},
            suppression_key="supp_bridal",
        )

        res = strategy.format_message(decision)
        self.assertIn("Kavya", res["body"])
        self.assertIn("Lakshmi", res["body"])
        self.assertIn("196 days", res["body"])
        self.assertEqual(res["send_as"], "merchant_on_behalf")

    def test_restaurant_ipl_match_reframe(self):
        """Verify restaurant strategy reframes Saturday IPL match with -12% covers data."""
        strategy = RestaurantStrategy()

        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_010", "kind": "ipl_match_today", "scope": "merchant", "payload": {"match": "DC vs MI", "is_weeknight": False}},
            merchant={"merchant_id": "m_005", "identity": {"owner_first_name": "Suresh"}, "offers": [{"title": "Buy 1 Pizza Get 1 Free (Tue-Thu)", "status": "active"}]},
            suppression_key="supp_ipl",
        )

        res = strategy.format_message(decision)
        self.assertIn("DC vs MI", res["body"])
        self.assertIn("-12% restaurant covers", res["body"])
        self.assertIn("delivery-only", res["body"])

    def test_gym_seasonal_dip_reframe(self):
        """Verify gym strategy reframes April acquisition lull without shame."""
        strategy = GymStrategy()

        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_014", "kind": "seasonal_perf_dip", "scope": "merchant", "payload": {"delta_pct": -0.30}},
            merchant={"merchant_id": "m_007", "identity": {"owner_first_name": "Karthik"}, "customer_aggregate": {"total_active_members": 245}},
            suppression_key="supp_gym_dip",
        )

        res = strategy.format_message(decision)
        self.assertIn("Karthik", res["body"])
        self.assertIn("245 members", res["body"])
        self.assertIn("summer attendance challenge", res["body"])

    def test_pharmacy_recall_alert(self):
        """Verify pharmacy strategy handles supply alerts with exact batch numbers."""
        strategy = PharmacyStrategy()

        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_018", "kind": "supply_alert", "scope": "merchant", "payload": {"molecule": "atorvastatin", "affected_batches": ["AT2024-1102", "AT2024-1108"], "manufacturer": "Mfr Z"}},
            merchant={"merchant_id": "m_009", "identity": {"owner_first_name": "Ramesh"}, "customer_aggregate": {"chronic_rx_count": 240}},
            suppression_key="supp_recall",
        )

        res = strategy.format_message(decision)
        self.assertIn("AT2024-1102", res["body"])
        self.assertIn("AT2024-1108", res["body"])
        self.assertIn("Mfr Z", res["body"])


if __name__ == "__main__":
    unittest.main()
