"""
RailSathi AI — Pytest Configuration & Fixtures
"""

import tempfile
from pathlib import Path
from typing import Any
import pytest
from google.genai import types

from backend.knowledge.database import init_database
from backend.knowledge.ingest import ingest
from backend.app import create_app


class MockGenerateContentResponse:
    """Mock for types.GenerateContentResponse."""

    def __init__(self, text: str = "", function_calls: list[dict] | None = None):
        self.parts = []
        if function_calls:
            for fc in function_calls:
                call_mock = type("MockFunctionCall", (), {
                    "name": fc["name"],
                    "args": fc.get("args", {}),
                })()
                self.parts.append(type("MockPart", (), {
                    "function_call": call_mock,
                    "text": None,
                })())
        elif text:
            self.parts.append(type("MockPart", (), {
                "function_call": None,
                "text": text,
            })())

        content = types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)] if text else []
        )
        # Attach parts directly to mock content for custom inspection
        content.parts = self.parts
        self.candidates = [type("MockCandidate", (), {"content": content})()]


class MockGeminiClient:
    """
    Mock Gemini client for deterministic unit and integration tests.
    Can be scripted with a queue of responses.
    """

    def __init__(self, responses: list[MockGenerateContentResponse] | None = None):
        self.responses = list(responses or [])
        self.call_history: list[list[types.Content]] = []

    def queue_response(self, response: MockGenerateContentResponse):
        self.responses.append(response)

    def generate(self, contents: list[types.Content]) -> MockGenerateContentResponse:
        self.call_history.append(contents)
        if not self.responses:
            return MockGenerateContentResponse(
                text="This is a default mock response from RailSathi AI."
            )
        return self.responses.pop(0)

    def is_function_call(self, response: Any) -> bool:
        if not response.candidates:
            return False
        parts = response.candidates[0].content.parts
        return any(bool(getattr(p, "function_call", None)) for p in parts if p)

    def get_function_calls(self, response: Any) -> list[dict]:
        calls = []
        if not response.candidates:
            return calls
        for part in response.candidates[0].content.parts:
            if part and getattr(part, "function_call", None):
                fc = part.function_call
                calls.append({
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                })
        return calls

    def get_text(self, response: Any) -> str:
        if not response.candidates:
            return ""
        parts = response.candidates[0].content.parts
        text_parts = [part.text for part in parts if part and getattr(part, "text", None)]
        return "\n".join(text_parts)

    def build_user_content(self, message: str) -> types.Content:
        return types.Content(role="user", parts=[types.Part.from_text(text=message)])

    def build_model_content(self, response: Any) -> types.Content:
        if response.candidates:
            return response.candidates[0].content
        return types.Content(role="model", parts=[types.Part.from_text(text="")])

    def build_function_response_content(self, function_responses: list[dict]) -> types.Content:
        parts = []
        for fr in function_responses:
            parts.append(types.Part.from_function_response(
                name=fr["name"],
                response=fr["response"],
            ))
        return types.Content(role="user", parts=parts)


@pytest.fixture
def temp_db():
    """Create a temporary populated RailSathi database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        init_database(db_path)
        ingest(db_path)
        yield db_path
    finally:
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    return MockGeminiClient()


@pytest.fixture
def app(temp_db, mock_llm):
    """Create a Flask test application."""
    test_app = create_app({
        "TESTING": True,
        "mock_llm": True,
        "llm_client": mock_llm,
    })
    # Overwrite DB_PATH in app config if needed
    yield test_app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app."""
    return app.test_client()
