"""Fixtures for the merged station-navigation tests (originally Navigation_exp/railsathi-navigation)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]  # backend/  (data/ lives here after the merge)
ADMIN_TOKEN = "test-admin-token"


def _pt(x: float, y: float) -> list[float]:
    return [x, y]


def synthetic_station(station_id: str = "test_town") -> dict:
    """A small synthetic station used to exercise routing rules.

    Layout (normalized coords, 1000x1000 image):

        A(0.1,0.1) --e_ab walkway-- B(0.5,0.1) --e_bd stairs-- D(0.9,0.1)
        |                                                     |
        e_ac ramp (verified accessible)          e_cd walkway (verified accessible)
        |                                                     |
        C(0.1,0.9) -------------------------------------------+
        E(0.5,0.5) isolated
        B --e_bf one-way--> F(0.5,0.3)
    """
    nodes = [
        ("A", "Gate A", "entrance", (0.1, 0.1)),
        ("B", "Hall B", "concourse", (0.5, 0.1)),
        ("C", "Corner C", "junction", (0.1, 0.9)),
        ("D", "Platform D", "platform", (0.9, 0.1)),
        ("E", "Kiosk E", "shop", (0.5, 0.5)),
        ("F", "Exit F", "entrance", (0.5, 0.3)),
    ]

    def edge(eid, a, b, ptype, geom, accessible="unknown", **kw):
        e = {
            "id": eid, "from": a, "to": b, "bidirectional": True, "distance_m": None, "path_type": ptype,
            "steps": None, "accessible": accessible, "status": "open", "verification": "simulated",
            "geometry": [list(p) for p in geom],
        }
        e.update(kw)
        return e

    return {
        "schema_version": 1,
        "station_id": station_id,
        "station_name": "Test Town",
        "map": {"image": f"/data/stations/{station_id}/map.png", "width": 1000, "height": 1000,
                "coordinate_system": "normalized_image"},
        "nodes": [
            {"id": i, "name": n, "type": t, "position": list(p), "verification": "simulated"} for i, n, t, p in nodes
        ],
        "edges": [
            edge("e_ab", "A", "B", "walkway", [(0.1, 0.1), (0.3, 0.12), (0.5, 0.1)]),
            edge("e_bd", "B", "D", "stairs", [(0.5, 0.1), (0.9, 0.1)], accessible="not_accessible", steps=20),
            edge("e_ac", "A", "C", "ramp", [(0.1, 0.1), (0.1, 0.9)], accessible="verified"),
            edge("e_cd", "C", "D", "walkway", [(0.1, 0.9), (0.5, 0.9), (0.9, 0.9), (0.9, 0.1)], accessible="verified"),
            edge("e_bf", "B", "F", "walkway", [(0.5, 0.1), (0.5, 0.3)], bidirectional=False),
        ],
    }


@pytest.fixture()
def data_dir(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "stations"
    src = REPO / "data" / "stations" / "chennai_central"
    dst = root / "chennai_central"
    dst.mkdir(parents=True)
    for name in ("station.json", "metadata.json", "map.png", "info.json"):
        shutil.copy2(src / name, dst / name)
    second = root / "test_town"
    second.mkdir()
    (second / "station.json").write_text(json.dumps(synthetic_station()))
    monkeypatch.setenv("RAILSATHI_DATA_DIR", str(root))
    monkeypatch.setenv("RAILSATHI_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("RAILSATHI_PUBLIC_DISRUPTION_SIMULATION", "false")
    return root


@pytest.fixture()
def client(data_dir) -> TestClient:
    """The navigation routes served by the main RailSaathi app (demo planner data, no LLM)."""
    from app.config import Settings
    from app.container import build_container
    from app.main import create_app

    settings = Settings(_env_file=None, rate_limit_per_minute=10_000, llm_provider="none")
    return TestClient(create_app(settings, build_container(settings, use_configured_llm=False)))


@pytest.fixture()
def admin() -> dict:
    return {"X-Admin-Token": ADMIN_TOKEN}
