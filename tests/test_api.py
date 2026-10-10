"""
RailSathi AI — Flask API Tests
"""

import json


def test_api_health(client):
    """Verify /api/health returns 200 and expected status fields."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert "status" in data
    assert "database" in data
    assert "llm" in data
    assert "tools_available" in data
    assert len(data["tools_available"]) >= 5
    assert "search_ticketing_guidance" in data["tools_available"]
    assert "plan_goal_based_journey" in data["tools_available"]


def test_api_sources(client):
    """Verify /api/sources returns list of verified official sources."""
    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.get_json()
    assert "sources" in data
    assert "total" in data
    assert data["total"] > 0
    # Every source must have official attributes
    for s in data["sources"]:
        assert "source_url" in s
        assert "publisher" in s
        assert "verification_status" in s


def test_api_chat_empty_request(client):
    """Verify POST /api/chat rejects empty or non-JSON payloads with 400."""
    response = client.post("/api/chat", data="not json", content_type="text/plain")
    assert response.status_code == 400

    response = client.post("/api/chat", json={})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_api_chat_message_length_limit(client):
    """Verify POST /api/chat enforces maximum message length."""
    response = client.post("/api/chat", json={"message": "X" * 2001})
    assert response.status_code == 400
    assert "exceeds" in response.get_json()["error"]


def test_api_chat_success_flow(client):
    """Verify POST /api/chat successfully processes a query and returns structured response."""
    payload = {
        "message": "What is the difference between 2A and 3A?",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert "answer" in data
    assert "status" in data
    assert "conversation_id" in data
    assert "trace_id" in data
    assert "sources" in data


def test_api_chat_conversation_continuation(client):
    """Verify multiple messages can be chained in the same conversation."""
    resp1 = client.post("/api/chat", json={"message": "What is Sleeper class?"})
    assert resp1.status_code == 200
    conv_id = resp1.get_json()["conversation_id"]

    resp2 = client.post("/api/chat", json={
        "message": "And how is it different from 3A?",
        "conversation_id": conv_id,
    })
    assert resp2.status_code == 200
    assert resp2.get_json()["conversation_id"] == conv_id


def test_cors_preflight(client):
    """Verify CORS preflight OPTIONS returns 204 with required headers."""
    response = client.options("/api/chat", headers={"Origin": "http://localhost:5173"})
    assert response.status_code in (200, 204)
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
