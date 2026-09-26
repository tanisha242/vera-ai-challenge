"""
Thread-safe SuppressionEngine tracking suppression keys, opt-out lists,
and deduplication constraints to prevent spamming merchants/customers.
"""

import threading
from datetime import datetime, timezone
from typing import Any


class SuppressionEngine:
    def __init__(self):
        self._lock = threading.RLock()
        # Set of active suppression keys: suppression_key -> expiration_iso_str
        self._suppression_keys: dict[str, str | None] = {}
        # Set of suppressed merchant IDs (opted out)
        self._opted_out_merchants: set[str] = set()
        # Set of suppressed customer IDs (opted out)
        self._opted_out_customers: set[str] = set()

    @staticmethod
    def get_trigger_suppression_key(trigger: dict[str, Any]) -> str:
        """
        Derive a stable suppression key for a trigger.
        Uses trigger["suppression_key"] if present, else synthesizes from kind and scope.
        """
        if trigger.get("suppression_key"):
            return trigger["suppression_key"]

        kind = trigger.get("kind", "gen")
        mid = trigger.get("merchant_id", "unknown_m")
        cid = trigger.get("customer_id") or "merchant"
        return f"{kind}:{mid}:{cid}"

    def is_suppressed(self, suppression_key: str | None) -> bool:
        """Check if a suppression key is active and not expired."""
        if not suppression_key:
            return False

        with self._lock:
            if suppression_key not in self._suppression_keys:
                return False

            expires_at = self._suppression_keys[suppression_key]
            if expires_at:
                try:
                    exp_clean = expires_at.replace("Z", "+00:00")
                    exp_dt = datetime.fromisoformat(exp_clean)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    now_dt = datetime.now(timezone.utc)
                    if now_dt > exp_dt:
                        # Expired, clean up
                        del self._suppression_keys[suppression_key]
                        return False
                except Exception:
                    pass

            return True

    def suppress(self, suppression_key: str, expires_at: str | None = None):
        """Mark a suppression key as active."""
        if not suppression_key:
            return
        with self._lock:
            self._suppression_keys[suppression_key] = expires_at

    def opt_out_merchant(self, merchant_id: str):
        """Opt-out a merchant from future proactive touchpoints."""
        if merchant_id:
            with self._lock:
                self._opted_out_merchants.add(merchant_id)

    def is_merchant_opted_out(self, merchant_id: str | None) -> bool:
        """Check if a merchant is opted out."""
        if not merchant_id:
            return False
        with self._lock:
            return merchant_id in self._opted_out_merchants

    def opt_out_customer(self, customer_id: str):
        """Opt-out a customer from future outreach."""
        if customer_id:
            with self._lock:
                self._opted_out_customers.add(customer_id)

    def is_customer_opted_out(self, customer_id: str | None) -> bool:
        """Check if a customer is opted out."""
        if not customer_id:
            return False
        with self._lock:
            return customer_id in self._opted_out_customers

    def clear(self):
        """Clear all suppression state (for testing/reset)."""
        with self._lock:
            self._suppression_keys.clear()
            self._opted_out_merchants.clear()
            self._opted_out_customers.clear()


# Global shared instance
suppression_engine = SuppressionEngine()
