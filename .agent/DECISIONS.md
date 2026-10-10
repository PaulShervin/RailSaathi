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

---

### DEC-019 — Deterministic Date Resolution, Spatial Conflict Detection, and Overnight Journey Discovery

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. Enforce `Asia/Kolkata` as the standard timezone context, dynamically injecting current reference time into LLM prompts and resolving relative keywords ("today", "tomorrow", weekdays, slash formats) deterministically in Python.
  2. Implement spatial conflict detection between venue's verified city and user-provided destination city (> 50 km triggers `status: "clarification_required"` rather than silent routing to the wrong city).
  3. Expand `STATION_REGISTRY` and `CITY_CENTROIDS` with key South and North Indian railway hubs (TEN, MDU, TPJ, CBE, SA, TVC, ERS, PUNE, ADI, JP, etc.).
  4. Implement multi-date schedule discovery for morning meetings ($\le 13:00$), automatically searching previous-day departures (`meeting_date - 1 day`) to discover viable overnight trains.
- **Rationale**: Prevents false-negative infeasibility reports, eliminates timezone-shift bugs, and protects passengers from cross-city geocoding errors.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/location.py`, `Ticketing_Guidance_Module/backend/journey/planner.py`, `Ticketing_Guidance_Module/backend/journey/feasibility.py`, `Ticketing_Guidance_Module/backend/agent/llm.py`, `Ticketing_Guidance_Module/tests/test_audit_fixes.py`

---

### DEC-020 — Connecting Trains & Multi-Leg Journey Planning Engine

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. Implement `ConnectingTrainDiscoveryService` to discover 1-transfer connecting train itineraries via verified railway interchange junctions (e.g. `TPJ`, `MDU`, `KPD`, `SA`, `ED`, `BZA`, `SC`, `PUNE`, `CNB`, `BPL`, `AGC`, `GTL`, `RU`).
  2. Enforce strict layover feasibility constraints: minimum transfer buffer ($\ge 30$ mins) and maximum connection window ($\le 6$ hours).
  3. Evaluate multi-leg arrival feasibility against passenger meeting deadlines and last-mile travel, computing combined journey duration, estimated fares, and dual IRCTC booking handoff links.
  4. Render rich connecting route cards in the frontend with interactive booking links for each leg.
- **Rationale**: Provides viable railway alternatives when direct trains are sold out, infrequent, or do not satisfy morning arrival deadlines.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/connecting.py`, `Ticketing_Guidance_Module/backend/journey/models.py`, `Ticketing_Guidance_Module/backend/journey/planner.py`, `Ticketing_Guidance_Module/frontend/src/App.jsx`, `Ticketing_Guidance_Module/tests/test_connecting_trains.py`

---

### DEC-021 — RailRadar Monthly Quota, Durable SQLite Persistence, Sliding-Window Rate Limiting, and 8-Stage Execution Controller

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. **Monthly Quota Enforcement**: Configurable 100 requests hard cap (`RAILRADAR_MONTHLY_QUOTA=100`) persisted across process restarts via SQLite (`backend/data/railradar_usage.sqlite`) in WAL mode. Outbound attempts (including retries and failed attempts) are counted conservatively. A configurable reserve (`RAILRADAR_QUOTA_RESERVE=5`) is held for emergency/recovery queries. Supports authoritative provider dashboard reconciliation.
  2. **Sliding-Window Rate Limiting**: Algorithmic per-minute limiter (`RAILRADAR_RATE_LIMIT_PER_MINUTE=10`) with `Retry-After` header tracking, bounded exponential backoff with full jitter on eligible retries, and non-retrying of deterministic 400/401/403/404 failures.
  3. **Centralized 8-Stage Execution Controller**:
     1. Validate & normalize operation.
     2. Check cache & deduplicate identical in-flight requests (SingleFlight lock).
     3. Check monthly quota.
     4. Acquire permission from per-minute limiter.
     5. Recheck monthly quota immediately before dispatch.
     6. Record attempt durably in SQLite with atomic reservation.
     7. Send HTTP request.
     8. Record outcome and sanitized diagnostics.
  4. **Cost-Aware Journey Planning**: Prioritize single schedule search + local filtering over redundant calls, enrich fares only for shortlisted candidates, only search connecting routes when direct options cannot meet hard constraints, and emit structured `monthly_quota_exhausted` and `rate_limit_wait` payloads.
- **Rationale**: Prevents unexpected monthly quota overages, guarantees crash-resilient accounting, eliminates race conditions under concurrent workers, and protects user request latency.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/quota.py`, `Ticketing_Guidance_Module/backend/journey/railradar_client.py`, `Ticketing_Guidance_Module/backend/journey/planner.py`, `Ticketing_Guidance_Module/tests/test_railradar_quota_limiter.py`

---

### DEC-022 — RailRadar RPM Optimization, Bounded Candidate Fare Lookups, and Virtual-Clock Rate Limit Testing

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. **Top-3 Feasible Fare Enrichment**: Strictly cap fare lookups to the top 3 feasible candidate trains (`RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST = 3`). Infeasible trains are never enriched when feasible candidates exist.
  2. **Suburban Stop Pair Pruning**: If the primary terminal pair search yields $\ge 4$ candidate train services, prune redundant suburban stop searches (e.g. `TBM->TEN`, `PER->TEN`) representing intermediate stops of the same train run.
  3. **Injected Virtual Clock for Rate Limiting**: Support `clock_fn` and `sleep_fn` in `RailRadarPerMinuteLimiter` enabling instant simulated-clock stress testing of sliding window invariants ($N \le \text{limit}$ in any rolling 60-second window) without real-time delays.
- **Rationale**: Reduces outbound RailRadar HTTP calls by $>50\%$ per journey planning session while preserving 100% accurate feasibility and fare data.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/timetable.py`, `Ticketing_Guidance_Module/backend/journey/quota.py`, `Ticketing_Guidance_Module/backend/journey/railradar_client.py`, `Ticketing_Guidance_Module/tests/test_railradar_rpm_optimization.py`

---

### DEC-023 — Multi-Branch Venue Disambiguation, Station Classification, SQLite Geocoding Cache, and Deterministic Last-Mile Urban Routing

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. **Multi-Branch Venue Disambiguation**: Resolved venues with multiple branches across Tamil Nadu/India (e.g., TIDEL Park Taramani vs Pattabiram vs Coimbatore vs Madurai vs Trichy) into distinct coordinate records. Ambiguous queries lacking city/locality context return `requires_user_clarification=True` with candidate options and low confidence (0.40).
  2. **Zero City-Centroid Hallucination**: Unverified venues are never silently substituted with dummy or city-centroid coordinates (`latitude=None`, `longitude=None`, `confidence=0.0`).
  3. **Railway Station Classification & Intercity Filtering**: Station registry classified with `station_type` (`major_intercity_terminal`, `intercity_junction`, `intercity_halt`, `suburban_halt`, `metro`) and `supports_intercity=True/False`. Intercity journey discovery automatically filters out MRTS/metro-only halts (e.g. `TYMR`, `KTBR`) while retaining long-distance terminals (`MAS`, `MS`, `TBM`).
  4. **Optimal vs Nearest Terminal Selection**: A farther terminal (e.g. `MAS`/`MS` vs `TBM`) can be recommended as the best match if it offers direct trains or earlier arrivals meeting the passenger's deadline.
  5. **Deterministic Urban Traffic Routing Model**: Computes realistic driving distances with a road detour ratio of 1.30 over Haversine distance, and travel time modeled at urban speed (22 km/h) plus an 8-minute taxi dispatch/station exit buffer. Unknown last mile is never treated as zero.
  6. **Durable SQLite Geocoding & Routing Cache**: `LocationCacheManager` durably stores place lookups and computed routes in SQLite (`data/location_cache.sqlite`) in WAL mode, architecturally separated from RailRadar (0 RailRadar requests consumed).
- **Rationale**: Eliminates false spatial assignments, prevents routing intercity trains to suburban halts, accurately reflects urban travel latency in meeting deadlines, and preserves RailRadar quota budget.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/location.py`, `Ticketing_Guidance_Module/backend/journey/models.py`, `Ticketing_Guidance_Module/backend/journey/planner.py`, `Ticketing_Guidance_Module/backend/journey/ranking.py`, `Ticketing_Guidance_Module/tests/test_venue_geocoding.py`

---

### DEC-024 — Dynamic LLM-Assisted Venue Geocoding, Provider Abstraction, Locality Validation & Routing Isolation

- **Date**: 2026-10-10
- **Status**: ACCEPTED
- **Decision**:
  1. **Geocoding Provider Abstraction (`GeocodingProvider`)**: Standard protocol resolving arbitrary real-world venues into normalized `GeocodedPlaceCandidate` models (`place_name`, `formatted_address`, `latitude`, `longitude`, `city`, `state`, `country`, `provider`, `provider_place_id`, `confidence`, `retrieved_at`).
  2. **Provider Implementations**:
     - `OSMNominatimGeocodingProvider`: Live OpenStreetMap Nominatim adapter adhering to OSM usage policies (custom User-Agent `RailSathi-AI/1.0`, strict atomic 1.0s interval rate limiter, structured error handling).
     - `VerifiedRegistryGeocodingProvider`: Authoritative local registry fallback.
     - `MockGeocodingProvider`: Injected fixture mock for offline testing without network access.
  3. **Zero Hallucinated Coordinates Policy**: LLMs extract intent (`destination_venue`, `destination_city`, `meeting_time`, `meeting_date`); Python invokes configured geocoders and executes deterministic spatial validation. If a venue is unknown or coordinates are invalid/missing, coordinates remain `None`, `confidence=0.0`, and clarification is requested.
  4. **Deterministic Locality Consistency & Ambiguity Validation**:
     - Locality checks reject cross-city mismatches (e.g. Pune vs Chennai).
     - Multi-branch ambiguous queries emit structured options with interactive UI chips.
  5. **Routing Provider Abstraction (`RoutingProvider`)**:
     - Separates provider-derived routes (`source_type='routing_provider'`) from heuristic models (`source_type='heuristic_urban_model'`).
     - `DeterministicUrbanRoutingModel` implements a 1.30x detour factor and 22 km/h traffic buffer, explicitly labeled as heuristic.
     - Unavailable last-mile durations are returned as `None`, never substituted with zero.
  6. **Zero RailRadar Quota Ingress**: Geocoding and routing operate with 100% architectural isolation from RailRadar quotas and rate limiters.
- **Rationale**: Enables RailSathi AI to resolve previously unseen real-world venues dynamically while preventing coordinate hallucination and protecting RailRadar API budgets.
- **Related files**: `Ticketing_Guidance_Module/backend/journey/geocoding.py`, `Ticketing_Guidance_Module/backend/journey/routing.py`, `Ticketing_Guidance_Module/backend/journey/location.py`, `Ticketing_Guidance_Module/backend/tools/journey_tools.py`, `Ticketing_Guidance_Module/tests/test_dynamic_geocoding.py`
