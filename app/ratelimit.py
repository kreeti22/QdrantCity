"""
app/ratelimit.py — Phase 3C: Lightweight in-process sliding-window rate limiter.

Protects expensive endpoints (search, sync/run) from abuse without
requiring any external service. Each limiter instance maintains a
per-client deque of request timestamps.

Design:
- One RateLimiter instance per endpoint (or shared by client key).
- Thread-safe via threading.Lock.
- Sliding window — drops timestamps older than window_seconds.
- Returns (allowed: bool, retry_after_seconds: float) so callers can
  build proper 429 responses without stack traces.
"""

import threading
import time
from collections import deque
from typing import Dict, Tuple


class _ClientWindow:
    """Sliding timestamp window for a single client key."""

    __slots__ = ("timestamps",)

    def __init__(self) -> None:
        self.timestamps: deque = deque()


class RateLimiter:
    """
    Sliding-window rate limiter keyed by an arbitrary string (e.g. client IP).

    Parameters
    ----------
    max_requests : int
        Maximum number of requests allowed within `window_seconds`.
    window_seconds : float
        Duration of the sliding window in seconds.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._clients: Dict[str, _ClientWindow] = {}

    def is_allowed(self, client_key: str) -> Tuple[bool, float]:
        """
        Check whether `client_key` is within the rate limit.

        Returns
        -------
        (allowed, retry_after_seconds)
            `allowed` is True when the request is within limit.
            `retry_after_seconds` is 0.0 when allowed, or the number of
            seconds until the oldest in-window request expires when denied.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            if client_key not in self._clients:
                self._clients[client_key] = _ClientWindow()
            window = self._clients[client_key]

            # Evict expired timestamps
            while window.timestamps and window.timestamps[0] <= cutoff:
                window.timestamps.popleft()

            if len(window.timestamps) < self._max_requests:
                window.timestamps.append(now)
                return True, 0.0
            else:
                # Retry after the oldest timestamp expires
                oldest = window.timestamps[0]
                retry_after = round(oldest - cutoff, 2)
                return False, retry_after

    def cleanup_stale_clients(self, max_idle_seconds: float = 3600.0) -> int:
        """
        Remove client entries that have had no requests in the past
        `max_idle_seconds`. Call periodically to avoid unbounded growth.
        Returns the number of entries removed.
        """
        cutoff = time.monotonic() - max_idle_seconds
        removed = 0
        with self._lock:
            stale = [
                k
                for k, w in self._clients.items()
                if not w.timestamps or w.timestamps[-1] <= cutoff
            ]
            for k in stale:
                del self._clients[k]
                removed += 1
        return removed
