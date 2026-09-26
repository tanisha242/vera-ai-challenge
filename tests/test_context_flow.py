"""
Comprehensive integration tests verifying end-to-end context storage, retrieval,
context-driven tick decisions, context-driven reply generation, and simulator compatibility.
"""

import unittest
from datetime import datetime
from fastapi.testclient import TestClient

from main import app
from core.store import store as global_store
from core.suppression import suppression_engine as global_suppression
from engine.controller import VeraEngine
from judge_simulator import DatasetLoader, DATASET_DIR


class TestContextFlowIntegration(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.engine = VeraEngine(store=global_store, suppression=global_suppression)
        self.engine.teardown()

    def tearDown(self):
        self.engine.teardown()

    # =========================================================================
    # 1. CONTEXT STORAGE & RETRIEVAL TESTS
    # =========================================================================

    def test_context_storage_retrieval_across_scopes(self):
        """Verify context push, versioning, atomic retrieval, and scope isolation."""
        # 1. Push category context
        cat_resp = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists", "display_name": "Dentists"},
            "delivered_at": "2026-09-27T10:00:00Z"
        })
        self.assertEqual(cat_resp.status_code, 200)
        self.assertTrue(cat_resp.json()["accepted"])

        # 2. Push merchant context with SAME ID string ("dentists") to test scope isolation
        merch_resp = self.client.post("/v1/context", json={
            "scope": "merchant",
            "context_id": "dentists",
            "version": 1,
            "payload": {"merchant_id": "dentists", "category_slug": "dentists", "identity": {"name": "Dentist Shop"}},
            "delivered_at": "2026-09-27T10:00:00Z"
        })
        self.assertEqual(merch_resp.status_code, 200)

        # 3. Verify store isolation: category payload and merchant payload exist independently under same ID
        cat_data = global_store.get_payload("category", "dentists")
        merch_data = global_store.get_payload("merchant", "dentists")
        self.assertEqual(cat_data["display_name"], "Dentists")
        self.assertEqual(merch_data["identity"]["name"], "Dentist Shop")

        # 4. Atomic Versioning (stale version 409 conflict)
        stale_resp = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists", "display_name": "Stale Dentists"},
            "delivered_at": "2026-09-27T10:01:00Z"
        })
        self.assertEqual(stale_resp.status_code, 409)
        self.assertFalse(stale_resp.json()["accepted"])
        self.assertEqual(stale_resp.json()["reason"], "stale_version")

        # 5. Invalid context_id 400 rejection
        empty_id_resp = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "   ",
            "version": 1,
            "payload": {"slug": "test"},
            "delivered_at": "2026-09-27T10:00:00Z"
        })
        self.assertEqual(empty_id_resp.status_code, 400)

    # =========================================================================
    # 2. CONTEXT-DRIVEN TICK DECISIONS
    # =========================================================================

    def test_tick_decision_with_full_context(self):
        """Verify /v1/tick uses stored trigger, merchant, category, and customer context."""
        now_iso = "2026-09-27T10:00:00Z"

        # Push category
        global_store.put("category", "dentists", 1, {"slug": "dentists"})
        # Push merchant
        global_store.put("merchant", "m_101", 1, {
            "merchant_id": "m_101",
            "category_slug": "dentists",
            "identity": {"name": "Dental Oasis", "owner_first_name": "Sarah"}
        })
        # Push customer
        global_store.put("customer", "c_101", 1, {
            "customer_id": "c_101",
            "merchant_id": "m_101",
            "identity": {"name": "Rohan"},
            "state": "active",
            "preferences": {"reminder_opt_in": True},
            "consent": {"opted_in": True}
        })
        # Push customer-scoped trigger
        global_store.put("trigger", "trg_101", 1, {
            "id": "trg_101",
            "scope": "customer",
            "kind": "recall_due",
            "source": "internal",
            "merchant_id": "m_101",
            "customer_id": "c_101",
            "urgency": 4,
            "payload": {"service_due": "cleaning"}
        })

        tick_resp = self.client.post("/v1/tick", json={
            "now": now_iso,
            "available_triggers": ["trg_101"]
        })
        self.assertEqual(tick_resp.status_code, 200)
        actions = tick_resp.json()["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["merchant_id"], "m_101")
        self.assertEqual(actions[0]["customer_id"], "c_101")
        self.assertIn("Rohan", actions[0]["body"])
        self.assertIn("Dental Oasis", actions[0]["body"])

    def test_tick_decision_missing_customer_context_safety(self):
        """Verify /v1/tick rejects customer-scoped trigger if customer context is missing."""
        now_iso = "2026-09-27T10:00:00Z"
        global_store.put("merchant", "m_102", 1, {"merchant_id": "m_102", "category_slug": "dentists"})
        global_store.put("trigger", "trg_102", 1, {
            "id": "trg_102",
            "scope": "customer",
            "kind": "recall_due",
            "source": "internal",
            "merchant_id": "m_102",
            "customer_id": "c_missing",
            "urgency": 4
        })

        tick_resp = self.client.post("/v1/tick", json={
            "now": now_iso,
            "available_triggers": ["trg_102"]
        })
        self.assertEqual(tick_resp.status_code, 200)
        actions = tick_resp.json()["actions"]
        self.assertEqual(len(actions), 0)  # Safe fallback: no action generated

    # =========================================================================
    # 3. CONTEXT-DRIVEN REPLY GENERATION
    # =========================================================================

    def test_reply_uses_stored_merchant_and_customer_context(self):
        """Verify /v1/reply retrieves stored merchant/customer details and incorporates them."""
        # Seed merchant context
        global_store.put("merchant", "m_201", 1, {
            "merchant_id": "m_201",
            "category_slug": "dentists",
            "identity": {"name": "Apex Dental", "owner_first_name": "Meera"}
        })
        # Seed customer context
        global_store.put("customer", "c_201", 1, {
            "customer_id": "c_201",
            "merchant_id": "m_201",
            "identity": {"name": "Priya"}
        })

        # 1. Affirmative reply turn with merchant context
        reply_resp = self.client.post("/v1/reply", json={
            "conversation_id": "conv_201",
            "merchant_id": "m_201",
            "customer_id": "c_201",
            "from_role": "merchant",
            "message": "Yes let's do it",
            "received_at": "2026-09-27T10:00:00Z",
            "turn_number": 2
        })
        self.assertEqual(reply_resp.status_code, 200)
        body = reply_resp.json()["body"]
        self.assertIn("Meera", body)
        self.assertIn("Apex Dental", body)

        # 2. General engaged turn with customer context
        reply_resp2 = self.client.post("/v1/reply", json={
            "conversation_id": "conv_202",
            "merchant_id": "m_201",
            "customer_id": "c_201",
            "from_role": "customer",
            "message": "When is the slot available?",
            "received_at": "2026-09-27T10:05:00Z",
            "turn_number": 1
        })
        self.assertEqual(reply_resp2.status_code, 200)
        body2 = reply_resp2.json()["body"]
        self.assertIn("Priya", body2)

    # =========================================================================
    # 4. SIMULATOR DATASET LOADING
    # =========================================================================

    def test_simulator_expanded_dataset_loading_counts(self):
        """Verify DatasetLoader successfully loads expanded dataset records."""
        loader = DatasetLoader(DATASET_DIR)
        success = loader.load()
        self.assertTrue(success)
        self.assertEqual(len(loader.categories), 5)
        self.assertEqual(len(loader.merchants), 50)
        self.assertEqual(len(loader.customers), 200)
        self.assertEqual(len(loader.triggers), 100)


if __name__ == "__main__":
    unittest.main()
