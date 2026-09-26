"""
Direct in-process test runner testing Vera API server against judge_simulator scenario routines.
"""

import time
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import config
from main import app, engine
from core.store import store as global_store
from core.suppression import suppression_engine as global_suppression
from judge_simulator import DatasetLoader, DATASET_DIR


class InProcessBotClient:
    """
    In-process BotClient adapter matching judge_simulator.BotClient interface
    using FastAPI TestClient instead of live HTTP requests over the network.
    """

    def __init__(self, app_instance):
        self.client = TestClient(app_instance)

    def healthz(self):
        start = time.time()
        resp = self.client.get("/v1/healthz")
        lat = (time.time() - start) * 1000
        if resp.status_code == 200:
            return resp.json(), None, lat
        return None, f"HTTP {resp.status_code}", lat

    def metadata(self):
        start = time.time()
        resp = self.client.get("/v1/metadata")
        lat = (time.time() - start) * 1000
        if resp.status_code == 200:
            return resp.json(), None, lat
        return None, f"HTTP {resp.status_code}", lat

    def push_context(self, scope, cid, version, payload):
        start = time.time()
        body = {
            "scope": scope,
            "context_id": cid,
            "version": version,
            "payload": payload,
            "delivered_at": datetime.utcnow().isoformat() + "Z",
        }
        resp = self.client.post("/v1/context", json=body)
        lat = (time.time() - start) * 1000
        if resp.status_code in (200, 400, 409):
            return resp.json(), None, lat
        return None, f"HTTP {resp.status_code}", lat

    def tick(self, triggers):
        start = time.time()
        body = {
            "now": datetime.utcnow().isoformat() + "Z",
            "available_triggers": triggers,
        }
        resp = self.client.post("/v1/tick", json=body)
        lat = (time.time() - start) * 1000
        if resp.status_code == 200:
            return resp.json(), None, lat
        return None, f"HTTP {resp.status_code}", lat

    def reply(self, conv_id, merchant_id, message, turn):
        start = time.time()
        body = {
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": None,
            "from_role": "merchant",
            "message": message,
            "received_at": datetime.utcnow().isoformat() + "Z",
            "turn_number": turn,
        }
        resp = self.client.post("/v1/reply", json=body)
        lat = (time.time() - start) * 1000
        if resp.status_code == 200:
            return resp.json(), None, lat
        return None, f"HTTP {resp.status_code}", lat


class TestSimulatorScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = InProcessBotClient(app)
        cls.dataset = DatasetLoader(DATASET_DIR)
        cls.dataset.load()

    def setUp(self):
        global_store.clear()
        global_suppression.clear()
        engine.state_machine.clear_all()

    def test_simulator_healthz_and_metadata(self):
        data, err, lat = self.client.healthz()
        self.assertIsNone(err, f"healthz error: {err}")
        self.assertEqual(data["status"], "ok")

        data, err, lat = self.client.metadata()
        self.assertIsNone(err, f"metadata error: {err}")
        self.assertEqual(data["team_name"], config.TEAM_NAME)

    def test_simulator_context_push_warmup(self):
        for slug, cat in self.dataset.categories.items():
            data, err, _ = self.client.push_context("category", slug, 1, cat)
            self.assertIsNone(err)
            self.assertTrue(data.get("accepted"))

        for mid, m in list(self.dataset.merchants.items())[:5]:
            data, err, _ = self.client.push_context("merchant", mid, 1, m)
            self.assertIsNone(err)
            self.assertTrue(data.get("accepted"))

    def test_simulator_auto_reply_scenario(self):
        """Simulates judge_simulator._auto_reply() scenario."""
        auto_msg = "Thank you for contacting us! Our team will respond shortly."
        mid = list(self.dataset.merchants.keys())[0] if self.dataset.merchants else "m_001"

        # Turn 1 -> bot returns send
        data1, err1, _ = self.client.reply("conv_sim_auto", mid, auto_msg, 2)
        self.assertIsNone(err1)
        self.assertEqual(data1.get("action"), "send")

        # Turn 2 -> bot returns wait (14400s)
        data2, err2, _ = self.client.reply("conv_sim_auto", mid, auto_msg, 3)
        self.assertIsNone(err2)
        self.assertEqual(data2.get("action"), "wait")
        self.assertEqual(data2.get("wait_seconds"), 14400)

        # Turn 3 -> bot returns end
        data3, err3, _ = self.client.reply("conv_sim_auto", mid, auto_msg, 4)
        self.assertIsNone(err3)
        self.assertEqual(data3.get("action"), "end")

    def test_simulator_intent_transition_scenario(self):
        """Simulates judge_simulator._intent() scenario."""
        commitment = "Ok lets do it. Whats next?"
        mid = list(self.dataset.merchants.keys())[0] if self.dataset.merchants else "m_001"

        data, err, _ = self.client.reply("conv_sim_intent", mid, commitment, 2)
        self.assertIsNone(err)
        self.assertEqual(data.get("action"), "send")

        body_lower = data.get("body", "").lower()
        # Verify actioning words present and qualifying words absent
        self.assertTrue(any(w in body_lower for w in ["sending", "draft", "confirm", "proceed", "here"]))
        self.assertFalse(any(w in body_lower for w in ["would you", "do you", "can you tell", "what if"]))

    def test_simulator_hostile_scenario(self):
        """Simulates judge_simulator._hostile() scenario."""
        hostile = "Stop messaging me. This is useless spam."
        mid = list(self.dataset.merchants.keys())[0] if self.dataset.merchants else "m_001"

        data, err, _ = self.client.reply("conv_sim_hostile", mid, hostile, 2)
        self.assertIsNone(err)
        self.assertEqual(data.get("action"), "end")


if __name__ == "__main__":
    unittest.main()
