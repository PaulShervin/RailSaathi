"""
RailSathi AI — RailRadar Provider & Journey Engine Integration Tests

Tests RailRadarTrainDataProvider normalization, TrainSearchService candidate filtering,
bounded fare enrichment, and integration with the deterministic journey planner.
"""

import pytest
from unittest.mock import MagicMock

from backend.journey.models import (
    TripRequirements,
    TrainService,
    JourneyEvaluation,
    FareQuote,
    FareBreakdown,
)
from backend.journey.timetable import (
    RailRadarTrainDataProvider,
    TrainSearchService,
    MockTrainDataProvider,
)
from backend.journey.planner import JourneyPlanner
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.journey.location import LocationResolutionService


# =====================================================================
# 1. RailRadarTrainDataProvider Normalization Tests
# =====================================================================

def test_provider_normalizes_train_response():
    """Verify RailRadar response maps accurately to TrainService models."""
    mock_client = MagicMock()
    mock_client.search_trains.return_value = {
        "data": {
            "from": {"code": "SBC", "name": "KSR Bengaluru"},
            "to": {"code": "MAS", "name": "MGR Chennai Central"},
            "count": 2,
            "trains": [
                {
                    "number": "20608",
                    "name": "MAS VANDE BHARAT",
                    "type": "VB",
                    "runDays": ["Mon", "Tue", "Thu", "Fri", "Sat", "Sun"],
                    "from": {"departure": "05:45", "day": 1},
                    "to": {"arrival": "10:10", "day": 1},
                    "duration": "04:25",
                    "classes": ["CC", "EC"],
                },
                {
                    "number": "12658",
                    "name": "CHENNAI MAIL",
                    "type": "SF",
                    "runDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    "from": {"departure": "22:40", "day": 1},
                    "to": {"arrival": "04:35", "day": 2},
                    "duration": "05:55",
                    "classes": ["1A", "2A", "3A", "SL"],
                },
            ],
        },
        "trace_id": "trace-norm-1",
        "retrieved_at": "2026-10-10T12:00:00Z",
    }

    provider = RailRadarTrainDataProvider(client=mock_client)
    trains = provider.search_trains("SBC", "MAS", journey_date="2026-10-25")

    assert len(trains) == 2
    
    # Train 1: Vande Bharat
    t1 = trains[0]
    assert t1.train_number == "20608"
    assert t1.train_name == "MAS VANDE BHARAT"
    assert t1.origin_station_code == "SBC"
    assert t1.destination_station_code == "MAS"
    assert t1.departure_time == "05:45"
    assert t1.arrival_time == "10:10"
    assert t1.day_offset == 0
    assert t1.duration_minutes == 265
    assert "CC" in t1.classes
    assert t1.data_source == "RailRadar API (api.railradar.in)"

    # Train 2: Overnight Chennai Mail (+1 day arrival)
    t2 = trains[1]
    assert t2.train_number == "12658"
    assert t2.departure_time == "22:40"
    assert t2.arrival_time == "04:35"
    assert t2.day_offset == 1
    assert t2.duration_minutes == 355


def test_provider_normalizes_fare_quote():
    """Verify RailRadar fare response maps into FareQuote and FareBreakdown."""
    mock_client = MagicMock()
    mock_client.get_fare.return_value = {
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
                "cateringCharge": 120.0,
                "goodsServiceTax": 40.0,
            },
        },
        "trace_id": "trace-fare-norm",
        "retrieved_at": "2026-10-10T12:00:00Z",
    }

    provider = RailRadarTrainDataProvider(client=mock_client)
    quote = provider.get_fare("20608", "SBC", "MAS", "2026-10-25", "CC", "GN")

    assert quote is not None
    assert quote.train_number == "20608"
    assert quote.total_fare == 995.0
    assert quote.breakdown.base_fare == 750.0
    assert quote.breakdown.catering_charge == 120.0
    assert quote.class_code == "CC"
    assert quote.data_source == "RailRadar API (api.railradar.in)"


# =====================================================================
# 2. TrainSearchService Bounded Fare Enrichment Tests
# =====================================================================

def test_train_search_service_bounded_fare_enrichment():
    """Verify that fare lookups are bounded to top candidates and do not exceed request cap."""
    mock_provider = MagicMock()
    mock_provider.get_fare.side_effect = lambda train_number, source_station_code, destination_station_code, journey_date, class_code, quota_code="GN": FareQuote(
        train_number=train_number,
        source_station=source_station_code,
        destination_station=destination_station_code,
        journey_date=journey_date,
        class_code=class_code,
        quota_code=quota_code,
        total_fare=850.0 if class_code == "3A" else 560.0,
        data_source="RailRadar API",
    )

    service = TrainSearchService(provider=mock_provider)


    # Create 8 dummy evaluations
    evaluations = []
    for i in range(8):
        t = TrainService(
            train_number=f"1000{i}",
            train_name=f"Express {i}",
            origin_station_code="SBC",
            origin_station_name="Bengaluru",
            destination_station_code="MAS",
            destination_station_name="Chennai",
            departure_time="06:00",
            arrival_time="11:00",
            duration_minutes=300,
            classes=["3A", "SL"],
        )
        ev = JourneyEvaluation(
            candidate_id=f"cand-{i}",
            train_service=t,
            journey_date="2026-10-25",
            departure_datetime_iso="2026-10-25T06:00:00",
            arrival_datetime_iso="2026-10-25T11:00:00",
            meeting_datetime_iso="2026-10-25T13:00:00",
            last_mile_origin_station="MAS",
            last_mile_destination_venue="Tidel Park",
            last_mile_duration_minutes=40,
            last_mile_distance_km=14.0,
            last_mile_mode="cab",
            latest_acceptable_station_arrival_iso="2026-10-25T11:35:00",
            actual_arrival_buffer_minutes=80,
            is_feasible=True,
            score=80.0 + i,
            rank=i + 1,
            match_category="feasible_alternative",
            explanation="Feasible option",
        )
        evaluations.append(ev)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="13:00",
        preferred_class="3A",
    )

    # Enrich with max 3 lookups
    service.enrich_candidate_fares(evaluations, req, max_lookups=3)

    # Ensure provider.get_fare was called exactly 3 times (not 8)
    assert mock_provider.get_fare.call_count == 3
    # Verify top candidate received enriched fare
    assert evaluations[-1].recommended_fare == 850.0  # highest score candidate


# =====================================================================
# 3. End-to-End Planning Integration with RailRadar Provider
# =====================================================================

def test_journey_planner_with_railradar_provider():
    """Verify JourneyPlanner end-to-end execution with RailRadar provider data."""
    mock_client = MagicMock()
    mock_client.search_trains.return_value = {
        "data": {
            "from": {"code": "SBC", "name": "KSR Bengaluru"},
            "to": {"code": "MAS", "name": "MGR Chennai Central"},
            "count": 2,
            "trains": [
                {
                    "number": "20608",
                    "name": "MAS VANDE BHARAT",
                    "runDays": ["Mon", "Tue", "Thu", "Fri", "Sat", "Sun"],
                    "from": {"departure": "05:45", "day": 1},
                    "to": {"arrival": "10:10", "day": 1},
                    "duration": "04:25",
                    "classes": ["CC", "EC"],
                },
                {
                    "number": "12640",
                    "name": "BRINDAVAN EXP",
                    "runDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    "from": {"departure": "15:10", "day": 1},
                    "to": {"arrival": "21:10", "day": 1},
                    "duration": "06:00",
                    "classes": ["CC", "2S"],
                },
            ],
        },
        "trace_id": "trace-plan-test",
        "retrieved_at": "2026-10-10T12:00:00Z",
    }
    mock_client.get_fare.return_value = {
        "data": {
            "trainNumber": "20608",
            "totalFare": 995.0,
            "classCode": "CC",
            "quotaCode": "GN",
        },
        "trace_id": "trace-fare-test",
        "retrieved_at": "2026-10-10T12:00:00Z",
    }

    provider = RailRadarTrainDataProvider(client=mock_client)
    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="11:45",  # Meeting at 11:45 AM
        required_arrival_buffer_minutes=45,  # Needs 45m buffer + ~40m cab = arrives before 10:20
        preferred_class="CC",
    )

    plan = planner.plan_journey(req)

    assert plan.status == "answered"
    assert plan.best_match is not None
    assert plan.best_match.train_service.train_number == "20608"
    assert plan.best_match.train_service.data_source == "RailRadar API (api.railradar.in)"
    assert plan.best_match.recommended_fare == 995.0
    # Brindavan express arriving at 21:10 misses 11:45 meeting and must be classified infeasible
    assert any(inf.train_service.train_number == "12640" for inf in plan.infeasible_options)
