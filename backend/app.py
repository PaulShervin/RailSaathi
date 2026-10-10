"""
RailSathi AI — Flask Application

Main backend API with endpoints for chat, health, and source metadata.
"""

import json
import logging
import os
import sys
import uuid
from pathlib import Path

from flask import Flask, request, jsonify

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TEMPERATURE, GEMINI_MAX_OUTPUT_TOKENS,
    MAX_AGENT_ROUNDS, MAX_TOOL_CALLS, MAX_INPUT_LENGTH, MAX_HISTORY_MESSAGES,
    FLASK_DEBUG, FLASK_PORT, CORS_ORIGINS, DB_PATH, LOG_LEVEL, LOG_DIR,
)
from backend.knowledge.database import init_database, get_connection, get_all_sources
from backend.knowledge.ingest import ingest
from backend.agent.conversations import ConversationManager
from backend.agent.controller import AgentController
from backend.tools.registry import get_all_tool_names
from backend.journey.models import TripRequirements
from backend.journey.planner import JourneyPlanner, parse_requirements_from_text

# === Logging Setup ===
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "railsaathi.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("railsaathi.app")


# === App Factory ===
def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Configuration
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # 16KB max request

    # === Initialize Database ===
    if not DB_PATH.exists():
        logger.info("Database not found. Running initial ingestion...")
        ingest(DB_PATH)
    else:
        # Ensure schema is up to date
        init_database(DB_PATH)

    # === Initialize LLM Client ===
    llm_client = None
    if GEMINI_API_KEY and (not test_config or not test_config.get("mock_llm")):
        try:
            from backend.agent.llm import GeminiClient
            llm_client = GeminiClient(
                api_key=GEMINI_API_KEY,
                model_name=GEMINI_MODEL,
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            )
            logger.info(f"Gemini client initialized: model={GEMINI_MODEL}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")

    if test_config and test_config.get("llm_client"):
        llm_client = test_config["llm_client"]
    elif llm_client is None and not (test_config and test_config.get("strict_no_llm")):
        from backend.agent.mock_llm import DevMockGeminiClient
        llm_client = DevMockGeminiClient()
        logger.info("Using DevMockGeminiClient (development/offline mode)")

    # === Initialize Conversation Manager ===
    conversation_manager = ConversationManager(
        max_history=MAX_HISTORY_MESSAGES,
    )

    # === CORS Middleware ===
    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin", "")
        if origin in CORS_ORIGINS or FLASK_DEBUG:
            response.headers["Access-Control-Allow-Origin"] = origin or CORS_ORIGINS[0]
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "3600"
        return response

    @app.route("/api/<path:path>", methods=["OPTIONS"])
    def handle_options(path):
        return "", 204

    # === Health Endpoint ===
    @app.route("/api/health", methods=["GET"])
    def health():
        """Return service health status."""
        db_ok = DB_PATH.exists()
        llm_ok = llm_client is not None

        return jsonify({
            "status": "healthy" if (db_ok and llm_ok) else "degraded",
            "database": "connected" if db_ok else "missing",
            "llm": "connected" if llm_ok else "not_configured",
            "model": GEMINI_MODEL if llm_ok else None,
            "tools_available": get_all_tool_names(),
            "journey_planner": "enabled",
        })

    # === Sources Endpoint ===
    @app.route("/api/sources", methods=["GET"])
    def list_sources():
        """Return source metadata for the UI."""
        try:
            conn = get_connection(DB_PATH)
            sources = get_all_sources(conn)
            conn.close()

            # Filter to safe fields only
            safe_sources = []
            for s in sources:
                safe_sources.append({
                    "source_id": s["source_id"],
                    "title": s["title"],
                    "publisher": s["publisher"],
                    "source_url": s["source_url"],
                    "source_type": s["source_type"],
                    "last_verified_at": s["last_verified_at"],
                    "verification_status": s["verification_status"],
                })

            return jsonify({"sources": safe_sources, "total": len(safe_sources)})
        except Exception as e:
            logger.error(f"Sources endpoint error: {e}")
            return jsonify({"error": "Failed to retrieve sources"}), 500

    # === Chat Endpoint ===
    @app.route("/api/chat", methods=["POST"])
    def chat():
        """Process a passenger question through the AI agent."""
        # Validate content type
        if not request.is_json:
            return jsonify({
                "error": "Request must be JSON",
                "status": "error",
            }), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "error": "Invalid JSON body",
                "status": "error",
            }), 400

        message = data.get("message", "").strip()
        conversation_id = data.get("conversation_id")

        # Validate message
        if not message:
            return jsonify({
                "error": "Message is required",
                "status": "error",
            }), 400

        if len(message) > MAX_INPUT_LENGTH:
            return jsonify({
                "error": f"Message exceeds maximum length ({MAX_INPUT_LENGTH} characters)",
                "status": "error",
            }), 400

        # Check LLM availability
        if llm_client is None:
            return jsonify({
                "error": "AI service is not configured. Please set GEMINI_API_KEY.",
                "status": "service_unavailable",
                "conversation_id": conversation_id,
            }), 503

        # Get or create conversation
        conv_id, history = conversation_manager.get_or_create(conversation_id)

        # Create controller and process
        controller = AgentController(
            llm_client=llm_client,
            db_path=str(DB_PATH),
            max_rounds=MAX_AGENT_ROUNDS,
            max_tool_calls=MAX_TOOL_CALLS,
        )

        try:
            result = controller.process_message(message, history)
        except Exception as e:
            logger.error(f"Controller error: {e}", exc_info=True)
            return jsonify({
                "error": "An unexpected error occurred processing your request.",
                "status": "error",
                "conversation_id": conv_id,
            }), 500

        # Update conversation history (simplified — store user message and final answer)
        from google.genai import types as genai_types
        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=message)],
        )
        model_content = genai_types.Content(
            role="model",
            parts=[genai_types.Part.from_text(text=result.answer)],
        )
        conversation_manager.add_exchange(conv_id, user_content, model_content)

        # Build response
        response_data = {
            "conversation_id": conv_id,
            "answer": result.answer,
            "status": result.status,
            "sources": result.sources,
            "trace_id": result.trace_id,
        }

        # Include trace in development mode only
        if FLASK_DEBUG:
            response_data["trace"] = result.trace
            response_data["tool_calls_made"] = result.tool_calls_made
            response_data["rounds_used"] = result.rounds_used

        # Log the request (redacted)
        logger.info(
            f"Chat request: trace={result.trace_id} status={result.status} "
            f"tools={result.tool_calls_made} rounds={result.rounds_used} "
            f"sources={len(result.sources)}"
        )

        return jsonify(response_data)

    # === Conversation Info Endpoint ===
    @app.route("/api/conversations/<conversation_id>", methods=["GET"])
    def get_conversation(conversation_id):
        """Get conversation metadata."""
        info = conversation_manager.get_conversation_info(conversation_id)
        if not info:
            return jsonify({"error": "Conversation not found"}), 404
        return jsonify(info)

    # === Journey Planning Storage & Planner ===
    journey_planner = JourneyPlanner()
    journey_plans_store: dict[str, dict] = {}

    def _store_journey_plan(plan_dict: dict) -> None:
        """Store a journey plan in memory with bounded eviction (max 200)."""
        tid = plan_dict.get("trace_id")
        if not tid:
            return
        if len(journey_plans_store) > 200:
            oldest_k = next(iter(journey_plans_store))
            journey_plans_store.pop(oldest_k, None)
        journey_plans_store[tid] = plan_dict

    # === Journey Plan Endpoint ===
    @app.route("/api/journey/plan", methods=["POST"])
    def plan_journey_endpoint():
        """
        Accept a natural language journey request or structured fields,
        deterministically validate requirements, compute feasibility,
        and return ranked recommendations with booking handoffs.
        """
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "status": "invalid_request"}), 400

        data = request.get_json(silent=True) or {}
        prompt = data.get("prompt", "").strip()
        trace_id = data.get("trace_id") or f"req-{uuid.uuid4().hex[:10]}"

        try:
            # If natural language prompt supplied, extract base requirements
            if prompt:
                req = parse_requirements_from_text(prompt)
            else:
                # Must provide structured fields
                origin = data.get("origin", "").strip()
                venue = data.get("destination_venue", "").strip()
                m_date = data.get("meeting_date", "").strip()
                m_time = data.get("meeting_time", "").strip()

                if not origin or not venue or not m_date or not m_time:
                    return jsonify({
                        "error": "Missing essential fields: origin, destination_venue, meeting_date, and meeting_time are required",
                        "status": "clarification_required",
                        "missing_fields": [
                            f for f, v in [
                                ("origin", origin),
                                ("destination_venue", venue),
                                ("meeting_date", m_date),
                                ("meeting_time", m_time),
                            ] if not v
                        ],
                    }), 400

                req = TripRequirements(
                    origin=origin,
                    destination_venue=venue,
                    destination_address=data.get("destination_address"),
                    destination_city=data.get("destination_city"),
                    meeting_date=m_date,
                    meeting_time=m_time,
                    required_arrival_buffer_minutes=int(data.get("required_arrival_buffer_minutes", 45)),
                    preferred_train_name_or_number=data.get("preferred_train_name_or_number"),
                    preferred_class=data.get("preferred_class"),
                    budget_max=float(data["budget_max"]) if data.get("budget_max") is not None else None,
                )

            # Override with any explicit structured overrides passed in data
            if data.get("origin"):
                req.origin = data["origin"].strip()
            if data.get("destination_venue"):
                req.destination_venue = data["destination_venue"].strip()
            if data.get("destination_city"):
                req.destination_city = data["destination_city"].strip()
            if data.get("meeting_date"):
                req.meeting_date = data["meeting_date"].strip()
            if data.get("meeting_time"):
                req.meeting_time = data["meeting_time"].strip()
            if data.get("required_arrival_buffer_minutes") is not None:
                req.required_arrival_buffer_minutes = int(data["required_arrival_buffer_minutes"])
            if data.get("preferred_class"):
                req.preferred_class = data["preferred_class"].strip()
            if data.get("preferred_train_name_or_number"):
                req.preferred_train_name_or_number = data["preferred_train_name_or_number"].strip()
            if data.get("budget_max") is not None:
                req.budget_max = float(data["budget_max"])

            plan_result = journey_planner.plan_journey(req, trace_id=trace_id)
            plan_dict = plan_result.model_dump()
            _store_journey_plan(plan_dict)

            logger.info(
                f"Journey plan generated: trace={trace_id} status={plan_result.status} "
                f"feasible={1 if plan_result.best_match else 0} alts={len(plan_result.feasible_alternatives)}"
            )
            return jsonify(plan_dict)

        except Exception as e:
            logger.error(f"Error in plan_journey_endpoint: {e}", exc_info=True)
            return jsonify({
                "error": "Failed to process journey plan",
                "detail": str(e),
                "status": "invalid_request",
                "trace_id": trace_id,
            }), 500

    # === Journey Refine Endpoint ===
    @app.route("/api/journey/refine", methods=["POST"])
    def refine_journey_endpoint():
        """
        Refine an existing journey plan with updated constraints or preferences.
        """
        if not request.is_json:
            return jsonify({"error": "Request must be JSON", "status": "invalid_request"}), 400

        data = request.get_json(silent=True) or {}
        base_req_data = data.get("requirements") or {}
        trace_id = data.get("trace_id") or f"refine-{uuid.uuid4().hex[:10]}"

        try:
            req = TripRequirements(**base_req_data)

            # Apply refinements
            if data.get("meeting_time"):
                req.meeting_time = data["meeting_time"].strip()
            if data.get("required_arrival_buffer_minutes") is not None:
                req.required_arrival_buffer_minutes = int(data["required_arrival_buffer_minutes"])
            if data.get("preferred_class") is not None:
                req.preferred_class = data["preferred_class"].strip() or None
            if data.get("preferred_train_name_or_number") is not None:
                req.preferred_train_name_or_number = data["preferred_train_name_or_number"].strip() or None
            if data.get("budget_max") is not None:
                req.budget_max = float(data["budget_max"]) if data["budget_max"] != "" else None

            plan_result = journey_planner.plan_journey(req, trace_id=trace_id)
            plan_dict = plan_result.model_dump()
            _store_journey_plan(plan_dict)

            return jsonify(plan_dict)

        except Exception as e:
            logger.error(f"Error in refine_journey_endpoint: {e}", exc_info=True)
            return jsonify({
                "error": "Failed to refine journey plan",
                "detail": str(e),
                "status": "invalid_request",
            }), 500

    # === Journey Options Endpoint ===
    @app.route("/api/journey/options/<request_id>", methods=["GET"])
    def get_journey_options(request_id):
        """Retrieve an existing generated journey plan by request/trace ID."""
        plan = journey_plans_store.get(request_id)
        if not plan:
            return jsonify({"error": "Journey plan not found or expired", "request_id": request_id}), 404
        return jsonify(plan)

    return app


# === Main ===
if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting RailSathi AI backend on port {FLASK_PORT}")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG)
