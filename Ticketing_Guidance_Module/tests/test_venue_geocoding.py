"""
RailSathi AI — Venue Geocoding and Nearest Station Resolution Tests

Unit, integration, and scenario tests for:
1. Multi-branch venue disambiguation (Tidel Park Taramani vs Pattabiram vs Coimbatore vs Madurai).
2. Ambiguous venue resolution requesting user clarification.
3. Nearest station vs optimal station selection for intercity journeys.
4. Prohibition of silent city-centroid fallback for unverified coordinates.
5. Strict non-zero handling of unknown last-mile transit duration.
6. Durable SQLite location and routing caching with zero RailRadar quota consumption.
7. Morning meeting feasibility arithmetic incorporating rail arrival, last mile, and buffer.
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.journey.models import (
    TripRequirements,
    ResolvedLocation,
    StationCandidate,
    LastMileEstimate,
    TrainService,
)
from backend.journey.location import (
    LocationResolutionService,
    LocationCacheManager,
    calculate_haversine_distance_km,
    estimate_urban_travel_time_minutes,
)
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.journey.planner import JourneyPlanner, parse_requirements_from_text
from backend.journey.quota import DurableRailRadarQuotaManager


def test_1_tidel_park_chennai_resolves_to_taramani(tmp_path):
    """1. 'Tidel Park, Chennai' resolves to the correct Taramani venue coordinates."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    resolved = loc_service.resolve_location("Tidel Park, Chennai")

    assert resolved.city == "Chennai"
    assert resolved.state == "Tamil Nadu"
    assert "Taramani" in resolved.display_name or "Taramani" in (resolved.resolved_address or "")
    assert abs(resolved.latitude - 12.9893) < 0.01
    assert abs(resolved.longitude - 80.2483) < 0.01
    assert resolved.confidence >= 0.95
    assert resolved.requires_user_clarification is False


def test_2_tidel_park_pattabiram_distinct_from_taramani(tmp_path):
    """2. 'Tidel Park, Pattabiram' does not resolve to the Chennai Taramani location."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    resolved_taramani = loc_service.resolve_location("Tidel Park, Chennai")
    resolved_pattabiram = loc_service.resolve_location("Tidel Park, Pattabiram")

    assert "Pattabiram" in resolved_pattabiram.display_name
    assert abs(resolved_pattabiram.latitude - 13.1235) < 0.01
    assert abs(resolved_pattabiram.longitude - 80.0574) < 0.01
    
    # Distance between Pattabiram and Taramani is > 25 km
    dist = calculate_haversine_distance_km(
        resolved_taramani.latitude, resolved_taramani.longitude,
        resolved_pattabiram.latitude, resolved_pattabiram.longitude,
    )
    assert dist > 20.0
    assert resolved_pattabiram.latitude != resolved_taramani.latitude


def test_3_ambiguous_venue_triggers_clarification(tmp_path):
    """3. An ambiguous venue name ('Tidel Park' with no city) triggers clarification."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    resolved = loc_service.resolve_location("Tidel Park")

    assert resolved.requires_user_clarification is True
    assert resolved.confidence < 0.60
    assert resolved.latitude is None
    assert resolved.longitude is None
    assert len(resolved.clarification_options) >= 3
    assert any("Taramani" in opt for opt in resolved.clarification_options)
    assert any("Pattabiram" in opt for opt in resolved.clarification_options)
    assert any("Coimbatore" in opt for opt in resolved.clarification_options)


def test_4_nearest_station_selection_using_verified_coordinates(tmp_path):
    """4. Candidate stations are discovered and ordered by proximity/hub status."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    venue = loc_service.resolve_location("Tidel Park, Chennai")
    stations = loc_service.find_nearby_stations(venue)

    codes = [s.station_code for s in stations]
    assert "MAS" in codes
    assert "MS" in codes
    assert "TBM" in codes

    # MRTS-only stop (TYMR) should be filtered out from intercity stations
    assert "TYMR" not in codes
    assert all(s.supports_intercity for s in stations)


def test_5_farther_station_can_be_selected_for_better_schedule(tmp_path):
    """5. A farther station can be selected when it offers a materially better feasible journey."""
    planner = JourneyPlanner()
    evaluator = JourneyFeasibilityEvaluator()

    # User meeting at Tidel Park at 08:30 AM with 30m buffer (Venue arrival needed by 08:00 AM)
    reqs = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="08:30",
        required_arrival_buffer_minutes=30,
    )

    # Train A: Arrives Tambaram (TBM - closer ~17km) at 08:15 AM (Too late! Arrives venue at 08:50 AM)
    train_tbm = TrainService(
        train_number="12636",
        train_name="VAIGAI SF EXP",
        origin_station_code="MDU",
        origin_station_name="Madurai",
        destination_station_code="TBM",
        destination_station_name="Tambaram",
        departure_time="01:00",
        arrival_time="08:15",
        duration_minutes=435,
        day_offset=0,
        classes=["3A", "CC", "SL"],
        fares={"3A": 750.0, "CC": 550.0, "SL": 260.0},
    )

    # Train B: Arrives Chennai Central (MAS - farther ~16km) at 04:35 AM (Chennai Mail - arrives venue ~05:15 AM, early & feasible)
    train_mas = TrainService(
        train_number="12658",
        train_name="CHENNAI MAIL",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="MGR Chennai Central",
        departure_time="22:40",
        arrival_time="04:35",
        duration_minutes=355,
        day_offset=1,
        classes=["3A", "2A", "SL"],
        fares={"3A": 750.0, "2A": 1050.0, "SL": 260.0},
    )

    lm_tbm = planner.location_service.estimate_last_mile("TBM", "Tidel Park, Chennai")
    lm_mas = planner.location_service.estimate_last_mile("MAS", "Tidel Park, Chennai")

    ev_tbm = evaluator.evaluate_candidate(train=train_tbm, requirements=reqs, last_mile=lm_tbm)
    ev_mas = evaluator.evaluate_candidate(train=train_mas, requirements=reqs, last_mile=lm_mas)

    assert ev_tbm.is_feasible is False  # Infeasible because reaches venue after deadline
    assert ev_mas.is_feasible is True   # Feasible! Farther terminal MAS is chosen as top recommendation


def test_6_missing_coordinates_never_silently_become_city_centroid(tmp_path):
    """6. Missing coordinates never silently become city-centroid coordinates."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    resolved = loc_service.resolve_location("Fictional Nonexistent Tech Park XYZ")

    assert resolved.latitude is None
    assert resolved.longitude is None
    assert resolved.confidence == 0.0
    assert resolved.requires_user_clarification is True
    assert "Unverified" in resolved.provider or "Heuristic" in resolved.provider


def test_7_unknown_last_mile_duration_is_not_treated_as_zero():
    """7. Unknown last-mile duration is not treated as zero and marks feasibility insufficient/infeasible."""
    evaluator = JourneyFeasibilityEvaluator()

    reqs = TripRequirements(
        origin="Bengaluru",
        destination_venue="Unverified Remote Location",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )

    train = TrainService(
        train_number="12658",
        train_name="CHENNAI MAIL",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="22:40",
        arrival_time="04:35",
        duration_minutes=355,
        day_offset=1,
    )

    unknown_lm = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Unverified Remote Location",
        distance_km=None,
        duration_minutes=None,
        confidence="unknown",
    )

    ev = evaluator.evaluate_candidate(train=train, requirements=reqs, last_mile=unknown_lm)

    assert ev.is_feasible is False
    assert ev.match_category == "insufficient_data"
    assert ev.actual_arrival_buffer_minutes is None
    assert any("last-mile transit duration to venue is unknown" in v for v in ev.hard_constraint_violations)


def test_8_repeated_venue_resolution_uses_cache(tmp_path):
    """8. Repeated venue resolution uses SQLite cache with is_cached=True."""
    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    res1 = loc_service.resolve_location("Tidel Park, Chennai")
    assert res1.is_cached is False
    assert loc_service.geocoding_requests_count == 1
    assert loc_service.geocoding_cache_hits_count == 0

    res2 = loc_service.resolve_location("Tidel Park, Chennai")
    assert res2.is_cached is True
    assert loc_service.geocoding_requests_count == 2
    assert loc_service.geocoding_cache_hits_count == 1
    assert res2.latitude == res1.latitude
    assert res2.longitude == res1.longitude


def test_9_geocoding_does_not_consume_railradar_requests(tmp_path):
    """9. Geocoding and routing do not consume RailRadar requests."""
    quota_mgr = DurableRailRadarQuotaManager(db_path=tmp_path / "quota.sqlite")
    report_before = quota_mgr.get_usage_report()
    used_before = report_before.used_requests

    cache = LocationCacheManager(db_path=tmp_path / "loc_cache.sqlite")
    loc_service = LocationResolutionService(cache_manager=cache)

    # Perform multiple geocoding and routing calls
    loc = loc_service.resolve_location("Tidel Park, Chennai")
    stations = loc_service.find_nearby_stations(loc)
    for st in stations:
        loc_service.estimate_last_mile(st.station_code, "Tidel Park, Chennai", loc)

    report_after = quota_mgr.get_usage_report()
    used_after = report_after.used_requests

    assert used_after == used_before  # Zero RailRadar quota consumed
    assert loc_service.geocoding_requests_count >= 1
    assert loc_service.routing_requests_count >= len(stations)


def test_10_morning_meeting_feasibility_includes_rail_last_mile_and_buffer():
    """
    10. A morning meeting feasibility includes rail arrival, last-mile duration, and buffer.
    Formula: latest_station_arrival = meeting_time - buffer - last_mile_duration.
    """
    evaluator = JourneyFeasibilityEvaluator()

    # Meeting: 10:00 AM. Buffer: 45 min.
    # Required venue arrival: 09:15 AM (555 min from midnight).
    # Last mile from MAS to Tidel Park: 35 min.
    # Latest acceptable station arrival: 08:40 AM (520 min from midnight).
    reqs = TripRequirements(
        origin="Bengaluru",
        destination_venue="Tidel Park, Chennai",
        destination_city="Chennai",
        meeting_date="2026-10-15",
        meeting_time="10:00",
        required_arrival_buffer_minutes=45,
    )

    last_mile = LastMileEstimate(
        origin_station_code="MAS",
        destination_venue="Tidel Park, Taramani, Chennai",
        distance_km=16.0,
        duration_minutes=35,
        confidence="verified_estimate",
    )

    # Train A: Arrives at 08:30 AM -> Leaves 45m buffer + 10m buffer = 55m total buffer -> Feasible
    train_a = TrainService(
        train_number="20608",
        train_name="VANDE BHARAT EXP",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="05:45",
        arrival_time="08:30",
        duration_minutes=165,
        day_offset=0,
    )
    ev_a = evaluator.evaluate_candidate(train=train_a, requirements=reqs, last_mile=last_mile)
    assert ev_a.is_feasible is True
    assert "08:40" in ev_a.latest_acceptable_station_arrival_iso
    assert ev_a.actual_arrival_buffer_minutes == 55  # Arrives venue at 09:05, 55m before 10:00

    # Train B: Arrives at 09:00 AM -> Arrives venue at 09:35 AM (Only 25m buffer, needs 45m) -> Infeasible
    train_b = TrainService(
        train_number="12028",
        train_name="SHATABDI EXP",
        origin_station_code="SBC",
        origin_station_name="KSR Bengaluru",
        destination_station_code="MAS",
        destination_station_name="Chennai Central",
        departure_time="06:00",
        arrival_time="09:00",
        duration_minutes=180,
        day_offset=0,
    )
    ev_b = evaluator.evaluate_candidate(train=train_b, requirements=reqs, last_mile=last_mile)
    assert ev_b.is_feasible is False
    assert ev_b.actual_arrival_buffer_minutes == 25
    assert any("20 mins after the required station deadline (08:40)" in v for v in ev_b.hard_constraint_violations)


def test_11_planner_end_to_end_location_resolution():
    """11. End-to-end planner execution verifies venue resolution and evidence visibility."""
    planner = JourneyPlanner()
    reqs = parse_requirements_from_text("I have a meeting at Tidel Park, Chennai, at 10:00 AM on 15 Oct 2026")

    response = planner.plan_journey(reqs)

    assert response.status == "answered"
    assert response.resolved_destination is not None
    assert response.resolved_destination.city == "Chennai"
    assert "Taramani" in response.resolved_destination.display_name or "Taramani" in (response.resolved_destination.resolved_address or "")
    assert response.selected_station in ["MAS", "MS", "TBM"]
    assert response.last_mile_distance is not None and response.last_mile_distance > 5.0
    assert response.last_mile_duration_minutes is not None and response.last_mile_duration_minutes >= 15
    assert response.location_telemetry["railradar_http_calls_for_location"] == 0
