"""
Abstract base strategy class for category-specific messaging in Vera AI Assistant.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from engine.decision import Decision


class VerticalStrategy(ABC):
    """
    Abstract strategy interface for vertical category messaging.
    Defines methods for factual mapping, voice enforcement, taboo checking, and CTA recommendation.
    """

    @property
    @abstractmethod
    def slug(self) -> str:
        """Category slug identifier (e.g. 'dentists', 'salons')."""
        pass

    @abstractmethod
    def get_voice_rules(self) -> Dict[str, Any]:
        """Returns category voice rules dictionary."""
        pass

    @abstractmethod
    def get_taboo_words(self) -> list[str]:
        """Returns forbidden taboo terms for this vertical."""
        pass

    @abstractmethod
    def format_message(self, decision: Decision) -> Dict[str, Any]:
        """
        Formats a factual, grounded proactive message based on decision context.

        Returns dict matching official schema:
        {
            "body": str,
            "cta": str,
            "send_as": "vera" | "merchant_on_behalf",
            "suppression_key": str,
            "rationale": str
        }
        """
        pass

    def check_and_clean_taboos(self, text: str) -> str:
        """Scans text for category taboos and removes or rewrites offending phrases."""
        text_lower = text.lower()
        cleaned = text
        for taboo in self.get_taboo_words():
            if taboo.lower() in text_lower:
                # Remove taboo phrase case-insensitively
                pattern = f"(?i){taboo}"
                import re
                cleaned = re.sub(pattern, "", cleaned).strip()
        return cleaned
