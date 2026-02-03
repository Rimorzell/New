#!/usr/bin/env python3
"""
Demonstration of the Intelligent Product Substitution Engine.

This script showcases the engine's ability to:
1. Parse vague/technical descriptions
2. Apply environment-aware IP rating matching
3. Handle "DITTO" references with modifications
4. Generate human-readable justifications
5. Provide confidence scores and alternatives
"""

import sys
from pathlib import Path

# Add to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from substitution_engine import SubstitutionEngine


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_result(result, show_breakdown=False):
    """Print a formatted match result."""
    print(f"\n  Request: \"{result.boq_item.raw_description[:60]}...\"")
    print(f"  {'(DITTO from row ' + str(result.boq_item.ditto_source_row) + ')' if result.boq_item.is_ditto else ''}")

    print(f"\n  MATCHED: {result.product.sku}")
    print(f"  Category: {result.product.category}")
    print(f"  Price: {result.product.price:.2f}")

    # Specs line
    specs = []
    if result.product.power_w:
        specs.append(f"{result.product.power_w}W")
    if result.product.lumen:
        specs.append(f"{result.product.lumen:.0f}lm")
    if result.product.ip_rating:
        specs.append(str(result.product.ip_rating))
    if result.product.form_factor:
        specs.append(result.product.form_factor.value)
    if result.product.is_dali:
        specs.append("DALI")
    print(f"  Specs: {' | '.join(specs)}")

    # Confidence
    conf_bar = "#" * int(result.confidence_score * 20) + "-" * (20 - int(result.confidence_score * 20))
    print(f"\n  Confidence: [{conf_bar}] {result.confidence_score:.0%} ({result.confidence_level})")

    # Justification
    print(f"  Justification: {result.justification}")

    if show_breakdown:
        print(f"\n  Score Breakdown:")
        print(f"    IP Rating:   {result.score_breakdown.ip_score:5.1f} - {result.score_breakdown.ip_reason}")
        print(f"    Form Factor: {result.score_breakdown.form_factor_score:5.1f} - {result.score_breakdown.form_factor_reason}")
        print(f"    Wattage:     {result.score_breakdown.wattage_score:5.1f} - {result.score_breakdown.wattage_reason}")
        print(f"    Lumens:      {result.score_breakdown.lumen_score:5.1f} - {result.score_breakdown.lumen_reason}")
        print(f"    Efficacy:    {result.score_breakdown.efficacy_bonus:5.1f} - {result.score_breakdown.efficacy_reason}")

    # Warnings
    if result.warnings:
        print(f"\n  WARNINGS:")
        for warning in result.warnings:
            print(f"    ! {warning}")

    # Alternatives
    if result.alternatives:
        print(f"\n  Alternatives:")
        for i, alt in enumerate(result.alternatives[:2], 1):
            print(f"    {i}. {alt.product.sku} ({alt.confidence_score:.0%})")

    # Review flag
    if result.needs_review:
        print(f"\n  >>> FLAGGED FOR HUMAN REVIEW <<<")


def main():
    """Run the demonstration."""
    print_header("INTELLIGENT PRODUCT SUBSTITUTION ENGINE - DEMONSTRATION")

    # Initialize engine
    catalog_path = Path(__file__).parent / 'price_list_2025_parsed_searchable.csv'
    print(f"\nLoading catalog from: {catalog_path}")

    engine = SubstitutionEngine(str(catalog_path))
    print(f"Loaded {len(engine.catalog.products)} products")

    # Demo 1: Basic matching
    print_header("DEMO 1: Basic Product Matching")
    print("Query: '12W Round Downlight IP20 for office'")

    result = engine.find_match_for_description("12W Round Downlight IP20 for office")
    print_result(result, show_breakdown=True)

    # Demo 2: Environment-aware IP matching
    print_header("DEMO 2: Environment-Aware IP Rating")
    print("The engine prioritizes IP rating based on application context.")

    queries = [
        "15W Downlight for standard office",
        "15W Downlight for bathroom application",
        "15W Downlight for outdoor covered area",
    ]

    for query in queries:
        result = engine.find_match_for_description(query)
        print(f"\n  '{query}'")
        print(f"  -> {result.product.sku} ({result.product.ip_rating}) - {result.confidence_score:.0%}")

    # Demo 3: Linear/Batten matching
    print_header("DEMO 3: Linear/Batten Light Matching")
    print("Query: '38W Linear Batten for wet-room application'")

    result = engine.find_match_for_description("38W Linear Batten for wet-room application")
    print_result(result, show_breakdown=True)

    # Demo 4: Form factor semantic understanding
    print_header("DEMO 4: Semantic Form Factor Understanding")
    print("The engine understands that different terms map to the same shape.")

    form_queries = [
        "Round downlight",
        "Circular recessed light",
        "Disk ceiling light",
        "LED Batten",
        "Linear profile",
        "Strip light fixture",
    ]

    for query in form_queries:
        item = engine.boq_parser.parse_description(query)
        ff = item.requested_form_factor
        print(f"  '{query}' -> {ff.value if ff else 'unknown'}")

    # Demo 5: Feature matching (DALI, Emergency)
    print_header("DEMO 5: Feature Matching")

    print("\nQuery: '20W Panel with DALI dimming'")
    result = engine.find_match_for_description("20W Panel with DALI dimming")
    print(f"  -> {result.product.sku}")
    print(f"     DALI: {result.product.is_dali}")
    print(f"     {result.score_breakdown.feature_reason}")

    # Demo 6: High power industrial
    print_header("DEMO 6: Industrial High-Power Matching")
    print("Query: '100W High Bay for warehouse IP65'")

    result = engine.find_match_for_description("100W High Bay for warehouse IP65")
    print_result(result)

    # Demo 7: Process a BOQ file
    print_header("DEMO 7: Processing a BOQ File")

    boq_path = Path(__file__).parent / 'test_data' / 'sample_boq_1.csv'
    if boq_path.exists():
        print(f"Processing: {boq_path}")
        results = engine.process_boq_file(str(boq_path))

        print(f"\nResults Summary:")
        print(f"  Total items: {len(results)}")
        print(f"  High confidence (>85%): {sum(1 for r in results if r.confidence_score >= 0.85)}")
        print(f"  Medium confidence (70-85%): {sum(1 for r in results if 0.70 <= r.confidence_score < 0.85)}")
        print(f"  Low confidence (<70%): {sum(1 for r in results if r.confidence_score < 0.70)}")
        print(f"  DITTO rows processed: {sum(1 for r in results if r.boq_item.is_ditto)}")
        print(f"  Flagged for review: {sum(1 for r in results if r.needs_review)}")

        print(f"\nFirst 3 matches:")
        for result in results[:3]:
            print(f"\n  Row {result.boq_item.row_number}: {result.boq_item.raw_description[:40]}...")
            print(f"  -> {result.product.sku} ({result.confidence_score:.0%})")
    else:
        print(f"  BOQ file not found: {boq_path}")

    # Summary
    print_header("DEMONSTRATION COMPLETE")
    print("""
The Intelligent Product Substitution Engine provides:

1. NEVER FAILS: Always returns the best available match
2. IP PRIORITY: Environment safety is the top consideration
3. SEMANTIC UNDERSTANDING: Maps vague terms to catalog attributes
4. WEIGHTED SCORING: Balanced multi-factor evaluation
5. DITTO SUPPORT: Stateful processing for hierarchical BOQs
6. HUMAN JUSTIFICATION: Clear explanations for every match
7. CONFIDENCE SCORES: Flags items needing human review
8. ALTERNATIVES: Always provides backup options

For production use:
  python -m substitution_engine process your_boq.csv -o results.csv
  python -m substitution_engine query "your product description"
  python -m substitution_engine interactive
""")


if __name__ == '__main__':
    main()
