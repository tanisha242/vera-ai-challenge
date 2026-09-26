"""
Thread-safe in-memory ContextStore supporting scope isolation, atomic versioning,
and HTTP 409 stale_version semantics matching magicpin challenge specifications.
"""

import threading
from datetime import datetime
from typing import Any, Tuple


VALID_SCOPES = {"category", "merchant", "customer", "trigger"}


class ContextStore:
    def __init__(self):
        self._lock = threading.RLock()
        # Internal dictionary keyed by (scope, context_id) -> {"version": int, "payload": dict, "updated_at": str}
        self._store: dict[Tuple[str, str], dict[str, Any]] = {}

    def put(
        self, scope: str, context_id: str, version: int, payload: dict[str, Any]
    ) -> Tuple[bool, str, int | None]:
        """
        Store context payload using atomic version checking.

        Returns:
            (success: True, ack_id: str, current_version: None) on 200 success
            (success: False, reason: "stale_version", current_version: int) on 409 conflict
            (success: False, reason: "invalid_scope", current_version: None) on 400 bad request
        """
        if scope not in VALID_SCOPES:
            return False, "invalid_scope", None

        if not context_id or not str(context_id).strip():
            return False, "invalid_context_id", None

        if version is None or version < 1:
            return False, "invalid_version", None

        key = (scope, str(context_id).strip())

        with self._lock:
            cur = self._store.get(key)
            if cur and cur["version"] >= version:
                return False, "stale_version", cur["version"]

            now_iso = datetime.utcnow().isoformat() + "Z"
            self._store[key] = {
                "version": version,
                "payload": payload,
                "updated_at": now_iso,
            }
            ack_id = f"ack_{context_id}_v{version}"
            return True, ack_id, None

    def get(self, scope: str, context_id: str) -> dict[str, Any] | None:
        """Get full record dict {"version": int, "payload": dict, ...} for a key."""
        with self._lock:
            return self._store.get((scope, context_id))

    def get_payload(self, scope: str, context_id: str) -> dict[str, Any] | None:
        """Get just the stored payload dict for a key."""
        with self._lock:
            rec = self._store.get((scope, context_id))
            return rec["payload"] if rec else None

    def get_version(self, scope: str, context_id: str) -> int | None:
        """Get current version number for a key."""
        with self._lock:
            rec = self._store.get((scope, context_id))
            return rec["version"] if rec else None

    def get_all(self, scope: str) -> dict[str, dict[str, Any]]:
        """Get all stored context_ids and their payloads for a specific scope."""
        with self._lock:
            return {
                cid: item["payload"]
                for (s, cid), item in self._store.items()
                if s == scope
            }

    def get_counts(self) -> dict[str, int]:
        """Return counts of loaded contexts per scope (used by /v1/healthz)."""
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _ in self._store.items():
                if scope in counts:
                    counts[scope] += 1
        return counts

    def clear(self):
        """Clear all stored contexts (used for testing or teardown)."""
        with self._lock:
            self._store.clear()


# Global shared instance
store = ContextStore()
