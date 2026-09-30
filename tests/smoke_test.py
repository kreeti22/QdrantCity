"""
Smoke test — Phase 4 end-to-end demo validation.
Tests the 9 critical paths for hackathon demo readiness.
Run with: pytest tests/smoke_test.py -v
"""
import pytest
from fastapi.testclient import TestClient
from app.config.settings import Settings
from app.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    edge_dir = tmp_path_factory.mktemp("smoke_edge")
    mem_dir = tmp_path_factory.mktemp("smoke_mem")
    s = Settings(
        edge_storage_path=edge_dir,
        sqlite_db_path=str(mem_dir / "user_memory.db"),
        collection_name="smoke_experiences",
        auto_seed_on_startup=True,
        sync_enabled=False,
    )
    app = create_app(settings=s)
    with TestClient(app) as c:
        yield c


def test_1_app_starts_and_is_live(client):
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_2_ready_probe(client):
    r = client.get("/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data["points_count"] >= 100  # seeded


def test_3_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["is_local_edge"] is True
    assert data["is_local_embedding"] is True


def test_4_hybrid_search(client):
    r = client.post("/api/experiences/search", json={"query": "comedy shows tonight", "mode": "hybrid"})
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] >= 1
    assert data["mode"] == "hybrid"
    assert data["latency_ms"]["total_ms"] < 2000


def test_5_bookmark_save(client):
    # Get a valid ID first
    r = client.post("/api/experiences/search", json={"query": "movies"})
    exp_id = r.json()["results"][0]["id"]

    # Bookmark it
    r = client.post(f"/api/users/smoke-user/bookmarks/{exp_id}")
    assert r.status_code == 200
    assert r.json()["status"] in ("saved", "already_saved")

    # List bookmarks
    r = client.get("/api/users/smoke-user/bookmarks")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_6_personalized_search(client):
    r = client.post("/api/experiences/search", json={
        "query": "live music", "personalize": True, "user_id": "smoke-user"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["personalization"] is not None


def test_7_sync_status(client):
    r = client.get("/api/sync/status")
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data


def test_8_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "uptime_seconds" in data
    assert data["search"]["total"] >= 1  # at least one search executed in prior tests


def test_9_frontend_ui_served(client):
    r = client.get("/ui/index.html")
    assert r.status_code == 200
    assert "QdrantCinema" in r.text
