"""
Weighted Scoring Engine for Product Matching.

Uses a soft-scoring approach that never hard-filters products,
ensuring we always return the best available match.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import math

from .models import (
    Product, BOQItem, IPRating, FormFactor, ScoreBreakdown,
    EnvironmentContext, ENVIRONMENT_IP_REQUIREMENTS
)


@dataclass
class ScoringWeights:
    """Configurable weights for the scoring algorithm."""
    # Environment/IP is highest priority (critical for safety/compliance)
    ip_rating: float = 35.0

    # Form factor is second priority (aesthetic/functional)
    form_factor: float = 25.0

    # Performance specs
    wattage: float = 15.0
    lumens: float = 10.0
    efficacy_bonus: float = 5.0

    # Features
    emergency: float = 5.0
    dali: float = 3.0
    dimming: float = 2.0


class ScoringEngine:
    """
    Calculates match scores between BOQ items and catalog products.
    Uses weighted scoring to rank all products without hard filtering.
    """

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()

    def score_match(self, item: BOQItem, product: Product) -> Tuple[float, ScoreBreakdown]:
        """
        Score how well a product matches a BOQ item.
        Returns (normalized_score, breakdown) where score is 0.0-1.0.
        """
        breakdown = ScoreBreakdown()

        # Calculate individual component scores
        breakdown.ip_score, breakdown.ip_reason = self._score_ip(item, product)
        breakdown.form_factor_score, breakdown.form_factor_reason = self._score_form_factor(item, product)
        breakdown.wattage_score, breakdown.wattage_reason = self._score_wattage(item, product)
        breakdown.lumen_score, breakdown.lumen_reason = self._score_lumens(item, product)
        breakdown.efficacy_bonus, breakdown.efficacy_reason = self._score_efficacy(item, product)
        breakdown.feature_score, breakdown.feature_reason = self._score_features(item, product)

        # Calculate total weighted score
        total = breakdown.total_weighted_score
        max_possible = self._max_possible_score(item)

        # Normalize to 0.0-1.0
        normalized = total / max_possible if max_possible > 0 else 0.0
        normalized = max(0.0, min(1.0, normalized))  # Clamp

        return normalized, breakdown

    def _max_possible_score(self, item: BOQItem) -> float:
        """Calculate maximum possible score for normalization."""
        max_score = (
            self.weights.ip_rating +
            self.weights.form_factor +
            self.weights.wattage +
            self.weights.lumens +
            self.weights.efficacy_bonus
        )

        # Add feature weights only if required
        if item.requires_emergency:
            max_score += self.weights.emergency
        if item.requires_dali:
            max_score += self.weights.dali
        if item.requires_dimming:
            max_score += self.weights.dimming

        return max_score

    def _score_ip(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """
        Score IP rating match.
        Critical: Indoor products should NEVER be suggested for outdoor/wet applications.
        """
        weight = self.weights.ip_rating

        # Get required IP based on environment
        required_ip = item.requested_ip
        if required_ip is None:
            required_ip = ENVIRONMENT_IP_REQUIREMENTS.get(
                item.environment,
                IPRating(2, 0, "IP20")
            )

        product_ip = product.ip_rating

        if product_ip is None:
            # No IP rating on product - assume IP20 (indoor only)
            product_ip = IPRating(2, 0, "IP20")

        # Calculate score
        if product_ip.meets_requirement(required_ip):
            # Full score for meeting requirement
            score = weight
            reason = f"IP{product_ip.solid_protection}{product_ip.liquid_protection} meets requirement"

            # Small bonus for exact match (avoid over-spec)
            if product_ip.numeric_value == required_ip.numeric_value:
                reason = f"Exact IP match ({product_ip})"
        else:
            # Penalty for not meeting requirement - proportional to gap
            required_val = required_ip.numeric_value
            product_val = product_ip.numeric_value
            gap = required_val - product_val

            # IP20 vs IP65 requirement is a severe mismatch
            if gap >= 45:
                score = weight * 0.1  # 90% penalty
                reason = f"CRITICAL: {product_ip} insufficient for {required_ip} requirement"
            elif gap >= 25:
                score = weight * 0.3  # 70% penalty
                reason = f"WARNING: {product_ip} below {required_ip} requirement"
            else:
                score = weight * 0.6  # 40% penalty
                reason = f"{product_ip} slightly below {required_ip} requirement"

        return score, reason

    def _score_form_factor(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """Score form factor match."""
        weight = self.weights.form_factor

        if item.requested_form_factor is None:
            # No specific form factor requested - neutral score
            return weight * 0.7, "No specific form factor requested"

        if item.requested_form_factor == FormFactor.UNKNOWN:
            return weight * 0.7, "Form factor not specified"

        if product.form_factor == item.requested_form_factor:
            return weight, f"Exact {item.requested_form_factor.value} match"

        # Check for compatible form factors
        compatibility = {
            FormFactor.ROUND: [FormFactor.CYLINDER, FormFactor.ADJUSTABLE],
            FormFactor.LINEAR: [FormFactor.RECTANGULAR],
            FormFactor.SPOT: [FormFactor.ADJUSTABLE, FormFactor.TRACK],
            FormFactor.SQUARE: [FormFactor.RECTANGULAR],
            FormFactor.RECTANGULAR: [FormFactor.SQUARE, FormFactor.LINEAR],
        }

        compatible_list = compatibility.get(item.requested_form_factor, [])
        if product.form_factor in compatible_list:
            score = weight * 0.7
            reason = f"{product.form_factor.value} compatible with {item.requested_form_factor.value}"
            return score, reason

        # Mismatch
        score = weight * 0.2
        reason = f"Form mismatch: requested {item.requested_form_factor.value}, got {product.form_factor.value}"
        return score, reason

    def _score_wattage(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """
        Score wattage match.
        Tolerance: ±20% is acceptable.
        """
        weight = self.weights.wattage

        if item.requested_wattage is None:
            # No wattage specified - neutral score
            return weight * 0.7, "No specific wattage requested"

        if product.power_w is None:
            return weight * 0.3, "Product wattage unknown"

        requested = item.requested_wattage
        actual = product.power_w

        # Calculate percentage difference
        diff_percent = abs(actual - requested) / requested * 100

        if diff_percent <= 5:
            score = weight
            reason = f"Exact wattage match ({actual}W)"
        elif diff_percent <= 10:
            score = weight * 0.95
            reason = f"{actual}W within 10% of requested {requested}W"
        elif diff_percent <= 20:
            score = weight * 0.85
            reason = f"{actual}W within 20% tolerance of {requested}W"
        elif diff_percent <= 30:
            score = weight * 0.6
            reason = f"{actual}W is {diff_percent:.0f}% from requested {requested}W"
        else:
            score = weight * 0.3
            direction = "higher" if actual > requested else "lower"
            reason = f"{actual}W significantly {direction} than {requested}W ({diff_percent:.0f}% difference)"

        return score, reason

    def _score_lumens(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """
        Score lumen output match.
        Tolerance: ±15% is acceptable.
        Prefer slightly higher lumens over lower.
        """
        weight = self.weights.lumens

        if item.requested_lumens is None:
            # No lumens specified - check if we can infer from wattage
            if item.requested_wattage and product.lumen:
                # Assume ~100 lm/W efficiency expectation
                expected = item.requested_wattage * 100
                return self._score_lumen_value(weight, expected, product.lumen)
            return weight * 0.7, "No specific lumen output requested"

        if product.lumen is None:
            return weight * 0.3, "Product lumen output unknown"

        return self._score_lumen_value(weight, item.requested_lumens, product.lumen)

    def _score_lumen_value(self, weight: float, requested: float,
                          actual: float) -> Tuple[float, str]:
        """Score lumen value comparison."""
        diff_percent = (actual - requested) / requested * 100

        if abs(diff_percent) <= 5:
            return weight, f"Lumen output matches ({actual:.0f}lm)"
        elif -15 <= diff_percent <= 20:
            # Slight bonus for higher lumens within tolerance
            bonus = 0.05 if diff_percent > 0 else 0
            score = weight * (0.9 + bonus)
            direction = "higher" if diff_percent > 0 else "lower"
            return score, f"{actual:.0f}lm ({abs(diff_percent):.0f}% {direction} than {requested:.0f}lm)"
        elif -25 <= diff_percent <= 30:
            score = weight * 0.6
            return score, f"{actual:.0f}lm outside 15% tolerance"
        else:
            score = weight * 0.3
            return score, f"{actual:.0f}lm significantly different from {requested:.0f}lm"

    def _score_efficacy(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """
        Score efficacy (lm/W) as a bonus factor.
        Higher efficacy is always better.
        """
        weight = self.weights.efficacy_bonus

        if product.efficacy is None:
            return 0, "Efficacy unknown"

        efficacy = product.efficacy

        # Benchmark: 100 lm/W is good, 120+ is excellent
        if efficacy >= 130:
            return weight, f"Excellent efficacy ({efficacy:.0f} lm/W)"
        elif efficacy >= 110:
            return weight * 0.8, f"Very good efficacy ({efficacy:.0f} lm/W)"
        elif efficacy >= 90:
            return weight * 0.5, f"Good efficacy ({efficacy:.0f} lm/W)"
        elif efficacy >= 70:
            return weight * 0.2, f"Standard efficacy ({efficacy:.0f} lm/W)"
        else:
            return 0, f"Low efficacy ({efficacy:.0f} lm/W)"

    def _score_features(self, item: BOQItem, product: Product) -> Tuple[float, str]:
        """Score feature matches (emergency, DALI, dimming)."""
        total_score = 0.0
        reasons = []

        # Emergency
        if item.requires_emergency:
            if product.is_emergency:
                total_score += self.weights.emergency
                reasons.append("Emergency backup included")
            else:
                reasons.append("WARNING: Emergency required but not available")

        # DALI
        if item.requires_dali:
            if product.is_dali:
                total_score += self.weights.dali
                reasons.append("DALI compatible")
            else:
                reasons.append("WARNING: DALI required but not available")

        # Dimming
        if item.requires_dimming:
            if product.dimming or product.is_dali:
                total_score += self.weights.dimming
                reasons.append("Dimmable")
            else:
                reasons.append("WARNING: Dimming required but not available")

        reason = "; ".join(reasons) if reasons else "No special features required"
        return total_score, reason

    def rank_products(self, item: BOQItem,
                     candidates: List[Product],
                     top_n: int = 10) -> List[Tuple[Product, float, ScoreBreakdown]]:
        """
        Rank all candidate products for a BOQ item.
        Returns list of (product, score, breakdown) tuples sorted by score descending.
        """
        scored = []

        for product in candidates:
            score, breakdown = self.score_match(item, product)
            scored.append((product, score, breakdown))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_n]
