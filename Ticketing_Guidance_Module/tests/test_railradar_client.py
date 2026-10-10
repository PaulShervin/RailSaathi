"""
RailSathi AI — RailRadar Client Unit & Integration Tests

Tests RailRadarClient HTTP handling, authentication headers, error mapping,
retries, timeout handling, secret protection, response normalization, and caching.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from backend.journey.railradar_client import (
    RailRadarClient,
    RailRadarCache,
    RailRadarError,
    RailRadarAuthError,
    RailRadarBadRequestError,
    RailRadarNotFoundError,
    RailRadarRateLimitError,
    RailRadarUnavailableError,
    RailRadarNetworkError,
    RailRadarSchemaError,
    RailRadarConfigurationError,
)
from backend.journey.timetable import (
    parse_duration_to_minutes,
    calculate_day_offset,
    RailRadarTrainDataProvider,
    TrainSearchService,
)
from backend.journey.models import TripRequirements, TrainService, JourneyEvaluation


class MockResponse:
    """Mock requests.Response helper."""
    def __init__(self, status_code: int, json_data: dict, text: str = "", headers: dict = None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or json.dumps(json_data)
        self.headers = headers or {"Content-Type": "application/json", "X-Trace-Id": "trace-test-123"}

    def json(self):
        return self._json_data


# =====================================================================
# 1. Helper Unit Tests (Duration & Day-Offset)
# =====================================================================

def test_parse_duration_to_minutes():
    """Verify robust duration parsing for various formats."""
    assert parse_duration_to_minutes("04:25") == 265
    assert parse_duration_to_minutes("4:25") == 265
    assert parse_duration_to_minutes("4h 25m") == 265
    assert parse_duration_to_minutes("5h") == 300
    assert parse_duration_to_minutes("45m") == 45
    assert parse_duration_to_minutes(360) == 360
    assert parse_duration_to_minutes("360") == 360
    assert parse_duration_to_minutes("") == 0
    assert parse_duration_to_minutes(None) == 0


def test_calculate_day_offset():
    """Verify calculation of overnight calendar day offsets."""
    # Explicit from_day & to_day
    assert calculate_day_offset("05:45", "10:10", from_day=1, to_day=1) == 0
    assert calculate_day_offset("22:40", "04:35", from_day=1, to_day=2) == 1
    assert calculate_day_offset("19:50", "05:20", from_day=1, to_day=3) == 2

    # Overnight time rollover heuristic (dep 22:40, arr 04:35)
    assert calculate_day_offset("22:40", "04:35") == 1
    # Daytime (dep 06:00, arr 11:00)
    assert calculate_day_offset("06:00", "11:00") == 0


# =====================================================================
# 2. RailRadarCache Tests
# =====================================================================

def test_cache_set_and_get():
    """Verify tier caching, retrieval, and TTL."""
    cache = RailRadarCache(enabled=True, ttl_stations=100, ttl_trains=100, ttl_fares=100)
    retrieved_at = cache.set("stations", "MAS:10", [{"code": "MAS", "name": "Chennai"}])
    assert retrieved_at is not None

    cached = cache.get("stations", "MAS:10")
    assert cached is not None
    data, ts = cached
    assert data == [{"code": "MAS", "name": "Chennai"}]
    assert ts == retrieved_at


def test_cache_disabled():
    """Verify that disabled cache returns None."""
    cache = RailRadarCache(enabled=False)
    cache.set("trains", "SBC:MAS", {"trains": []})
    assert cache.get("trains", "SBC:MAS") is None


# =====================================================================
# 3. RailRadarClient Authentication & Header Security Tests
# =====================================================================

def test_client_missing_api_key_raises_config_error():
    """Client must raise RailRadarConfigurationError when API key is missing."""
    client = RailRadarClient(api_key="")
    with pytest.raises(RailRadarConfigurationError) as exc_info:
        client.search_trains("SBC", "MAS")
    assert "RAILRADAR_API_KEY is not configured" in str(exc_info.value)


def test_client_headers_contain_bearer_token():
    """Verify request headers contain Bearer token."""
    client = RailRadarClient(api_key="test_secret_key_12345")
    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer test_secret_key_12345"
    assert headers["Accept"] == "application/json"


def test_client_logs_and_errors_redact_secrets():
    """Ensure error messages never leak the actual API key."""
    client = RailRadarClient(api_key="super_secret_pat_99999")
    safe_url = client._sanitize_log_url("https://api.railradar.in/v1/test?token=super_secret_pat_99999&q=MAS")
    assert "super_secret_pat_99999" not in safe_url
    assert "[REDACTED]" in safe_url


# =====================================================================
# 4. Mocked HTTP Endpoint Tests
# =====================================================================

def test_search_trains_success():
    """Test successful GET /v1/trains/between/{from}/{to} response parsing."""
    mock_session = MagicMock()
    mock_resp_data = {
        "success": True,
        "data": {
            "from": {"code": "SBC", "name": "KSR Bengaluru"},
            "to": {"code": "MAS", "name": "MGR Chennai Central"},
            "count": 1,
            "trains": [
                {
                    "number": "20608",
                    "name": "MAS VANDE BHARAT",
                    "type": "VB",
                    "runDays": ["Mon", "Tue", "Thu", "Fri", "Sat", "Sun"],
                    "from": {"departure": "05:45", "day": 1, "sequence": 1},
                    "to": {"arrival": "10:10", "day": 1, "sequence": 5},
                    "duration": "04:25",
                    "classes": ["CC", "EC"],
                }
            ],
        },
        "meta": {"traceId": "trace-rr-001"},
    }
    mock_session.request.return_value = MockResponse(200, mock_resp_data)

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    res = client.search_trains("SBC", "MAS", journey_date="2026-10-25")

    assert res["data"]["count"] == 1
    assert res["data"]["trains"][0]["number"] == "20608"
    assert res["trace_id"] == "trace-rr-001"
    assert client.get_metrics()["train_searches_made"] == 1


def test_search_stations_success():
    """Test successful GET /v1/lookup/search/stations."""
    mock_session = MagicMock()
    mock_resp_data = {
        "success": True,
        "data": [
            {"code": "MAS", "name": "MGR Chennai Central", "city": "Chennai"},
            {"code": "MS", "name": "Chennai Egmore", "city": "Chennai"},
        ],
        "meta": {"traceId": "trace-station-001"},
    }
    mock_session.request.return_value = MockResponse(200, mock_resp_data)

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    res = client.search_stations("Chennai", limit=10)

    assert len(res["data"]) == 2
    assert res["data"][0]["code"] == "MAS"
    assert client.get_metrics()["station_searches_made"] == 1


def test_get_fare_success():
    """Test successful GET /v1/trains/{number}/fare."""
    mock_session = MagicMock()
    mock_resp_data = {
        "success": True,
        "data": {
            "trainNumber": "20608",
            "trainName": "MAS VANDE BHARAT",
            "sourceStation": "SBC",
            "destinationStation": "MAS",
            "classCode": "CC",
            "quotaCode": "GN",
            "totalFare": 995.0,
            "breakdown": {
                "baseFare": 750.0,
                "reservationCharge": 40.0,
                "superfastCharge": 45.0,
                "goodsServiceTax": 40.0,
                "cateringCharge": 120.0,
            },
        },
        "meta": {"traceId": "trace-fare-001"},
    }
    mock_session.request.return_value = MockResponse(200, mock_resp_data)

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    res = client.get_fare(
        train_number="20608",
        source_station_code="SBC",
        destination_station_code="MAS",
        journey_date="2026-10-25",
        class_code="CC",
        quota_code="GN",
    )

    assert res["data"]["totalFare"] == 995.0
    assert res["data"]["breakdown"]["cateringCharge"] == 120.0
    assert client.get_metrics()["fare_lookups_made"] == 1


# =====================================================================
# 5. HTTP Error Code Mapping Tests
# =====================================================================

def test_http_400_bad_request_mapping():
    """HTTP 400 must raise RailRadarBadRequestError."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(400, {"message": "Invalid date parameter"})

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    with pytest.raises(RailRadarBadRequestError) as exc:
        client.search_trains("SBC", "MAS", journey_date="2026-10-25")
    assert "Bad Request" in str(exc.value)


def test_http_401_auth_error_mapping():
    """HTTP 401 must raise RailRadarAuthError."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(401, {"message": "Invalid API key"})

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    with pytest.raises(RailRadarAuthError) as exc:
        client.search_trains("SBC", "MAS")
    assert "authentication failed" in str(exc.value)


def test_http_404_not_found_mapping():
    """HTTP 404 must raise RailRadarNotFoundError."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(404, {"message": "No trains found"})

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    with pytest.raises(RailRadarNotFoundError) as exc:
        client.search_trains("XYZ", "ABC")
    assert "Not Found" in str(exc.value)


def test_http_429_rate_limit_mapping():
    """HTTP 429 must raise RailRadarRateLimitError with Retry-After parsed."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(
        429,
        {"message": "Rate limit exceeded. Quota: 100/min."},
        headers={"Retry-After": "30", "X-Trace-Id": "trace-429"},
    )

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    with pytest.raises(RailRadarRateLimitError) as exc:
        client.search_trains("SBC", "MAS")
    assert exc.value.retry_after == 30
    assert "Rate Limit Exceeded" in str(exc.value)


def test_http_503_unavailable_mapping():
    """HTTP 503 must raise RailRadarUnavailableError after retries."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(503, {"message": "Service under maintenance"})

    client = RailRadarClient(api_key="test_key", session=mock_session, max_retries=0, cache_enabled=False)
    with pytest.raises(RailRadarUnavailableError) as exc:
        client.search_trains("SBC", "MAS")
    assert "unavailable" in str(exc.value)


def test_success_false_in_200_body():
    """If provider returns HTTP 200 with success: false envelope, raise error."""
    mock_session = MagicMock()
    mock_session.request.return_value = MockResponse(200, {"success": False, "message": "Station code invalid"})

    client = RailRadarClient(api_key="test_key", session=mock_session, cache_enabled=False)
    with pytest.raises(RailRadarBadRequestError) as exc:
        client.search_trains("SBC", "MAS")
    assert "Station code invalid" in str(exc.value)
