import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database
from app.intent.parser import LocalQueryParser
from app.metrics import get_metrics_collector
from app.ratelimit import RateLimiter

# ---------------------------------------------------------------------------
# Logging setup (Phase 3B)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("qdrant_edge.main")


def _configure_logging(settings: Settings) -> None:
    """Apply log level from settings to the root logger."""
    import logging as _logging
    level = getattr(_logging, settings.log_level, _logging.INFO)
    _logging.getLogger().setLevel(level)
    logger.setLevel(level)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Application factory for QdrantCinema Edge platform."""
    app_settings = settings or get_settings()
    _configure_logging(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ---- Startup -------------------------------------------------------
        logger.info("Starting %s v%s [env=%s]",
                    app_settings.app_name, app_settings.app_version,
                    app_settings.environment)
        logger.info("Qdrant Edge storage directory: %s",
                    app_settings.edge_storage_path.resolve())
        logger.info("Active local embedding model: '%s' (dim=%d)",
                    app_settings.embedding_model_name, app_settings.vector_size)

        # 1. Embedding service
        embedding_service = get_embedding_service(
            model_name=app_settings.embedding_model_name,
            dimension=app_settings.embedding_dimension,
            cache_dir=app_settings.embedding_cache_dir,
        )

        # 2. Qdrant Edge
        client = EdgeClient(app_settings.edge_storage_path)
        shard = initialize_experience_collection(client, app_settings)
        repository = ExperienceRepository(shard, client, app_settings)
        query_parser = LocalQueryParser(settings=app_settings)

        # 3. Local User Memory & Personalization Substrate (Phase 2C)
        from app.memory.repository import MemoryRepository
        from app.memory.service import UserMemoryService
        memory_repo = MemoryRepository(app_settings.user_memory_path)
        memory_service = UserMemoryService(memory_repo, repository)

        # 4. Edge-to-Server Sync Substrate (Phase 2D)
        from app.sync import SyncClient, SyncRepository, SyncService
        sync_repo = SyncRepository(app_settings.sync_checkpoint_path)
        sync_client = SyncClient(
            server_url=app_settings.sync_server_url,
            timeout_seconds=app_settings.sync_timeout_seconds,
            api_key=app_settings.sync_api_key,
        )
        sync_service = SyncService(
            sync_repo=sync_repo,
            sync_client=sync_client,
            experience_repo=repository,
            embedding_service=embedding_service,
            settings=app_settings,
        )

        # 5. Metrics collector (Phase 3D)
        metrics = get_metrics_collector()

        # 6. Rate limiters (Phase 3C)
        search_limiter = RateLimiter(
            max_requests=app_settings.rate_limit_search_requests,
            window_seconds=app_settings.rate_limit_search_window_seconds,
        )
        sync_limiter = RateLimiter(
            max_requests=app_settings.rate_limit_sync_requests,
            window_seconds=app_settings.rate_limit_sync_window_seconds,
        )

        # Attach to application state for dependency injection
        app.state.settings = app_settings
        app.state.embedding_service = embedding_service
        app.state.edge_client = client
        app.state.edge_shard = shard
        app.state.repository = repository
        app.state.query_parser = query_parser
        app.state.memory_repo = memory_repo
        app.state.memory_service = memory_service
        app.state.sync_repo = sync_repo
        app.state.sync_client = sync_client
        app.state.sync_service = sync_service
        app.state.metrics = metrics
        app.state.search_limiter = search_limiter
        app.state.sync_limiter = sync_limiter

        # 7. Local OpenStreetMap Routing Engine
        from app.routing.service import get_routing_service
        routing_service = get_routing_service(
            load_local=app_settings.routing_local_enabled,
        )
        app.state.routing_service = routing_service

        # 7. Seed initial dataset if collection is empty
        if app_settings.auto_seed_on_startup:
            try:
                seed_database(
                    repository,
                    app_settings,
                    embedding_service=embedding_service,
                    overwrite=False,
                )
            except Exception as e:
                logger.error("Error during auto-seeding: %s", e)

        # 8. Optionally trigger background synchronization
        if app_settings.sync_enabled and app_settings.sync_server_url:
            try:
                sync_service.start_background_sync()
            except Exception as e:
                logger.error("Failed to start background sync worker: %s", e)

        logger.info("Qdrant Edge local substrate initialized successfully.")
        yield

        # ---- Shutdown ------------------------------------------------------
        logger.info("Shutting down Qdrant Edge substrate, sync worker, and local user memory...")
        sync_service.stop_background_sync()
        memory_repo.close()
        client.close()
        logger.info("Qdrant Edge shards and user memory closed cleanly.")

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "Offline-first city experiences discovery platform powered by Qdrant Edge "
            "and local FastEmbed embeddings as the local intelligence substrate."
        ),
        lifespan=lifespan,
    )

    # -----------------------------------------------------------------------
    # Middleware 1: X-Request-ID propagation (Phase 3B)
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        logger.debug(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
            request_id, request.method, request.url.path,
            response.status_code, duration_ms,
        )
        return response

    # -----------------------------------------------------------------------
    # Middleware 2: Security headers (Phase 3C)
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "X-Permitted-Cross-Domain-Policies", "none"
        )
        return response

    # -----------------------------------------------------------------------
    # Middleware 3: CORS
    # -----------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Exception handlers — include request_id in envelope (Phase 3B/3C)
    # -----------------------------------------------------------------------

    def _get_request_id(request: Request) -> str:
        return getattr(request.state, "request_id", "unknown")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            code = detail["code"]
            msg = detail["message"]
            details = detail.get("details")
        else:
            msg = str(detail)
            code_map = {
                400: "INVALID_REQUEST",
                404: "NOT_FOUND",
                422: "VALIDATION_ERROR",
                429: "RATE_LIMITED",
                500: "INTERNAL_SERVER_ERROR",
                503: "SERVICE_UNAVAILABLE",
            }
            code = code_map.get(exc.status_code, "HTTP_ERROR")
            details = None

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": msg,
                    "details": details,
                    "request_id": _get_request_id(request),
                },
                "detail": msg,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = exc.errors()
        first_msg = errors[0]["msg"] if errors else "Validation failed"
        loc = " -> ".join(str(l) for l in errors[0]["loc"]) if errors and "loc" in errors[0] else ""
        full_msg = f"Invalid request: {loc} ({first_msg})" if loc else f"Invalid request: {first_msg}"
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": full_msg,
                    "details": errors,
                    "request_id": _get_request_id(request),
                },
                "detail": full_msg,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):
        req_id = _get_request_id(request)
        logger.exception(
            "Unhandled exception during request processing [request_id=%s]: %s",
            req_id, type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred while processing your request.",
                    "request_id": req_id,
                },
                "detail": "An unexpected error occurred while processing your request.",
            },
        )

    app.include_router(router)

    # Mount Frontend SPA
    from pathlib import Path
    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        from starlette.staticfiles import StaticFiles
        app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="ui")

    @app.get("/", tags=["Overview"])
    def root():
        return {
            "name": app_settings.app_name,
            "version": app_settings.app_version,
            "architecture": "Qdrant Edge + Local FastEmbed In-Process Substrate",
            "phase": "Phase 2D + Phase 3 — Production Hardening",
            "environment": app_settings.environment,
            "embedding_model": app_settings.embedding_model_name,
            "embedding_dimension": app_settings.vector_size,
            "has_sparse_bm25": True,
            "has_query_understanding": True,
            "has_user_memory": True,
            "has_catalog_sync": True,
            "has_metrics": True,
            "is_offline_only": True,
            "endpoints": {
                "ui": "/ui",
                "health": "/health",
                "live": "/live",
                "ready": "/ready",
                "metrics": "/metrics",
                "diagnostics": "/api/diagnostics",
                "edge_status": "/edge/status",
                "search": "/search",
                "get_experience": "/api/experiences/{id}",
                "seed": "/api/experiences/seed",
                "bookmarks": "/api/users/{user_id}/bookmarks",
                "preferences": "/api/users/{user_id}/preferences",
                "sync_status": "/api/sync/status",
                "sync_run": "/api/sync/run",
                "sync_manifest": "/api/sync/manifest",
                "documentation": "/docs",
            },
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
