"""
Unit and integration tests for Quota Exhaustion and Search Outcome Semantics.
Verifies all 9 mandatory requirements under 100% offline test constraints:
1. Quota exhausted and no cached schedules
2. Quota exhausted but valid cached schedules exist
3. Cached schedules exist but are stale or for the wrong date
4. Successful live search returning no trains
5. Valid schedules exist but all fail the deadline
6. Partial schedule data with uncertain feasibility
7. Provider outage versus quota exhaustion
8. Quick-refine action while quota is exhausted
9. Reset timestamp rendering with the correct timezone
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.journey.models import (
    TripRequirements,
    TrainService,
    JourneyPlanResponse,
    QuotaInfo,
)
from backend.journey.planner import JourneyPlanner
from backend.journey.timetable import (
    TrainSearchService,
    RailRadarTrainDataProvider,
    MockTrainDataProvider,
)
from backend.journey.railradar_client import (
    RailRadarClient,
    RailRadarCache,
    RailRadarUnavailableError,
    RailRadarQuotaExhaustedError,
)
from backend.journey.quota import (
    DurableRailRadarQuotaManager,
    format_reset_time_with_timezone,
)
from backend.journey.ranking import JourneyRankingEngine


def exhaust_quota(quota_mgr: DurableRailRadarQuotaManager, used: int | None = None) -> None:
    """Durably exhaust quota in the SQLite database by ensuring the row exists first."""
    quota_mgr.get_usage_report()
    target_used = used if used is not None else quota_mgr.monthly_limit
    with quota_mgr._lock:
        conn = quota_mgr._get_connection()
        conn.execute("UPDATE quota_periods SET used_requests = ?", (target_used,))
        conn.commit()
        conn.close()


# =====================================================================
# 1. Quota exhausted and no cached schedules
# =====================================================================

def test_1_quota_exhausted_no_cached_schedules(tmp_path):
    """When quota is exhausted and no cached schedules exist, return quota_exhausted outcome."""
    db_file = tmp_path / "quota_exhausted.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=2)
    exhaust_quota(quota_mgr, 10)

    client = RailRadarClient(api_key="test-key", quota_manager=quota_mgr)
    client._session.request = MagicMock(side_effect=RuntimeError("Offline test: live requests forbidden"))
    provider = RailRadarTrainDataProvider(client=client)
    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )

    resp = planner.plan_journey(req)

    assert resp.status == "monthly_quota_exhausted"
    assert resp.search_outcome == "quota_exhausted"
    assert resp.best_match is None
    assert len(resp.feasible_alternatives) == 0
    assert resp.quota_info is not None
    assert resp.quota_info.is_exhausted is True
    assert resp.quota_info.usable_cached_results_exist is False
    assert "train data request budget exhausted" in resp.summary.lower()
    assert "feasibility could not be verified" in resp.tradeoff_explanation.lower()


# =====================================================================
# 2. Quota exhausted but valid cached schedules exist
# =====================================================================

def test_2_quota_exhausted_valid_cached_schedules_exist(tmp_path):
    """When quota is exhausted but valid cached schedules exist, evaluate feasibility from cache."""
    db_file = tmp_path / "quota_cached.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=2)
    exhaust_quota(quota_mgr, 10)

    client = RailRadarClient(api_key="test-key", quota_manager=quota_mgr)
    client._session.request = MagicMock(side_effect=RuntimeError("Offline test: live requests forbidden"))

    # Populate cache for SBC -> MAS on 2026-10-15
    train_data = {
        "trains": [
            {
                "number": "20608",
                "name": "MAS VANDE BHARAT",
                "runDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "from": {"code": "SBC", "name": "KSR Bengaluru", "departure": "05:45", "day": 1},
                "to": {"code": "MAS", "name": "MGR Chennai Central", "arrival": "10:10", "day": 1},
                "duration": "04:25",
                "classes": ["CC", "EC"],
            }
        ],
        "from": {"code": "SBC", "name": "KSR Bengaluru"},
        "to": {"code": "MAS", "name": "MGR Chennai Central"},
    }
    # Cache key: SBC:MAS:2026-10-15:all:False
    client.cache.set("trains", "SBC:MAS:2026-10-15:all:False", train_data)

    provider = RailRadarTrainDataProvider(client=client)
    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    # Meeting at 11:45 (train arrives 10:10, cab ~40m arrives 10:50, buffer = 55m >= 45m)
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="11:45",
        required_arrival_buffer_minutes=45,
        preferred_class="CC",
    )

    resp = planner.plan_journey(req)

    assert resp.search_outcome == "feasible_options_found"
    assert resp.best_match is not None
    assert resp.best_match.train_service.train_number == "20608"
    assert resp.best_match.is_feasible is True
    assert resp.quota_info is not None
    assert resp.quota_info.is_exhausted is True
    assert resp.quota_info.usable_cached_results_exist is True
    assert "cached schedule data" in resp.summary.lower()


# =====================================================================
# 3. Cached schedules exist but are stale or for the wrong date
# =====================================================================

def test_3_cached_schedules_stale_or_wrong_date(tmp_path):
    """Mismatched date or TTL-expired cache must not be used as current."""
    db_file = tmp_path / "quota_stale.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=2)
    exhaust_quota(quota_mgr, 10)

    client = RailRadarClient(api_key="test-key", quota_manager=quota_mgr)
    client._session.request = MagicMock(side_effect=RuntimeError("Offline test: live requests forbidden"))

    # Cache for a DIFFERENT date: 2026-10-10
    cached_payload = {
        "trains": [
            {
                "number": "20608",
                "name": "MAS VANDE BHARAT",
                "from": {"code": "SBC", "departure": "05:45"},
                "to": {"code": "MAS", "arrival": "10:10"},
                "classes": ["CC"],
            }
        ]
    }
    client.cache.set("trains", "SBC:MAS:2026-10-10:all:False", cached_payload)

    # Also put an expired entry for 2026-10-15 in the cache store manually
    client.cache._store["trains:SBC:MAS:2026-10-15:all:False"] = (
        time.time() - 100.0,  # Expired 100 seconds ago
        cached_payload,
        "2026-10-01T00:00:00Z",
    )

    provider = RailRadarTrainDataProvider(client=client)
    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="11:45",
    )

    resp = planner.plan_journey(req)

    # Must NOT use stale or wrong-date cache
    assert resp.status == "monthly_quota_exhausted"
    assert resp.search_outcome == "quota_exhausted"
    assert resp.best_match is None
    assert resp.quota_info.usable_cached_results_exist is False


# =====================================================================
# 4. Successful live search returning no trains
# =====================================================================

def test_4_successful_live_search_returning_no_trains():
    """Live search returning 0 trains must return search_data_unavailable, NOT no_feasible_options."""
    mock_client = MagicMock()
    # Provider successfully responds with empty trains list
    mock_client.search_trains.return_value = {
        "data": {
            "from": {"code": "SBC"},
            "to": {"code": "MAS"},
            "trains": [],
        },
        "trace_id": "trace-empty",
        "retrieved_at": "2026-10-10T12:00:00Z",
    }

    provider = RailRadarTrainDataProvider(client=mock_client)
    # Ensure provider.search_trains returns empty list
    provider.search_trains = MagicMock(return_value=[])

    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
    )

    resp = planner.plan_journey(req)

    # Crucial check: Must not claim infeasible journey when 0 trains were evaluated!
    assert resp.search_outcome == "search_data_unavailable"
    assert resp.status == "insufficient_data"
    assert resp.best_match is None
    assert "no scheduled train services found" in resp.summary.lower()


# =====================================================================
# 5. Valid schedules exist but all fail the deadline
# =====================================================================

def test_5_valid_schedules_exist_all_fail_deadline():
    """When train schedules exist and are evaluated, but all miss the deadline, return no_feasible_options."""
    planner = JourneyPlanner()
    # Uses MockTrainDataProvider with real known trains between Bengaluru and Chennai
    # Set an impossible morning deadline: 06:00 AM
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="06:00",  # 06:00 AM meeting: earliest morning arrival MAS Vande Bharat arrives at 10:10 AM
        required_arrival_buffer_minutes=45,
    )

    resp = planner.plan_journey(req)

    assert resp.search_outcome == "no_feasible_options"
    assert resp.status == "no_feasible_journey"
    assert resp.best_match is None
    assert len(resp.infeasible_options) > 0
    assert any("misses" in inf.hard_constraint_violations[0].lower() or "deadline" in inf.hard_constraint_violations[0].lower() for inf in resp.infeasible_options)


# =====================================================================
# 6. Partial schedule data with uncertain feasibility
# =====================================================================

def test_6_partial_schedule_data_uncertain_feasibility():
    """When last-mile transit duration is unknown (None), feasibility is uncertain, yielding partial_results."""
    engine = JourneyRankingEngine()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Unmapped Village, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="11:45",
    )

    train = TrainService(
        train_number="20608",
        train_name="MAS VANDE BHARAT",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="05:45",
        arrival_time="10:10",
        duration_minutes=265,
    )

    from backend.journey.feasibility import JourneyFeasibilityEvaluator
    evaluator = JourneyFeasibilityEvaluator()

    # Last-mile with unknown duration (duration_minutes is None)
    from backend.journey.models import LastMileEstimate
    unknown_last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Unmapped Village",
        distance_km=15.0,
        duration_minutes=None,  # Unknown!
        is_heuristic=True,
    )

    ev = evaluator.evaluate_candidate(train=train, requirements=req, last_mile=unknown_last_mile)
    assert ev.match_category == "insufficient_data"
    assert ev.is_feasible is False

    response = engine.rank_and_assemble_plan(
        requirements=req,
        evaluations=[ev],
        resolved_origin=None,
        resolved_destination=None,
        candidate_origin_stations=[],
        candidate_destination_stations=[],
        trace_id="test-partial-trace",
    )

    assert response.search_outcome == "partial_results"
    assert response.status == "insufficient_data"
    assert response.best_match is None


# =====================================================================
# 7. Provider outage versus quota exhaustion
# =====================================================================

def test_7_provider_outage_vs_quota_exhaustion(tmp_path):
    """Server outage (503) and quota exhaustion (429) must produce distinctly different outcomes."""
    # Scenario A: Provider Outage
    planner_outage = JourneyPlanner()
    mock_prov_outage = MagicMock()
    mock_prov_outage.search_trains.side_effect = RailRadarUnavailableError(
        "RailRadar upstream 503 service unavailable", status_code=503
    )
    planner_outage.train_service = TrainSearchService(provider=mock_prov_outage)

    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="10:00",
    )

    resp_outage = planner_outage.plan_journey(req)
    assert resp_outage.status == "provider_unavailable"
    assert resp_outage.search_outcome == "search_data_unavailable"
    assert "provider unavailable" in resp_outage.summary.lower()

    # Scenario B: Quota Exhaustion
    db_file = tmp_path / "quota_diff.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=5, reserve_quota=1)
    exhaust_quota(quota_mgr, 5)

    client = RailRadarClient(api_key="test-key", quota_manager=quota_mgr)
    client._session.request = MagicMock(side_effect=RuntimeError("Offline test: live requests forbidden"))
    prov_quota = RailRadarTrainDataProvider(client=client)
    planner_quota = JourneyPlanner()
    planner_quota.train_service = TrainSearchService(provider=prov_quota)

    resp_quota = planner_quota.plan_journey(req)
    assert resp_quota.status == "monthly_quota_exhausted"
    assert resp_quota.search_outcome == "quota_exhausted"
    assert "budget exhausted" in resp_quota.summary.lower()


# =====================================================================
# 8. Quick-refine action while quota is exhausted
# =====================================================================

def test_8_quick_refine_action_while_quota_exhausted(tmp_path):
    """Quick-refine re-evaluates cached schedules without outbound requests when quota is exhausted."""
    db_file = tmp_path / "quota_refine.sqlite"
    quota_mgr = DurableRailRadarQuotaManager(db_path=db_file, monthly_limit=10, reserve_quota=2)
    exhaust_quota(quota_mgr, 10)

    client = RailRadarClient(api_key="test-key", quota_manager=quota_mgr)
    client._session.request = MagicMock(side_effect=RuntimeError("Offline test: live requests forbidden"))

    # Cache SBC -> MAS schedule
    train_data = {
        "trains": [
            {
                "number": "20608",
                "name": "MAS VANDE BHARAT",
                "runDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "from": {"code": "SBC", "name": "KSR Bengaluru", "departure": "05:45", "day": 1},
                "to": {"code": "MAS", "name": "MGR Chennai Central", "arrival": "10:10", "day": 1},
                "duration": "04:25",
                "classes": ["CC", "EC"],
            }
        ]
    }
    client.cache.set("trains", "SBC:MAS:2026-10-15:all:False", train_data)

    provider = RailRadarTrainDataProvider(client=client)
    planner = JourneyPlanner()
    planner.train_service = TrainSearchService(provider=provider)

    # Initial plan with 11:30 AM meeting (fails with 45m buffer because 10:10 + 46m = 10:56 > 10:45)
    req1 = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="11:30",
        required_arrival_buffer_minutes=45,
    )
    plan1 = planner.plan_journey(req1)
    assert plan1.best_match is None  # Infeasible with 45m buffer

    # Quick refine: Relax buffer to 10m (11:30 - 10m = 11:20 >= 10:56 -> feasible)
    req2 = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="11:30",
        required_arrival_buffer_minutes=10,
    )
    plan2 = planner.plan_journey(req2)

    # Evaluated from cache: now feasible!
    assert plan2.best_match is not None
    assert plan2.best_match.train_service.train_number == "20608"
    assert plan2.search_outcome == "feasible_options_found"
    assert plan2.quota_info.is_exhausted is True


# =====================================================================
# 9. Reset timestamp rendering with the correct timezone
# =====================================================================

def test_9_reset_timestamp_rendering_with_correct_timezone():
    """Reset timestamp must be formatted with explicit timezone (Asia/Kolkata IST and UTC offset)."""
    # Test standard ISO UTC string
    utc_iso = "2026-11-01T00:00:00+00:00"
    formatted_ist = format_reset_time_with_timezone(utc_iso, tz_name="Asia/Kolkata")

    # In IST (UTC+05:30), 00:00 UTC corresponds to 05:30 AM
    assert "01 Nov 2026" in formatted_ist
    assert "05:30 AM" in formatted_ist
    assert "IST" in formatted_ist
    assert "(+05:30)" in formatted_ist

    # Test UTC timezone formatting
    formatted_utc = format_reset_time_with_timezone(utc_iso, tz_name="UTC")
    assert "UTC" in formatted_utc
    assert "(+00:00)" in formatted_utc

    # Test None / empty string fallback
    assert "unverified" in format_reset_time_with_timezone(None).lower()
    assert "unverified" in format_reset_time_with_timezone("").lower()
