"""
Main Substitution Engine - Orchestrates the entire matching process.
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .models import (
    Product, BOQItem, MatchResult, ScoreBreakdown,
    FormFactor, EnvironmentContext, IPRating,
    ENVIRONMENT_IP_REQUIREMENTS
)
from .catalog import ProductCatalog
from .boq_parser import BOQParser
from .scoring import ScoringEngine, ScoringWeights
from .justifier import JustificationGenerator


class SubstitutionEngine:
    """
    Intelligent Product Substitution Engine.

    Philosophy: Never return "No results." Always find the closest
    engineering equivalent and explain the trade-offs.
    """

    def __init__(self, catalog_path: Optional[str] = None,
                 weights: Optional[ScoringWeights] = None):
        """
        Initialize the substitution engine.

        Args:
            catalog_path: Path to the product catalog CSV file
            weights: Optional custom scoring weights
        """
        self.catalog = ProductCatalog()
        self.boq_parser = BOQParser()
        self.scorer = ScoringEngine(weights)
        self.justifier = JustificationGenerator()

        self._catalog_loaded = False

        if catalog_path:
            self.load_catalog(catalog_path)

    def load_catalog(self, filepath: str) -> int:
        """
        Load the product catalog from a CSV file.
        Returns number of products loaded.
        """
        count = self.catalog.load_from_csv(filepath)
        self._catalog_loaded = True
        return count

    def process_boq_file(self, filepath: str,
                        output_path: Optional[str] = None) -> List[MatchResult]:
        """
        Process an entire BOQ file and find matches for all items.

        Args:
            filepath: Path to the BOQ file (CSV or Excel)
            output_path: Optional path to write results

        Returns:
            List of MatchResult objects
        """
        if not self._catalog_loaded:
            raise RuntimeError("Catalog not loaded. Call load_catalog() first.")

        # Parse BOQ
        items = self.boq_parser.parse_file(filepath)

        # Process each item
        results = []
        for item in items:
            result = self.find_best_match(item)
            results.append(result)

        # Write output if path provided
        if output_path:
            self._write_results(results, output_path)

        return results

    def find_best_match(self, item: BOQItem,
                       num_alternatives: int = 3) -> MatchResult:
        """
        Find the best matching product for a BOQ item.

        This method NEVER returns None - it always finds the closest
        engineering equivalent available.
        """
        # Get candidate products
        candidates = self._get_candidates(item)

        if not candidates:
            # Fallback to all products if no candidates found
            candidates = self.catalog.products

        # Score and rank candidates
        ranked = self.scorer.rank_products(item, candidates, top_n=num_alternatives + 1)

        if not ranked:
            # Emergency fallback - should never happen with proper catalog
            raise RuntimeError("No products available in catalog")

        # Best match
        best_product, best_score, best_breakdown = ranked[0]

        # Generate justification and warnings
        justification = self.justifier.generate_justification(
            item, best_product, best_score, best_breakdown
        )
        warnings = self.justifier.generate_warnings(item, best_product, best_breakdown)

        # Build alternative matches
        alternatives = []
        for product, score, breakdown in ranked[1:num_alternatives + 1]:
            alt_justification = self.justifier.generate_justification(
                item, product, score, breakdown
            )
            alt_warnings = self.justifier.generate_warnings(item, product, breakdown)
            alt_result = MatchResult(
                boq_item=item,
                product=product,
                confidence_score=score,
                score_breakdown=breakdown,
                justification=alt_justification,
                warnings=alt_warnings
            )
            alternatives.append(alt_result)

        # Create result
        result = MatchResult(
            boq_item=item,
            product=best_product,
            confidence_score=best_score,
            score_breakdown=best_breakdown,
            justification=justification,
            warnings=warnings,
            alternatives=alternatives
        )

        return result

    def find_match_for_description(self, description: str,
                                   num_alternatives: int = 3) -> MatchResult:
        """
        Find matches for a single description string.
        Useful for ad-hoc queries without a full BOQ file.
        """
        if not self._catalog_loaded:
            raise RuntimeError("Catalog not loaded. Call load_catalog() first.")

        item = self.boq_parser.parse_description(description)
        return self.find_best_match(item, num_alternatives)

    def _get_candidates(self, item: BOQItem) -> List[Product]:
        """
        Get candidate products for an item.
        Uses smart filtering to reduce search space while ensuring
        we don't miss potential matches.
        """
        # Use dict keyed by row_id to track unique products
        candidates_by_id = {}

        # Primary filter: Form factor
        if item.requested_form_factor and item.requested_form_factor != FormFactor.UNKNOWN:
            ff_products = self.catalog.get_by_form_factor(item.requested_form_factor)
            for p in ff_products:
                candidates_by_id[p.row_id] = p

            # Add compatible form factors
            compatibility = {
                FormFactor.ROUND: [FormFactor.CYLINDER, FormFactor.ADJUSTABLE],
                FormFactor.LINEAR: [FormFactor.RECTANGULAR],
                FormFactor.SPOT: [FormFactor.ADJUSTABLE, FormFactor.TRACK],
                FormFactor.SQUARE: [FormFactor.RECTANGULAR],
            }
            for compat_ff in compatibility.get(item.requested_form_factor, []):
                for p in self.catalog.get_by_form_factor(compat_ff):
                    candidates_by_id[p.row_id] = p

        # Secondary filter: IP rating (add products that meet requirement)
        required_ip = item.requested_ip
        if required_ip is None:
            required_ip = ENVIRONMENT_IP_REQUIREMENTS.get(
                item.environment,
                IPRating(2, 0, "IP20")
            )

        ip_products = self.catalog.get_products_meeting_ip(required_ip)
        ip_product_ids = {p.row_id for p in ip_products}

        if candidates_by_id:
            # Intersect with IP-appropriate products
            intersected = {rid: p for rid, p in candidates_by_id.items() if rid in ip_product_ids}

            # If intersection is too small, add IP-appropriate products
            if len(intersected) < 10:
                for p in ip_products[:50]:
                    intersected[p.row_id] = p
            candidates_by_id = intersected
        else:
            for p in ip_products:
                candidates_by_id[p.row_id] = p

        # If still no candidates, use text search
        if not candidates_by_id and item.raw_description:
            text_results = self.catalog.search_text(item.raw_description, limit=50)
            for p in text_results:
                candidates_by_id[p.row_id] = p

        # Final fallback: all products
        if not candidates_by_id:
            for p in self.catalog.products[:200]:
                candidates_by_id[p.row_id] = p

        return list(candidates_by_id.values())

    def _write_results(self, results: List[MatchResult], output_path: str):
        """Write results to file (CSV, JSON, or TXT)."""
        path = Path(output_path)
        suffix = path.suffix.lower()

        if suffix == '.csv':
            self._write_csv(results, path)
        elif suffix == '.json':
            self._write_json(results, path)
        else:
            self._write_text(results, path)

    def _write_csv(self, results: List[MatchResult], path: Path):
        """Write results to CSV."""
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'BOQ_Row', 'BOQ_Description', 'Matched_SKU', 'Matched_Category',
                'Price', 'Wattage', 'Lumens', 'IP_Rating', 'Confidence_Score',
                'Confidence_Level', 'Justification', 'Warnings', 'Needs_Review',
                'Alt_1_SKU', 'Alt_1_Score', 'Alt_2_SKU', 'Alt_2_Score'
            ])

            # Data rows
            for result in results:
                alt_1_sku = result.alternatives[0].product.sku if len(result.alternatives) > 0 else ''
                alt_1_score = f"{result.alternatives[0].confidence_score:.0%}" if len(result.alternatives) > 0 else ''
                alt_2_sku = result.alternatives[1].product.sku if len(result.alternatives) > 1 else ''
                alt_2_score = f"{result.alternatives[1].confidence_score:.0%}" if len(result.alternatives) > 1 else ''

                writer.writerow([
                    result.boq_item.row_number,
                    result.boq_item.raw_description[:100],
                    result.product.sku,
                    result.product.category,
                    f"{result.product.price:.2f}",
                    result.product.power_w or '',
                    result.product.lumen or '',
                    str(result.product.ip_rating) if result.product.ip_rating else '',
                    f"{result.confidence_score:.2f}",
                    result.confidence_level,
                    result.justification,
                    '; '.join(result.warnings),
                    'YES' if result.needs_review else 'NO',
                    alt_1_sku,
                    alt_1_score,
                    alt_2_sku,
                    alt_2_score
                ])

    def _write_json(self, results: List[MatchResult], path: Path):
        """Write results to JSON."""
        output = {
            'generated_at': datetime.now().isoformat(),
            'total_items': len(results),
            'high_confidence_count': sum(1 for r in results if r.confidence_score >= 0.85),
            'needs_review_count': sum(1 for r in results if r.needs_review),
            'results': []
        }

        for result in results:
            item_data = {
                'boq_row': result.boq_item.row_number,
                'boq_description': result.boq_item.raw_description,
                'is_ditto': result.boq_item.is_ditto,
                'match': {
                    'sku': result.product.sku,
                    'category': result.product.category,
                    'price': result.product.price,
                    'wattage': result.product.power_w,
                    'lumens': result.product.lumen,
                    'ip_rating': str(result.product.ip_rating) if result.product.ip_rating else None,
                    'form_factor': result.product.form_factor.value,
                },
                'confidence_score': result.confidence_score,
                'confidence_level': result.confidence_level,
                'justification': result.justification,
                'warnings': result.warnings,
                'needs_review': result.needs_review,
                'score_breakdown': {
                    'ip': {'score': result.score_breakdown.ip_score, 'reason': result.score_breakdown.ip_reason},
                    'form_factor': {'score': result.score_breakdown.form_factor_score, 'reason': result.score_breakdown.form_factor_reason},
                    'wattage': {'score': result.score_breakdown.wattage_score, 'reason': result.score_breakdown.wattage_reason},
                    'lumens': {'score': result.score_breakdown.lumen_score, 'reason': result.score_breakdown.lumen_reason},
                    'efficacy': {'score': result.score_breakdown.efficacy_bonus, 'reason': result.score_breakdown.efficacy_reason},
                    'features': {'score': result.score_breakdown.feature_score, 'reason': result.score_breakdown.feature_reason},
                },
                'alternatives': [
                    {
                        'sku': alt.product.sku,
                        'confidence_score': alt.confidence_score,
                        'justification': alt.justification
                    }
                    for alt in result.alternatives
                ]
            }
            output['results'].append(item_data)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    def _write_text(self, results: List[MatchResult], path: Path):
        """Write results as formatted text report."""
        report = self.justifier.format_batch_report(results)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)

    def get_statistics(self) -> Dict:
        """Get catalog and engine statistics."""
        catalog_stats = self.catalog.get_statistics()
        return {
            'catalog': catalog_stats,
            'scoring_weights': {
                'ip_rating': self.scorer.weights.ip_rating,
                'form_factor': self.scorer.weights.form_factor,
                'wattage': self.scorer.weights.wattage,
                'lumens': self.scorer.weights.lumens,
                'efficacy_bonus': self.scorer.weights.efficacy_bonus,
            }
        }


def create_engine(catalog_path: str = None) -> SubstitutionEngine:
    """
    Factory function to create a configured SubstitutionEngine.

    Args:
        catalog_path: Path to the catalog CSV. If None, uses default location.

    Returns:
        Configured SubstitutionEngine instance
    """
    if catalog_path is None:
        # Try default location
        default_path = Path(__file__).parent.parent / 'price_list_2025_parsed_searchable.csv'
        if default_path.exists():
            catalog_path = str(default_path)
        else:
            raise FileNotFoundError(
                "Catalog file not found. Please provide catalog_path."
            )

    engine = SubstitutionEngine(catalog_path)
    return engine
