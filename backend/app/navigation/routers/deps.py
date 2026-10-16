"""Shared FastAPI dependencies: admin protection and station loading."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Path

from app.navigation.config import get_settings
from app.navigation.models import STATION_ID_PATTERN, Station
from app.navigation.services import station_store

StationIdPath = Path(pattern=STATION_ID_PATTERN, description="Station ID, e.g. chennai_central")


def _check_token(token: str | None) -> None:
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(503, "Admin writes are disabled: RAILSATHI_ADMIN_TOKEN is not configured on the server.")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Missing or invalid X-Admin-Token header.")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    _check_token(x_admin_token)


def require_simulation_access(x_admin_token: str | None = Header(default=None)) -> None:
    """Disruption simulation is admin-only unless explicitly opened for demos."""
    if get_settings().public_disruption_simulation:
        return
    _check_token(x_admin_token)


def ensure_station_exists(station_id: str) -> None:
    if station_id not in station_store.list_station_ids():
        raise HTTPException(404, f"Unknown station '{station_id}'")


def load_published(station_id: str) -> Station:
    ensure_station_exists(station_id)
    try:
        return station_store.load_station(station_id)
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise HTTPException(500, f"Published data for '{station_id}' is invalid: {exc}") from exc
