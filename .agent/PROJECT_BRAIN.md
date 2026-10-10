# PROJECT BRAIN — RailSathi AI

> Last updated: 2026-10-10

## Project Identity

**RailSathi AI** — Intelligent Indian Railways Goal-Based Train Journey Planner & Ticketing Guidance System.

A tool-using GenAI application that interprets passenger goals (meetings, exams, interviews, appointments), resolves real-world destination venues to railway hubs, deterministically calculates latest acceptable station arrivals, accounts for last-mile transit and required arrival buffers, ranks feasible train options, diagnoses infeasibility, and generates safe official IRCTC booking handoffs.

Powered by a dual-provider train data architecture:
1. **Live RailRadar API Integration** (`https://api.railradar.in`): Real scheduled train timetables, multi-station corridor searches, and journey-specific fare calculator with granular charge breakdowns (`FareBreakdown`).
2. **Verified Mock Data Provider**: Deterministic local database for CI/CD and offline evaluation.

The AI guides passengers — it does not impersonate railway authorities or perform actual booking transactions.

## Product Scope

1. **Goal-Based Train Journey Planning**:
   - Extracting structured trip goals (origin, destination venue, date, meeting time, arrival buffer, preferred train, class, budget).
   - Resolving venue addresses to geographic coordinates and discovering candidate arrival/departure railway hubs.
   - Deterministic last-mile transfer calculation (distance & duration via urban traffic model / Haversine).
   - Live RailRadar train search (`/v1/trains/between/{from}/{to}`) and fare calculations (`/v1/trains/{number}/fare`).
   - Deterministic deadline formula: `latest_acceptable_station_arrival = meeting_start - requested_buffer - estimated_last_mile_duration`.
   - Overnight journey and date offset handling (`day_offset = 1` or `2`).
   - Strict constraint filtering (hard constraints vs soft preferences).
   - Transparent scoring and ranking (best feasible match vs feasible alternatives vs infeasible options).
   - Bounded candidate fare enrichment (capped by `RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST = 5`).
   - Security-allowlisted official IRCTC booking handoff.
2. **AI Ticketing Guidance Module**:
   - Explaining ticket classes (SL, 3A, 2A, 1A, CC, 3E, 2S, etc.).
   - Explaining reservation terminology (CNF, RAC, WL, GNWL, RLWL, PQWL).
   - Official booking procedures (IRCTC online vs station counter).
   - Cancellation and refund policies.
   - Source-backed explanations with URLs and verification timestamps.

See [CONSTRAINTS.md](./CONSTRAINTS.md) for explicit exclusions.

## Confirmed Technology Stack

| Layer | Technology | Status |
|---|---|---|
| Frontend | React + Vite + Vanilla CSS & Tailwind styling (`Ticketing_Guidance_Module/frontend/`) | VERIFIED |
| Backend | Python 3.14 + Flask 3.1 + Pydantic 2.14 (`Ticketing_Guidance_Module/backend/`) | VERIFIED |
| Train Data Providers | RailRadar API (`api.railradar.in`) + Mock Data Provider (`Ticketing_Guidance_Module/backend/journey/`) | VERIFIED |
| LLM Providers | Gemini SDK (`google-genai` 2.29) + AWS Bedrock Converse (`boto3`) + `DevMockGeminiClient` | VERIFIED |
| Agent Controller | Deterministic Python, Tool Registry, Budget & Trace Tracking | VERIFIED |
| Journey Engine | Deterministic Feasibility & Deadline Calculator, Ranking Engine | VERIFIED |
| Security | Per-IP Sliding-Window Rate Limiter & URL Domain Allowlist | VERIFIED |
| Geo & Timetables | Verified Hub & Venue Registry + RailRadar Live Timetables | VERIFIED |
| Testing | Pytest 9.1.1 (90 unit/integration tests passing, 3 live smoke tests) | VERIFIED |

## Implemented Modules (Under `Ticketing_Guidance_Module/`)

1. `backend/journey/models.py`: Typed Pydantic data models for TripRequirements, StationCandidates, TrainServices, FareQuotes, FareBreakdowns, JourneyEvaluations, and BookingHandoffs.
2. `backend/journey/railradar_client.py`: Resilient HTTP client adapter for RailRadar with Bearer auth, secret redaction, bounded retries, rate limit awareness, error mapping, and tiered in-memory caching.
3. `backend/journey/timetable.py`: `TrainDataProvider` abstraction with `RailRadarTrainDataProvider`, `MockTrainDataProvider`, and `TrainSearchService` with bounded candidate fare enrichment.
4. `backend/journey/location.py`: Geocoding, venue resolver, candidate station finder, and last-mile transit estimator.
5. `backend/journey/feasibility.py`: Deterministic deadline calculations, arrival buffers, overnight date shifts, and hard constraint validation.
6. `backend/journey/ranking.py`: Recommendation ranking engine and trade-off synthesizer.
7. `backend/journey/booking.py`: Official booking handoff service with domain allowlisting (`irctc.co.in`, `enquiry.indianrail.gov.in`, `confirmtkt.com`).
8. `backend/journey/planner.py`: Pipeline orchestrator and natural language requirement parser with Step 4.5 live fare enrichment.
9. `backend/agent/bedrock.py`: AWS Bedrock Converse provider with streaming and function tool calling.
10. `backend/rate_limiter.py`: In-memory thread-safe sliding window rate limiter.
11. `backend/tools/journey_tools.py` & `backend/tools/registry.py`: Unified tool declarations and execution dispatcher.
12. `backend/app.py`: REST endpoints (`POST /api/journey/plan`, `POST /api/journey/refine`, `GET /api/journey/options/<id>`, `GET /api/stations/search`, `POST /api/chat`, `GET /api/health`, static serving).
13. `frontend/src/App.jsx` & `frontend/src/App.css`: Dual-tabbed UI with Goal Planner timeline visualizer, overnight indicators, fare quotas, data source badges, alternatives, and ticketing chat.

## Critical Constraints

- No actual ticket purchasing, automated login, or payment submissions.
- No synthetic live seat availability presented as real-time confirmed data without authorized live integration.
- Deterministic Python is the authoritative engine for time calculations and constraints; LLM interprets and explains.
- Booking links restricted strictly to allowlisted official domains.
- See [CONSTRAINTS.md](./CONSTRAINTS.md) for complete details.

## Detailed Files

- [ARCHITECTURE.md](./ARCHITECTURE.md) — System architecture & data flow
- [DECISIONS.md](./DECISIONS.md) — Architecture and implementation decisions
- [CONSTRAINTS.md](./CONSTRAINTS.md) — Non-negotiable system rules
- [TASKS.md](./TASKS.md) — Tracked tasks and milestones
- [ISSUES.md](./ISSUES.md) — Known issues and future roadmap
- [TEST_STATUS.md](./TEST_STATUS.md) — Complete automated test report (90 unit/integration tests)
- [diagrams/DATA_FLOW.md](./diagrams/DATA_FLOW.md) — Request lifecycle diagram
- [diagrams/PROJECT_TREE.md](./diagrams/PROJECT_TREE.md) — Project file tree
- [sessions/SESSION_INDEX.md](./sessions/SESSION_INDEX.md) — Session index
