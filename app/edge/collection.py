import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeSparseVectorParams,
    EdgeVectorParams,
    PayloadSchemaType,
    UpdateOperation,
)
from app.config.settings import Settings
from app.edge.client import EdgeClient

logger = logging.getLogger("qdrant_edge.collection")

METADATA_FILENAME = "embedding_metadata.json"


class CollectionDimensionMismatchError(Exception):
    """Raised when on-disk EdgeShard vector schema or dimension does not match configured models."""
    pass


def parse_distance(distance_name: str) -> Distance:
    """Maps configured distance string to Qdrant Edge Distance enum."""
    dist_upper = distance_name.strip().upper()
    if dist_upper == "COSINE":
        return Distance.Cosine
    elif dist_upper in ("EUCLID", "EUCLIDEAN"):
        return Distance.Euclid
    elif dist_upper == "DOT":
        return Distance.Dot
    elif dist_upper in ("MANHATTAN"):
        return Distance.Manhattan
    else:
        logger.warning(f"Unknown distance '{distance_name}', defaulting to Cosine")
        return Distance.Cosine


def build_collection_config(settings: Settings) -> EdgeConfig:
    """Builds EdgeConfig using application settings with named dense and BM25 sparse vectors."""
    distance = parse_distance(settings.vector_distance)
    dense_params = EdgeVectorParams(
        size=settings.vector_size,
        distance=distance,
    )
    sparse_params = EdgeSparseVectorParams()
    return EdgeConfig(
        vectors={settings.dense_vector_name: dense_params},
        sparse_vectors={settings.sparse_vector_name: sparse_params},
    )


def detect_collection_dimension(shard_dir: Path) -> Optional[int]:
    """Reads edge_config.json from shard directory to detect existing vector dimension."""
    config_file = shard_dir / "edge_config.json"
    if not config_file.exists():
        return None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        vectors = data.get("vectors", {})
        for _, v in vectors.items():
            if isinstance(v, dict) and "size" in v:
                return int(v["size"])
    except Exception as e:
        logger.warning(f"Could not parse edge_config.json at {shard_dir}: {e}")

    return None


def detect_collection_named_vectors(shard_dir: Path) -> List[str]:
    """Reads edge_config.json to detect existing named dense vectors."""
    config_file = shard_dir / "edge_config.json"
    if not config_file.exists():
        return []

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        vectors = data.get("vectors", {})
        if isinstance(vectors, dict):
            return list(vectors.keys())
    except Exception as e:
        logger.warning(f"Could not parse vectors in edge_config.json at {shard_dir}: {e}")

    return []


def detect_collection_sparse_vectors(shard_dir: Path) -> List[str]:
    """Reads edge_config.json to detect existing configured sparse vectors."""
    config_file = shard_dir / "edge_config.json"
    if not config_file.exists():
        return []

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        sparse_vectors = data.get("sparse_vectors", {})
        if isinstance(sparse_vectors, dict):
            return list(sparse_vectors.keys())
    except Exception as e:
        logger.warning(f"Could not parse sparse_vectors in edge_config.json at {shard_dir}: {e}")

    return []


def read_embedding_metadata(shard_dir: Path) -> Optional[Dict[str, Any]]:
    """Reads stored embedding metadata from collection directory."""
    meta_file = shard_dir / METADATA_FILENAME
    if not meta_file.exists():
        return None
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read {meta_file}: {e}")
        return None


def write_embedding_metadata(shard_dir: Path, settings: Settings) -> None:
    """Writes active embedding and sparse model metadata alongside collection storage."""
    meta_file = shard_dir / METADATA_FILENAME
    meta_content = {
        "embedding_model_name": settings.embedding_model_name,
        "embedding_model_version": settings.embedding_model_version,
        "embedding_dimension": settings.embedding_dimension,
        "vector_size": settings.vector_size,
        "vector_distance": settings.vector_distance,
        "dense_vector_name": settings.dense_vector_name,
        "sparse_vector_name": settings.sparse_vector_name,
        "phase": "Phase 1C",
    }
    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_content, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write {meta_file}: {e}")


def setup_payload_indexes(shard: EdgeShard) -> None:
    """Applies payload schema indexes to the shard for fast structured filtering."""
    index_definitions = [
        ("category", PayloadSchemaType.Keyword),
        ("city", PayloadSchemaType.Keyword),
        ("neighborhood", PayloadSchemaType.Keyword),
        ("venue", PayloadSchemaType.Keyword),
        ("subcategories", PayloadSchemaType.Keyword),
        ("price", PayloadSchemaType.Float),
        ("is_indoor", PayloadSchemaType.Integer),
        ("rating", PayloadSchemaType.Float),
        ("start_time", PayloadSchemaType.Datetime),
        ("end_time", PayloadSchemaType.Datetime),
    ]

    for field_name, schema_type in index_definitions:
        try:
            shard.update(UpdateOperation.create_field_index(field_name, schema_type))
        except Exception as e:
            logger.warning(f"Could not create field index for '{field_name}': {e}")


def initialize_experience_collection(client: EdgeClient, settings: Settings) -> EdgeShard:
    """Initializes or loads the experience collection shard, validating schema and dimension compatibility."""
    shard_dir = client.get_collection_path(settings.collection_name)

    # Incompatibility check for existing storage
    if (shard_dir / "edge_config.json").exists():
        stored_dim = detect_collection_dimension(shard_dir)
        named_vectors = detect_collection_named_vectors(shard_dir)
        sparse_vectors = detect_collection_sparse_vectors(shard_dir)

        mismatch_reasons = []
        if stored_dim is not None and stored_dim != settings.vector_size:
            mismatch_reasons.append(f"dimension mismatch (stored {stored_dim} vs expected {settings.vector_size})")

        if settings.dense_vector_name not in named_vectors:
            mismatch_reasons.append(f"missing dense vector '{settings.dense_vector_name}' (found: {named_vectors})")

        if settings.sparse_vector_name not in sparse_vectors:
            mismatch_reasons.append(f"missing sparse vector '{settings.sparse_vector_name}' (found: {sparse_vectors})")

        if mismatch_reasons:
            stored_meta = read_embedding_metadata(shard_dir)
            prev_phase = stored_meta.get("phase") if stored_meta else "Phase 1B or earlier"
            raise CollectionDimensionMismatchError(
                f"Collection '{settings.collection_name}' at {shard_dir} is incompatible with Phase 1C dual vectors: "
                f"{'; '.join(mismatch_reasons)} ({prev_phase}). "
                f"Run explicit migration with: python -m app.edge.migration --reset"
            )

    config = build_collection_config(settings)
    shard = client.get_or_create_shard(settings.collection_name, config)
    write_embedding_metadata(shard_dir, settings)
    setup_payload_indexes(shard)
    return shard


def get_shard_diagnostics(shard: EdgeShard) -> Dict[str, Any]:
    """Extracts diagnostic metrics and metadata from an active EdgeShard."""
    info = shard.info()
    return {
        "points_count": getattr(info, "points_count", 0),
        "segments_count": getattr(info, "segments_count", 0),
        "indexed_vectors_count": getattr(info, "indexed_vectors_count", 0),
        "payload_schema": list(getattr(info, "payload_schema", {}).keys()),
    }
