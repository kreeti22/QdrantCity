import pytest
from app.models.experience import ExperienceSearchResult
from app.retrieval.fusion import reciprocal_rank_fusion


def make_search_result(item_id: int, score: float, title: str, category: str = "movies") -> ExperienceSearchResult:
    return ExperienceSearchResult(
        id=item_id,
        score=score,
        title=title,
        category=category,
        description=f"Description for {title}",
        payload={"id": item_id, "title": title, "category": category},
    )


def test_rrf_exact_arithmetic_and_overlap_boost():
    """Verify exact formula: RRF(d) = sum(1 / (k + rank_m(d))) and overlap boosting."""
    k = 60
    # Dense results: Doc 1 (rank 1), Doc 2 (rank 2)
    dense_results = [
        make_search_result(1, 0.95, "Doc One"),
        make_search_result(2, 0.85, "Doc Two"),
    ]
    # Sparse results: Doc 2 (rank 1), Doc 3 (rank 2)
    sparse_results = [
        make_search_result(2, 4.5, "Doc Two"),
        make_search_result(3, 3.2, "Doc Three"),
    ]

    fused = reciprocal_rank_fusion(dense_results, sparse_results, k=k, limit=10)

    assert len(fused) == 3

    # Expected calculations:
    # Doc 2: dense rank 2, sparse rank 1 -> 1/(60+2) + 1/(60+1) = 1/62 + 1/61
    expected_doc_2_score = round(1.0 / 62 + 1.0 / 61, 6)
    # Doc 1: dense rank 1 -> 1/(60+1) = 1/61
    expected_doc_1_score = round(1.0 / 61, 6)
    # Doc 3: sparse rank 2 -> 1/(60+2) = 1/62
    expected_doc_3_score = round(1.0 / 62, 6)

    # 1. Overlapping Doc 2 must be ranked first due to fusion boost
    assert fused[0].id == 2
    assert fused[0].score == expected_doc_2_score
    assert fused[0].dense_rank == 2
    assert fused[0].sparse_rank == 1
    assert fused[0].dense_score == 0.85
    assert fused[0].sparse_score == 4.5
    assert fused[0].rrf_score == expected_doc_2_score

    # 2. Doc 1 ranked second
    assert fused[1].id == 1
    assert fused[1].score == expected_doc_1_score
    assert fused[1].dense_rank == 1
    assert fused[1].sparse_rank is None
    assert fused[1].dense_score == 0.95
    assert fused[1].sparse_score is None

    # 3. Doc 3 ranked third
    assert fused[2].id == 3
    assert fused[2].score == expected_doc_3_score
    assert fused[2].dense_rank is None
    assert fused[2].sparse_rank == 2
    assert fused[2].dense_score is None
    assert fused[2].sparse_score == 3.2


def test_rrf_disjoint_lists():
    """Verify fusion with no overlapping candidates."""
    dense = [
        make_search_result(10, 0.9, "Dense Only 1"),
        make_search_result(20, 0.8, "Dense Only 2"),
    ]
    sparse = [
        make_search_result(30, 5.0, "Sparse Only 1"),
        make_search_result(40, 4.0, "Sparse Only 2"),
    ]

    fused = reciprocal_rank_fusion(dense, sparse, k=60, limit=10)
    assert len(fused) == 4
    # Rank 1 dense (10) and Rank 1 sparse (30) both have score 1/61
    # Due to secondary tie-breaking on dense rank, item 10 comes first
    assert fused[0].id == 10
    assert fused[1].id == 30
    assert fused[0].score == fused[1].score


def test_rrf_identical_lists():
    """Verify fusion when both branches return the identical items in same order."""
    dense = [
        make_search_result(1, 0.9, "Alpha"),
        make_search_result(2, 0.8, "Beta"),
    ]
    sparse = [
        make_search_result(1, 5.0, "Alpha"),
        make_search_result(2, 4.0, "Beta"),
    ]

    fused = reciprocal_rank_fusion(dense, sparse, k=60, limit=10)
    assert len(fused) == 2
    assert fused[0].id == 1
    assert fused[0].score == round(2.0 / 61, 6)
    assert fused[1].id == 2
    assert fused[1].score == round(2.0 / 62, 6)


def test_rrf_custom_k():
    """Verify that custom smoothing constant k alters scores correctly."""
    dense = [make_search_result(1, 0.9, "Alpha")]
    sparse = [make_search_result(1, 4.0, "Alpha")]

    fused_k10 = reciprocal_rank_fusion(dense, sparse, k=10, limit=10)
    expected_score = round(2.0 / 11, 6)
    assert fused_k10[0].score == expected_score


def test_rrf_limit_truncation():
    """Verify limit parameter properly caps returned candidates."""
    dense = [make_search_result(i, 1.0 - i * 0.05, f"Item {i}") for i in range(1, 15)]
    sparse = [make_search_result(i, 10.0 - i, f"Item {i}") for i in range(10, 25)]

    fused = reciprocal_rank_fusion(dense, sparse, k=60, limit=5)
    assert len(fused) == 5
