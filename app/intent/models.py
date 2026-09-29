from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class IntentSource(str, Enum):
    """Origin of the extracted intent constraint."""
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class ExtractedField(BaseModel):
    """Structured field representation with confidence and source tracking."""
    value: Any
    source: IntentSource = IntentSource.EXPLICIT
    raw_token: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "high"


class StructuredSearchIntent(BaseModel):
    """Comprehensive representation of structured intent extracted from natural-language search."""
    original_query: str = Field(..., description="Original user query text, preserved untouched")
    semantic_query: str = Field(default="", description="Refined query text retaining descriptive intent for dense/BM25 retrieval")

    # Hard-filter candidate fields
    category: Optional[ExtractedField] = None
    city: Optional[ExtractedField] = None
    neighborhood: Optional[ExtractedField] = None
    venue: Optional[ExtractedField] = None
    date: Optional[ExtractedField] = None           # ISO Date string: YYYY-MM-DD
    start_time: Optional[ExtractedField] = None     # Time string: HH:MM:SS
    end_time: Optional[ExtractedField] = None       # Time string: HH:MM:SS
    time_period: Optional[ExtractedField] = None    # "morning", "afternoon", "evening", "night"
    price_min: Optional[ExtractedField] = None
    price_max: Optional[ExtractedField] = None
    currency: Optional[str] = None
    is_indoor: Optional[ExtractedField] = None
    language: Optional[ExtractedField] = None       # e.g. "English", "Japanese", "Spanish"
    format: Optional[ExtractedField] = None         # e.g. "IMAX", "3D", "70mm", "35mm"
    status: Optional[ExtractedField] = None         # e.g. "available", "upcoming"

    # Geo radius constraint
    radius_km: Optional[ExtractedField] = None
    location_required: bool = False

    # Negative constraints
    excluded_categories: List[str] = Field(default_factory=list)
    excluded_subcategories: List[str] = Field(default_factory=list)

    # Conceptual & unstructured tokens
    themes: List[str] = Field(default_factory=list)
    unresolved_terms: List[str] = Field(default_factory=list)

    # Execution telemetry
    parse_latency_ms: float = 0.0

    def has_filters(self) -> bool:
        """Returns True if at least one structured constraint was recognized."""
        return any(
            [
                self.category is not None,
                self.city is not None,
                self.neighborhood is not None,
                self.venue is not None,
                self.date is not None,
                self.start_time is not None,
                self.time_period is not None,
                self.price_min is not None,
                self.price_max is not None,
                self.is_indoor is not None,
                self.language is not None,
                self.format is not None,
                self.status is not None,
                self.radius_km is not None,
                bool(self.excluded_categories),
                bool(self.excluded_subcategories),
            ]
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        """Provides a clean key-value summary of resolved structured values."""
        summary: Dict[str, Any] = {}
        for field_name in [
            "category", "city", "neighborhood", "venue", "date",
            "start_time", "end_time", "time_period", "price_min",
            "price_max", "is_indoor", "language", "format", "status",
            "radius_km",
        ]:
            field_obj: Optional[ExtractedField] = getattr(self, field_name, None)
            if field_obj is not None:
                summary[field_name] = field_obj.value

        if self.location_required:
            summary["location_required"] = True
        if self.excluded_categories:
            summary["excluded_categories"] = self.excluded_categories
        if self.excluded_subcategories:
            summary["excluded_subcategories"] = self.excluded_subcategories
        if self.themes:
            summary["themes"] = self.themes
        if self.unresolved_terms:
            summary["unresolved_terms"] = self.unresolved_terms

        return summary
