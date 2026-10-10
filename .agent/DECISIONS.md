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
- **Decision**: Target stack: React+Vite (frontend), Python+Flask (backend), Gemini/Bedrock API (LLM), SQLite FTS5 (knowledge), pytest (testing).
- **Related files**: `Ticketing_Guidance_Module/backend/requirements.txt`, `Ticketing_Guidance_Module/frontend/package.json`

---

### DEC-004 — SQLite FTS5 for Knowledge Storage & Retrieval
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Use SQLite with an FTS5 virtual table for full-text keyword indexing and search, supplemented with standard relational tables for sources and guidance records.
- **Related files**: `Ticketing_Guidance_Module/backend/knowledge/database.py`, `Ticketing_Guidance_Module/backend/knowledge/retrieval.py`

---

### DEC-005 — Deterministic Read-Only Tool Suite with Provenance
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Implement narrowly scoped, read-only tools with source attribution.
- **Related files**: `Ticketing_Guidance_Module/backend/tools/ticketing.py`, `Ticketing_Guidance_Module/backend/tools/journey_tools.py`, `Ticketing_Guidance_Module/backend/tools/registry.py`

---

### DEC-006 — Deterministic Controller with Call Budgets and Tracing
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: The Agent Controller enforces strict maximum rounds (`MAX_AGENT_ROUNDS=4`) and maximum tool calls (`MAX_TOOL_CALLS=6`) per user request, emitting a structured trace.
- **Related files**: `Ticketing_Guidance_Module/backend/agent/controller.py`

---

### DEC-007 — Development Mock LLM for Local Evaluation
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Provide `DevMockGeminiClient` as a drop-in fallback when `GEMINI_API_KEY` is not present in `.env`.
- **Related files**: `Ticketing_Guidance_Module/backend/agent/mock_llm.py`, `Ticketing_Guidance_Module/backend/app.py`

---

### DEC-008 — Separation of LLM Reasoning from Deterministic Feasibility Engine
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: LLMs must NEVER perform authoritative time arithmetic, date offset calculation, or constraint verification from memory. All feasibility evaluations, station deadlines (`latest_acceptable_station_arrival = meeting_start - requested_buffer - last_mile_transit`), overnight date shifts, and ranking scores are executed in deterministic Python.
- **Rationale**: LLM arithmetic is prone to hallucination, subtle time subtraction errors, and double-subtraction. Deterministic code guarantees mathematical correctness and reproducible ranking.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/feasibility.py`, `Ticketing_Guidance_Module/backend/journey/ranking.py`

---

### DEC-009 — Strict Hard Constraints vs Soft Preferences
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Explicitly separate non-negotiable hard constraints (e.g. arrival deadline before meeting start, required buffer satisfaction) from soft preferences (e.g. preferred travel class, budget ceiling, preferred train).
- **Rationale**: A cheaper train or preferred train must NEVER be recommended as the best match if it violates the arrival deadline. Trains violating hard constraints are isolated in an "Infeasible / Does Not Meet Requirements" section with clear diagnostic explanations.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/models.py`, `Ticketing_Guidance_Module/backend/journey/feasibility.py`, `Ticketing_Guidance_Module/backend/journey/ranking.py`

---

### DEC-010 — Abstracted Location & Timetable Data Providers with Verified Data
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Abstract geocoding, station discovery, last-mile estimation, and train schedules behind service interfaces (`LocationResolutionService`, `TrainSearchService`) powered by verified data sources.
- **Rationale**: Prevents hardcoding fragile external scrapers while providing reliable, verified train schedules and geographic distances for major Indian corridors. Prohibits inventing synthetic data.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/location.py`, `Ticketing_Guidance_Module/backend/journey/timetable.py`

---

### DEC-011 — Official IRCTC Booking Handoff with Strict URL Allowlist
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: RailSathi acts strictly as a booking advisor. Booking is completed by handing off passengers to official IRCTC portal search links validated against an approved hostname allowlist (`www.irctc.co.in`, `enquiry.indianrail.gov.in`, `confirmtkt.com`).
- **Rationale**: Automated credential scraping or booking submission violates IRCTC terms and creates security liabilities. Allowlisting prevents malicious URL injection or phishing links.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/booking.py`

---

### DEC-012 — Dual-Mode React Frontend with Timeline Visualizer
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Provide a unified application interface featuring a dedicated "🎯 Goal Journey Planner" tab with journey timeline visualizers, candidate station badges, and one-click refiners alongside the "💬 Ticketing Guidance" chat.
- **Rationale**: Maximizes usability for passengers planning time-critical journeys while retaining instant access to ticketing rules.
- **Related files**: `Ticketing_Guidance_Module/frontend/src/App.jsx`, `Ticketing_Guidance_Module/frontend/src/App.css`

---

### DEC-013 — AWS Bedrock Converse Provider Pluggability
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Implement AWS Bedrock Converse API support (`backend/agent/bedrock.py`) alongside Google Gemini GenAI SDK, selectable via environment configuration (`LLM_PROVIDER=bedrock` vs `gemini`).
- **Rationale**: Enables enterprise multi-cloud deployment with AWS Claude 3.5 Sonnet / Haiku models while maintaining seamless local DevMock fallback.
- **Related files**: `Ticketing_Guidance_Module/backend/agent/bedrock.py`, `Ticketing_Guidance_Module/backend/config.py`

---

### DEC-014 — Per-IP Sliding-Window Rate Limiting
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Protect all incoming REST endpoints with an in-memory thread-safe sliding window rate limiter (`backend/rate_limiter.py`).
- **Rationale**: Defends against automated scraping, API resource exhaustion, and denial of service attacks without external Redis infrastructure overhead.
- **Related files**: `Ticketing_Guidance_Module/backend/rate_limiter.py`, `Ticketing_Guidance_Module/tests/test_rate_limiter.py`

---

### DEC-015 — Monorepo Module Namespace Restructuring
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Restructure application components under `Ticketing_Guidance_Module/` directory containing `backend/`, `frontend/`, and `tests/`.
- **Rationale**: Aligns module structure cleanly for subproject isolation within the broader RailSaathi system while maintaining centralized `.agent/` project memory.
- **Related files**: `Ticketing_Guidance_Module/*`, `.gitignore`

---

### DEC-016 — RailRadar API Client Adapter & Provider Interface
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Integrate RailRadar (`https://api.railradar.in`) behind an abstract `TrainDataProvider` interface with `RailRadarTrainDataProvider` and `MockTrainDataProvider` implementations.
- **Rationale**: Isolates external HTTP communication, authentication headers, error mapping (400, 401, 404, 429, 503), retries, and normalization from the deterministic journey feasibility and ranking engine. Retains deterministic mock provider for CI/CD and offline testing without risking credentials or quotas.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/railradar_client.py`, `Ticketing_Guidance_Module/backend/journey/timetable.py`

---

### DEC-017 — Bounded Candidate Fare Enrichment
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Train searches retrieve scheduled timetables without fan-out fare queries for all trains and classes. Only top shortlisted candidates (capped by `RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST = 5`) trigger journey-specific fare lookups for the passenger's requested class and quota (`GN`).
- **Rationale**: Prevents API quota exhaustion, reduces latency, and protects external request budgets while still providing exact fare calculations for the most promising travel options.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/timetable.py`, `Ticketing_Guidance_Module/backend/journey/planner.py`

---

### DEC-018 — Tiered In-Memory Caching for RailRadar
- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**: Implement a thread-safe tiered cache (`RailRadarCache`) with distinct TTLs: 24 hours for station lookups, 1 hour for train timetables, and 30 minutes for journey fares.
- **Rationale**: Minimizes duplicate queries for identical origin/destination/date pairs, improves response times, and respects data freshness rules without external database infrastructure.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/railradar_client.py`

