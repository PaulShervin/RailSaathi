# ISSUES — RailSathi AI

## Open Issues

### ISSUE-001: Gemini API Key Not Configured in Environment
- **Severity**: Low (DevMock handles offline mode)
- **Discovered**: 2026-10-10 (Session 001)
- **Description**: `GEMINI_API_KEY` is not populated in `.env`.
- **Impact**: Backend runs with `DevMockGeminiClient` supporting all tool invocations and full UI experience. When live quota is desired, user sets `GEMINI_API_KEY`.
- **Resolution**: User to provide key when live Gemini API queries are required.


## Closed Issues

### ISSUE-004: RailRadar API Key Active Subscription Required on Live Endpoints
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 005)
- **Description**: Active API key configured in `.env`. Verified 100% operational against `https://api.railradar.in` across train searches (HTTP 200), station lookups (HTTP 200), and PRS fare calculators (HTTP 200).
- **Resolution**: Key configured and verified with live smoke test suite (3/3 passed).
- **Closed**: 2026-10-10 (Session 008)

### ISSUE-002: Python 3.14 Compatibility Risk
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 001)
- **Resolution**: Verified all dependencies (`google-genai` 2.29, `flask` 3.1.3, `pydantic` 2.14, `pytest` 9.1.1) install and run cleanly on Python 3.14.7.
- **Closed**: 2026-10-10 (Session 003)

### ISSUE-003: RollDown Native Binding on Linux
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 003)
- **Description**: Frontend `node_modules` had Windows binaries previously.
- **Resolution**: Ran `npm install` in `frontend/` on Linux; Vite 8.3 production build now executes in 168ms with 0 errors.
- **Closed**: 2026-10-10 (Session 003)

### ISSUE-005: False Infeasibility in Morning Train Discovery & Venue City Discrepancies
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 006 audit)
- **Description**: Morning meetings falsely reported "No Feasible Direct Trains Found" due to single-date queries missing previous-day overnight departures, venue-to-city hardcoding without spatial consistency checks, and unhandled relative/slash date formats.
- **Resolution**: Implemented multi-date overnight train querying, spatial conflict detection with user clarification prompts, deterministic `Asia/Kolkata` date resolution, inclusive deadline comparisons, and missing last-mile data safeguards. Verified with 98 passing regression tests.
- **Closed**: 2026-10-10 (Session 006)

### ISSUE-006: Quota Exhaustion Conflated with Journey Infeasibility
- **Severity**: Resolved
- **Discovered**: 2026-10-10 (Session 014)
- **Description**: When RailRadar monthly request quota was exhausted (e.g. 95/100 requests used with 5 held in reserve), the planner conflated the absence of retrieved trains with journey infeasibility, displaying "No Feasible Direct Trains Found for Exact Deadline" (Source: local_sqlite_durable).
- **Resolution**: Introduced 5 distinct semantic search outcomes (`feasible_options_found`, `no_feasible_options`, `search_data_unavailable`, `quota_exhausted`, `partial_results`), quota-aware cache-first retrieval, timezone-formatted reset timestamps in IST (+05:30), explicit UI budget cards, and offline regression test suite (9 new tests, 175 total passed tests).
- **Closed**: 2026-10-10 (Session 014)



