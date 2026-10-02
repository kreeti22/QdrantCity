import datetime
import logging
from typing import Any, Dict, List, Optional, Union

from qdrant_edge import (
    FieldCondition,
    Filter,
    MatchValue,
    RangeDateTime,
    RangeFloat,
)
from app.intent.models import ExtractedField, IntentSource, StructuredSearchIntent
from app.models.experience import SearchFilterParams
from app.utils.clock import TimeProvider, get_clock

logger = logging.getLogger("qdrant_edge.retrieval.filter_builder")


class FilterBuilder:
    """Constructs validated, safe Qdrant Edge Filters from structured search intent or filter parameters."""

    def __init__(self, clock: Optional[TimeProvider] = None):
        self.clock = clock or get_clock()

    def build_from_params(self, params: Optional[SearchFilterParams]) -> Optional[Filter]:
        """Translates basic SearchFilterParams into a Qdrant Edge Filter."""
        if not params:
            return None

        must_conditions: List[FieldCondition] = []
        must_not_conditions: List[FieldCondition] = []

        if params.category and params.category.strip():
            cat_value = params.category.strip().lower()
            logger.debug(f"Building category filter: '{cat_value}' (original: '{params.category}')")
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(cat_value))
            )

        if params.city and params.city.strip():
            must_conditions.append(
                FieldCondition(key="city", match=MatchValue(params.city.strip()))
            )

        if params.is_indoor is not None:
            must_conditions.append(
                FieldCondition(
                    key="is_indoor",
                    match=MatchValue(1 if params.is_indoor else 0),
                )
            )

        if params.min_price is not None or params.max_price is not None:
            must_conditions.append(
                FieldCondition(
                    key="price",
                    range=RangeFloat(gte=params.min_price, lte=params.max_price),
                )
            )

        # Extended fields if present in params
        if hasattr(params, "neighborhood") and params.neighborhood and params.neighborhood.strip():
            must_conditions.append(
                FieldCondition(key="neighborhood", match=MatchValue(params.neighborhood.strip()))
            )

        if hasattr(params, "venue") and params.venue and params.venue.strip():
            must_conditions.append(
                FieldCondition(key="venue", match=MatchValue(params.venue.strip()))
            )

        if hasattr(params, "format") and params.format and params.format.strip():
            must_conditions.append(
                FieldCondition(key="subcategories", match=MatchValue(params.format.strip().lower()))
            )

        if hasattr(params, "language") and params.language and params.language.strip():
            must_conditions.append(
                FieldCondition(key="subcategories", match=MatchValue(params.language.strip().lower()))
            )

        if hasattr(params, "start_date") and hasattr(params, "end_date"):
            if params.start_date and params.end_date:
                must_conditions.append(
                    FieldCondition(
                        key="start_time",
                        range=RangeDateTime(gte=params.start_date, lte=params.end_date),
                    )
                )

        if hasattr(params, "excluded_categories") and params.excluded_categories:
            for ex in params.excluded_categories:
                if ex and ex.strip():
                    must_not_conditions.append(
                        FieldCondition(key="category", match=MatchValue(ex.strip().lower()))
                    )

        if hasattr(params, "excluded_subcategories") and params.excluded_subcategories:
            for ex in params.excluded_subcategories:
                if ex and ex.strip():
                    must_not_conditions.append(
                        FieldCondition(key="subcategories", match=MatchValue(ex.strip().lower()))
                    )

        if not must_conditions and not must_not_conditions:
            return None

        return Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
        )

    def build_from_intent(
        self,
        intent: Optional[StructuredSearchIntent],
        override_filters: Optional[SearchFilterParams] = None,
        override_params: Optional[SearchFilterParams] = None,
    ) -> Optional[Filter]:
        """Translates structured search intent into a safe, validated Qdrant Edge Filter."""
        overrides = override_filters or override_params

        must_conditions: List[FieldCondition] = []
        must_not_conditions: List[FieldCondition] = []

        # 1. Category (override takes precedence)
        cat_val = None
        if overrides and overrides.category and overrides.category.strip():
            cat_val = overrides.category.strip().lower()
        elif intent and intent.category and intent.category.confidence != "low":
            val = str(intent.category.value).strip().lower()
            if val:
                cat_val = val
        if cat_val:
            logger.debug(f"Building category filter from intent: '{cat_val}'")
            must_conditions.append(FieldCondition(key="category", match=MatchValue(cat_val)))

        # 2. City (override takes precedence)
        city_val = None
        if overrides and overrides.city and overrides.city.strip():
            city_val = overrides.city.strip()
        elif intent and intent.city and intent.city.confidence != "low":
            val = str(intent.city.value).strip()
            if val:
                city_val = val
        if city_val:
            must_conditions.append(FieldCondition(key="city", match=MatchValue(city_val)))

        # 3. Neighborhood
        if intent and intent.neighborhood and intent.neighborhood.confidence != "low":
            val = str(intent.neighborhood.value).strip()
            if val:
                must_conditions.append(FieldCondition(key="neighborhood", match=MatchValue(val)))

        # 4. Venue
        if intent and intent.venue and intent.venue.confidence != "low":
            val = str(intent.venue.value).strip()
            if val:
                must_conditions.append(FieldCondition(key="venue", match=MatchValue(val)))

        # 5. Price range (override takes precedence)
        p_min = None
        p_max = None
        if overrides and (overrides.min_price is not None or overrides.max_price is not None):
            p_min = overrides.min_price
            p_max = overrides.max_price
        elif intent:
            if intent.price_min and intent.price_min.confidence != "low":
                p_min = intent.price_min.value
            if intent.price_max and intent.price_max.confidence != "low":
                p_max = intent.price_max.value

        if p_min is not None or p_max is not None:
            must_conditions.append(
                FieldCondition(
                    key="price",
                    range=RangeFloat(
                        gte=float(p_min) if p_min is not None else None,
                        lte=float(p_max) if p_max is not None else None,
                    ),
                )
            )

        # 6. Indoor / Outdoor (override takes precedence)
        indoor_val = None
        if overrides and overrides.is_indoor is not None:
            indoor_val = overrides.is_indoor
        elif intent and intent.is_indoor and intent.is_indoor.confidence != "low":
            indoor_val = intent.is_indoor.value
        if indoor_val is not None:
            must_conditions.append(
                FieldCondition(
                    key="is_indoor",
                    match=MatchValue(1 if indoor_val else 0),
                )
            )

        # 7. Presentation format (e.g. IMAX, 3D, 70mm in subcategories)
        if intent and intent.format and intent.format.confidence != "low":
            fmt_val = str(intent.format.value).strip().lower()
            if fmt_val:
                must_conditions.append(FieldCondition(key="subcategories", match=MatchValue(fmt_val)))

        # 8. Language (e.g. English, Spanish in subcategories/payload)
        if intent and intent.language and intent.language.confidence != "low":
            lang_val = str(intent.language.value).strip().lower()
            if lang_val:
                must_conditions.append(FieldCondition(key="subcategories", match=MatchValue(lang_val)))

        # 9. Date and Time window
        if intent.date and intent.date.confidence != "low":
            try:
                date_str = str(intent.date.value)
                target_date = datetime.date.fromisoformat(date_str)

                # Determine start and end datetimes
                time_period = intent.time_period.value if intent.time_period and intent.time_period.confidence != "low" else None

                if time_period:
                    start_dt, end_dt = self.clock.time_period_bounds(target_date, time_period)
                else:
                    start_dt = datetime.datetime.combine(target_date, datetime.time(0, 0, 0), tzinfo=self.clock.tz)
                    end_dt = datetime.datetime.combine(target_date, datetime.time(23, 59, 59), tzinfo=self.clock.tz)

                # If specific start_time or end_time with high confidence
                if intent.start_time and intent.start_time.confidence == "high":
                    t_parts = [int(p) for p in str(intent.start_time.value).split(":")]
                    start_dt = datetime.datetime.combine(
                        target_date,
                        datetime.time(t_parts[0], t_parts[1], t_parts[2] if len(t_parts) > 2 else 0),
                        tzinfo=self.clock.tz,
                    )

                if intent.end_time and intent.end_time.confidence == "high":
                    t_parts = [int(p) for p in str(intent.end_time.value).split(":")]
                    end_dt = datetime.datetime.combine(
                        target_date,
                        datetime.time(t_parts[0], t_parts[1], t_parts[2] if len(t_parts) > 2 else 0),
                        tzinfo=self.clock.tz,
                    )

                # Format ISO 8601 strings in UTC format for Qdrant RangeDateTime
                start_iso = start_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                end_iso = end_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                must_conditions.append(
                    FieldCondition(
                        key="start_time",
                        range=RangeDateTime(gte=start_iso, lte=end_iso),
                    )
                )
            except Exception as e:
                logger.warning(f"Could not build datetime filter condition for {intent.date}: {e}")

        # 10. Negations: excluded categories
        if intent.excluded_categories:
            for ex in intent.excluded_categories:
                if ex and ex.strip():
                    must_not_conditions.append(
                        FieldCondition(key="category", match=MatchValue(ex.strip().lower()))
                    )

        # 11. Negations: excluded subcategories (e.g. horror)
        if intent.excluded_subcategories:
            for ex in intent.excluded_subcategories:
                if ex and ex.strip():
                    must_not_conditions.append(
                        FieldCondition(key="subcategories", match=MatchValue(ex.strip().lower()))
                    )

        if not must_conditions and not must_not_conditions:
            return None

        return Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
        )


_global_filter_builder: Optional[FilterBuilder] = None


def get_filter_builder() -> FilterBuilder:
    """Singleton accessor for FilterBuilder."""
    global _global_filter_builder
    if _global_filter_builder is None:
        _global_filter_builder = FilterBuilder()
    return _global_filter_builder
