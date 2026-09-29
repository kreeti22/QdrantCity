import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastembed import TextEmbedding

from app.embeddings.model import EmbeddingModelMetadata
from app.models.experience import ExperiencePayload

logger = logging.getLogger("qdrant_edge.embeddings")


def build_embedding_text(experience: Union[ExperiencePayload, Dict[str, Any]]) -> str:
    """Builds a deterministic, semantic text representation from stable descriptive fields.
    
    Excludes rapidly fluctuating operational fields like price, status, or remaining capacity.
    """
    if hasattr(experience, "model_dump"):
        data = experience.model_dump()
    else:
        data = dict(experience)

    title = (data.get("title") or "").strip()
    category = (data.get("category") or "").strip()
    subcategories = data.get("subcategories") or []
    subcat_str = ", ".join(sorted(str(s).strip() for s in subcategories if s))
    description = (data.get("description") or "").strip()
    venue = (data.get("venue") or "").strip()
    neighborhood = (data.get("neighborhood") or "").strip()
    city = (data.get("city") or "").strip()
    state = (data.get("state") or "").strip()
    language = (data.get("language") or "").strip()

    parts = [f"Title: {title}"]
    if category:
        parts.append(f"Category: {category}")
    if subcat_str:
        parts.append(f"Themes: {subcat_str}")
    if language:
        parts.append(f"Language: {language}")
    if description:
        parts.append(f"Description: {description}")
    if venue:
        parts.append(f"Venue: {venue}")
    location_parts = [p for p in [neighborhood, city, state] if p]
    if location_parts:
        parts.append(f"Location: {', '.join(location_parts)}")

    return "\n".join(parts)


class EmbeddingService:
    """Local embedding service powered by FastEmbed running CPU ONNX inference.
    
    Guarantees offline execution without any external cloud LLM or embedding API calls.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        model_version: str = "1.5",
        dimension: int = 384,
        cache_dir: Optional[Path] = None,
    ):
        self.model_name = model_name
        self.model_version = model_version
        self.dimension = dimension
        self.cache_dir = cache_dir
        self.init_time_ms: float = 0.0

        self._model: Optional[TextEmbedding] = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> TextEmbedding:
        """Loads the embedding model once in a thread-safe manner."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(f"Loading local embedding model '{self.model_name}'...")
                    t0 = time.perf_counter()
                    cache_path = str(self.cache_dir.resolve()) if self.cache_dir else None
                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=cache_path,
                    )
                    self.init_time_ms = (time.perf_counter() - t0) * 1000
                    logger.info(
                        f"Local model '{self.model_name}' loaded in {self.init_time_ms:.1f}ms (dimension: {self.dimension})"
                    )
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generates a dense embedding vector for a single query or text string."""
        if not text or not text.strip():
            raise ValueError("Cannot embed an empty or whitespace-only query text.")

        model = self._ensure_model()
        generator = model.embed([text.strip()])
        vector = next(iter(generator))
        return [float(x) for x in vector]

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Batch-embeds a list of texts into dense vectors with local batching."""
        if not texts:
            return []

        cleaned_texts = [t.strip() if t and t.strip() else "experience" for t in texts]
        model = self._ensure_model()
        generator = model.embed(cleaned_texts, batch_size=batch_size)
        return [[float(x) for x in vec] for vec in generator]

    def get_metadata(self) -> EmbeddingModelMetadata:
        """Returns structured metadata regarding the active local embedding model."""
        return EmbeddingModelMetadata(
            model_name=self.model_name,
            model_version=self.model_version,
            dimension=self.dimension,
            is_local=True,
            device="cpu",
            initialization_time_ms=round(self.init_time_ms, 2),
        )


_singleton_embedding_service: Optional[EmbeddingService] = None
_singleton_lock = threading.Lock()


def get_embedding_service(
    model_name: str = "BAAI/bge-small-en-v1.5",
    dimension: int = 384,
    cache_dir: Optional[Path] = None,
) -> EmbeddingService:
    """Returns a shared process-level singleton instance of EmbeddingService."""
    global _singleton_embedding_service
    if _singleton_embedding_service is None:
        with _singleton_lock:
            if _singleton_embedding_service is None:
                _singleton_embedding_service = EmbeddingService(
                    model_name=model_name,
                    dimension=dimension,
                    cache_dir=cache_dir,
                )
    return _singleton_embedding_service
