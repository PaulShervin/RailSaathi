# TEST STATUS — RailSathi AI

> Last updated: 2026-10-10

## Test Infrastructure

- **Backend framework**: pytest 9.1.1 (VERIFIED on Python 3.14.7)
- **Frontend build test**: Vite 8.3.4 (VERIFIED on Node 26.11.1)
- **Total Tests**: 93 (90 passed, 3 skipped live smoke tests, 0 failed, 100% pass rate)

## Test Suites

| Suite | Location | Tests | Status | Result |
|---|---|---|---|---|
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
| RailRadar Live Smoke Suite | `Ticketing_Guidance_Module/tests/test_railradar_smoke.py` | 3 | SKIPPED | Requires `RAILRADAR_API_KEY` |
| Frontend Production Build | `Ticketing_Guidance_Module/frontend/` | 1 | PASSING | Built clean in 156ms |

## Summary

- **Total Unit & Integration Tests**: 90
- **Passed**: 90 (100%)
- **Skipped**: 3 (Live smoke tests waiting for user key)
- **Failed**: 0
- **Duration**: ~0.37 seconds

## Test Execution Commands

```bash
# Run complete pytest test suite (mock & unit tests)
source .venv/bin/activate
pytest Ticketing_Guidance_Module/tests/ -v

# Run optional live RailRadar smoke test (requires RAILRADAR_API_KEY in .env)
RAILRADAR_API_KEY=your_key_here pytest Ticketing_Guidance_Module/tests/test_railradar_smoke.py -v -s

# Run frontend build verification
cd Ticketing_Guidance_Module/frontend && npm run build
```

## Unresolved Test Failures

_None. All 90 automated tests pass._
