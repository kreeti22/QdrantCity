# ============================================================================
# QdrantCinema Edge Platform — Production Dockerfile
# Phase 3E: Deployment Packaging
# ============================================================================
# Build image:   docker build -t qdrant-cinema-edge .
# Run container: docker-compose up
# ============================================================================

FROM python:3.11-slim

# Metadata
LABEL org.opencontainers.image.title="QdrantCinema Edge Platform"
LABEL org.opencontainers.image.description="Offline-first city experiences discovery powered by Qdrant Edge"
LABEL org.opencontainers.image.version="0.6.0"

WORKDIR /app

# Install system build dependencies (required for some FastEmbed/ONNX wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Pre-download FastEmbed ONNX model during image build ----
# This ensures 100% offline operation at runtime — no network calls needed.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# ---- Application source ----
COPY app/ ./app/
COPY data/osm/ ./data/osm/
COPY data/seed/ ./data/seed/
COPY frontend/ ./frontend/

# ---- Default environment variables ----
# These can be overridden at container runtime or via docker-compose.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    QDRANT_EDGE_ENVIRONMENT="production" \
    QDRANT_EDGE_LOG_LEVEL="INFO" \
    QDRANT_EDGE_HOST="0.0.0.0" \
    QDRANT_EDGE_PORT="8000" \
    QDRANT_EDGE_EDGE_STORAGE_PATH="/app/data/edge" \
    QDRANT_EDGE_USER_MEMORY_PATH="/app/data/memory/user_memory.db" \
    QDRANT_EDGE_SYNC_CHECKPOINT_PATH="/app/data/sync/sync_checkpoint.json" \
    QDRANT_EDGE_EMBEDDING_MODEL_NAME="BAAI/bge-small-en-v1.5" \
    QDRANT_EDGE_VECTOR_SIZE="384" \
    QDRANT_EDGE_AUTO_SEED_ON_STARTUP="true"

# ---- Persistent volumes ----
# Mount /app/data for durable storage of:
#   /app/data/edge       — Qdrant Edge shard (vectors + payloads)
#   /app/data/memory     — SQLite user memory
#   /app/data/sync       — Sync checkpoint state
VOLUME ["/app/data"]

# ---- Health check ----
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/live || exit 1

EXPOSE 8000

# Run with uvicorn — workers=1 because Qdrant Edge is an in-process singleton.
# Render supplies PORT; the default keeps local Docker usage on port 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
