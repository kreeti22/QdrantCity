from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SyncStatusEnum(str, Enum):
    """Possible synchronization states."""
    DISABLED = "disabled"
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class SyncChanges(BaseModel):
    """IDs of experiences added, updated, or deleted since catalog version."""
    added: List[int] = Field(default_factory=list, description="IDs of newly added experiences")
    updated: List[int] = Field(default_factory=list, description="IDs of updated experiences")
    deleted: List[int] = Field(default_factory=list, description="IDs of deleted experiences to prune")


class SyncManifest(BaseModel):
    """Server-side synchronization manifest detailing current catalog version and diff."""
    catalog_version: str = Field(..., description="Timestamp or monotonic version of central catalog")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    dataset_checksum: str = Field(..., description="SHA-256 or cryptographic hash of central dataset")
    total_items: int = Field(default=0, description="Total active items in central catalog")
    changes: SyncChanges = Field(default_factory=SyncChanges, description="Diff against requesting version")


class SyncCheckpoint(BaseModel):
    """Local checkpoint persisted to disk tracking sync progression and status."""
    catalog_version: Optional[str] = None
    dataset_checksum: Optional[str] = None
    last_successful_sync: Optional[str] = None
    last_attempted_sync: Optional[str] = None
    status: str = "idle"
    items_added: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    last_error: Optional[str] = None


class SyncStatusResponse(BaseModel):
    """Diagnostic response exposing local edge synchronization state."""
    enabled: bool = False
    status: str = "disabled"
    last_successful_sync: Optional[str] = None
    last_attempted_sync: Optional[str] = None
    catalog_version: Optional[str] = None
    dataset_checksum: Optional[str] = None
    items_added: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    last_error: Optional[str] = None


class SyncRunResult(BaseModel):
    """Detailed summary returned after an explicit or scheduled sync cycle."""
    ran: bool = False
    status: str = "idle"
    previous_version: Optional[str] = None
    new_version: Optional[str] = None
    added_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    duration_ms: float = 0.0
    message: str = ""
    error: Optional[str] = None
