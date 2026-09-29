import datetime
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.edge.repository import ExperienceRepository
from app.embeddings.model import SearchLatencyMetrics
from app.embeddings.service import EmbeddingService
from app.ingestion.seed import seed_database
from app.intent.models import StructuredSearchIntent
from app.intent.parser import LocalQueryParser
from app.metrics import MetricsCollector
from app.models.experience import (
    APIErrorResponse,
    DiagnosticsInfo,
    ExperienceSearchResult,
    NaturalLanguageSearchRequest,
)
from app.memory.models import (
    BookmarksListResponse,
    InteractionRecordRequest,
    UserPreferenceProfile,
)
from app.memory.service import UserMemoryService
from app.ratelimit import RateLimiter
from app.sync.models import (
    SyncChanges,
    SyncManifest,
    SyncRunResult,
    SyncStatusResponse,
)
from app.sync.service import SyncService

router = APIRouter()


def get_repository(request: Request) -> ExperienceRepository:
    """Dependency provider for ExperienceRepository attached to app state."""
    repo: Optional[ExperienceRepository] = getattr(request.app.state, "repository", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant Edge repository is not initialized",
        )
    return repo


def get_embedding_service_dep(request: Request) -> EmbeddingService:
    """Dependency provider for local EmbeddingService attached to app state."""
    service: Optional[EmbeddingService] = getattr(request.app.state, "embedding_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local FastEmbed embedding service is not initialized",
        )
    return service


def get_query_parser_dep(request: Request) -> LocalQueryParser:
    """Dependency provider for LocalQueryParser attached to app state."""
    parser: Optional[LocalQueryParser] = getattr(request.app.state, "query_parser", None)
    if parser is None:
        settings = getattr(request.app.state, "settings", None)
        parser = LocalQueryParser(settings=settings)
        request.app.state.query_parser = parser
    return parser


def get_memory_service(request: Request):
    """Dependency provider for UserMemoryService attached to app state."""
    service = getattr(request.app.state, "memory_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User memory service is not initialized",
        )
    return service


def get_sync_service(request: Request) -> SyncService:
    """Dependency provider for SyncService attached to app state."""
    service = getattr(request.app.state, "sync_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync service is not initialized",
        )
    return service


def get_metrics_dep(request: Request) -> MetricsCollector:
    """Dependency provider for MetricsCollector attached to app state."""
    collector = getattr(request.app.state, "metrics", None)
    if collector is None:
        from app.metrics import get_metrics_collector
        collector = get_metrics_collector()
    return collector


def get_search_limiter_dep(request: Request) -> Optional[RateLimiter]:
    """Dependency provider for the search rate limiter."""
    return getattr(request.app.state, "search_limiter", None)


def get_sync_limiter_dep(request: Request) -> Optional[RateLimiter]:
    """Dependency provider for the sync rate limiter."""
    return getattr(request.app.state, "sync_limiter", None)


class HealthCheckResponse(BaseModel):
    """Health status and local Edge engine summary."""
    status: str
    app_name: str
    version: str
    engine: str
    engine_version: str
    storage_path: str
    points_count: int
    embedding_model: str
    is_local_edge: bool = True
    is_local_embedding: bool = True
    has_sparse_bm25: bool = True
    sync_enabled: bool = False
    catalog_version: Optional[str] = None
    last_successful_sync: Optional[str] = None
    sync_status: Optional[str] = None


class SearchResponse(BaseModel):
    """Retrieved results with retrieval metadata and latency metrics."""
    query: str
    semantic_query: Optional[str] = None
    mode: str = "hybrid"
    total_returned: int
    latency_ms: SearchLatencyMetrics
    filters_applied: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    personalization: Optional[Dict[str, Any]] = None
    results: List[ExperienceSearchResult]


class SeedResponse(BaseModel):
    """Response returned upon triggering seed ingestion."""
    status: str
    seeded_count: int
    total_points: int


# ---------------------------------------------------------------------------
# Phase 3D: Operational Metrics Endpoint
# ---------------------------------------------------------------------------

@router.get("/metrics", tags=["Diagnostics"])
def get_metrics(
    metrics: MetricsCollector = Depends(get_metrics_dep),
) -> Dict[str, Any]:
    """
    Returns privacy-safe operational metrics — no query text, no user IDs,
    no personal data. Suitable for demo dashboards and operational monitoring.
    """
    return metrics.snapshot()


@router.get("/live", tags=["Diagnostics"])
def liveness_probe() -> Dict[str, str]:
    """Lightweight liveness probe for container orchestrator health checking."""
    return {"status": "ok", "app": "QdrantCinema Edge Platform"}


@router.get("/ready", tags=["Diagnostics"])
def readiness_probe(
    request: Request,
    repo: ExperienceRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Readiness probe confirming local Qdrant Edge shard is initialized and open."""
    sync_service = getattr(request.app.state, "sync_service", None)
    sync_status = sync_service.get_status() if sync_service else None
    return {
        "status": "ready",
        "points_count": repo.count(),
        "sync_enabled": repo.settings.sync_enabled,
        "catalog_version": sync_status.catalog_version if sync_status else None,
        "sync_status": sync_status.status if sync_status else "disabled",
    }


@router.get("/health", response_model=HealthCheckResponse, tags=["Diagnostics"])
@router.get("/api/health", response_model=HealthCheckResponse, tags=["Diagnostics"])
def health_check(
    request: Request,
    repo: ExperienceRepository = Depends(get_repository),
) -> HealthCheckResponse:
    """Programmatic health check verifying Qdrant Edge and FastEmbed state."""
    diag = repo.get_diagnostics()
    sync_service = getattr(request.app.state, "sync_service", None)
    sync_status = sync_service.get_status() if sync_service else None
    return HealthCheckResponse(
        status="healthy" if diag.healthy else "degraded",
        app_name=repo.settings.app_name,
        version=repo.settings.app_version,
        engine=diag.engine,
        engine_version=diag.engine_version,
        storage_path=diag.storage_path,
        points_count=diag.points_count,
        embedding_model=diag.embedding_model_name,
        is_local_edge=True,
        is_local_embedding=True,
        has_sparse_bm25=True,
        sync_enabled=repo.settings.sync_enabled,
        catalog_version=sync_status.catalog_version if sync_status else None,
        last_successful_sync=sync_status.last_successful_sync if sync_status else None,
        sync_status=sync_status.status if sync_status else "disabled",
    )


@router.get("/edge/status", response_model=DiagnosticsInfo, tags=["Diagnostics"])
@router.get("/api/diagnostics", response_model=DiagnosticsInfo, tags=["Diagnostics"])
def get_diagnostics(
    repo: ExperienceRepository = Depends(get_repository),
) -> DiagnosticsInfo:
    """Provides deep runtime diagnostics proving retrieval is executed via local Qdrant Edge."""
    return repo.get_diagnostics()


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={400: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse}},
    tags=["Retrieval"],
)
@router.post(
    "/api/experiences/search",
    response_model=SearchResponse,
    responses={400: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse}},
    tags=["Retrieval"],
)
def search_experiences(
    search_request: NaturalLanguageSearchRequest,
    request: Request,
    repo: ExperienceRepository = Depends(get_repository),
    emb_service: EmbeddingService = Depends(get_embedding_service_dep),
    query_parser: LocalQueryParser = Depends(get_query_parser_dep),
    memory_service: UserMemoryService = Depends(get_memory_service),
    metrics: MetricsCollector = Depends(get_metrics_dep),
    rate_limiter: Optional[RateLimiter] = Depends(get_search_limiter_dep),
) -> SearchResponse:
    """Performs hybrid, dense, or sparse BM25 search over local Qdrant Edge with payload filtering and query understanding."""
    # Phase 3C: rate limiting for search endpoint
    settings = getattr(request.app.state, "settings", None)
    if rate_limiter and settings and getattr(settings, "rate_limit_search_enabled", False):
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = rate_limiter.is_allowed(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMITED",
                    "message": f"Too many search requests. Please retry after {retry_after:.1f} seconds.",
                },
            )

    t_total_start = time.perf_counter()
    query_str = search_request.get_query_string()
    mode = search_request.mode
    limit = search_request.limit

    filters_dict = search_request.filters.model_dump(exclude_none=True) if search_request.filters else None

    # Handle query input validation and auto-routing for raw vector requests
    has_text = bool(query_str and query_str.strip())
    has_vector = search_request.vector is not None

    if not has_text and not has_vector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_QUERY",
                "message": "Search query cannot be empty or whitespace only.",
            },
        )

    if has_text and len(query_str.strip()) > repo.settings.max_query_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "QUERY_TOO_LONG",
                "message": f"Search query exceeds maximum allowed length of {repo.settings.max_query_length} characters.",
            },
        )

    if has_vector and not has_text:
        # Caller provided a low-level vector without text; execute dense search
        mode = "dense"

    # 1. Deterministic Query Understanding & Intent Extraction
    intent: Optional[StructuredSearchIntent] = None
    t_parse: Optional[float] = None
    semantic_query: Optional[str] = None
    edge_filter = None

    if has_text and search_request.enable_intent and repo.settings.enable_query_understanding:
        t_parse_start = time.perf_counter()
        intent = query_parser.parse(query_str)
        t_parse = (time.perf_counter() - t_parse_start) * 1000
        semantic_query = intent.semantic_query or query_str
        edge_filter = repo.build_filter_from_intent(intent, override_filters=search_request.filters)
    else:
        edge_filter = repo.build_filter(search_request.filters)
        semantic_query = query_str

    # Text used for dense and BM25 vectorization
    vector_search_text = semantic_query if semantic_query else (query_str or "")

    # Compile applied filters dictionary for response transparency
    applied_filters: Dict[str, Any] = {}
    if filters_dict:
        applied_filters.update(filters_dict)
    if intent:
        if intent.category and intent.category.value:
            applied_filters["category"] = intent.category.value
        if intent.price_min and intent.price_min.value is not None:
            applied_filters["min_price"] = intent.price_min.value
        if intent.price_max and intent.price_max.value is not None:
            applied_filters["max_price"] = intent.price_max.value
        if intent.is_indoor and intent.is_indoor.value is not None:
            applied_filters["is_indoor"] = intent.is_indoor.value
        if intent.date and intent.date.value is not None:
            applied_filters["date"] = intent.date.value
        if intent.city and intent.city.value:
            applied_filters["city"] = intent.city.value
        if intent.neighborhood and intent.neighborhood.value:
            applied_filters["neighborhood"] = intent.neighborhood.value
        if intent.venue and intent.venue.value:
            applied_filters["venue"] = intent.venue.value
        if intent.format and intent.format.value:
            applied_filters["format"] = intent.format.value
        if intent.language and intent.language.value:
            applied_filters["language"] = intent.language.value
        if intent.excluded_categories:
            applied_filters["excluded_categories"] = intent.excluded_categories
        if intent.excluded_subcategories:
            applied_filters["excluded_subcategories"] = intent.excluded_subcategories

    if mode == "hybrid":
        # 1. Dense query vectorization
        t_dense_emb_start = time.perf_counter()
        try:
            dense_vector = emb_service.embed_text(vector_search_text)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Local dense embedding failed: {e}",
            )
        t_dense_emb = (time.perf_counter() - t_dense_emb_start) * 1000

        # 2. BM25 query sparse vectorization
        t_bm25_emb_start = time.perf_counter()
        sparse_vector = repo.bm25_service.embed_query(vector_search_text)
        t_bm25_emb = (time.perf_counter() - t_bm25_emb_start) * 1000

        # 3. Hybrid search with pre-filtering and RRF
        dense_top_k = search_request.dense_top_k or repo.settings.dense_top_k
        bm25_top_k = search_request.bm25_top_k or repo.settings.bm25_top_k
        rrf_k = search_request.rrf_k or repo.settings.rrf_k

        results, timings = repo.search_hybrid(
            query_vector=dense_vector,
            sparse_vector=sparse_vector,
            dense_top_k=dense_top_k,
            bm25_top_k=bm25_top_k,
            final_top_k=limit,
            rrf_k=rrf_k,
            filters=edge_filter,
        )

        t_total = (time.perf_counter() - t_total_start) * 1000
        latency = SearchLatencyMetrics(
            embedding_ms=round(t_dense_emb + t_bm25_emb, 2),
            search_ms=round(timings["dense_search_ms"] + timings["bm25_search_ms"] + timings["fusion_ms"], 2),
            total_ms=round(t_total, 2),
            dense_embedding_ms=round(t_dense_emb, 2),
            dense_search_ms=timings["dense_search_ms"],
            bm25_embedding_ms=round(t_bm25_emb, 2),
            bm25_search_ms=timings["bm25_search_ms"],
            fusion_ms=timings["fusion_ms"],
            query_parsing_ms=round(t_parse, 2) if t_parse is not None else None,
        )

    elif mode == "dense":
        if vector_search_text and vector_search_text.strip():
            t_dense_emb_start = time.perf_counter()
            try:
                query_vector = emb_service.embed_text(vector_search_text)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Local embedding failed: {e}",
                )
            t_dense_emb = (time.perf_counter() - t_dense_emb_start) * 1000
        elif search_request.vector is not None:
            query_vector = search_request.vector
            t_dense_emb = 0.0
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A non-empty 'query' text or vector must be provided for dense retrieval.",
            )

        if len(query_vector) != repo.settings.vector_size:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Query vector dimension {len(query_vector)} does not match "
                    f"configured vector size {repo.settings.vector_size}"
                ),
            )

        t_search_start = time.perf_counter()
        results = repo.search_dense(
            query_vector=query_vector,
            limit=limit,
            filters=edge_filter,
        )
        t_search = (time.perf_counter() - t_search_start) * 1000
        t_total = (time.perf_counter() - t_total_start) * 1000

        latency = SearchLatencyMetrics(
            embedding_ms=round(t_dense_emb, 2),
            search_ms=round(t_search, 2),
            total_ms=round(t_total, 2),
            dense_embedding_ms=round(t_dense_emb, 2),
            dense_search_ms=round(t_search, 2),
            bm25_embedding_ms=0.0,
            bm25_search_ms=0.0,
            fusion_ms=0.0,
            query_parsing_ms=round(t_parse, 2) if t_parse is not None else None,
        )

    elif mode == "sparse":
        if not vector_search_text or not vector_search_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A non-empty 'query' text must be provided for sparse BM25 retrieval.",
            )

        t_bm25_emb_start = time.perf_counter()
        sparse_vector = repo.bm25_service.embed_query(vector_search_text)
        t_bm25_emb = (time.perf_counter() - t_bm25_emb_start) * 1000

        t_search_start = time.perf_counter()
        results = repo.search_sparse(
            sparse_vector=sparse_vector,
            limit=limit,
            filters=edge_filter,
        )
        t_search = (time.perf_counter() - t_search_start) * 1000
        t_total = (time.perf_counter() - t_total_start) * 1000

        latency = SearchLatencyMetrics(
            embedding_ms=round(t_bm25_emb, 2),
            search_ms=round(t_search, 2),
            total_ms=round(t_total, 2),
            dense_embedding_ms=0.0,
            dense_search_ms=0.0,
            bm25_embedding_ms=round(t_bm25_emb, 2),
            bm25_search_ms=round(t_search, 2),
            fusion_ms=0.0,
            query_parsing_ms=round(t_parse, 2) if t_parse is not None else None,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported search mode '{mode}'. Choose 'hybrid', 'dense', or 'sparse'.",
        )

    # 4. Personalization & User Memory Integration (Phase 2C)
    personalization_dict: Optional[Dict[str, Any]] = None
    user_id = search_request.user_id

    if search_request.personalize and repo.settings.enable_personalization:
        active_user = user_id or repo.settings.default_user_id
        results, pers_meta = memory_service.personalize_results(
            user_id=active_user,
            results=results,
            boost_weight=repo.settings.personalization_boost_weight,
        )
        personalization_dict = pers_meta.model_dump()
        if query_str and query_str.strip():
            memory_service.record_search(user_id=active_user, query=query_str.strip())
    else:
        active_user = user_id or (repo.settings.default_user_id if search_request.personalize else None)
        personalization_dict = {
            "enabled": repo.settings.enable_personalization,
            "applied": False,
            "signals_used": [],
            "user_id": active_user,
        }

    # Populate is_saved status on cards if user_id is provided
    check_user = user_id or (repo.settings.default_user_id if search_request.personalize else None)
    if check_user:
        saved_ids = set(memory_service.get_bookmarks(check_user))
        results = [
            r.model_copy(update={"is_saved": r.id in saved_ids}) for r in results
        ]

    # Phase 3D: Record metrics
    metrics.record_search(success=True, latency_ms=latency.total_ms)

    return SearchResponse(
        query=query_str or "",
        semantic_query=semantic_query,
        mode=mode,
        total_returned=len(results),
        latency_ms=latency,
        filters_applied=applied_filters if applied_filters else None,
        intent=intent.model_dump() if intent else None,
        personalization=personalization_dict,
        results=results,
    )


@router.get(
    "/api/experiences/{experience_id}",
    response_model=ExperienceSearchResult,
    responses={404: {"model": APIErrorResponse}},
    tags=["Retrieval"],
)
def get_experience_by_id(
    experience_id: int,
    repo: ExperienceRepository = Depends(get_repository),
) -> ExperienceSearchResult:
    """Retrieves an experience directly by ID from the local Qdrant Edge shard."""
    experience = repo.get_by_id(experience_id)
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": f"Experience with ID {experience_id} not found in local Edge shard.",
            },
        )
    return experience


@router.post("/api/experiences/seed", response_model=SeedResponse, tags=["Ingestion"])
def trigger_seed(
    overwrite: bool = False,
    repo: ExperienceRepository = Depends(get_repository),
    emb_service: EmbeddingService = Depends(get_embedding_service_dep),
) -> SeedResponse:
    """Manually triggers or forces re-seeding of the experience dataset with local embeddings."""
    seeded = seed_database(
        repo,
        repo.settings,
        embedding_service=emb_service,
        overwrite=overwrite,
    )
    total = repo.count()
    return SeedResponse(
        status="success",
        seeded_count=seeded,
        total_points=total,
    )


# --------------------------------------------------------------------------
# User Memory & Bookmarks Endpoints (Phase 2C)
# --------------------------------------------------------------------------

@router.post(
    "/api/users/{user_id}/bookmarks/{experience_id}",
    responses={404: {"model": APIErrorResponse}},
    tags=["Memory"],
)
def add_bookmark(
    user_id: str,
    experience_id: int,
    repo: ExperienceRepository = Depends(get_repository),
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> Dict[str, Any]:
    """Saves an experience to local bookmarks and updates interaction history."""
    exp = repo.get_by_id(experience_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EXPERIENCE_NOT_FOUND",
                "message": f"Experience with ID {experience_id} not found.",
            },
        )
    saved = memory_service.add_bookmark(user_id, experience_id)
    return {
        "status": "saved" if saved else "already_saved",
        "user_id": user_id,
        "experience_id": experience_id,
    }


@router.delete(
    "/api/users/{user_id}/bookmarks/{experience_id}",
    tags=["Memory"],
)
def remove_bookmark(
    user_id: str,
    experience_id: int,
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> Dict[str, Any]:
    """Removes an experience from local bookmarks."""
    removed = memory_service.remove_bookmark(user_id, experience_id)
    return {
        "status": "removed" if removed else "not_found",
        "user_id": user_id,
        "experience_id": experience_id,
    }


@router.get(
    "/api/users/{user_id}/bookmarks",
    response_model=BookmarksListResponse,
    tags=["Memory"],
)
def list_bookmarks(
    user_id: str,
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> BookmarksListResponse:
    """Lists all saved experiences for a local user."""
    bookmark_ids = memory_service.get_bookmarks(user_id)
    experiences = memory_service.get_bookmarked_experiences(user_id)
    experiences = [e.model_copy(update={"is_saved": True}) for e in experiences]
    bookmarks_info = [
        {"experience_id": e.id, "title": e.title, "category": e.category, "price": e.price}
        for e in experiences
    ]
    if not bookmarks_info and bookmark_ids:
        bookmarks_info = [{"experience_id": b_id} for b_id in bookmark_ids]

    return BookmarksListResponse(
        user_id=user_id,
        total=len(bookmark_ids),
        count=len(bookmark_ids),
        bookmarks=bookmarks_info,
        experiences=experiences,
    )


@router.get(
    "/api/users/{user_id}/preferences",
    response_model=UserPreferenceProfile,
    tags=["Memory"],
)
def get_user_preferences(
    user_id: str,
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> UserPreferenceProfile:
    """Returns the current inferred preference profile computed locally from user interactions."""
    return memory_service.get_user_preferences(user_id)


@router.delete(
    "/api/users/{user_id}/memory",
    tags=["Memory"],
)
def reset_user_memory(
    user_id: str,
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> Dict[str, str]:
    """Resets and purges all bookmarks, interactions, and preference memory for the specified user."""
    memory_service.reset_memory(user_id)
    return {
        "status": "cleared",
        "user_id": user_id,
        "message": f"Local memory and preferences for user '{user_id}' cleared successfully.",
    }


@router.post(
    "/api/users/{user_id}/interactions",
    tags=["Memory"],
)
def record_interaction(
    user_id: str,
    request: InteractionRecordRequest,
    memory_service: UserMemoryService = Depends(get_memory_service),
) -> Dict[str, Any]:
    """Records a lightweight interaction event (e.g. view or search) into local storage."""
    e_type = request.get_event_type()
    meta = dict(request.metadata or {})
    if request.category:
        meta["category"] = request.category
    if request.price is not None:
        meta["price"] = request.price
    if request.is_indoor is not None:
        meta["is_indoor"] = request.is_indoor

    memory_service.record_interaction(
        user_id=user_id,
        interaction_type=e_type,
        experience_id=request.experience_id,
        query=request.query,
        category=request.category,
        price=request.price,
        is_indoor=request.is_indoor,
        metadata=meta,
    )
    return {
        "status": "recorded",
        "user_id": user_id,
        "event_type": e_type,
    }


# ============================================================================
# Phase 2D: Edge-to-Server Synchronization Endpoints
# ============================================================================

@router.get(
    "/api/sync/status",
    response_model=SyncStatusResponse,
    tags=["Synchronization"],
)
def get_sync_status(
    sync_service: SyncService = Depends(get_sync_service),
) -> SyncStatusResponse:
    """Returns the current local synchronization status, last sync timestamp, and checkpoint metrics."""
    return sync_service.get_status()


@router.post(
    "/api/sync/run",
    response_model=SyncRunResult,
    tags=["Synchronization"],
)
def trigger_sync_run(
    request: Request,
    force: bool = False,
    sync_service: SyncService = Depends(get_sync_service),
    metrics: MetricsCollector = Depends(get_metrics_dep),
    rate_limiter: Optional[RateLimiter] = Depends(get_sync_limiter_dep),
) -> SyncRunResult:
    """Manually triggers a selective catalog synchronization run from the configured server."""
    # Phase 3C: rate limiting for sync endpoint
    settings = getattr(request.app.state, "settings", None)
    if rate_limiter and settings and getattr(settings, "rate_limit_sync_enabled", False):
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = rate_limiter.is_allowed(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMITED",
                    "message": f"Too many sync requests. Please retry after {retry_after:.1f} seconds.",
                },
            )

    result = sync_service.run_sync(force=force)
    # Phase 3D: Record sync metrics
    items_applied = result.added_count + result.updated_count + result.deleted_count
    metrics.record_sync(
        success=result.status == "completed",
        items_applied=items_applied,
    )
    return result


@router.get(
    "/api/sync/manifest",
    response_model=SyncManifest,
    tags=["Synchronization"],
)
def get_sync_manifest(
    since: Optional[str] = None,
    repo: ExperienceRepository = Depends(get_repository),
) -> SyncManifest:
    """Returns the current catalog version manifest for edge nodes or test suites to synchronize against."""
    import hashlib
    # Compute deterministic dataset checksum based on points in shard
    checksum_seed = f"{repo.settings.collection_name}:{repo.count()}:{repo.settings.reference_datetime}"
    dataset_checksum = hashlib.sha256(checksum_seed.encode("utf-8")).hexdigest()[:16]
    catalog_version = repo.settings.reference_datetime or "2026-10-15T12:00:00Z"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return SyncManifest(
        catalog_version=catalog_version,
        generated_at=now_iso,
        dataset_checksum=dataset_checksum,
        total_items=repo.count(),
        changes=SyncChanges(),
    )


@router.get(
    "/api/sync/experiences",
    tags=["Synchronization"],
)
def get_sync_experiences(
    ids: Optional[str] = None,
    repo: ExperienceRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieves full experience payloads for catalog synchronization."""
    if not ids or not ids.strip():
        return {"experiences": []}

    id_list: List[int] = []
    for part in ids.split(","):
        part = part.strip()
        if part.isdigit():
            id_list.append(int(part))

    experiences = repo.get_by_ids(id_list)
    return {
        "experiences": [
            e.payload if e.payload else {
                "id": e.id,
                "title": e.title,
                "category": e.category,
                "description": e.description,
                "venue": e.venue,
                "city": e.city,
                "neighborhood": e.neighborhood,
                "price": e.price,
                "is_indoor": e.is_indoor,
                "rating": e.rating,
                "start_time": e.start_time,
                "end_time": e.end_time,
            }
            for e in experiences
        ]
    }


