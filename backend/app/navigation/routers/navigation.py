from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.navigation.config import get_settings
from app.navigation.models import RouteRequest, RouteResponse, SnapRequest, SnapResult, Station
from app.navigation.routers.deps import load_published
from app.navigation.services import disruption_store, station_store
from app.navigation.services.geometry import project_to_polyline
from app.navigation.services.graph_builder import StationGraph, build_graph, snap_to_walkway
from app.navigation.services.route_validator import check_route_integrity, validate_graph
from app.navigation.services.routing_engine import RoutingError, find_route, snap_result

router = APIRouter()


def _graph(station_id: str, apply_disruptions: bool = True) -> tuple[Station, StationGraph]:
    station = load_published(station_id)
    metadata = station_store.load_metadata(station_id)
    errors, _ = validate_graph(station, metadata)
    if errors:
        raise HTTPException(
            422,
            {"message": "Station graph is invalid; fix it in the editor before routing.",
             "errors": [e.model_dump() for e in errors]},
        )
    disruptions = disruption_store.list_disruptions(station_id) if apply_disruptions else []
    return station, build_graph(station, metadata, disruptions)


def _verify(station: Station, resp: RouteResponse) -> list[str]:
    """Refuse any geometry that is not exactly the stored polylines."""
    if not resp.segments or not resp.segments[0].partial:
        return check_route_integrity(station, resp.node_ids, resp.edge_ids, resp.geometry)
    # Route starts part-way along an edge: that piece must lie on the stored polyline.
    first = resp.segments[0]
    edge = next((e for e in station.edges if e.id == first.edge_id), None)
    if edge is None:
        return [f"unknown edge {first.edge_id}"]
    w, h = station.map.width, station.map.height
    if any(project_to_polyline(edge.geometry, p, w, h)[0] > 1.0 for p in first.geometry):
        return [f"partial segment does not lie on {edge.id}"]
    rest = resp.geometry[len(first.geometry) - 1 :]
    return check_route_integrity(station, resp.node_ids[1:], resp.edge_ids[1:], rest) if len(resp.edge_ids) > 1 else []


@router.post("/api/navigation/route", response_model=RouteResponse)
def calculate_route(req: RouteRequest) -> RouteResponse:
    station, graph = _graph(req.station_id, req.apply_disruptions)
    try:
        resp = find_route(graph, req, get_settings().walking_speed_mps)
    except RoutingError as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    if resp.status == "ok":
        problems = _verify(station, resp)
        if problems:  # should never happen; refuse to return a route we cannot vouch for
            raise HTTPException(500, {"message": "Route integrity check failed", "problems": problems})
    return resp


@router.post("/api/navigation/snap", response_model=SnapResult)
def snap_position(req: SnapRequest) -> SnapResult:
    """Match a free position (GPS / tap) to the nearest open traced walkway."""
    if not all(0 <= v <= 1 for v in req.position):
        raise HTTPException(422, "position must be normalized coordinates between 0 and 1")
    _, graph = _graph(req.station_id)
    snap = snap_to_walkway(graph, tuple(req.position), req.max_snap_distance_m)
    if snap is None:
        raise HTTPException(422, "This station has no open traced walkways.")
    return snap_result(graph, snap)
