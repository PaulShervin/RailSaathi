from __future__ import annotations

import pytest

from app.navigation.models import Disruption, RouteRequest, Station
from app.navigation.services.graph_builder import build_graph
from app.navigation.services.route_validator import check_route_integrity
from app.navigation.services.routing_engine import RoutingError, find_route
from tests.navigation.conftest import synthetic_station


def _station(**overrides) -> Station:
    return Station.model_validate(synthetic_station())


def _route(station, src, dst, disruptions=(), **prefs):
    graph = build_graph(station, None, disruptions)
    return find_route(graph, RouteRequest(station_id=station.station_id, source=src, destination=dst, preferences=prefs))


def _closure(target, target_type="edge"):
    from datetime import datetime, timezone

    return Disruption(id=f"sim_{target}", station_id="test_town", target_type=target_type, target_id=target,
                      kind="pathway_closure" if target_type == "edge" else "facility_outage",
                      reason="test closure", created_at=datetime.now(timezone.utc))


def test_shortest_path_returns_connected_route():
    st = _station()
    r = _route(st, "A", "D")
    assert r.status == "ok"
    assert r.node_ids == ["A", "B", "D"]
    assert r.edge_ids == ["e_ab", "e_bd"]
    assert check_route_integrity(st, r.node_ids, r.edge_ids, r.geometry) == []


def test_geometry_is_concatenated_polylines_without_duplicate_junction_points():
    st = _station()
    r = _route(st, "A", "D")
    assert [tuple(p) for p in r.geometry] == [(0.1, 0.1), (0.3, 0.12), (0.5, 0.1), (0.9, 0.1)]
    # never a straight source->destination line when the traced path bends
    assert len(r.geometry) > 2


def test_reverse_traversal_reverses_geometry():
    st = _station()
    r = _route(st, "D", "A")
    assert r.edge_ids == ["e_bd", "e_ab"]
    assert [tuple(p) for p in r.geometry] == [(0.9, 0.1), (0.5, 0.1), (0.3, 0.12), (0.1, 0.1)]
    assert check_route_integrity(st, r.node_ids, r.edge_ids, r.geometry) == []


def test_avoid_stairs_rejects_stairs_edge():
    r = _route(_station(), "A", "D", avoid_stairs=True)
    assert r.status == "ok"
    assert "e_bd" not in r.edge_ids
    assert r.edge_ids == ["e_ac", "e_cd"]


def test_wheelchair_route_with_all_verified_edges_reports_verified():
    r = _route(_station(), "A", "D", wheelchair=True)
    assert r.edge_ids == ["e_ac", "e_cd"]
    assert r.accessibility_confidence == "verified"


def test_unknown_accessibility_is_not_presented_as_verified():
    r = _route(_station(), "A", "B", wheelchair=True)
    assert r.status == "ok"
    assert r.accessibility_confidence == "unverified"
    assert any("UNKNOWN accessibility" in w for w in r.warnings)


def test_require_verified_excludes_unknown_edges():
    r = _route(_station(), "A", "B", wheelchair=True, require_verified_accessibility=True)
    assert r.status == "no_route"
    assert r.reason == "accessibility_constraints"
    assert "e_ab" in r.blocking_edge_ids


def test_hard_constraint_not_overridden_by_low_cost():
    # e_bd is far cheaper than the detour but is not accessible; wheelchair must never use it
    st = _station()
    r = _route(st, "A", "D", [_closure("e_cd")], wheelchair=True)
    assert r.status == "no_route"
    assert r.reason == "accessibility_constraints"
    assert "e_bd" in r.blocking_edge_ids
    assert "No verified suitable route" in r.explanation


def test_closed_edge_causes_alternative_route():
    r = _route(_station(), "A", "D", [_closure("e_bd")])
    assert r.status == "ok"
    assert r.edge_ids == ["e_ac", "e_cd"]


def test_closures_with_no_alternative_report_no_route():
    r = _route(_station(), "A", "D", [_closure("e_bd"), _closure("e_cd")])
    assert r.status == "no_route"
    assert r.reason == "blocked_by_closure"
    assert set(r.blocking_edge_ids) & {"e_bd", "e_cd"}


def test_node_outage_blocks_routes_through_it():
    r = _route(_station(), "A", "D", [_closure("B", "node")])
    assert r.edge_ids == ["e_ac", "e_cd"]
    r2 = _route(_station(), "A", "B", [_closure("B", "node")])
    assert r2.status == "no_route" and r2.reason == "endpoint_closed"


def test_disruption_does_not_change_accessibility_or_source_data():
    st = _station()
    graph = build_graph(st, None, [_closure("e_ac")])
    assert graph.edges["e_ac"].status == "closed"
    assert graph.edges["e_ac"].accessible == "verified"
    original = next(e for e in st.edges if e.id == "e_ac")
    assert original.status == "open"


def test_isolated_destination_is_explained():
    r = _route(_station(), "A", "E")
    assert r.status == "no_route"
    assert r.reason == "not_connected"
    assert "Kiosk E" in r.explanation


def test_one_way_edge_is_respected():
    st = _station()
    assert _route(st, "B", "F").status == "ok"
    back = _route(st, "F", "B")
    assert back.status == "no_route"


def test_unknown_node_raises():
    with pytest.raises(RoutingError) as exc:
        _route(_station(), "A", "ZZZ")
    assert exc.value.status_code == 404


def test_previous_route_blocked_is_reported():
    st = _station()
    graph = build_graph(st, None, [_closure("e_bd")])
    r = find_route(graph, RouteRequest(station_id="test_town", source="A", destination="D",
                                       previous_edge_ids=["e_ab", "e_bd"]))
    assert r.previous_route_blocked
    assert r.previous_route_blocked_edge_ids == ["e_bd"]
    assert r.warnings[0].startswith("SIMULATED DISRUPTION")


def test_distance_unavailable_without_scale_or_measurements():
    r = _route(_station(), "A", "D")
    assert r.distance_m is None
    assert r.estimated_distance_m is None
    assert r.distance_basis == "unavailable"
    assert r.estimated_duration_s is None


def test_measured_distances_are_summed():
    raw = synthetic_station()
    for e in raw["edges"]:
        e["distance_m"] = 10.0
    r = _route(Station.model_validate(raw), "A", "D")
    assert r.distance_m == 20.0
    assert r.distance_basis == "measured"
    assert r.estimated_duration_s is not None


def test_instructions_cover_every_segment_and_arrival():
    r = _route(_station(), "A", "D")
    assert len(r.instructions) == len(r.edge_ids) + 1
    assert r.instructions[0].text.startswith("Start at Gate A")
    assert "stairs" in r.instructions[1].text
    assert r.instructions[-1].text == "Arrive at Platform D."
