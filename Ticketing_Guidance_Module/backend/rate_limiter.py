"""
RailSathi AI — Sliding Window Rate Limiter

Thread-safe, in-memory sliding window rate limiter for Flask API endpoints.
Provides IP-based throttling, rate-limit headers, and HTTP 429 responses.
"""

import time
import threading
from collections import defaultdict, deque
from functools import wraps
from flask import request, jsonify


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter per client IP."""

    def __init__(self, requests_per_minute: int = 60):
        self.limit = requests_per_minute
        self.window_seconds = 60.0
        self.requests = defaultdict(deque)
        self.lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> tuple[bool, int, int]:
        """
        Check if request is allowed for client_ip.
        Returns: (is_allowed, remaining_requests, reset_seconds)
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self.lock:
            q = self.requests[client_ip]

            # Evict timestamps older than sliding window
            while q and q[0] < window_start:
                q.popleft()

            count = len(q)
            if count >= self.limit:
                oldest = q[0]
                reset_sec = int(max(1, (oldest + self.window_seconds) - now))
                return False, 0, reset_sec

            # Record current request
            q.append(now)
            remaining = self.limit - len(q)
            return True, remaining, 60


def rate_limit(limiter: SlidingWindowRateLimiter):
    """Decorator to apply rate limiting to a Flask route."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
            if "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            allowed, remaining, retry_after = limiter.is_allowed(client_ip)
            if not allowed:
                response = jsonify({
                    "error": "Rate limit exceeded. Please slow down your requests.",
                    "status": "rate_limited",
                    "retry_after_seconds": retry_after,
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                response.headers["X-RateLimit-Limit"] = str(limiter.limit)
                response.headers["X-RateLimit-Remaining"] = "0"
                return response

            response = f(*args, **kwargs)
            # Add rate limit headers to response
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(limiter.limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response
        return decorated_function
    return decorator
