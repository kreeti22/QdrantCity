import json
import logging
import os
from pathlib import Path
import threading
from typing import Optional

from app.sync.models import SyncCheckpoint

logger = logging.getLogger("qdrant_edge.sync.repository")


class SyncRepository:
    """Local repository managing durable sync checkpoint persistence."""

    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get_checkpoint(self) -> SyncCheckpoint:
        """Loads checkpoint from local disk, or returns default if not found."""
        with self._lock:
            if not self.checkpoint_path.exists():
                return SyncCheckpoint()
            try:
                data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                return SyncCheckpoint(**data)
            except Exception as e:
                logger.warning(f"Failed to read sync checkpoint at {self.checkpoint_path}: {e}. Returning default.")
                return SyncCheckpoint()

    def save_checkpoint(self, checkpoint: SyncCheckpoint) -> None:
        """Atomically saves checkpoint to disk via temporary swap file."""
        with self._lock:
            try:
                tmp_path = self.checkpoint_path.with_suffix(".tmp")
                content = checkpoint.model_dump_json(indent=2)
                tmp_path.write_text(content, encoding="utf-8")
                # Atomic file replacement
                os.replace(str(tmp_path), str(self.checkpoint_path))
                logger.debug(f"Saved sync checkpoint: version={checkpoint.catalog_version}, status={checkpoint.status}")
            except Exception as e:
                logger.error(f"Failed to save sync checkpoint at {self.checkpoint_path}: {e}")

    def update_status(
        self,
        status: str,
        error: Optional[str] = None,
        attempted_at: Optional[str] = None,
    ) -> SyncCheckpoint:
        """Updates transient status of checkpoint and persists."""
        checkpoint = self.get_checkpoint()
        checkpoint.status = status
        if error is not None:
            checkpoint.last_error = error
        if attempted_at is not None:
            checkpoint.last_attempted_sync = attempted_at
        self.save_checkpoint(checkpoint)
        return checkpoint

    def reset_checkpoint(self) -> None:
        """Clears local checkpoint state."""
        with self._lock:
            try:
                if self.checkpoint_path.exists():
                    self.checkpoint_path.unlink()
            except Exception as e:
                logger.error(f"Failed to reset sync checkpoint: {e}")
