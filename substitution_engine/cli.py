#!/usr/bin/env python3
"""
Command-Line Interface for the Intelligent Product Substitution Engine.
"""

import argparse
import sys
from pathlib import Path

from .engine import SubstitutionEngine, create_engine
from .scoring import ScoringWeights


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Intelligent Product Substitution Engine for Lighting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a BOQ file
  python -m substitution_engine process boq.csv -o results.csv

  # Query a single description
  python -m substitution_engine query "38W Linear Batten for wet-room IP65"

  # Show catalog statistics
  python -m substitution_engine stats
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process a BOQ file')
    process_parser.add_argument('boq_file', help='Path to BOQ file (CSV or Excel)')
    process_parser.add_argument('-o', '--output', help='Output file path (csv, json, or txt)')
    process_parser.add_argument('-c', '--catalog', help='Path to catalog CSV file')
    process_parser.add_argument('--alternatives', type=int, default=3,
                               help='Number of alternative matches to show')

    # Query command
    query_parser = subparsers.add_parser('query', help='Query a single product description')
    query_parser.add_argument('description', help='Product description to match')
    query_parser.add_argument('-c', '--catalog', help='Path to catalog CSV file')
    query_parser.add_argument('--alternatives', type=int, default=3,
                             help='Number of alternative matches to show')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show catalog statistics')
    stats_parser.add_argument('-c', '--catalog', help='Path to catalog CSV file')

    # Interactive command
    interactive_parser = subparsers.add_parser('interactive',
                                               help='Start interactive query mode')
    interactive_parser.add_argument('-c', '--catalog', help='Path to catalog CSV file')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == 'process':
            run_process(args)
        elif args.command == 'query':
            run_query(args)
        elif args.command == 'stats':
            run_stats(args)
        elif args.command == 'interactive':
            run_interactive(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_process(args):
    """Process a BOQ file."""
    engine = create_engine(args.catalog)

    print(f"Loading catalog... {len(engine.catalog.products)} products loaded")
    print(f"Processing BOQ file: {args.boq_file}")

    results = engine.process_boq_file(
        args.boq_file,
        output_path=args.output
    )

    # Print summary
    print("\n" + "=" * 60)
    print("PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Total items processed: {len(results)}")
    print(f"High confidence matches (>85%): {sum(1 for r in results if r.confidence_score >= 0.85)}")
    print(f"Medium confidence (70-85%): {sum(1 for r in results if 0.70 <= r.confidence_score < 0.85)}")
    print(f"Low confidence (<70%): {sum(1 for r in results if r.confidence_score < 0.70)}")
    print(f"Flagged for review: {sum(1 for r in results if r.needs_review)}")

    if args.output:
        print(f"\nResults written to: {args.output}")
    else:
        # Print results to console
        print("\n" + "-" * 60)
        for result in results:
            print(f"\nRow {result.boq_item.row_number}: {result.boq_item.raw_description[:50]}...")
            print(f"  -> {result.product.sku}")
            print(f"     Confidence: {result.confidence_score:.0%} ({result.confidence_level})")
            print(f"     {result.justification}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"     WARNING: {warning}")


def run_query(args):
    """Query a single description."""
    engine = create_engine(args.catalog)

    print(f"Catalog loaded: {len(engine.catalog.products)} products")
    print(f"\nSearching for: {args.description}")
    print("-" * 60)

    result = engine.find_match_for_description(
        args.description,
        num_alternatives=args.alternatives
    )

    # Print main match
    print(f"\nBEST MATCH:")
    print(f"  SKU: {result.product.sku}")
    print(f"  Category: {result.product.category}")
    print(f"  Price: {result.product.price:.2f}")

    specs = []
    if result.product.power_w:
        specs.append(f"{result.product.power_w}W")
    if result.product.lumen:
        specs.append(f"{result.product.lumen:.0f}lm")
    if result.product.ip_rating:
        specs.append(str(result.product.ip_rating))
    if result.product.form_factor:
        specs.append(result.product.form_factor.value)
    print(f"  Specs: {' | '.join(specs)}")

    print(f"\n  Confidence: {result.confidence_score:.0%} ({result.confidence_level})")
    print(f"  Justification: {result.justification}")

    # Score breakdown
    print(f"\n  Score Breakdown:")
    print(f"    IP Rating: {result.score_breakdown.ip_score:.1f} - {result.score_breakdown.ip_reason}")
    print(f"    Form Factor: {result.score_breakdown.form_factor_score:.1f} - {result.score_breakdown.form_factor_reason}")
    print(f"    Wattage: {result.score_breakdown.wattage_score:.1f} - {result.score_breakdown.wattage_reason}")
    print(f"    Lumens: {result.score_breakdown.lumen_score:.1f} - {result.score_breakdown.lumen_reason}")
    print(f"    Efficacy: {result.score_breakdown.efficacy_bonus:.1f} - {result.score_breakdown.efficacy_reason}")

    if result.warnings:
        print(f"\n  WARNINGS:")
        for warning in result.warnings:
            print(f"    - {warning}")

    # Alternatives
    if result.alternatives:
        print(f"\nALTERNATIVES:")
        for i, alt in enumerate(result.alternatives, 1):
            print(f"  {i}. {alt.product.sku} - {alt.confidence_score:.0%}")
            print(f"     {alt.justification}")


def run_stats(args):
    """Show catalog statistics."""
    engine = create_engine(args.catalog)

    stats = engine.get_statistics()

    print("=" * 60)
    print("CATALOG STATISTICS")
    print("=" * 60)

    print(f"\nTotal Products: {stats['catalog']['total_products']}")

    print(f"\nForm Factor Distribution:")
    for ff, count in sorted(stats['catalog']['form_factors'].items(),
                           key=lambda x: x[1], reverse=True):
        print(f"  {ff}: {count}")

    print(f"\nIP Rating Distribution:")
    for ip, count in sorted(stats['catalog']['ip_ratings'].items(),
                           key=lambda x: x[1], reverse=True):
        print(f"  {ip}: {count}")

    print(f"\nWattage Distribution:")
    for watt, count in sorted(stats['catalog']['wattage_distribution'].items()):
        print(f"  {watt}: {count}")

    print(f"\nScoring Weights:")
    for name, weight in stats['scoring_weights'].items():
        print(f"  {name}: {weight}")


def run_interactive(args):
    """Run interactive query mode."""
    engine = create_engine(args.catalog)

    print("=" * 60)
    print("INTERACTIVE PRODUCT SUBSTITUTION ENGINE")
    print("=" * 60)
    print(f"Catalog loaded: {len(engine.catalog.products)} products")
    print("Enter product descriptions to find matches.")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            description = input("Enter description: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if description.lower() in ('quit', 'exit', 'q'):
            print("Goodbye!")
            break

        if not description:
            continue

        result = engine.find_match_for_description(description)

        print(f"\n  Match: {result.product.sku}")
        print(f"  Confidence: {result.confidence_score:.0%}")
        print(f"  {result.justification}")

        if result.alternatives:
            print(f"  Alternatives: {', '.join(a.product.sku for a in result.alternatives[:2])}")

        print()


if __name__ == '__main__':
    main()
