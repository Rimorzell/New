"""
Product Catalog loader and indexer.
"""

import csv
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import defaultdict

from .models import (
    Product, IPRating, FormFactor, FORM_FACTOR_KEYWORDS
)


class ProductCatalog:
    """
    Loads and indexes the product catalog for efficient searching.
    """

    def __init__(self):
        self.products: List[Product] = []
        self._by_form_factor: Dict[FormFactor, List[Product]] = defaultdict(list)
        self._by_ip_rating: Dict[str, List[Product]] = defaultdict(list)
        self._by_product_type: Dict[str, List[Product]] = defaultdict(list)
        self._by_wattage_range: Dict[str, List[Product]] = defaultdict(list)

    def load_from_csv(self, filepath: str) -> int:
        """
        Load products from CSV file.
        Returns the number of products loaded.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Catalog file not found: {filepath}")

        products_loaded = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                product = self._parse_product_row(row)
                if product and not row.get('is_pricing_rule', '').lower() == 'true':
                    # Skip pricing rules, only load actual products
                    if product.sku and not product.sku.startswith(('CUSTOM', 'READY', 'IP40', 'IP65')):
                        self.products.append(product)
                        products_loaded += 1

        # Build indexes
        self._build_indexes()

        return products_loaded

    def _parse_product_row(self, row: Dict) -> Optional[Product]:
        """Parse a CSV row into a Product object."""
        try:
            # Parse basic fields
            row_id = int(row.get('row_id', 0))
            category = row.get('category', '').strip()
            product_type = row.get('product_type', '').strip()
            sku = row.get('sku', '').strip()

            # Parse price
            price_str = row.get('price', '0')
            try:
                price = float(price_str) if price_str else 0.0
            except ValueError:
                price = 0.0

            # Parse power
            power_w = self._safe_float(row.get('power_w'))
            power_w_per_m = self._safe_float(row.get('power_w_per_m'))

            # Parse lumens
            lumen = self._safe_float(row.get('lumen'))

            # Parse IP rating
            ip_str = row.get('ip_rating', '')
            ip_rating = IPRating.parse(ip_str) if ip_str else None

            # Parse dimensions
            length_mm = self._safe_float(row.get('length_mm'))
            width_mm = self._safe_float(row.get('width_mm'))
            height_mm = self._safe_float(row.get('height_mm'))
            diameter_mm = self._safe_float(row.get('diameter_mm'))

            # Parse features
            dimming = row.get('dimming', '').strip()
            cct_k = self._safe_float(row.get('cct_k'))
            beam_deg = self._safe_float(row.get('beam_deg'))

            # Get search text
            search_text = row.get('search_text', '')

            # Detect features from SKU and description
            sku_upper = sku.upper()
            is_dali = 'DALI' in sku_upper or 'DALI' in dimming.upper()
            is_emergency = 'EM' in sku_upper or 'EMERGENCY' in search_text.upper()

            # Infer form factor
            form_factor = self._infer_form_factor(category, product_type, sku, search_text)

            product = Product(
                row_id=row_id,
                category=category,
                product_type=product_type,
                sku=sku,
                price=price,
                power_w=power_w,
                power_w_per_m=power_w_per_m,
                lumen=lumen,
                ip_rating=ip_rating,
                length_mm=length_mm,
                width_mm=width_mm,
                height_mm=height_mm,
                diameter_mm=diameter_mm,
                dimming=dimming,
                cct_k=cct_k,
                beam_deg=beam_deg,
                form_factor=form_factor,
                is_emergency=is_emergency,
                is_dali=is_dali,
                search_text=search_text,
                raw_data=dict(row)
            )

            return product

        except Exception as e:
            # Log error but continue processing
            print(f"Error parsing row: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _infer_form_factor(self, category: str, product_type: str,
                           sku: str, search_text: str) -> FormFactor:
        """Infer the form factor from product attributes."""
        # Combine all text for matching
        combined = f"{category} {product_type} {sku} {search_text}".lower()

        # Check product_type first (most reliable)
        type_mappings = {
            'downlight': FormFactor.ROUND,
            'led_linear': FormFactor.LINEAR,
            'linear_light': FormFactor.LINEAR,
            'panel_light': FormFactor.SQUARE,  # Default, may be rectangular
            'street_light': FormFactor.STREET,
            'flood_light': FormFactor.FLOOD,
            'high_bay': FormFactor.HIGH_BAY,
            'track_light': FormFactor.TRACK,
            'led_spot': FormFactor.SPOT,
            'led_wall': FormFactor.WALL,
            'led_cylinder': FormFactor.CYLINDER,
            'exit_light': FormFactor.EXIT,
            'led_tube': FormFactor.LINEAR,
            'spike_light': FormFactor.SPOT,
            'canopy_light': FormFactor.FLOOD,
            'strip_light': FormFactor.LINEAR,
        }

        if product_type.lower() in type_mappings:
            ff = type_mappings[product_type.lower()]
            # Check for rectangular panels
            if ff == FormFactor.SQUARE and ('60120' in combined or '1200' in combined):
                return FormFactor.RECTANGULAR
            return ff

        # Check category keywords
        category_lower = category.lower()
        if 'linear' in category_lower or 'batten' in category_lower or 'tube' in category_lower:
            return FormFactor.LINEAR
        if 'down' in category_lower or 'downlight' in category_lower:
            return FormFactor.ROUND
        if 'panel' in category_lower:
            if '60120' in combined or '1200' in combined:
                return FormFactor.RECTANGULAR
            return FormFactor.SQUARE
        if 'street' in category_lower:
            return FormFactor.STREET
        if 'flood' in category_lower:
            return FormFactor.FLOOD
        if 'track' in category_lower:
            return FormFactor.TRACK
        if 'spot' in category_lower:
            return FormFactor.SPOT
        if 'high bay' in category_lower or 'highbay' in category_lower:
            return FormFactor.HIGH_BAY

        # Fallback to keyword matching
        for form_factor, keywords in FORM_FACTOR_KEYWORDS.items():
            for keyword in keywords:
                if keyword in combined:
                    return form_factor

        return FormFactor.UNKNOWN

    def _build_indexes(self):
        """Build lookup indexes for efficient searching."""
        self._by_form_factor.clear()
        self._by_ip_rating.clear()
        self._by_product_type.clear()
        self._by_wattage_range.clear()

        for product in self.products:
            # Index by form factor
            self._by_form_factor[product.form_factor].append(product)

            # Index by IP rating
            if product.ip_rating:
                self._by_ip_rating[str(product.ip_rating)].append(product)

            # Index by product type
            if product.product_type:
                self._by_product_type[product.product_type.lower()].append(product)

            # Index by wattage range (10W buckets)
            if product.power_w:
                bucket = f"{int(product.power_w // 10) * 10}-{int(product.power_w // 10) * 10 + 10}W"
                self._by_wattage_range[bucket].append(product)

    def get_by_form_factor(self, form_factor: FormFactor) -> List[Product]:
        """Get all products with a specific form factor."""
        return self._by_form_factor.get(form_factor, [])

    def get_by_ip_rating(self, ip_rating: str) -> List[Product]:
        """Get all products with a specific IP rating."""
        return self._by_ip_rating.get(ip_rating, [])

    def get_products_meeting_ip(self, min_ip: IPRating) -> List[Product]:
        """Get all products that meet or exceed the IP requirement."""
        matching = []
        for product in self.products:
            if product.ip_rating and product.ip_rating.meets_requirement(min_ip):
                matching.append(product)
        return matching

    def get_candidates(self, form_factor: Optional[FormFactor] = None,
                       min_ip: Optional[IPRating] = None,
                       wattage_range: Optional[tuple] = None) -> List[Product]:
        """
        Get candidate products matching the given criteria.
        Uses soft matching - returns all products but prioritizes matches.
        """
        candidates = set()

        if form_factor and form_factor != FormFactor.UNKNOWN:
            # Start with form factor matches
            candidates.update(self._by_form_factor.get(form_factor, []))

        if not candidates:
            # If no form factor match, use all products
            candidates = set(self.products)

        return list(candidates)

    def search_text(self, query: str, limit: int = 50) -> List[Product]:
        """
        Simple text search across product search_text field.
        """
        query_lower = query.lower()
        query_terms = query_lower.split()

        scored_products = []

        for product in self.products:
            search_text = product.search_text.lower()
            category = product.category.lower()
            sku = product.sku.lower()

            score = 0
            for term in query_terms:
                if term in search_text:
                    score += 2
                if term in category:
                    score += 3
                if term in sku:
                    score += 1

            if score > 0:
                scored_products.append((score, product))

        # Sort by score descending
        scored_products.sort(key=lambda x: x[0], reverse=True)

        return [p for _, p in scored_products[:limit]]

    def get_statistics(self) -> Dict:
        """Get catalog statistics."""
        form_factors = defaultdict(int)
        ip_ratings = defaultdict(int)
        wattage_ranges = defaultdict(int)

        for product in self.products:
            form_factors[product.form_factor.value] += 1

            if product.ip_rating:
                ip_ratings[str(product.ip_rating)] += 1

            if product.power_w:
                if product.power_w <= 10:
                    wattage_ranges['0-10W'] += 1
                elif product.power_w <= 20:
                    wattage_ranges['11-20W'] += 1
                elif product.power_w <= 40:
                    wattage_ranges['21-40W'] += 1
                elif product.power_w <= 60:
                    wattage_ranges['41-60W'] += 1
                else:
                    wattage_ranges['60W+'] += 1

        return {
            'total_products': len(self.products),
            'form_factors': dict(form_factors),
            'ip_ratings': dict(ip_ratings),
            'wattage_distribution': dict(wattage_ranges)
        }
