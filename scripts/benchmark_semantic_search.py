import statistics
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import EmbeddingService

BENCHMARK_QUERIES = [
    "something scary to watch late at night",
    "relaxing evening with acoustic live music",
    "fun hands-on workshop for children and parents",
    "intense competitive sports tournament",
    "subterranean standup comedy show",
    "Shakespeare immersive drama play",
    "nighttime outdoor adventure and cycling",
    "interactive modern art and technology installation",
    "waterfront cultural food and artisan market",
    "classical string quartet concert by candlelight",
]


def run_benchmark(iterations_per_query: int = 5):
    print("=" * 70)
    print(" QdrantCinema — Phase 1B Semantic Retrieval Benchmark")
    print("=" * 70)

    settings = get_settings()

    # 1. Model initialization measurement
    t_init_start = time.perf_counter()
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
    )
    # Trigger model load
    embedding_service._ensure_model()
    model_init_time_s = time.perf_counter() - t_init_start

    # 2. Edge client & shard initialization
    client = EdgeClient(settings.edge_storage_path)
    shard = initialize_experience_collection(client, settings)
    repository = ExperienceRepository(shard, client, settings)

    dataset_size = repository.count()

    print(f"Embedding Model      : {settings.embedding_model_name}")
    print(f"Embedding Dimension  : {settings.vector_size}")
    print(f"Dataset Size         : {dataset_size} points")
    print(f"Model Init Time      : {model_init_time_s * 1000:.2f} ms ({model_init_time_s:.2f} s)")
    print(f"Benchmark Queries    : {len(BENCHMARK_QUERIES)} unique queries ({iterations_per_query} runs each)")
    print("-" * 70)

    # 3. Cold query measurement (first run)
    cold_query = BENCHMARK_QUERIES[0]
    t0 = time.perf_counter()
    cold_vec = embedding_service.embed_text(cold_query)
    t1 = time.perf_counter()
    cold_results = repository.search(cold_vec, limit=5)
    t2 = time.perf_counter()

    cold_emb_ms = (t1 - t0) * 1000
    cold_search_ms = (t2 - t1) * 1000
    cold_total_ms = (t2 - t0) * 1000

    print("COLD QUERY PERFORMANCE (First query after startup):")
    print(f" Query               : \"{cold_query}\"")
    print(f" Top Result          : [{cold_results[0].category}] {cold_results[0].title} (score: {cold_results[0].score:.4f})")
    print(f" Cold Embedding Time : {cold_emb_ms:.2f} ms")
    print(f" Cold Edge Search    : {cold_search_ms:.2f} ms")
    print(f" Cold Total Latency  : {cold_total_ms:.2f} ms")
    print("-" * 70)

    # 4. Warm repeated benchmark
    embedding_latencies: List[float] = []
    search_latencies: List[float] = []
    total_latencies: List[float] = []

    for query in BENCHMARK_QUERIES:
        for _ in range(iterations_per_query):
            t_start = time.perf_counter()
            vec = embedding_service.embed_text(query)
            t_emb_end = time.perf_counter()

            res = repository.search(vec, limit=5)
            t_end = time.perf_counter()

            emb_ms = (t_emb_end - t_start) * 1000
            search_ms = (t_end - t_emb_end) * 1000
            total_ms = (t_end - t_start) * 1000

            embedding_latencies.append(emb_ms)
            search_latencies.append(search_ms)
            total_latencies.append(total_ms)

    def calc_percentiles(data: List[float]) -> Tuple[float, float, float, float]:
        avg = statistics.mean(data)
        sorted_data = sorted(data)
        n = len(sorted_data)
        p50 = sorted_data[int(n * 0.50)]
        p95 = sorted_data[int(n * 0.95)]
        p99 = sorted_data[int(min(n - 1, int(n * 0.99)))]
        return avg, p50, p95, p99

    avg_emb, p50_emb, p95_emb, p99_emb = calc_percentiles(embedding_latencies)
    avg_search, p50_search, p95_search, p99_search = calc_percentiles(search_latencies)
    avg_tot, p50_tot, p95_tot, p99_tot = calc_percentiles(total_latencies)

    print("WARM QUERY LATENCY BENCHMARK (N={}):".format(len(total_latencies)))
    print(f" {'Metric':<22} | {'Avg (ms)':<10} | {'P50 (ms)':<10} | {'P95 (ms)':<10} | {'P99 (ms)':<10}")
    print(" " + "-" * 68)
    print(f" {'Local Embedding':<22} | {avg_emb:<10.2f} | {p50_emb:<10.2f} | {p95_emb:<10.2f} | {p99_emb:<10.2f}")
    print(f" {'Qdrant Edge Search':<22} | {avg_search:<10.2f} | {p50_search:<10.2f} | {p95_search:<10.2f} | {p99_search:<10.2f}")
    print(f" {'Total Retrieval':<22} | {avg_tot:<10.2f} | {p50_tot:<10.2f} | {p95_tot:<10.2f} | {p99_tot:<10.2f}")
    print("=" * 70)

    client.close()


if __name__ == "__main__":
    run_benchmark(iterations_per_query=5)
