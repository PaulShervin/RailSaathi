# Session 012: Dynamic LLM-Assisted Venue Geocoding, Station Resolution, and Routing Isolation

**Date**: 2026-10-10  
**Status**: Completed  
**Branch**: `Ticketing-Guidance-Module`

## Objective
Upgrade RailSathi's location resolution system to dynamically resolve arbitrary real-world venues to verified coordinates via external geocoding providers (e.g., OpenStreetMap Nominatim), validate locality consistency, disambiguate multi-branch venues, find suitable intercity railway stations, and estimate transparent last-mile transit without consuming RailRadar quota or inventing coordinates.

## Key Changes
1. **Created Geocoding Provider Abstraction (`backend/journey/geocoding.py`)**:
   - `GeocodingProvider` protocol.
   - `OSMNominatimGeocodingProvider`: OSM Nominatim client with custom User-Agent, 1.0s atomic interval rate limiter, and structured error handling.
   - `VerifiedRegistryGeocodingProvider`: Local offline dataset provider.
   - `MockGeocodingProvider`: Deterministic mock for offline testing.
   - `get_geocoding_provider()` factory.
2. **Created Routing Provider Abstraction (`backend/journey/routing.py`)**:
   - `RoutingProvider` protocol.
   - `DeterministicUrbanRoutingModel`: 1.30x detour, 22 km/h average speed, 8m buffer, explicitly labeled `is_heuristic=True`.
   - `MockRoutingProvider`: Injected mock for provider-derived routes.
   - `get_routing_provider()` factory.
3. **Refactored Location Resolution Service (`backend/journey/location.py`)**:
   - Integrated `GeocodingProvider` and `RoutingProvider`.
   - Implemented Stages A-E (intent normalization $\rightarrow$ persistent SQLite cache $\rightarrow$ station lookup $\rightarrow$ dynamic geocoding $\rightarrow$ coordinate and locality validation $\rightarrow$ ambiguity handling $\rightarrow$ caching).
   - Unknown last-mile duration returned as `None` (never zero).
4. **Registered `resolve_venue` Tool (`backend/tools/journey_tools.py`)**:
   - Added schema and execution dispatch for LLM tool calling.
5. **Enhanced Frontend UI (`frontend/src/App.jsx`)**:
   - Added interactive suggested location chips for disambiguating ambiguous venues.
6. **Comprehensive Offline Test Suite (`tests/test_dynamic_geocoding.py`)**:
   - 18 specific offline test cases covering all edge cases.

## Test Results
- **Pytest Suite**: 153 passed, 3 skipped (live smoke tests), 0 failed (100% pass rate).
- **Frontend Build**: Production build clean in 141ms.
- **RailRadar Quota Impact**: 0 RailRadar API calls consumed for geocoding and routing.
