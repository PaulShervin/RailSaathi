"""
RailSathi AI — RailRadar Quota & Rate-Limit Test Suite

Comprehensive tests verifying:
1. Monthly quota hard cap enforcement and persistent SQLite tracking across restarts.
2. Reserve quota isolation for critical recovery.
3. Conservative counting of outbound attempts, transient 500 failures, and retries.
4. SingleFlight deduplication and cache hits consuming 0 quota.
5. Thread-safe atomic reservations under concurrent worker pressure.
6. Sliding window per-minute rate limiting and Retry-After backoff handling.
7. Non-retrying of permanent 400/401/403/404 failures.
8. Provider dashboard usage reconciliation without state corruption.
9. Planner quota exhaustion handling and structured responses.
"""

import time
import pytest
import sqlite3
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.journey.quota import (
    DurableRailRadarQuotaManager,
    RailRadarPerMinuteLimiter,
    SingleFlightDeduplicator,
    RailRadarQuotaExhaustedError,
    RailRadarRateLimitWaitError,
    QuotaUsageReport,
)
from backend.journey.railradar_client import (
    RailRadarClient,
    RailRadarError,
    RailRadarAuthError,
    RailRadarBadRequestError,
    RailRadarNotFoundError,
    RailRadarRateLimitError,
    RailRadarUnavailableError,
)
from backend.journey.planner import JourneyPlanner, TripRequirements


# =====================================================================
# 1. Monthly Quota Manager & SQLite Persistence Tests
# =====================================================================

def test_quota_manager_initialization_and_default_report(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=5)

    report = mgr.get_usage_report()
    assert report.monthly_limit == 100
    assert report.used_requests == 0
    assert report.remaining_requests == 100
    assert report.reserve_held == 5
    assert report.available_for_standard == 95
    assert report.is_exhausted is False
    assert report.source == "local_sqlite_durable"
    assert report.reset_date != ""


def test_quota_persistence_across_restarts(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    
    # Process 1: Record 3 attempts
    mgr1 = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=50, reserve_quota=5)
    mgr1.reserve_and_record_attempt(endpoint="/v1/trains/between/SBC/MAS", method="GET")
    mgr1.reserve_and_record_attempt(endpoint="/v1/lookup/search/stations", method="GET")
    mgr1.reserve_and_record_attempt(endpoint="/v1/trains/20608/fare", method="GET")
    
    report1 = mgr1.get_usage_report()
    assert report1.used_requests == 3
    assert report1.remaining_requests == 47

    # Process 2 (simulated restart): Re-instantiate manager pointing to same SQLite database
    mgr2 = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=50, reserve_quota=5)
    report2 = mgr2.get_usage_report()
    assert report2.used_requests == 3
    assert report2.remaining_requests == 47
    assert report2.available_for_standard == 42


def test_quota_exhaustion_stops_standard_reservations(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=3, reserve_quota=1)

    # 1st request -> ok
    mgr.reserve_and_record_attempt(endpoint="/v1/test", allow_reserve=False)
    # 2nd request -> ok (used=2, limit=3, reserve=1 -> standard available=0)
    mgr.reserve_and_record_attempt(endpoint="/v1/test", allow_reserve=False)

    # 3rd request should fail for standard requests because reserve is held
    with pytest.raises(RailRadarQuotaExhaustedError) as exc_info:
        mgr.reserve_and_record_attempt(endpoint="/v1/test", allow_reserve=False)

    err = exc_info.value
    assert err.used_requests == 2
    assert err.monthly_limit == 3
    assert err.reserve_held == 1
    assert err.remaining_requests == 1

    # Emergency / priority request with allow_reserve=True can use the remaining 1
    attempt_id, rep = mgr.reserve_and_record_attempt(endpoint="/v1/emergency", allow_reserve=True)
    assert attempt_id > 0
    assert rep.used_requests == 3
    assert rep.remaining_requests == 0

    # Next attempt (even with reserve allowed) fails completely
    with pytest.raises(RailRadarQuotaExhaustedError):
        mgr.reserve_and_record_attempt(endpoint="/v1/emergency", allow_reserve=True)


def test_quota_counts_failed_attempts_conservatively(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=0)

    # Attempt 1 failed with 500
    att1_id, _ = mgr.reserve_and_record_attempt(endpoint="/v1/trains", attempt_number=1)
    mgr.record_attempt_outcome(att1_id, status_code=500, is_success=False, error_type="RailRadarUnavailableError")

    # Attempt 2 retry failed with timeout
    att2_id, _ = mgr.reserve_and_record_attempt(endpoint="/v1/trains", attempt_number=2, is_retry=True)
    mgr.record_attempt_outcome(att2_id, status_code=None, is_success=False, error_type="Timeout")

    # Attempt 3 succeeded
    att3_id, _ = mgr.reserve_and_record_attempt(endpoint="/v1/trains", attempt_number=3, is_retry=True)
    mgr.record_attempt_outcome(att3_id, status_code=200, is_success=True)

    report = mgr.get_usage_report()
    assert report.used_requests == 3
    assert report.remaining_requests == 7


def test_dashboard_reconciliation_updates_without_corrupting(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=5)

    mgr.reserve_and_record_attempt(endpoint="/v1/test")
    mgr.reserve_and_record_attempt(endpoint="/v1/test")
    assert mgr.get_usage_report().used_requests == 2

    # Provider dashboard indicates 12 requests have actually been consumed
    reconciled = mgr.reconcile_with_dashboard(dashboard_used=12, provider_reset_date="2026-11-01T00:00:00Z")
    assert reconciled.used_requests == 12
    assert reconciled.source == "provider_dashboard_reconciled"
    assert reconciled.dashboard_confirmed_used == 12
    assert reconciled.reset_date == "2026-11-01T00:00:00Z"

    # If local counter becomes higher later, reconciliation preserves the conservative higher count
    for _ in range(3):
        mgr.reserve_and_record_attempt(endpoint="/v1/test")
    assert mgr.get_usage_report().used_requests == 15

    # Reconciling with older stale dashboard value (12) will not downgrade 15
    reconciled_again = mgr.reconcile_with_dashboard(dashboard_used=12)
    assert reconciled_again.used_requests == 15


# =====================================================================
# 2. Per-Minute Rate Limiter & Backoff Tests
# =====================================================================

def test_rate_limiter_sliding_window_enforcement():
    # 3 requests per 1.0 second window
    limiter = RailRadarPerMinuteLimiter(rate_limit_per_minute=3, window_seconds=1.0)

    # 3 rapid tokens
    limiter.acquire(wait_if_needed=False)
    limiter.acquire(wait_if_needed=False)
    limiter.acquire(wait_if_needed=False)

    # 4th immediate token without waiting raises RailRadarRateLimitWaitError
    with pytest.raises(RailRadarRateLimitWaitError) as exc_info:
        limiter.acquire(wait_if_needed=False)

    assert exc_info.value.wait_seconds > 0.0

    # Wait window to slide
    time.sleep(1.05)
    # Next token should succeed immediately
    waited = limiter.acquire(wait_if_needed=False)
    assert waited == 0.0


def test_rate_limiter_respects_retry_after():
    limiter = RailRadarPerMinuteLimiter(rate_limit_per_minute=10, window_seconds=60.0)

    # Simulate upstream 429 returning Retry-After: 2
    limiter.note_retry_after(2)

    with pytest.raises(RailRadarRateLimitWaitError) as exc_info:
        limiter.acquire(wait_if_needed=False)

    assert exc_info.value.wait_seconds >= 1.0


def test_rate_limiter_jittered_backoff_calculation():
    limiter = RailRadarPerMinuteLimiter(max_backoff_seconds=5.0)

    for attempt in range(1, 5):
        backoff = limiter.calculate_backoff_jitter(attempt, base_delay=0.5)
        assert 0.1 <= backoff <= 5.0


# =====================================================================
# 3. Centralized 8-Stage Client Execution & Deduplication Tests
# =====================================================================

def test_cache_hits_consume_zero_quota(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"X-Trace-Id": "tr-123"}
    mock_resp.text = '{"success": true, "data": [{"trainNumber": "12633", "trainName": "KANYAKUMARI EXP"}]}'
    mock_resp.json.return_value = {"success": True, "data": [{"trainNumber": "12633", "trainName": "KANYAKUMARI EXP"}]}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
    )

    # 1st Call: Network dispatch -> consumes 1 quota
    res1 = client.search_trains("MS", "TEN", "2026-10-15")
    assert res1["cached"] is False
    assert quota_mgr.get_usage_report().used_requests == 1
    assert mock_session.request.call_count == 1

    # 2nd Call with identical params: Served from cache -> 0 quota consumed!
    res2 = client.search_trains("MS", "TEN", "2026-10-15")
    assert res2["cached"] is True
    assert quota_mgr.get_usage_report().used_requests == 1
    assert mock_session.request.call_count == 1  # No additional network dispatch


def test_singleflight_concurrent_deduplication(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=0)

    call_count = 0

    def mock_slow_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        time.sleep(0.1)
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = '{"success": true, "data": []}'
        resp.json.return_value = {"success": True, "data": []}
        return resp

    mock_session = MagicMock()
    mock_session.request.side_effect = mock_slow_request

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
    )

    # Launch 5 concurrent identical requests
    results = []
    threads = []
    def worker():
        res = client.search_trains("SBC", "MAS", "2026-10-20")
        results.append(res)

    for _ in range(5):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 5
    # SingleFlight ensures only 1 outbound network call was dispatched and 1 quota consumed
    assert call_count == 1
    assert quota_mgr.get_usage_report().used_requests == 1


def test_concurrent_workers_respect_quota_atomically(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    # Hard cap of exactly 5 requests
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=5, reserve_quota=0)

    def mock_request(*args, **kwargs):
        time.sleep(0.02)
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = '{"success": true, "data": []}'
        resp.json.return_value = {"success": True, "data": []}
        return resp

    mock_session = MagicMock()
    mock_session.request.side_effect = mock_request

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
        rate_limit_per_minute=100,  # High rate limit so pure quota atomicity is tested
        cache_enabled=False,  # Disable cache so all attempt network
    )

    successes = 0
    quota_errors = 0
    lock = threading.Lock()

    def worker(idx: int):
        nonlocal successes, quota_errors
        try:
            # Vary query so they don't deduplicate
            client.search_stations(f"STATION_{idx}")
            with lock:
                successes += 1
        except RailRadarQuotaExhaustedError:
            with lock:
                quota_errors += 1

    # 15 concurrent threads competing for 5 quota tokens
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert successes == 5
    assert quota_errors == 10
    assert quota_mgr.get_usage_report().used_requests == 5


def test_permanent_errors_are_not_retried(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.headers = {}
    mock_resp.text = '{"error": "Unauthorized"}'
    mock_resp.json.return_value = {"error": "Unauthorized"}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp

    client = RailRadarClient(
        api_key="bad_key",
        session=mock_session,
        max_retries=3,
        quota_manager=quota_mgr,
    )

    with pytest.raises(RailRadarAuthError):
        client.search_trains("MS", "TEN", "2026-10-15")

    # Exactly 1 outbound attempt made, no retries on 401!
    assert mock_session.request.call_count == 1
    assert quota_mgr.get_usage_report().used_requests == 1


# =====================================================================
# 4. Planner Integration & Quota Exhaustion Response Tests
# =====================================================================

def test_planner_returns_structured_quota_exhausted_response(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    # Set limit to 1 with 1 reserve -> standard available = 0
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=1, reserve_quota=1)

    with patch("backend.journey.timetable.TRAIN_DATA_PROVIDER", "railradar"):
        with patch("backend.journey.timetable.RAILRADAR_API_KEY", "test_key"):
            planner = JourneyPlanner()
            # Inject exhausted client
            exhausted_client = RailRadarClient(
                api_key="test_key",
                quota_manager=quota_mgr,
            )
            planner.train_service.provider.client = exhausted_client

            reqs = TripRequirements(
                origin="Chennai Egmore",
                destination_venue="Anna Stadium",
                destination_city="Tirunelveli",
                meeting_date="2026-10-15",
                meeting_time="10:00",
            )

            resp = planner.plan_journey(reqs)
            assert resp.status == "monthly_quota_exhausted"
            assert "quota exhausted" in resp.summary.lower()
            assert resp.trace[0]["stage"] == "candidate_retrieval"
            assert resp.trace[0]["status"] == "monthly_quota_exhausted"
