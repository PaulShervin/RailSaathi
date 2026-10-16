"""Navigation settings, read from the main backend configuration.

Same variable names as the original module (RAILSATHI_*), so they can be set in
backend/.env or the environment. Settings are re-read on every call so tests can
override them with monkeypatch (the original module's behaviour).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings as AppSettings

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "stations"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    admin_token: str | None
    public_disruption_simulation: bool
    cors_origins: list[str]
    walking_speed_mps: float
    max_backups: int


def get_settings() -> Settings:
    app = AppSettings()
    token = app.railsathi_admin_token.get_secret_value().strip() if app.railsathi_admin_token else ""
    data_dir = Path(app.railsathi_data_dir) if app.railsathi_data_dir else DEFAULT_DATA_DIR
    return Settings(
        data_dir=data_dir.resolve(),
        admin_token=token or None,
        public_disruption_simulation=app.railsathi_public_disruption_simulation,
        cors_origins=app.cors_origin_list,
        walking_speed_mps=app.railsathi_walking_speed_mps,
        max_backups=app.railsathi_max_backups,
    )
