"""
Service settings, read once from ``SARGCS_*`` environment variables.

Defaults are safe for a developer laptop: the API listens on loopback only.
The container image overrides the host so the reverse proxy can reach it.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Every tunable of the fleet service; one field per ``SARGCS_<NAME>`` variable."""

    model_config = SettingsConfigDict(env_prefix="SARGCS_", extra="forbid", frozen=True)

    station_name: str = Field(
        default="ground-station-1",
        min_length=1,
        max_length=64,
        description="Human-readable name of this ground station, shown to operators.",
    )
    host: str = Field(default="127.0.0.1", description="Interface the API listens on.")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    log_json: bool = Field(default=True, description="JSON log lines (false: human-readable).")
    data_dir: Path = Field(
        default=Path("data"),
        description="Directory for the operational and telemetry databases.",
    )

    session_idle_timeout_s: int = Field(
        default=4 * 3600, ge=60, description="A session unused for this long expires."
    )
    session_max_lifetime_s: int = Field(
        default=12 * 3600, ge=300, description="A session expires this long after login (a shift)."
    )
    login_max_failures_per_user: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=20, ge=1)
    login_failure_window_s: int = Field(default=300, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (read from the environment on first call)."""
    return Settings()
