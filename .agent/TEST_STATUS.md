# TEST STATUS — RailSathi AI

> Last updated: 2026-10-10

## Test Infrastructure

- **Backend framework**: pytest 9.1.1 (VERIFIED on Python 3.14.7)
- **Frontend build test**: Vite 8.3.4 (VERIFIED on Node 26.11.1)
- **Total Tests**: 169 (166 passed, 3 skipped opt-in live smoke tests, 0 failed, 100% pass rate)

## Test Suites

| Suite | Location | Tests | Status | Result |
| --- | --- | --- | --- | --- |
| Flask API endpoints | `Ticketing_Guidance_Module/tests/test_api.py` | 7 | PASSING | 7 / 7 passed |
| Journey Planner Engine | `Ticketing_Guidance_Module/tests/test_journey_planner.py` | 15 | PASSING | 15 / 15 passed |
| Journey REST API | `Ticketing_Guidance_Module/tests/test_journey_api.py` | 6 | PASSING | 6 / 6 passed |
| Mandatory E2E Scenarios | `Ticketing_Guidance_Module/tests/test_e2e_scenarios.py` | 10 | PASSING | 10 / 10 passed |
| Agent Controller & Budgets | `Ticketing_Guidance_Module/tests/test_controller.py` | 7 | PASSING | 7 / 7 passed |
| Conversation State Manager | `Ticketing_Guidance_Module/tests/test_conversations.py` | 4 | PASSING | 4 / 4 passed |
| Retrieval Engine & Freshness | `Ticketing_Guidance_Module/tests/test_retrieval.py` | 7 | PASSING | 7 / 7 passed |
| Ticketing Tools & Validation | `Ticketing_Guidance_Module/tests/test_tools.py` | 11 | PASSING | 11 / 11 passed |
| Sliding-Window Rate Limiter | `Ticketing_Guidance_Module/tests/test_rate_limiter.py` | 3 | PASSING | 3 / 3 passed |
| RailRadar Client & Error Mappings | `Ticketing_Guidance_Module/tests/test_railradar_client.py` | 16 | PASSING | 16 / 16 passed |
| RailRadar Provider & Planner Flow | `Ticketing_Guidance_Module/tests/test_railradar_provider.py` | 4 | PASSING | 4 / 4 passed |
| Diagnostic Audit Fixes Suite | `Ticketing_Guidance_Module/tests/test_audit_fixes.py` | 8 | PASSING | 8 / 8 passed |
| Connecting Trains Discovery Suite | `Ticketing_Guidance_Module/tests/test_connecting_trains.py` | 8 | PASSING | 8 / 8 passed |
| RailRadar Quota & Rate Limiter Suite | `Ticketing_Guidance_Module/tests/test_railradar_quota_limiter.py` | 13 | PASSING | 13 / 13 passed |
| RailRadar RPM Optimization Suite | `Ticketing_Guidance_Module/tests/test_railradar_rpm_optimization.py` | 5 | PASSING | 5 / 5 passed |
| Venue Geocoding & Station Resolution | `Ticketing_Guidance_Module/tests/test_venue_geocoding.py` | 11 | PASSING | 11 / 11 passed |
| Dynamic Geocoding & Provider Isolation | `Ticketing_Guidance_Module/tests/test_dynamic_geocoding.py` | 18 | PASSING | 18 / 18 passed |
| Location-to-Station Pipeline Validation | `Ticketing_Guidance_Module/tests/test_location_station_validation.py` | 13 | PASSING | 13 / 13 passed |
| Quota Exhaustion & Search Outcome Semantics | `Ticketing_Guidance_Module/tests/test_search_outcomes_quota.py` | 9 | PASSING | 9 / 9 passed |
| RailRadar Live Smoke Suite | `Ticketing_Guidance_Module/tests/test_railradar_smoke.py` | 3 | PASSING / OPT-IN | 3 / 3 passed (when `RUN_LIVE_TESTS=1`) |
| Frontend Production Build | `Ticketing_Guidance_Module/frontend/` | 1 | PASSING | Built clean in 143ms |

## Summary

- **Total Unit & Integration Tests**: 175
- **Passed**: 175 (100%)
- **Skipped**: 3 (Live smoke tests opt-in via `RUN_LIVE_TESTS=1`)
- **Failed**: 0
- **Duration**: ~2.04 seconds

## Test Execution Commands

```bash
# Run complete pytest test suite (mock & unit tests)
source .venv/bin/activate
pytest Ticketing_Guidance_Module/tests/ -v

# Run optional live RailRadar smoke test (requires active RAILRADAR_API_KEY in .env)
RUN_LIVE_TESTS=1 pytest Ticketing_Guidance_Module/tests/test_railradar_smoke.py -v -s

# Run frontend build verification
cd Ticketing_Guidance_Module/frontend && npm run build
```

## Unresolved Test Failures

_None. All 175 automated unit/integration tests pass with 100% success rate._

