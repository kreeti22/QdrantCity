from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
def api_client(tmp_path: Path):
    """Provides a TestClient initialized with an isolated Qdrant Edge environment."""
    test_settings = Settings(
        edge_storage_path=tmp_path / "phase2a_edge",
        collection_name="phase2a_test_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        cors_origins=["http://localhost:3000", "https://qdrantcinema.app"],
        max_query_length=500,
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_1_valid_natural_language_search(api_client: TestClient):
    """Valid natural-language search returns HTTP 200 with structured results."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "comedy tonight under $50"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "comedy tonight under $50"
    assert data["total_returned"] > 0
    assert len(data["results"]) == data["total_returned"]


def test_2_empty_query_rejected(api_client: TestClient):
    """Empty query returns HTTP 400 with standardized error shape."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": ""},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_QUERY"
    assert "cannot be empty" in data["error"]["message"].lower()


def test_3_whitespace_only_query_rejected(api_client: TestClient):
    """Whitespace-only query is treated as empty and returns HTTP 400."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "     "},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_QUERY"


def test_4_very_long_query_rejected(api_client: TestClient):
    """Pathological inputs exceeding max_query_length (500 chars) are rejected."""
    long_query = "concert " * 80  # 640 characters
    response = api_client.post(
        "/api/experiences/search",
        json={"query": long_query},
    )
    assert response.status_code in (400, 422)
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] in ("QUERY_TOO_LONG", "VALIDATION_ERROR")


def test_5_no_results_search_returns_200_empty_list(api_client: TestClient):
    """No-result searches return HTTP 200 with results: [] rather than failing."""
    response = api_client.post(
        "/api/experiences/search",
        json={
            "query": "something completely impossible",
            "filters": {
                "category": "sports",
                "max_price": 0.01,
                "is_indoor": True,
                "city": "Atlantis",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert data["total_returned"] == 0


def test_6_result_serialization_and_card_fields(api_client: TestClient):
    """Each result item exposes complete frontend card fields."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "Interstellar IMAX", "limit": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    card = data["results"][0]

    # Required frontend display fields
    assert isinstance(card["id"], int)
    assert isinstance(card["title"], str) and len(card["title"]) > 0
    assert isinstance(card["category"], str)
    assert isinstance(card["description"], str)
    assert "venue" in card
    assert "city" in card
    assert "neighborhood" in card
    assert "start_time" in card
    assert "end_time" in card
    assert "price" in card
    assert "currency" in card
    assert "image_url" in card
    assert isinstance(card["subcategories"], list)
    assert "language" in card
    assert "is_indoor" in card
    assert isinstance(card["score"], float)


def test_7_missing_optional_fields_safe(api_client: TestClient):
    """Missing optional fields like image_url or language default safely to None."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "comedy", "limit": 3},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["results"]:
        # None is a safe, valid value for optional fields
        assert item.get("image_url") is None or isinstance(item["image_url"], str)
        assert item.get("language") is None or isinstance(item["language"], str)


def test_8_search_metadata_breakdown(api_client: TestClient):
    """Response exposes complete search metadata and latency metrics."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "rock concert in San Francisco"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "rock concert in San Francisco"
    assert "semantic_query" in data
    assert data["mode"] == "hybrid"
    assert "total_returned" in data
    assert "latency_ms" in data

    latency = data["latency_ms"]
    assert "query_parsing_ms" in latency
    assert "dense_embedding_ms" in latency
    assert "dense_search_ms" in latency
    assert "bm25_embedding_ms" in latency
    assert "bm25_search_ms" in latency
    assert "total_ms" in latency
    assert latency["total_ms"] > 0


def test_9_health_liveness_readiness_endpoints(api_client: TestClient):
    """Lightweight health, liveness, and readiness endpoints behave correctly."""
    # Liveness probe
    live_resp = api_client.get("/live")
    assert live_resp.status_code == 200
    assert live_resp.json()["status"] == "ok"

    # Readiness probe
    ready_resp = api_client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"
    assert ready_resp.json()["points_count"] == 115

    # Health endpoint
    health_resp = api_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"
    assert health_resp.json()["points_count"] == 115


def test_10_startup_reuse_and_idempotent_seeding(api_client: TestClient):
    """Calling seed without overwrite reuses existing Edge shard idempotently."""
    seed_resp = api_client.post("/api/experiences/seed?overwrite=false")
    assert seed_resp.status_code == 200
    seed_data = seed_resp.json()
    assert seed_data["seeded_count"] == 0  # Reused existing 115 points
    assert seed_data["total_points"] == 115


def test_11_cors_headers_handling(api_client: TestClient):
    """CORS middleware returns proper access-control-allow-origin headers."""
    response = api_client.options(
        "/api/experiences/search",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_12_api_error_response_shape(api_client: TestClient):
    """Standardized API error response follows {error: {code, message}} contract."""
    response = api_client.get("/api/experiences/999999")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]
    assert "999999" in data["error"]["message"]


def test_13_phase_1d_query_understanding_intact(api_client: TestClient):
    """Phase 1D query understanding, filter building, and radius safety remain intact."""
    # Radius expression sets location_required = True
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "jazz concerts near me within 5 km"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] is not None
    assert data["intent"]["location_required"] is True
    assert data["intent"]["radius_km"]["value"] == 5.0
