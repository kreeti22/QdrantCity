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

# Curated benchmark evaluation queries with ground truth relevant item IDs
BENCHMARK_QUERIES = [
    {
        "query": "Interstellar 70mm IMAX",
        "type": "exact_keyword",
        "expected_ids": {1},
    },
    {
        "query": "Blade Runner 2049 laser",
        "type": "exact_keyword",
        "expected_ids": {2},
    },
    {
        "query": "Tennessee Williams Streetcar",
        "type": "exact_keyword",
        "expected_ids": {48},
    },
    {
        "query": "Castro Theatre Pavilion",
        "type": "exact_keyword",
        "expected_ids": {4, 49},
    },
    {
        "query": "relaxing acoustic folk guitar concert",
        "type": "semantic",
        "expected_ids": {16, 21, 23},
    },
    {
        "query": "something terrifying scary horror late at night",
        "type": "semantic",
        "expected_ids": {3, 5, 8},
    },
    {
        "query": "fun creative craft activity for kids and family",
        "type": "semantic",
        "expected_ids": {67, 72, 73, 75},
    },
    {
        "query": "intense competitive outdoor sports match",
        "type": "semantic",
        "expected_ids": {53, 54, 55, 61},
    },
    {
        "query": "midnight double feature horror movies",
        "type": "mixed",
        "expected_ids": {3, 10},
    },
    {
        "query": "standup comedy improv laughs with drinks",
        "type": "mixed",
        "expected_ids": {27, 28, 29, 31},
    },
    {
        "query": "artisan sourdough bread baking culinary workshop",
        "type": "mixed",
        "expected_ids": {71, 74},
    },
    {
        "query": "ancient Egyptian archaeology artifacts exhibition",
        "type": "mixed",
        "expected_ids": {80, 83},
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

    # Ensure collection is loaded with 115 experiences
    total_count = repo.count()
    if total_count == 0:
        seed_database(repo, settings, embedding_service=dense_service, overwrite=True)
        total_count = repo.count()

    print("=" * 80)
    print("      QDRANTCINEMA PHASE 1C HYBRID RETRIEVAL BENCHMARK REPORT")
    print("=" * 80)
    print(f"Collection:            {settings.collection_name} ({total_count} points)")
    print(f"Dense Model:           {settings.embedding_model_name} (dim={settings.vector_size})")
    print(f"Sparse Engine:         Native Qdrant Edge BM25 (using='{settings.sparse_vector_name}')")
    print(f"Fusion Strategy:       Reciprocal Rank Fusion (RRF, k={settings.rrf_k})")
    print(f"Candidate Pools:       Dense Top-{settings.dense_top_k}, BM25 Top-{settings.bm25_top_k} -> Final Top-{settings.final_top_k}")
    print(f"Total Test Queries:    {len(BENCHMARK_QUERIES)} (Exact Keyword, Semantic, Mixed)")
    print(f"Execution Target:      100% Local In-Process CPU (Zero External APIs)")
    print("-" * 80)

    # Warmup
    _ = dense_service.embed_text("warmup query")
    _ = bm25_service.embed_query("warmup query")

    # Metrics containers for 3 modes
    modes = ["dense", "sparse", "hybrid"]
    metrics: Dict[str, Dict[str, Any]] = {
        m: {
            "recalls_5": [],
            "recalls_10": [],
            "latencies_ms": [],
            "embed_latencies_ms": [],
            "search_latencies_ms": [],
        }
        for m in modes
    }
    hybrid_fusion_latencies_ms = []

    iterations = 5  # Run each query multiple times for stable latency measurement

    for item in BENCHMARK_QUERIES:
        q_text = item["query"]
        expected = item["expected_ids"]

        for _ in range(iterations):
            # 1. Dense Branch
            t_d_start = time.perf_counter()
            d_vec = dense_service.embed_text(q_text)
            t_d_emb = (time.perf_counter() - t_d_start) * 1000

            t_ds_start = time.perf_counter()
            d_results = repo.search_dense(d_vec, limit=10)
            t_ds = (time.perf_counter() - t_ds_start) * 1000
            t_d_total = (time.perf_counter() - t_d_start) * 1000

            metrics["dense"]["latencies_ms"].append(t_d_total)
            metrics["dense"]["embed_latencies_ms"].append(t_d_emb)
            metrics["dense"]["search_latencies_ms"].append(t_ds)
            metrics["dense"]["recalls_5"].append(calculate_recall([r.id for r in d_results], expected, 5))
            metrics["dense"]["recalls_10"].append(calculate_recall([r.id for r in d_results], expected, 10))

            # 2. Sparse BM25 Branch
            t_s_start = time.perf_counter()
            s_vec = bm25_service.embed_query(q_text)
            t_s_emb = (time.perf_counter() - t_s_start) * 1000

            t_ss_start = time.perf_counter()
            s_results = repo.search_sparse(s_vec, limit=10)
            t_ss = (time.perf_counter() - t_ss_start) * 1000
            t_s_total = (time.perf_counter() - t_s_start) * 1000

            metrics["sparse"]["latencies_ms"].append(t_s_total)
            metrics["sparse"]["embed_latencies_ms"].append(t_s_emb)
            metrics["sparse"]["search_latencies_ms"].append(t_ss)
            metrics["sparse"]["recalls_5"].append(calculate_recall([r.id for r in s_results], expected, 5))
            metrics["sparse"]["recalls_10"].append(calculate_recall([r.id for r in s_results], expected, 10))

            # 3. Hybrid Branch
            t_h_start = time.perf_counter()
            d_vec_h = dense_service.embed_text(q_text)
            s_vec_h = bm25_service.embed_query(q_text)
            t_h_emb = (time.perf_counter() - t_h_start) * 1000

            h_results, timings = repo.search_hybrid(
                query_vector=d_vec_h,
                sparse_vector=s_vec_h,
                dense_top_k=settings.dense_top_k,
                bm25_top_k=settings.bm25_top_k,
                final_top_k=settings.final_top_k,
                rrf_k=settings.rrf_k,
            )
            t_h_total = (time.perf_counter() - t_h_start) * 1000

            metrics["hybrid"]["latencies_ms"].append(t_h_total)
            metrics["hybrid"]["embed_latencies_ms"].append(t_h_emb)
            metrics["hybrid"]["search_latencies_ms"].append(timings["dense_search_ms"] + timings["bm25_search_ms"])
            hybrid_fusion_latencies_ms.append(timings["fusion_ms"])
            metrics["hybrid"]["recalls_5"].append(calculate_recall([r.id for r in h_results], expected, 5))
            metrics["hybrid"]["recalls_10"].append(calculate_recall([r.id for r in h_results], expected, 10))

    def compute_percentiles(vals: List[float]) -> Dict[str, float]:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "avg": statistics.mean(vals),
            "p50": sorted_vals[int(n * 0.50)],
            "p95": sorted_vals[min(int(n * 0.95), n - 1)],
            "p99": sorted_vals[min(int(n * 0.99), n - 1)],
        }

    print("\nRETRIEVAL QUALITY & LATENCY COMPARISON:")
    print("-" * 80)
    print(f"{'Retrieval Mode':<18} | {'Recall@5':<10} | {'Recall@10':<10} | {'Avg (ms)':<9} | {'P50 (ms)':<9} | {'P95 (ms)':<9} | {'P99 (ms)':<9}")
    print("-" * 80)

    for m in ["dense", "sparse", "hybrid"]:
        r5 = statistics.mean(metrics[m]["recalls_5"]) * 100
        r10 = statistics.mean(metrics[m]["recalls_10"]) * 100
        p = compute_percentiles(metrics[m]["latencies_ms"])
        label = "Dense (BGE-small)" if m == "dense" else ("Sparse (BM25)" if m == "sparse" else "Hybrid (RRF k=60)")
        print(f"{label:<18} | {r5:>8.1f}% | {r10:>8.1f}% | {p['avg']:>9.2f} | {p['p50']:>9.2f} | {p['p95']:>9.2f} | {p['p99']:>9.2f}")

    print("-" * 80)

    # Detailed component timing breakdown for Hybrid mode
    p_d_emb = compute_percentiles([d for d in metrics["dense"]["embed_latencies_ms"]])
    p_s_emb = compute_percentiles([s for s in metrics["sparse"]["embed_latencies_ms"]])
    p_fus = compute_percentiles(hybrid_fusion_latencies_ms)
    p_hyb = compute_percentiles(metrics["hybrid"]["latencies_ms"])

    print("\nHYBRID COMPONENT LATENCY BREAKDOWN (Avg / P50 / P95):")
    print(f"  * Dense Vectorization:   {p_d_emb['avg']:.2f} ms / {p_d_emb['p50']:.2f} ms / {p_d_emb['p95']:.2f} ms")
    print(f"  * BM25 Query Encoding:   {p_s_emb['avg']:.2f} ms / {p_s_emb['p50']:.2f} ms / {p_s_emb['p95']:.2f} ms")
    print(f"  * RRF Fusion Step:       {p_fus['avg']:.3f} ms / {p_fus['p50']:.3f} ms / {p_fus['p95']:.3f} ms")
    print(f"  * Total Hybrid Pipeline: {p_hyb['avg']:.2f} ms / {p_hyb['p50']:.2f} ms / {p_hyb['p95']:.2f} ms")

    print("\nRETRIEVAL DIVERSITY BY QUERY TYPE:")
    print("-" * 80)
    for q_item in BENCHMARK_QUERIES:
        q = q_item["query"]
        q_type = q_item["type"]
        d_vec = dense_service.embed_text(q)
        s_vec = bm25_service.embed_query(q)
        d_top = [r.title[:35] for r in repo.search_dense(d_vec, limit=2)]
        s_top = [r.title[:35] for r in repo.search_sparse(s_vec, limit=2)]
        h_top, _ = repo.search_hybrid(d_vec, s_vec, dense_top_k=20, bm25_top_k=20, final_top_k=2, rrf_k=60)
        h_titles = [r.title[:35] for r in h_top]

        print(f"[{q_type.upper()}] '{q}'")
        print(f"  - Dense Top-1:  {d_top[0] if d_top else 'None'}")
        print(f"  - BM25 Top-1:   {s_top[0] if s_top else 'None'}")
        print(f"  - Hybrid Top-1: {h_titles[0] if h_titles else 'None'}")
    print("-" * 80)
    print("BENCHMARK COMPLETED SUCCESSFULLY.")
    client.close()


if __name__ == "__main__":
    run_benchmark()
