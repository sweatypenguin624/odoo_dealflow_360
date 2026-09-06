"""Small in-process sliding-window rate limiter for auth-sensitive routes.

Deliberately dependency-free (no Redis). For a multi-process deployment
swap the store for a shared one; the interface is a single `check()`.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from app.core.errors import RateLimitedError


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                raise RateLimitedError(
                    "Too many attempts. Please wait a few minutes and try again.", code="rate_limited"
                )
            bucket.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
