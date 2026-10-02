# QdrantCity — Local Intelligence Substrate

> **Architectural Principle:** Qdrant Edge is the local intelligence substrate, not an add-on vector database.

QdrantCity is an **offline-first city experiences & event discovery platform** powered by Qdrant Edge running fully in-process — no cloud LLM, no external embedding API, no external search server.

## ⚡ Quick Start (5 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server (auto-seeds 115 experiences on first run)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Open the discovery UI (served by FastAPI)
#    http://localhost:8000/

# 4. Or use Docker
#    docker-compose up --build
```

**Key endpoints:**
| URL | Purpose |
|---|---|
| `http://localhost:8000/` | Discovery & Routing UI |
| `http://localhost:8000/ui` | Compatibility URL for the UI |
| `http://localhost:8000/docs` | Interactive API docs |
| `http://localhost:8000/route` | Local OSM shortest path routing |
| `http://localhost:8000/api/routing/status` | Road graph diagnostics |
| `http://localhost:8000/live` | Liveness probe |
| `http://localhost:8000/metrics` | Operational metrics |

**What makes it different:**
- 🔒 **100% offline** — all embeddings, search, local OSM graph, and memory run locally on CPU
- 🗺️ **Offline Road Network Routing** — Dijkstra shortest-path navigation using local OpenStreetMap road graph (62k+ nodes)
- 📍 **Location-Aware Experiences** — movies and events geocoded with real coordinates and instant routing
- 🧠 **Hybrid retrieval** — dense semantic (FastEmbed) + sparse BM25 fused via RRF
- 🎯 **Local query understanding** — parses "comedy tonight under $50" deterministically, no LLM
- 💾 **Privacy-first user memory** — bookmarks + preferences stored in local SQLite only
- 🔄 **Optional catalog sync** — pull catalog updates from a central server when online
- 158+ automated tests passing

## Deploy to Render

This repository includes a [`render.yaml`](render.yaml) Blueprint for a Docker web service. In Render, choose **New > Blueprint**, connect the repository, and deploy the `qdrantcity` service. The Blueprint provisions a persistent `/app/data` disk for the Qdrant Edge shard, SQLite memory, and sync checkpoint.

The container binds to Render's injected `PORT` and exposes `/live` as its health check. The first build downloads the local FastEmbed model into the image, so the initial deploy can take several minutes. The free Render configuration disables the memory-heavy local road graph and uses OSRM/direct fallback routing. Because free services do not provide persistent disks, the local Edge catalog and SQLite memory can reset after a restart; the catalog is automatically reseeded on startup.

For a custom frontend origin, replace `QDRANT_EDGE_CORS_ORIGINS` in `render.yaml` with the deployed origin or configure that environment variable in the Render dashboard.

---

## Phase 1D: Local Query Understanding & Structured Intent

Phase 1D implements a deterministic, local Query Understanding layer that converts a user's natural-language search query into structured search intent (`StructuredSearchIntent`), extracts strict payload filters, and safely connects them to the existing hybrid retrieval engine (FastEmbed dense + native Qdrant Edge BM25 + RRF) while **always preserving the original query** for semantic context.

```text
                             USER QUERY
                                 ↓
                     Local Query Understanding
                    (Deterministic Pattern Parser)
                                 ↓
            ┌─────────────────────────────────────────┐
            │ Structured Intent & Safe Filter Builder │
            │ + Preserved Original & Semantic Query   │
            └────────────────────┬────────────────────┘
                                 ↓
                    Hybrid Retrieval Execution
                    ↙                         ↘
         Dense Semantic Branch              Sparse Lexical Branch
      (FastEmbed / bge-small-en-v1.5)      (Native Qdrant Edge BM25)
                    ↓                                 ↓
            Dense Retrieval                    BM25 Retrieval
        (Qdrant Edge: using='dense')      (Qdrant Edge: using='bm25')
        [Qdrant Pre-fusion Intent Filters] [Qdrant Pre-fusion Intent Filters]
                    ↓                                 ↓
         Top-20 Dense Candidates           Top-20 BM25 Candidates
                    ↘                         ↙
                    Reciprocal Rank Fusion (RRF)
                                 ↓
                      Final Ranked Result List
```

---

## 1. Verified Technology Stack & Models

* **Python:** `3.11.9`
* **Qdrant Edge Package:** `qdrant-edge-py == 0.8.0` (with `qdrant-client == 1.19.1`)
  * **In-Process Shard:** Native `EdgeShard` with dual named vectors (`dense` and `bm25`)
  * **Sparse Vector Engine:** Native in-process `qdrant_edge.Bm25` tokenizer and indexer
  * **Indexed Payload Fields:** `category`, `city`, `neighborhood`, `venue`, `price`, `is_indoor`, `rating`, `subcategories`, `start_time`, `end_time`
* **Local Embedding Package:** `fastembed == 0.8.1` (with `onnxruntime == 1.30.0`)
  * **Dense Model:** `BAAI/bge-small-en-v1.5` (dimension: 384, Cosine distance)
* **Local Clock & Timezone Provider:** Centralized `TimeProvider` (`app/utils/clock.py`) with configurable timezone (default `UTC`) and default reference datetime `2026-10-15T12:00:00Z`
* **Query Understanding Engine:** Deterministic rule-based parser (`LocalQueryParser`) running in ~0.5ms on local CPU with zero network dependencies
* **Fusion Strategy:** Reciprocal Rank Fusion (RRF) with default smoothing constant $k = 60$
* **Candidate Pools:** Dense Top-20, BM25 Top-20 -> Final Top-10
* **API Framework:** `fastapi == 0.141.1`
* **Data Validation:** `pydantic == 2.13.5`, `pydantic-settings == 2.15.0`
* **Test Suite:** `pytest == 9.1.1` (55 automated unit and integration tests)

> **Local-Only Runtime Guarantee:**  
> All query parsing, dense embeddings, BM25 sparse vectors, and Qdrant Edge shard queries run **100% locally on CPU without an Internet connection, without API keys, and without external network calls**.

---

## 2. Query Understanding Architecture & Intent Model

The `StructuredSearchIntent` model explicitly distinguishes between:
1. **Hard Constraints:** Deterministic filters that must be satisfied in the dataset (category, city, neighborhood, venue, price max/min, indoor/outdoor, date/time bounds, formats, languages, negations).
2. **Semantic Descriptors:** Emotional, contextual, or descriptive tokens retained in `semantic_query` for dense and lexical vector retrieval (e.g. "relaxing", "scary", "hilarious", "acoustic").
3. **Ambiguous Signals:** Terms like "around 1000" or "cheap" that lack explicit mathematical boundaries remain semantic signals to prevent over-filtering.

### Query Intent Schema (`StructuredSearchIntent`)

```python
class StructuredSearchIntent(BaseModel):
    original_query: str                          # Original query preserved untouched
    semantic_query: str = ""                     # Descriptors retained for vectorization
    category: Optional[ExtractedField[str]]      # e.g. "comedy", "movies", "concerts"
    city: Optional[ExtractedField[str]]          # e.g. "San Francisco"
    neighborhood: Optional[ExtractedField[str]]  # e.g. "Mission", "SOMA", "Marina"
    venue: Optional[ExtractedField[str]]         # e.g. "Castro Theatre"
    date: Optional[ExtractedField[str]]          # ISO Date: YYYY-MM-DD
    start_time: Optional[ExtractedField[str]]    # Time: HH:MM:SS
    end_time: Optional[ExtractedField[str]]      # Time: HH:MM:SS
    time_period: Optional[ExtractedField[str]]   # "morning", "afternoon", "evening", "night"
    price_min: Optional[ExtractedField[float]]   # Minimum price threshold
    price_max: Optional[ExtractedField[float]]   # Maximum price threshold
    currency: Optional[str]                      # e.g. "USD", "INR"
    is_indoor: Optional[ExtractedField[bool]]    # True (indoor) or False (outdoor)
    language: Optional[ExtractedField[str]]      # e.g. "English", "Japanese", "Spanish"
    format: Optional[ExtractedField[str]]        # e.g. "IMAX", "3D", "70mm"
    radius_km: Optional[ExtractedField[float]]   # Distance radius constraint
    location_required: bool = False              # True when radius or "near me" present
    excluded_categories: List[str]               # Negative category filters
    excluded_subcategories: List[str]            # Negative subcategory filters (e.g. horror)
    themes: List[str]                            # Thematic tokens
    unresolved_terms: List[str]                  # Ambiguous expressions
    parse_latency_ms: float                      # Extraction latency (typically < 1ms)
```

---

## 3. Supported Query Expressions

| Expression Type | Natural Language Examples | Structured Field Extracted | Qdrant Filter Action |
| :--- | :--- | :--- | :--- |
| **Category** | "movies", "standup comedy", "rock concerts", "art exhibitions", "pottery workshops", "sports match" | `category` (enum) | `FieldCondition(key="category", match=MatchValue(...))` |
| **Price (Upper)** | "under 30", "below $25", "less than 50 dollars", "up to 40" | `price_max` (float) | `FieldCondition(key="price", range=RangeFloat(lte=...))` |
| **Price (Range)** | "between 15 and 35 dollars" | `price_min`, `price_max` | `FieldCondition(key="price", range=RangeFloat(gte=..., lte=...))` |
| **Price (Free)** | "free festival", "free admission" | `price_max = 0.0` | `FieldCondition(key="price", range=RangeFloat(lte=0.0))` |
| **Relative Date** | "today", "tonight", "tomorrow", "this weekend", "friday" | `date` (YYYY-MM-DD) | `FieldCondition(key="start_time", range=RangeDateTime(gte=..., lte=...))` |
| **Time Period** | "morning", "afternoon", "evening", "night" | `time_period` | Time boundary window combined with date |
| **Specific Time** | "after 8pm", "before 6 pm" | `start_time`, `end_time` | Precise `RangeDateTime` timestamp boundary |
| **Neighborhood** | "in Mission", "in SOMA", "Marina", "North Beach", "Castro" | `neighborhood` | `FieldCondition(key="neighborhood", match=MatchValue(...))` |
| **Venue** | "at Castro Theatre", "The Fillmore", "SFMOMA" | `venue` | `FieldCondition(key="venue", match=MatchValue(...))` |
| **Format** | "IMAX", "3D", "70mm", "4DX" | `format` | `FieldCondition(key="subcategories", match=MatchValue(...))` |
| **Language** | "Japanese anime", "Spanish film", "French", "Korean" | `language` | `FieldCondition(key="subcategories", match=MatchValue(...))` |
| **Environment** | "outdoor festival", "indoor pottery" | `is_indoor` (bool) | `FieldCondition(key="is_indoor", match=MatchValue(1 or 0))` |
| **Negation** | "not horror", "no comedy", "not 3D" | `excluded_categories`, `excluded_subcategories` | `must_not=[FieldCondition(key=..., match=MatchValue(...))]` |
| **Radius / Proximity** | "within 5 km", "near me" | `radius_km`, `location_required=True` | Flags location requirement safely (no GPS spoofing) |
| **Ambiguous Terms** | "around 1000", "cheap", "after 8" (no am/pm) | `unresolved_terms` | Left in semantic query, **no hard filter invented** |

---

## 4. Benchmark Results: Baseline Hybrid vs Query Understanding + Hybrid

Benchmark evaluation executed on the local Qdrant Edge shard with 115 points across 10 structured intent queries (5 runs each, total 100 retrieval passes) on local CPU:

### Quality & Latency Comparison

| Metric | Baseline Hybrid (No QU) | Query Understanding + Hybrid | Impact |
| :--- | :---: | :---: | :--- |
| **Recall@5** | 51.15% | 50.47% | Strict hard-filtering prevents off-constraint candidates |
| **Recall@10** | 74.29% | **79.02%** | **+4.73% improvement** in top-10 candidate quality |
| **Query Parse P50** | *N/A* | **0.48 ms** | Sub-millisecond deterministic parsing |
| **Query Parse P95** | *N/A* | **0.56 ms** | Reliable, predictable CPU rule execution |
| **Query Parse P99** | *N/A* | **0.78 ms** | Zero external API latency |
| **Total Latency P50** | 10.05 ms | **9.65 ms** | Pre-filtering reduces vector distance comparisons |
| **Total Latency P95** | 32.66 ms | **28.95 ms** | Faster candidate search space narrowing |
| **Total Latency P99** | 44.26 ms | **37.31 ms** | Consistent performance |
| **Mean Total Latency** | 13.94 ms | **12.55 ms** | 1.39 ms faster average end-to-end response |

### Notable Query Retrieval Highlights

* **`"standup comedy under 30"`**: Baseline Recall@5: 50% → **QU Recall@5: 67%** (strictly eliminates shows above $30).
* **`"free outdoor festival"`**: Baseline Recall@5: 67% → **QU Recall@5: 100%** (eliminates paid indoor festivals).
* **`"movies not horror"`**: Baseline Recall@5: 18% → **QU Recall@5: 36%** (excludes all horror subcategories upstream via `must_not`).

---

## 5. Automated Test Suite (55 Tests)

```powershell
.\.venv\Scripts\python -m pytest -v
```

All 55 tests pass cleanly in ~1.5 minutes:
* `tests/test_query_parser.py`: 10 unit tests for deterministic category, price, date, time, location, format, language, negation, and ambiguity handling.
* `tests/test_filter_builder.py`: 6 unit tests for safe filter compilation, RangeDateTime UTC bounds, negations, and override handling.
* `tests/test_query_understanding_integration.py`: 6 end-to-end integration tests verifying API search, intent extraction, and filter enforcement.
* `tests/test_rrf.py`: 5 tests verifying exact RRF arithmetic, deduplication, and rank fusion.
* `tests/test_hybrid_retrieval.py`: 5 tests verifying exact keyword, dense semantic, pre-fusion filtering, and API modes.
* `tests/test_embedding_service.py`: 5 tests for FastEmbed determinism and dimensionality.
* `tests/test_semantic_retrieval.py`: 4 tests for semantic search relevance and ingestion.
* `tests/test_edge_foundation.py`: 4 tests for EdgeShard initialization, vector search, and payload filtering.
* `tests/test_api.py`: 9 tests for FastAPI diagnostic, health, and search routes.
* `tests/test_persistence.py`: 1 test verifying data durability across restarts.

---

## 6. Execution Commands

### 1. Run Automated Test Suite
```powershell
.\.venv\Scripts\python -m pytest -v
```

### 2. Run Query Understanding Benchmark
```powershell
.\.venv\Scripts\python scripts/benchmark_query_understanding.py
```

### 3. Start Local API Server
```powershell
.\.venv\Scripts\uvicorn app.main:app --port 8000
```

### 4. Search API Example
```powershell
curl -X POST "http://127.0.0.1:8000/api/experiences/search" `
  -H "Content-Type: application/json" `
  -d '{"query": "standup comedy under 30 in San Francisco", "mode": "hybrid", "limit": 5}'
```

Response includes original query, distilled semantic query, complete structured intent, latency breakdown including `query_parsing_ms`, and fused search results:
```json
{
  "query": "standup comedy under 30 in San Francisco",
  "semantic_query": "standup",
  "mode": "hybrid",
  "total_returned": 5,
  "latency_ms": {
    "embedding_ms": 11.23,
    "search_ms": 1.15,
    "total_ms": 13.08,
    "dense_embedding_ms": 11.21,
    "dense_search_ms": 0.72,
    "bm25_embedding_ms": 0.02,
    "bm25_search_ms": 0.25,
    "query_parsing_ms": 0.48,
    "fusion_ms": 0.18
  },
  "filters_applied": {
    "category": "comedy",
    "city": "San Francisco",
    "max_price": 30.0
  },
  "intent": {
    "original_query": "standup comedy under 30 in San Francisco",
    "semantic_query": "standup",
    "category": {"value": "comedy", "confidence": "high", "source": "explicit"},
    "price_max": {"value": 30.0, "confidence": "high", "source": "explicit"},
    "city": {"value": "San Francisco", "confidence": "high", "source": "explicit"},
    "location_required": false
  },
  "results": [...]
}
```

---

## Phase 2A: Hardened Backend & Frontend-Ready API Contract

Phase 2A hardens the backend into a clean, stable, frontend-ready API contract for downstream UI consumption while maintaining 100% offline-first execution and backwards compatibility with earlier phases.

### 1. Hardened API Endpoints
* `POST /api/experiences/search` & `POST /search`: Primary natural-language search with structured intent and RRF hybrid retrieval. Accepts:
  * Minimal payload: `{"query": "comedy tonight under ₹1000"}`
  * Advanced payload with filters/pagination/mode overrides: `{"query": "...", "limit": 10, "filters": {"category": "movies"}, "mode": "hybrid", "enable_intent": true}`
  * Input validation: Empty or whitespace query returns HTTP 400 (`INVALID_QUERY`), query > 500 characters returns HTTP 400 (`QUERY_TOO_LONG`), zero matches return HTTP 200 with `results: []`.
* `GET /api/experiences/{id}` & `GET /experiences/{id}`: Detailed card retrieval by ID. Returns HTTP 404 with standardized error envelope if not found.
* Probes & Diagnostics:
  * `GET /live`: Instant liveness probe for process supervisors.
  * `GET /ready`: Readiness probe verifying storage and vector model availability.
  * `GET /health`: Comprehensive status including experience count, storage path, dimension, and uptime.

### 2. Normalized Result Schema
Search results elevate all UI card fields to the top level of each result item for direct consumption by frontend components, while preserving the full `payload` and rank scores for backwards compatibility:
```json
{
  "id": 31,
  "title": "Late Night Underground Standup Comedy Showcase",
  "category": "comedy",
  "description": "Raw, unfiltered standup comedy featuring rising underground comics and surprise headliners.",
  "venue": "The Purple Onion",
  "city": "San Francisco",
  "neighborhood": "North Beach",
  "start_time": "2026-10-15T22:00:00Z",
  "end_time": "2026-10-15T23:30:00Z",
  "price": 22.0,
  "currency": "USD",
  "image_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819",
  "subcategories": ["standup", "underground", "late night"],
  "language": "English",
  "is_indoor": true,
  "rating": 4.6,
  "score": 0.032786,
  "payload": { ... }
}
```

### 3. Standardized Error Envelope
All error responses adhere to a uniform structure:
```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "Query string cannot be empty or whitespace only.",
    "details": null
  },
  "detail": "Query string cannot be empty or whitespace only."
}
```

### 4. Configuration & Deployment Settings
Configurable via environment variables with safe offline defaults:
* `QDRANT_EDGE_HOST`: Server bind address (default: `0.0.0.0`)
* `QDRANT_EDGE_PORT`: Server port (default: `8000`)
* `QDRANT_EDGE_ENVIRONMENT`: Runtime environment (default: `development`)
* `QDRANT_EDGE_CORS_ORIGINS`: Allowed origins as comma-separated string or JSON array (default: `*`)
* `QDRANT_EDGE_MAX_QUERY_LENGTH`: Maximum permitted query length in characters (default: `500`)

---

## Phase 2B: Frontend Discovery UI Foundation

Phase 2B delivers a modern, responsive Single Page Application (SPA) discovery interface for QdrantCinema built with vanilla modern ES modules (zero bundlers, zero npm dependencies, zero build steps) communicating directly with the backend API.

### 1. Architecture & Component Hierarchy
```text
frontend/
├── api/
│   └── client.js             # Centralized API client (search, detail, ready)
├── components/
│   ├── SearchBar.js          # Natural-language search bar with keyboard & loading states
│   ├── QueryChips.js         # Clickable popular search chips (comedy tonight, etc.)
│   ├── FilterBar.js          # Lightweight controls (category, max price, indoor/outdoor)
│   ├── ExperienceCard.js     # Responsive experience card with image fallback & tags
│   ├── ResultsGrid.js        # Card grid with count header & local latency telemetry
│   ├── EmptyState.js         # Friendly empty state with query broadening recommendations
│   ├── ErrorState.js         # Error banner with query preservation and retry action
│   └── ExperienceDetail.js   # Full modal overlay for GET /api/experiences/{id}
├── pages/
│   └── DiscoveryPage.js      # App coordinator & state machine
├── utilities/
│   └── formatting.js         # Human-readable date/time, price, score, and badge formatters
├── styles/
│   └── main.css              # Cinematic dark theme, responsive grid & typography
├── config.js                 # Centralized configuration with dynamic API base URL
├── index.html                # Single-page application entry point
└── .env.example              # Example environment configuration
```

### 2. Running the Application
The discovery interface can be accessed in two ways:

#### Option A: Unified FastAPI Serving (Recommended)
FastAPI automatically mounts the frontend at `/ui`:
```powershell
.\.venv\Scripts\uvicorn app.main:app --port 8000
```
Open in browser:
```text
http://localhost:8000/ui
```

#### Option B: Standalone Frontend Server
Run frontend on an independent port (e.g. 3000):
```powershell
python -m http.server 3000 --directory frontend
```
Open in browser:
```text
http://localhost:3000
```
*(Backend CORS is pre-configured to accept requests from all origins).*

---

## 7. Phase 2C: Durable Semantic User Memory & Personalization

Phase 2C adds a lightweight, local, privacy-preserving user preference and interaction-memory layer to QdrantCinema using native SQLite (`data/memory/user_memory.db`). It enables personalized discovery based on user interactions while guaranteeing that **all memory remains strictly local to the device**.

```text
USER INTERACTION (Search / View / Bookmark)
                     ↓
       Local SQLite Memory Repository
      (data/memory/user_memory.db)
     ├── bookmarks (user_id, exp_id, title, category, price)
     ├── interactions (bounded to 200 items per user)
     └── user_profiles (cached preference profiles)
                     ↓
    Deterministic Preference Extraction
      (Weights: Bookmark 5.0 > View 2.0 > Search 1.0)
                     ↓
       Qdrant Edge Hybrid RRF Retrieval
                     ↓
      Modest Personalization Re-ranking
     S_final = S_rrf * (1.0 + 0.20 * S_affinity)
                     ↓
   Ranked Results + Personalization Telemetry
  {"enabled": true, "applied": true, "signals_used": [...]}
```

### 1. Memory Architecture & Privacy
* **Local SQLite Store:** Stored at `data/memory/user_memory.db`. No cloud database, no external telemetry.
* **Bounded Storage:** Interactions are strictly capped at 200 entries per user with automatic FIFO trimming.
* **Cold Start & Degradation:** Unseen or interaction-free users seamlessly receive unpersonalized pure RRF results with `applied: false`.
* **Zero Cloud Dependence:** All affinity calculations and scoring adjustments run in-process on CPU.

### 2. Personalization Formula
A modest personalization multiplier ($\alpha = 0.20$, 20% max adjustment) ensures that relevance is preserved while prioritizing user preferences:
$$S_{final} = S_{rrf} \times (1.0 + \alpha \times \min(S_{affinity}, 1.0))$$

Signals used:
* **Category Affinity (up to 0.50):** Derived from bookmarks, card views, and search query terms.
* **Subcategory Affinity (up to 0.25):** Derived from specific event subcategories and tags.
* **Price Compatibility (up to 0.25):** Rewards experiences aligned with the user's historical price range.

### 3. API Endpoints
* `POST /api/users/{user_id}/bookmarks/{experience_id}`: Saves an experience and updates memory.
* `DELETE /api/users/{user_id}/bookmarks/{experience_id}`: Removes an experience from bookmarks.
* `GET /api/users/{user_id}/bookmarks`: Lists all saved experiences with card metadata.
* `GET /api/users/{user_id}/preferences`: Returns inferred category affinities, average price, and indoor bias.
* `DELETE /api/users/{user_id}/memory`: Purges all bookmarks, interactions, and profile data for that user.
* `POST /api/users/{user_id}/interactions`: Records a custom interaction event (e.g. view or search).
* `POST /api/experiences/search`: Supports optional `user_id` and `personalize` flags; returns `personalization` telemetry.

### 4. Frontend Integration
* **Card Bookmark Toggle:** Interactive bookmark icon on every experience card with optimistic UI updates.
* **"Saved (N)" View:** Header button to filter the view directly to saved experiences.
* **Personalization Badge:** Displays `✨ Personalized for you` alongside execution latency when personal re-ranking was applied.
* **Privacy Badge & Reset:** Header displays `🔒 Local Device Memory` and provides a "Reset Memory" action for explicit user data purge.

---

## 8. Phase 2D: Edge-to-Server Synchronization

Phase 2D adds a safe, selective synchronization mechanism that allows a local Qdrant Edge shard to receive catalog updates from a central server while keeping the application fully functional when offline or when the server is unavailable.

> **Key Architectural Guarantee:**  
> **QdrantCinema remains fully usable without synchronization. Sync is an optional catalog-update mechanism, not a runtime dependency.**

```text
                    CENTRAL CATALOG / SERVER
                              │
                    Selective Sync API
                              │
                    ┌─────────▼─────────┐
                    │ Sync Manifest      │
                    │ version / checksum │
                    │ added / updated     │
                    │ deleted IDs        │
                    └─────────┬─────────┘
                              │
                      Local Sync Engine
                  (app/sync/service.py)
                              │
                    ┌─────────▼─────────┐
                    │ Qdrant Edge Shard  │
                    │ local catalog      │
                    └─────────┬─────────┘
                              │
                    Existing Hybrid Search
                              │
                  Dense + BM25 + RRF + Memory
```

### 1. Synchronization Architecture & Guarantees
* **Incremental Vector Updates:** Only added or updated experiences are fetched and vectorized via local FastEmbed and BM25. Unchanged records are never re-embedded.
* **Deletion Safety:** Deleted items are pruned directly from the Edge shard using `UpdateOperation.delete_points` without clearing the collection.
* **Atomicity & Checkpoints:** The local checkpoint (`data/sync/sync_checkpoint.json`) is advanced **only after all batch upserts and deletions succeed**. If any batch fails, the previous checkpoint is retained and retried safely on the next cycle.
* **Non-Blocking Startup:** Synchronization runs in the background and never blocks server startup, readiness probes (`/ready`), or search availability.
* **Zero User Data Leakage:** User bookmarks, interactions, preferences, and search queries are strictly excluded from all sync calls and manifests.

### 2. Configuration Options
Configured via environment variables (`QDRANT_EDGE_*`) or `.env`:
* `sync_enabled`: Enables background/manual sync (default: `False`).
* `sync_server_url`: Base URL of central catalog server (e.g. `https://catalog.qdrantcinema.app`).
* `sync_interval_seconds`: Background sync cycle duration (default: `3600` seconds / 1 hour).
* `sync_timeout_seconds`: HTTP request timeout (default: `10.0` seconds).
* `sync_batch_size`: Bounded experience download batch size (default: `50`).
* `sync_max_items_per_run`: Safety limit per sync cycle (default: `500`).
* `sync_checkpoint_path`: Checkpoint file location (default: `data/sync/sync_checkpoint.json`).

### 3. API Endpoints
* `GET /api/sync/status`: Inspects local synchronization state, last success timestamp, catalog version, and item delta counts.
* `POST /api/sync/run`: Triggers an immediate synchronization run with optional `force=true`.
* `GET /api/sync/manifest`: Server-side endpoint exposing the current catalog version, dataset checksum, and diff changes.
* `GET /api/sync/experiences`: Server-side endpoint streaming experience records for specific IDs.

### 4. Diagnostic Probes
* `GET /health`: Safely exposes `sync_enabled`, `catalog_version`, `last_successful_sync`, and `sync_status`.
* `GET /ready`: Confirms shard readiness and points count. Never fails solely because the sync server is unreachable.

---

## 9. Offline Verification & Test Suite

1. **Local Model Caching:** FastEmbed model weights are stored locally in `data/models/cache`. No internet connection is requested or needed at runtime.
2. **Deterministic Query Parser:** Uses compiled regex tokenizers, pattern matchers, and bounded dictionaries. Zero external NLP libraries or cloud LLM endpoints.
3. **In-Process Qdrant Edge:** Native Rust binaries run within the Python process accessing local storage in `data/edge/city_experiences`.
4. **Local SQLite Memory Substrate:** Self-contained file database at `data/memory/user_memory.db` with zero external database dependencies.
5. **Robust Offline Sync Engine:** Sync errors or unreachable servers do not affect startup or search. All sync tests mock external network traffic.
6. **Zero-Dependency Frontend:** Native browser ES modules running in standard modern browsers without external CDN or npm packages.
7. **Test Suite Coverage:** **150/150 automated tests passing** across production hardening (Phase 3), synchronization, memory repository, personalization re-ranking, bookmarks CRUD, frontend integration, API contracts, Qdrant Edge foundation, embedding service, BM25, filter builder, hybrid retrieval, and query understanding.

---

## 10. Phase 3 — Production Hardening, Deployment & Demo Readiness

Phase 3 hardened the platform for reliable hackathon demo and production-grade operation without introducing any new cloud services, Prometheus, or external dependencies.

### 3A — Production Configuration & Validation
All settings validated on startup with descriptive errors:
- `port`: 1–65535 | `personalization_boost_weight`: 0.0–1.0
- `sync_interval_seconds`: ≥ 30 | `sync_batch_size`: 1–1000
- `log_level`: `DEBUG | INFO | WARNING | ERROR | CRITICAL`

Copy `.env.example` to `.env` and customize. Fully documented and grouped by subsystem.

### 3B — Structured Logging & Request ID
Every HTTP request gets a `X-Request-ID` (generated or propagated). Echoed in response headers and included in all error envelopes. Response time in `X-Response-Time-Ms`. Log level via `QDRANT_EDGE_LOG_LEVEL`.

### 3C — Security Hardening
Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`. All errors include `request_id`. Optional in-process rate limiting for search/sync (disabled by default, no external service).

### 3D — Operational Metrics
`GET /metrics` — privacy-safe aggregate data, no personal data:
```json
{
  "uptime_seconds": 120.5,
  "search": { "total": 45, "latency_ms": { "p50": 42.0, "p95": 85.0, "p99": 120.0 } },
  "bookmarks": { "adds": 8, "removes": 2 },
  "sync": { "attempts": 0, "success": 0 }
}
```

### 3E — Deployment Packaging
```bash
docker-compose up --build
# UI: http://localhost:8000/ui
# API docs: http://localhost:8000/docs
# Health: http://localhost:8000/live
# Metrics: http://localhost:8000/metrics
```
Consolidated `/app/data` volume covers edge shards, SQLite user memory, and sync checkpoints.

### Hackathon Demo Flow (5-Minute Walkthrough)

**Startup Command:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

1. **Open `/ui`**: Navigate to `http://localhost:8000/ui` in your browser.
2. **Natural-Language Hybrid Search**: Enter queries like `"comedy tonight under $50"`.
3. **Semantic & BM25 Results**: Observe parsed intent, filters applied, and fused results with latency breakdown.
4. **Bookmark an Experience**: Click the bookmark icon on any card; counter updates in header.
5. **Personalized Search**: Search again (e.g. `"live shows"`) to trigger personalized ranking.
6. **`✨ Personalized for you`**: Verify the boost pill appears on preference-aligned experiences.
7. **`🔒 Local Device Memory`**: Highlight SQLite-backed private storage (zero tracking/telemetry).
8. **Catalog Sync Status**: Check header sync badge indicating local shard status.
9. **Operational Metrics**: Visit `http://localhost:8000/metrics` to show real-time query counts and P50/P95 latencies.
10. **Offline/Local Architecture**: Explain that FastEmbed, BM25, and Qdrant Edge run 100% locally in-process on CPU.

### 3H — Performance Benchmarks (Windows 11, Python 3.11, warm shard)

| Operation | P50 | P95 |
|---|---|---|
| Liveness probe | 23ms | — |
| Readiness probe | 6ms | — |
| `/metrics` | 4ms | — |
| Hybrid search (warm) | **52ms** | 77ms |
| Internal `total_ms` | 68ms | — |

Model load (~1.2s) is a one-time startup cost. All retrieval is fully local with no network calls.

---

## Offline Event & Movie Location Locator & Local OSM Routing

QdrantCinema includes an **in-process offline routing engine** powered by NetworkX and local OpenStreetMap (OSM) Delhi road network data:

```text
  User Location (GPS / Preset)               Event / Movie Venue (Qdrant Edge)
  (e.g., Connaught Place: 28.6315, 77.2167)   (e.g., PVR Director's Cut: 28.5429, 77.1557)
               \                                       /
                \                                     /
                 ▼                                   ▼
        Nearest OSM Road Node Snapping (<2ms, NumPy spatial index)
                                 ↓
            NetworkX Dijkstra Shortest-Path Graph Engine
                 (data/osm/delhi_roads.json: 62k+ nodes)
                                 ↓
                  100% Offline Route Calculation
                    (Latency: 5-25ms on CPU)
                                 ↓
           Interactive Vector Map UI (Local Leaflet 1.9.4)
          Polyline Route + Origin & Destination Markers + Telemetry
```

### Architecture Summary

1. **Qdrant Edge Local Retrieval:** In-process vector database (`qdrant-edge-py`) running dual dense vectors (FastEmbed `BAAI/bge-small-en-v1.5`, 384-dim) and BM25 sparse lexical vectors with Reciprocal Rank Fusion (RRF). Zero cloud calls.
2. **Local OSM Data:** Pre-packaged Delhi road network in `data/osm/delhi_roads.json` containing 62,817 intersections and 82,749 road segments.
3. **Local Route Calculation:** Fast nearest-node spatial snapping via vectorized NumPy Euclidean distances followed by NetworkX Dijkstra shortest-path routing over the road network graph.
4. **Online Fallback:** If coordinates fall outside the local OSM bounding box, requests seamlessly fall back to public OSRM (`router.project-osrm.org`). If the network is disconnected, it cleanly degrades to an offline direct geodesic trajectory.
5. **Attribution:** OpenStreetMap compliance via `"Map data © OpenStreetMap contributors"` attribution banner on all route responses and map displays.

### Routing Endpoints

- **`POST /route`** (or **`POST /api/route`**):
  - Request: `{"start": {"latitude": 28.6315, "longitude": 77.2167}, "destination": {"latitude": 28.5429, "longitude": 77.1557}}`
  - Response: GeoJSON LineString coordinates, `distance_km`, `duration_minutes`, `source: "local_osm"`, `is_offline: true`, and attribution: `"Map data © OpenStreetMap contributors"`.
- **`GET /api/routing/status`**:
  - Reports graph diagnostics: `node_count` (62,817), `edge_count` (82,749), bounding box, load duration, and availability.

### Offline Acceptance Demo Steps

To verify 100% offline operation:

1. **Start QdrantCity:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **Open the Web UI:**
   Navigate to `http://localhost:8000/ui` in your browser.
3. **Search Online / Connected:**
   - Search for `PVR movie Delhi` or click one of the query chips.
   - Select an experience card or open the details view.
   - Click **`[Route]`** to compute a route.
   - Confirm the badge displays **`LOCAL OSM ROUTE`** (with `100% OFFLINE` indicator and OSM attribution).
4. **Disconnect Internet:**
   - Disconnect Wi-Fi / Ethernet or disable network adapter.
5. **Search & Route Offline:**
   - Search for `Standup comedy` or `Dune Part Two`.
   - Results are retrieved instantaneously from local Qdrant Edge.
   - Click **`[Route]`** on any result.
   - Confirm the route is still calculated locally via local OSM NetworkX Dijkstra graph with polyline geometry rendered completely offline.
---

## 11. Phase 4: TrekAI - Fully Offline Chatbot Integration

TrekAI is a **100% offline chatbot** integrated into QdrantCity that helps you discover events, plan routes, check management statistics, and get guidance on using the app - all without internet access.

### 11.1 Overview

TrekAI uses **local intent detection and template-based responses** to provide a conversational interface while maintaining the offline-first architecture of QdrantCity.

```text
                    USER QUERY
                         ↓
              Local Intent Detection
           (Rule-based, No External APIs)
                         ↓
        ┌────────────────────────────────┐
        │ Context Preservation           │
        │ - City                         │
        │ - Category                     │
        │ - Last Event Viewed            │
        │ - Recent Queries               │
        └──────────────┬─────────────────┘
                       ↓
              Intent Handler
        ┌──────────────┴─────────────────┐
        │ Event Discovery                │
        │ Event Details                  │
        │ Route Planning                 │
        │ Saved Events                   │
        │ Management Statistics          │
        │ App Guidance                   │
        └──────────────┬─────────────────┘
                       ↓
              Response Generation
           (Template + Local Data)
```

### 11.2 Key Features

| Feature | Description |
|---------|-------------|
| **100% Offline** | No cloud LLM, external APIs, or network calls |
| **Local Intent Detection** | Rule-based parsing with keyword matching |
| **Template Responses** | Grounded in local event data |
| **Voice Input** | Browser-based offline speech recognition |
| **Context Preservation** | Follow-up questions work correctly |
| **Privacy First** | All conversations stay on device |

### 11.3 Supported Queries

| Query Type | Examples |
|------------|----------|
| Greeting | "hello", "hi there", "good morning" |
| Event Search | "find sports events in Delhi", "show concerts tonight" |
| Event Details | "tell me about Dune", "event details" |
| Routes | "plan route", "how to get there", "navigate" |
| Statistics | "show stats", "how many events", "total bookmarks" |
| Saved Events | "my bookmarks", "saved events", "favorites" |
| Guidance | "how to use", "what can you do", "guide" |

### 11.4 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Process chat message |
| `/api/chat/status` | GET | Service status |
| `/api/chat/intents` | GET | List supported intents |

### 11.5 Usage

1. **Start the server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Open QdrantCity:**
   ```
   http://localhost:8000/
   ```

3. **Click the TrekAI icon** (bottom-right corner) to open the chat panel

4. **Start asking questions!**

### 11.6 Voice Input

TrekAI supports **offline voice input** using Web Speech API:

1. Click the microphone button in the chat panel or search bar
2. Speak your query
3. The recognized text appears in the input field
4. Press Enter or click Send to submit

**Browser Requirements:**
- Chrome/Edge: Full support
- Safari: Partial support
- Firefox: Enable `media.cubeb.enabled` flag

**Fallback:** If voice input isn't available, you'll see a helpful message and can type your query instead.

### 11.7 Architecture

```
TrekAI/
├── models.py          # Intent definitions, response templates
├── service.py         # Offline NLP engine, intent detection
└── api/
    └── trekai_routes.py  # FastAPI endpoints
```

**Key Design Decisions:**
- **No LLM required**: Works without local LLM using templates
- **Context stored client-side**: Reduces server load
- **Local event data**: All responses grounded in Qdrant Edge data
- **No network fallbacks**: True offline operation

### 11.8 Integration Points

TrekAI integrates with existing QdrantCity components:

| Component | Usage |
|-----------|-------|
| Qdrant Edge | Local event retrieval |
| Intent Parser | Query understanding |
| Memory Service | User preferences & bookmarks |
| Routing Service | Offline route calculation |
| FastEmbed | Semantic event matching |

### 11.9 Testing

Run the offline acceptance tests:

```bash
pytest tests/test_trekai_offline.py -v
```

**Test Coverage:**
1. ✅ TrekAI opens and responds with internet disconnected
2. ✅ Local event discovery works through Qdrant Edge
3. ✅ NLP intent detection works without external services
4. ✅ Replies are grounded in local event records
5. ✅ Follow-up questions preserve event and city context
6. ✅ Preferences work from local memory
7. ✅ Route requests use locally available OSM data
8. ✅ Management statistics match actual database counts
9. ✅ Sports filtering returns matching records when present
10. ✅ Voice controls use offline engine or report unavailable setup
11. ✅ Network-disabled tests confirm no cloud LLM requests
12. ✅ Existing search, filters, maps remain functional

### 11.10 File Changes

**Backend:**
- `app/api/trekai_routes.py` - New: Chatbot API endpoints
- `app/trekai/models.py` - New: Models and templates
- `app/trekai/service.py` - New: Offline NLP engine
- `app/main.py` - Modified: Added TrekAI router
- `app/retrieval/filter_builder.py` - Modified: Added debug logging

**Frontend:**
- `frontend/components/TrekAIChatIcon.js` - New: Floating chat icon
- `frontend/components/TrekAIChat.js` - New: Chat panel
- `frontend/pages/DiscoveryPage.js` - Modified: Integrated TrekAI
- `frontend/components/SearchBar.js` - Modified: Added voice input
- `frontend/services/client.js` - Modified: Added TrekAI API methods

**Tests:**
- `tests/test_trekai_offline.py` - New: Offline acceptance tests

### 11.11 Limitations

1. **Voice Input**: Requires browser Web Speech API support
2. **Response Generation**: Template-based (not generative AI)
3. **Language**: Currently English-only intent detection
4. **Offline Routes**: Uses local OSM data (Delhi region by default)

### 11.12 Documentation

See `TREKAI_README.md` for complete documentation including:
- Detailed architecture
- API reference
- Development guide
- Adding new intents and templates

---

## Phase 3 — Production Hardening, Deployment & Demo Readiness

Phase 3 ha