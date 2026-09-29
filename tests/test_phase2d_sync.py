import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database
from app.main import create_app
from app.models.experience import Experience, ExperiencePayload
from app.sync.client import SyncClient
from app.sync.models import (
    SyncChanges,
    SyncCheckpoint,
    SyncManifest,
    SyncRunResult,
    SyncStatusEnum,
    SyncStatusResponse,
)
from app.sync.repository import SyncRepository
from app.sync.service import SyncService


# Sample valid experience fixture for sync
SAMPLE_EXPERIENCE_DICT = {
    "id": 1001,
    "title": "Neon Cyberpunk Film Marathon",
    "category": "movies",
    "subcategories": ["sci-fi", "cyberpunk", "retro"],
    "description": "All-night 35mm screening of iconic cyberpunk cinema with synthwave DJ sets.",
    "venue": "The Roxie Cinema",
    "neighborhood": "Mission",
    "city": "San Francisco",
    "price": 32.0,
    "currency": "USD",
    "is_indoor": True,
    "rating": 4.8,
    "start_time": "2026-10-20T21:00:00Z",
    "end_time": "2026-10-21T05:00:00Z",
}


@pytest.fixture
def sync_test_env(tmp_path: Path):
    """Sets up an isolated Qdrant Edge shard, embedding service, and sync repo."""
    edge_dir = tmp_path / "sync_edge"
    settings = Settings(
        edge_storage_path=edge_dir,
        collection_name="sync_test_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        user_memory_path=tmp_path / "user_memory.db",
        sync_enabled=True,
        sync_server_url="http://mock-server.local",
        sync_checkpoint_path=tmp_path / "sync_checkpoint.json",
        sync_batch_size=2,
    )
    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repository = ExperienceRepository(shard, client, settings)
    emb_service = get_embedding_service(
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )
    seed_database(repository, settings, embedding_service=emb_service)

    sync_repo = SyncRepository(settings.sync_checkpoint_path)
    mock_client = MagicMock(spec=SyncClient)
    sync_service = SyncService(
        sync_repo=sync_repo,
        sync_client=mock_client,
        experience_repo=repository,
        embedding_service=emb_service,
        settings=settings,
    )
    return {
        "settings": settings,
        "repo": repository,
        "emb_service": emb_service,
        "sync_repo": sync_repo,
        "sync_client": mock_client,
        "sync_service": sync_service,
        "tmp_path": tmp_path,
    }


# 1. Manifest parsing
def test_1_manifest_parsing():
    raw_json = {
        "catalog_version": "2026-10-20T12:00:00Z",
        "generated_at": "2026-10-20T12:00:01Z",
        "dataset_checksum": "abc123def456",
        "total_items": 120,
        "changes": {
            "added": [101, 102],
            "updated": [14, 27],
            "deleted": [55, 61],
        },
    }
    manifest = SyncManifest(**raw_json)
    assert manifest.catalog_version == "2026-10-20T12:00:00Z"
    assert manifest.dataset_checksum == "abc123def456"
    assert manifest.total_items == 120
    assert manifest.changes.added == [101, 102]
    assert manifest.changes.updated == [14, 27]
    assert manifest.changes.deleted == [55, 61]


# 2. Version comparison & no-op sync
def test_2_version_comparison_and_noop(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    repo = sync_test_env["sync_repo"]

    # Pre-populate checkpoint
    repo.save_checkpoint(
        SyncCheckpoint(
            catalog_version="v1.0",
            dataset_checksum="hash-111",
            status="success",
        )
    )

    # Server returns identical version and checksum
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v1.0",
            generated_at="2026-10-15T12:00:00Z",
            dataset_checksum="hash-111",
            total_items=115,
            changes=SyncChanges(),
        ),
        None,
    )

    result = service.run_sync()
    assert result.ran is True
    assert result.status == "success"
    assert "up to date" in result.message.lower()
    client.fetch_experiences.assert_not_called()


# 3. Empty diff sync
def test_3_empty_diff_sync(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    repo = sync_test_env["sync_repo"]

    # New version, but 0 changes
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.0",
            generated_at="2026-10-16T12:00:00Z",
            dataset_checksum="hash-222",
            total_items=115,
            changes=SyncChanges(),
        ),
        None,
    )

    result = service.run_sync()
    assert result.ran is True
    assert result.status == "success"
    assert result.new_version == "v2.0"
    assert repo.get_checkpoint().catalog_version == "v2.0"


# 4. Added experience synchronization
def test_4_added_experience_synchronization(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    exp_repo = sync_test_env["repo"]

    initial_count = exp_repo.count()

    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.1",
            generated_at="2026-10-17T12:00:00Z",
            dataset_checksum="hash-added",
            total_items=initial_count + 1,
            changes=SyncChanges(added=[1001]),
        ),
        None,
    )
    client.fetch_experiences.return_value = ([SAMPLE_EXPERIENCE_DICT], None)

    result = service.run_sync()
    assert result.ran is True
    assert result.status == "success"
    assert result.added_count == 1
    assert exp_repo.count() == initial_count + 1

    item = exp_repo.get_by_id(1001)
    assert item is not None
    assert item.title == "Neon Cyberpunk Film Marathon"


# 5. Updated experience synchronization
def test_5_updated_experience_synchronization(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    exp_repo = sync_test_env["repo"]

    initial_count = exp_repo.count()

    # Modify experience ID 1
    updated_exp_1 = dict(SAMPLE_EXPERIENCE_DICT)
    updated_exp_1["id"] = 1
    updated_exp_1["title"] = "Interstellar: Ultimate 70mm IMAX Revival"

    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.2",
            generated_at="2026-10-18T12:00:00Z",
            dataset_checksum="hash-updated",
            total_items=initial_count,
            changes=SyncChanges(updated=[1]),
        ),
        None,
    )
    client.fetch_experiences.return_value = ([updated_exp_1], None)

    result = service.run_sync()
    assert result.status == "success"
    assert result.updated_count == 1
    assert exp_repo.count() == initial_count  # Count must remain unchanged

    item = exp_repo.get_by_id(1)
    assert item is not None
    assert item.title == "Interstellar: Ultimate 70mm IMAX Revival"


# 6. Deleted experience synchronization
def test_6_deleted_experience_synchronization(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    exp_repo = sync_test_env["repo"]

    initial_count = exp_repo.count()
    assert exp_repo.get_by_id(2) is not None

    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.3",
            generated_at="2026-10-19T12:00:00Z",
            dataset_checksum="hash-deleted",
            total_items=initial_count - 1,
            changes=SyncChanges(deleted=[2]),
        ),
        None,
    )

    result = service.run_sync()
    assert result.status == "success"
    assert result.deleted_count == 1
    assert exp_repo.count() == initial_count - 1
    assert exp_repo.get_by_id(2) is None


# 7. Incremental sync without full reindex
def test_7_incremental_sync_without_full_reindex(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    emb_service = sync_test_env["emb_service"]

    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.4",
            generated_at="2026-10-20T12:00:00Z",
            dataset_checksum="hash-inc",
            total_items=116,
            changes=SyncChanges(added=[1002]),
        ),
        None,
    )
    new_item = dict(SAMPLE_EXPERIENCE_DICT)
    new_item["id"] = 1002
    client.fetch_experiences.return_value = ([new_item], None)

    with patch.object(emb_service, "embed_texts", wraps=emb_service.embed_texts) as mock_embed:
        result = service.run_sync()
        assert result.status == "success"
        # Only the 1 new item should be embedded, NOT all 115+ items
        mock_embed.assert_called_once()
        args, _ = mock_embed.call_args
        assert len(args[0]) == 1


# 8. Batch processing
def test_8_batch_processing(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    service.settings.sync_batch_size = 2  # Batch size = 2

    # 5 added IDs: [1003, 1004, 1005, 1006, 1007]
    five_ids = [1003, 1004, 1005, 1006, 1007]
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.5",
            generated_at="2026-10-21T12:00:00Z",
            dataset_checksum="hash-batch",
            total_items=120,
            changes=SyncChanges(added=five_ids),
        ),
        None,
    )

    def side_effect_fetch(batch_ids):
        items = []
        for b_id in batch_ids:
            it = dict(SAMPLE_EXPERIENCE_DICT)
            it["id"] = b_id
            items.append(it)
        return items, None

    client.fetch_experiences.side_effect = side_effect_fetch

    result = service.run_sync()
    assert result.status == "success"
    assert result.added_count == 5
    # For 5 items with batch size 2: ceil(5/2) = 3 calls
    assert client.fetch_experiences.call_count == 3


# 9. Sync checkpoint persistence
def test_9_sync_checkpoint_persistence(tmp_path: Path):
    chk_path = tmp_path / "persist_chk.json"
    repo1 = SyncRepository(chk_path)
    chk1 = SyncCheckpoint(
        catalog_version="v-persisted",
        dataset_checksum="chk-hash-999",
        status="success",
        items_added=4,
    )
    repo1.save_checkpoint(chk1)

    # Reopen from fresh instance
    repo2 = SyncRepository(chk_path)
    chk2 = repo2.get_checkpoint()
    assert chk2.catalog_version == "v-persisted"
    assert chk2.dataset_checksum == "chk-hash-999"
    assert chk2.status == "success"
    assert chk2.items_added == 4


# 10. Failed sync does not advance checkpoint
def test_10_failed_sync_does_not_advance_checkpoint(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    repo = sync_test_env["sync_repo"]

    # Initial checkpoint is v1.0
    repo.save_checkpoint(SyncCheckpoint(catalog_version="v1.0", status="success"))

    # Manifest offers v2.0
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v2.0",
            generated_at="2026-10-22T12:00:00Z",
            dataset_checksum="hash-fail",
            total_items=116,
            changes=SyncChanges(added=[2001]),
        ),
        None,
    )
    # Experience download fails
    client.fetch_experiences.return_value = ([], "500 Server Internal Error")

    result = service.run_sync()
    assert result.status == "failed"
    assert "500" in result.error

    # Checkpoint must NOT advance to v2.0
    chk = repo.get_checkpoint()
    assert chk.catalog_version == "v1.0"
    assert chk.status == "failed"
    assert "500" in chk.last_error


# 11. Retry after failure
def test_11_retry_after_failure(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    repo = sync_test_env["sync_repo"]

    # First attempt: failure
    client.fetch_manifest.return_value = (None, "Connection refused")
    res1 = service.run_sync()
    assert res1.status == "failed"

    # Second attempt: recovery
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v3.0",
            generated_at="2026-10-23T12:00:00Z",
            dataset_checksum="hash-retry",
            total_items=115,
            changes=SyncChanges(),
        ),
        None,
    )
    res2 = service.run_sync()
    assert res2.status == "success"
    assert repo.get_checkpoint().catalog_version == "v3.0"


# 12. Idempotent repeated sync
def test_12_idempotent_repeated_sync(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]
    exp_repo = sync_test_env["repo"]

    manifest = SyncManifest(
        catalog_version="v4.0",
        generated_at="2026-10-24T12:00:00Z",
        dataset_checksum="hash-idempotent",
        total_items=116,
        changes=SyncChanges(added=[3001]),
    )
    new_item = dict(SAMPLE_EXPERIENCE_DICT)
    new_item["id"] = 3001

    client.fetch_manifest.return_value = (manifest, None)
    client.fetch_experiences.return_value = ([new_item], None)

    # Run 1
    res1 = service.run_sync()
    assert res1.status == "success"
    count1 = exp_repo.count()

    # Run 2 with force=True
    res2 = service.run_sync(force=True)
    assert res2.status == "success"
    count2 = exp_repo.count()

    # Shard count must not duplicate
    assert count1 == count2
    assert exp_repo.get_by_id(3001) is not None


# 13. Server timeout handling
def test_13_server_timeout_handling():
    client = SyncClient(server_url="http://192.0.2.1:81", timeout_seconds=0.01)
    manifest, err = client.fetch_manifest()
    assert manifest is None
    assert err is not None
    assert "timeout" in err.lower() or "error" in err.lower()
    client.close()


# 14. Malformed server response handling
def test_14_malformed_server_response_handling(sync_test_env):
    service = sync_test_env["sync_service"]
    client = sync_test_env["sync_client"]

    # Manifest with invalid changes structure
    client.fetch_manifest.return_value = (None, "Malformed manifest response: Missing required field")
    result = service.run_sync()
    assert result.status == "failed"
    assert "Malformed" in result.error


# 15. Disabled synchronization
def test_15_disabled_synchronization(sync_test_env):
    service = sync_test_env["sync_service"]
    service.settings.sync_enabled = False

    result = service.run_sync()
    assert result.ran is False
    assert result.status == "disabled"
    assert "disabled" in result.message.lower()


# --- FastAPI TestClient Integration Tests ---

@pytest.fixture
def api_client(tmp_path: Path):
    """Provides a TestClient initialized with Qdrant Edge and sync configuration."""
    test_settings = Settings(
        edge_storage_path=tmp_path / "api_sync_edge",
        collection_name="api_sync_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        user_memory_path=tmp_path / "api_user_memory.db",
        sync_enabled=True,
        sync_server_url="http://mock-sync.app",
        sync_checkpoint_path=tmp_path / "api_sync_checkpoint.json",
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


# 16. Manual sync endpoint API
def test_16_manual_sync_endpoint_api(api_client: TestClient):
    # Mock sync client on app.state
    sync_service: SyncService = api_client.app.state.sync_service
    sync_service.client = MagicMock(spec=SyncClient)
    sync_service.client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v-api-1",
            generated_at="2026-10-15T12:00:00Z",
            dataset_checksum="hash-api",
            total_items=115,
            changes=SyncChanges(),
        ),
        None,
    )

    res = api_client.post("/api/sync/run")
    assert res.status_code == 200
    data = res.json()
    assert data["ran"] is True
    assert data["status"] == "success"
    assert data["new_version"] == "v-api-1"


# 17. Sync status endpoint API
def test_17_sync_status_endpoint_api(api_client: TestClient):
    res = api_client.get("/api/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert "status" in data
    assert "last_successful_sync" in data


# 18. Startup remains operational when server unavailable
def test_18_startup_remains_operational_when_server_unavailable(tmp_path: Path):
    test_settings = Settings(
        edge_storage_path=tmp_path / "offline_sync_edge",
        collection_name="offline_sync_experiences",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        vector_distance="Cosine",
        seed_data_path=Path("data/seed/experiences.json"),
        auto_seed_on_startup=True,
        timezone="UTC",
        reference_datetime="2026-10-15T12:00:00Z",
        enable_query_understanding=True,
        user_memory_path=tmp_path / "offline_user_memory.db",
        sync_enabled=True,
        sync_server_url="http://127.0.0.1:59999",  # Non-existent server
        sync_checkpoint_path=tmp_path / "offline_sync_checkpoint.json",
    )
    app = create_app(test_settings)
    with TestClient(app) as client:
        # 1. Probes must be operational
        assert client.get("/live").status_code == 200
        assert client.get("/ready").status_code == 200
        assert client.get("/health").status_code == 200

        # 2. Local search must remain functional
        search_res = client.post("/api/experiences/search", json={"query": "comedy", "limit": 3})
        assert search_res.status_code == 200
        assert len(search_res.json()["results"]) > 0


# 19. Search remains operational after sync failure
def test_19_search_remains_operational_after_sync_failure(api_client: TestClient):
    sync_service: SyncService = api_client.app.state.sync_service
    sync_service.client = MagicMock(spec=SyncClient)
    sync_service.client.fetch_manifest.return_value = (None, "503 Service Unavailable")

    # Run failed sync
    sync_res = api_client.post("/api/sync/run")
    assert sync_res.status_code == 200
    assert sync_res.json()["status"] == "failed"

    # Search remains fully functional
    search_res = api_client.post("/api/experiences/search", json={"query": "concerts", "limit": 2})
    assert search_res.status_code == 200
    assert len(search_res.json()["results"]) > 0


# 20. User memory is never included in synchronization
def test_20_user_memory_is_never_included_in_synchronization(sync_test_env):
    """Guarantees user bookmarks, interactions, and preferences are excluded from sync."""
    client = sync_test_env["sync_client"]
    service = sync_test_env["sync_service"]

    # Manifest schema check
    manifest_fields = SyncManifest.model_fields.keys()
    for sensitive_field in ["user_id", "bookmarks", "interactions", "preferences", "history"]:
        assert sensitive_field not in manifest_fields

    changes_fields = SyncChanges.model_fields.keys()
    assert set(changes_fields) == {"added", "updated", "deleted"}

    # Inspect client network call
    client.fetch_manifest.return_value = (
        SyncManifest(
            catalog_version="v9.0",
            generated_at="2026-10-25T12:00:00Z",
            dataset_checksum="hash-privacy",
            total_items=115,
            changes=SyncChanges(),
        ),
        None,
    )
    service.run_sync()

    # Verify fetch_manifest was called without any user parameters
    client.fetch_manifest.assert_called_once()
    args, kwargs = client.fetch_manifest.call_args
    assert "user_id" not in kwargs
    assert "bookmarks" not in kwargs
