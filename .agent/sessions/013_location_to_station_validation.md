# Session 013: Location-to-Station Pipeline Validation with Tidel Park Live Fixture

**Date**: 2026-10-10  
**Status**: Completed  
**Branch**: `Ticketing-Guidance-Module`

## Objective
Validate the complete pipeline from a resolved destination venue (using verified live Nominatim fixture for Tidel Park Chennai: `lat=12.9893849, lon=80.2508691`) to railway station discovery, last-mile estimation, deadline feasibility arithmetic, and cache behavior under 100% offline test constraints.

## Validated Requirements
1. **Venue Validation**:
   - Resolved coordinates treated strictly as provider-derived data.
   - City-level match alone does not establish exact venue.
   - OSM importance represented as uncalibrated match confidence (0.40).
   - Ambiguous or low-confidence requests prompt user clarification.
2. **Station Discovery & Distance Arithmetic**:
   - Verified Haversine distances to Chennai railway hubs within $\pm 0.2$km tolerance (Egmore MS ~10.11km, Central MAS ~10.71km, Tambaram TBM ~15.11km).
   - Non-intercity suburban/MRTS halts (`TYMR`, `KTBR`) excluded from intercity searches when `filter_intercity=True`.
   - Distinguishes geographically nearest station (MS) from best train service terminal (MAS).
3. **Last-Mile Transparency**:
   - Unknown travel time remains `None` (not 0).
   - Heuristic urban road model clearly labeled (`is_heuristic=True`, `source_type='heuristic_urban_model'`).
   - Provider-derived routes attributed with live provider name (`is_heuristic=False`, `source_type='routing_provider'`).
4. **Journey Feasibility**:
   - Fixed meeting deadline (10:00 AM on 2026-10-15).
   - Evaluated station arrival deadlines ($10:00 - 46\text{m last-mile} - 45\text{m buffer} = 08:29$).
   - Rejects late trains (e.g. Shatabdi arriving 09:15).
   - Unknown last-mile duration cannot produce a feasible recommendation (`match_category='insufficient_data'`).
5. **Cache & Provider Invariants**:
   - Re-lookup of cached venue uses SQLite without extra provider calls.
   - Provider outage returns structured error without silent mock fallback.
   - 100% offline tests; zero external HTTP calls during automated suite runs.

## Test Results
- **Test Suite (`test_location_station_validation.py`)**: 13 passed / 13 tests.
- **Full Pytest Suite**: 166 passed, 3 skipped (live smoke tests), 0 failed (100% pass rate).
