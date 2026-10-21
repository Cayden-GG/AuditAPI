"""
Simple request rate limiting module that sits in front of all api enpoints 
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import Request


class RateLimiter:
    """RateLimiter class

    uses clients IP to bucket clients and track incoming requests from each client
    
    @Args:
        max_requests (int) -- max allowed incoming requests per client per window
        window_seconds (int) -- window duration 
    """
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> Tuple[bool, int]:
        """Bucket each request and allows all requests in window under max requets
        
        If a request is more than the max request count disallow the request and return the wait time till next allowed request 

        @Returns:
            allowed (bool) -- if the request is allowed
            retry_after_time (int) -- time till next retry
        """
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

    def __repr__(self) -> str:
        return f"RateLimiter(max_requests: {self.max_requests}, window_seconds: {self.window_seconds}, buckets: {len(self._buckets)})"


def _client_ip(request: Request) -> str:
    """Collect the clients IP from the request

    @Args:
        request (Request) -- browser request 

    @Returns:
        client ip (str) -- clients ip or "unkown"
    """

    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()
    
    if request.client:
        return request.client.host

    return "unknown"


def build_rate_limiter() -> Tuple[int, int, RateLimiter | None]:
    """Builds and initialises a RateLimiter instance from the RATE_LIMIT_* env vars

    @Returns:
        max_requests (int) -- max requests allowed per window
        window_seconds (int) -- window duration
        rate limiter (RateLimiter | None) -- the rate limiter if enabled else None
    """
    disabled = os.getenv("RATE_LIMIT_DISABLED", False) 
    disabled = disabled in ("True", "true", "1") 

    try:
        max_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
        window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError:
        max_requests = 30
        window_seconds = 60

    if disabled or max_requests <= 0 or window_seconds <= 0: 
        return max_requests, window_seconds, None

    return max_requests, window_seconds, RateLimiter(max_requests, window_seconds)


def rate_limit_key(request: Request) -> str:
    """returns the clients ip to use a key for rate limiting""" 
    return _client_ip(request)
