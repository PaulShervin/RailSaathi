# TASKS — RailSathi AI

## Completed Tasks

### TASK-001 to TASK-011: Ticketing Guidance Bootstrap & Test Suite

- **Status**: COMPLETED
- **Description**: SQLite FTS5 database, deterministic agent controller, Gemini SDK + DevMock client, 5 ticketing tools, source freshness scoring, React chat UI, and 36 baseline pytest tests.
- **Completed**: 2026-10-10

### TASK-012: Journey Data Models & Typed Schemas

- **Status**: COMPLETED
- **Description**: Implemented Pydantic models in `backend/journey/models.py` (`TripRequirements`, `ResolvedLocation`, `StationCandidate`, `LastMileEstimate`, `TrainService`, `JourneyEvaluation`, `BookingHandoff`, `JourneyPlanResponse`).
- **Completed**: 2026-10-10

### TASK-013: Location Resolution & Last-Mile Transit Engine

- **Status**: COMPLETED
- **Description**: Implemented `LocationResolutionService` in `backend/journey/location.py` with verified landmark registry (Tidel Park, IIT Madras, BKC, HITEC City, etc.), railway station hub finder (MAS, MS, SBC, YPR, NDLS, CSMT, etc.), Haversine geodesics, and urban traffic transfer modeling.
- **Completed**: 2026-10-10

### TASK-014: Authoritative Train Timetable & Fare Service

- **Status**: COMPLETED
- **Description**: Implemented `TrainSearchService` in `backend/journey/timetable.py` containing verified schedules, stops, days of run, classes, and fare structures across major corridors.
- **Completed**: 2026-10-10

### TASK-015: Deterministic Feasibility & Deadline Calculator

- **Status**: COMPLETED
- **Description**: Implemented `JourneyFeasibilityEvaluator` in `backend/journey/feasibility.py` using formula `latest_acceptable_station_arrival = meeting_start - requested_buffer - last_mile_duration`, overnight date shifts (`day_offset = 1/2`), and hard constraint validation without double subtraction.
- **Completed**: 2026-10-10

### TASK-016: Recommendation Ranking & Trade-off Engine

- **Status**: COMPLETED
- **Description**: Implemented `JourneyRankingEngine` in `backend/journey/ranking.py` with transparent scoring prioritizing deadline safety, preferred train matches, class matches, and duration. Isolates infeasible options with diagnostic breach explanations.
- **Completed**: 2026-10-10

### TASK-017: Booking Handoff Service with URL Allowlisting

- **Status**: COMPLETED
- **Description**: Implemented `BookingHandoffService` in `backend/journey/booking.py` with strict domain allowlisting (`irctc.co.in`, `enquiry.indianrail.gov.in`, `confirmtkt.com`). Rejects unapproved or insecure URLs.
- **Completed**: 2026-10-10

### TASK-018: Unified Tool Registry & Agent Function Calling

- **Status**: COMPLETED
- **Description**: Unified all 13 tools in `backend/tools/registry.py` and `backend/tools/journey_tools.py`, updated `AgentController`, `GeminiClient`, and `DevMockGeminiClient` with goal-based journey planning dispatch and evidence synthesis.
- **Completed**: 2026-10-10

### TASK-019: Journey REST API Endpoints

- **Status**: COMPLETED
- **Description**: Added `POST /api/journey/plan`, `POST /api/journey/refine`, `GET /api/journey/options/<request_id>` to `backend/app.py`.
- **Completed**: 2026-10-10

### TASK-020: Dual-Mode Frontend UI & Comprehensive Test Suite

- **Status**: COMPLETED
- **Description**: Built Goal-Based Journey Planner React view with timeline step visualizer, best match card, alternatives, and one-click refiners. Created 67 automated tests covering all 10 mandatory evaluation scenarios. All 67 tests pass.
- **Completed**: 2026-10-10

### TASK-021: AWS Bedrock Converse Provider

- **Status**: COMPLETED
- **Description**: Implemented `BedrockClient` in `backend/agent/bedrock.py` using Amazon Bedrock Converse API with streaming, tool calling, and fallback support.
- **Completed**: 2026-10-10

### TASK-022: Per-IP Sliding-Window Rate Limiter

- **Status**: COMPLETED
- **Description**: Implemented `RateLimiter` in `backend/rate_limiter.py` with thread-safe sliding-window queues per client IP and 3 new test cases in `tests/test_rate_limiter.py` (total test suite = 70 tests).
- **Completed**: 2026-10-10

### TASK-023: Static Bundle Hosting & Universal CORS

- **Status**: COMPLETED
- **Description**: Configured Flask `backend/app.py` to serve built frontend static files from `frontend/dist/` and handle CORS for cross-origin environments.
- **Completed**: 2026-10-10

### TASK-024: Namespace Restructuring to Ticketing_Guidance_Module

- **Status**: COMPLETED
- **Description**: Restructured `backend/`, `frontend/`, and `tests/` into `Ticketing_Guidance_Module/`, updated `.gitignore`, and verified all 70 tests execute and pass cleanly.
- **Completed**: 2026-10-10

### TASK-025: RailRadar API Client Adapter Implementation

- **Status**: COMPLETED
- **Description**: Implemented `RailRadarClient` (`backend/journey/railradar_client.py`) covering `/v1/trains/between/{from}/{to}`, `/v1/lookup/search/stations`, and `/v1/trains/{number}/fare` with Bearer auth, secret redaction in logs/errors, bounded retries with backoff, HTTP error mappings (400, 401, 404, 429 with Retry-After, 503), metrics tracking, and tiered in-memory caching.
- **Completed**: 2026-10-10

### TASK-026: TrainDataProvider Interface & RailRadar Normalization

- **Status**: COMPLETED
- **Description**: Created abstract `TrainDataProvider` base class with `RailRadarTrainDataProvider` and `MockTrainDataProvider` in `backend/journey/timetable.py`. Normalizes train types, running days, day offsets (`day_offset = 1/2`), duration parsing, class allocations, and fare quotes (`FareQuote`, `FareBreakdown`).
- **Completed**: 2026-10-10

### TASK-027: Bounded Candidate Fare Enrichment & Station Search Endpoint

- **Status**: COMPLETED
- **Description**: Connected fare enrichment in `TrainSearchService` and `JourneyPlanner` to fetch live fares for top candidate trains (capped by `RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST = 5`) for passenger's requested class. Added `GET /api/stations/search` endpoint and updated health check.
- **Completed**: 2026-10-10

### TASK-028: Comprehensive Unit, Integration & Live Smoke Test Suite

- **Status**: COMPLETED
- **Description**: Added 20 new tests in `test_railradar_client.py` and `test_railradar_provider.py` covering normalization, error mappings, caching, rate limit handling, and regression verification (total 90 passed tests). Added standalone live smoke test suite `test_railradar_smoke.py`.
- **Completed**: 2026-10-10

### TASK-029: Diagnostic Audit Fixes — Date Resolution, Spatial Conflicts, Hub Discovery & Overnight Feasibility

- **Status**: COMPLETED
- **Description**: Implemented deterministic date parser in `Asia/Kolkata` supporting relative dates ("today", "tomorrow", weekdays, slash formats), injected dynamic date/time context into LLM system instructions, added spatial conflict detection between venue and destination city (>50km triggers clarification), expanded station registry with key hubs (TEN, MDU, TPJ, CBE, SA, TVC, ERS, PUNE, ADI, JP), enabled multi-date overnight schedule searches for morning meetings, and added test suite `test_audit_fixes.py` (98/98 tests passing).
- **Completed**: 2026-10-10

### TASK-030: Connecting Trains & Multi-Leg Journey Planning Engine

- **Status**: COMPLETED
- **Description**: Implemented `ConnectingTrainDiscoveryService` with corridor hub matching (`TPJ`, `MDU`, `KPD`, `SA`, `ED`, `BZA`, etc.), layover constraints (30m to 6h), dual-leg feasibility evaluation against meeting deadlines, models in `models.py`, frontend UI in `App.jsx` with dual IRCTC booking links and transfer layover timelines, and unit/integration tests in `test_connecting_trains.py` (101/101 passing).
- **Completed**: 2026-10-10

### TASK-031: Live Data Readiness & Connecting-Journey Integration Audit

- **Status**: COMPLETED
- **Description**: Audited RailRadar authentication headers and endpoints, verified environment loading, inspected sanitized provider 401 error payloads, updated connecting-train discovery with running days check, allowlisted booking handoffs, safe non-invented combined fares, and provider failure isolation without silent mock fallback. Added 8 new unit/integration tests (total 106 passed tests).
- **Completed**: 2026-10-10

### TASK-032: RailRadar Monthly Quota, Rate Limiting & 8-Stage Controller Architecture

- **Status**: COMPLETED
- **Description**: Implemented `DurableRailRadarQuotaManager` with SQLite persistence across application restarts, atomic reservation transactions, configurable 100 requests hard cap and 5 reserve, provider reset policy, and dashboard reconciliation. Implemented sliding-window `RailRadarPerMinuteLimiter` respecting `Retry-After` headers and bounded jittered backoff. Implemented `SingleFlightDeduplicator` and centralized 8-stage execution controller in `RailRadarClient`. Integrated cost-aware budgeting in `JourneyPlanner`. Added test suite `test_railradar_quota_limiter.py` (122 total tests, 100% passing).
- **Completed**: 2026-10-10

### TASK-033: RailRadar RPM Optimization, Request Efficiency Audit & Simulated Stress Test

- **Status**: COMPLETED
- **Description**: Optimized candidate fare enrichment to strictly fetch fares for top 3 feasible candidates (or fewer if fewer qualify), reduced suburban station pair fan-out when primary terminal queries yield ample trains, enhanced `RailRadarPerMinuteLimiter` with injected virtual clock support, built simulated-clock RPM stress test (20 requests with 5 RPM limit verifying sliding window invariants) and cache stress test (20 rapid queries -> 0 network calls). Added test suite `test_railradar_rpm_optimization.py` (127 total tests, 100% passing).
- **Completed**: 2026-10-10

### TASK-034: Venue Geocoding, Disambiguation & Station Resolution Pipeline

- **Status**: COMPLETED
- **Description**: Audited and revamped location resolution pipeline: implemented multi-branch venue disambiguation (distinguishing Tidel Park Taramani vs Pattabiram vs Coimbatore vs Madurai), unambiguous clarification prompt generation for multi-location venues, station classification into intercity terminals vs junctions vs suburban/MRTS stops with intercity filtering, deterministic urban traffic routing model with Haversine road detour factor (1.30) and traffic buffer, durable SQLite caching for geocoding and routing (`LocationCacheManager`), and total isolation from RailRadar API quota (0 RailRadar requests consumed). Added test suite `test_venue_geocoding.py` (135 passing tests, 0 failures).
- **Completed**: 2026-10-10

### TASK-035: Dynamic LLM-Assisted Venue Geocoding, Provider Abstractions, Station Resolution & Routing Pipeline

- **Status**: COMPLETED
- **Description**: Upgraded location resolution architecture to resolve arbitrary real-world venues dynamically: implemented `GeocodingProvider` protocol with `OSMNominatimGeocodingProvider` (OpenStreetMap Nominatim with custom User-Agent, strict 1.0s atomic rate limiter, and structured error handling), `VerifiedRegistryGeocodingProvider`, and `MockGeocodingProvider`. Implemented `RoutingProvider` protocol with `DeterministicUrbanRoutingModel` and `MockRoutingProvider`. Implemented Stages A-E (intent normalization $\rightarrow$ SQLite persistent caching with TTL $\rightarrow$ station lookup $\rightarrow$ dynamic geocoding $\rightarrow$ coordinate and locality consistency validation $\rightarrow$ multi-branch ambiguity handling with interactive UI chips $\rightarrow$ persistent caching). Exposed `resolve_venue` tool for LLM orchestration. Added comprehensive 18-test offline suite `test_dynamic_geocoding.py` verifying all edge cases, zero coordinate hallucination, and 0 RailRadar API calls consumed (153 passed unit/integration tests, 3 skipped live smoke tests, 100% pass rate).
- **Completed**: 2026-10-10

### TASK-036: Location-to-Station Pipeline Validation with Tidel Park Live Fixture

- **Status**: COMPLETED
- **Description**: Validated end-to-end pipeline from resolved venue coordinates (Tidel Park Nominatim live fixture: `12.9893849, 80.2508691`) to railway station discovery, last-mile travel calculations, and meeting deadline feasibility. Verified Haversine distance accuracy against independent geometric math (Egmore ~10.1km, Central ~10.7km, Tambaram ~15.1km), excluded non-intercity MRTS stops (TYMR, KTBR) from long-distance searches, distinguished nearest terminal from best train service station, confirmed unknown last-mile transit remains `None` (not 0) and cannot produce a false feasible journey, and verified cache reuse with 0 extra calls. Added 13 new offline tests in `test_location_station_validation.py` (total 166 passed unit/integration tests, 100% pass rate).
- **Completed**: 2026-10-10

### TASK-037: Fix Quota Exhaustion Semantics, Search Outcomes & UI Differentiation

- **Status**: COMPLETED
- **Description**: Diagnosed and resolved false "No Feasible Direct Trains Found" search error on quota exhaustion. Separated search outcomes into 5 distinct semantic states (`feasible_options_found`, `no_feasible_options`, `search_data_unavailable`, `quota_exhausted`, `partial_results`). Introduced `QuotaInfo` typed model, formatted reset timestamp in `Asia/Kolkata` IST (+05:30), quota-aware cache-first retrieval in `TrainSearchService`, guarded fare enrichment, frontend quota-exhausted and data-unavailable cards, cached evaluation indicators, quick-refine idempotency and cache re-evaluation without false quota restoration. Added 9 offline regression tests in `test_search_outcomes_quota.py` (175 passed unit/integration tests, 3 skipped live smoke tests, 100% pass rate).
- **Completed**: 2026-10-10

