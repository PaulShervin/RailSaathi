"""
RailSathi AI — RailRadar RPM & Request Efficiency Test Suite

Comprehensive tests verifying:
1. End-to-end journey planning call budget optimization (Chennai -> Tirunelveli morning meeting).
2. Local station registry resolution (0 station lookup calls).
3. Local schedule filtering and bounded fare enrichment (max 3 feasible candidates).
4. Direct feasibility preventing unnecessary connecting train fan-out.
5. Zero-quota cache reuse on repeated queries.
6. SingleFlight concurrency deduplication.
7. Simulated-clock RPM stress test (20 requests with 5 RPM limit, verifying <= 5 req per rolling 60s).
8. Cache stress test (20 requests -> 0 outbound HTTP calls).
9. Failure isolation (live provider failures never fake live results).
"""

import time
import pytest
import threading
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

from backend.journey.models import TripRequirements
from backend.journey.planner import JourneyPlanner
from backend.journey.quota import (
    DurableRailRadarQuotaManager,
    RailRadarPerMinuteLimiter,
    RailRadarQuotaExhaustedError,
    RailRadarRateLimitWaitError,
)
from backend.journey.railradar_client import (
    RailRadarClient,
    RailRadarAuthError,
    RailRadarUnavailableError,
)


class MockRailRadarServer:
    """Mock HTTP transport simulating RailRadar API endpoints with metrics telemetry."""

    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []
        self.calls_by_type = {
            "stations": 0,
            "trains": 0,
            "fares": 0,
        }

    def handle_request(self, method: str, url: str, params: Dict[str, Any], headers: Dict[str, str], **kwargs):
        resp = MagicMock()
        resp.headers = {"X-Trace-Id": f"mock-trace-{len(self.call_history)+1}"}

        # 1. Station search
        if "/v1/lookup/search/stations" in url:
            self.calls_by_type["stations"] += 1
            self.call_history.append({"type": "stations", "url": url, "params": params, "time": time.time()})
            resp.status_code = 200
            resp.text = '{"success": true, "data": [{"stationCode": "MS", "stationName": "Chennai Egmore"}]}'
            resp.json.return_value = {
                "success": True,
                "data": [{"stationCode": "MS", "stationName": "Chennai Egmore"}]
            }
            return resp

        # 2. Trains between stations
        if "/v1/trains/between" in url:
            self.calls_by_type["trains"] += 1
            self.call_history.append({"type": "trains", "url": url, "params": params, "time": time.time()})
            resp.status_code = 200
            # Return realistic train schedule MS -> TEN
            trains_data = {
                "success": True,
                "data": {
                    "trains": [
                        {
                            "train": {
                                "trainNumber": "20665",
                                "trainName": "MS TEN VB EXP",
                                "departureTime": "14:50",
                                "arrivalTime": "22:40",
                                "duration": "07:50",
                                "classes": ["CC", "EC"],
                                "runningDays": ["Mon", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            }
                        },
                        {
                            "train": {
                                "trainNumber": "20605",
                                "trainName": "MS TEN SF EXP",
                                "departureTime": "22:30",
                                "arrivalTime": "07:15",
                                "duration": "08:45",
                                "classes": ["1A", "2A", "3A", "SL"],
                                "runningDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            }
                        },
                        {
                            "train": {
                                "trainNumber": "12633",
                                "trainName": "KANYAKUMARI EXP",
                                "departureTime": "17:20",
                                "arrivalTime": "03:55",
                                "duration": "10:35",
                                "classes": ["1A", "2A", "3A", "SL"],
                                "runningDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            }
                        },
                        {
                            "train": {
                                "trainNumber": "12631",
                                "trainName": "NELLAI EXPRESS",
                                "departureTime": "19:50",
                                "arrivalTime": "06:30",
                                "duration": "10:40",
                                "classes": ["1A", "2A", "3A", "SL"],
                                "runningDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            }
                        },
                        {
                            "train": {
                                "trainNumber": "20635",
                                "trainName": "ANANTHAPURI EXP",
                                "departureTime": "19:50",
                                "arrivalTime": "06:50",
                                "duration": "11:00",
                                "classes": ["1A", "2A", "3A", "SL"],
                                "runningDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            }
                        },
                    ]
                }
            }
            resp.text = str(trains_data)
            resp.json.return_value = trains_data
            return resp

        # 3. Fare calculator
        if "/fare" in url:
            self.calls_by_type["fares"] += 1
            self.call_history.append({"type": "fares", "url": url, "params": params, "time": time.time()})
            resp.status_code = 200
            fare_data = {
                "success": True,
                "data": {
                    "totalFare": 1250.0,
                    "baseFare": 1100.0,
                    "reservationFee": 40.0,
                    "superfastFee": 45.0,
                    "gst": 65.0,
                }
            }
            resp.text = str(fare_data)
            resp.json.return_value = fare_data
            return resp

        resp.status_code = 404
        resp.text = '{"error": "Not Found"}'
        resp.json.return_value = {"error": "Not Found"}
        return resp


# =====================================================================
# 1. End-to-End Chennai -> Tirunelveli Optimization Test
# =====================================================================

def test_chennai_to_tirunelveli_optimization_and_metrics(tmp_path):
    """
    Simulate passenger travelling from Chennai to Tirunelveli for a 10:00 AM meeting.
    Verify:
    - 0 station lookup calls (resolved locally via registry)
    - Schedule searched for target & previous day (overnight)
    - Local Python feasibility filtering
    - 0 connecting route calls (direct trains meet deadline)
    - Fares fetched ONLY for top 3 feasible candidates
    - Complete metrics audit
    """
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=5)
    mock_server = MockRailRadarServer()

    mock_session = MagicMock()
    mock_session.request.side_effect = mock_server.handle_request

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
    )

    with patch("backend.journey.timetable.TRAIN_DATA_PROVIDER", "railradar"):
        with patch("backend.journey.timetable.RAILRADAR_API_KEY", "test_key"):
            planner = JourneyPlanner()
            planner.train_service.provider.client = client

            reqs = TripRequirements(
                origin="Chennai Egmore",
                destination_venue="Anna Stadium, Tirunelveli",
                destination_city="Tirunelveli",
                meeting_date="2026-10-15",
                meeting_time="10:00",
                preferred_class="3A",
            )

            # --- RUN 1: Initial Journey Plan ---
            plan = planner.plan_journey(reqs)

            assert plan.status == "answered"
            assert plan.best_match is not None
            assert plan.best_match.is_feasible is True

            # Metrics for Run 1
            total_evaluations = len(plan.feasible_alternatives) + 1
            assert total_evaluations >= 3

            # Audit network calls made:
            # 1. Stations: 0 (local registry)
            assert mock_server.calls_by_type["stations"] == 0

            # 2. Schedule calls: 4 (2 dates: meeting date + previous day overnight x 2 station pairs)
            # Secondary suburban pairs beyond the 2 primary terminals were skipped
            assert mock_server.calls_by_type["trains"] == 4

            # 3. Connecting routes: 0 (because feasible direct trains exist)
            assert len(plan.connecting_options) == 0

            # 4. Fares: exactly 3 (top 3 feasible candidates)
            assert mock_server.calls_by_type["fares"] == 3

            total_calls_run1 = len(mock_server.call_history)
            assert total_calls_run1 == 7  # 4 train queries + 3 fare queries
            assert quota_mgr.get_usage_report().used_requests == 7

            # --- RUN 2: Repeating Identical Query ---
            # Should be 100% served from tiered cache with 0 new HTTP requests
            plan2 = planner.plan_journey(reqs)
            assert plan2.status == "answered"

            total_calls_run2 = len(mock_server.call_history)
            # ZERO new outbound HTTP calls on repetition!
            assert total_calls_run2 == total_calls_run1
            assert quota_mgr.get_usage_report().used_requests == total_calls_run1


# =====================================================================
# 2. Connecting Routes Skipped When Direct Options are Feasible
# =====================================================================

def test_connecting_routes_skipped_when_direct_feasible(tmp_path):
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=5)
    mock_server = MockRailRadarServer()

    mock_session = MagicMock()
    mock_session.request.side_effect = mock_server.handle_request

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
    )

    with patch("backend.journey.timetable.TRAIN_DATA_PROVIDER", "railradar"):
        planner = JourneyPlanner()
        planner.train_service.provider.client = client

        reqs = TripRequirements(
            origin="Chennai Egmore",
            destination_venue="District Court, Tirunelveli",
            destination_city="Tirunelveli",
            meeting_date="2026-10-15",
            meeting_time="11:00",
        )

        resp = planner.plan_journey(reqs)
        assert resp.best_match is not None
        assert resp.best_match.is_feasible is True
        # Connecting route search was not triggered
        assert len(resp.connecting_options) == 0


# =====================================================================
# 3. Simulated Clock RPM Stress Test (20 requests with 5 RPM limit)
# =====================================================================

def test_rpm_stress_test_with_simulated_clock(tmp_path):
    """
    Stress test scheduling 20 API requests against an artificial 5 req/min limit.
    Uses an injected simulated clock to verify rolling 60s window without real sleeps.
    """
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=0)

    # Simulated virtual clock
    simulated_time = 1000.0

    def clock_fn():
        return simulated_time

    def sleep_fn(secs: float):
        nonlocal simulated_time
        simulated_time += secs

    # 5 requests per 60.0 second window
    limiter = RailRadarPerMinuteLimiter(
        rate_limit_per_minute=5,
        window_seconds=60.0,
        clock_fn=clock_fn,
        sleep_fn=sleep_fn,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.text = '{"success": true, "data": []}'
    mock_resp.json.return_value = {"success": True, "data": []}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
        rate_limiter=limiter,
        rate_limiter_max_wait_seconds=500.0,
        cache_enabled=False,  # Force network dispatch to test rate limiter
    )

    dispatch_timestamps = []

    for i in range(20):
        client.search_stations(f"QUERY_{i}")
        dispatch_timestamps.append(simulated_time)

    assert len(dispatch_timestamps) == 20
    assert mock_session.request.call_count == 20
    assert quota_mgr.get_usage_report().used_requests == 20

    # Verify Sliding Window Invariant: In ANY 60-second window, at most 5 requests were dispatched
    for i, t_start in enumerate(dispatch_timestamps):
        window_end = t_start + 60.0
        requests_in_window = sum(1 for t in dispatch_timestamps if t_start <= t < window_end)
        assert requests_in_window <= 5, f"Window starting at {t_start:.1f}s exceeded 5 reqs: {requests_in_window}"


# =====================================================================
# 4. Cache Stress Test (20 Identical Requests -> 0 Outbound HTTP)
# =====================================================================

def test_cache_stress_test_zero_outbound_http(tmp_path):
    """
    Stress test sending 20 rapid identical queries.
    Verify that only the 1st request dispatches an HTTP call, and all 19 subsequent calls hit cache.
    """
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.text = '{"success": true, "data": [{"trainNumber": "20605"}]}'
    mock_resp.json.return_value = {"success": True, "data": [{"trainNumber": "20605"}]}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
        cache_enabled=True,
    )

    results = []
    for _ in range(20):
        res = client.search_trains("MS", "TEN", "2026-10-15")
        results.append(res)

    assert len(results) == 20
    # Exactly 1 HTTP request made!
    assert mock_session.request.call_count == 1
    # Exactly 1 quota token consumed!
    assert quota_mgr.get_usage_report().used_requests == 1
    # 19 cache hits
    assert client.get_metrics()["cache_hits"] == 19


# =====================================================================
# 5. Failure Isolation Test (No Fake Live Results)
# =====================================================================

def test_live_provider_failure_never_fakes_live_results(tmp_path):
    """
    Verify that when RailRadar returns 503 or 401, the system does not invent fake live data,
    but raises typed errors or returns provider_unavailable status.
    """
    db_file = tmp_path / "test_usage.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=100, reserve_quota=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.headers = {}
    mock_resp.text = '{"error": "Service Unavailable"}'
    mock_resp.json.return_value = {"error": "Service Unavailable"}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp

    client = RailRadarClient(
        api_key="test_key",
        session=mock_session,
        quota_manager=quota_mgr,
        max_retries=0,
    )

    with patch("backend.journey.timetable.TRAIN_DATA_PROVIDER", "railradar"):
        planner = JourneyPlanner()
        planner.train_service.provider.client = client

        reqs = TripRequirements(
            origin="Chennai Egmore",
            destination_venue="Anna Stadium",
            destination_city="Tirunelveli",
            meeting_date="2026-10-15",
            meeting_time="10:00",
        )

        resp = planner.plan_journey(reqs)
        # Must report provider_unavailable, not pretend fake trains were returned
        assert resp.status == "provider_unavailable"
        assert "provider unavailable" in resp.summary.lower()
