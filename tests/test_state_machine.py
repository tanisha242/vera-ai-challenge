"""
Unit tests for engine/state_machine.py verifying conversation state transitions,
auto-reply detection, affirmative intent transitions, hostile opt-outs, and off-topic redirects.
"""

import unittest
from core.store import ContextStore
from core.suppression import SuppressionEngine
from engine.state_machine import ConversationStateMachine


class TestConversationStateMachine(unittest.TestCase):
    def setUp(self):
        self.store = ContextStore()
        self.supp = SuppressionEngine()
        self.sm = ConversationStateMachine()

    def test_affirmative_intent_transition(self):
        """Verify merchant saying 'ok lets do it' transitions to action execution without re-qualifying."""
        res = self.sm.handle_reply(
            conversation_id="conv_intent_1",
            merchant_id="m_001",
            customer_id=None,
            from_role="merchant",
            message="Ok lets do it. Whats next?",
            received_at="2026-04-26T10:45:00Z",
            turn_number=2,
            store=self.store,
            suppression=self.supp,
        )

        self.assertEqual(res["action"], "send")
        self.assertEqual(res["cta"], "binary_confirm_cancel")
        body_lower = res["body"].lower()
        # Verify body contains actioning terms and does not ask qualifying questions
        self.assertTrue(any(w in body_lower for w in ["sending", "draft", "confirm", "proceed", "here"]))
        self.assertFalse(any(w in body_lower for w in ["would you", "do you", "can you tell", "what if"]))

    def test_repeated_auto_reply_sequence(self):
        """Verify turn 1 auto-reply returns send, turn 2 returns wait, turn 3 returns end."""
        canned_msg = "Thank you for contacting us! Our team will respond shortly."

        # Turn 1
        res1 = self.sm.handle_reply("conv_auto", "m_001", None, "merchant", canned_msg, "2026-04-26T10:00:00Z", 2, self.store, self.supp)
        self.assertEqual(res1["action"], "send")
        self.assertIn("auto-reply", res1["body"].lower())

        # Turn 2
        res2 = self.sm.handle_reply("conv_auto", "m_001", None, "merchant", canned_msg, "2026-04-26T10:05:00Z", 3, self.store, self.supp)
        self.assertEqual(res2["action"], "wait")
        self.assertEqual(res2["wait_seconds"], 14400)

        # Turn 3
        res3 = self.sm.handle_reply("conv_auto", "m_001", None, "merchant", canned_msg, "2026-04-26T10:10:00Z", 4, self.store, self.supp)
        self.assertEqual(res3["action"], "end")

    def test_hostile_stop_opt_out(self):
        """Verify STOP / hostile message returns end and registers merchant opt-out."""
        hostile_msg = "Stop messaging me. This is useless spam."

        res = self.sm.handle_reply("conv_hostile", "m_001", None, "merchant", hostile_msg, "2026-04-26T10:00:00Z", 2, self.store, self.supp)

        self.assertEqual(res["action"], "end")
        self.assertTrue(self.supp.is_merchant_opted_out("m_001"))

    def test_off_topic_redirect(self):
        """Verify off-topic question about GST filing is politely declined and pivoted back."""
        off_topic_msg = "Btw can you also help me with my GST filing this month?"

        res = self.sm.handle_reply("conv_offtopic", "m_001", None, "merchant", off_topic_msg, "2026-04-26T10:00:00Z", 2, self.store, self.supp)

        self.assertEqual(res["action"], "send")
        self.assertIn("gst", res["body"].lower())
        self.assertIn("outside", res["body"].lower())

    def test_multiple_independent_conversations(self):
        """Verify conversation states are isolated across different conversation_ids."""
        res_m1 = self.sm.handle_reply("conv_m1", "m_001", None, "merchant", "Ok lets do it", "2026-04-26T10:00:00Z", 2, self.store, self.supp)
        res_m2 = self.sm.handle_reply("conv_m2", "m_002", None, "merchant", "Stop messaging me", "2026-04-26T10:00:00Z", 2, self.store, self.supp)

        self.assertEqual(res_m1["action"], "send")
        self.assertEqual(res_m2["action"], "end")
        self.assertFalse(self.supp.is_merchant_opted_out("m_001"))
        self.assertTrue(self.supp.is_merchant_opted_out("m_002"))


if __name__ == "__main__":
    unittest.main()
