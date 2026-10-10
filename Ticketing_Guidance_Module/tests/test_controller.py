"""
RailSathi AI — Agent Controller Tests
"""

from tests.conftest import MockGeminiClient, MockGenerateContentResponse
from backend.agent.controller import AgentController


def test_controller_direct_text(temp_db):
    """Verify controller handles a direct text response from LLM."""
    mock_llm = MockGeminiClient([
        MockGenerateContentResponse(text="Hello! I am RailSathi AI, your Indian Railways assistant.")
    ])
    controller = AgentController(
        llm_client=mock_llm,
        db_path=temp_db,
    )

    response = controller.process_message("Hello")
    assert response.status == "answered"
    assert "RailSathi AI" in response.answer
    assert response.tool_calls_made == 0
    assert response.rounds_used == 1
    assert len(response.trace) >= 1


def test_controller_tool_execution_flow(temp_db):
    """Verify controller executes requested tool and passes evidence back to LLM."""
    # Round 1: Model requests explain_ticket_class for 3A
    # Round 2: Model returns synthesized answer
    mock_llm = MockGeminiClient([
        MockGenerateContentResponse(function_calls=[{
            "name": "explain_ticket_class",
            "args": {"class_code": "3A"},
        }]),
        MockGenerateContentResponse(text="Third AC (3A) has 3 tiers of air-conditioned berths with bedding provided."),
    ])

    controller = AgentController(
        llm_client=mock_llm,
        db_path=temp_db,
    )

    response = controller.process_message("Tell me about 3A")
    assert response.status == "answered"
    assert "Third AC" in response.answer
    assert response.tool_calls_made == 1
    assert response.rounds_used == 2
    assert len(response.sources) > 0
    assert response.evidence_sufficient is True


def test_controller_disallowed_tool(temp_db):
    """Verify controller rejects a tool not in the allowed list."""
    mock_llm = MockGeminiClient([
        MockGenerateContentResponse(function_calls=[{
            "name": "unauthorized_tool",
            "args": {},
        }]),
        MockGenerateContentResponse(text="I cannot execute that tool."),
    ])

    controller = AgentController(
        llm_client=mock_llm,
        db_path=temp_db,
        allowed_tools=["explain_ticket_class"],
    )

    response = controller.process_message("Run something")
    # Disallowed tool should have an error trace entry
    error_traces = [t for t in response.trace if t.get("event") == "error"]
    assert any("not allowed" in t.get("detail", "").lower() for t in error_traces)


def test_controller_max_rounds_budget(temp_db):
    """Verify controller stops when max rounds budget is reached."""
    # Model keeps calling functions endlessly
    infinite_calls = [
        MockGenerateContentResponse(function_calls=[{
            "name": "explain_ticket_class",
            "args": {"class_code": "SL"},
        }])
        for _ in range(10)
    ]
    mock_llm = MockGeminiClient(infinite_calls)

    controller = AgentController(
        llm_client=mock_llm,
        db_path=temp_db,
        max_rounds=2,
        max_tool_calls=10,
    )

    response = controller.process_message("Infinite loop test")
    assert response.status == "execution_limit_reached"
    assert response.rounds_used == 2
    assert "limit" in response.answer.lower()


def test_controller_max_tool_budget(temp_db):
    """Verify controller stops when max tool calls limit is reached."""
    # Model requests 3 tool calls in 1 round, but max_tool_calls is 2
    mock_llm = MockGeminiClient([
        MockGenerateContentResponse(function_calls=[
            {"name": "explain_ticket_class", "args": {"class_code": "SL"}},
            {"name": "explain_ticket_class", "args": {"class_code": "3A"}},
            {"name": "explain_ticket_class", "args": {"class_code": "2A"}},
        ]),
        MockGenerateContentResponse(text="Summary of classes"),
    ])

    controller = AgentController(
        llm_client=mock_llm,
        db_path=temp_db,
        max_rounds=5,
        max_tool_calls=2,
    )

    response = controller.process_message("Compare three classes")
    assert response.tool_calls_made <= 2
    budget_traces = [t for t in response.trace if t.get("event") == "budget_exceeded"]
    assert len(budget_traces) >= 1


def test_controller_empty_message(temp_db):
    """Verify controller validates empty or whitespace input."""
    mock_llm = MockGeminiClient()
    controller = AgentController(llm_client=mock_llm, db_path=temp_db)

    response = controller.process_message("")
    assert response.status == "error"

    response = controller.process_message("    ")
    assert response.status == "error"


def test_controller_message_length_limit(temp_db):
    """Verify controller rejects messages exceeding character limit."""
    mock_llm = MockGeminiClient()
    controller = AgentController(llm_client=mock_llm, db_path=temp_db)

    response = controller.process_message("A" * 2001)
    assert response.status == "error"
    assert "too long" in response.answer.lower()
