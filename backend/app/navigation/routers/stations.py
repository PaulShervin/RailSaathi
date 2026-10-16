from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.navigation.config import get_settings
from app.navigation.models import Station, ValidationReport
from app.navigation.routers.deps import StationIdPath, ensure_station_exists, require_admin
from app.navigation.services import station_store
from app.navigation.services.route_validator import validate_station_data

router = APIRouter()


@router.get("/api/stations")
def list_stations() -> list[dict]:
    out = []
    for sid in station_store.list_station_ids():
        try:
            raw = station_store.load_raw(sid)
            meta = station_store.load_metadata(sid)
        except (station_store.StationNotFound, ValueError):
            continue
        out.append(
            {
                "station_id": sid,
                "station_name": raw.get("station_name", sid),
                "node_count": len(raw.get("nodes", [])),
                "edge_count": len(raw.get("edges", [])),
                "has_draft": station_store.has_draft(sid),
                "data_status": meta.data_status if meta else "unknown",
                "city": meta.city if meta else None,
            }
        )
    return out


@router.get("/api/admin/status")
def admin_status() -> dict:
    s = get_settings()
    return {
        "admin_writes_enabled": bool(s.admin_token),
        "public_disruption_simulation": s.public_disruption_simulation,
    }


@router.get("/api/stations/{station_id}")
def get_station(station_id: str = StationIdPath, draft: bool = Query(False)) -> dict:
    ensure_station_exists(station_id)
    source = "draft" if draft and station_store.has_draft(station_id) else "published"
    raw = station_store.load_raw(station_id, draft=source == "draft")
    meta = station_store.load_metadata(station_id)
    return {
        "station": raw,
        "metadata": meta.model_dump(mode="json") if meta else None,
        "source": source,
        "has_draft": station_store.has_draft(station_id),
    }


def _report(station_id: str, payload: Any) -> ValidationReport:
    return validate_station_data(payload, station_store.load_metadata(station_id), expected_station_id=station_id)


@router.get("/api/stations/{station_id}/info")
def station_info(station_id: str = StationIdPath) -> dict:
    """Helplines, station facts and amenities gathered from online references (with sources)."""
    ensure_station_exists(station_id)
    return station_store.load_info(station_id)


@router.post("/api/stations/{station_id}/validate", response_model=ValidationReport)
def validate_station(station_id: str = StationIdPath, payload: Any = Body(...)) -> ValidationReport:
    ensure_station_exists(station_id)
    return _report(station_id, payload)


@router.put("/api/stations/{station_id}", dependencies=[Depends(require_admin)])
def publish_station(station_id: str = StationIdPath, payload: Any = Body(...)) -> dict:
    """Validate and publish. Errors block the save; warnings are returned but allowed."""
    ensure_station_exists(station_id)
    report = _report(station_id, payload)
    if not report.valid:
        raise HTTPException(422, {"message": "Station data failed validation", "report": report.model_dump()})
    station = Station.model_validate(payload)
    backup = station_store.save_published(station)
    return {"saved": True, "backup": backup, "report": report.model_dump()}


@router.put("/api/stations/{station_id}/draft", dependencies=[Depends(require_admin)])
def save_draft(station_id: str = StationIdPath, payload: Any = Body(...)) -> dict:
    """Drafts may contain graph errors, but must be a JSON object with node and edge lists."""
    ensure_station_exists(station_id)
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise HTTPException(422, "Draft must be a JSON object containing 'nodes' and 'edges' lists.")
    station_store.save_draft(station_id, payload)
    return {"saved": True, "report": _report(station_id, payload).model_dump()}


@router.delete("/api/stations/{station_id}/draft", dependencies=[Depends(require_admin)])
def discard_draft(station_id: str = StationIdPath) -> dict:
    ensure_station_exists(station_id)
    return {"discarded": station_store.discard_draft(station_id)}


@router.get("/api/stations/{station_id}/versions", dependencies=[Depends(require_admin)])
def list_versions(station_id: str = StationIdPath) -> list[str]:
    ensure_station_exists(station_id)
    return station_store.list_backups(station_id)


@router.get("/api/stations/{station_id}/versions/{name}", dependencies=[Depends(require_admin)])
def get_version(name: str, station_id: str = StationIdPath) -> dict:
    ensure_station_exists(station_id)
    try:
        return station_store.load_backup(station_id, name)
    except station_store.StationNotFound:
        raise HTTPException(404, f"Unknown backup '{name}'")


@router.get("/data/stations/{station_id}/{filename}")
def station_image(filename: str, station_id: str = StationIdPath) -> FileResponse:
    try:
        return FileResponse(station_store.image_path(station_id, filename))
    except (station_store.StationNotFound, station_store.InvalidStationId):
        raise HTTPException(404, "Image not found")
