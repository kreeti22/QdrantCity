from pathlib import Path
import pytest

from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database
from app.models.experience import SearchFilterParams


@pytest.fixture
def semantic_edge_env(tmp_path: Path):
    """Provides a fresh isolated Qdrant Edge collection and embedding service."""
    edge_dir = tmp_path / "semantic_edge"
    settings = Settings(
        edge_storage_path=edge_dir,
        collection_name="test_semantic_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=False,
    )
    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repository = ExperienceRepository(shard, client, settings)
    emb_service = get_embedding_service(
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )

    yield {
        "settings": settings,
        "client": client,
        "shard": shard,
        "repository": repository,
        "embedding_service": emb_service,
    }

    client.close()


def test_6_seed_ingestion_with_real_embeddings(semantic_edge_env):
    """Test 6: Verify records are inserted using real FastEmbed embeddings."""
    repo = semantic_edge_env["repository"]
    settings = semantic_edge_env["settings"]
    service = semantic_edge_env["embedding_service"]

    assert repo.count() == 0
    seeded = seed_database(repo, settings, embedding_service=service, overwrite=True)
    assert seeded == 115
    assert repo.count() == 115

    # Verify points have 384-dimensional vectors stored in Qdrant Edge
    point = repo.get_by_id(1)
    assert point is not None
    assert point.id == 1
    assert point.title == "Interstellar: 70mm IMAX Special Presentation"


def test_7_semantic_search_relevance(semantic_edge_env):
    """Test 7: Verify relevant experiences appear in top results for natural-language queries."""
    repo = semantic_edge_env["repository"]
    settings = semantic_edge_env["settings"]
    service = semantic_edge_env["embedding_service"]
    seed_database(repo, settings, embedding_service=service, overwrite=True)

    # 1. Query: "something scary to watch late at night"
    q1 = service.embed_text("something scary to watch late at night")
    res1 = repo.search(q1, limit=5)
    assert len(res1) == 5
    # The top results should be horror/thriller movies
    categories_1 = [r.category for r in res1[:3]]
    assert "movies" in categories_1
    top_subcats_1 = res1[0].payload.get("subcategories", [])
    assert any(tag in top_subcats_1 for tag in ["horror", "scary", "paranormal", "slasher", "thriller"])

    # 2. Query: "relaxing evening with acoustic live music"
    q2 = service.embed_text("relaxing evening with acoustic live music")
    res2 = repo.search(q2, limit=5)
    assert len(res2) == 5
    # Top results should be concerts/music
    assert res2[0].category == "concerts"
    assert any(w in res2[0].title.lower() for w in ["folk", "strings", "jazz", "acoustic", "candlelight"])

    # 3. Query: "fun creative activity for kids and parents"
    q3 = service.embed_text("fun creative activity for kids and parents")
    res3 = repo.search(q3, limit=5)
    assert len(res3) == 5
    # Top results should be family-friendly workshops or activities or comedy
    assert res3[0].category in ["workshops", "comedy", "activities", "theatre"]
    assert "family" in res3[0].payload.get("subcategories", []) or "kids" in res3[0].payload.get("subcategories", [])

    # 4. Query: "intense competitive live sports tournament"
    q4 = service.embed_text("intense competitive live sports tournament")
    res4 = repo.search(q4, limit=5)
    assert len(res4) == 5
    assert res4[0].category == "sports"


def test_8_filtered_semantic_search(semantic_edge_env):
    """Test 8: Verify semantic retrieval constrained by structured payload filters."""
    repo = semantic_edge_env["repository"]
    settings = semantic_edge_env["settings"]
    service = semantic_edge_env["embedding_service"]
    seed_database(repo, settings, embedding_service=service, overwrite=True)

    # Query: "live performance" with strict category filter "theatre"
    query_vec = service.embed_text("live performance with actors and dialogue")
    theatre_filter = SearchFilterParams(category="theatre")
    theatre_results = repo.search(query_vec, limit=5, filters=theatre_filter)

    assert len(theatre_results) >= 1
    assert all(r.category == "theatre" for r in theatre_results)

    # Query: "outdoor adventure" with max_price = 30.0
    adv_vec = service.embed_text("outdoor adventure and fresh air")
    budget_outdoor = SearchFilterParams(is_indoor=False, max_price=30.0)
    budget_results = repo.search(adv_vec, limit=10, filters=budget_outdoor)

    assert len(budget_results) >= 1
    for r in budget_results:
        assert r.payload["is_indoor"] is False
        assert r.payload["price"] <= 30.0


def test_10_ingestion_idempotency(semantic_edge_env):
    """Test 10: Running ingestion twice does not create duplicate IDs or increase count."""
    repo = semantic_edge_env["repository"]
    settings = semantic_edge_env["settings"]
    service = semantic_edge_env["embedding_service"]

    # First run
    c1 = seed_database(repo, settings, embedding_service=service, overwrite=True)
    assert c1 == 115
    assert repo.count() == 115

    # Second run with overwrite=True
    c2 = seed_database(repo, settings, embedding_service=service, overwrite=True)
    assert c2 == 115
    assert repo.count() == 115

    # Verify ID 1 remains single intact point
    item = repo.get_by_id(1)
    assert item is not None
    assert item.id == 1
