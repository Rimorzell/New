"""
Intelligent Product Substitution Engine for Lighting Manufacturing

This engine processes customer BOQs (Bill of Quantities) and finds the best matching
products from our 2025 catalog using weighted scoring across multiple dimensions:
- Environment/IP Rating (highest priority)
- Form Factor/Shape
- Performance (Wattage, Lumens, Efficacy)
- Features (Dimming, Emergency, etc.)
"""

from .engine import SubstitutionEngine
from .models import Product, BOQItem, MatchResult, EnvironmentContext
from .catalog import ProductCatalog
from .boq_parser import BOQParser
from .scoring import ScoringEngine

__version__ = "1.0.0"
__all__ = [
    "SubstitutionEngine",
    "Product",
    "BOQItem",
    "MatchResult",
    "EnvironmentContext",
    "ProductCatalog",
    "BOQParser",
    "ScoringEngine",
]
