from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
def api_client(tmp_path: Path):
    """Provides a TestClient initialized with an isolated Qdrant Edge environment."""
    test_settings = Settings(
        edge_storage_path=tmp_path / "api_edge",
        collection_name="api_test_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_root_endpoint(api_client: TestClient):
    response = api_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["architecture"] == "Qdrant Edge + Local FastEmbed In-Process Substrate"
    assert "Phase 2" in data["phase"]
    assert data["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert data["is_offline_only"] is True


def test_health_check(api_client: TestClient):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["engine"] == "qdrant-edge-py"
    assert data["engine_version"] == "0.8.0"
    assert data["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert data["is_local_edge"] is True
    assert data["is_local_embedding"] is True
    assert data["points_count"] == 115


def test_diagnostics_and_edge_status(api_client: TestClient):
    for endpoint in ["/api/diagnostics", "/edge/status"]:
        response = api_client.get(endpoint)
        assert response.status_code == 200
        diag = response.json()
        assert diag["engine"] == "qdrant-edge-py"
        assert diag["execution_mode"] == "in_process_local"
        assert diag["collection_name"] == "api_test_experiences"
        assert diag["points_count"] == 115
        assert diag["vector_size"] == 384
        assert diag["distance"] == "Cosine"
        assert diag["embedding_model_name"] == "BAAI/bge-small-en-v1.5"
        assert diag["embedding_dimension"] == 384
        assert diag["is_local_embedding"] is True
        assert diag["healthy"] is True


def test_natural_language_search(api_client: TestClient):
    payload = {
        "query": "something scary to watch late at night",
        "limit": 3,
    }
    response = api_client.post("/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_returned"] == 3
    assert data["query"] == "something scary to watch late at night"
    assert "latency_ms" in data
    assert data["latency_ms"]["embedding_ms"] > 0
    assert data["latency_ms"]["search_ms"] > 0
    assert data["latency_ms"]["total_ms"] > 0

    top_result = data["results"][0]
    assert "title" in top_result
    assert "category" in top_result
    assert "score" in top_result
    assert top_result["category"] == "movies"


def test_search_with_category_and_price_filters(api_client: TestClient):
    payload = {
        "query": "live music concert",
        "limit": 10,
        "filters": {
            "category": "concerts",
            "max_price": 40.0,
        },
    }
    response = api_client.post("/api/experiences/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_returned"] >= 1
    for item in data["results"]:
        assert item["category"] == "concerts"
        assert item["payload"]["price"] <= 40.0


def test_get_experience_by_id(api_client: TestClient):
    response = api_client.get("/api/experiences/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert "Interstellar" in data["title"]
    assert data["category"] == "movies"

    missing_response = api_client.get("/api/experiences/99999")
    assert missing_response.status_code == 404


def test_search_missing_query(api_client: TestClient):
    response = api_client.post("/search", json={"limit": 5})
    assert response.status_code == 400


def test_search_invalid_vector_dimension(api_client: TestClient):
    response = api_client.post(
        "/search",
        json={"vector": [0.1, 0.2], "limit": 5},
    )
    assert response.status_code == 422


def test_trigger_seed_api(api_client: TestClient):
    response = api_client.post("/api/experiences/seed?overwrite=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["seeded_count"] == 115
    assert data["total_points"] == 115
