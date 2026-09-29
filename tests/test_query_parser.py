import datetime
import pytest

from app.config.settings import Settings
from app.intent.models import IntentSource, StructuredSearchIntent
from app.intent.parser import LocalQueryParser
from app.utils.clock import TimeProvider


@pytest.fixture
def parser() -> LocalQueryParser:
    clock = TimeProvider(
        tz_name="UTC",
        reference_datetime="2026-10-15T12:00:00Z",  # Thursday noon
    )
    settings = Settings(
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        default_currency="USD",
    )
    return LocalQueryParser(clock=clock, settings=settings)


def test_category_extraction(parser: LocalQueryParser):
    test_cases = [
        ("action movies in imax", "movies"),
        ("rock concerts downtown", "concerts"),
        ("standup comedy show", "comedy"),
        ("broadway musical theatre", "theatre"),
        ("basketball sports match", "sports"),
        ("craft beer festival", "festivals"),
        ("pottery workshops for beginners", "workshops"),
        ("modern art exhibitions", "exhibitions"),
        ("outdoor hiking activities", "activities"),
    ]
    for query, expected_cat in test_cases:
        intent = parser.parse(query)
        assert intent.category is not None, f"Failed for query '{query}'"
        assert intent.category.value == expected_cat
        assert intent.category.confidence in ("high", "medium")


def test_price_extraction(parser: LocalQueryParser):
    # Under price
    intent = parser.parse("indie movies under 25 dollars")
    assert intent.price_max is not None
    assert intent.price_max.value == 25.0
    assert intent.price_min is None

    # Below price with dollar sign
    intent = parser.parse("live jazz below $40")
    assert intent.price_max is not None
    assert intent.price_max.value == 40.0

    # Free
    intent = parser.parse("free outdoor festival")
    assert intent.price_max is not None
    assert intent.price_max.value == 0.0

    # Between range
    intent = parser.parse("comedy club between 15 and 35 dollars")
    assert intent.price_min is not None
    assert intent.price_min.value == 15.0
    assert intent.price_max is not None
    assert intent.price_max.value == 35.0


def test_date_extraction(parser: LocalQueryParser):
    # Reference date is Thursday 2026-10-15
    intent_today = parser.parse("comedy tonight")
    assert intent_today.date is not None
    assert intent_today.date.value == "2026-10-15"
    assert intent_today.time_period is not None
    assert intent_today.time_period.value in ("evening", "night")

    intent_tomorrow = parser.parse("rock concert tomorrow")
    assert intent_tomorrow.date is not None
    assert intent_tomorrow.date.value == "2026-10-16"

    intent_weekend = parser.parse("art festival this weekend")
    assert intent_weekend.date is not None
    assert intent_weekend.date.value == "2026-10-17"


def test_time_extraction(parser: LocalQueryParser):
    # Evening period
    intent_eve = parser.parse("evening film screening")
    assert intent_eve.time_period is not None
    assert intent_eve.time_period.value == "evening"

    # After specific hour
    intent_after = parser.parse("electronic music after 8pm")
    assert intent_after.start_time is not None
    assert intent_after.start_time.value == "20:00:00"

    # Before specific hour
    intent_before = parser.parse("workshop before 5 pm")
    assert intent_before.end_time is not None
    assert intent_before.end_time.value == "17:00:00"


def test_location_and_radius_extraction(parser: LocalQueryParser):
    # City and neighborhood
    intent_loc = parser.parse("jazz clubs in Mission San Francisco")
    assert intent_loc.city is not None
    assert intent_loc.city.value == "San Francisco"
    assert intent_loc.neighborhood is not None
    assert intent_loc.neighborhood.value == "Mission"

    # Venue
    intent_venue = parser.parse("screening at Castro Theatre")
    assert intent_venue.venue is not None
    assert intent_venue.venue.value == "Castro Theatre"

    # Radius requires device location
    intent_radius = parser.parse("concerts within 5 km")
    assert intent_radius.radius_km is not None
    assert intent_radius.radius_km.value == 5.0
    assert intent_radius.location_required is True

    intent_near = parser.parse("comedy near me")
    assert intent_near.location_required is True


def test_language_and_format_extraction(parser: LocalQueryParser):
    # Language
    intent_lang = parser.parse("japanese anime screening")
    assert intent_lang.language is not None
    assert intent_lang.language.value == "Japanese"

    # Format
    intent_fmt = parser.parse("sci-fi film in IMAX 3D")
    assert intent_fmt.format is not None
    assert "imax" in intent_fmt.format.value.lower()


def test_indoor_outdoor_extraction(parser: LocalQueryParser):
    intent_in = parser.parse("indoor pottery workshop")
    assert intent_in.is_indoor is not None
    assert intent_in.is_indoor.value is True

    intent_out = parser.parse("outdoor food festival")
    assert intent_out.is_indoor is not None
    assert intent_out.is_indoor.value is False


def test_negation_extraction(parser: LocalQueryParser):
    intent = parser.parse("japanese movie not horror no comedy")
    assert "horror" in intent.excluded_subcategories
    assert "comedy" in intent.excluded_categories


def test_semantic_query_distillation(parser: LocalQueryParser):
    query = "standup comedy tonight under 30 in San Francisco"
    intent = parser.parse(query)
    # Original query must ALWAYS be perfectly preserved
    assert intent.original_query == query
    # Semantic query strips hard constraints while keeping core keywords
    assert "comedy" in intent.semantic_query or "standup" in intent.semantic_query
    assert "under 30" not in intent.semantic_query
    assert "tonight" not in intent.semantic_query


def test_ambiguity_conservative_handling(parser: LocalQueryParser):
    # "around 1000" is ambiguous (not strict under/over) -> must NOT invent hard price filter
    intent_approx = parser.parse("something cheap around 1000")
    assert intent_approx.price_max is None
    assert intent_approx.price_min is None
    assert intent_approx.original_query == "something cheap around 1000"
    assert "around 1000" in intent_approx.unresolved_terms or "around 1000" in intent_approx.semantic_query

    # "after 8" without am/pm -> ambiguous, must not produce invalid high-confidence filter
    intent_ambig_time = parser.parse("live music after 8")
    if intent_ambig_time.start_time is not None:
        assert intent_ambig_time.start_time.confidence == "low"
