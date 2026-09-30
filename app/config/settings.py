import json
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration for QdrantCinema Edge with Local FastEmbed."""

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_EDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QdrantCinema Edge Platform"
    app_version: str = "0.6.0"
    debug: bool = False
    environment: str = "development"

    # Server deployment settings
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: Union[List[str], str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if not v_trimmed:
                return ["*"]
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            origins = [origin.strip() for origin in v_trimmed.split(",") if origin.strip()]
            return origins if origins else ["*"]
        elif isinstance(v, (list, tuple)):
            return list(v)
        return ["*"]

    @field_validator("port", mode="before")
    @classmethod
    def validate_port(cls, v: Any) -> int:
        port = int(v)
        if not (1 <= port <= 65535):
            raise ValueError(f"port must be between 1 and 65535, got {port}")
        return port

    # Search constraints
    max_query_length: int = 500

    # Storage paths
    edge_storage_path: Path = Path("data/edge")
    collection_name: str = "city_experiences"
    user_memory_path: Path = Path("data/memory/user_memory.db")
    default_user_id: str = "local-default"
    enable_personalization: bool = True
    personalization_boost_weight: float = 0.20

    @field_validator("personalization_boost_weight", mode="before")
    @classmethod
    def validate_boost_weight(cls, v: Any) -> float:
        val = float(v)
        if not (0.0 <= val <= 1.0):
            raise ValueError(
                f"personalization_boost_weight must be between 0.0 and 1.0, got {val}"
            )
        return val

    # Phase 2D: Edge-to-Server Synchronization Settings
    sync_enabled: bool = False
    sync_server_url: Optional[str] = None
    sync_interval_seconds: int = 3600
    sync_timeout_seconds: float = 10.0
    sync_batch_size: int = 50
    sync_max_items_per_run: int = 500
    sync_api_key: Optional[str] = None
    sync_checkpoint_path: Path = Path("data/sync/sync_checkpoint.json")

    @field_validator("sync_interval_seconds", mode="before")
    @classmethod
    def validate_sync_interval(cls, v: Any) -> int:
        val = int(v)
        if val < 30:
            raise ValueError(
                f"sync_interval_seconds must be at least 30 seconds, got {val}"
            )
        return val

    @field_validator("sync_batch_size", mode="before")
    @classmethod
    def validate_sync_batch_size(cls, v: Any) -> int:
        val = int(v)
        if not (1 <= val <= 1000):
            raise ValueError(
                f"sync_batch_size must be between 1 and 1000, got {val}"
            )
        return val

    # Phase 3: Production Hardening
    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" | "json"

    # Rate limiting (disabled by default — set max_requests > 0 to enable)
    rate_limit_search_enabled: bool = False
    rate_limit_search_requests: int = 60    # requests per window
    rate_limit_search_window_seconds: float = 60.0
    rate_limit_sync_enabled: bool = False
    rate_limit_sync_requests: int = 10
    rate_limit_sync_window_seconds: float = 60.0

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> str:
        level = str(v).upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in valid:
            raise ValueError(f"log_level must be one of {valid}, got '{v}'")
        return level

    # Timezone & Clock Configuration (Phase 1D Centralized Time)
    timezone: str = "UTC"
    reference_datetime: Optional[str] = "2026-10-15T12:00:00Z"
    default_currency: str = "USD"
    enable_query_understanding: bool = True

    # Local embedding configuration (FastEmbed)
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_model_version: str = "1.5"
    embedding_dimension: int = 384
    embedding_cache_dir: Optional[Path] = None

    # Vector specification for Qdrant Edge
    vector_size: int = 384
    vector_distance: str = "Cosine"
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "bm25"

    # Hybrid Retrieval and RRF Fusion
    rrf_k: int = 60
    dense_top_k: int = 20
    bm25_top_k: int = 20
    final_top_k: int = 10

    # Ingestion seed
    seed_data_path: Path = Path("data/seed/experiences.json")
    auto_seed_on_startup: bool = True

    @property
    def full_collection_path(self) -> Path:
        """Returns the full filesystem path for the collection shard."""
        return (self.edge_storage_path / self.collection_name).resolve()


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()
