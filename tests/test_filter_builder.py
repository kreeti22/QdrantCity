import datetime
import pytest

from app.intent.models import ExtractedField, IntentSource, StructuredSearchIntent
from app.models.experience import SearchFilterParams
from app.retrieval.filter_builder import FilterBuilder
from app.utils.clock import TimeProvider


@pytest.fixture
def clock() -> TimeProvider:
    return TimeProvider(tz_name="UTC", reference_datetime="2026-10-15T12:00:00Z")


@pytest.fixture
def filter_builder(clock: TimeProvider) -> FilterBuilder:
    return FilterBuilder(clock=clock)


def test_build_from_params(filter_builder: FilterBuilder):
    # None returns None
    assert filter_builder.build_from_params(None) is None

    # Empty params returns None
    assert filter_builder.build_from_params(SearchFilterParams()) is None

    # Params with category and price
    params = SearchFilterParams(category="movies", min_price=10.0, max_price=30.0, is_indoor=True)
    f = filter_builder.build_from_params(params)
    assert f is not None
    assert f.must is not None
    assert len(f.must) == 3
    keys = [cond.key for cond in f.must]
    assert "category" in keys
    assert "price" in keys
    assert "is_indoor" in keys


def test_build_from_intent_category_and_price(filter_builder: FilterBuilder):
    intent = StructuredSearchIntent(
        original_query="movies under 25",
        semantic_query="movies",
        category=ExtractedField(value="movies", source=IntentSource.EXPLICIT, confidence="high"),
        price_max=ExtractedField(value=25.0, source=IntentSource.EXPLICIT, confidence="high"),
    )
    f = filter_builder.build_from_intent(intent)
    assert f is not None
    assert f.must is not None
    assert len(f.must) == 2
    cat_cond = next(c for c in f.must if c.key == "category")
    assert cat_cond.match.value == "movies"
    price_cond = next(c for c in f.must if c.key == "price")
    assert price_cond.range.lte == 25.0


def test_build_from_intent_date_range(filter_builder: FilterBuilder):
    # Date with evening period
    intent = filter_builder.clock
    intent_obj = StructuredSearchIntent(
        original_query="comedy tonight",
        semantic_query="comedy",
        category=ExtractedField(value="comedy", source=IntentSource.EXPLICIT, confidence="high"),
        date=ExtractedField(value="2026-10-15", source=IntentSource.EXPLICIT, confidence="high"),
        time_period=ExtractedField(value="evening", source=IntentSource.EXPLICIT, confidence="high"),
    )
    f = filter_builder.build_from_intent(intent_obj)
    assert f is not None
    time_cond = next(c for c in f.must if c.key == "start_time")
    assert "2026-10-15" in str(time_cond.range.gte) and "17:00:00" in str(time_cond.range.gte)
    assert "2026-10-15" in str(time_cond.range.lte) and "20:59:59" in str(time_cond.range.lte)


def test_build_from_intent_negations(filter_builder: FilterBuilder):
    intent = StructuredSearchIntent(
        original_query="movies not horror no drama",
        semantic_query="movies",
        category=ExtractedField(value="movies", source=IntentSource.EXPLICIT, confidence="high"),
        excluded_categories=["theatre"],
        excluded_subcategories=["horror"],
    )
    f = filter_builder.build_from_intent(intent)
    assert f is not None
    assert f.must_not is not None
    assert len(f.must_not) == 2
    must_not_keys = [c.key for c in f.must_not]
    assert "category" in must_not_keys
    assert "subcategories" in must_not_keys


def test_build_from_intent_with_override_params(filter_builder: FilterBuilder):
    # Intent specifies category=comedy and max_price=30
    intent = StructuredSearchIntent(
        original_query="comedy under 30",
        semantic_query="comedy",
        category=ExtractedField(value="comedy", source=IntentSource.EXPLICIT, confidence="high"),
        price_max=ExtractedField(value=30.0, source=IntentSource.EXPLICIT, confidence="high"),
    )
    # Caller explicitly overrides category to "movies" and max_price to 15
    override = SearchFilterParams(category="movies", max_price=15.0)
    f = filter_builder.build_from_intent(intent, override_filters=override)
    assert f is not None
    cat_cond = next(c for c in f.must if c.key == "category")
    assert cat_cond.match.value == "movies"
    price_cond = next(c for c in f.must if c.key == "price")
    assert price_cond.range.lte == 15.0


def test_safe_handling_of_empty_and_low_confidence(filter_builder: FilterBuilder):
    # Empty intent returns None
    intent_empty = StructuredSearchIntent(original_query="something vague")
    assert filter_builder.build_from_intent(intent_empty) is None

    # Low confidence fields are ignored to prevent over-filtering
    intent_low = StructuredSearchIntent(
        original_query="maybe around 1000",
        price_max=ExtractedField(value=1000.0, source=IntentSource.AMBIGUOUS, confidence="low"),
    )
    assert filter_builder.build_from_intent(intent_low) is None
