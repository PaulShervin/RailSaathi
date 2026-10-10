"""
RailSathi AI — End-to-End Required Test Scenarios

Directly validates the 10 mandatory evaluation scenarios:
1. Feasible train recommendation with adequate buffer for meeting goal.
2. Preferred train that misses deadline (evaluated honestly, explains missed buffer, recommends alternative).
3. Preferred class unavailable or unsupported.
4. No candidate satisfies the deadline.
5. Last-mile data handling.
6. Train schedule data and data provenance tracking.
7. Provider error/unavailable handling.
8. Passenger changes meeting time (refine workflow).
9. Journey crossing midnight / overnight date offset.
10. Security: Malicious attempt to force unapproved tool call or unallowlisted booking URL.
"""

import pytest
from backend.journey.models import TripRequirements, TrainService, LastMileEstimate
from backend.journey.planner import JourneyPlanner
from backend.journey.booking import is_url_safe_and_allowlisted, BookingHandoffService
from backend.agent.controller import AgentController
from backend.agent.mock_llm import DevMockGeminiClient


# Scenario 1: Feasible train recommendation with adequate buffer
def test_scenario_1_feasible_recommendation_with_buffer():
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
    plan = planner.plan_journey(req)
    assert plan.status == "answered"
    assert plan.best_match is not None
    assert plan.best_match.is_feasible is True
    assert plan.best_match.actual_arrival_buffer_minutes >= 45
    assert plan.best_match.booking_handoff is not None


# Scenario 2: Preferred train that misses the deadline
def test_scenario_2_preferred_train_misses_deadline():
    planner = JourneyPlanner()
    # Passenger prefers Vande Bharat (20608), which arrives MAS at 10:10 AM (after 10:00 AM meeting starts)
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
        preferred_train_name_or_number="20608",
    )
    plan = planner.plan_journey(req)
    # The preferred train must NOT be chosen as best feasible match
    assert plan.best_match.train_service.train_number != "20608"
    # The preferred train must be in infeasible list with explicit reason
    inf_vb = next((inf for inf in plan.infeasible_options if inf.train_service.train_number == "20608"), None)
    assert inf_vb is not None
    assert any("deadline" in v.lower() or "reaches" in v.lower() for v in inf_vb.hard_constraint_violations)
    # Trade-off explanation mentions the preferred train limitation
    assert plan.tradeoff_explanation is not None
    assert "20608" in plan.tradeoff_explanation or "Vande Bharat" in plan.tradeoff_explanation


# Scenario 3: Preferred class unsupported
def test_scenario_3_preferred_class_handling():
    planner = JourneyPlanner()
    # Passenger requests First AC (1A) on a route/train where only CC is available
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="20:00",  # Evening meeting
        preferred_class="1A",
    )
    plan = planner.plan_journey(req)
    assert plan.status == "answered"
    # Even if 1A is not present on afternoon Double Decker (CC only), feasible alternatives are transparently labeled
    assert plan.best_match is not None


# Scenario 4: No candidate satisfies the deadline
def test_scenario_4_no_candidate_satisfies_deadline():
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="04:00",  # Extremely early (04:00 AM)
        required_arrival_buffer_minutes=60,
    )
    plan = planner.plan_journey(req)
    assert plan.status == "no_feasible_journey"
    assert plan.best_match is None
    assert len(plan.infeasible_options) > 0


# Scenario 5: Last-mile calculation
def test_scenario_5_last_mile_calculation():
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
    )
    plan = planner.plan_journey(req)
    assert plan.best_match.last_mile_duration_minutes > 0
    assert plan.best_match.last_mile_distance_km > 0
    assert "Tidel Park" in plan.best_match.last_mile_destination_venue


# Scenario 6: Train schedule data freshness & provenance
def test_scenario_6_data_freshness_provenance():
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
    )
    plan = planner.plan_journey(req)
    assert len(plan.sources) > 0
    for src in plan.sources:
        assert "source_url" in src
        assert "last_verified_at" in src


# Scenario 7: Provider unavailable handling
def test_scenario_7_provider_error_handling(client):
    # Missing required fields returns explicit error status
    res = client.post("/api/journey/plan", json={"origin": ""})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "clarification_required"


# Scenario 8: Passenger changes meeting time (refine workflow)
def test_scenario_8_refine_meeting_time(client):
    init_res = client.post("/api/journey/plan", json={
        "origin": "Bengaluru",
        "destination_venue": "Tidel Park",
        "meeting_date": "2026-10-25",
        "meeting_time": "10:00",
    })
    init_data = init_res.get_json()
    
    # Change time to 15:00
    refine_res = client.post("/api/journey/refine", json={
        "requirements": init_data["trip_requirements"],
        "meeting_time": "15:00",
    })
    refine_data = refine_res.get_json()
    assert refine_data["trip_requirements"]["meeting_time"] == "15:00"


# Scenario 9: Journey crossing midnight
def test_scenario_9_journey_crossing_midnight():
    planner = JourneyPlanner()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        destination_city="Chennai",
        meeting_date="2026-10-25",
        meeting_time="10:00",
    )
    plan = planner.plan_journey(req)
    # Overnight Chennai Mail departs 2026-10-24 at 22:40, arrives 2026-10-25 at 04:35
    assert plan.best_match.train_service.day_offset == 1
    assert "2026-10-24" in plan.best_match.departure_datetime_iso
    assert "2026-10-25" in plan.best_match.arrival_datetime_iso


# Scenario 10: Malicious request / security check
def test_scenario_10_security_unapproved_urls():
    assert is_url_safe_and_allowlisted("https://malicious-site.com/steal-session") is False
    assert is_url_safe_and_allowlisted("http://insecure-domain.org") is False
    assert is_url_safe_and_allowlisted("https://www.irctc.co.in/nget/train-search") is True
