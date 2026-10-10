"""
RailSathi AI — Ticketing Tools Tests
"""

from backend.tools.ticketing import (
    get_tool_names,
    get_tool_schema,
    validate_tool_args,
    execute_tool,
    TOOL_SCHEMAS,
)


def test_tool_registration():
    """Verify all 5 planned tools are registered with schemas."""
    names = get_tool_names()
    assert "search_ticketing_guidance" in names
    assert "explain_ticket_class" in names
    assert "explain_reservation_status" in names
    assert "get_booking_steps" in names
    assert "get_cancellation_refund_guidance" in names
    assert len(names) == 5

    for name in names:
        schema = get_tool_schema(name)
        assert schema is not None
        assert "description" in schema
        assert "parameters" in schema


def test_validate_tool_args():
    """Verify argument validation accepts valid args and catches invalid or missing args."""
    # Unknown tool
    valid, err = validate_tool_args("non_existent_tool", {})
    assert not valid
    assert "Unknown tool" in err

    # Missing required argument
    valid, err = validate_tool_args("explain_ticket_class", {})
    assert not valid
    assert "Missing required argument" in err

    # Valid args
    valid, err = validate_tool_args("explain_ticket_class", {"class_code": "3A"})
    assert valid
    assert err is None

    # Invalid enum
    valid, err = validate_tool_args("get_booking_steps", {"booking_channel": "telegram_bot"})
    assert not valid
    assert "must be one of" in err


def test_explain_ticket_class_valid(temp_db):
    """Verify explain_ticket_class returns structured class details and sources."""
    result = execute_tool("explain_ticket_class", {"class_code": "3A"}, temp_db)
    assert result["status"] == "success"
    assert result["tool_name"] == "explain_ticket_class"
    assert "primary_class" in result
    assert len(result["primary_class"]["results"]) > 0
    assert len(result["sources"]) > 0
    assert result["evidence_sufficient"] is True


def test_explain_ticket_class_comparison(temp_db):
    """Verify comparing two classes returns guidance for both."""
    result = execute_tool("explain_ticket_class", {"class_code": "3A", "comparison_class": "2A"}, temp_db)
    assert result["status"] == "success"
    assert "primary_class" in result
    assert "comparison_class" in result
    assert len(result["primary_class"]["results"]) > 0
    assert len(result["comparison_class"]["results"]) > 0
    assert len(result["sources"]) >= 2


def test_explain_ticket_class_invalid(temp_db):
    """Verify invalid class code returns error status."""
    result = execute_tool("explain_ticket_class", {"class_code": "ZZZ"}, temp_db)
    assert result["status"] == "error"
    assert "Unsupported class code" in result["error"]


def test_explain_reservation_status_valid(temp_db):
    """Verify explain_reservation_status returns RAC / WL rules."""
    result = execute_tool("explain_reservation_status", {"status_code": "RAC"}, temp_db)
    assert result["status"] == "success"
    assert len(result["results"]) > 0
    assert any("RAC" in r["answer_text"] for r in result["results"])


def test_explain_reservation_status_invalid(temp_db):
    """Verify invalid reservation status code returns error."""
    result = execute_tool("explain_reservation_status", {"status_code": "INVALID_CODE"}, temp_db)
    assert result["status"] == "error"
    assert "Unsupported status code" in result["error"]


def test_get_booking_steps_irctc(temp_db):
    """Verify get_booking_steps returns IRCTC procedure."""
    result = execute_tool("get_booking_steps", {"booking_channel": "irctc_online"}, temp_db)
    assert result["status"] == "success"
    assert len(result["results"]) > 0


def test_get_booking_steps_counter(temp_db):
    """Verify get_booking_steps returns counter procedure."""
    result = execute_tool("get_booking_steps", {"booking_channel": "counter"}, temp_db)
    assert result["status"] == "success"
    assert len(result["results"]) > 0


def test_get_cancellation_refund_guidance(temp_db):
    """Verify get_cancellation_refund_guidance returns refund rules."""
    result = execute_tool(
        "get_cancellation_refund_guidance",
        {"question": "What is the cancellation charge for confirmed ticket?"},
        temp_db,
    )
    assert result["status"] == "success"
    assert len(result["results"]) > 0


def test_search_ticketing_guidance(temp_db):
    """Verify general search tool returns relevant results and sources."""
    result = execute_tool(
        "search_ticketing_guidance",
        {"query": "Tatkal booking timing"},
        temp_db,
    )
    assert result["status"] == "success"
    assert len(result["results"]) > 0
    assert len(result["sources"]) > 0
