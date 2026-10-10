"""
RailSathi AI — Location-to-Station Validation Test Suite

Validates the full pipeline from a resolved destination venue (using verified Tidel Park
live fixture: lat=12.9893849, lon=80.2508691, provider='OpenStreetMap Nominatim')
to railway station discovery, last-mile estimation, deadline feasibility, and cache behavior.

100% Offline tests: Zero external HTTP requests made to Nominatim or RailRadar.
"""

import math
import pytest
from datetime import datetime, timedelta

from backend.journey.models import (
    GeocodedPlaceCandidate,
    ResolvedLocation,
    TripRequirements,
    TrainService,
    LastMileEstimate,
)
from backend.journey.geocoding import (
    MockGeocodingProvider,
    OSMNominatimGeocodingProvider,
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
from backend.journey.planner import JourneyPlanner


# Standard verified fixture from controlled live Nominatim test
TIDEL_PARK_NOMINATIM_FIXTURE = GeocodedPlaceCandidate(
    place_name="Tidel park",
    formatted_address="Tidel park, Rajiv Gandhi IT Expressway, Ward 180, Zone 13 Adyar, Chennai, Chennai District, Tamil Nadu, 600113, India",
    latitude=12.9893849,
    longitude=80.2508691,
    city="Chennai",
    state="Tamil Nadu",
    country="India",
    provider="OpenStreetMap Nominatim",
    provider_place_id="251418697",
    confidence=0.40,
    raw_metadata={"osm_id": 1183430763, "category": "highway"},
)


@pytest.fixture
def mock_geocoder_with_tidel():
    """Mock geocoder preloaded with verified live Tidel Park Nominatim fixture."""
    geocoder = MockGeocodingProvider()
    geocoder.add_fixture(
        "tidel park, taramani, chennai, tamil nadu, india",
        [TIDEL_PARK_NOMINATIM_FIXTURE],
    )
    geocoder.add_fixture(
        "tidel park, chennai",
        [TIDEL_PARK_NOMINATIM_FIXTURE],
    )
    return geocoder


@pytest.fixture
def isolated_service(tmp_path, mock_geocoder_with_tidel):
    """Provide LocationResolutionService with isolated SQLite cache."""
    db_file = tmp_path / "test_loc_station_val.sqlite"
    cache = LocationCacheManager(db_path=str(db_file))
    return LocationResolutionService(
        cache_manager=cache,
        geocoding_provider=mock_geocoder_with_tidel,
    )


# =====================================================================
# 1. Venue Validation Tests
# =====================================================================

def test_venue_and_locality_consistency_with_tidel_fixture(isolated_service):
    """Confirm returned venue and locality match requested Chennai destination."""
    resolved = isolated_service.resolve_location(
        "Tidel Park, Taramani, Chennai, Tamil Nadu, India",
        context_city="Chennai",
    )
    
    assert resolved.latitude == pytest.approx(12.9893849, abs=1e-5)
    assert resolved.longitude == pytest.approx(80.2508691, abs=1e-5)
    assert "chennai" in resolved.city.lower()
    assert resolved.state == "Tamil Nadu"
    assert resolved.provider == "OpenStreetMap Nominatim"
    assert resolved.provider_place_id == "251418697"
    assert resolved.requires_user_clarification is False


def test_city_level_match_alone_cannot_establish_exact_venue(isolated_service):
    """Ensure querying an unverified venue name in Chennai does not establish a venue match."""
    resolved = isolated_service.resolve_location(
        "Arbitrary Unknown Research Center 404",
        context_city="Chennai",
    )
    
    # Must NOT substitute Chennai City Center coordinates
    assert resolved.latitude is None
    assert resolved.longitude is None
    assert resolved.confidence == 0.0
    assert resolved.requires_user_clarification is True
    assert "could not be verified" in (resolved.resolution_error or "").lower()


def test_osm_importance_represented_as_uncalibrated_match_score(isolated_service):
    """Confirm OSM importance is represented as match quality signal rather than calibrated probability."""
    resolved = isolated_service.resolve_location(
        "Tidel Park, Chennai",
        context_city="Chennai",
    )
    # Nominatim importance for highway node is 0.40; should not be fabricated to 0.99
    assert resolved.confidence == 0.40
    assert resolved.confidence <= 0.98


# =====================================================================
# 2. Station Discovery & Geographic Distance Verification
# =====================================================================

def test_haversine_distances_from_tidel_park_fixture(isolated_service):
    """Verify calculated Haversine distances to Chennai railway stations against independent geometric math."""
    resolved = isolated_service.resolve_location(
        "Tidel Park, Chennai",
        context_city="Chennai",
    )
    
    # Tidel Park coords: (12.9893849, 80.2508691)
    t_lat, t_lon = resolved.latitude, resolved.longitude
    
    # Independent calculations:
    # 1. MS (Egmore: 13.0797, 80.2612) -> ~10.11 km
    dist_ms = calculate_haversine_distance_km(t_lat, t_lon, 13.0797, 80.2612)
    assert dist_ms == pytest.approx(10.11, abs=0.2)
    
    # 2. MAS (Central: 13.0827, 80.2757) -> ~10.71 km
    dist_mas = calculate_haversine_distance_km(t_lat, t_lon, 13.0827, 80.2757)
    assert dist_mas == pytest.approx(10.71, abs=0.2)
    
    # 3. TBM (Tambaram: 12.9249, 80.1278) -> ~15.11 km
    dist_tbm = calculate_haversine_distance_km(t_lat, t_lon, 12.9249, 80.1278)
    assert dist_tbm == pytest.approx(15.11, abs=0.3)


def test_station_discovery_excludes_non_intercity_mrts_stops(isolated_service):
    """Confirm suburban/MRTS stops (TYMR, KTBR) are filtered out when searching intercity stations."""
    resolved = isolated_service.resolve_location(
        "Tidel Park, Chennai",
        context_city="Chennai",
    )
    
    stations = isolated_service.find_nearby_stations(resolved, filter_intercity=True)
    codes = [s.station_code for s in stations]
    
    # Major intercity terminals must be present
    assert "MAS" in codes
    assert "MS" in codes
    assert "TBM" in codes
    
    # MRTS halts (which cannot receive intercity express trains) must be excluded
    assert "TYMR" not in codes
    assert "KTBR" not in codes


def test_distinguish_nearest_station_from_best_journey_station(isolated_service):
    """
    Demonstrate that while Egmore (MS ~10.1km) is geographically closer to Tidel Park than
    Central (MAS ~10.7km), MAS can be the superior destination for trains from Bengaluru/Delhi.
    """
    resolved = isolated_service.resolve_location(
        "Tidel Park, Chennai",
        context_city="Chennai",
    )
    stations = isolated_service.find_nearby_stations(resolved, filter_intercity=True)
    
    # Find MS and MAS
    st_ms = next(s for s in stations if s.station_code == "MS")
    st_mas = next(s for s in stations if s.station_code == "MAS")
    
    assert st_ms.distance_to_venue_km < st_mas.distance_to_venue_km
    assert st_mas.is_major_hub is True
    assert st_ms.is_major_hub is True


# =====================================================================
# 3. Last-Mile Estimation Transparency Tests
# =====================================================================

def test_missing_last_mile_data_remains_none_not_zero(isolated_service):
    """Verify that last-mile estimate for an unverified location returns None (not 0)."""
    unverified_loc = ResolvedLocation(
        query="Unknown Landmark",
        display_name="Unknown Landmark",
        city="Chennai",
        latitude=None,
        longitude=None,
    )
    
    est = isolated_service.estimate_last_mile("MAS", "Unknown Landmark", venue_location=unverified_loc)
    
    assert est.duration_minutes is None
    assert est.distance_km is None
    assert est.duration_minutes != 0
    assert est.is_heuristic is True


def test_heuristic_road_estimate_transparency(isolated_service):
    """Verify that deterministic urban road routing is explicitly labeled as a heuristic estimate."""
    resolved = isolated_service.resolve_location(
        "Tidel Park, Chennai",
        context_city="Chennai",
    )
    est = isolated_service.estimate_last_mile("MAS", "Tidel Park", venue_location=resolved)
    
    assert est.is_heuristic is True
    assert est.source_type == "heuristic_urban_model"
    assert est.distance_km is not None
    assert est.duration_minutes is not None
    assert est.duration_minutes > 0
    # Road distance is ~1.3x aerial distance: ~10.7km * 1.30 ≈ 13.9km
    assert est.distance_km == pytest.approx(13.92, abs=0.5)


def test_provider_derived_routing_source_attribution(isolated_service):
    """Verify that when a live routing provider is configured, source_type is 'routing_provider'."""
    mock_router = MockRoutingProvider(fixed_distance_km=14.5, fixed_duration_minutes=38)
    service = LocationResolutionService(
        cache_manager=isolated_service.cache,
        geocoding_provider=isolated_service.geocoding_provider,
        routing_provider=mock_router,
    )
    resolved = service.resolve_location("Tidel Park, Chennai", context_city="Chennai")
    est = service.estimate_last_mile("MAS", "Tidel Park", venue_location=resolved)
    
    assert est.is_heuristic is False
    assert est.source_type == "routing_provider"
    assert est.provider == "MockLiveRoutingEngine"
    assert est.distance_km == 14.5
    assert est.duration_minutes == 38


# =====================================================================
# 4. Journey Feasibility & Deadline Arithmetic Tests
# =====================================================================

def test_journey_feasibility_morning_meeting_with_tidel_fixture(isolated_service):
    """
    Simulate passenger with 10:00 AM meeting at Tidel Park Chennai on 2026-10-15:
    - Last mile from MAS to Tidel Park: ~46 mins (13.9km @ 22km/h + 8m terminal buffer).
    - Required arrival buffer at venue: 45 mins.
    - Required latest arrival at station: 10:00 - 46m - 45m = 08:29.
    - Train 1: Arrives 08:00 (Feasible, 29m extra buffer).
    - Train 2: Arrives 09:15 (Late / Infeasible, arrives station too late).
    """
    evaluator = JourneyFeasibilityEvaluator()
    resolved = isolated_service.resolve_location("Tidel Park, Chennai", context_city="Chennai")
    last_mile = isolated_service.estimate_last_mile("MAS", "Tidel Park", venue_location=resolved)
    
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
    
    # Feasible train arriving at 08:00
    early_train = TrainService(
        train_number="12658",
        train_name="Chennai Mail (Overnight)",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="MGR Chennai Central",
        departure_time="22:40",
        arrival_time="08:00",
        day_offset=1,
        duration_minutes=560,
        runs_on_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        classes=["3A", "2A", "SL"],
        fares={"3A": 850.0, "2A": 1200.0, "SL": 320.0},
        data_source="mock",
    )
    
    eval_early = evaluator.evaluate_candidate(early_train, req, last_mile)
    assert eval_early.is_feasible is True
    assert eval_early.actual_arrival_buffer_minutes is not None
    assert eval_early.actual_arrival_buffer_minutes >= 45
    assert len(eval_early.hard_constraint_violations) == 0

    # Infeasible train arriving at 09:15 (reaches venue at ~10:01, misses meeting)
    late_train = TrainService(
        train_number="12008",
        train_name="Shatabdi Express",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="MGR Chennai Central",
        departure_time="06:00",
        arrival_time="09:15",
        day_offset=0,
        duration_minutes=195,
        runs_on_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        classes=["CC", "EC"],
        fares={"CC": 1050.0, "EC": 1980.0},
        data_source="mock",
    )
    
    eval_late = evaluator.evaluate_candidate(late_train, req, last_mile)
    assert eval_late.is_feasible is False
    assert any("deadline" in v.lower() for v in eval_late.hard_constraint_violations)


def test_missing_travel_time_cannot_produce_feasible_recommendation():
    """Verify that an evaluation with unknown last mile is marked infeasible with insufficient_data."""
    evaluator = JourneyFeasibilityEvaluator()
    req = TripRequirements(
        origin="Bengaluru",
        destination_venue="Unknown Remote Place",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )
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
        classes=["CC"],
        fares={"CC": 1050.0},
        data_source="mock",
    )
    unknown_last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Unknown Remote Place",
        distance_km=None,
        duration_minutes=None,
        confidence="unknown",
    )
    
    eval_res = evaluator.evaluate_candidate(train, req, unknown_last_mile)
    assert eval_res.is_feasible is False
    assert eval_res.match_category == "insufficient_data"


# =====================================================================
# 5. Cache & Provider Error Handling Tests (100% Offline)
# =====================================================================

def test_cached_resolution_emits_zero_provider_calls(isolated_service, mock_geocoder_with_tidel):
    """Verify that repeated venue resolutions reuse SQLite cache without invoking provider."""
    # First call - queries mock provider
    loc1 = isolated_service.resolve_location("Tidel Park, Chennai", context_city="Chennai")
    assert loc1.is_cached is False
    assert mock_geocoder_with_tidel.calls_count == 1
    
    # Second call - resolved from cache
    loc2 = isolated_service.resolve_location("Tidel Park, Chennai", context_city="Chennai")
    assert loc2.is_cached is True
    assert loc2.latitude == loc1.latitude
    assert loc2.longitude == loc1.longitude
    assert mock_geocoder_with_tidel.calls_count == 1  # Calls count unchanged!


def test_provider_outage_resilience(tmp_path):
    """Verify that a geocoding provider network outage produces a structured clarification request."""
    broken_geocoder = MockGeocodingProvider()
    broken_geocoder.simulate_outage = True
    
    cache = LocationCacheManager(db_path=tmp_path / "outage_cache.sqlite")
    service = LocationResolutionService(cache_manager=cache, geocoding_provider=broken_geocoder)
    
    resolved = service.resolve_location("Random Uncached Venue", context_city="Delhi")
    assert resolved.latitude is None
    assert resolved.longitude is None
    assert resolved.confidence == 0.0
    assert resolved.requires_user_clarification is True
    assert resolved.resolution_error is not None
