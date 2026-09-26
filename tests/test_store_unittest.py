"""
Standard unittest test suite for ContextStore.
Ensures zero external dependency execution.
"""

import json
import unittest
import concurrent.futures
from pathlib import Path

from core.store import ContextStore, VALID_SCOPES
from core.models import ContextPush, ContextPushAck, ContextPushReject


DATASET_DIR = Path(__file__).parent.parent / "dataset_expanded"


class TestContextStore(unittest.TestCase):
    def setUp(self):
        self.store = ContextStore()

    def test_initial_insert(self):
        payload = {"slug": "dentists", "voice": {"tone": "peer_clinical"}}
        success, ack_id, cur_ver = self.store.put("category", "dentists", 1, payload)

        self.assertTrue(success)
        self.assertEqual(ack_id, "ack_dentists_v1")
        self.assertIsNone(cur_ver)

        stored = self.store.get("category", "dentists")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["version"], 1)
        self.assertEqual(stored["payload"], payload)

        counts = self.store.get_counts()
        self.assertEqual(counts["category"], 1)
        self.assertEqual(counts["merchant"], 0)

    def test_higher_version_update(self):
        self.store.put("merchant", "m_001", 1, {"name": "Old Clinic", "views": 100})

        success, ack_id, cur_ver = self.store.put("merchant", "m_001", 2, {"name": "New Clinic", "views": 200})

        self.assertTrue(success)
        self.assertEqual(ack_id, "ack_m_001_v2")
        self.assertIsNone(cur_ver)

        stored_payload = self.store.get_payload("merchant", "m_001")
        self.assertEqual(stored_payload["name"], "New Clinic")
        self.assertEqual(stored_payload["views"], 200)
        self.assertEqual(self.store.get_version("merchant", "m_001"), 2)

    def test_duplicate_and_stale_version_rejection(self):
        self.store.put("trigger", "trg_001", 3, {"kind": "research_digest"})

        # Duplicate version 3
        success, reason, cur_ver = self.store.put("trigger", "trg_001", 3, {"kind": "research_digest"})
        self.assertFalse(success)
        self.assertEqual(reason, "stale_version")
        self.assertEqual(cur_ver, 3)

        # Lower version 2
        success, reason, cur_ver = self.store.put("trigger", "trg_001", 2, {"kind": "old_kind"})
        self.assertFalse(success)
        self.assertEqual(reason, "stale_version")
        self.assertEqual(cur_ver, 3)

        # Payload remains unchanged
        self.assertEqual(self.store.get_payload("trigger", "trg_001")["kind"], "research_digest")

    def test_invalid_scope_rejection(self):
        success, reason, cur_ver = self.store.put("unknown_scope", "id_123", 1, {"foo": "bar"})
        self.assertFalse(success)
        self.assertEqual(reason, "invalid_scope")
        self.assertIsNone(cur_ver)

    def test_scope_entity_isolation(self):
        self.store.put("category", "dentists", 1, {"type": "category_pack"})
        self.store.put("merchant", "dentists", 1, {"type": "merchant_profile"})

        cat_payload = self.store.get_payload("category", "dentists")
        mer_payload = self.store.get_payload("merchant", "dentists")

        self.assertEqual(cat_payload["type"], "category_pack")
        self.assertEqual(mer_payload["type"], "merchant_profile")

        self.store.put("category", "dentists", 2, {"type": "category_pack_v2"})
        self.assertEqual(self.store.get_version("category", "dentists"), 2)
        self.assertEqual(self.store.get_version("merchant", "dentists"), 1)

    def test_multiple_entities_isolation(self):
        self.store.put("merchant", "m_001", 1, {"name": "Meera"})
        self.store.put("merchant", "m_002", 1, {"name": "Bharat"})
        self.store.put("customer", "c_001", 1, {"name": "Priya"})

        self.assertEqual(self.store.get_payload("merchant", "m_001")["name"], "Meera")
        self.assertEqual(self.store.get_payload("merchant", "m_002")["name"], "Bharat")
        self.assertEqual(self.store.get_payload("customer", "c_001")["name"], "Priya")

        counts = self.store.get_counts()
        self.assertEqual(counts["merchant"], 2)
        self.assertEqual(counts["customer"], 1)

    def test_concurrent_updates(self):
        def worker(idx):
            for ver in range(1, 20):
                self.store.put("merchant", f"m_concurrent_{idx}", ver, {"worker": idx, "ver": ver})

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            concurrent.futures.wait(futures)

        counts = self.store.get_counts()
        self.assertEqual(counts["merchant"], 10)
        for i in range(10):
            self.assertEqual(self.store.get_version("merchant", f"m_concurrent_{i}"), 19)

    def test_load_actual_generated_dataset(self):
        if not DATASET_DIR.exists():
            self.skipTest("dataset_expanded directory not found")

        # Ingest categories
        cat_dir = DATASET_DIR / "categories"
        for cat_file in cat_dir.glob("*.json"):
            data = json.loads(cat_file.read_text(encoding="utf-8"))
            slug = data.get("slug", cat_file.stem)
            ok, ack, _ = self.store.put("category", slug, 1, data)
            self.assertTrue(ok)

        # Ingest merchants
        mer_dir = DATASET_DIR / "merchants"
        for mer_file in list(mer_dir.glob("*.json"))[:10]:
            data = json.loads(mer_file.read_text(encoding="utf-8"))
            mid = data["merchant_id"]
            ok, ack, _ = self.store.put("merchant", mid, 1, data)
            self.assertTrue(ok)

        counts = self.store.get_counts()
        self.assertEqual(counts["category"], 5)
        self.assertEqual(counts["merchant"], 10)


if __name__ == "__main__":
    unittest.main()
