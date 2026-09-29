"""
app/metrics.py — Phase 3D: In-process operational metrics collector.

Collects lightweight, privacy-safe metrics (no query text, no user IDs,
no personal data). Aggregates search counts, latencies, sync stats, and
uptime for the /metrics endpoint.
"""

import threading
import time
from typing import Any, Dict, List, Optional


class MetricsCollector:
    """
    Thread-safe, in-process metrics collector.

    All data stored is aggregate / non-personal:
    - counters (search, success, failure, bookmark ops, sync attempts)
    - rolling latency buffer for P50/P95/P99 computation
    - startup timestamp for uptime
    """

    def __init__(self, max_latency_samples: int = 1000) -> None:
        self._lock = threading.Lock()
        self._started_at: float = time.monotonic()
        self._started_wall: float = time.time()

        # Search counters
        self._search_total: int = 0
        self._search_success: int = 0
        self._search_error: int = 0

        # Latency samples (rolling window, milliseconds)
        self._max_samples = max_latency_samples
        self._latency_samples: List[float] = []

        # Bookmark operation counters
        self._bookmark_adds: int = 0
        self._bookmark_removes: int = 0

        # Sync counters
        self._sync_attempts: int = 0
        self._sync_success: int = 0
        self._sync_error: int = 0
        self._sync_items_applied: int = 0

    # ------------------------------------------------------------------
    # Search instrumentation
    # ------------------------------------------------------------------

    def record_search(self, *, success: bool, latency_ms: float) -> None:
        """Record one completed search request."""
        with self._lock:
            self._search_total += 1
            if success:
                self._search_success += 1
            else:
                self._search_error += 1
            # Rolling window — discard oldest if full
            if len(self._latency_samples) >= self._max_samples:
                self._latency_samples.pop(0)
            self._latency_samples.append(latency_ms)

    # ------------------------------------------------------------------
    # Bookmark instrumentation
    # ------------------------------------------------------------------

    def record_bookmark_add(self) -> None:
        with self._lock:
            self._bookmark_adds += 1

    def record_bookmark_remove(self) -> None:
        with self._lock:
            self._bookmark_removes += 1

    # ------------------------------------------------------------------
    # Sync instrumentation
    # ------------------------------------------------------------------

    def record_sync(self, *, success: bool, items_applied: int = 0) -> None:
        with self._lock:
            self._sync_attempts += 1
            if success:
                self._sync_success += 1
                self._sync_items_applied += items_applied
            else:
                self._sync_error += 1

    # ------------------------------------------------------------------
    # Latency percentile helpers
    # ------------------------------------------------------------------

    def _percentile(self, samples: List[float], p: float) -> Optional[float]:
        """Compute the p-th percentile (0–100) from a sorted list."""
        if not samples:
            return None
        sorted_s = sorted(samples)
        idx = (p / 100.0) * (len(sorted_s) - 1)
        lo = int(idx)
        hi = lo + 1
        if hi >= len(sorted_s):
            return round(sorted_s[lo], 2)
        frac = idx - lo
        return round(sorted_s[lo] + frac * (sorted_s[hi] - sorted_s[lo]), 2)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Return a privacy-safe dict suitable for the /metrics endpoint."""
        with self._lock:
            uptime_seconds = round(time.monotonic() - self._started_at, 1)
            samples = list(self._latency_samples)

        avg_latency: Optional[float] = None
        if samples:
            avg_latency = round(sum(samples) / len(samples), 2)

        return {
            "uptime_seconds": uptime_seconds,
            "search": {
                "total": self._search_total,
                "success": self._search_success,
                "error": self._search_error,
                "latency_ms": {
                    "p50": self._percentile(samples, 50),
                    "p95": self._percentile(samples, 95),
                    "p99": self._percentile(samples, 99),
                    "avg": avg_latency,
                    "sample_count": len(samples),
                },
            },
            "bookmarks": {
                "adds": self._bookmark_adds,
                "removes": self._bookmark_removes,
            },
            "sync": {
                "attempts": self._sync_attempts,
                "success": self._sync_success,
                "error": self._sync_error,
                "items_applied": self._sync_items_applied,
            },
        }


# Module-level singleton used by the application
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Return (or lazily create) the process-global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
