# DECISIONS — RailSathi AI

## Decision Log

### DEC-001 — Project Brain Directory Structure
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Use `.agent/` directory at repository root for project memory and management infrastructure.
- **Rationale**: Follows standard established conventions with clean namespaces.
- **Related files**: `.agent/*`

---

### DEC-002 — Fresh Repository Initialization
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Initialize a fresh Git repository on `master` branch.
- **Related files**: `.git/`

---

### DEC-003 — Target Technology Stack
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Target stack: React+Vite (frontend), Python+Flask (backend), Gemini API (LLM), SQLite FTS5 (knowledge), pytest (testing).
- **Related files**: `backend/requirements.txt`, `frontend/package.json`

---

### DEC-004 — SQLite FTS5 for Knowledge Storage & Retrieval
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Use SQLite with an FTS5 virtual table for full-text keyword indexing and search, supplemented with standard relational tables for sources and guidance records.
- **Related files**: `backend/knowledge/database.py`, `backend/knowledge/retrieval.py`

---

### DEC-005 — Deterministic Read-Only Tool Suite with Provenance
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Implement narrowly scoped, read-only tools with source attribution.
- **Related files**: `backend/tools/ticketing.py`, `backend/tools/journey_tools.py`, `backend/tools/registry.py`

---

### DEC-006 — Deterministic Controller with Call Budgets and Tracing
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: The Agent Controller enforces strict maximum rounds (`MAX_AGENT_ROUNDS=4`) and maximum tool calls (`MAX_TOOL_CALLS=6`) per user request, emitting a structured trace.
- **Related files**: `backend/agent/controller.py`

---

### DEC-007 — Development Mock LLM for Local Evaluation
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Provide `DevMockGeminiClient` as a drop-in fallback when `GEMINI_API_KEY` is not present in `.env`.
- **Related files**: `backend/agent/mock_llm.py`, `backend/app.py`

---

### DEC-008 — Separation of LLM Reasoning from Deterministic Feasibility Engine
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: LLMs must NEVER perform authoritative time arithmetic, date offset calculation, or constraint verification from memory. All feasibility evaluations, station deadlines (`latest_acceptable_station_arrival = meeting_start - requested_buffer - last_mile_transit`), overnight date shifts, and ranking scores are executed in deterministic Python.
- **Rationale**: LLM arithmetic is prone to hallucination, subtle time subtraction errors, and double-subtraction. Deterministic code guarantees mathematical correctness and reproducible ranking.
- **Related files**: `backend/journey/feasibility.py`, `backend/journey/ranking.py`

---

### DEC-009 — Strict Hard Constraints vs Soft Preferences
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Explicitly separate non-negotiable hard constraints (e.g. arrival deadline before meeting start, required buffer satisfaction) from soft preferences (e.g. preferred travel class, budget ceiling, preferred train).
- **Rationale**: A cheaper train or preferred train must NEVER be recommended as the best match if it violates the arrival deadline. Trains violating hard constraints are isolated in an "Infeasible / Does Not Meet Requirements" section with clear diagnostic explanations.
- **Related files**: `backend/journey/models.py`, `backend/journey/feasibility.py`, `backend/journey/ranking.py`

---

### DEC-010 — Abstracted Location & Timetable Data Providers with Verified Data
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Abstract geocoding, station discovery, last-mile estimation, and train schedules behind service interfaces (`LocationResolutionService`, `TrainSearchService`) powered by verified data sources.
- **Rationale**: Prevents hardcoding fragile external scrapers while providing reliable, verified train schedules and geographic distances for major Indian corridors. Prohibits inventing synthetic data.
- **Related files**: `backend/journey/location.py`, `backend/journey/timetable.py`

---

### DEC-011 — Official IRCTC Booking Handoff with Strict URL Allowlist
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: RailSathi acts strictly as a booking advisor. Booking is completed by handing off passengers to official IRCTC portal search links validated against an approved hostname allowlist (`www.irctc.co.in`, `enquiry.indianrail.gov.in`, `confirmtkt.com`).
- **Rationale**: Automated credential scraping or booking submission violates IRCTC terms and creates security liabilities. Allowlisting prevents malicious URL injection or phishing links.
- **Related files**: `backend/journey/booking.py`

---

### DEC-012 — Dual-Mode React Frontend with Timeline Visualizer
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Provide a unified application interface featuring a dedicated "🎯 Goal Journey Planner" tab with journey timeline visualizers, candidate station badges, and one-click refiners alongside the "💬 Ticketing Guidance" chat.
- **Rationale**: Maximizes usability for passengers planning time-critical journeys while retaining instant access to ticketing rules.
- **Related files**: `frontend/src/App.jsx`, `frontend/src/App.css`
