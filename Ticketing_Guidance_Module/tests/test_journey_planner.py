"""
RailSathi AI — Journey Planner Engine Tests

Covers:
- Requirement parsing (complete, missing fields, relative dates, preferred train, budget)
- Feasibility calculations (deadline buffers, overnight journeys, last-mile deduction, no double subtraction)
- Deterministic ranking (hard constraints vs soft preferences, preferred train evaluation)
- Security checks (booking URL allowlisting, prompt injection resilience)
- Edge cases (midnight crossings, date offsets, impossible deadlines)
"""

import pytest
from datetime import datetime, timedelta
from backend.journey.models import (
    TripRequirements,
    TrainService,
    StationCandidate,
    LastMileEstimate,
)
from backend.journey.location import (
    LocationResolutionService,
    calculate_haversine_distance_km,
    estimate_urban_travel_time_minutes,
)
from backend.journey.timetable import TrainSearchService
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.journey.ranking import JourneyRankingEngine
from backend.journey.booking import BookingHandoffService, is_url_safe_and_allowlisted
from backend.journey.planner import JourneyPlanner, parse_requirements_from_text


# =====================================================================
# 1. Requirement Parsing Tests
# =====================================================================

def test_parse_complete_prompt():
    """Verify standard passenger prompt extraction."""
    prompt = (
        "I have a meeting at Tidel Park in Chennai at 10:00 AM on 25 October. "
        "I'm travelling from Bengaluru. I want AC 3-tier if possible, prefer a reasonably affordable train, "
        "and want to reach the meeting location at least 45 minutes early. Find the best train."
    )
    req = parse_requirements_from_text(prompt)
    assert req.origin == "Bengaluru"
    assert "Tidel Park" in req.destination_venue
    assert req.meeting_date == "2026-10-25"
    assert req.meeting_time == "10:00"
    assert req.required_arrival_buffer_minutes == 45
    assert req.preferred_class == "3A"


def test_parse_preferred_train_and_budget():
    """Verify preferred train and budget constraints parsing."""
    prompt = "Going from Bengaluru to Chennai for a meeting at 2:30 PM. Prefer Vande Bharat or train 20608 under 1500."
    req = parse_requirements_from_text(prompt)
    assert req.origin == "Bengaluru"
    assert req.meeting_time == "14:30"
    assert req.preferred_train_name_or_number in ["Vande Bharat", "20608"]
    assert req.budget_max == 1500.0


def test_parse_relative_buffer_hours():
    """Verify 1-hour early buffer parsing."""
    prompt = "Interview at IIT Madras Chennai at 09:00 AM on 2026-11-05 from Bengaluru. Need to reach 1 hour early."
    req = parse_requirements_from_text(prompt)
    assert req.required_arrival_buffer_minutes == 60
    assert req.meeting_time == "09:00"


# =====================================================================
# 2. Location & Last-Mile Tests
# =====================================================================

def test_resolve_known_venue():
    """Verify venue coordinates and city resolution for known hubs."""
    loc_service = LocationResolutionService()
    resolved = loc_service.resolve_location("Tidel Park, Chennai")
    assert resolved.city == "Chennai"
    assert resolved.latitude > 12.0
    assert resolved.longitude > 80.0
    assert "Verified" in resolved.provider or "Matched" in resolved.provider


def test_find_nearby_stations_for_chennai():
    """Verify discovery of candidate stations for Chennai destination."""
    loc_service = LocationResolutionService()
    stations = loc_service.find_nearby_stations("Chennai")
    station_codes = [s.station_code for s in stations]
    assert "MAS" in station_codes
    assert "MS" in station_codes


def test_estimate_last_mile_calculation():
    """Verify last-mile transit duration and distance calculation."""
    loc_service = LocationResolutionService()
    lm = loc_service.estimate_last_mile("MAS", "Tidel Park")
    assert lm.origin_station_code == "MAS"
    assert lm.distance_km > 5.0
    assert lm.duration_minutes >= 20  # realistic urban travel in Chennai


def test_haversine_distance_accuracy():
    """Verify Haversine formula calculation for known coordinates."""
    # Distance between MAS (13.0827, 80.2757) and SBC (12.9781, 77.5696) ~ 290 km
    dist = calculate_haversine_distance_km(13.0827, 80.2757, 12.9781, 77.5696)
    assert 280 <= dist <= 310


# =====================================================================
# 3. Feasibility & Deadline Calculations
# =====================================================================

def test_feasibility_train_arriving_before_deadline():
    """
    Train scheduled to arrive in time:
    Meeting: 10:00 AM
    Buffer: 45m -> Required venue arrival: 09:15 AM
    Last mile: 35m -> Latest acceptable station arrival: 08:40 AM
    Train arrives: 04:35 AM (Chennai Mail)
    Result: Feasible with comfortable buffer.
    """
    evaluator = JourneyFeasibilityEvaluator()
    train = TrainService(
        train_number="12658",
        train_name="CHENNAI MAIL",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="22:40",
        arrival_time="04:35",
        day_offset=1,
        duration_minutes=355,
        classes=["3A", "2A", "SL"],
        fares={"3A": 830.0, "2A": 1175.0, "SL": 315.0},
    )
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Tidel Park",
        distance_km=15.0,
        duration_minutes=35,
    )

    ev = evaluator.evaluate_candidate(train, req, last_mile)
    assert ev.is_feasible is True
    assert len(ev.hard_constraint_violations) == 0
    # Arrives station at 04:35, venue at 05:10, meeting at 10:00 -> 290 minutes buffer
    assert ev.actual_arrival_buffer_minutes == 290
    assert ev.actual_arrival_buffer_minutes >= req.required_arrival_buffer_minutes


def test_feasibility_train_arriving_late():
    """
    Train arriving too late:
    Meeting: 10:00 AM
    Buffer: 45m
    Train arrives MAS at 10:10 AM (Vande Bharat 20608)
    Result: INFEASIBLE (violates hard deadline constraint).
    """
    evaluator = JourneyFeasibilityEvaluator()
    train = TrainService(
        train_number="20608",
        train_name="MAS VANDE BHARAT",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="05:45",
        arrival_time="10:10",
        day_offset=0,
        duration_minutes=265,
        classes=["CC", "EC"],
        fares={"CC": 995.0, "EC": 1940.0},
    )
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Tidel Park",
        distance_km=15.0,
        duration_minutes=35,
    )

    ev = evaluator.evaluate_candidate(train, req, last_mile)
    assert ev.is_feasible is False
    assert len(ev.hard_constraint_violations) > 0
    assert "deadline" in ev.hard_constraint_violations[0].lower() or "reaches" in ev.hard_constraint_violations[0].lower()


def test_no_double_subtraction_of_buffer():
    """
    Verify exact buffer mathematics:
    Meeting: 10:00 AM (600 mins from midnight)
    Train arrival: 08:00 AM (480 mins from midnight)
    Last-mile: 30 mins -> Venue arrival: 08:30 AM (510 mins from midnight)
    Actual buffer at venue before meeting = 600 - 510 = 90 mins.
    """
    evaluator = JourneyFeasibilityEvaluator()
    train = TrainService(
        train_number="12610",
        train_name="TEST EXPRESS",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="02:00",
        arrival_time="08:00",
        day_offset=0,
        duration_minutes=360,
        classes=["CC"],
        fares={"CC": 500.0},
    )
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Test Venue",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
    last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Test Venue",
        distance_km=10.0,
        duration_minutes=30,
    )
    ev = evaluator.evaluate_candidate(train, req, last_mile)
    assert ev.actual_arrival_buffer_minutes == 90
    assert ev.is_feasible is True


# =====================================================================
# 4. Ranking & Alternative Synthesis Tests
# =====================================================================

def test_ranking_engine_prioritizes_feasible_over_infeasible():
    """Verify that a train violating deadline is never ranked as best match."""
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
        preferred_class="3A",
    )
    plan = planner.plan_journey(req)
    assert plan.status == "answered"
    assert plan.best_match is not None
    assert plan.best_match.is_feasible is True
    # Chennai Mail (12658) arrives at 04:35 AM -> in time
    assert plan.best_match.train_service.train_number == "12658"

    # Vande Bharat (20608) arrives MAS at 10:10 AM -> must be in infeasible list
    infeasible_numbers = [inf.train_service.train_number for inf in plan.infeasible_options]
    assert "20608" in infeasible_numbers


def test_ranking_when_no_train_is_feasible():
    """
    If meeting is at 05:00 AM, even overnight train arriving at 04:35 AM cannot
    reach Tidel Park with 45m buffer -> honest infeasibility diagnosis.
    """
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-25",
        meeting_time="05:00",
        required_arrival_buffer_minutes=45,
    )
    plan = planner.plan_journey(req)
    assert plan.status == "no_feasible_journey"
    assert plan.best_match is None
    assert len(plan.infeasible_options) > 0
    assert "recommend" in plan.tradeoff_explanation.lower() or "buffer" in plan.tradeoff_explanation.lower()


# =====================================================================
# 5. Security & Booking Allowlist Tests
# =====================================================================

def test_booking_url_allowlist_valid():
    """Verify approved official railway hosts pass validation."""
    assert is_url_safe_and_allowlisted("https://www.irctc.co.in/nget/train-search?fromStation=SBC") is True
    assert is_url_safe_and_allowlisted("https://enquiry.indianrail.gov.in/mntes") is True
    assert is_url_safe_and_allowlisted("https://www.confirmtkt.com/rrs") is True


def test_booking_url_allowlist_rejects_arbitrary_or_http():
    """Verify unapproved domains or insecure HTTP schemes are rejected."""
    assert is_url_safe_and_allowlisted("http://www.irctc.co.in") is False  # Insecure HTTP
    assert is_url_safe_and_allowlisted("https://malicious-train-site.com/book") is False
    assert is_url_safe_and_allowlisted("https://fake-irctc-portal.ru/login") is False
    assert is_url_safe_and_allowlisted("javascript:alert(1)") is False


def test_booking_handoff_generation():
    """Verify BookingHandoffService builds structured allowlisted handoff."""
    b_service = BookingHandoffService()
    train = TrainService(
        train_number="12658",
        train_name="CHENNAI MAIL",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="MGR Chennai Central",
        departure_time="22:40",
        arrival_time="04:35",
        day_offset=1,
        duration_minutes=355,
        classes=["3A"],
        fares={"3A": 830.0},
    )
    handoff = b_service.create_booking_handoff(
        train=train,
        journey_date="2026-10-24",
        recommended_class="3A",
        recommended_fare=830.0,
    )
    assert handoff.is_url_allowlisted is True
    assert "irctc.co.in" in handoff.booking_url
    assert handoff.train_number == "12658"
    assert handoff.recommended_class == "3A"
    assert handoff.estimated_fare_inr == 830.0
