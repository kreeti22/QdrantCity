import os
import statistics
import sys
import time
from typing import Any, Dict, List, Set

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config.settings import get_settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.bm25 import get_bm25_service
from app.embeddings.service import get_embedding_service
from app.ingestion.seed import seed_database
from app.intent.parser import LocalQueryParser
from app.utils.clock import TimeProvider

# Curated queries testing structured intent understanding against ground truth relevant item IDs
BENCHMARK_INTENT_QUERIES = [
    {
        "query": "standup comedy under 30",
        "category": "comedy",
        "expected_ids": {31, 33, 35, 36, 38, 39},
        "description": "Category + price filter (max $30)",
    },
    {
        "query": "IMAX sci-fi movies",
        "category": "movies",
        "expected_ids": {1, 2, 9, 13},
        "description": "Category + format filter (IMAX)",
    },
    {
        "query": "free outdoor festival",
        "category": "festivals",
        "expected_ids": {70, 74, 76},
        "description": "Category + price (0) + outdoor filter",
    },
    {
        "query": "movies not horror",
        "category": "movies",
        "expected_ids": {1, 2, 4, 6, 7, 9, 11, 12, 13, 14, 15},
        "description": "Category + negated subcategory (not horror)",
    },
    {
        "query": "electronic music concert",
        "category": "concerts",
        "expected_ids": {18, 22, 24},
        "description": "Category + subcategory music genre",
    },
    {
        "query": "pottery workshops for beginners",
        "category": "workshops",
        "expected_ids": {81, 84},
        "description": "Category + theme constraint",
    },
    {
        "query": "craft beer festival",
        "category": "festivals",
        "expected_ids": {68, 73},
        "description": "Category + keyword constraint",
    },
    {
        "query": "Tennessee Williams Streetcar theatre",
        "category": "theatre",
        "expected_ids": {48},
        "description": "Category + title keyword constraint",
    },
    {
        "query": "relaxing acoustic folk guitar concert",
        "category": "concerts",
        "expected_ids": {16, 21, 23},
        "description": "Descriptive semantic query with category constraint",
    },
    {
        "query": "competitive outdoor sports match",
        "category": "sports",
        "expected_ids": {56, 59, 63, 64, 66},
        "description": "Category + outdoor constraint",
    },
]


def calculate_recall(retrieved_ids: List[int], expected_ids: Set[int], k: int) -> float:
    """Computes Recall@K: fraction of expected relevant items found in top-K."""
    if not expected_ids:
        return 0.0
    top_k_ids = set(retrieved_ids[:k])
    hits = len(top_k_ids.intersection(expected_ids))
    return hits / len(expected_ids)


def run_benchmark():
    settings = get_settings()
    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repo = ExperienceRepository(shard, client, settings)
    dense_service = get_embedding_service(
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )
    bm25_service = get_bm25_service()

    # Seed if needed
    if repo.count() == 0:
        print("[*] Seeding database for benchmark...")
        seed_database(repo, settings, embedding_service=dense_service, overwrite=False)

    clock = TimeProvider(
        tz_name=settings.timezone,
        reference_datetime=settings.reference_datetime or "2026-10-15T12:00:00Z",
    )
    query_parser = LocalQueryParser(clock=clock, settings=settings)

    print("=" * 80)
    print("PHASE 1D: BENCHMARK — BASELINE HYBRID vs QUERY UNDERSTANDING + HYBRID")
    print(f"Dataset Size: {repo.count()} points in Qdrant Edge")
    print(f"Dense Model: {settings.embedding_model_name} (384-dim, FastEmbed CPU)")
    print(f"Sparse Engine: BM25 (Qdrant Edge native)")
    print(f"Query Understanding: Deterministic Rule-Based CPU Engine")
    print("=" * 80)

    # 1. Warm-up
    warmup_q = "warmup query test"
    _ = query_parser.parse(warmup_q)
    w_dense = dense_service.embed_text(warmup_q)
    w_sparse = bm25_service.embed_query(warmup_q)
    _ = repo.search_hybrid(w_dense, w_sparse, final_top_k=5)

    # 2. Evaluation: Baseline Hybrid Search (No Query Understanding)
    baseline_latencies: List[float] = []
    baseline_recalls_at_5: List[float] = []
    baseline_recalls_at_10: List[float] = []

    # 3. Evaluation: Query Understanding + Hybrid Search
    qu_latencies: List[float] = []
    qu_parse_latencies: List[float] = []
    qu_recalls_at_5: List[float] = []
    qu_recalls_at_10: List[float] = []

    num_iterations = 5  # Run 5 iterations per query for solid latency percentiles

    print(f"\nExecuting {len(BENCHMARK_INTENT_QUERIES)} benchmark queries ({num_iterations} runs each)...")

    for item in BENCHMARK_INTENT_QUERIES:
        q_text = item["query"]
        expected = item["expected_ids"]

        for _ in range(num_iterations):
            # A. Baseline Hybrid: Raw text directly to embeddings and search without intent filters
            t0 = time.perf_counter()
            b_dense = dense_service.embed_text(q_text)
            b_sparse = bm25_service.embed_query(q_text)
            b_results, _ = repo.search_hybrid(
                query_vector=b_dense,
                sparse_vector=b_sparse,
                final_top_k=10,
                filters=None,
            )
            t_baseline = (time.perf_counter() - t0) * 1000
            baseline_latencies.append(t_baseline)

            b_ids = [r.id for r in b_results]
            baseline_recalls_at_5.append(calculate_recall(b_ids, expected, 5))
            baseline_recalls_at_10.append(calculate_recall(b_ids, expected, 10))

            # B. Query Understanding + Hybrid: Parse intent, build Edge filter, vectorize semantic query
            t1 = time.perf_counter()
            intent = query_parser.parse(q_text)
            t_parsed = (time.perf_counter() - t1) * 1000
            qu_parse_latencies.append(t_parsed)

            edge_filter = repo.build_filter_from_intent(intent)
            sem_query = intent.semantic_query or q_text
            qu_dense = dense_service.embed_text(sem_query)
            qu_sparse = bm25_service.embed_query(sem_query)
            qu_results, _ = repo.search_hybrid(
                query_vector=qu_dense,
                sparse_vector=qu_sparse,
                final_top_k=10,
                filters=edge_filter,
            )
            t_qu_total = (time.perf_counter() - t1) * 1000
            qu_latencies.append(t_qu_total)

            qu_ids = [r.id for r in qu_results]
            qu_recalls_at_5.append(calculate_recall(qu_ids, expected, 5))
            qu_recalls_at_10.append(calculate_recall(qu_ids, expected, 10))

    # Calculate percentiles and averages
    def get_percentiles(vals: List[float]) -> Dict[str, float]:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "p50": sorted_vals[int(0.50 * n)],
            "p95": sorted_vals[int(0.95 * n)],
            "p99": sorted_vals[min(int(0.99 * n), n - 1)],
            "mean": statistics.mean(sorted_vals),
        }

    b_perc = get_percentiles(baseline_latencies)
    qu_perc = get_percentiles(qu_latencies)
    parse_perc = get_percentiles(qu_parse_latencies)

    mean_b_r5 = statistics.mean(baseline_recalls_at_5)
    mean_b_r10 = statistics.mean(baseline_recalls_at_10)

    mean_qu_r5 = statistics.mean(qu_recalls_at_5)
    mean_qu_r10 = statistics.mean(qu_recalls_at_10)

    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON RESULTS")
    print("=" * 80)
    print(f"{'Metric':<30} | {'Baseline Hybrid':<22} | {'Query Understanding + Hybrid':<25}")
    print("-" * 80)
    print(f"{'Recall@5':<30} | {mean_b_r5 * 100:>19.2f}% | {mean_qu_r5 * 100:>22.2f}%")
    print(f"{'Recall@10':<30} | {mean_b_r10 * 100:>19.2f}% | {mean_qu_r10 * 100:>22.2f}%")
    print("-" * 80)
    print(f"{'Query Parse P50 (ms)':<30} | {'N/A (no parser)':>22} | {parse_perc['p50']:>22.2f} ms")
    print(f"{'Query Parse P95 (ms)':<30} | {'N/A (no parser)':>22} | {parse_perc['p95']:>22.2f} ms")
    print(f"{'Query Parse P99 (ms)':<30} | {'N/A (no parser)':>22} | {parse_perc['p99']:>22.2f} ms")
    print("-" * 80)
    print(f"{'Total Latency P50 (ms)':<30} | {b_perc['p50']:>19.2f} ms | {qu_perc['p50']:>22.2f} ms")
    print(f"{'Total Latency P95 (ms)':<30} | {b_perc['p95']:>19.2f} ms | {qu_perc['p95']:>22.2f} ms")
    print(f"{'Total Latency P99 (ms)':<30} | {b_perc['p99']:>19.2f} ms | {qu_perc['p99']:>22.2f} ms")
    print(f"{'Total Latency Mean (ms)':<30} | {b_perc['mean']:>19.2f} ms | {qu_perc['mean']:>22.2f} ms")
    print("=" * 80)

    # Detailed per-query breakdown
    print("\nDetailed Per-Query Retrieval Comparison:")
    print("-" * 80)
    for item in BENCHMARK_INTENT_QUERIES:
        q_text = item["query"]
        expected = item["expected_ids"]

        b_dense = dense_service.embed_text(q_text)
        b_sparse = bm25_service.embed_query(q_text)
        b_results, _ = repo.search_hybrid(b_dense, b_sparse, final_top_k=5)
        b_ids = [r.id for r in b_results]
        b_r5 = calculate_recall(b_ids, expected, 5)

        intent = query_parser.parse(q_text)
        edge_filter = repo.build_filter_from_intent(intent)
        qu_dense = dense_service.embed_text(intent.semantic_query or q_text)
        qu_sparse = bm25_service.embed_query(intent.semantic_query or q_text)
        qu_results, _ = repo.search_hybrid(qu_dense, qu_sparse, final_top_k=5, filters=edge_filter)
        qu_ids = [r.id for r in qu_results]
        qu_r5 = calculate_recall(qu_ids, expected, 5)

        print(f"Query: \"{q_text}\"")
        print(f"  Extracted Intent Filter: {edge_filter is not None}")
        print(f"  Semantic Query: \"{intent.semantic_query}\"")
        print(f"  Baseline Recall@5: {b_r5 * 100:.0f}% -> QU Recall@5: {qu_r5 * 100:.0f}%")
        print("-" * 80)

    client.close()


if __name__ == "__main__":
    run_benchmark()
