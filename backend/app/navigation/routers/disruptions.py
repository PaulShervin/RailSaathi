from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.navigation.models import Disruption, DisruptionCreate
from app.navigation.routers.deps import StationIdPath, ensure_station_exists, load_published, require_simulation_access
from app.navigation.services import disruption_store

router = APIRouter()


@router.get("/api/stations/{station_id}/disruptions", response_model=list[Disruption])
def list_disruptions(station_id: str = StationIdPath) -> list[Disruption]:
    ensure_station_exists(station_id)
    return disruption_store.list_disruptions(station_id)


@router.post(
    "/api/stations/{station_id}/disruptions",
    response_model=Disruption,
    status_code=201,
    dependencies=[Depends(require_simulation_access)],
)
def create_disruption(req: DisruptionCreate, station_id: str = StationIdPath) -> Disruption:
    station = load_published(station_id)
    try:
        return disruption_store.create_disruption(station, req)
    except disruption_store.DisruptionTargetNotFound as exc:
        raise HTTPException(404, str(exc))


@router.delete(
    "/api/stations/{station_id}/disruptions/{event_id}",
    dependencies=[Depends(require_simulation_access)],
)
def delete_disruption(event_id: str, station_id: str = StationIdPath) -> dict:
    ensure_station_exists(station_id)
    if not disruption_store.delete_disruption(station_id, event_id):
        raise HTTPException(404, f"Unknown disruption '{event_id}'")
    return {"deleted": event_id}


@router.delete("/api/stations/{station_id}/disruptions", dependencies=[Depends(require_simulation_access)])
def clear_disruptions(station_id: str = StationIdPath) -> dict:
    ensure_station_exists(station_id)
    return {"cleared": disruption_store.clear_disruptions(station_id)}
