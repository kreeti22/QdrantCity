import logging
import threading
from typing import Any, Dict, Optional, Union

from qdrant_edge import Bm25, Bm25Config, SparseVector
from app.models.experience import ExperiencePayload

logger = logging.getLogger("qdrant_edge.bm25")


def build_bm25_text(experience: Union[ExperiencePayload, Dict[str, Any]]) -> str:
    """Builds a rich, tokenized lexical text representation for BM25 keyword matching.

    Combines key lexical fields: title, category, subcategories/tags, venue,
    neighborhood, city, and description into a single tokenizable string.
    """
    if hasattr(experience, "model_dump"):
        data = experience.model_dump()
    else:
        data = dict(experience)

    title = (data.get("title") or "").strip()
    category = (data.get("category") or "").strip()
    subcategories = data.get("subcategories") or []
    subcat_str = " ".join(str(s).strip() for s in subcategories if s)
    venue = (data.get("venue") or "").strip()
    neighborhood = (data.get("neighborhood") or "").strip()
    city = (data.get("city") or "").strip()
    state = (data.get("state") or "").strip()
    language = (data.get("language") or "").strip()
    description = (data.get("description") or "").strip()

    tokens = [title]
    if category:
        tokens.append(category)
    if subcat_str:
        tokens.append(subcat_str)
    if language:
        tokens.append(language)
    if venue:
        tokens.append(venue)
    if neighborhood:
        tokens.append(neighborhood)
    if city:
        tokens.append(city)
    if state:
        tokens.append(state)
    if description:
        tokens.append(description)

    return " ".join(tokens)


class BM25Service:
    """Local BM25 tokenization and sparse vector generator powered by native Qdrant Edge."""

    def __init__(self, config: Optional[Bm25Config] = None):
        self._config = config
        self._bm25: Optional[Bm25] = None
        self._lock = threading.Lock()

    def _ensure_bm25(self) -> Bm25:
        """Initializes Bm25 instance in a thread-safe manner."""
        if self._bm25 is None:
            with self._lock:
                if self._bm25 is None:
                    logger.info("Initializing native Qdrant Edge BM25 engine...")
                    self._bm25 = Bm25(self._config) if self._config else Bm25()
                    logger.info("Native Qdrant Edge BM25 engine initialized.")
        return self._bm25

    def embed_document(self, text: str) -> SparseVector:
        """Generates a SparseVector for indexing a document."""
        if not text or not text.strip():
            return SparseVector(indices=[], values=[])
        bm25 = self._ensure_bm25()
        return bm25.embed_document(text.strip())

    def embed_query(self, query: str) -> SparseVector:
        """Generates a SparseVector for searching with a query string."""
        if not query or not query.strip():
            return SparseVector(indices=[], values=[])
        bm25 = self._ensure_bm25()
        return bm25.embed_query(query.strip())


_global_bm25_service: Optional[BM25Service] = None
_global_bm25_lock = threading.Lock()


def get_bm25_service() -> BM25Service:
    """Singleton provider for BM25Service."""
    global _global_bm25_service
    if _global_bm25_service is None:
        with _global_bm25_lock:
            if _global_bm25_service is None:
                _global_bm25_service = BM25Service()
    return _global_bm25_service
