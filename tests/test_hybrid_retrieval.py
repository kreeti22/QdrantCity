from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.bm25 import get_bm25_service
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database
from app.main import create_app
from app.models.experience import SearchFilterParams


@pytest.fixture
def hybrid_env(tmp_path: Path):
    """Provides an isolated Qdrant Edge environment with dual dense+BM25 vectors."""
    edge_dir = tmp_path / "hybrid_edge"
    settings = Settings(
        edge_storage_path=edge_dir,
        collection_name="test_hybrid_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        dense_vector_name="dense",
        sparse_vector_name="bm25",
        rrf_k=60,
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=10,
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
    bm25_service = get_bm25_service()

    # Seed the 115 experiences with dual vectors
    seed_database(repository, settings, embedding_service=emb_service, overwrite=True)

    yield {
        "settings": settings,
        "client": client,
        "shard": shard,
        "repository": repository,
        "embedding_service": emb_service,
        "bm25_service": bm25_service,
    }

    client.close()


@pytest.fixture
def hybrid_api_client(tmp_path: Path):
    """Provides a TestClient initialized with an isolated Qdrant Edge environment for API testing."""
    test_settings = Settings(
        edge_storage_path=tmp_path / "api_hybrid_edge",
        collection_name="api_hybrid_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        dense_vector_name="dense",
        sparse_vector_name="bm25",
        rrf_k=60,
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=10,
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_exact_keyword_retrieval(hybrid_env):
    """Verify BM25 and Hybrid retrieval precisely surface exact title/venue keywords."""
    repo = hybrid_env["repository"]
    emb_service = hybrid_env["embedding_service"]
    bm25_service = hybrid_env["bm25_service"]

    query_str = "Interstellar IMAX"
    dense_vec = emb_service.embed_text(query_str)
    sparse_vec = bm25_service.embed_query(query_str)

    # 1. Sparse BM25 alone
    sparse_results = repo.search_sparse(sparse_vec, limit=5)
    assert len(sparse_results) > 0
    # Top sparse result must be Interstellar
    assert "Interstellar" in sparse_results[0].title
    assert sparse_results[0].sparse_rank == 1
    assert sparse_results[0].sparse_score is not None

    # 2. Hybrid search combining dense and BM25
    hybrid_results, timings = repo.search_hybrid(
        query_vector=dense_vec,
        sparse_vector=sparse_vec,
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=5,
        rrf_k=60,
    )
    assert len(hybrid_results) > 0
    # Rank 1 must be the exact match
    assert "Interstellar" in hybrid_results[0].title
    assert hybrid_results[0].rrf_score is not None
    assert hybrid_results[0].sparse_rank == 1
    assert hybrid_results[0].dense_rank is not None


def test_pure_semantic_retrieval(hybrid_env):
    """Verify semantic queries without exact title keywords match correctly in Hybrid mode."""
    repo = hybrid_env["repository"]
    emb_service = hybrid_env["embedding_service"]
    bm25_service = hybrid_env["bm25_service"]

    # Conceptual query with no title word match
    query_str = "hilarious standup jokes and laughing with friends"
    dense_vec = emb_service.embed_text(query_str)
    sparse_vec = bm25_service.embed_query(query_str)

    hybrid_results, _ = repo.search_hybrid(
        query_vector=dense_vec,
        sparse_vector=sparse_vec,
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=5,
    )

    assert len(hybrid_results) > 0
    # Top results should be comedy
    assert any(r.category == "comedy" for r in hybrid_results[:3])


def test_pre_fusion_payload_filtering(hybrid_env):
    """Verify that structured filters are enforced inside Qdrant Edge before RRF fusion."""
    repo = hybrid_env["repository"]
    emb_service = hybrid_env["embedding_service"]
    bm25_service = hybrid_env["bm25_service"]

    query_str = "live show performance music"
    dense_vec = emb_service.embed_text(query_str)
    sparse_vec = bm25_service.embed_query(query_str)

    theatre_filter = SearchFilterParams(category="theatre")
    theatre_results, _ = repo.search_hybrid(
        query_vector=dense_vec,
        sparse_vector=sparse_vec,
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=5,
        filters=theatre_filter,
    )

    assert len(theatre_results) > 0
    assert all(r.category == "theatre" for r in theatre_results)


def test_api_modes_and_timing_breakdown(hybrid_api_client: TestClient):
    """Verify API endpoint supports mode='hybrid', 'dense', and 'sparse' with detailed timings."""
    # 1. Hybrid Mode
    res_hybrid = hybrid_api_client.post(
        "/search",
        json={"query": "outdoor cycling and fresh air", "mode": "hybrid", "limit": 3},
    )
    assert res_hybrid.status_code == 200
    data_h = res_hybrid.json()
    assert data_h["mode"] == "hybrid"
    assert len(data_h["results"]) == 3
    assert data_h["latency_ms"]["dense_embedding_ms"] is not None
    assert data_h["latency_ms"]["bm25_embedding_ms"] is not None
    assert data_h["latency_ms"]["fusion_ms"] is not None

    # Top result has RRF score
    top_h = data_h["results"][0]
    assert top_h["rrf_score"] is not None

    # 2. Dense Mode
    res_dense = hybrid_api_client.post(
        "/search",
        json={"query": "outdoor cycling and fresh air", "mode": "dense", "limit": 3},
    )
    assert res_dense.status_code == 200
    data_d = res_dense.json()
    assert data_d["mode"] == "dense"
    assert data_d["latency_ms"]["dense_embedding_ms"] > 0
    assert data_d["latency_ms"]["bm25_embedding_ms"] == 0.0

    # 3. Sparse Mode
    res_sparse = hybrid_api_client.post(
        "/search",
        json={"query": "Blade Runner 2049", "mode": "sparse", "limit": 3},
    )
    assert res_sparse.status_code == 200
    data_s = res_sparse.json()
    assert data_s["mode"] == "sparse"
    assert data_s["latency_ms"]["dense_embedding_ms"] == 0.0
    assert data_s["latency_ms"]["bm25_embedding_ms"] > 0
    assert "Blade Runner 2049" in data_s["results"][0]["title"]


def test_dual_vector_idempotency(hybrid_env):
    """Verify that multiple seeding runs preserve exactly 101 points with valid dual vectors."""
    repo = hybrid_env["repository"]
    settings = hybrid_env["settings"]
    service = hybrid_env["embedding_service"]

    # Re-seed over existing data
    seeded = seed_database(repo, settings, embedding_service=service, overwrite=True)
    assert seeded == 102
    assert repo.count() == 102

    # Check that retrieve preserves named vectors
    records = repo.shard.retrieve([1], with_payload=True, with_vector=True)
    assert len(records) == 1
    assert "dense" in records[0].vector
    assert "bm25" in records[0].vector
