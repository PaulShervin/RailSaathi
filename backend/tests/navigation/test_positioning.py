"""Routing from a free position (GPS / mock GPS / 'start here'), snapping, along-the-way, station info."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.navigation.models import RouteRequest, Station
from app.navigation.services.graph_builder import VIRTUAL_SOURCE, build_graph
from app.navigation.services.routing_engine import find_route
from tests.navigation.conftest import synthetic_station


def _req(**kw):
    return RouteRequest(station_id="test_town", destination=kw.pop("destination", "D"), **kw)


def test_route_from_position_starts_part_way_along_stored_edge():
    st = Station.model_validate(synthetic_station())
    r = find_route(build_graph(st), _req(source_position=(0.3, 0.13)))
    assert r.status == "ok"
    assert r.node_ids[0] == VIRTUAL_SOURCE
    assert r.edge_ids == ["e_ab", "e_bd"]
    assert r.segments[0].partial is True
    # snapped onto the traced polyline vertex (0.3, 0.12), never a straight line to D
    assert tuple(r.geometry[0]) == pytest.approx((0.3, 0.12), abs=1e-6)
    assert [tuple(p) for p in r.geometry[1:]] == [(0.5, 0.1), (0.9, 0.1)]
    assert r.start_snap.edge_id == "e_ab" and r.start_snap.within_tolerance
    assert r.instructions[0].text.startswith("Start at your current position")


def test_position_far_from_any_walkway_is_rejected_with_explanation():
    st = Station.model_validate(synthetic_station())
    r = find_route(build_graph(st), _req(source_position=(0.5, 0.6)))
    assert r.status == "no_route"
    assert r.reason == "position_not_on_walkway"
    assert "beyond the allowed snapping distance" in r.explanation


def test_snapping_ignores_closed_pathways():
    from datetime import datetime, timezone

    from app.navigation.models import Disruption

    st = Station.model_validate(synthetic_station())
    closed = Disruption(id="x", station_id="test_town", target_type="edge", target_id="e_ab",
                        kind="pathway_closure", reason="t", created_at=datetime.now(timezone.utc))
    r = find_route(build_graph(st, None, [closed]), _req(source_position=(0.12, 0.2), max_snap_distance_m=200))
    assert r.start_snap.edge_id == "e_ac"


def test_exactly_one_source_required():
    with pytest.raises(ValidationError):
        _req(source="A", source_position=(0.1, 0.1))
    with pytest.raises(ValidationError):
        _req()


def test_api_route_from_mock_gps_position(client):
    body = client.post("/api/navigation/route", json={
        "station_id": "chennai_central", "source_position": [0.43, 0.497], "source_position_origin": "mock_gps",
        "destination": "platform_10"}).json()
    assert body["status"] == "ok"
    assert body["source"] == "current_position"
    assert body["source_position_origin"] == "mock_gps"
    assert "MOCK GPS" in body["warnings"][0]


def test_api_snap(client):
    r = client.post("/api/navigation/snap", json={"station_id": "chennai_central", "position": [0.4, 0.5]})
    body = r.json()
    assert r.status_code == 200
    assert body["within_tolerance"] is True
    assert body["distance_m"] is not None
    assert client.post("/api/navigation/snap", json={"station_id": "chennai_central", "position": [2, 0]}).status_code == 422


def test_along_the_way_lists_nearby_facilities_in_order(client):
    body = client.post("/api/navigation/route", json={
        "station_id": "chennai_central", "source": "ent_wall_tax", "destination": "platform_10"}).json()
    names = [i["node_id"] for i in body["along_the_way"]]
    assert "info_desk" in names
    progress = [i["progress"] for i in body["along_the_way"]]
    assert progress == sorted(progress)
    assert all(i["node_id"] != "platform_10" for i in body["along_the_way"])


def test_station_info_has_sourced_helplines(client):
    info = client.get("/api/stations/chennai_central/info").json()
    assert info["helplines"][0]["number"] in {"139", "112"}
    numbers = {h["number"] for h in info["helplines"]}
    assert {"139", "112"} <= numbers
    assert "182" not in numbers  # withdrawn; listed under not_used instead
    assert all(h["sources"] for h in info["helplines"])
    assert any(a["mapped"] is False for a in info["amenities"])
    # a station without info.json still gets national helplines
    assert client.get("/api/stations/test_town/info").json()["helplines"]
