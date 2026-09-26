"""
Unit tests for ContextStore verifying initial inserts, version updates,
duplicate/stale version behavior, scope isolation, payload safety, and concurrency.
"""

import json
import concurrent.futures
from pathlib import Path
import pytest

from core.store import ContextStore, VALID_SCOPES
from core.models import ContextPush, ContextPushAck, ContextPushReject


DATASET_DIR = Path(__file__).parent.parent / "dataset_expanded"


@pytest.fixture
def store():
    """Fresh ContextStore instance for each test."""
    return ContextStore()


def test_initial_insert(store):
    """Verify initial insertion across all valid scopes."""
    payload = {"slug": "dentists", "voice": {"tone": "peer_clinical"}}
    success, ack_id, cur_ver = store.put("category", "dentists", 1, payload)

    assert success is True
    assert ack_id == "ack_dentists_v1"
    assert cur_ver is None

    stored = store.get("category", "dentists")
    assert stored is not None
    assert stored["version"] == 1
    assert stored["payload"] == payload

    counts = store.get_counts()
    assert counts["category"] == 1
    assert counts["merchant"] == 0


def test_higher_version_update(store):
    """Verify posting a higher version replaces the prior version atomically."""
    store.put("merchant", "m_001", 1, {"name": "Old Clinic", "views": 100})

    # Post version 2
    success, ack_id, cur_ver = store.put("merchant", "m_001", 2, {"name": "New Clinic", "views": 200})

    assert success is True
    assert ack_id == "ack_m_001_v2"
    assert cur_ver is None

    stored_payload = store.get_payload("merchant", "m_001")
    assert stored_payload["name"] == "New Clinic"
    assert stored_payload["views"] == 200
    assert store.get_version("merchant", "m_001") == 2


def test_duplicate_and_stale_version_rejection(store):
    """Verify posting same or lower version returns stale_version conflict."""
    store.put("trigger", "trg_001", 3, {"kind": "research_digest"})

    # Post duplicate version 3 -> expect stale_version
    success, reason, cur_ver = store.put("trigger", "trg_001", 3, {"kind": "research_digest"})
    assert success is False
    assert reason == "stale_version"
    assert cur_ver == 3

    # Post lower version 2 -> expect stale_version
    success, reason, cur_ver = store.put("trigger", "trg_001", 2, {"kind": "old_kind"})
    assert success is False
    assert reason == "stale_version"
    assert cur_ver == 3

    # Payload must remain unchanged
    assert store.get_payload("trigger", "trg_001")["kind"] == "research_digest"


def test_invalid_scope_rejection(store):
    """Verify invalid scope is rejected cleanly."""
    success, reason, cur_ver = store.put("unknown_scope", "id_123", 1, {"foo": "bar"})
    assert success is False
    assert reason == "invalid_scope"
    assert cur_ver is None


def test_scope_entity_isolation(store):
    """Verify entity with same context_id in different scopes are stored independently."""
    store.put("category", "dentists", 1, {"type": "category_pack"})
    store.put("merchant", "dentists", 1, {"type": "merchant_profile"})

    cat_payload = store.get_payload("category", "dentists")
    mer_payload = store.get_payload("merchant", "dentists")

    assert cat_payload["type"] == "category_pack"
    assert mer_payload["type"] == "merchant_profile"

    # Updating category version does not affect merchant version
    store.put("category", "dentists", 2, {"type": "category_pack_v2"})
    assert store.get_version("category", "dentists") == 2
    assert store.get_version("merchant", "dentists") == 1


def test_multiple_entities_isolation(store):
    """Verify isolation between multiple merchants and customers."""
    store.put("merchant", "m_001", 1, {"name": "Meera"})
    store.put("merchant", "m_002", 1, {"name": "Bharat"})
    store.put("customer", "c_001", 1, {"name": "Priya"})

    assert store.get_payload("merchant", "m_001")["name"] == "Meera"
    assert store.get_payload("merchant", "m_002")["name"] == "Bharat"
    assert store.get_payload("customer", "c_001")["name"] == "Priya"

    counts = store.get_counts()
    assert counts["merchant"] == 2
    assert counts["customer"] == 1


def test_concurrent_updates(store):
    """Verify thread-safety when multiple threads update the store concurrently."""
    def worker(idx):
        for ver in range(1, 20):
            store.put("merchant", f"m_concurrent_{idx}", ver, {"worker": idx, "ver": ver})

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        concurrent.futures.wait(futures)

    counts = store.get_counts()
    assert counts["merchant"] == 10
    for i in range(10):
        assert store.get_version("merchant", f"m_concurrent_{i}") == 19


def test_load_actual_generated_dataset(store):
    """Verify store can ingest generated dataset files cleanly."""
    if not DATASET_DIR.exists():
        pytest.skip("dataset_expanded directory not found")

    # Ingest categories
    cat_dir = DATASET_DIR / "categories"
    for cat_file in cat_dir.glob("*.json"):
        data = json.loads(cat_file.read_text(encoding="utf-8"))
        slug = data.get("slug", cat_file.stem)
        ok, ack, _ = store.put("category", slug, 1, data)
        assert ok is True

    # Ingest merchants
    mer_dir = DATASET_DIR / "merchants"
    for mer_file in list(mer_dir.glob("*.json"))[:10]:
        data = json.loads(mer_file.read_text(encoding="utf-8"))
        mid = data["merchant_id"]
        ok, ack, _ = store.put("merchant", mid, 1, data)
        assert ok is True

    counts = store.get_counts()
    assert counts["category"] == 5
    assert counts["merchant"] == 10
