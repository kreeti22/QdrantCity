from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    test_settings = Settings(
        edge_storage_path=tmp_path / "test_intent_edge",
        collection_name="intent_test_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
    )
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        yield test_client


def test_end_to_end_search_with_intent(client: TestClient):
    query = "standup comedy under 30"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 5, "enable_intent": True},
    )
    assert response.status_code == 200
    data = response.json()

    # Original query must ALWAYS be preserved
    assert data["query"] == query
    assert data["semantic_query"] is not None
    assert "under 30" not in data["semantic_query"]

    # Intent breakdown present
    assert data["intent"] is not None
    assert data["intent"]["original_query"] == query
    assert data["intent"]["category"]["value"] == "comedy"
    assert data["intent"]["price_max"]["value"] == 30.0

    # Query parsing latency recorded
    assert data["latency_ms"]["query_parsing_ms"] is not None
    assert data["latency_ms"]["query_parsing_ms"] >= 0.0

    # Hard filter verified on returned items
    for item in data["results"]:
        assert item["category"] == "comedy"
        assert item["payload"]["price"] <= 30.0


def test_search_with_intent_disabled(client: TestClient):
    query = "standup comedy under 30"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 5, "enable_intent": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == query
    assert data["intent"] is None
    assert data["latency_ms"]["query_parsing_ms"] is None


def test_imax_scifi_movies(client: TestClient):
    query = "IMAX sci-fi movies"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] is not None
    assert data["intent"]["category"]["value"] == "movies"
    assert data["intent"]["format"]["value"].lower() == "imax"

    # Verify returned experiences have movie category and imax subcategory
    for item in data["results"]:
        assert item["category"] == "movies"
        subs = [s.lower() for s in item["payload"].get("subcategories", [])]
        assert "imax" in subs


def test_radius_and_near_me_sets_location_required(client: TestClient):
    query = "jazz concert near me within 5 km"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] is not None
    assert data["intent"]["location_required"] is True
    assert data["intent"]["radius_km"]["value"] == 5.0


def test_ambiguous_pricing_does_not_break_retrieval(client: TestClient):
    # "something cheap around 1000" should NOT eliminate results with an invalid hard filter
    query = "something cheap around 1000"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] is not None
    assert data["intent"]["price_max"] is None
    assert data["intent"]["price_min"] is None
    assert len(data["results"]) > 0


def test_negation_filter_integration(client: TestClient):
    query = "movies not horror"
    response = client.post(
        "/api/experiences/search",
        json={"query": query, "mode": "hybrid", "limit": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] is not None
    assert "horror" in data["intent"]["excluded_subcategories"]

    for item in data["results"]:
        assert item["category"] == "movies"
        subs = [s.lower() for s in item["payload"].get("subcategories", [])]
        assert "horror" not in subs
