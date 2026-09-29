import numpy as np
import pytest

from app.embeddings.model import EmbeddingModelMetadata
from app.embeddings.service import (
    EmbeddingService,
    build_embedding_text,
    get_embedding_service,
)
from app.models.experience import ExperiencePayload


@pytest.fixture(scope="module")
def embedding_service():
    """Provides a shared FastEmbed embedding service instance."""
    return get_embedding_service(
        model_name="BAAI/bge-small-en-v1.5",
        dimension=384,
    )


def test_1_embedding_service_initialization(embedding_service):
    """Test 1: Verify local FastEmbed model loads and reports valid metadata."""
    meta = embedding_service.get_metadata()
    assert isinstance(meta, EmbeddingModelMetadata)
    assert meta.model_name == "BAAI/bge-small-en-v1.5"
    assert meta.dimension == 384
    assert meta.is_local is True
    assert meta.device == "cpu"
    assert embedding_service._model is not None


def test_2_embedding_determinism(embedding_service):
    """Test 2: Same text produces deterministic embeddings within float tolerance."""
    sample_text = "A relaxing evening with live acoustic jazz and saxophone melodies."
    vec1 = embedding_service.embed_text(sample_text)
    vec2 = embedding_service.embed_text(sample_text)

    assert len(vec1) == 384
    assert len(vec2) == 384
    # Check numeric equivalence with float tolerance
    np.testing.assert_allclose(vec1, vec2, rtol=1e-5, atol=1e-6)


def test_3_correct_dimension(embedding_service):
    """Test 3: Verify output vector length matches the configured 384 dimensions."""
    vec = embedding_service.embed_text("Test experience headline")
    assert len(vec) == 384
    # Dense normalized vector should have unit norm
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-2


def test_4_embedding_text_generation():
    """Test 4: Verify build_embedding_text includes semantic fields and excludes volatile ones."""
    payload = ExperiencePayload(
        title="Midnight Film Noir",
        category="movies",
        subcategories=["noir", "crime", "detective"],
        description="A private detective investigates a shadowy conspiracy in 1940s downtown.",
        venue="The Bijou Theater",
        neighborhood="Downtown",
        city="San Francisco",
        price=18.50,
        currency="USD",
        is_indoor=True,
        rating=4.8,
        start_time="2026-11-01T20:00:00Z",
        end_time="2026-11-01T22:00:00Z",
    )

    text = build_embedding_text(payload)

    # Must contain stable semantic fields
    assert "Title: Midnight Film Noir" in text
    assert "Category: movies" in text
    assert "Themes: crime, detective, noir" in text
    assert "Description: A private detective investigates" in text
    assert "Venue: The Bijou Theater" in text
    assert "Location: Downtown, San Francisco" in text

    # Must NOT contain volatile operational fields
    assert "18.5" not in text
    assert "price" not in text.lower()
    assert "start_time" not in text.lower()
    assert "rating" not in text.lower()

    # Determinism: same payload produces exact identical string
    text2 = build_embedding_text(payload)
    assert text == text2


def test_5_batch_embedding(embedding_service):
    """Test 5: Verify multiple texts can be embedded in batch with matching single outputs."""
    texts = [
        "First live indie folk concert",
        "Second terrifying horror experience",
        "Third hands-on pottery workshop",
    ]
    batch_vectors = embedding_service.embed_texts(texts, batch_size=2)

    assert len(batch_vectors) == 3
    for vec in batch_vectors:
        assert len(vec) == 384

    # Compare batch result to single embedding result
    single_vec = embedding_service.embed_text(texts[1])
    np.testing.assert_allclose(batch_vectors[1], single_vec, rtol=1e-5, atol=1e-6)
