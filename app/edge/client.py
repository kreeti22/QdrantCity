import logging
import threading
from pathlib import Path
from typing import Dict, Optional

import importlib.metadata
from qdrant_edge import EdgeConfig, EdgeShard

logger = logging.getLogger("qdrant_edge.client")


class EdgeClient:
    """In-process client managing local Qdrant Edge shards and lifecycles."""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._shards: Dict[str, EdgeShard] = {}
        self._lock = threading.Lock()
        self._version = self._detect_version()

    @staticmethod
    def _detect_version() -> str:
        try:
            return importlib.metadata.version("qdrant-edge-py")
        except Exception:
            return "0.8.0"

    @property
    def version(self) -> str:
        """Returns the installed qdrant-edge-py package version."""
        return self._version

    def get_collection_path(self, collection_name: str) -> Path:
        """Computes the on-disk directory for a specific collection shard."""
        return (self.storage_path / collection_name).resolve()

    def is_shard_persisted(self, collection_name: str) -> bool:
        """Checks if a shard directory already contains initialized Edge storage."""
        shard_dir = self.get_collection_path(collection_name)
        return (shard_dir / "edge_config.json").exists()

    def get_or_create_shard(self, collection_name: str, config: EdgeConfig) -> EdgeShard:
        """Returns an open EdgeShard instance, creating it if not present, or loading from disk."""
        with self._lock:
            if collection_name in self._shards:
                return self._shards[collection_name]

            shard_dir = self.get_collection_path(collection_name)
            shard_dir.mkdir(parents=True, exist_ok=True)

            if (shard_dir / "edge_config.json").exists():
                logger.info(f"Opening existing Qdrant Edge shard at {shard_dir}")
                shard = EdgeShard.load(str(shard_dir))
            else:
                logger.info(f"Initializing new Qdrant Edge shard at {shard_dir}")
                shard = EdgeShard.create(str(shard_dir), config)

            self._shards[collection_name] = shard
            return shard

    def get_shard(self, collection_name: str) -> Optional[EdgeShard]:
        """Retrieves a currently opened EdgeShard instance."""
        with self._lock:
            return self._shards.get(collection_name)

    def flush_all(self) -> None:
        """Flushes in-memory segment WALs to disk across all active shards."""
        with self._lock:
            for name, shard in self._shards.items():
                try:
                    shard.flush()
                except Exception as e:
                    logger.error(f"Error flushing shard {name}: {e}")

    def close(self) -> None:
        """Gracefully flushes and closes all open EdgeShard instances."""
        with self._lock:
            for name, shard in list(self._shards.items()):
                try:
                    logger.info(f"Closing Qdrant Edge shard '{name}'")
                    shard.flush()
                    shard.close()
                except Exception as e:
                    logger.warning(f"Error closing shard {name}: {e}")
            self._shards.clear()
