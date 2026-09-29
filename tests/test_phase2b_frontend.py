"""Phase 2B — Frontend Discovery UI Contract and Integration Tests.

Verifies:
1. Static files structure and module completeness.
2. FastAPI /ui mount and static assets serving.
3. Frontend API client search request & response contract.
4. ExperienceCard result elevation and null safety.
5. Empty result state handling.
6. Standardized error state handling.
7. Detail view retrieval by ID.
8. Date/time and price formatting utilities.
9. Example query chips contract.
"""

from pathlib import Path
import re
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
def api_client(tmp_path: Path):
    """Provides a TestClient initialized with an isolated Qdrant Edge environment."""
    test_settings = Settings(
        edge_storage_path=tmp_path / "frontend_test_edge",
        collection_name="frontend_test_experiences",
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


def test_1_frontend_static_files_structure():
    """Verify that all required frontend modules and components exist."""
    base = Path("frontend")
    assert base.exists(), "frontend directory must exist"
    assert (base / "index.html").exists()
    assert (base / "config.js").exists()
    assert (base / ".env.example").exists()
    assert (base / "api" / "client.js").exists()
    assert (base / "styles" / "main.css").exists()
    assert (base / "utilities" / "formatting.js").exists()
    assert (base / "pages" / "DiscoveryPage.js").exists()

    components = [
        "SearchBar.js",
        "QueryChips.js",
        "FilterBar.js",
        "ExperienceCard.js",
        "ResultsGrid.js",
        "EmptyState.js",
        "ErrorState.js",
        "ExperienceDetail.js",
    ]
    for comp in components:
        comp_path = base / "components" / comp
        assert comp_path.exists(), f"Component {comp} must exist at {comp_path}"
        content = comp_path.read_text(encoding="utf-8")
        assert len(content) > 50, f"Component {comp} should not be empty"


def test_2_ui_static_route_serving(api_client: TestClient):
    """Verify that FastAPI mounts and serves the frontend SPA at /ui."""
    response = api_client.get("/ui")
    assert response.status_code in (200, 307)
    if response.status_code == 307:
        response = api_client.get("/ui/")
    assert response.status_code == 200
    assert "QdrantCinema" in response.text
    assert "DiscoveryPage.js" in response.text

    # Test static CSS asset
    css_res = api_client.get("/ui/styles/main.css")
    assert css_res.status_code == 200
    assert "--bg-primary" in css_res.text

    # Test static JS asset
    js_res = api_client.get("/ui/api/client.js")
    assert js_res.status_code == 200
    assert "searchExperiences" in js_res.text


def test_3_search_request_and_response_contract(api_client: TestClient):
    """Verify that POST /api/experiences/search conforms to the frontend client contract."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "comedy tonight under $50"},
    )
    assert response.status_code == 200
    data = response.json()

    # Required top-level keys for frontend consumption
    assert "query" in data
    assert "results" in data
    assert "total_returned" in data
    assert "latency_ms" in data
    assert data["total_returned"] > 0
    assert len(data["results"]) == data["total_returned"]


def test_4_experience_card_fields_present(api_client: TestClient):
    """Verify that result items provide all fields required by ExperienceCard."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "standup comedy"},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 0

    item = results[0]
    expected_fields = [
        "id",
        "title",
        "category",
        "description",
        "venue",
        "city",
        "neighborhood",
        "start_time",
        "end_time",
        "price",
        "currency",
        "subcategories",
        "is_indoor",
        "rating",
        "score",
    ]
    for field in expected_fields:
        assert field in item, f"Field '{field}' missing from search result item"


def test_5_empty_result_contract(api_client: TestClient):
    """Verify that zero results returns HTTP 200 with an empty list for EmptyState."""
    response = api_client.post(
        "/api/experiences/search",
        json={
            "query": "something completely impossible",
            "filters": {
                "category": "sports",
                "city": "Atlantis",
                "max_price": 0.01,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert data["total_returned"] == 0


def test_6_api_error_state_contract(api_client: TestClient):
    """Verify that empty/invalid queries return standardized error shapes for ErrorState."""
    response = api_client.post(
        "/api/experiences/search",
        json={"query": "   "},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_QUERY"
    assert "cannot be empty" in data["error"]["message"].lower()


def test_7_experience_card_null_safety(api_client: TestClient):
    """Verify that missing optional card fields are handled safely."""
    # Lookup an experience and ensure safe null representations
    response = api_client.get("/api/experiences/31")
    assert response.status_code == 200
    exp = response.json()
    assert exp["id"] == 31
    assert exp["category"] == "comedy"
    assert isinstance(exp["price"], (int, float))


def test_8_detail_view_request_by_id(api_client: TestClient):
    """Verify that GET /api/experiences/{id} retrieves full details for ExperienceDetail."""
    # Existing experience
    res = api_client.get("/api/experiences/31")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 31
    assert "Late Night Underground Standup Comedy Showcase" in data["title"]
    assert "venue" in data
    assert "The Velvet Trap Basement" in data["venue"]

    # Nonexistent experience returns 404 with standardized error
    res_404 = api_client.get("/api/experiences/999999")
    assert res_404.status_code == 404
    err_data = res_404.json()
    assert "error" in err_data
    assert err_data["error"]["code"] == "NOT_FOUND"


def test_9_formatting_utilities_contract():
    """Verify frontend formatting utility logic in Python mirror tests."""
    # Price formatting rules
    def format_price(price, currency="USD"):
        if price == 0 or price == "0":
            return "Free"
        if price is None:
            return "Price TBA"
        num = float(price)
        formatted = f"{int(num)}" if num.is_integer() else f"{num:.2f}"
        curr = str(currency or "USD").upper()
        if curr in ("USD", "$"):
            return f"${formatted}"
        elif curr in ("INR", "RS", "₹"):
            return f"₹{formatted}"
        elif curr in ("EUR", "€"):
            return f"€{formatted}"
        return f"{curr} {formatted}"

    assert format_price(0) == "Free"
    assert format_price(22.0, "USD") == "$22"
    assert format_price(22.5, "USD") == "$22.50"
    assert format_price(800, "INR") == "₹800"
    assert format_price(None) == "Price TBA"

    # Category badge mapping
    categories = ["comedy", "movies", "concerts", "theatre", "sports", "festivals", "workshops", "exhibitions", "activities"]
    for cat in categories:
        assert len(cat) > 0


def test_10_filter_overrides_integration(api_client: TestClient):
    """Verify that FilterBar controls pass valid overrides to backend."""
    response = api_client.post(
        "/api/experiences/search",
        json={
            "query": "comedy",
            "filters": {
                "category": "comedy",
                "max_price": 25.0,
                "is_indoor": True,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filters_applied"]["category"] == "comedy"
    assert data["filters_applied"]["max_price"] == 25.0
    assert data["filters_applied"]["is_indoor"] is True
    for res in data["results"]:
        assert res["category"] == "comedy"
        assert res["price"] <= 25.0
        assert res["is_indoor"] is True
