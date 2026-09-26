"""
API integration unit tests for main.py testing all 5 HTTP endpoints (/v1/healthz, /v1/metadata,
/v1/context, /v1/tick, /v1/reply), schema validation, 409 stale versioning, 400 bad requests, and end-to-end flows.
"""

import json
import unittest
from fastapi.testclient import TestClient

from main import app
from core.store import store as global_store
from core.suppression import suppression_engine as global_suppression


import config

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        global_store.clear()
        global_suppression.clear()

    def test_healthz_endpoint(self):
        response = self.client.get("/v1/healthz")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_seconds", data)
        self.assertIn("contexts_loaded", data)

    def test_metadata_endpoint(self):
        response = self.client.get("/v1/metadata")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["team_name"], config.TEAM_NAME)
        self.assertIn("model", data)
        self.assertIn("version", data)

    def test_push_context_endpoint_success_and_stale_conflict(self):
        cat_payload = {
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"slug": "dentists", "voice": {"tone": "peer_clinical"}},
        }

        # 1. Initial Insert -> 200 OK
        resp1 = self.client.post("/v1/context", json=cat_payload)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1["accepted"])
        self.assertEqual(data1["ack_id"], "ack_dentists_v1")

        # 2. Duplicate Version -> 409 Conflict
        resp2 = self.client.post("/v1/context", json=cat_payload)
        self.assertEqual(resp2.status_code, 409)
        data2 = resp2.json()
        self.assertFalse(data2["accepted"])
        self.assertEqual(data2["reason"], "stale_version")
        self.assertEqual(data2["current_version"], 1)

        # 3. Version Bump -> 200 OK
        cat_payload["version"] = 2
        resp3 = self.client.post("/v1/context", json=cat_payload)
        self.assertEqual(resp3.status_code, 200)

    def test_push_context_invalid_scope(self):
        bad_payload = {
            "scope": "unknown_scope",
            "context_id": "bad_1",
            "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {},
        }
        resp = self.client.post("/v1/context", json=bad_payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertEqual(data["reason"], "invalid_scope")

    def test_tick_and_reply_end_to_end_flow(self):
        # Seed contexts via /v1/context
        self.client.post("/v1/context", json={
            "scope": "category", "context_id": "dentists", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"slug": "dentists", "voice": {"tone": "peer_clinical"}}
        })
        self.client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_001", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"merchant_id": "m_001", "category_slug": "dentists", "identity": {"owner_first_name": "Meera"}}
        })
        self.client.post("/v1/context", json={
            "scope": "trigger", "context_id": "trg_001", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"id": "trg_001", "scope": "merchant", "kind": "research_digest", "source": "external", "merchant_id": "m_001", "urgency": 2, "suppression_key": "supp_001"}
        })

        # Call /v1/tick
        tick_resp = self.client.post("/v1/tick", json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": ["trg_001"]
        })
        self.assertEqual(tick_resp.status_code, 200)
        actions = tick_resp.json()["actions"]
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["merchant_id"], "m_001")
        self.assertIn("Dr. Meera", action["body"])

        # Call /v1/reply with affirmative message
        reply_resp = self.client.post("/v1/reply", json={
            "conversation_id": action["conversation_id"],
            "merchant_id": "m_001",
            "from_role": "merchant",
            "message": "Yes please send the abstract",
            "received_at": "2026-04-26T10:42:00Z",
            "turn_number": 2
        })
        self.assertEqual(reply_resp.status_code, 200)
        reply_data = reply_resp.json()
        self.assertEqual(reply_data["action"], "send")
        self.assertEqual(reply_data["cta"], "binary_confirm_cancel")

    def test_teardown_endpoint_behavior(self):
        # 1. Insert data and establish state
        self.client.post("/v1/context", json={
            "scope": "category", "context_id": "dentists", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"slug": "dentists"}
        })
        self.client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_001", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"merchant_id": "m_001", "category_slug": "dentists"}
        })

        # Verify healthz reports loaded contexts
        hz1 = self.client.get("/v1/healthz").json()
        self.assertEqual(hz1["contexts_loaded"]["category"], 1)
        self.assertEqual(hz1["contexts_loaded"]["merchant"], 1)

        # 2. Call POST /v1/teardown
        td_resp = self.client.post("/v1/teardown")
        self.assertEqual(td_resp.status_code, 200)
        td_data = td_resp.json()
        self.assertEqual(td_data["status"], "ok")
        self.assertTrue(td_data["cleared"])

        # 3. Verify store is wiped
        hz2 = self.client.get("/v1/healthz").json()
        self.assertEqual(hz2["contexts_loaded"]["category"], 0)
        self.assertEqual(hz2["contexts_loaded"]["merchant"], 0)

        # 4. Verify repeated teardown calls are idempotent
        td_resp2 = self.client.post("/v1/teardown")
        self.assertEqual(td_resp2.status_code, 200)
        self.assertEqual(td_resp2.json()["status"], "ok")

        # 5. Verify system can accept new requests normally after teardown
        post_resp = self.client.post("/v1/context", json={
            "scope": "category", "context_id": "salons", "version": 1,
            "delivered_at": "2026-04-26T10:00:00Z",
            "payload": {"slug": "salons"}
        })
        self.assertEqual(post_resp.status_code, 200)
        self.assertTrue(post_resp.json()["accepted"])


if __name__ == "__main__":
    unittest.main()
