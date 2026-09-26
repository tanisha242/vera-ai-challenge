"""
Strategies package factory for Vera AI Assistant.
"""

from typing import Dict
from strategies.base import VerticalStrategy
from strategies.dentists import DentistStrategy
from strategies.salons import SalonStrategy
from strategies.restaurants import RestaurantStrategy
from strategies.gyms import GymStrategy
from strategies.pharmacies import PharmacyStrategy


_STRATEGIES: Dict[str, VerticalStrategy] = {
    "dentists": DentistStrategy(),
    "salons": SalonStrategy(),
    "restaurants": RestaurantStrategy(),
    "gyms": GymStrategy(),
    "pharmacies": PharmacyStrategy(),
}


def get_strategy(category_slug: str) -> VerticalStrategy:
    """
    Factory function returning the appropriate VerticalStrategy instance for a category.
    Falls back to DentistStrategy if category slug is unrecognized.
    """
    slug = (category_slug or "dentists").lower().strip()
    return _STRATEGIES.get(slug, _STRATEGIES["dentists"])
