import datetime
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import Settings
from app.edge.repository import ExperienceRepository
from app.embeddings.bm25 import build_bm25_text, get_bm25_service
from app.embeddings.service import EmbeddingService, build_embedding_text
from app.models.experience import Experience, ExperiencePayload
from app.sync.client import SyncClient
from app.sync.models import (
    SyncCheckpoint,
    SyncManifest,
    SyncRunResult,
    SyncStatusEnum,
    SyncStatusResponse,
)
from app.sync.repository import SyncRepository

logger = logging.getLogger("qdrant_edge.sync.service")


class SyncService:
    """Coordinates selective catalog synchronization between central server and local Qdrant Edge shard."""

    def __init__(
        self,
        sync_repo: SyncRepository,
        sync_client: SyncClient,
        experience_repo: ExperienceRepository,
        embedding_service: EmbeddingService,
        settings: Settings,
    ):
        self.repo = sync_repo
        self.client = sync_client
        self.exp_repo = experience_repo
        self.emb_service = embedding_service
        self.settings = settings
        self.bm25_service = get_bm25_service()
        self._sync_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def get_status(self) -> SyncStatusResponse:
        """Returns current sync status and diagnostic checkpoint metrics."""
        chk = self.repo.get_checkpoint()
        status_val = chk.status if self.settings.sync_enabled else SyncStatusEnum.DISABLED.value
        return SyncStatusResponse(
            enabled=self.settings.sync_enabled,
            status=status_val,
            last_successful_sync=chk.last_successful_sync,
            last_attempted_sync=chk.last_attempted_sync,
            catalog_version=chk.catalog_version,
            dataset_checksum=chk.dataset_checksum,
            items_added=chk.items_added,
            items_updated=chk.items_updated,
            items_deleted=chk.items_deleted,
            last_error=chk.last_error,
        )

    def run_sync(self, force: bool = False) -> SyncRunResult:
        """Executes a single synchronization cycle with atomic updates and failure safety."""
        t_start = time.perf_counter()

        # 1. Guard against disabled or unconfigured sync
        if not self.settings.sync_enabled:
            return SyncRunResult(
                ran=False,
                status=SyncStatusEnum.DISABLED.value,
                message="Synchronization is disabled in application settings.",
            )

        if not self.settings.sync_server_url:
            return SyncRunResult(
                ran=False,
                status=SyncStatusEnum.DISABLED.value,
                message="Sync server URL is not configured.",
            )

        # 2. Prevent overlapping / concurrent sync executions
        acquired = self._sync_lock.acquire(blocking=False)
        if not acquired:
            return SyncRunResult(
                ran=False,
                status=SyncStatusEnum.SYNCING.value,
                message="A synchronization run is already actively in progress.",
            )

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_chk = self.repo.get_checkpoint()
        prev_version = current_chk.catalog_version

        try:
            # Mark status as syncing
            self.repo.update_status(status=SyncStatusEnum.SYNCING.value, attempted_at=now_iso)

            # 3. Fetch manifest from central server
            manifest, err = self.client.fetch_manifest(since_version=prev_version)
            if err or manifest is None:
                err_msg = err or "Unknown error fetching manifest."
                self.repo.update_status(status=SyncStatusEnum.FAILED.value, error=err_msg)
                duration = (time.perf_counter() - t_start) * 1000
                return SyncRunResult(
                    ran=True,
                    status=SyncStatusEnum.FAILED.value,
                    previous_version=prev_version,
                    duration_ms=round(duration, 2),
                    error=err_msg,
                    message="Failed to retrieve synchronization manifest from server.",
                )

            # 4. Compare version and checksum
            if (
                not force
                and manifest.catalog_version == current_chk.catalog_version
                and manifest.dataset_checksum == current_chk.dataset_checksum
            ):
                current_chk.status = SyncStatusEnum.SUCCESS.value
                current_chk.last_successful_sync = now_iso
                current_chk.last_error = None
                self.repo.save_checkpoint(current_chk)
                duration = (time.perf_counter() - t_start) * 1000
                return SyncRunResult(
                    ran=True,
                    status=SyncStatusEnum.SUCCESS.value,
                    previous_version=prev_version,
                    new_version=manifest.catalog_version,
                    duration_ms=round(duration, 2),
                    message="Catalog is already up to date with server.",
                )

            # 5. Extract change sets
            added_ids = manifest.changes.added
            updated_ids = manifest.changes.updated
            deleted_ids = manifest.changes.deleted
            to_fetch = added_ids + updated_ids

            # Apply batch boundary safeguards
            if len(to_fetch) > self.settings.sync_max_items_per_run:
                logger.warning(
                    f"Sync items to fetch ({len(to_fetch)}) exceeds max items per run ({self.settings.sync_max_items_per_run}). Processing capped batch."
                )
                to_fetch = to_fetch[: self.settings.sync_max_items_per_run]

            # 6. Download changed records in bounded batches
            fetched_records: List[Dict[str, Any]] = []
            batch_size = max(1, self.settings.sync_batch_size)

            for i in range(0, len(to_fetch), batch_size):
                batch_ids = to_fetch[i : i + batch_size]
                items, batch_err = self.client.fetch_experiences(batch_ids)
                if batch_err:
                    self.repo.update_status(status=SyncStatusEnum.FAILED.value, error=batch_err)
                    duration = (time.perf_counter() - t_start) * 1000
                    return SyncRunResult(
                        ran=True,
                        status=SyncStatusEnum.FAILED.value,
                        previous_version=prev_version,
                        duration_ms=round(duration, 2),
                        error=batch_err,
                        message=f"Failed to fetch experience batch: {batch_err}",
                    )
                fetched_records.extend(items)

            # 7. Incremental Vector Updates (embed and upsert into Qdrant Edge)
            if fetched_records:
                experiences_to_upsert: List[Experience] = []
                payloads: List[ExperiencePayload] = []
                semantic_texts: List[str] = []
                lexical_texts: List[str] = []
                exp_ids: List[int] = []

                for item in fetched_records:
                    try:
                        p = ExperiencePayload(**item)
                        payloads.append(p)
                        semantic_texts.append(build_embedding_text(p))
                        lexical_texts.append(build_bm25_text(p))
                        exp_ids.append(int(item["id"]))
                    except Exception as parse_e:
                        err_msg = f"Failed to validate incoming experience record {item.get('id')}: {parse_e}"
                        self.repo.update_status(status=SyncStatusEnum.FAILED.value, error=err_msg)
                        duration = (time.perf_counter() - t_start) * 1000
                        return SyncRunResult(
                            ran=True,
                            status=SyncStatusEnum.FAILED.value,
                            previous_version=prev_version,
                            duration_ms=round(duration, 2),
                            error=err_msg,
                        )

                # Batch embed semantic texts with local FastEmbed
                dense_vectors = self.emb_service.embed_texts(semantic_texts, batch_size=32)

                # Generate sparse vectors with native BM25
                sparse_vectors = [self.bm25_service.embed_document(t) for t in lexical_texts]

                for e_id, d_vec, s_vec, pl in zip(exp_ids, dense_vectors, sparse_vectors, payloads):
                    experiences_to_upsert.append(
                        Experience(
                            id=e_id,
                            vector=d_vec,
                            sparse_vector=s_vec,
                            payload=pl,
                        )
                    )

                self.exp_repo.upsert_experiences(experiences_to_upsert)

            # 8. Deletion Safety (remove deleted IDs from Edge shard)
            if deleted_ids:
                self.exp_repo.delete_experiences(deleted_ids)

            # 9. Atomicity: Advance checkpoint ONLY after complete success
            new_chk = SyncCheckpoint(
                catalog_version=manifest.catalog_version,
                dataset_checksum=manifest.dataset_checksum,
                last_successful_sync=now_iso,
                last_attempted_sync=now_iso,
                status=SyncStatusEnum.SUCCESS.value,
                items_added=len(added_ids),
                items_updated=len(updated_ids),
                items_deleted=len(deleted_ids),
                last_error=None,
            )
            self.repo.save_checkpoint(new_chk)

            duration = (time.perf_counter() - t_start) * 1000
            msg = (
                f"Successfully synced catalog to version '{manifest.catalog_version}': "
                f"+{len(added_ids)} added, ~{len(updated_ids)} updated, -{len(deleted_ids)} deleted."
            )
            logger.info(msg)

            return SyncRunResult(
                ran=True,
                status=SyncStatusEnum.SUCCESS.value,
                previous_version=prev_version,
                new_version=manifest.catalog_version,
                added_count=len(added_ids),
                updated_count=len(updated_ids),
                deleted_count=len(deleted_ids),
                duration_ms=round(duration, 2),
                message=msg,
            )

        except Exception as e:
            err_msg = f"Unexpected failure during sync cycle: {e}"
            logger.exception(err_msg)
            # Guarantee: Do NOT advance version on unexpected failure
            self.repo.update_status(status=SyncStatusEnum.FAILED.value, error=err_msg)
            duration = (time.perf_counter() - t_start) * 1000
            return SyncRunResult(
                ran=True,
                status=SyncStatusEnum.FAILED.value,
                previous_version=prev_version,
                duration_ms=round(duration, 2),
                error=err_msg,
            )

        finally:
            self._sync_lock.release()

    # Background worker execution
    def start_background_sync(self) -> None:
        """Starts background synchronization thread if enabled and configured."""
        if not self.settings.sync_enabled or not self.settings.sync_server_url:
            logger.info("Background catalog sync is disabled or unconfigured.")
            return

        if self._worker_thread is not None and self._worker_thread.is_alive():
            logger.warning("Background sync thread is already running.")
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
            name="QdrantCinema-SyncWorker",
        )
        self._worker_thread.start()
        logger.info(
            f"Background sync worker started (interval={self.settings.sync_interval_seconds}s, server='{self.settings.sync_server_url}')."
        )

    def _background_loop(self) -> None:
        """Periodic background sync loop with graceful termination handling."""
        interval = max(5, self.settings.sync_interval_seconds)
        while not self._stop_event.is_set():
            # Wait for interval or stop event
            stopped = self._stop_event.wait(timeout=interval)
            if stopped:
                break
            try:
                logger.info("Triggering periodic background synchronization...")
                self.run_sync()
            except Exception as e:
                logger.error(f"Error in background sync worker: {e}")

    def stop_background_sync(self) -> None:
        """Signals background sync worker to stop gracefully."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
            self._worker_thread = None
        self.client.close()
        logger.info("Background sync worker stopped.")
