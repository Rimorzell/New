"""
Core data models for the Product Substitution Engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import re


class EnvironmentContext(Enum):
    """Environment contexts that drive IP rating requirements."""
    INDOOR_DRY = "indoor_dry"           # IP20 acceptable
    INDOOR_DAMP = "indoor_damp"         # IP44+ required (bathrooms, kitchens)
    INDOOR_WET = "indoor_wet"           # IP65+ required (shower areas)
    OUTDOOR_COVERED = "outdoor_covered"  # IP44+ required
    OUTDOOR_EXPOSED = "outdoor_exposed"  # IP65+ required
    INDUSTRIAL = "industrial"           # IP65+ required
    HAZARDOUS = "hazardous"             # IP66+ required
    SUBMERSIBLE = "submersible"         # IP67/IP68 required


class FormFactor(Enum):
    """Canonical form factors for lighting products."""
    ROUND = "round"           # Downlights, circular panels, globes
    LINEAR = "linear"         # Battens, strips, profiles, tubes
    SQUARE = "square"         # Square panels
    RECTANGULAR = "rectangular"  # Rectangular panels, 60x120
    TRACK = "track"           # Track lights
    FLOOD = "flood"           # Flood lights
    STREET = "street"         # Street lights
    HIGH_BAY = "high_bay"     # High bay lights
    SPOT = "spot"             # Spot lights
    WALL = "wall"             # Wall lights
    CYLINDER = "cylinder"     # Cylindrical lights
    ADJUSTABLE = "adjustable" # Adjustable/gimbal lights
    DECORATIVE = "decorative" # Decorative lights
    EXIT = "exit"             # Exit/emergency signs
    UNKNOWN = "unknown"


@dataclass
class IPRating:
    """IP (Ingress Protection) rating representation."""
    solid_protection: int  # First digit (0-6)
    liquid_protection: int  # Second digit (0-9)
    raw: str

    @classmethod
    def parse(cls, ip_string: str) -> Optional['IPRating']:
        """Parse IP rating string like 'IP20', 'IP65', etc."""
        if not ip_string:
            return None

        match = re.search(r'IP(\d)(\d)', str(ip_string).upper())
        if match:
            return cls(
                solid_protection=int(match.group(1)),
                liquid_protection=int(match.group(2)),
                raw=ip_string
            )
        return None

    @property
    def numeric_value(self) -> int:
        """Combined numeric value for comparison."""
        return self.solid_protection * 10 + self.liquid_protection

    def meets_requirement(self, required: 'IPRating') -> bool:
        """Check if this rating meets or exceeds the requirement."""
        return (self.solid_protection >= required.solid_protection and
                self.liquid_protection >= required.liquid_protection)

    def __str__(self) -> str:
        return f"IP{self.solid_protection}{self.liquid_protection}"


@dataclass
class Product:
    """Represents a product from the catalog."""
    row_id: int
    category: str
    product_type: str
    sku: str
    price: float

    # Technical specs
    power_w: Optional[float] = None
    power_w_per_m: Optional[float] = None
    lumen: Optional[float] = None
    ip_rating: Optional[IPRating] = None

    # Dimensions
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    diameter_mm: Optional[float] = None

    # Features
    dimming: Optional[str] = None
    cct_k: Optional[float] = None
    beam_deg: Optional[float] = None

    # Derived/inferred attributes
    form_factor: FormFactor = FormFactor.UNKNOWN
    is_emergency: bool = False
    is_dali: bool = False

    # Search text for semantic matching
    search_text: str = ""

    # Raw data for reference
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def efficacy(self) -> Optional[float]:
        """Lumens per watt - efficiency metric."""
        if self.lumen and self.power_w and self.power_w > 0:
            return self.lumen / self.power_w
        return None

    @property
    def display_name(self) -> str:
        """Human-readable product name."""
        parts = [self.category]
        if self.power_w:
            parts.append(f"{self.power_w}W")
        if self.ip_rating:
            parts.append(str(self.ip_rating))
        return " | ".join(parts)


@dataclass
class BOQItem:
    """Represents a single line item from a Bill of Quantities."""
    row_number: int
    raw_description: str
    quantity: int = 1

    # Extracted specifications
    requested_wattage: Optional[float] = None
    requested_lumens: Optional[float] = None
    requested_ip: Optional[IPRating] = None
    requested_form_factor: Optional[FormFactor] = None
    requested_cct_k: Optional[float] = None
    requested_length_mm: Optional[float] = None
    requested_beam_deg: Optional[float] = None

    # Inferred context
    environment: EnvironmentContext = EnvironmentContext.INDOOR_DRY

    # Features
    requires_emergency: bool = False
    requires_dali: bool = False
    requires_dimming: bool = False

    # Reference to previous row (for DITTO support)
    is_ditto: bool = False
    ditto_source_row: Optional[int] = None
    ditto_modifications: Dict[str, Any] = field(default_factory=dict)

    # Original parsed fields for reference
    parsed_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of how a match score was calculated."""
    ip_score: float = 0.0
    ip_reason: str = ""

    form_factor_score: float = 0.0
    form_factor_reason: str = ""

    wattage_score: float = 0.0
    wattage_reason: str = ""

    lumen_score: float = 0.0
    lumen_reason: str = ""

    efficacy_bonus: float = 0.0
    efficacy_reason: str = ""

    feature_score: float = 0.0
    feature_reason: str = ""

    cct_score: float = 0.0
    cct_reason: str = ""

    length_score: float = 0.0
    length_reason: str = ""

    beam_score: float = 0.0
    beam_reason: str = ""

    text_relevance_score: float = 0.0
    text_relevance_reason: str = ""

    @property
    def total_weighted_score(self) -> float:
        """Sum of all weighted scores."""
        return (self.ip_score + self.form_factor_score +
                self.wattage_score + self.lumen_score +
                self.efficacy_bonus + self.feature_score +
                self.cct_score + self.length_score +
                self.beam_score + self.text_relevance_score)


@dataclass
class MatchResult:
    """Result of matching a BOQ item to a catalog product."""
    boq_item: BOQItem
    product: Product

    # Scoring
    confidence_score: float  # 0.0 to 1.0
    score_breakdown: ScoreBreakdown

    # Human-readable justification
    justification: str = ""
    warnings: List[str] = field(default_factory=list)

    # Alternative matches for review
    alternatives: List['MatchResult'] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """Flag items with low confidence for human review."""
        return self.confidence_score < 0.7 or len(self.warnings) > 0

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence_score >= 0.9:
            return "HIGH"
        elif self.confidence_score >= 0.7:
            return "MEDIUM"
        elif self.confidence_score >= 0.5:
            return "LOW"
        else:
            return "VERY LOW"


# Environment keyword mappings for context detection
ENVIRONMENT_KEYWORDS = {
    EnvironmentContext.INDOOR_WET: [
        'wet', 'shower', 'steam', 'sauna', 'pool', 'spa', 'wet room',
        'wet-room', 'wetroom', 'water spray'
    ],
    EnvironmentContext.INDOOR_DAMP: [
        'bathroom', 'toilet', 'wc', 'washroom', 'kitchen', 'laundry',
        'damp', 'humid', 'moisture', 'utility'
    ],
    EnvironmentContext.OUTDOOR_EXPOSED: [
        'outdoor', 'exterior', 'external', 'outside', 'garden',
        'parking', 'car park', 'carpark', 'street', 'pathway',
        'landscape', 'facade', 'weatherproof', 'all-weather'
    ],
    EnvironmentContext.OUTDOOR_COVERED: [
        'canopy', 'covered', 'porch', 'awning', 'shelter', 'carport',
        'veranda', 'balcony', 'terrace'
    ],
    EnvironmentContext.INDUSTRIAL: [
        'industrial', 'factory', 'warehouse', 'workshop', 'plant',
        'manufacturing', 'production', 'clean room', 'cleanroom'
    ],
    EnvironmentContext.HAZARDOUS: [
        'hazardous', 'explosive', 'flammable', 'chemical', 'atex',
        'zone 1', 'zone 2', 'petrol', 'gas station'
    ],
    EnvironmentContext.SUBMERSIBLE: [
        'underwater', 'submersible', 'submerged', 'fountain', 'pond',
        'aquarium', 'swimming pool light'
    ]
}

# IP rating requirements by environment
ENVIRONMENT_IP_REQUIREMENTS = {
    EnvironmentContext.INDOOR_DRY: IPRating(2, 0, "IP20"),
    EnvironmentContext.INDOOR_DAMP: IPRating(4, 4, "IP44"),
    EnvironmentContext.INDOOR_WET: IPRating(6, 5, "IP65"),
    EnvironmentContext.OUTDOOR_COVERED: IPRating(4, 4, "IP44"),
    EnvironmentContext.OUTDOOR_EXPOSED: IPRating(6, 5, "IP65"),
    EnvironmentContext.INDUSTRIAL: IPRating(6, 5, "IP65"),
    EnvironmentContext.HAZARDOUS: IPRating(6, 6, "IP66"),
    EnvironmentContext.SUBMERSIBLE: IPRating(6, 8, "IP68"),
}

# Form factor keyword mappings
FORM_FACTOR_KEYWORDS = {
    FormFactor.ROUND: [
        'round', 'circular', 'circle', 'globe', 'disk', 'disc',
        'downlight', 'down light', 'recessed', 'spot'
    ],
    FormFactor.LINEAR: [
        'linear', 'batten', 'strip', 'profile', 'tube', 'line',
        'trunking', 'continuous', 'pendant linear', 'suspended linear',
        'led bar', 'light bar'
    ],
    FormFactor.SQUARE: [
        'square', 'panel 6060', '600x600', '60x60', '595x595',
        'square panel'
    ],
    FormFactor.RECTANGULAR: [
        'rectangular', 'panel 60120', '600x1200', '60x120', '1200x600',
        'rectangle', '30x120', '300x1200'
    ],
    FormFactor.TRACK: [
        'track', 'rail', 'magnetic track'
    ],
    FormFactor.FLOOD: [
        'flood', 'floodlight', 'flood light', 'area light'
    ],
    FormFactor.STREET: [
        'street', 'road', 'highway', 'pathway light', 'street light'
    ],
    FormFactor.HIGH_BAY: [
        'high bay', 'highbay', 'high-bay', 'warehouse light', 'industrial bay'
    ],
    FormFactor.SPOT: [
        'spot', 'spotlight', 'spot light', 'mr16', 'gu10', 'accent'
    ],
    FormFactor.WALL: [
        'wall', 'sconce', 'wall light', 'wall mount', 'wall-mounted',
        'bulkhead', 'uplight', 'up-light'
    ],
    FormFactor.CYLINDER: [
        'cylinder', 'cylindrical', 'pendant cylinder', 'surface cylinder'
    ],
    FormFactor.ADJUSTABLE: [
        'adjustable', 'gimbal', 'tilt', 'rotatable', 'directional'
    ],
    FormFactor.EXIT: [
        'exit', 'emergency exit', 'exit sign', 'evacuation'
    ],
}
