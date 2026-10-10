"""
RailSathi AI — Journey Planner API Endpoints Tests
"""

import json
import pytest


def test_api_journey_plan_natural_language(client):
    """Test /api/journey/plan with natural language prompt."""
    payload = {
        "prompt": (
            "I have a meeting at Tidel Park in Chennai at 10:00 AM on 25 October. "
            "I'm travelling from Bengaluru. I want AC 3-tier if possible, prefer a reasonably affordable train, "
            "and want to reach at least 45 minutes early."
        )
    }
    response = client.post("/api/journey/plan", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "answered"
    assert "trip_requirements" in data
    assert data["trip_requirements"]["origin"] == "Bengaluru"
    assert data["best_match"] is not None
    assert data["best_match"]["is_feasible"] is True
    assert "booking_handoff" in data["best_match"]
    assert "irctc.co.in" in data["best_match"]["booking_handoff"]["booking_url"]


def test_api_journey_plan_structured_fields(client):
    """Test /api/journey/plan with structured input fields."""
    payload = {
        "origin": "Bengaluru",
        "destination_venue": "Tidel Park",
        "meeting_date": "2026-10-25",
        "meeting_time": "10:00",
        "required_arrival_buffer_minutes": 45,
        "preferred_class": "3A",
    }
    response = client.post("/api/journey/plan", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "answered"
    assert data["best_match"]["train_service"]["train_number"] == "12658"


def test_api_journey_plan_missing_fields(client):
    """Test /api/journey/plan missing required fields returns clarification required."""
    payload = {
        "origin": "Bengaluru",
        # missing destination_venue, meeting_date, meeting_time
    }
    response = client.post("/api/journey/plan", json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "clarification_required"
    assert "missing_fields" in data


def test_api_journey_refine_flow(client):
    """Test /api/journey/refine modifying time and buffer."""
    # First plan
    init_res = client.post("/api/journey/plan", json={
        "prompt": "Meeting at Tidel Park Chennai from Bengaluru on 2026-10-25 at 10:00 AM."
    })
    assert init_res.status_code == 200
    init_data = init_res.get_json()

    # Refine to 2:00 PM meeting time
    refine_payload = {
        "requirements": init_data["trip_requirements"],
        "meeting_time": "14:00",
        "required_arrival_buffer_minutes": 60,
    }
    refine_res = client.post("/api/journey/refine", json=refine_payload)
    assert refine_res.status_code == 200
    refine_data = refine_res.get_json()
    assert refine_data["trip_requirements"]["meeting_time"] == "14:00"
    assert refine_data["trip_requirements"]["required_arrival_buffer_minutes"] == 60


def test_api_journey_options_get_by_id(client):
    """Test /api/journey/options/<request_id> retrieval."""
    plan_res = client.post("/api/journey/plan", json={
        "prompt": "Meeting at Tidel Park Chennai from Bengaluru on 2026-10-25 at 10:00 AM."
    })
    plan_data = plan_res.get_json()
    trace_id = plan_data["trace_id"]

    get_res = client.get(f"/api/journey/options/{trace_id}")
    assert get_res.status_code == 200
    get_data = get_res.get_json()
    assert get_data["trace_id"] == trace_id
    assert get_data["status"] == "answered"


def test_api_journey_options_not_found(client):
    """Test 404 for non-existent trace ID."""
    res = client.get("/api/journey/options/non-existent-id-12345")
    assert res.status_code == 404
