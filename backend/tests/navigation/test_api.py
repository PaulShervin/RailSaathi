from __future__ import annotations

import json

from tests.navigation.conftest import synthetic_station


def _route(client, src, dst, station="chennai_central", **extra):
    body = {"station_id": station, "source": src, "destination": dst, **extra}
    return client.post("/api/navigation/route", json=body)


# --- stations ---------------------------------------------------------------


def test_list_stations_includes_seed_and_second_station(client):
    ids = {s["station_id"] for s in client.get("/api/stations").json()}
    assert {"chennai_central", "test_town"} <= ids


def test_get_station_returns_graph_and_metadata(client):
    body = client.get("/api/stations/chennai_central").json()
    assert body["station"]["station_id"] == "chennai_central"
    assert body["metadata"]["map_scale"]["metres_per_pixel"] > 0
    assert body["source"] == "published"


def test_unknown_station_is_404(client):
    assert client.get("/api/stations/nowhere").status_code == 404
    assert client.get("/api/stations/..%2Fetc").status_code in (404, 422)


def test_map_image_is_served_but_not_json(client):
    r = client.get("/data/stations/chennai_central/map.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/data/stations/chennai_central/station.json").status_code == 404


# --- protection -------------------------------------------------------------


def test_publish_requires_admin_token(client):
    raw = client.get("/api/stations/chennai_central").json()["station"]
    assert client.put("/api/stations/chennai_central", json=raw).status_code == 401
    assert client.put("/api/stations/chennai_central", json=raw, headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_writes_disabled_when_no_token_configured(client, monkeypatch):
    monkeypatch.delenv("RAILSATHI_ADMIN_TOKEN")
    raw = client.get("/api/stations/chennai_central").json()["station"]
    assert client.put("/api/stations/chennai_central", json=raw, headers={"X-Admin-Token": "x"}).status_code == 503


# --- save / reload / backups -----------------------------------------------


def test_publish_persists_and_creates_backup(client, admin, data_dir):
    raw = client.get("/api/stations/chennai_central").json()["station"]
    raw["nodes"][0]["name"] = "Renamed Entrance"
    r = client.put("/api/stations/chennai_central", json=raw, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["backup"]
    reloaded = client.get("/api/stations/chennai_central").json()["station"]
    assert reloaded["nodes"][0]["name"] == "Renamed Entrance"
    versions = client.get("/api/stations/chennai_central/versions", headers=admin).json()
    assert len(versions) == 1
    old = client.get(f"/api/stations/chennai_central/versions/{versions[0]}", headers=admin).json()
    assert old["nodes"][0]["name"] == "Main Entrance (Wall Tax Road)"


def test_invalid_graph_is_rejected_and_not_saved(client, admin, data_dir):
    before = (data_dir / "chennai_central" / "station.json").read_text()
    raw = json.loads(before)
    raw["edges"][0]["to"] = "missing_node"
    r = client.put("/api/stations/chennai_central", json=raw, headers=admin)
    assert r.status_code == 422
    assert r.json()["detail"]["report"]["errors"][0]["code"] == "unknown_node"
    assert (data_dir / "chennai_central" / "station.json").read_text() == before


def test_draft_is_saved_separately_and_cleared_on_publish(client, admin):
    raw = client.get("/api/stations/chennai_central").json()["station"]
    raw["edges"][0]["to"] = "half_traced"  # drafts may be invalid
    assert client.put("/api/stations/chennai_central/draft", json=raw, headers=admin).status_code == 200
    d = client.get("/api/stations/chennai_central?draft=true").json()
    assert d["source"] == "draft" and d["station"]["edges"][0]["to"] == "half_traced"
    assert client.get("/api/stations/chennai_central").json()["source"] == "published"
    good = client.get("/api/stations/chennai_central").json()["station"]
    client.put("/api/stations/chennai_central", json=good, headers=admin)
    assert client.get("/api/stations/chennai_central").json()["has_draft"] is False


def test_export_then_import_round_trip_preserves_graph(client, admin):
    exported = client.get("/api/stations/chennai_central").json()["station"]
    text = json.dumps(exported)  # what the Export button downloads
    r = client.put("/api/stations/chennai_central", json=json.loads(text), headers=admin)
    assert r.status_code == 200
    assert client.get("/api/stations/chennai_central").json()["station"] == exported


def test_validate_endpoint_reports_errors(client):
    raw = synthetic_station()
    raw["edges"][0]["geometry"][0] = [0.9, 0.9]
    r = client.post("/api/stations/test_town/validate", json=raw).json()
    assert r["valid"] is False
    assert r["errors"][0]["code"] == "geometry_start_mismatch"


# --- routing ----------------------------------------------------------------


def test_chennai_route_follows_saved_geometry(client):
    r = _route(client, "ent_wall_tax", "platform_9")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    station = client.get("/api/stations/chennai_central").json()["station"]
    edges = {e["id"]: e for e in station["edges"]}
    pts = set()
    for eid in body["edge_ids"]:
        pts |= {tuple(p) for p in edges[eid]["geometry"]}
    assert all(tuple(p) in pts for p in body["geometry"])
    assert len(body["geometry"]) > 2
    assert body["distance_basis"] == "estimated_from_map_scale"
    assert body["distance_m"] is None  # nothing measured; never invented


def test_chennai_wheelchair_route_is_unverified(client):
    body = _route(client, "ent_wall_tax", "ticketing", preferences={"wheelchair": True}).json()
    assert body["status"] == "ok"
    assert body["accessibility_confidence"] == "unverified"


def test_chennai_avoid_stairs_rejects_drawn_stairs(client):
    body = _route(client, "ent_jn_road", "platform_9", preferences={"avoid_stairs": True}).json()
    assert body["status"] == "no_route"
    assert body["reason"] == "accessibility_constraints"


def test_chennai_unconnected_facility_is_explained(client, admin):
    station = client.get("/api/stations/chennai_central").json()["station"]
    station["nodes"].append({"id": "new_kiosk", "name": "New Kiosk", "type": "shop",
                             "position": [0.5, 0.5], "verification": "pending"})
    assert client.put("/api/stations/chennai_central", json=station, headers=admin).status_code == 200
    body = _route(client, "ent_wall_tax", "new_kiosk").json()
    assert body["status"] == "no_route" and body["reason"] == "not_connected"
    assert "New Kiosk" in body["explanation"]


def test_chennai_suggested_pathways_are_flagged(client):
    body = _route(client, "ent_parking", "reserved_lounge").json()
    assert body["status"] == "ok"
    assert all(s["verification"] == "simulated" for s in body["segments"])
    assert any("not verified on site" in w for w in body["warnings"])


def test_second_station_routes_without_engine_changes(client):
    body = _route(client, "A", "D", station="test_town", preferences={"wheelchair": True}).json()
    assert body["status"] == "ok" and body["edge_ids"] == ["e_ac", "e_cd"]


def test_route_errors(client):
    assert _route(client, "ent_wall_tax", "nope").status_code == 404
    assert _route(client, "a", "b", station="nowhere").status_code == 404
    assert client.post("/api/navigation/route", json={"station_id": "chennai_central"}).status_code == 422
    assert _route(client, "a", "b", preferences={"fly": True}).status_code == 422


# --- disruptions ------------------------------------------------------------


def test_disruption_requires_access(client):
    r = client.post("/api/stations/chennai_central/disruptions", json={"target_type": "edge", "target_id": "edge_001"})
    assert r.status_code == 401


def test_disruption_public_mode(client, monkeypatch):
    monkeypatch.setenv("RAILSATHI_PUBLIC_DISRUPTION_SIMULATION", "true")
    r = client.post("/api/stations/chennai_central/disruptions", json={"target_type": "edge", "target_id": "edge_001"})
    assert r.status_code == 201


def test_closure_reroutes_and_can_be_removed(client, admin, data_dir):
    first = _route(client, "ent_wall_tax", "platform_9").json()
    blocked = first["edge_ids"][1]
    ev = client.post(
        "/api/stations/chennai_central/disruptions",
        json={"target_type": "edge", "target_id": blocked, "reason": "Simulated cleaning"},
        headers=admin,
    )
    assert ev.status_code == 201 and ev.json()["simulated"] is True
    listed = client.get("/api/stations/chennai_central/disruptions").json()
    assert [d["target_id"] for d in listed] == [blocked]

    second = _route(client, "ent_wall_tax", "platform_9", previous_edge_ids=first["edge_ids"]).json()
    assert second["status"] == "ok"
    assert blocked not in second["edge_ids"]
    assert second["previous_route_blocked"] is True
    assert second["simulated_disruptions_applied"] == [ev.json()["id"]]

    # station data (accessibility, status, geometry) untouched by the overlay
    station = client.get("/api/stations/chennai_central").json()["station"]
    edge = next(e for e in station["edges"] if e["id"] == blocked)
    assert edge["status"] == "open" and edge["accessible"] == "unknown"

    assert client.delete(f"/api/stations/chennai_central/disruptions/{ev.json()['id']}", headers=admin).status_code == 200
    assert client.get("/api/stations/chennai_central/disruptions").json() == []
    assert _route(client, "ent_wall_tax", "platform_9").json()["edge_ids"] == first["edge_ids"]


def test_closure_with_no_alternative_reports_no_route(client, admin):
    # Platform 9 has exactly one platform edge; closing it leaves no alternative.
    station = client.get("/api/stations/chennai_central").json()["station"]
    plat = next(e for e in station["edges"] if {e["from"], e["to"]} == {"p9_access", "platform_9"})
    client.post("/api/stations/chennai_central/disruptions", json={"target_type": "edge", "target_id": plat["id"]},
                headers=admin)
    body = _route(client, "ent_wall_tax", "platform_9").json()
    assert body["status"] == "no_route"
    assert body["reason"] == "blocked_by_closure"
    assert plat["id"] in body["blocking_edge_ids"]


def test_disruption_unknown_target(client, admin):
    r = client.post("/api/stations/chennai_central/disruptions", json={"target_type": "edge", "target_id": "zzz"},
                    headers=admin)
    assert r.status_code == 404
    assert client.delete("/api/stations/chennai_central/disruptions/nope", headers=admin).status_code == 404
