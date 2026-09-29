from typing import Optional
from pydantic import BaseModel, Field


class EmbeddingModelMetadata(BaseModel):
    """Metadata describing the active local embedding model."""
    model_name: str = Field(..., description="Canonical model identifier in FastEmbed")
    model_version: str = Field(default="1.5", description="Version of the embedding model")
    dimension: int = Field(..., description="Dense vector output dimensionality")
    is_local: bool = Field(default=True, description="Indicates purely offline local execution")
    device: str = Field(default="cpu", description="Execution hardware target (e.g. CPU via ONNX Runtime)")
    initialization_time_ms: float = Field(default=0.0, description="Time taken to load model into memory")


class SearchLatencyMetrics(BaseModel):
    """Execution timing breakdown for semantic and hybrid query execution."""
    embedding_ms: float = Field(..., description="Time taken to vectorize query locally (dense + sparse)")
    search_ms: float = Field(..., description="Time taken to search vectors in local Qdrant Edge")
    total_ms: float = Field(..., description="End-to-end retrieval latency in milliseconds")
    dense_embedding_ms: Optional[float] = Field(default=None, description="Time taken to compute dense embedding")
    dense_search_ms: Optional[float] = Field(default=None, description="Time taken to search dense vectors")
    bm25_embedding_ms: Optional[float] = Field(default=None, description="Time taken to tokenize BM25 sparse query")
    bm25_search_ms: Optional[float] = Field(default=None, description="Time taken to search BM25 sparse index")
    query_parsing_ms: Optional[float] = Field(default=None, description="Time taken to extract structured intent")
    fusion_ms: Optional[float] = Field(default=None, description="Time taken for RRF fusion")
