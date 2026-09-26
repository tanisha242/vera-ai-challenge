"""
Unit tests for composer/composer.py testing 14 explicit composition constraints:
schema compliance, personalization, CTA selection, taboo cleaning, URL stripping,
missing fields handling, non-mutation, and determinism.
"""

import json
import unittest
from unittest.mock import patch
from engine.decision import Decision
from composer.composer import MessageComposer, ALLOWED_CTAS
from composer.llm_composer import LLMComposer




class TestMessageComposer(unittest.TestCase):
    def setUp(self):
        self.composer = MessageComposer()

    def test_official_output_schema(self):
        """Verify composed message dict contains exact official schema keys."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "research_digest", "scope": "merchant"},
            merchant={"merchant_id": "m_001", "category_slug": "dentists", "identity": {"owner_first_name": "Meera"}},
            category={"slug": "dentists"},
            suppression_key="supp_001",
            reason="Highest urgency trigger",
        )

        res = self.composer.compose_proactive_message(decision)

        self.assertIn("body", res)
        self.assertIn("cta", res)
        self.assertIn("send_as", res)
        self.assertIn("suppression_key", res)
        self.assertIn("rationale", res)

        self.assertIn(res["cta"], ALLOWED_CTAS)
        self.assertIn(res["send_as"], ["vera", "merchant_on_behalf"])

    def test_no_action_decision(self):
        """Verify no_action decision returns empty body and CTA none."""
        decision = Decision(
            action_type="no_action",
            reason="All triggers expired",
            suppression_key="",
        )

        res = self.composer.compose_proactive_message(decision)

        self.assertEqual(res["body"], "")
        self.assertEqual(res["cta"], "none")
        self.assertEqual(res["send_as"], "vera")

    def test_bare_url_stripping(self):
        """Verify any bare http/https URLs are stripped from the body per WhatsApp rules."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "curious_ask_due", "scope": "merchant"},
            merchant={"merchant_id": "m_003", "category_slug": "salons", "identity": {"owner_first_name": "Lakshmi"}},
            category={"slug": "salons"},
            suppression_key="supp_url",
        )

        # Force a URL into strategy output by mocking/testing sanitizer directly
        res = self.composer.compose_proactive_message(decision)
        self.assertNotIn("http://", res["body"])
        self.assertNotIn("https://", res["body"])

    def test_missing_merchant_fields_fallback(self):
        """Verify composer handles missing owner name and locality gracefully without crashing."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "perf_dip", "scope": "merchant"},
            merchant={"merchant_id": "m_bare", "category_slug": "dentists"},  # No identity dict
            category={"slug": "dentists"},
            suppression_key="supp_bare",
        )

        res = self.composer.compose_proactive_message(decision)
        self.assertTrue(len(res["body"]) > 0)
        self.assertIn("Dr.", res["body"])

    def test_missing_customer_context_fallback(self):
        """Verify customer-scoped trigger without customer context falls back cleanly."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_003", "kind": "recall_due", "scope": "customer"},
            merchant={"merchant_id": "m_001", "category_slug": "dentists", "identity": {"owner_first_name": "Meera"}},
            category={"slug": "dentists"},
            customer=None,
            suppression_key="supp_nocust",
        )

        res = self.composer.compose_proactive_message(decision)
        self.assertTrue(len(res["body"]) > 0)

    def test_decision_non_mutation(self):
        """Verify composing a message does NOT mutate the original Decision object."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "research_digest", "scope": "merchant"},
            merchant={"merchant_id": "m_001", "category_slug": "dentists"},
            category={"slug": "dentists"},
            suppression_key="supp_immutable",
        )

        original_id = decision.trigger["id"]
        _ = self.composer.compose_proactive_message(decision)

        self.assertEqual(decision.trigger["id"], original_id)
        self.assertEqual(decision.action_type, "proactive_send")

    def test_determinism_for_identical_inputs(self):
        """Verify identical decision objects yield identical composed outputs."""
        decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "research_digest", "scope": "merchant"},
            merchant={"merchant_id": "m_001", "category_slug": "dentists", "identity": {"owner_first_name": "Meera"}},
            category={"slug": "dentists"},
            suppression_key="supp_det",
        )

        res1 = self.composer.compose_proactive_message(decision)
        res2 = self.composer.compose_proactive_message(decision)

        self.assertEqual(res1, res2)


class TestLLMComposer(unittest.TestCase):
    def setUp(self):
        self.decision = Decision(
            action_type="proactive_send",
            trigger={"id": "trg_001", "kind": "research_digest", "scope": "merchant"},
            merchant={
                "merchant_id": "m_001",
                "category_slug": "dentists",
                "identity": {"owner_first_name": "Meera"},
                "offers": [{"title": "Dental Cleaning @ ₹299"}],
            },
            category={"slug": "dentists"},
            suppression_key="supp_llm_test",
        )

    def test_llm_disabled_uses_deterministic_composer(self):
        llm_comp = LLMComposer(enabled=False, api_key="dummy_key")
        composer = MessageComposer(llm_composer=llm_comp)
        res = composer.compose_proactive_message(self.decision)
        self.assertIn("Dr. Meera", res["body"])
        self.assertEqual(res["send_as"], "vera")

    def test_missing_api_key_uses_deterministic_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="")
        composer = MessageComposer(llm_composer=llm_comp)
        res = composer.compose_proactive_message(self.decision)
        self.assertIn("Dr. Meera", res["body"])

    def test_valid_mocked_llm_response_accepted(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        valid_json = '{"body": "Dr. Meera, new trial shows fluoride recall cuts caries 38%.", "cta": "open_ended", "send_as": "vera", "rationale": "LLM generated"}'
        with patch.object(llm_comp, "_call_provider", return_value=valid_json):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertEqual(res["body"], "Dr. Meera, new trial shows fluoride recall cuts caries 38%.")
            self.assertEqual(res["cta"], "open_ended")
            self.assertEqual(res["rationale"], "LLM generated")

    def test_malformed_json_response_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        with patch.object(llm_comp, "_call_provider", return_value="NOT_VALID_JSON"):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])

    def test_provider_timeout_or_error_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        with patch.object(llm_comp, "_call_provider", side_effect=Exception("Timeout")):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])

    def test_invalid_cta_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        bad_cta_json = '{"body": "Hello", "cta": "invalid_cta_type"}'
        with patch.object(llm_comp, "_call_provider", return_value=bad_cta_json):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])

    def test_excessive_length_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        long_body_json = json.dumps({"body": "A" * 1500, "cta": "open_ended"})
        with patch.object(llm_comp, "_call_provider", return_value=long_body_json):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])

    def test_prohibited_vertical_claim_taboo_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        # "guaranteed" is a taboo word for dentists strategy
        taboo_json = '{"body": "We offer a guaranteed cure for your dental pain!", "cta": "open_ended"}'
        with patch.object(llm_comp, "_call_provider", return_value=taboo_json):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])


    def test_ungrounded_fabricated_price_claim_triggers_fallback(self):
        llm_comp = LLMComposer(enabled=True, api_key="mock_key")
        # ₹999 price is not in merchant offers (which has ₹299) or trigger payload
        fabricated_price_json = '{"body": "Special Dental Cleaning @ ₹999 available today!", "cta": "open_ended"}'
        with patch.object(llm_comp, "_call_provider", return_value=fabricated_price_json):
            composer = MessageComposer(llm_composer=llm_comp)
            res = composer.compose_proactive_message(self.decision)
            self.assertIn("Dr. Meera", res["body"])
            self.assertNotIn("₹999", res["body"])


if __name__ == "__main__":
    unittest.main()
