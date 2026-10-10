"""
RailSathi AI — Rate Limiter Unit Tests
"""

import time
import pytest
from backend.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_allows_under_limit():
    limiter = SlidingWindowRateLimiter(requests_per_minute=5)
    ip = "192.168.1.100"
    for i in range(5):
        allowed, rem, _ = limiter.is_allowed(ip)
        assert allowed is True
        assert rem == 5 - (i + 1)


def test_rate_limiter_blocks_over_limit():
    limiter = SlidingWindowRateLimiter(requests_per_minute=3)
    ip = "10.0.0.1"
    # First 3 allowed
    assert limiter.is_allowed(ip)[0] is True
    assert limiter.is_allowed(ip)[0] is True
    assert limiter.is_allowed(ip)[0] is True
    # 4th blocked
    allowed, rem, retry = limiter.is_allowed(ip)
    assert allowed is False
    assert rem == 0
    assert retry > 0


def test_rate_limiter_distinct_ips():
    limiter = SlidingWindowRateLimiter(requests_per_minute=2)
    # IP 1 uses quota
    limiter.is_allowed("1.1.1.1")
    limiter.is_allowed("1.1.1.1")
    assert limiter.is_allowed("1.1.1.1")[0] is False

    # IP 2 still has quota
    assert limiter.is_allowed("2.2.2.2")[0] is True
