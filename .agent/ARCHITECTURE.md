# ARCHITECTURE — RailSathi AI

> Last updated: 2026-10-10
> All components are currently **PLANNED** unless marked otherwise.

## System Overview

RailSathi AI is a tool-using GenAI application with a React frontend, Flask backend, Gemini LLM integration, and a deterministic agent controller that manages tool execution for Indian Railways ticketing guidance.

## Component Architecture

### Frontend — PLANNED
- **Technology**: React + Vite + Tailwind CSS
- **Responsibility**: Chat interface for passenger interaction
- **Location**: `frontend/` (planned)
- **Key features**: Message display, input handling, source citation rendering, loading states

### Backend API — PLANNED
- **Technology**: Python + Flask
- **Responsibility**: HTTP API layer, request validation, session management
- **Location**: `backend/` (planned)
- **Key endpoints**:
  - `POST /api/chat` — Accept passenger question, return guidance response
  - `GET /api/health` — Health check
- **Environment variables**: `GEMINI_API_KEY`, `FLASK_ENV`, `FLASK_PORT`

### Agent Controller — PLANNED
- **Technology**: Deterministic Python
- **Responsibility**: Orchestrate LLM calls and tool execution with validation, budgets, and logging
- **Location**: `backend/agent/` (planned)
- **Key behaviors**:
  - Parse LLM function-call responses
  - Validate tool names against allowed set
  - Validate tool arguments against schemas
  - Enforce per-request call budget (configurable, default TBD)
  - Execute approved tools
  - Collect evidence and pass back to LLM for synthesis
  - Log full execution trace (redacting secrets)
  - Return insufficient-information response when evidence is lacking

### LLM Integration — PLANNED
- **Technology**: Google Gemini API with function/tool calling
- **Responsibility**: Intent interpretation, tool selection, answer synthesis
- **Configuration**: Model name, temperature, max tokens, system prompt, tool declarations
- **Status**: API key not yet configured in environment

### Ticketing Guidance Tools — PLANNED
- **Location**: `backend/tools/` (planned)
- **Planned tools**:

| Tool | Purpose | Status |
|---|---|---|
| `explain_ticket_class` | Explain a specific ticket class (SL, 3A, 2A, etc.) | PLANNED |
| `explain_reservation_status` | Explain reservation terms (CNF, RAC, WL) | PLANNED |
| `get_booking_guidance` | Step-by-step booking process guidance | PLANNED |
| `get_cancellation_refund_info` | Cancellation rules and refund guidance | PLANNED |

- All tools return structured responses with `source_url`, `verification_date`, `content`, and `confidence` fields.

### Knowledge Storage — PLANNED
- **Technology**: Structured JSON files and/or SQLite
- **Location**: `backend/knowledge/` (planned)
- **Content**: Curated, source-attributed Indian Railways ticketing information
- **Schema**: TBD — must include source URL, retrieval date, applicable conditions, staleness indicator
- **Ingestion**: Manual curation from authoritative IRCTC/Indian Railways sources
- **Freshness**: Verification date tracked per entry; stale entries flagged

### Source Attribution & Freshness — PLANNED
- Every knowledge entry must have: `source_url`, `verification_date`, `applicable_conditions`
- Tools must return source metadata alongside content
- Agent must include source references in final responses
- Stale data (age TBD, e.g. >6 months) triggers a staleness warning

### Error Handling & Abstention — PLANNED
- Invalid tool arguments → reject with validation error, do not execute
- API timeout/error → return error status, do not retry unboundedly
- Empty retrieval → return insufficient-information response
- Contradictory sources → acknowledge contradiction, do not pick arbitrarily
- Budget exceeded → stop execution, return partial result with explanation

### Logging & Tracing — PLANNED
- **Location**: `backend/logs/` (planned)
- Per-request trace: question → intent → tool calls → evidence → response
- Each tool call logged: name, arguments (validated), result status, duration
- Secrets and personal data redacted from logs

### Test Architecture — PLANNED
- **Location**: `tests/` (planned)
- **Framework**: pytest (backend), Vitest or Jest (frontend)
- **Test categories**:
  - Unit: Individual tool functions, validation logic
  - Integration: Controller + tools, controller + LLM mock
  - Grounding: Responses cite valid sources, no hallucinated rules
  - Failure: Timeout handling, budget exceeded, invalid input, empty retrieval

## Configuration & Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API authentication | Yes (for LLM features) |
| `FLASK_ENV` | Flask environment (development/production) | No (default: development) |
| `FLASK_PORT` | Backend port | No (default: 5000) |
| `MAX_CALLS_PER_REQUEST` | Agent call budget | No (default: TBD) |

## Dependency Map

```
Frontend (React/Vite)
  └── calls → Backend API (Flask)
                ├── uses → Agent Controller
                │            ├── calls → Gemini API (LLM)
                │            ├── calls → Ticketing Tools
                │            │            └── reads → Knowledge Store
                │            └── writes → Trace Logger
                └── serves → Static assets (if applicable)
```

## Data Flow

See [diagrams/DATA_FLOW.md](./diagrams/DATA_FLOW.md) for the complete Mermaid diagram.
