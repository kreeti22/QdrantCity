from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.memory.models import InteractionType
from app.memory.repository import MemoryRepository
from app.memory.service import UserMemoryService
from app.models.experience import Experience


@pytest.fixture
def memory_test_settings(tmp_path: Path):
    """Provides isolated test settings for Phase 2C memory tests."""
    return Settings(
        edge_storage_path=tmp_path / "phase2c_edge",
        collection_name="phase2c_test_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        user_memory_path=tmp_path / "user_memory.db",
        default_user_id="test-user-1",
        enable_personalization=True,
        personalization_boost_weight=0.20,
    )


@pytest.fixture
def api_client(memory_test_settings: Settings):
    """Provides a TestClient initialized with isolated Qdrant Edge and SQLite memory."""
    app = create_app(memory_test_settings)
    with TestClient(app) as client:
        yield client


# --- Repository & Service Unit Tests ---

def test_default_user_preference_profile(tmp_path: Path):
    db_path = tmp_path / "repo_test.db"
    repo = MemoryRepository(db_path)
    profile = repo.get_user_profile("unknown-user")
    assert profile.user_id == "unknown-user"
    assert profile.category_affinities == {}
    assert profile.total_interactions == 0
    assert profile.saved_experience_count == 0
    repo.close()


def test_record_interactions_and_weighting(tmp_path: Path):
    db_path = tmp_path / "weights_test.db"
    repo = MemoryRepository(db_path)
    service = UserMemoryService(repo)

    # Record 1 search (weight 1.0) for comedy
    service.record_interaction(
        user_id="u1",
        interaction_type=InteractionType.SEARCH,
        category="comedy",
        price=30.0,
        is_indoor=True,
    )

    profile = service.get_user_preferences("u1")
    assert profile.category_affinities.get("comedy") == 1.0
    assert profile.total_interactions == 1

    # Record 1 view (weight 2.0) for concerts
    service.record_interaction(
        user_id="u1",
        interaction_type=InteractionType.VIEW,
        category="concerts",
        price=90.0,
        is_indoor=False,
    )

    profile = service.get_user_preferences("u1")
    # Total weights: comedy 1.0, concerts 2.0 => sum 3.0
    # comedy = 1/3 ~ 0.333, concerts = 2/3 ~ 0.667
    assert pytest.approx(profile.category_affinities["comedy"], 0.01) == 0.333
    assert pytest.approx(profile.category_affinities["concerts"], 0.01) == 0.667
    assert profile.total_interactions == 2
    repo.close()


def test_bounded_interaction_history_trimming(tmp_path: Path):
    db_path = tmp_path / "trim_test.db"
    repo = MemoryRepository(db_path)

    # Insert 250 interactions
    for i in range(250):
        repo.record_interaction(
            user_id="u_trim",
            event_type="view",
            experience_id=f"exp-{i}",
            metadata={"category": "movies", "price": 15.0, "is_indoor": True},
        )

    # Bounded to MAX_INTERACTIONS = 200
    interactions = repo.get_interactions("u_trim", limit=300)
    assert len(interactions) == 200
    # Most recent should be exp-249
    assert interactions[0].experience_id == "exp-249"
    repo.close()


def test_bookmark_persistence_across_restarts(tmp_path: Path):
    db_path = tmp_path / "persist_test.db"
    
    # Session 1
    repo1 = MemoryRepository(db_path)
    service1 = UserMemoryService(repo1)
    service1.add_bookmark("u_persist", "exp-001", "theatre", "Hamlet", 45.0)
    repo1.close()

    # Session 2 - New instance pointing to same SQLite DB
    repo2 = MemoryRepository(db_path)
    service2 = UserMemoryService(repo2)
    bookmarks = service2.list_bookmarks("u_persist")
    assert len(bookmarks) == 1
    assert bookmarks[0].experience_id == "exp-001"
    assert bookmarks[0].title == "Hamlet"
    assert bookmarks[0].category == "theatre"
    assert service2.is_bookmarked("u_persist", "exp-001") is True
    repo2.close()


# --- API Integration Tests ---

def test_bookmark_api_crud(api_client: TestClient):
    user_id = "test-user-1"
    # Find a valid experience from search or seed
    search_res = api_client.post("/api/experiences/search", json={"query": "comedy", "limit": 1})
    assert search_res.status_code == 200
    exp_id = search_res.json()["results"][0]["id"]
    exp_title = search_res.json()["results"][0]["title"]

    # 1. Add Bookmark
    post_res = api_client.post(f"/api/users/{user_id}/bookmarks/{exp_id}")
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["status"] == "saved"
    assert data["experience_id"] == exp_id

    # 2. List Bookmarks
    get_res = api_client.get(f"/api/users/{user_id}/bookmarks")
    assert get_res.status_code == 200
    b_data = get_res.json()
    assert b_data["count"] == 1
    assert b_data["bookmarks"][0]["experience_id"] == exp_id
    assert b_data["bookmarks"][0]["title"] == exp_title

    # 3. Search should now reflect is_saved=True
    search_with_user = api_client.post(
        "/api/experiences/search",
        json={"query": "comedy", "user_id": user_id, "limit": 10},
    )
    assert search_with_user.status_code == 200
    saved_hits = [e for e in search_with_user.json()["results"] if e["id"] == exp_id]
    assert len(saved_hits) == 1
    assert saved_hits[0]["is_saved"] is True

    # 4. Remove Bookmark
    del_res = api_client.delete(f"/api/users/{user_id}/bookmarks/{exp_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "removed"

    # 5. List should be empty
    get_res2 = api_client.get(f"/api/users/{user_id}/bookmarks")
    assert get_res2.status_code == 200
    assert get_res2.json()["count"] == 0


def test_bookmark_nonexistent_experience_404(api_client: TestClient):
    res = api_client.post("/api/users/test-user-1/bookmarks/999999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "EXPERIENCE_NOT_FOUND"


def test_preferences_api_and_interaction_recording(api_client: TestClient):
    user_id = "user-pref-test"
    # Check default preferences
    pref_res = api_client.get(f"/api/users/{user_id}/preferences")
    assert pref_res.status_code == 200
    pref_data = pref_res.json()
    assert pref_data["total_interactions"] == 0
    assert pref_data["category_affinities"] == {}

    # Record a view interaction via API
    rec_res = api_client.post(
        f"/api/users/{user_id}/interactions",
        json={
            "interaction_type": "view",
            "experience_id": "exp-test-1",
            "category": "festivals",
            "price": 50.0,
            "is_indoor": False,
        },
    )
    assert rec_res.status_code == 200
    assert rec_res.json()["status"] == "recorded"

    # Check updated preferences
    pref_res2 = api_client.get(f"/api/users/{user_id}/preferences")
    assert pref_res2.status_code == 200
    pref_data2 = pref_res2.json()
    assert pref_data2["total_interactions"] == 1
    assert pref_data2["category_affinities"]["festivals"] == 1.0


def test_memory_reset(api_client: TestClient):
    user_id = "user-reset-test"
    # Add interaction
    api_client.post(
        f"/api/users/{user_id}/interactions",
        json={"interaction_type": "search", "category": "movies"},
    )
    pref1 = api_client.get(f"/api/users/{user_id}/preferences").json()
    assert pref1["total_interactions"] == 1

    # Reset memory
    reset_res = api_client.delete(f"/api/users/{user_id}/memory")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "cleared"

    # Confirm cleared
    pref2 = api_client.get(f"/api/users/{user_id}/preferences").json()
    assert pref2["total_interactions"] == 0
    assert pref2["category_affinities"] == {}


def test_search_personalization_reranking_and_telemetry(api_client: TestClient):
    user_id = "user-personalize-test"
    
    # User interacts heavily with comedy
    for _ in range(5):
        api_client.post(
            f"/api/users/{user_id}/interactions",
            json={
                "interaction_type": "view",
                "category": "comedy",
                "price": 35.0,
                "is_indoor": True,
            },
        )

    # Search query that returns multiple categories (e.g. "weekend" or broad query)
    res_personalized = api_client.post(
        "/api/experiences/search",
        json={
            "query": "weekend fun",
            "user_id": user_id,
            "personalize": True,
            "limit": 10,
        },
    )
    assert res_personalized.status_code == 200
    data_p = res_personalized.json()
    
    # Verify personalization metadata is returned
    assert "personalization" in data_p
    p_meta = data_p["personalization"]
    assert p_meta["enabled"] is True
    assert p_meta["user_id"] == user_id
    if p_meta["applied"]:
        assert len(p_meta["signals_used"]) > 0

    # Search with personalize=False
    res_unpersonalized = api_client.post(
        "/api/experiences/search",
        json={
            "query": "weekend fun",
            "user_id": user_id,
            "personalize": False,
            "limit": 10,
        },
    )
    assert res_unpersonalized.status_code == 200
    data_unp = res_unpersonalized.json()
    assert data_unp["personalization"]["enabled"] is True
    assert data_unp["personalization"]["applied"] is False


def test_multi_user_isolation(api_client: TestClient):
    # User A likes comedy
    api_client.post(
        "/api/users/user-A/interactions",
        json={"interaction_type": "view", "category": "comedy"},
    )
    # User B likes sports
    api_client.post(
        "/api/users/user-B/interactions",
        json={"interaction_type": "view", "category": "sports"},
    )

    pref_a = api_client.get("/api/users/user-A/preferences").json()
    pref_b = api_client.get("/api/users/user-B/preferences").json()

    assert "comedy" in pref_a["category_affinities"]
    assert "sports" not in pref_a["category_affinities"]
    assert "sports" in pref_b["category_affinities"]
    assert "comedy" not in pref_b["category_affinities"]


def test_disabled_personalization_in_settings(tmp_path: Path):
    test_settings = Settings(
        edge_storage_path=tmp_path / "disabled_pers_edge",
        collection_name="disabled_pers_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        user_memory_path=tmp_path / "disabled_memory.db",
        default_user_id="test-disabled-user",
        enable_personalization=False,
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        # Record interactions
        client.post(
            "/api/users/test-disabled-user/interactions",
            json={"interaction_type": "view", "category": "comedy"},
        )
        res = client.post(
            "/api/experiences/search",
            json={"query": "comedy", "personalize": True, "user_id": "test-disabled-user"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["personalization"]["enabled"] is False
        assert data["personalization"]["applied"] is False


def test_price_and_indoor_preference_derivation(tmp_path: Path):
    db_path = tmp_path / "stats_test.db"
    repo = MemoryRepository(db_path)
    service = UserMemoryService(repo)

    # 3 indoor views with prices 20, 30, 40
    for price in [20.0, 30.0, 40.0]:
        service.record_interaction(
            user_id="u_stats",
            interaction_type="view",
            price=price,
            is_indoor=True,
        )

    profile = service.get_user_preferences("u_stats")
    assert profile.preferred_price_min == 20.0
    assert profile.preferred_price_max == 40.0
    assert profile.preferred_price_avg == 30.0
    assert profile.preferred_indoor is True
    repo.close()

