"""
Human-Readable Justification Generator.

Creates clear, professional explanations for product matches
that sales teams can use directly with customers.
"""

from typing import List
from .models import (
    Product, BOQItem, MatchResult, ScoreBreakdown,
    FormFactor, EnvironmentContext
)


class JustificationGenerator:
    """
    Generates human-readable justifications for product match decisions.
    """

    def generate_justification(self, item: BOQItem, product: Product,
                              score: float, breakdown: ScoreBreakdown) -> str:
        """
        Generate a comprehensive justification for the match.
        """
        parts = []

        # Opening statement based on confidence
        opening = self._generate_opening(score, item, product)
        parts.append(opening)

        # Key matching factors
        factors = self._summarize_key_factors(breakdown)
        if factors:
            parts.append(f"Key factors: {factors}")

        # Any trade-offs or compromises
        tradeoffs = self._identify_tradeoffs(item, product, breakdown)
        if tradeoffs:
            parts.append(f"Note: {tradeoffs}")

        return " ".join(parts)

    def _generate_opening(self, score: float, item: BOQItem, product: Product) -> str:
        """Generate the opening statement."""
        if score >= 0.95:
            return f"Excellent match: {product.sku} precisely meets all specifications."
        elif score >= 0.85:
            return f"Strong match: {product.sku} meets requirements with minor variations."
        elif score >= 0.70:
            return f"Good match: {product.sku} is a suitable alternative."
        elif score >= 0.50:
            return f"Acceptable match: {product.sku} is the closest available option."
        else:
            return f"Best available: {product.sku} selected as nearest engineering equivalent."

    def _summarize_key_factors(self, breakdown: ScoreBreakdown) -> str:
        """Summarize the key positive matching factors."""
        factors = []

        # IP rating
        if "meets" in breakdown.ip_reason.lower() or "exact" in breakdown.ip_reason.lower():
            factors.append(breakdown.ip_reason.split("(")[0].strip())

        # Form factor
        if "exact" in breakdown.form_factor_reason.lower():
            factors.append("correct form factor")
        elif "compatible" in breakdown.form_factor_reason.lower():
            factors.append("compatible shape")

        # Wattage
        if breakdown.wattage_score > 0:
            if "exact" in breakdown.wattage_reason.lower():
                factors.append("exact wattage")
            elif "within" in breakdown.wattage_reason.lower():
                factors.append(breakdown.wattage_reason.lower())

        # Efficacy
        if "excellent" in breakdown.efficacy_reason.lower():
            factors.append("excellent energy efficiency")
        elif "very good" in breakdown.efficacy_reason.lower():
            factors.append("high efficiency")

        return ", ".join(factors) if factors else ""

    def _identify_tradeoffs(self, item: BOQItem, product: Product,
                           breakdown: ScoreBreakdown) -> str:
        """Identify any trade-offs or compromises in the match."""
        tradeoffs = []

        # Wattage difference
        if item.requested_wattage and product.power_w:
            diff = product.power_w - item.requested_wattage
            if abs(diff) > 2:  # More than 2W difference
                direction = "higher" if diff > 0 else "lower"
                percent = abs(diff) / item.requested_wattage * 100
                tradeoffs.append(f"{percent:.0f}% {direction} wattage")

        # IP rating compromise
        if "CRITICAL" in breakdown.ip_reason or "WARNING" in breakdown.ip_reason:
            tradeoffs.append("IP rating review recommended")

        # Missing features
        if "WARNING" in breakdown.feature_reason:
            if "Emergency" in breakdown.feature_reason:
                tradeoffs.append("emergency option may need separate sourcing")
            if "DALI" in breakdown.feature_reason:
                tradeoffs.append("DALI variant recommended")

        return "; ".join(tradeoffs) if tradeoffs else ""

    def generate_warnings(self, item: BOQItem, product: Product,
                         breakdown: ScoreBreakdown) -> List[str]:
        """Generate warning messages for issues requiring attention."""
        warnings = []

        # Critical IP mismatch
        if "CRITICAL" in breakdown.ip_reason:
            warnings.append(
                f"IP RATING MISMATCH: Product is {product.ip_rating or 'IP20'} but "
                f"application requires higher protection. Verify suitability for "
                f"{item.environment.value.replace('_', ' ')} environment."
            )

        # Form factor mismatch
        if "mismatch" in breakdown.form_factor_reason.lower():
            warnings.append(
                f"FORM FACTOR: Requested {item.requested_form_factor.value if item.requested_form_factor else 'unspecified'} "
                f"but matched {product.form_factor.value}. Verify physical compatibility."
            )

        # Missing emergency
        if item.requires_emergency and not product.is_emergency:
            warnings.append(
                "EMERGENCY: Product does not include emergency backup. "
                "Consider emergency conversion kit or alternative SKU."
            )

        # Missing DALI
        if item.requires_dali and not product.is_dali:
            warnings.append(
                "DALI: Product is not DALI compatible. "
                "Check for DALI variant or separate DALI driver."
            )

        # Large wattage difference
        if item.requested_wattage and product.power_w:
            diff_pct = abs(product.power_w - item.requested_wattage) / item.requested_wattage * 100
            if diff_pct > 25:
                warnings.append(
                    f"WATTAGE: {diff_pct:.0f}% difference from specification. "
                    f"Requested {item.requested_wattage}W, matched {product.power_w}W. "
                    "Verify lighting design calculations."
                )

        return warnings

    def format_match_summary(self, result: MatchResult) -> str:
        """Format a complete match summary for output."""
        lines = []

        # Header
        lines.append(f"BOQ Row {result.boq_item.row_number}: {result.boq_item.raw_description[:60]}...")
        lines.append("-" * 70)

        # Match result
        lines.append(f"  Matched SKU: {result.product.sku}")
        lines.append(f"  Category: {result.product.category}")
        lines.append(f"  Price: {result.product.price:.2f}")

        # Specs
        specs = []
        if result.product.power_w:
            specs.append(f"{result.product.power_w}W")
        if result.product.lumen:
            specs.append(f"{result.product.lumen:.0f}lm")
        if result.product.ip_rating:
            specs.append(str(result.product.ip_rating))
        if specs:
            lines.append(f"  Specifications: {' | '.join(specs)}")

        # Confidence
        lines.append(f"  Confidence: {result.confidence_score:.0%} ({result.confidence_level})")

        # Justification
        lines.append(f"  Justification: {result.justification}")

        # Warnings
        if result.warnings:
            lines.append("  WARNINGS:")
            for warning in result.warnings:
                lines.append(f"    - {warning}")

        # Review flag
        if result.needs_review:
            lines.append("  >>> FLAGGED FOR HUMAN REVIEW <<<")

        return "\n".join(lines)

    def format_batch_report(self, results: List[MatchResult]) -> str:
        """Format a report for a batch of matches."""
        lines = []

        # Summary header
        total = len(results)
        high_conf = sum(1 for r in results if r.confidence_score >= 0.85)
        needs_review = sum(1 for r in results if r.needs_review)

        lines.append("=" * 70)
        lines.append("PRODUCT SUBSTITUTION REPORT")
        lines.append("=" * 70)
        lines.append(f"Total Items: {total}")
        lines.append(f"High Confidence Matches: {high_conf} ({high_conf/total*100:.0f}%)")
        lines.append(f"Flagged for Review: {needs_review} ({needs_review/total*100:.0f}%)")
        lines.append("=" * 70)
        lines.append("")

        # Individual matches
        for result in results:
            lines.append(self.format_match_summary(result))
            lines.append("")

        # Footer summary
        lines.append("=" * 70)
        lines.append("LEGEND:")
        lines.append("  HIGH confidence (>85%): Proceed with order")
        lines.append("  MEDIUM confidence (70-85%): Review recommended")
        lines.append("  LOW confidence (<70%): Manual selection required")
        lines.append("=" * 70)

        return "\n".join(lines)
