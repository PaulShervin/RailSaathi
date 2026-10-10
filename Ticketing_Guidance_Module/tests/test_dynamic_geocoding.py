"""
RailSathi AI — Dynamic Venue Geocoding & Station Resolution Offline Test Suite

Comprehensive offline tests verifying:
1. Dynamic venue resolution via injected geocoder
2. Cache hit avoiding redundant geocoding requests
3. Locality mismatch detection and rejection
4. Multi-branch ambiguity handling and clarification generation
5. Zero results handling without hallucinating coordinates
6. Invalid coordinates rejection
7. Provider outage resilience
8. Complete isolation from RailRadar quota
9. Station proximity vs journey suitability
10. Suburban/MRTS exclusion from intercity searches
11. Unknown last-mile duration handling (not zero)
12. Heuristic duration source transparency
13. Provider-derived route attribution
14. Independent geocoder rate limiting
15. SQLite persistent caching
16. Feasibility integration with meeting deadlines
17. Database isolation
18. Zero external network calls
"""

import os
import time
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from backend.journey.models import (
    GeocodedPlaceCandidate,
    ResolvedLocation,
    TripRequirements,
    TrainService,
)
from backend.journey.geocoding import (
    MockGeocodingProvider,
    OSMNominatimGeocodingProvider,
    get_geocoding_provider,
)
from backend.journey.routing import (
    DeterministicUrbanRoutingModel,
    MockRoutingProvider,
    calculate_haversine_distance_km,
)
from backend.journey.location import (
    LocationCacheManager,
    LocationResolutionService,
    STATION_REGISTRY,
)
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.tools.journey_tools import execute_journey_tool


@pytest.fixture
def temp_cache(tmp_path):
    """Provide an isolated temporary SQLite cache database."""
    db_file = tmp_path / "test_location_cache.db"
    return LocationCacheManager(db_path=str(db_file))


@pytest.fixture
def mock_geocoder():
    """Provide a mock geocoder with preloaded venue fixtures."""
    geocoder = MockGeocodingProvider()
    
    # Fixture: Tidel Park Chennai
    geocoder.add_fixture(
        "tidel park, chennai",
        [
            GeocodedPlaceCandidate(
                place_name="TIDEL Park",
                formatted_address="TIDEL Park, Rajiv Gandhi Salai (OMR), Taramani, Chennai, Tamil Nadu, 600113, India",
                latitude=12.9897,
                longitude=80.2476,
                city="Chennai",
                state="Tamil Nadu",
                country="India",
                provider="MockGeocodingProvider",
                provider_place_id="osm_node_1001",
                confidence=0.92,
            )
        ],
    )
    
    # Fixture: Ambiguous Tidel Park (Multiple cities)
    geocoder.add_fixture(
        "tidel park",
        [
            GeocodedPlaceCandidate(
                place_name="TIDEL Park Taramani",
                formatted_address="TIDEL Park, Taramani, Chennai, Tamil Nadu, India",
                latitude=12.9897,
                longitude=80.2476,
                city="Chennai",
                state="Tamil Nadu",
                country="India",
                provider="MockGeocodingProvider",
                provider_place_id="osm_node_1001",
                confidence=0.90,
            ),
            GeocodedPlaceCandidate(
                place_name="TIDEL Park Coimbatore",
                formatted_address="TIDEL Park Coimbatore, Civil Aerodrome Post, Coimbatore, Tamil Nadu, India",
                latitude=11.0289,
                longitude=77.0278,
                city="Coimbatore",
                state="Tamil Nadu",
                country="India",
                provider="MockGeocodingProvider",
                provider_place_id="osm_node_1002",
                confidence=0.88,
            ),
        ],
    )
    
    # Fixture: Arbitrary New Venue (e.g. Phoenix Marketcity Bengaluru)
    geocoder.add_fixture(
        "phoenix marketcity, bengaluru",
        [
            GeocodedPlaceCandidate(
                place_name="Phoenix Marketcity",
                formatted_address="Phoenix Marketcity, Whitefield Main Rd, Mahadevapura, Bengaluru, Karnataka, 560048, India",
                latitude=12.9958,
                longitude=77.6964,
                city="Bengaluru",
                state="Karnataka",
                country="India",
                provider="MockGeocodingProvider",
                provider_place_id="osm_way_2002",
                confidence=0.95,
            )
        ],
    )
    return geocoder


# Test 1: Unknown venue is resolved through injected geocoding provider
def test_unknown_venue_resolved_via_geocoding_provider(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    loc = service.resolve_location("Phoenix Marketcity", context_city="Bengaluru")

    assert loc.latitude == pytest.approx(12.9958, rel=1e-4)
    assert loc.longitude == pytest.approx(77.6964, rel=1e-4)
    assert loc.city == "Bengaluru"
    assert loc.provider == "MockGeocodingProvider"
    assert loc.is_cached is False
    assert mock_geocoder.calls_count == 1


# Test 2: Verified cached venue avoids a second provider request
def test_cached_venue_avoids_second_provider_request(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    # First call - queries provider
    loc1 = service.resolve_location("Phoenix Marketcity", context_city="Bengaluru")
    assert loc1.is_cached is False
    assert mock_geocoder.calls_count == 1

    # Second call - served from cache
    loc2 = service.resolve_location("Phoenix Marketcity", context_city="Bengaluru")
    assert loc2.is_cached is True
    assert loc2.latitude == loc1.latitude
    assert loc2.longitude == loc1.longitude
    assert mock_geocoder.calls_count == 1  # No additional provider call!


# Test 3: Locality mismatch is detected and rejected
def test_locality_mismatch_rejected(temp_cache, mock_geocoder):
    # Geocoder only knows about Phoenix Marketcity in Bengaluru
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    # User asks for Phoenix Marketcity in Chennai (which mock geocoder doesn't have in Chennai)
    # The geocoder returns the Bengaluru candidate, but the requested city is Chennai
    loc = service.resolve_location("Phoenix Marketcity, Bengaluru", context_city="Chennai")

    assert loc.latitude is None
    assert loc.requires_user_clarification is True
    assert "Locality Mismatch" in loc.display_name or "mismatch" in (loc.resolution_error or "").lower()


# Test 4: Multiple ambiguous venue candidates trigger clarification
def test_multiple_ambiguous_candidates_trigger_clarification(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    # Query "Tidel Park" without city context
    loc = service.resolve_location("Tidel Park")

    assert loc.requires_user_clarification is True
    assert loc.latitude is None
    assert len(loc.clarification_options) >= 2
    assert any("Chennai" in opt for opt in loc.clarification_options)
    assert any("Coimbatore" in opt for opt in loc.clarification_options)


# Test 5: Zero geocoder results do not produce invented coordinates
def test_zero_geocoder_results_no_hallucinated_coordinates(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    loc = service.resolve_location("NonExistentFictionalBuilding999", context_city="Chennai")

    assert loc.latitude is None
    assert loc.longitude is None
    assert loc.confidence == 0.0
    assert loc.requires_user_clarification is True
    assert loc.resolution_error is not None


# Test 6: Invalid coordinates returned from provider are rejected
def test_invalid_coordinates_rejected(temp_cache):
    geocoder = MockGeocodingProvider()
    geocoder.add_fixture(
        "broken coords venue",
        [
            GeocodedPlaceCandidate(
                place_name="Broken Coords Place",
                formatted_address="Broken Place, Chennai",
                latitude=999.0,  # Invalid latitude (> 90)
                longitude=80.25,
                city="Chennai",
                provider="MockGeocodingProvider",
            )
        ],
    )
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=geocoder)
    loc = service.resolve_location("Broken Coords Venue", context_city="Chennai")

    assert loc.latitude is None
    assert loc.requires_user_clarification is True


# Test 7: Geocoder outage returns structured error
def test_geocoder_outage_returns_structured_error(temp_cache):
    geocoder = MockGeocodingProvider()
    geocoder.simulate_outage = True
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=geocoder)
    
    loc = service.resolve_location("Some Random Venue", context_city="Hyderabad")

    assert loc.latitude is None
    assert loc.requires_user_clarification is True
    assert loc.resolution_error is not None


# Test 8: Cached venue results remain independent of RailRadar quota
def test_geocoding_independent_of_railradar_quota(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    # Geocode a venue
    loc = service.resolve_location("Phoenix Marketcity", context_city="Bengaluru")
    assert loc.latitude is not None
    
    # Verify zero RailRadar calls and only geocoding requests tracked
    assert service.geocoding_requests_count == 1
    assert service.routing_requests_count == 0


# Test 9: Station selection distinguishes geographic proximity from journey-level suitability
def test_station_selection_proximity_vs_suitability(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    
    # Tidel Park Chennai
    loc = service.resolve_location("Tidel Park", context_city="Chennai")
    stations = service.find_nearby_stations(loc, filter_intercity=True)

    # Major hub MAS/MS should be present along with distance rankings
    station_codes = [s.station_code for s in stations]
    assert "MAS" in station_codes
    assert "MS" in station_codes
    assert "TBM" in station_codes
    
    # All candidates have calculated distances and estimated minutes
    for s in stations:
        assert s.distance_to_venue_km is not None
        assert s.estimated_last_mile_minutes is not None
        assert s.supports_intercity is True


# Test 10: Local-only stops (e.g. MRTS/Suburban halts) are excluded from intercity train searches
def test_local_only_stops_excluded_when_filter_intercity_true(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    loc = service.resolve_location("Tidel Park", context_city="Chennai")
    
    intercity_stations = service.find_nearby_stations(loc, filter_intercity=True)
    codes = [s.station_code for s in intercity_stations]
    
    assert "TYMR" not in codes  # Taramani MRTS
    assert "KTBR" not in codes  # Kasturba Nagar MRTS
    
    # When filter_intercity=False, suburban halts are included
    all_stations = service.find_nearby_stations(loc, filter_intercity=False)
    all_codes = [s.station_code for s in all_stations]
    assert "TYMR" in all_codes


# Test 11: Unknown last-mile duration is not treated as zero
def test_unknown_last_mile_duration_is_none_not_zero(temp_cache):
    service = LocationResolutionService(cache_manager=temp_cache)
    
    # Venue with missing coordinates
    unresolved_loc = ResolvedLocation(
        query="Unknown Place",
        display_name="Unknown Place",
        city="Chennai",
        latitude=None,
        longitude=None,
    )
    
    estimate = service.estimate_last_mile("MAS", "Unknown Place", venue_location=unresolved_loc)
    
    assert estimate.duration_minutes is None
    assert estimate.distance_km is None
    assert estimate.duration_minutes != 0


# Test 12: Heuristic durations are explicitly labelled as heuristic
def test_heuristic_durations_labelled_as_heuristic(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    loc = service.resolve_location("Tidel Park", context_city="Chennai")
    
    estimate = service.estimate_last_mile("MAS", "Tidel Park", venue_location=loc)
    
    assert estimate.is_heuristic is True
    assert estimate.source_type == "heuristic_urban_model"
    assert "Heuristic" in estimate.provider or "Deterministic Urban" in estimate.provider
    assert estimate.duration_minutes is not None and estimate.duration_minutes > 0


# Test 13: Provider-derived routes are labelled with their actual source
def test_provider_derived_routes_labelled_with_source(temp_cache, mock_geocoder):
    mock_router = MockRoutingProvider(fixed_distance_km=14.2, fixed_duration_minutes=42)
    service = LocationResolutionService(
        cache_manager=temp_cache,
        geocoding_provider=mock_geocoder,
        routing_provider=mock_router,
    )
    loc = service.resolve_location("Tidel Park", context_city="Chennai")
    
    estimate = service.estimate_last_mile("MAS", "Tidel Park", venue_location=loc)
    
    assert estimate.is_heuristic is False
    assert estimate.source_type == "routing_provider"
    assert estimate.provider == "MockLiveRoutingEngine"
    assert estimate.distance_km == 14.2
    assert estimate.duration_minutes == 42


# Test 14: Geocoding provider rate limits are enforced independently
def test_geocoding_provider_rate_limiting():
    provider = OSMNominatimGeocodingProvider(min_request_interval_seconds=0.1)
    
    t0 = time.time()
    provider._enforce_rate_limit()
    provider._enforce_rate_limit()
    elapsed = time.time() - t0
    
    assert elapsed >= 0.09


# Test 15: Repeated requests use persistent SQLite cache across service restarts
def test_persistent_cache_across_restarts(tmp_path, mock_geocoder):
    db_file = tmp_path / "persistent_cache.db"
    
    # Service instance 1 writes to DB
    cache1 = LocationCacheManager(db_path=str(db_file))
    service1 = LocationResolutionService(cache_manager=cache1, geocoding_provider=mock_geocoder)
    loc1 = service1.resolve_location("Phoenix Marketcity", context_city="Bengaluru")
    assert loc1.is_cached is False
    assert mock_geocoder.calls_count == 1
    
    # Service instance 2 reads from same DB
    cache2 = LocationCacheManager(db_path=str(db_file))
    service2 = LocationResolutionService(cache_manager=cache2, geocoding_provider=mock_geocoder)
    loc2 = service2.resolve_location("Phoenix Marketcity", context_city="Bengaluru")
    assert loc2.is_cached is True
    assert loc2.latitude == pytest.approx(12.9958, rel=1e-4)
    assert mock_geocoder.calls_count == 1  # No additional calls!


# Test 16: Deadline feasibility calculation with last-mile duration
def test_journey_feasibility_with_last_mile(temp_cache, mock_geocoder):
    service = LocationResolutionService(cache_manager=temp_cache, geocoding_provider=mock_geocoder)
    evaluator = JourneyFeasibilityEvaluator()
    
    loc = service.resolve_location("Tidel Park", context_city="Chennai")
    last_mile = service.estimate_last_mile("MAS", "Tidel Park", venue_location=loc)
    
    # Train arriving at 08:30 for a 10:00 meeting with 45 min buffer + ~50 min last-mile
    # 08:30 + 50m last mile = 09:20 arrival at venue. 09:20 <= 09:15 buffer boundary?
    train = TrainService(
        train_number="20608",
        train_name="Vande Bharat Express",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="MGR Chennai Central",
        departure_time="05:45",
        arrival_time="08:30",
        duration_minutes=165,
        runs_on_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        classes=["CC", "EC"],
        fares={"CC": 1050.0, "EC": 1980.0},
        data_source="mock",
    )
    
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=30,
    )
    
    eval_res = evaluator.evaluate_candidate(train, req, last_mile)
    
    assert eval_res.is_feasible is True
    assert eval_res.actual_arrival_buffer_minutes is not None
    assert eval_res.actual_arrival_buffer_minutes >= 30
    assert len(eval_res.hard_constraint_violations) == 0


# Test 17: Tool orchestration execution for resolve_venue
def test_tool_orchestration_resolve_venue():
    res = execute_journey_tool(
        "resolve_venue",
        {"query": "Tidel Park", "city": "Chennai", "state": "Tamil Nadu"},
    )
    
    assert res["status"] == "success"
    loc = res["resolved_location"]
    assert loc["latitude"] is not None
    assert "Chennai" in loc["city"] or "Taramani" in loc["display_name"]


# Test 18: No external HTTP calls during offline tests
def test_zero_external_network_calls_in_mock():
    geocoder = MockGeocodingProvider()
    assert geocoder.calls_count == 0
    res = geocoder.search_venue("Any Venue")
    assert res == []
    assert geocoder.calls_count == 1
