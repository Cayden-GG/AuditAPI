from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import Request


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> Tuple[bool, int]:
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = int(bucket[0] + self.window_seconds - now)
                return False, max(retry_after, 1)
            bucket.append(now)
            return True, 0


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def build_rate_limiter() -> tuple[bool, int, int, RateLimiter | None]:
    enabled = os.getenv("RATE_LIMIT_ENABLED", "1") != "0"
    try:
        max_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    except ValueError:
        max_requests = 60
    try:
        window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError:
        window_seconds = 60

    if not enabled or max_requests <= 0 or window_seconds <= 0:
        return False, max_requests, window_seconds, None
    return True, max_requests, window_seconds, RateLimiter(max_requests, window_seconds)


def rate_limit_key(request: Request) -> str:
    return _client_ip(request)
