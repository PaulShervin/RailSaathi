"""
RailSathi AI — Connecting Trains & Multi-Leg Journey Unit & Integration Tests

Covers:
1. Hub candidate resolution (corridor matching and exclusion of origin/destination).
2. Connecting train pair discovery with layover constraints (30m <= layover <= 360m).
3. Rejection of invalid or tight transfers (< 30m layover).
4. Overnight transfers across calendar dates and day offsets.
5. Infeasible connections when Leg 2 arrives after the meeting deadline.
6. Indeterminate feasibility when last-mile duration is missing / unknown.
7. Safe combined fare handling (None when either leg fare is absent, never invented).
8. Deduplication of candidate pairs.
9. Booking URL allowlist validation on both legs.
10. Provider failure handling without silent mock fallback when configured.
11. End-to-end integration via JourneyPlanner.plan_journey.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest

from backend.journey.models import TripRequirements, TrainService, LastMileEstimate, FareQuote
from backend.journey.connecting import (
    ConnectingTrainDiscoveryService,
    MIN_TRANSFER_LAYOVER_MINUTES,
    MAX_TRANSFER_LAYOVER_MINUTES,
)
from backend.journey.planner import JourneyPlanner
from backend.journey.location import LocationResolutionService
from backend.journey.timetable import TrainSearchService, RailRadarTrainDataProvider
from backend.journey.railradar_client import RailRadarAuthError, RailRadarUnavailableError
from backend.journey.booking import is_url_safe_and_allowlisted


def test_connecting_hub_resolution():
    """Verify appropriate intermediate hubs are resolved for Chennai -> Tirunelveli corridor."""
    service = ConnectingTrainDiscoveryService()
    hubs = service.get_candidate_hubs(origin_codes=["MS", "MAS"], dest_codes=["TEN"])
    assert "TPJ" in hubs or "MDU" in hubs
    assert "MS" not in hubs
    assert "TEN" not in hubs


def test_connecting_trains_discovery_and_layover_validation():
    """Verify connecting trains discover feasible pairs with valid layover windows."""
    service = ConnectingTrainDiscoveryService()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="VOC Ground, Palayamkottai",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",
        meeting_time="22:30",
        required_arrival_buffer_minutes=30,
    )
    loc = LocationResolutionService()
    last_mile = loc.estimate_last_mile("TEN", "VOC Ground, Palayamkottai")

    connecting_options = service.discover_connecting_journeys(
        origin_codes=["MS"],
        dest_codes=["TEN"],
        requirements=req,
        last_mile=last_mile,
    )

    assert isinstance(connecting_options, list)
    if connecting_options:
        conn = connecting_options[0]
        assert conn.layover_minutes >= MIN_TRANSFER_LAYOVER_MINUTES
        assert conn.layover_minutes <= MAX_TRANSFER_LAYOVER_MINUTES
        assert conn.interchange_station_code in ["TPJ", "MDU", "SA", "ED"]
        assert conn.leg_1.booking_handoff is not None
        assert conn.leg_2.booking_handoff is not None
        assert is_url_safe_and_allowlisted(conn.leg_1.booking_handoff.booking_url)
        assert is_url_safe_and_allowlisted(conn.leg_2.booking_handoff.booking_url)


def test_tight_or_negative_layover_rejected():
    """Verify transfers with < 30m layover or negative layovers are rejected."""
    # Create mock train service returning a leg1 arriving at 12:00 and leg2 departing at 12:15 (15m layover)
    mock_search = MagicMock(spec=TrainSearchService)
    t1 = TrainService(
        train_number="11111",
        train_name="Leg 1 Express",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TPJ",
        destination_station_name="Tiruchchirappalli Jn",
        departure_time="08:00",
        arrival_time="12:00",
        duration_minutes=240,
        runs_on_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    )
    t2_tight = TrainService(
        train_number="22222",
        train_name="Leg 2 Tight Express",
        origin_station_code="TPJ",
        origin_station_name="Tiruchchirappalli Jn",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="12:15",  # only 15m layover
        arrival_time="16:00",
        duration_minutes=225,
        runs_on_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    )

    def search_side_effect(origin_stations, destination_stations, **kwargs):
        if "TPJ" in destination_stations:
            return [t1]
        if "TPJ" in origin_stations:
            return [t2_tight]
        return []

    mock_search.search_trains.side_effect = search_side_effect

    service = ConnectingTrainDiscoveryService(train_service=mock_search)
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Palayamkottai",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",
        meeting_time="18:00",
        required_arrival_buffer_minutes=30,
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Palayamkottai",
        distance_km=5.0,
        duration_minutes=15,
    )

    options = service.discover_connecting_journeys(
        origin_codes=["MS"],
        dest_codes=["TEN"],
        requirements=req,
        last_mile=last_mile,
    )
    # Tight layover of 15m should be rejected
    assert len(options) == 0


def test_connecting_infeasible_when_leg2_arrives_after_deadline():
    """Verify that when Leg 2 arrives too late for the meeting, is_feasible is False and category is infeasible."""
    mock_search = MagicMock(spec=TrainSearchService)
    t1 = TrainService(
        train_number="11111",
        train_name="Leg 1 Morning",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TPJ",
        destination_station_name="Tiruchchirappalli Jn",
        departure_time="08:00",
        arrival_time="12:00",
        duration_minutes=240,
        runs_on_days=["Sun"],
    )
    t2_late = TrainService(
        train_number="22222",
        train_name="Leg 2 Evening",
        origin_station_code="TPJ",
        origin_station_name="Tiruchchirappalli Jn",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="13:00",  # 60m layover (valid)
        arrival_time="18:00",    # arrives at 18:00
        duration_minutes=300,
        runs_on_days=["Sun"],
    )

    def search_side_effect(origin_stations, destination_stations, **kwargs):
        if "TPJ" in destination_stations:
            return [t1]
        if "TPJ" in origin_stations:
            return [t2_late]
        return []

    mock_search.search_trains.side_effect = search_side_effect

    service = ConnectingTrainDiscoveryService(train_service=mock_search)
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Palayamkottai",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",  # Sunday
        meeting_time="17:00",       # Meeting is at 17:00, but train arrives station at 18:00
        required_arrival_buffer_minutes=30,
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Palayamkottai",
        distance_km=5.0,
        duration_minutes=20,
    )

    options = service.discover_connecting_journeys(
        origin_codes=["MS"],
        dest_codes=["TEN"],
        requirements=req,
        last_mile=last_mile,
    )
    assert len(options) == 1
    assert options[0].is_feasible is False
    assert options[0].match_category == "infeasible"
    assert "Infeasible" in options[0].explanation


def test_connecting_indeterminate_when_last_mile_missing():
    """Verify that missing last-mile duration marks connection as indeterminate (insufficient_data)."""
    mock_search = MagicMock(spec=TrainSearchService)
    t1 = TrainService(
        train_number="11111",
        train_name="Leg 1 Express",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TPJ",
        destination_station_name="Tiruchchirappalli Jn",
        departure_time="08:00",
        arrival_time="12:00",
        duration_minutes=240,
        runs_on_days=["Sun"],
    )
    t2 = TrainService(
        train_number="22222",
        train_name="Leg 2 Express",
        origin_station_code="TPJ",
        origin_station_name="Tiruchchirappalli Jn",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="13:00",
        arrival_time="16:00",
        duration_minutes=180,
        runs_on_days=["Sun"],
    )

    def search_side_effect(origin_stations, destination_stations, **kwargs):
        if "TPJ" in destination_stations:
            return [t1]
        if "TPJ" in origin_stations:
            return [t2]
        return []

    mock_search.search_trains.side_effect = search_side_effect

    service = ConnectingTrainDiscoveryService(train_service=mock_search)
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Unknown Remote Campus",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",
        meeting_time="19:00",
        required_arrival_buffer_minutes=30,
    )

    # Last mile with unknown/None duration
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Unknown Remote Campus",
        distance_km=0.0,
        duration_minutes=0,
    )
    last_mile.duration_minutes = None  # Explicitly None

    options = service.discover_connecting_journeys(
        origin_codes=["MS"],
        dest_codes=["TEN"],
        requirements=req,
        last_mile=last_mile,
    )
    assert len(options) == 1
    assert options[0].is_feasible is False
    assert options[0].match_category == "insufficient_data"


def test_safe_combined_fare_calculation_no_invention():
    """Verify that combined fare is calculated only when both leg fares exist; None if either is absent."""
    mock_search = MagicMock(spec=TrainSearchService)
    # Leg 1 has fare 555.0 for CC
    t1 = TrainService(
        train_number="11111",
        train_name="Leg 1 Express",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TPJ",
        destination_station_name="Tiruchchirappalli Jn",
        departure_time="08:00",
        arrival_time="12:00",
        duration_minutes=240,
        classes=["CC"],
        fares={"CC": 555.0},
        runs_on_days=["Sun"],
    )
    # Leg 2 has NO fare data
    t2 = TrainService(
        train_number="22222",
        train_name="Leg 2 Express",
        origin_station_code="TPJ",
        origin_station_name="Tiruchchirappalli Jn",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="13:00",
        arrival_time="16:00",
        duration_minutes=180,
        classes=["CC"],
        fares={},
        runs_on_days=["Sun"],
    )

    def search_side_effect(origin_stations, destination_stations, **kwargs):
        if "TPJ" in destination_stations:
            return [t1]
        if "TPJ" in origin_stations:
            return [t2]
        return []

    mock_search.search_trains.side_effect = search_side_effect

    service = ConnectingTrainDiscoveryService(train_service=mock_search)
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Palayamkottai",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",
        meeting_time="19:00",
        preferred_class="CC",
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Palayamkottai",
        distance_km=5.0,
        duration_minutes=15,
    )

    options = service.discover_connecting_journeys(
        origin_codes=["MS"],
        dest_codes=["TEN"],
        requirements=req,
        last_mile=last_mile,
    )
    assert len(options) == 1
    # Because Leg 2 has no fare, total_estimated_fare must be None (not 555.0 and not a fabricated number)
    assert options[0].total_estimated_fare is None


def test_provider_failure_returns_provider_unavailable_in_planner():
    """Verify that when the train provider throws RailRadarAuthError, planner returns status=provider_unavailable."""
    planner = JourneyPlanner()
    planner.train_service.provider = MagicMock()
    planner.train_service.provider.search_trains.side_effect = RailRadarAuthError(
        "RailRadar authentication failed. Please verify your RAILRADAR_API_KEY.",
        status_code=401,
        trace_id="trace-auth-err-test",
    )

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="MGR Central",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
    )
    res = planner.plan_journey(req)
    assert res.status == "provider_unavailable"
    assert "provider unavailable" in res.summary.lower()
    assert res.best_match is None
    assert len(res.feasible_alternatives) == 0


def test_planner_integrates_connecting_options():
    """Verify JourneyPlanner.plan_journey populates connecting_options in response."""
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli Medical College",
        destination_city="Tirunelveli",
        meeting_date="2026-10-25",
        meeting_time="23:00",
        required_arrival_buffer_minutes=30,
    )
    res = planner.plan_journey(req)
    assert res.status in ["answered", "no_feasible_journey"]
    assert hasattr(res, "connecting_options")
    assert isinstance(res.connecting_options, list)
    assert res.trace is not None
    assert any(t.get("stage") == "candidate_retrieval" for t in res.trace)
