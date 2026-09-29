import argparse
import datetime
import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple

from app.config.settings import Settings, get_settings
from app.edge.client import EdgeClient
from app.edge.collection import (
    CollectionDimensionMismatchError,
    detect_collection_dimension,
    detect_collection_named_vectors,
    detect_collection_sparse_vectors,
    initialize_experience_collection,
    read_embedding_metadata,
)
from app.edge.repository import ExperienceRepository
from app.ingestion.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("qdrant_edge.migration")


def check_collection_compatibility(settings: Settings) -> Tuple[bool, Optional[str]]:
    """Checks whether the on-disk collection matches the Phase 1C dual vector schema."""
    shard_dir = settings.full_collection_path
    if not (shard_dir / "edge_config.json").exists():
        return True, "No existing collection found. A new one will be created on initialization."

    stored_dim = detect_collection_dimension(shard_dir)
    named_vectors = detect_collection_named_vectors(shard_dir)
    sparse_vectors = detect_collection_sparse_vectors(shard_dir)
    stored_meta = read_embedding_metadata(shard_dir)
    prev_phase = stored_meta.get("phase") if stored_meta else "Phase 1B or earlier"

    reasons = []
    if stored_dim != settings.vector_size:
        reasons.append(f"Dimension mismatch: on-disk dimension {stored_dim} != configured {settings.vector_size}")

    if settings.dense_vector_name not in named_vectors:
        reasons.append(f"Missing dense vector '{settings.dense_vector_name}' (found: {named_vectors})")

    if settings.sparse_vector_name not in sparse_vectors:
        reasons.append(f"Missing sparse vector '{settings.sparse_vector_name}' (found: {sparse_vectors})")

    if reasons:
        return False, (
            f"Schema mismatch: Collection at {shard_dir} ({prev_phase}) requires migration: "
            f"{'; '.join(reasons)}. Run explicit migration with: python -m app.edge.migration --reset"
        )

    return True, f"Compatible: Shard supports dual vectors ('{settings.dense_vector_name}' + '{settings.sparse_vector_name}')."


def migrate_collection(settings: Settings, backup: bool = True) -> int:
    """Explicitly archives any incompatible shard, creates a new collection, and re-seeds it."""
    shard_dir = settings.full_collection_path

    if shard_dir.exists():
        if backup:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = settings.edge_storage_path / "backups" / f"{settings.collection_name}_{timestamp}"
            backup_dir.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Backing up existing shard from {shard_dir} to {backup_dir}")
            shutil.copytree(shard_dir, backup_dir)
            logger.info(f"Backup preserved at: {backup_dir}")

        logger.info(f"Removing old shard at {shard_dir}")
        shutil.rmtree(shard_dir)

    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repository = ExperienceRepository(shard, client, settings)

    logger.info(f"Re-seeding collection '{settings.collection_name}' with local FastEmbed and BM25 vectors...")
    seeded_count = seed_database(repository, settings, overwrite=True)
    logger.info(f"Migration complete: {seeded_count} points seeded into {shard_dir}")

    client.close()
    return seeded_count


def main():
    parser = argparse.ArgumentParser(description="Qdrant Edge Collection Migration Tool")
    parser.add_argument("--check", action="store_true", help="Check collection compatibility without making changes")
    parser.add_argument("--reset", action="store_true", help="Reset/migrate collection to active dual vector schema")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup before reset")
    args = parser.parse_args()

    settings = get_settings()

    if args.check:
        compatible, msg = check_collection_compatibility(settings)
        print(f"[{'OK' if compatible else 'INCOMPATIBLE'}] {msg}")
        return 0 if compatible else 1

    if args.reset:
        print(f"Starting explicit migration for collection '{settings.collection_name}'...")
        migrate_collection(settings, backup=not args.no_backup)
        print("Migration and re-seeding finished successfully.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
