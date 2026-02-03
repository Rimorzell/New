#!/usr/bin/env python3
"""
Test suite for the Intelligent Product Substitution Engine.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from substitution_engine import (
    SubstitutionEngine, ProductCatalog, BOQParser, ScoringEngine,
    Product, BOQItem, MatchResult, EnvironmentContext
)
from substitution_engine.models import IPRating, FormFactor, ENVIRONMENT_IP_REQUIREMENTS
from substitution_engine.scoring import ScoringWeights


def test_ip_rating_parsing():
    """Test IP rating parsing."""
    print("Testing IP Rating Parsing...")

    # Valid IP ratings
    ip20 = IPRating.parse("IP20")
    assert ip20 is not None
    assert ip20.solid_protection == 2
    assert ip20.liquid_protection == 0

    ip65 = IPRating.parse("IP65")
    assert ip65 is not None
    assert ip65.solid_protection == 6
    assert ip65.liquid_protection == 5

    # Test meets_requirement
    assert ip65.meets_requirement(ip20)
    assert not ip20.meets_requirement(ip65)
    assert ip65.meets_requirement(ip65)

    print("  PASSED")


def test_catalog_loading():
    """Test catalog loading."""
    print("Testing Catalog Loading...")

    catalog_path = Path(__file__).parent.parent / 'price_list_2025_parsed_searchable.csv'
    if not catalog_path.exists():
        print(f"  SKIPPED (catalog not found at {catalog_path})")
        return

    catalog = ProductCatalog()
    count = catalog.load_from_csv(str(catalog_path))

    assert count > 0, "No products loaded"
    assert len(catalog.products) > 0

    # Check form factor distribution
    stats = catalog.get_statistics()
    assert 'form_factors' in stats
    assert stats['total_products'] > 100

    print(f"  PASSED ({count} products loaded)")


def test_boq_parser():
    """Test BOQ parser."""
    print("Testing BOQ Parser...")

    parser = BOQParser()

    # Test single description parsing
    item = parser.parse_description("38W Linear Batten for wet-room IP65")

    assert item is not None
    assert item.requested_wattage == 38
    assert item.requested_form_factor == FormFactor.LINEAR
    assert item.requested_ip is not None
    assert item.requested_ip.numeric_value == 65
    assert item.environment == EnvironmentContext.INDOOR_WET

    # Test emergency detection
    item2 = parser.parse_description("12W Downlight with emergency backup")
    assert item2.requires_emergency

    # Test DALI detection
    item3 = parser.parse_description("20W Panel DALI dimmable")
    assert item3.requires_dali
    assert item3.requires_dimming

    print("  PASSED")


def test_boq_ditto():
    """Test DITTO functionality."""
    print("Testing DITTO Parsing...")

    parser = BOQParser()

    # Simulate parsing two rows
    item1 = parser._parse_row(1, {'description': '38W Linear Batten IP65'})
    parser._previous_item = item1

    item2 = parser._parse_row(2, {'description': 'DITTO but with emergency'})

    assert item2.is_ditto
    assert item2.ditto_source_row == 1
    assert item2.requires_emergency
    assert item2.requested_wattage == 38  # Inherited from previous

    print("  PASSED")


def test_scoring_engine():
    """Test scoring engine."""
    print("Testing Scoring Engine...")

    scorer = ScoringEngine()

    # Create a BOQ item
    item = BOQItem(
        row_number=1,
        raw_description="20W Downlight IP44",
        requested_wattage=20,
        requested_ip=IPRating.parse("IP44"),
        requested_form_factor=FormFactor.ROUND,
        environment=EnvironmentContext.INDOOR_DAMP
    )

    # Create a matching product
    product = Product(
        row_id=1,
        category="LED DOWN LIGHT",
        product_type="downlight",
        sku="TEST-DL-20W-IP44",
        price=100.0,
        power_w=20,
        lumen=2000,
        ip_rating=IPRating.parse("IP44"),
        form_factor=FormFactor.ROUND
    )

    score, breakdown = scorer.score_match(item, product)

    assert score > 0.8, f"Expected high score, got {score}"
    assert breakdown.ip_score > 0
    assert breakdown.form_factor_score > 0
    assert breakdown.wattage_score > 0

    print(f"  PASSED (score: {score:.2f})")


def test_ip_priority():
    """Test that IP rating is prioritized correctly."""
    print("Testing IP Priority...")

    scorer = ScoringEngine()

    # Item requiring IP65
    item = BOQItem(
        row_number=1,
        raw_description="Outdoor light IP65",
        requested_ip=IPRating.parse("IP65"),
        environment=EnvironmentContext.OUTDOOR_EXPOSED
    )

    # Product with IP20 (insufficient)
    product_ip20 = Product(
        row_id=1,
        category="LED Light",
        product_type="downlight",
        sku="TEST-IP20",
        price=50.0,
        ip_rating=IPRating.parse("IP20"),
        form_factor=FormFactor.ROUND
    )

    # Product with IP65 (sufficient)
    product_ip65 = Product(
        row_id=2,
        category="LED Light",
        product_type="downlight",
        sku="TEST-IP65",
        price=80.0,
        ip_rating=IPRating.parse("IP65"),
        form_factor=FormFactor.ROUND
    )

    score_ip20, _ = scorer.score_match(item, product_ip20)
    score_ip65, _ = scorer.score_match(item, product_ip65)

    assert score_ip65 > score_ip20, "IP65 should score higher than IP20 for outdoor application"

    print(f"  PASSED (IP20: {score_ip20:.2f}, IP65: {score_ip65:.2f})")


def test_full_engine():
    """Test full engine workflow."""
    print("Testing Full Engine...")

    catalog_path = Path(__file__).parent.parent / 'price_list_2025_parsed_searchable.csv'
    if not catalog_path.exists():
        print(f"  SKIPPED (catalog not found)")
        return

    engine = SubstitutionEngine(str(catalog_path))

    # Test single query
    result = engine.find_match_for_description("20W Round Downlight IP44 for bathroom")

    assert result is not None
    assert result.product is not None
    assert result.confidence_score > 0
    assert result.justification

    print(f"  Matched: {result.product.sku}")
    print(f"  Confidence: {result.confidence_score:.0%}")
    print(f"  PASSED")


def test_boq_file_processing():
    """Test processing a BOQ file."""
    print("Testing BOQ File Processing...")

    catalog_path = Path(__file__).parent.parent / 'price_list_2025_parsed_searchable.csv'
    boq_path = Path(__file__).parent.parent / 'test_data' / 'sample_boq_1.csv'

    if not catalog_path.exists() or not boq_path.exists():
        print("  SKIPPED (files not found)")
        return

    engine = SubstitutionEngine(str(catalog_path))
    results = engine.process_boq_file(str(boq_path))

    assert len(results) > 0
    assert all(r.product is not None for r in results)
    assert all(r.confidence_score >= 0 for r in results)

    # Check ditto rows were processed
    ditto_results = [r for r in results if r.boq_item.is_ditto]

    print(f"  Processed {len(results)} items")
    print(f"  DITTO rows: {len(ditto_results)}")
    print(f"  High confidence: {sum(1 for r in results if r.confidence_score >= 0.85)}")
    print(f"  PASSED")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("RUNNING SUBSTITUTION ENGINE TESTS")
    print("=" * 60)
    print()

    tests = [
        test_ip_rating_parsing,
        test_catalog_loading,
        test_boq_parser,
        test_boq_ditto,
        test_scoring_engine,
        test_ip_priority,
        test_full_engine,
        test_boq_file_processing,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
