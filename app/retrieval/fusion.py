import logging
from typing import Dict, List, Optional

from app.models.experience import ExperienceSearchResult

logger = logging.getLogger("qdrant_edge.fusion")


def reciprocal_rank_fusion(
    dense_results: List[ExperienceSearchResult],
    sparse_results: List[ExperienceSearchResult],
    k: int = 60,
    limit: int = 10,
) -> List[ExperienceSearchResult]:
    """Combines dense semantic and sparse BM25 candidate lists using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF(d) = sum_{m in {dense, sparse}} (1 / (k + rank_m(d)))

    where rank_m(d) is 1-indexed (1, 2, ...).
    Candidates appearing in both result lists receive additive reciprocal score boosts.
    """
    scores: Dict[int, float] = {}
    dense_ranks: Dict[int, int] = {}
    dense_scores: Dict[int, float] = {}
    sparse_ranks: Dict[int, int] = {}
    sparse_scores: Dict[int, float] = {}
    item_map: Dict[int, ExperienceSearchResult] = {}

    # 1. Accumulate dense candidate ranks and scores
    for rank_0, item in enumerate(dense_results):
        rank = rank_0 + 1
        item_id = item.id
        item_map[item_id] = item
        dense_ranks[item_id] = rank
        dense_scores[item_id] = item.score
        contribution = 1.0 / (k + rank)
        scores[item_id] = scores.get(item_id, 0.0) + contribution

    # 2. Accumulate sparse candidate ranks and scores
    for rank_0, item in enumerate(sparse_results):
        rank = rank_0 + 1
        item_id = item.id
        if item_id not in item_map:
            item_map[item_id] = item
        sparse_ranks[item_id] = rank
        sparse_scores[item_id] = item.score
        contribution = 1.0 / (k + rank)
        scores[item_id] = scores.get(item_id, 0.0) + contribution

    # 3. Sort candidates deterministically:
    # Primary: RRF score descending
    # Secondary: Dense rank ascending (preferring higher semantic relevance on exact tie)
    # Tertiary: Experience ID ascending
    sorted_ids = sorted(
        scores.keys(),
        key=lambda pid: (
            round(scores[pid], 8),
            -(dense_ranks.get(pid, 9999)),
            -pid,
        ),
        reverse=True,
    )

    # 4. Construct final fused result models
    fused_results: List[ExperienceSearchResult] = []
    for pid in sorted_ids[:limit]:
        base_item = item_map[pid]
        total_rrf = scores[pid]
        fused_item = ExperienceSearchResult(
            id=base_item.id,
            score=round(total_rrf, 6),
            title=base_item.title,
            category=base_item.category,
            description=base_item.description,
            payload=base_item.payload,
            dense_score=round(dense_scores[pid], 6) if pid in dense_scores else None,
            dense_rank=dense_ranks.get(pid),
            sparse_score=round(sparse_scores[pid], 6) if pid in sparse_scores else None,
            sparse_rank=sparse_ranks.get(pid),
            rrf_score=round(total_rrf, 6),
        )
        fused_results.append(fused_item)

    return fused_results
