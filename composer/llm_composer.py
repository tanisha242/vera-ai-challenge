"""
Optional Provider-Agnostic LLM-Assisted Message Composer for magicpin AI Challenge (Vera).
Generates grounded WhatsApp outbounds using standard HTTP APIs (OpenAI, Anthropic, Gemini, DeepSeek, Groq)
with strict schema validation, taboo filtering, price factual grounding, and deterministic fallback.
"""

import json
import os
import re
import time
from typing import Any, Dict, Optional, Set
from urllib import error as urlerror, request as urlrequest

from engine.decision import Decision
from strategies import get_strategy


ALLOWED_CTAS: Set[str] = {
    "open_ended",
    "binary_yes_no",
    "binary_confirm_cancel",
    "multi_choice_slot",
    "none",
}

MAX_BODY_LENGTH = 1000
TIMEOUT_LLM_SECONDS = 10.0


class LLMMessageValidator:
    """Validates LLM-generated message dict against schema, taboos, and factual grounding."""

    @staticmethod
    def validate(
        raw_output: Dict[str, Any],
        decision: Decision,
        taboo_words: list[str],
        allowed_prices: set[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Validates raw output dict from LLM. Returns sanitized dict if valid, else None.
        """
        if not isinstance(raw_output, dict):
            return None

        body = raw_output.get("body")
        if not isinstance(body, str) or not body.strip():
            return None

        body_clean = body.strip()

        # 1. Length Check
        if len(body_clean) > MAX_BODY_LENGTH:
            return None

        # 2. URL Compliance Check (strip bare http/https URLs)
        body_clean = re.sub(r"https?://\S+", "", body_clean).strip()
        if not body_clean:
            return None

        # 3. Taboo Words Check (e.g., prohibited clinical claims like "cure", "guaranteed")
        body_lower = body_clean.lower()
        for taboo in taboo_words:
            if taboo.lower() in body_lower:
                return None  # Rejected due to prohibited claims

        # 4. Price Factual Grounding Check
        # Detect currency numbers like ₹299, ₹1,499, Rs 299, Rs. 299
        found_prices = set(re.findall(r"(?:₹|rs\.?\s*)(\d+(?:,\d+)*)", body_clean, flags=re.IGNORECASE))
        if found_prices:
            normalized_allowed = {p.replace(",", "").strip() for p in allowed_prices}
            for price_str in found_prices:
                clean_price = price_str.replace(",", "").strip()
                if clean_price not in normalized_allowed:
                    return None  # Rejected due to ungrounded price claim

        # 5. CTA Check
        cta = raw_output.get("cta", "open_ended")
        if cta not in ALLOWED_CTAS:
            return None

        # 6. Send As Check
        send_as = raw_output.get("send_as", "vera")
        if send_as not in ("vera", "merchant_on_behalf"):
            send_as = "vera"

        # 7. Rationale Check
        rationale = raw_output.get("rationale") or decision.reason or "LLM generated outbound."

        return {
            "body": body_clean,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": decision.suppression_key,
            "rationale": rationale,
        }


class LLMComposer:
    """
    Provider-agnostic LLM composer supporting OpenAI, Anthropic, Gemini, DeepSeek, and Groq.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.enabled = (
            enabled
            if enabled is not None
            else (os.getenv("VERA_LLM_ENABLED", "false").lower() in ("true", "1"))
        )
        self.provider = (
            provider or os.getenv("VERA_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "openai"
        ).lower()
        self.api_key = (
            api_key
            or os.getenv("VERA_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or ""
        )
        self.model = model or os.getenv("VERA_LLM_MODEL") or ""

    def is_available(self) -> bool:
        return bool(self.enabled and self.api_key.strip())

    def compose(self, decision: Decision) -> Optional[Dict[str, Any]]:
        """
        Attempts to compose proactive message via LLM provider.
        Returns validated message dict on success, or None on failure/fallback.
        """
        if not self.is_available() or decision.action_type == "no_action":
            return None

        merchant = decision.merchant or {}
        category = decision.category or {}
        trigger = decision.trigger or {}
        customer = decision.customer or {}
        cat_slug = category.get("slug") or merchant.get("category_slug", "dentists")

        strategy = get_strategy(cat_slug)
        taboo_words = strategy.get_taboo_words()

        # Extract allowed prices from contexts for factual grounding validation
        allowed_prices = set()
        for offer in merchant.get("offers", []) + category.get("offer_catalog", []):
            title = str(offer.get("title", "")) + " " + str(offer.get("value", ""))
            matches = re.findall(r"\d+", title)
            allowed_prices.update(matches)
        if trigger.get("payload"):
            payload_str = json.dumps(trigger["payload"])
            allowed_prices.update(re.findall(r"\d+", payload_str))

        prompt = self._build_prompt(category, merchant, trigger, customer, strategy)

        try:
            raw_response = self._call_provider(prompt)
            if not raw_response:
                return None

            json_match = re.search(r"\{[\s\S]*\}", raw_response)
            if not json_match:
                return None

            parsed = json.loads(json_match.group())
            return LLMMessageValidator.validate(parsed, decision, taboo_words, allowed_prices)
        except Exception:
            return None

    def _build_prompt(
        self, category: Dict, merchant: Dict, trigger: Dict, customer: Dict, strategy: Any
    ) -> str:
        owner = (
            merchant.get("identity", {}).get("owner_first_name")
            or merchant.get("identity", {}).get("name", "Merchant")
        )
        return f"""You are Vera, magicpin's merchant AI assistant on WhatsApp in India.
COMPOSE A WHATSAPP MESSAGE FOR:
Merchant: {merchant.get('identity', {}).get('name', 'Merchant')} (Owner: {owner})
Category: {category.get('slug', 'general')}
Voice Rules: {json.dumps(category.get('voice', {}))}
Taboo Phrases (FORBIDDEN): {strategy.get_taboo_words()}
Trigger Event: {trigger.get('kind', 'nudge')} - Payload: {json.dumps(trigger.get('payload', {}))}
Customer (if any): {customer.get('identity', {}).get('name') if customer else 'None'}

CONSTRAINTS:
1. Concise WhatsApp body (<150 words). Ground ONLY on provided facts. No invented prices or discounts.
2. Taboo phrases strictly forbidden. No claims of "cure" or "guaranteed".
3. Output MUST be valid JSON with keys: "body", "cta", "send_as", "rationale".
Allowed CTA values: "open_ended", "binary_yes_no", "binary_confirm_cancel", "multi_choice_slot".

Respond ONLY with valid JSON."""

    def _call_provider(self, prompt: str) -> Optional[str]:
        if self.provider in ("openai", "groq", "deepseek"):
            url_map = {
                "openai": ("https://api.openai.com/v1/chat/completions", self.model or "gpt-4o-mini"),
                "groq": ("https://api.groq.com/openai/v1/chat/completions", self.model or "llama-3.1-70b-versatile"),
                "deepseek": ("https://api.deepseek.com/v1/chat/completions", self.model or "deepseek-chat"),
            }
            url, model_name = url_map[self.provider]
            body = json.dumps({
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 500,
            }).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            req = urlrequest.Request(url, data=body, headers=headers)
            resp = urlrequest.urlopen(req, timeout=TIMEOUT_LLM_SECONDS)
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        elif self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            body = json.dumps({
                "model": self.model or "claude-3-5-sonnet-20241022",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            req = urlrequest.Request(url, data=body, headers=headers)
            resp = urlrequest.urlopen(req, timeout=TIMEOUT_LLM_SECONDS)
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"]
        elif self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model or 'gemini-1.5-flash'}:generateContent?key={self.api_key}"
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
            }).encode("utf-8")
            req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"})
            resp = urlrequest.urlopen(req, timeout=TIMEOUT_LLM_SECONDS)
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return None
