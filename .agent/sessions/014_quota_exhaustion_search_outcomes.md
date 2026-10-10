# Session 014: Fix Quota Exhaustion and Search Outcome Semantics

**Date**: 2026-10-10  
**Status**: Completed  
**Branch**: `Ticketing-Guidance-Module`

## Objective
Diagnose and resolve the search failure where quota exhaustion (95/100 requests used) falsely displayed "No Feasible Direct Trains Found for Exact Deadline". Disentangle true journey infeasibility from quota exhaustion and provider errors, introduce 5 distinct semantic search outcomes, implement quota-aware cache-first retrieval, format reset timestamps in `Asia/Kolkata` IST (+05:30), improve the UI, and verify all 9 regression requirements under 100% offline test constraints.

## Root Cause Analysis
1. **Flawed Fallback in `planner.py`**:
   - When RailRadar quota was exhausted, `TrainSearchService.search_trains` previously raised or trapped errors that flowed into the empty train fallback.
   - The empty train fallback unconditionally set `status = "no_feasible_journey"`, emitting the user-facing message: `"No Feasible Direct Trains Found for Exact Deadline"`.
   - This erroneously conflated provider quota exhaustion with confirmed mathematical infeasibility.
2. **Missing Outcome Distinction**:
   - The application only had a binary notion of feasible vs. infeasible, conflating 5 distinct states:
     - `feasible_options_found`: verified schedules meet constraints.
     - `no_feasible_options`: valid schedules evaluated and all failed constraints.
     - `search_data_unavailable`: provider outage, error, or live query returned 0 trains.
     - `quota_exhausted`: monthly request budget depleted; feasibility unverified.
     - `partial_results`: uncertain feasibility (e.g., missing last-mile duration).
3. **Cache Retrieval Order**:
   - Cache lookup did not precede quota check in `TrainSearchService`, failing to evaluate usable cached schedules before attempting outbound calls when quota was exhausted.

## Implemented Solutions
1. **Typed Models & Explicit Outcomes**:
   - Added `QuotaInfo` model in `backend/journey/models.py` tracking `used_requests`, `remaining_requests`, `monthly_limit`, `reserve_held`, `reset_date`, `reset_date_formatted`, `source`, `is_exhausted`, `usable_cached_results_exist`, and `last_successful_retrieval_at`.
   - Added `search_outcome` field to `JourneyPlanResponse`.
2. **Quota-Aware Cache-First Retrieval**:
   - `TrainSearchService.search_trains` checks `provider.get_cached_trains()` across station pairs first.
   - If quota is exhausted and valid unexpired cached schedules exist, feasibility is evaluated from cache with disclosure `[Evaluated from cached schedule data; live request budget is exhausted]`.
   - If quota is exhausted and no usable cached schedules exist, returns `status="monthly_quota_exhausted"` and `search_outcome="quota_exhausted"`, clearly declaring feasibility unverified.
   - Fare enrichment is bypassed when quota is depleted to prevent failing the entire journey plan.
3. **Timezone Formatting**:
   - Implemented `format_reset_time_with_timezone(reset_iso, tz_name="Asia/Kolkata")` in `backend/journey/quota.py` producing explicit human-readable strings, e.g. `"01 Nov 2026, 05:30 AM IST (+05:30)"`.
4. **UI & Quick-Refine Enhancements**:
   - Added dedicated `quota-exhausted-card` in `frontend/src/App.jsx` showing request budget, verified reset time with timezone, cache availability, and unverified feasibility badge.
   - Added `data-unavailable-card` and `partial-results-card`.
   - Updated quick-refine handler to evaluate cached schedules without triggering duplicate requests or implying that changes will restore quota.
5. **Offline Regression Test Suite**:
   - Added `Ticketing_Guidance_Module/tests/test_search_outcomes_quota.py` with 9 comprehensive offline regression tests covering all requirements.

## Test Results
- **Test Suite (`test_search_outcomes_quota.py`)**: 9 passed / 9 tests (100% offline, 0.08s).
- **Full Pytest Suite (`Ticketing_Guidance_Module/tests/`)**: 175 passed, 3 skipped (live smoke tests), 0 failed (100% pass rate in 2.04s).
- **Frontend Production Build**: Vite build completed cleanly in 143ms (`npm run build`).
