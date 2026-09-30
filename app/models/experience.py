from enum import Enum
from typing import Any, Dict, List, Literal, Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, model_validator


class ErrorDetail(BaseModel):
    """Structured error descriptor for machine and human consumption."""
    code: str = Field(..., description="Machine-readable error identifier (e.g. INVALID_QUERY)")
    message: str = Field(..., description="Human-readable explanation of the error")
    details: Optional[Any] = Field(default=None, description="Optional validation details or field context")


class APIErrorResponse(BaseModel):
    """Standardized API error envelope for client and server errors."""
    error: ErrorDetail = Field(..., description="Structured error payload")
    detail: Optional[str] = Field(default=None, description="Backward-compatible detail summary")


class ExperienceCategory(str, Enum):
    """Supported city experience categories."""
    MOVIES = "movies"
    CONCERTS = "concerts"
    COMEDY = "comedy"
    THEATRE = "theatre"
    SPORTS = "sports"
    FESTIVALS = "festivals"
    WORKSHOPS = "workshops"
    EXHIBITIONS = "exhibitions"
    ACTIVITIES = "activities"


class ExperiencePayload(BaseModel):
    """Structured payload metadata stored alongside each point in Qdrant Edge."""
    title: str = Field(..., description="Name or headline of the city experience")
    category: str = Field(..., description="Primary category of the experience")
    subcategories: List[str] = Field(default_factory=list, description="Descriptive subcategories/tags")
    description: str = Field(..., description="Rich textual summary of the event")
    venue: str = Field(..., description="Venue or location name")
    neighborhood: str = Field(default="", description="Neighborhood or district within the city")
    city: str = Field(..., description="City where experience occurs")
    state: Optional[str] = Field(default="India", description="State or province")
    price: float = Field(..., ge=0.0, description="Admission/ticket price")
    currency: str = Field(default="INR", description="ISO currency code")
    is_indoor: bool = Field(..., description="Whether the event takes place indoors")
    rating: float = Field(default=0.0, ge=0.0, le=5.0, description="Average review score")
    start_time: str = Field(..., description="ISO 8601 formatted start datetime")
    end_time: str = Field(..., description="ISO 8601 formatted end datetime")
    image_url: Optional[str] = Field(default=None, description="Hero or banner image URL")
    language: Optional[str] = Field(default=None, description="Primary performance or audio language")
    source_url: Optional[str] = Field(default=None, description="Reference or official source URL")
    image_credit: Optional[str] = Field(default=None, description="Image attribution or license")
    last_verified: Optional[str] = Field(default="2026-09", description="Verification timestamp")
    demo_data: Optional[bool] = Field(default=False, description="Whether record is demo/illustrative data")
    latitude: Optional[float] = Field(default=28.6139, description="Geographic latitude coordinate")
    longitude: Optional[float] = Field(default=77.2090, description="Geographic longitude coordinate")
    type: Optional[str] = Field(default="event", description="Type of attraction: 'movie' or 'event'")
    osm_id: Optional[str] = Field(default=None, description="OpenStreetMap reference ID")


class Experience(BaseModel):
    """Full experience representation with ID, dense vector embedding, optional sparse vector, and payload."""
    id: int = Field(..., description="Unique integer ID")
    vector: Optional[List[float]] = Field(default=None, description="Dense embedding vector")
    sparse_vector: Optional[Any] = Field(default=None, description="BM25 sparse vector representation")
    payload: ExperiencePayload = Field(..., description="Structured payload")


class ExperienceSearchResult(BaseModel):
    """Frontend-ready result item returned from local Qdrant Edge retrieval with scoring metadata."""
    id: int = Field(..., description="Unique integer ID")
    score: float = Field(..., description="Relevance score (RRF score for hybrid, cosine similarity for dense, BM25 score for sparse)")
    title: str = Field(..., description="Headline of the city experience")
    category: str = Field(..., description="Primary category")
    description: str = Field(..., description="Descriptive summary of the experience")
    venue: Optional[str] = Field(default=None, description="Venue or landmark name")
    city: Optional[str] = Field(default=None, description="City name")
    state: Optional[str] = Field(default=None, description="State name")
    neighborhood: Optional[str] = Field(default=None, description="Neighborhood or district")
    start_time: Optional[str] = Field(default=None, description="ISO 8601 formatted start datetime")
    end_time: Optional[str] = Field(default=None, description="ISO 8601 formatted end datetime")
    price: Optional[float] = Field(default=None, description="Admission/ticket price")
    currency: Optional[str] = Field(default="INR", description="ISO currency code")
    image_url: Optional[str] = Field(default=None, description="Hero image URL")
    subcategories: List[str] = Field(default_factory=list, description="Descriptive tags/subcategories")
    language: Optional[str] = Field(default=None, description="Primary performance or audio language")
    is_indoor: Optional[bool] = Field(default=None, description="Whether event takes place indoors")
    rating: Optional[float] = Field(default=None, description="Average review score")
    source_url: Optional[str] = Field(default=None, description="Source URL")
    image_credit: Optional[str] = Field(default=None, description="Image attribution or license")
    last_verified: Optional[str] = Field(default=None, description="Last verification date")
    demo_data: Optional[bool] = Field(default=None, description="Whether record is demo data")
    latitude: Optional[float] = Field(default=None, description="Geographic latitude coordinate")
    longitude: Optional[float] = Field(default=None, description="Geographic longitude coordinate")
    type: Optional[str] = Field(default=None, description="Attraction type: 'movie' or 'event'")
    osm_id: Optional[str] = Field(default=None, description="OpenStreetMap reference ID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Raw point payload dictionary for backwards compatibility")
    dense_score: Optional[float] = Field(default=None, description="Score from dense semantic retrieval")
    dense_rank: Optional[int] = Field(default=None, description="1-based rank from dense retrieval")
    sparse_score: Optional[float] = Field(default=None, description="Score from BM25 sparse retrieval")
    sparse_rank: Optional[int] = Field(default=None, description="1-based rank from BM25 retrieval")
    rrf_score: Optional[float] = Field(default=None, description="Fused Reciprocal Rank Fusion score")
    is_saved: Optional[bool] = Field(default=None, description="Whether experience is bookmarked by the requesting user")

    @model_validator(mode="before")
    @classmethod
    def populate_from_payload(cls, data: Any) -> Any:
        """Normalizes and safely extracts frontend card fields from raw payload dictionary."""
        if isinstance(data, dict):
            p = data.get("payload") or {}
            if isinstance(p, dict):
                # Pull top-level card attributes from payload if not explicitly supplied
                for field in [
                    "venue", "city", "state", "neighborhood", "start_time", "end_time",
                    "currency", "image_url", "language", "subcategories",
                    "source_url", "image_credit", "last_verified", "demo_data",
                    "type", "osm_id"
                ]:
                    if data.get(field) is None and field in p:
                        data[field] = p[field]
                if data.get("type") is None:
                    cat = (data.get("category") or p.get("category") or "").lower()
                    data["type"] = "movie" if cat == "movies" else "event"
                if data.get("latitude") is None and "latitude" in p and p["latitude"] is not None:
                    try:
                        data["latitude"] = float(p["latitude"])
                    except (ValueError, TypeError):
                        pass
                if data.get("longitude") is None and "longitude" in p and p["longitude"] is not None:
                    try:
                        data["longitude"] = float(p["longitude"])
                    except (ValueError, TypeError):
                        pass
                if data.get("price") is None and "price" in p and p["price"] is not None:
                    try:
                        data["price"] = float(p["price"])
                    except (ValueError, TypeError):
                        pass
                if data.get("is_indoor") is None and "is_indoor" in p:
                    data["is_indoor"] = bool(p["is_indoor"])
                if data.get("rating") is None and "rating" in p and p["rating"] is not None:
                    try:
                        data["rating"] = float(p["rating"])
                    except (ValueError, TypeError):
                        pass
        return data


class SearchFilterParams(BaseModel):
    """Payload filter parameters for structured edge querying."""
    category: Optional[str] = None
    city: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    is_indoor: Optional[bool] = None


class NaturalLanguageSearchRequest(BaseModel):
    """Request model for natural language semantic and hybrid retrieval."""
    query: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Search query text (e.g. 'Dune IMAX' or 'relaxing evening with music'). Max length 500 characters."
    )
    query_text: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Alias for query. Max length 500 characters."
    )
    vector: Optional[List[float]] = Field(
        default=None,
        description="Optional pre-computed dense vector for low-level testing."
    )
    limit: int = Field(default=5, ge=1, le=50, description="Maximum number of points to retrieve")
    filters: Optional[SearchFilterParams] = Field(
        default=None,
        description="Structured payload filtering constraints"
    )
    mode: Literal["hybrid", "dense", "sparse"] = Field(
        default="hybrid",
        description="Retrieval mode: 'hybrid' (default, dense + BM25 via RRF), 'dense', or 'sparse' (BM25 only)."
    )
    dense_top_k: Optional[int] = Field(
        default=None,
        description="Candidate pool size retrieved from dense branch before fusion (default 20)."
    )
    bm25_top_k: Optional[int] = Field(
        default=None,
        description="Candidate pool size retrieved from BM25 branch before fusion (default 20)."
    )
    rrf_k: Optional[int] = Field(
        default=None,
        description="RRF smoothing constant (default 60)."
    )
    enable_intent: bool = Field(
        default=True,
        description="Whether to run local query understanding to extract structured intent and filters."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional local user ID for personalized ranking (e.g. 'local-default')."
    )
    personalize: bool = Field(
        default=False,
        description="Whether to apply local preference boosting to the fused retrieval results."
    )

    def get_query_string(self) -> Optional[str]:
        """Resolves natural language query string from query or query_text."""
        return self.query or self.query_text


# Backwards compatibility alias
VectorSearchRequest = NaturalLanguageSearchRequest


class DiagnosticsInfo(BaseModel):
    """Diagnostic details proving retrieval is running through Qdrant Edge locally."""
    engine: str = "qdrant-edge-py"
    engine_version: str
    execution_mode: str = "in_process_local"
    storage_path: str
    collection_name: str
    points_count: int
    segments_count: int
    indexed_vectors_count: int
    vector_size: int
    distance: str
    indexed_payload_fields: List[str]
    embedding_model_name: str
    embedding_dimension: int
    is_local_embedding: bool = True
    has_sparse_bm25: bool = True
    healthy: bool
