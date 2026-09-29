import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from qdrant_edge import (
    CountRequest,
    EdgeShard,
    FieldCondition,
    Filter,
    MatchValue,
    Point,
    Query,
    RangeFloat,
    SearchRequest,
    SparseVector,
    UpdateOperation,
)
from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import get_shard_diagnostics
from app.embeddings.bm25 import build_bm25_text, get_bm25_service
from app.intent.models import StructuredSearchIntent
from app.models.experience import (
    DiagnosticsInfo,
    Experience,
    ExperienceSearchResult,
    SearchFilterParams,
)
from app.retrieval.filter_builder import FilterBuilder
from app.retrieval.fusion import reciprocal_rank_fusion

logger = logging.getLogger("qdrant_edge.repository")


class ExperienceRepository:
    """Repository handling dual vector storage, hybrid retrieval, and payload filtering via Qdrant Edge."""

    def __init__(self, shard: EdgeShard, client: EdgeClient, settings: Settings):
        self.shard = shard
        self.client = client
        self.settings = settings
        self.bm25_service = get_bm25_service()
        self.filter_builder = FilterBuilder()

    def upsert_experiences(self, experiences: List[Experience]) -> int:
        """Inserts or updates points with named dense and BM25 sparse vectors and payloads."""
        if not experiences:
            return 0

        points: List[Point] = []
        for exp in experiences:
            payload_data = exp.payload.model_dump()
            payload_data["is_indoor"] = 1 if exp.payload.is_indoor else 0

            # Build vector dictionary for dual named vectors
            vectors_dict: Dict[str, Any] = {}

            if exp.vector is not None:
                vectors_dict[self.settings.dense_vector_name] = exp.vector

            if exp.sparse_vector is not None:
                vectors_dict[self.settings.sparse_vector_name] = exp.sparse_vector
            else:
                # Auto-generate BM25 sparse vector from payload text
                lexical_text = build_bm25_text(exp.payload)
                vectors_dict[self.settings.sparse_vector_name] = self.bm25_service.embed_document(lexical_text)

            points.append(
                Point(
                    id=exp.id,
                    vector=vectors_dict,
                    payload=payload_data,
                )
            )

        self.shard.update(UpdateOperation.upsert_points(points))
        self.shard.flush()
        logger.info(f"Successfully upserted and flushed {len(points)} experiences with dual vectors to EdgeShard")
        return len(points)

    def delete_experiences(self, experience_ids: List[int]) -> int:
        """Deletes points from local Qdrant Edge shard by primary IDs."""
        if not experience_ids:
            return 0
        int_ids = [int(i) for i in experience_ids]
        self.shard.update(UpdateOperation.delete_points(int_ids))
        self.shard.flush()
        logger.info(f"Successfully deleted and flushed {len(int_ids)} experiences from EdgeShard")
        return len(int_ids)

    def get_by_id(self, experience_id: int) -> Optional[ExperienceSearchResult]:
        """Direct point retrieval by primary ID."""
        records = self.shard.retrieve([experience_id], with_payload=True, with_vector=True)
        if not records:
            return None

        rec = records[0]
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        if "is_indoor" in payload:
            payload["is_indoor"] = bool(payload["is_indoor"])

        return ExperienceSearchResult(
            id=rec.id,
            score=1.0,
            title=payload.get("title", ""),
            category=payload.get("category", ""),
            description=payload.get("description", ""),
            payload=payload,
        )

    def get_by_ids(self, experience_ids: List[int]) -> List[ExperienceSearchResult]:
        """Retrieves multiple points by primary IDs."""
        if not experience_ids:
            return []
        int_ids = [int(i) for i in experience_ids]
        records = self.shard.retrieve(int_ids, with_payload=True, with_vector=False)
        results: List[ExperienceSearchResult] = []
        for rec in records:
            payload = rec.payload if isinstance(rec.payload, dict) else {}
            if "is_indoor" in payload:
                payload["is_indoor"] = bool(payload["is_indoor"])
            results.append(
                ExperienceSearchResult(
                    id=rec.id,
                    score=1.0,
                    title=payload.get("title", ""),
                    category=payload.get("category", ""),
                    description=payload.get("description", ""),
                    payload=payload,
                )
            )
        return results

    def build_filter(self, filters: Optional[SearchFilterParams]) -> Optional[Filter]:
        """Translates high-level search filters into Qdrant Edge Filter expressions."""
        return self.filter_builder.build_from_params(filters)

    def build_filter_from_intent(
        self,
        intent: StructuredSearchIntent,
        override_filters: Optional[SearchFilterParams] = None,
    ) -> Optional[Filter]:
        """Translates structured intent and optional overrides into a Qdrant Edge Filter."""
        return self.filter_builder.build_from_intent(intent, override_filters=override_filters)

    def _resolve_filter(self, filters: Optional[Union[SearchFilterParams, Filter]]) -> Optional[Filter]:
        """Helper to resolve either pre-built Filter or SearchFilterParams."""
        if isinstance(filters, Filter):
            return filters
        elif isinstance(filters, SearchFilterParams):
            return self.build_filter(filters)
        return None

    def search_dense(
        self,
        query_vector: List[float],
        limit: int = 20,
        filters: Optional[Union[SearchFilterParams, Filter]] = None,
    ) -> List[ExperienceSearchResult]:
        """Executes dense semantic retrieval with pre-filtering in local Qdrant Edge."""
        edge_filter = self._resolve_filter(filters)

        search_req = SearchRequest(
            query=Query.Nearest(query_vector, using=self.settings.dense_vector_name),
            limit=limit,
            filter=edge_filter,
            with_payload=True,
            with_vector=False,
        )

        scored_points = self.shard.search(search_req)

        results: List[ExperienceSearchResult] = []
        for rank_0, sp in enumerate(scored_points):
            payload = sp.payload if isinstance(sp.payload, dict) else {}
            if "is_indoor" in payload:
                payload["is_indoor"] = bool(payload["is_indoor"])
            score_val = float(sp.score)
            results.append(
                ExperienceSearchResult(
                    id=sp.id,
                    score=score_val,
                    title=payload.get("title", ""),
                    category=payload.get("category", ""),
                    description=payload.get("description", ""),
                    payload=payload,
                    dense_score=score_val,
                    dense_rank=rank_0 + 1,
                )
            )

        return results

    def search_sparse(
        self,
        sparse_vector: SparseVector,
        limit: int = 20,
        filters: Optional[Union[SearchFilterParams, Filter]] = None,
    ) -> List[ExperienceSearchResult]:
        """Executes BM25 sparse keyword retrieval with pre-filtering in local Qdrant Edge."""
        if not sparse_vector or not hasattr(sparse_vector, "indices") or len(sparse_vector.indices) == 0:
            return []

        edge_filter = self._resolve_filter(filters)

        search_req = SearchRequest(
            query=Query.Nearest(sparse_vector, using=self.settings.sparse_vector_name),
            limit=limit,
            filter=edge_filter,
            with_payload=True,
            with_vector=False,
        )

        scored_points = self.shard.search(search_req)

        results: List[ExperienceSearchResult] = []
        for rank_0, sp in enumerate(scored_points):
            payload = sp.payload if isinstance(sp.payload, dict) else {}
            if "is_indoor" in payload:
                payload["is_indoor"] = bool(payload["is_indoor"])
            score_val = float(sp.score)
            results.append(
                ExperienceSearchResult(
                    id=sp.id,
                    score=score_val,
                    title=payload.get("title", ""),
                    category=payload.get("category", ""),
                    description=payload.get("description", ""),
                    payload=payload,
                    sparse_score=score_val,
                    sparse_rank=rank_0 + 1,
                )
            )

        return results

    def search_hybrid(
        self,
        query_vector: List[float],
        sparse_vector: SparseVector,
        dense_top_k: int = 20,
        bm25_top_k: int = 20,
        final_top_k: int = 10,
        rrf_k: int = 60,
        filters: Optional[Union[SearchFilterParams, Filter]] = None,
    ) -> Tuple[List[ExperienceSearchResult], Dict[str, float]]:
        """Executes dual-branch retrieval (Dense + BM25) and combines results via Reciprocal Rank Fusion."""
        # 1. Dense retrieval branch
        t0 = time.perf_counter()
        dense_candidates = self.search_dense(
            query_vector=query_vector,
            limit=dense_top_k,
            filters=filters,
        )
        dense_search_ms = (time.perf_counter() - t0) * 1000

        # 2. Sparse BM25 retrieval branch
        t1 = time.perf_counter()
        sparse_candidates = self.search_sparse(
            sparse_vector=sparse_vector,
            limit=bm25_top_k,
            filters=filters,
        )
        bm25_search_ms = (time.perf_counter() - t1) * 1000

        # 3. Reciprocal Rank Fusion
        t2 = time.perf_counter()
        fused_results = reciprocal_rank_fusion(
            dense_results=dense_candidates,
            sparse_results=sparse_candidates,
            k=rrf_k,
            limit=final_top_k,
        )
        fusion_ms = (time.perf_counter() - t2) * 1000

        timings = {
            "dense_search_ms": round(dense_search_ms, 2),
            "bm25_search_ms": round(bm25_search_ms, 2),
            "fusion_ms": round(fusion_ms, 2),
        }

        return fused_results, timings

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Union[SearchFilterParams, Filter]] = None,
    ) -> List[ExperienceSearchResult]:
        """Backwards compatibility alias delegating to search_dense."""
        return self.search_dense(query_vector=query_vector, limit=limit, filters=filters)

    def count(self) -> int:
        """Returns the total number of points stored in the local Edge shard."""
        return self.shard.count(CountRequest(exact=True))

    def get_diagnostics(self) -> DiagnosticsInfo:
        """Returns runtime diagnostics proving local in-process Qdrant Edge execution."""
        stats = get_shard_diagnostics(self.shard)
        collection_path = str(self.client.get_collection_path(self.settings.collection_name))

        return DiagnosticsInfo(
            engine="qdrant-edge-py",
            engine_version=self.client.version,
            execution_mode="in_process_local",
            storage_path=collection_path,
            collection_name=self.settings.collection_name,
            points_count=stats["points_count"],
            segments_count=stats["segments_count"],
            indexed_vectors_count=stats["indexed_vectors_count"],
            vector_size=self.settings.vector_size,
            distance=self.settings.vector_distance,
            indexed_payload_fields=stats["payload_schema"],
            embedding_model_name=self.settings.embedding_model_name,
            embedding_dimension=self.settings.embedding_dimension,
            is_local_embedding=True,
            has_sparse_bm25=True,
            healthy=True,
        )
