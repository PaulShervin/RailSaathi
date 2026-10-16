from __future__ import annotations

import copy

from app.navigation.services.route_validator import validate_station_data
from tests.navigation.conftest import synthetic_station


def _codes(report, level="errors"):
    return {i.code for i in getattr(report, level)}


def test_synthetic_station_is_valid_with_isolated_warning():
    r = validate_station_data(synthetic_station())
    assert r.valid
    assert "isolated_node" in _codes(r, "warnings")


def test_duplicate_ids_are_errors():
    raw = synthetic_station()
    raw["nodes"].append(copy.deepcopy(raw["nodes"][0]))
    raw["edges"].append(copy.deepcopy(raw["edges"][0]))
    r = validate_station_data(raw)
    assert not r.valid
    assert {"duplicate_node_id", "duplicate_edge_id"} <= _codes(r)


def test_unknown_node_reference_is_error():
    raw = synthetic_station()
    raw["edges"][0]["to"] = "NOPE"
    r = validate_station_data(raw)
    assert "unknown_node" in _codes(r)


def test_geometry_must_start_and_end_at_nodes():
    raw = synthetic_station()
    raw["edges"][0]["geometry"][0] = [0.2, 0.2]
    raw["edges"][0]["geometry"][-1] = [0.6, 0.6]
    r = validate_station_data(raw)
    assert {"geometry_start_mismatch", "geometry_end_mismatch"} <= _codes(r)


def test_invalid_coordinates_are_errors():
    raw = synthetic_station()
    raw["nodes"][4]["position"] = [1.4, -0.2]
    r = validate_station_data(raw)
    assert "invalid_coordinates" in _codes(r)


def test_missing_accessibility_status_is_error():
    raw = synthetic_station()
    del raw["edges"][0]["accessible"]
    r = validate_station_data(raw)
    assert not r.valid
    assert any("accessibility status is required" in e.message for e in r.errors)
    assert r.errors[0].edge_id == "e_ab"


def test_verified_accessible_stairs_is_contradiction():
    raw = synthetic_station()
    raw["edges"][1]["accessible"] = "verified"
    r = validate_station_data(raw)
    assert "contradictory_accessibility" in _codes(r)


def test_malformed_connection_self_loop():
    raw = synthetic_station()
    raw["edges"][0]["to"] = "A"
    raw["edges"][0]["geometry"][-1] = [0.1, 0.1]
    r = validate_station_data(raw)
    assert "self_loop" in _codes(r)


def test_disconnected_component_and_long_segment_warnings():
    raw = synthetic_station()
    raw["nodes"].append({"id": "G", "name": "G", "type": "junction", "position": [0.6, 0.6], "verification": "pending"})
    raw["nodes"].append({"id": "H", "name": "H", "type": "junction", "position": [0.7, 0.6], "verification": "pending"})
    raw["edges"].append({"id": "e_gh", "from": "G", "to": "H", "path_type": "walkway", "accessible": "unknown",
                         "status": "open", "verification": "pending", "geometry": [[0.6, 0.6], [0.7, 0.6]]})
    r = validate_station_data(raw)
    assert r.valid
    warn = _codes(r, "warnings")
    assert "disconnected_component" in warn
    assert "long_straight_segment" in warn  # e_cd/e_ac span most of the image in one segment


def test_not_an_object_is_schema_error():
    r = validate_station_data([1, 2, 3])
    assert not r.valid and r.errors[0].code == "schema"


def test_seeded_chennai_central_is_valid():
    from app.navigation.services import station_store

    r = validate_station_data(station_store.load_raw("chennai_central"), station_store.load_metadata("chennai_central"))
    assert r.valid, [e.message for e in r.errors]
