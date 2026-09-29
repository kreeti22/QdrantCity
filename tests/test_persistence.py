from pathlib import Path
from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database


def test_edge_data_persistence_across_restarts(tmp_path: Path):
    """Test 9: Verifies that EdgeShard persists points and indexes across client close and reload."""
    edge_dir = tmp_path / "persistence_edge"
    settings = Settings(
        edge_storage_path=edge_dir,
        collection_name="persisted_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=False,
    )
    service = get_embedding_service(settings.embedding_model_name, settings.embedding_dimension)

    # 1. First run: Initialize and insert points
    client1 = EdgeClient(settings.edge_storage_path)
    shard1 = initialize_experience_collection(client1, settings)
    repo1 = ExperienceRepository(shard1, client1, settings)

    assert repo1.count() == 0
    seeded = seed_database(repo1, settings, embedding_service=service, overwrite=True)
    assert seeded == 115
    assert repo1.count() == 115

    # Query before closing
    query_vec = service.embed_text("cyberpunk live synthwave concert")
    res1 = repo1.search(query_vec, limit=2)
    assert len(res1) == 2
    assert "Neon Horizon" in res1[0].title or "synthwave" in res1[0].payload.get("subcategories", [])

    # Gracefully close client & shard
    client1.close()
    del repo1
    del shard1
    del client1

    # 2. Verify on-disk artifacts exist
    collection_dir = settings.full_collection_path
    assert collection_dir.exists()
    assert (collection_dir / "edge_config.json").exists()
    assert (collection_dir / "embedding_metadata.json").exists()
    assert (collection_dir / "segments").exists()
    assert (collection_dir / "wal").exists()

    # 3. Second run: Re-open existing shard
    client2 = EdgeClient(settings.edge_storage_path)
    assert client2.is_shard_persisted(settings.collection_name) is True

    shard2 = initialize_experience_collection(client2, settings)
    repo2 = ExperienceRepository(shard2, client2, settings)

    # Assert count is preserved without re-seeding
    assert repo2.count() == 115

    # Search again on the reloaded shard
    res2 = repo2.search(query_vec, limit=2)
    assert len(res2) == 2
    assert res2[0].id == res1[0].id
    assert res2[0].title == res1[0].title

    client2.close()
