import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config.settings import Settings, get_settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.bm25 import build_bm25_text, get_bm25_service
from app.embeddings.service import (
    EmbeddingService,
    build_embedding_text,
    get_embedding_service,
)
from app.models.experience import Experience, ExperiencePayload

logger = logging.getLogger("qdrant_edge.seed")


def load_seed_experiences(
    file_path: Path,
    embedding_service: Optional[EmbeddingService] = None,
    settings: Optional[Settings] = None,
) -> List[Experience]:
    """Loads raw experience JSON, validates schemas, and generates local FastEmbed and BM25 vectors."""
    app_settings = settings or get_settings()
    service = embedding_service or get_embedding_service(
        model_name=app_settings.embedding_model_name,
        dimension=app_settings.embedding_dimension,
        cache_dir=app_settings.embedding_cache_dir,
    )
    bm25_service = get_bm25_service()

    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Seed dataset file not found: {resolved_path}")

    with open(resolved_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    # 1. Parse payloads and construct semantic and lexical texts
    payloads: List[ExperiencePayload] = []
    semantic_texts: List[str] = []
    lexical_texts: List[str] = []
    item_ids: List[int] = []

    for item in raw_items:
        payload = ExperiencePayload(**item)
        semantic_text = build_embedding_text(payload)
        lexical_text = build_bm25_text(payload)
        payloads.append(payload)
        semantic_texts.append(semantic_text)
        lexical_texts.append(lexical_text)
        item_ids.append(item["id"])

    # 2. Batch-embed semantic texts locally via FastEmbed
    logger.info(f"Generating local dense embeddings for {len(semantic_texts)} experiences with '{service.model_name}'...")
    dense_vectors = service.embed_texts(semantic_texts, batch_size=32)

    # 3. Generate BM25 sparse vectors via native Qdrant Edge Bm25
    logger.info(f"Generating native BM25 sparse vectors for {len(lexical_texts)} experiences...")
    sparse_vectors = [bm25_service.embed_document(t) for t in lexical_texts]

    # 4. Assemble Experience instances with dual vectors
    experiences: List[Experience] = []
    for exp_id, vector, sparse_vec, payload in zip(item_ids, dense_vectors, sparse_vectors, payloads):
        if len(vector) != app_settings.vector_size:
            raise ValueError(
                f"Generated vector length {len(vector)} does not match configured vector size {app_settings.vector_size}"
            )
        experiences.append(
            Experience(
                id=exp_id,
                vector=vector,
                sparse_vector=sparse_vec,
                payload=payload,
            )
        )

    return experiences


def seed_database(
    repository: ExperienceRepository,
    settings: Settings,
    embedding_service: Optional[EmbeddingService] = None,
    overwrite: bool = False,
) -> int:
    """Seeds the Qdrant Edge collection with city experiences using dual dense + BM25 sparse vectors."""
    current_count = repository.count()
    if current_count > 0 and not overwrite:
        logger.info(f"Collection '{settings.collection_name}' already contains {current_count} points. Skipping seed.")
        return 0

    experiences = load_seed_experiences(
        settings.seed_data_path,
        embedding_service=embedding_service,
        settings=settings,
    )
    count = repository.upsert_experiences(experiences)
    logger.info(f"Seeded {count} experiences into collection '{settings.collection_name}' at {settings.full_collection_path}")
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repo = ExperienceRepository(shard, client, settings)
    seed_database(repo, settings, overwrite=True)
    client.close()
