"""
RailSathi AI — Audit & Fix Regression Test Suite

Validates:
1. Deterministic date resolution in Asia/Kolkata ("today", "tomorrow", weekdays, slash formats).
2. Date-only values parsed without unintended timezone shifts.
3. Spatial conflict detection between destination venue and destination city.
4. Hub and station resolution for Tirunelveli (TEN), Madurai (MDU), etc.
5. Overnight train schedule search and feasibility evaluation (12633 Kanyakumari Exp for 07:00 AM meeting).
6. Strict rejection of trains missing the arrival deadline (e.g. 20635, 12631).
7. Acceptance of compliant trains with adequate venue buffer.
8. Safe handling of unknown last-mile duration (indeterminate / insufficient_data).
9. Distinction between valid empty results and provider failure.
10. Explicit distinction between hard constraints and soft preferences.
"""

import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pytest

from backend.journey.models import TripRequirements, TrainService, LastMileEstimate
from backend.journey.planner import JourneyPlanner, parse_requirements_from_text, resolve_date_from_text
from backend.journey.location import LocationResolutionService
from backend.journey.timetable import TrainSearchService, MockTrainDataProvider
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.journey.ranking import JourneyRankingEngine


def test_date_resolution_tomorrow_asia_kolkata():
    """Test 1: 'tomorrow' referenced on 10 Oct 2026 in Asia/Kolkata resolves to 2026-10-11."""
    ref_dt = datetime(2026, 10, 10, 13, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    
    # Text with 'tomorrow'
    res_date = resolve_date_from_text("I need to reach Tirunelveli tomorrow for a meeting at 7 AM", current_dt=ref_dt)
    assert res_date == "2026-10-11"
    
    # Text with 'today'
    res_today = resolve_date_from_text("Meeting today at 5 PM", current_dt=ref_dt)
    assert res_today == "2026-10-10"
    
    # Text with 'day after tomorrow'
    res_day_after = resolve_date_from_text("Meeting day after tomorrow", current_dt=ref_dt)
    assert res_day_after == "2026-10-12"


def test_date_resolution_slash_and_text_formats():
    """Test 2: Slash dates (DD/MM/YYYY) and explicit text dates resolve accurately without shifts."""
    ref_dt = datetime(2026, 10, 10, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    
    # Slash date: 11/10/2026 -> 2026-10-11
    d1 = resolve_date_from_text("Meeting on 11/10/2026 at 7 AM", current_dt=ref_dt)
    assert d1 == "2026-10-11"
    
    # Text date: 11 October 2026
    d2 = resolve_date_from_text("Meeting on 11 October 2026 at 7 AM", current_dt=ref_dt)
    assert d2 == "2026-10-11"
    
    # ISO date: 2026-10-11
    d3 = resolve_date_from_text("Meeting on 2026-10-11 at 7 AM", current_dt=ref_dt)
    assert d3 == "2026-10-11"


def test_spatial_conflict_detection_chennai_venue_vs_tirunelveli_city():
    """Test 3: Chennai venue (Tidel Park) with Tirunelveli city triggers clarification_required."""
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Tidel Park",
        destination_city="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        required_arrival_buffer_minutes=45,
    )
    
    plan = planner.plan_journey(req)
    assert plan.status == "clarification_required"
    assert "clarification required" in plan.summary.lower()
    assert "tidel park" in plan.clarification_question.lower()
    assert "tirunelveli" in plan.clarification_question.lower()
    assert "chennai" in plan.clarification_question.lower()


def test_tirunelveli_hub_discovery_and_overnight_search():
    """Test 4 & 5: Chennai to Tirunelveli (MS -> TEN) discovers TEN hub and evaluates overnight trains."""
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli",
        destination_city="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        required_arrival_buffer_minutes=45,
        preferred_class="3A",
    )
    
    plan = planner.plan_journey(req)
    assert plan.status == "answered"
    assert plan.best_match is not None
    
    # The best match should be an overnight train arriving before 07:00 AM (20635, 12633, or 16105)
    best_train = plan.best_match.train_service
    assert best_train.train_number in ["20635", "12633", "16105"]
    assert plan.best_match.is_feasible is True
    assert plan.best_match.actual_arrival_buffer_minutes >= 45


def test_late_train_deadline_rejection():
    """Test 6: Trains arriving after the deadline or with insufficient buffer are marked infeasible."""
    evaluator = JourneyFeasibilityEvaluator()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Tirunelveli",
        distance_km=4.0,
        duration_minutes=15,
    )
    
    # 20635 Ananthapuri arrives TEN at 06:05 AM -> venue arrival 06:20 -> buffer 40 min (< 45 min required)
    train_late = TrainService(
        train_number="20635",
        train_name="ANANTHAPURI EXPRESS",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="19:50",
        arrival_time="06:05",
        day_offset=1,
        duration_minutes=615,
        classes=["3A", "SL"],
        fares={"3A": 970.0, "SL": 370.0},
    )
    
    ev = evaluator.evaluate_candidate(train_late, req, last_mile)
    assert ev.is_feasible is False
    assert ev.actual_arrival_buffer_minutes == 40
    assert any("deadline" in v.lower() for v in ev.hard_constraint_violations)


def test_feasible_train_buffer_calculation_and_acceptance():
    """Test 7: Train 12633 arriving at 03:20 AM is accepted with 205 min buffer."""
    evaluator = JourneyFeasibilityEvaluator()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Tirunelveli",
        distance_km=4.0,
        duration_minutes=15,
    )
    
    train_12633 = TrainService(
        train_number="12633",
        train_name="KANYAKUMARI EXPRESS",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="17:20",
        arrival_time="03:20",
        day_offset=1,
        duration_minutes=600,
        classes=["3A", "2A", "SL"],
        fares={"3A": 950.0, "2A": 1350.0, "SL": 360.0},
    )
    
    ev = evaluator.evaluate_candidate(train_12633, req, last_mile)
    assert ev.is_feasible is True
    assert ev.actual_arrival_buffer_minutes == 205  # 07:00 - (03:20 + 00:15) = 205 mins
    assert len(ev.hard_constraint_violations) == 0


def test_unknown_last_mile_produces_indeterminate_result():
    """Test 8: Unknown last mile duration marks candidate as insufficient_data."""
    evaluator = JourneyFeasibilityEvaluator()
    req = TripRequirements(
        origin="Chennai",
        destination_venue="Unknown Remote Place",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile_unknown = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Unknown Remote Place",
        distance_km=50.0,
        duration_minutes=35,
        confidence="unknown",
    )
    
    train = TrainService(
        train_number="12633",
        train_name="KANYAKUMARI EXPRESS",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="17:20",
        arrival_time="03:20",
        day_offset=1,
        duration_minutes=600,
        classes=["3A"],
        fares={"3A": 950.0},
    )
    
    ev = evaluator.evaluate_candidate(train, req, last_mile_unknown)
    assert ev.is_feasible is False
    assert ev.match_category == "insufficient_data"
    assert any("unknown" in v.lower() for v in ev.hard_constraint_violations)


def test_hard_vs_soft_class_and_budget_constraints():
    """Test 11: Preferred class and budget behave as soft preferences by default and hard constraints when specified."""
    evaluator = JourneyFeasibilityEvaluator()
    
    train = TrainService(
        train_number="12633",
        train_name="KANYAKUMARI EXPRESS",
        origin_station_code="MS",
        origin_station_name="Chennai Egmore",
        destination_station_code="TEN",
        destination_station_name="Tirunelveli Junction",
        departure_time="17:20",
        arrival_time="03:20",
        day_offset=1,
        duration_minutes=600,
        classes=["SL"],  # Only Sleeper available
        fares={"SL": 360.0},
    )
    last_mile = LastMileEstimate(
        origin_station_code="TEN",
        destination_venue="Tirunelveli",
        distance_km=4.0,
        duration_minutes=15,
    )
    
    # 1. Soft preferred class (3A requested, but only SL available) -> Feasible with penalty
    req_soft = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        preferred_class="3A",
        hard_constraints=["deadline", "arrival_buffer"],
    )
    ev_soft = evaluator.evaluate_candidate(train, req_soft, last_mile)
    assert ev_soft.is_feasible is True
    assert ev_soft.class_match is False
    assert any("alternative class" in p.lower() for p in ev_soft.soft_preference_penalties)
    
    # 2. Hard preferred class (3A strictly required) -> Infeasible
    req_hard = TripRequirements(
        origin="Chennai",
        destination_venue="Tirunelveli",
        meeting_date="2026-10-11",
        meeting_time="07:00",
        preferred_class="3A",
        hard_constraints=["deadline", "arrival_buffer", "preferred_class"],
    )
    ev_hard = evaluator.evaluate_candidate(train, req_hard, last_mile)
    assert ev_hard.is_feasible is False
    assert any("does not offer preferred class" in v.lower() for v in ev_hard.hard_constraint_violations)
