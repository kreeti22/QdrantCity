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
def temp_edge_env(tmp_path: Path):
    """Provides a fresh isolated Qdrant Edge directory and client for testing."""
    edge_dir = tmp_path / "edge_data"
    settings = Settings(
        edge_storage_path=edge_dir,
        collection_name="test_experiences",
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
    emb_service = get_embedding_service(settings.embedding_model_name, settings.embedding_dimension)

    yield {
        "settings": settings,
        "client": client,
        "shard": shard,
        "repository": repository,
        "embedding_service": emb_service,
        "edge_dir": edge_dir,
    }

    client.close()


def test_edge_initialization_and_seeding(temp_edge_env):
    repo = temp_edge_env["repository"]
    settings = temp_edge_env["settings"]
    service = temp_edge_env["embedding_service"]

    assert repo.count() == 0
    seeded = seed_database(repo, settings, embedding_service=service, overwrite=True)
    assert seeded == 115
    assert repo.count() == 115


def test_edge_vector_retrieval(temp_edge_env):
    repo = temp_edge_env["repository"]
    settings = temp_edge_env["settings"]
    service = temp_edge_env["embedding_service"]
    seed_database(repo, settings, embedding_service=service, overwrite=True)

    query_vec = service.embed_text("Interstellar 70mm screening cosmic epic")
    results = repo.search(query_vector=query_vec, limit=3)

    assert len(results) == 3
    assert results[0].score > 0.0
    assert results[0].category == "movies"
    assert "Interstellar" in results[0].title


def test_edge_payload_filtering(temp_edge_env):
    repo = temp_edge_env["repository"]
    settings = temp_edge_env["settings"]
    service = temp_edge_env["embedding_service"]
    seed_database(repo, settings, embedding_service=service, overwrite=True)

    query_vec = service.embed_text("live event music")

    # 1. Filter by category
    filter_category = SearchFilterParams(category="comedy")
    comedy_results = repo.search(query_vec, limit=5, filters=filter_category)
    assert len(comedy_results) >= 1
    assert all(r.category == "comedy" for r in comedy_results)

    # 2. Filter by max_price
    filter_cheap = SearchFilterParams(max_price=20.0)
    cheap_results = repo.search(query_vec, limit=10, filters=filter_cheap)
    assert len(cheap_results) > 0
    assert all(r.payload["price"] <= 20.0 for r in cheap_results)

    # 3. Filter by outdoor (is_indoor=False)
    filter_outdoor = SearchFilterParams(is_indoor=False)
    outdoor_results = repo.search(query_vec, limit=10, filters=filter_outdoor)
    assert len(outdoor_results) >= 2
    assert all(r.payload["is_indoor"] is False for r in outdoor_results)


def test_get_by_id(temp_edge_env):
    repo = temp_edge_env["repository"]
    settings = temp_edge_env["settings"]
    service = temp_edge_env["embedding_service"]
    seed_database(repo, settings, embedding_service=service, overwrite=True)

    item = repo.get_by_id(1)
    assert item is not None
    assert item.id == 1
    assert "Interstellar" in item.title

    missing = repo.get_by_id(99999)
    assert missing is None
