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

    # --- simulation (ADR 0021) ---
    simulation: bool = Field(
        default=False,
        description="Back every registered aircraft with a simulated one; never mixed with "
        "real links. Shown to operators as a banner.",
    )
    sim_origin_latitude: float = Field(default=47.3977, ge=-80.0, le=80.0)
    sim_origin_longitude: float = Field(default=8.5456, ge=-180.0, le=180.0)
    sim_origin_altitude_amsl_m: float = Field(default=500.0, ge=-400.0, le=8000.0)
    sim_seed: int = Field(default=0, ge=0)

    # --- links and alerts (ADR 0010) ---
    mavlink_links: bool = Field(
        default=True,
        description="Open the MAVLink connections of registered aircraft (ADR 0022). Off in "
        "unit tests, which must not bind UDP ports; ignored in simulation mode.",
    )
    mavlink_threads: int = Field(
        default=64,
        ge=8,
        le=512,
        description="Threads for MAVSDK's blocking calls (arm, takeoff, hold...): at least "
        "the largest bulk command, so none waits for another aircraft's answer.",
    )
    nats_url: str | None = Field(
        default=None,
        description="NATS server of the swarm bridge (ADR 0024), e.g. nats://127.0.0.1:4222. "
        "Unset: no swarm link. Ignored in simulation mode.",
    )
    swarm_name: str = Field(
        default="default",
        pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$",
        description="The swarm's name in NATS subjects (sar.v1.swarm.<name>.*).",
    )
    swarm_grid_resolution_m: float = Field(
        default=5.0,
        gt=0.0,
        le=100.0,
        description="Coverage grid cell size sent with swarm missions (the onboard default).",
    )
    link_stale_after_s: float = Field(default=3.0, gt=0.0, le=60.0)
    link_lost_after_s: float = Field(default=15.0, gt=0.0, le=600.0)
    battery_low_pct: float = Field(default=30.0, ge=0.0, le=100.0)
    battery_critical_pct: float = Field(default=15.0, ge=0.0, le=100.0)
    return_reserve_pct: float = Field(
        default=10.0, ge=0.0, le=50.0, description="Battery kept in reserve on the way home."
    )
    alert_escalate_after_s: float = Field(
        default=60.0,
        ge=10.0,
        le=3600.0,
        description="An unacknowledged warning then turns critical.",
    )
    proximity_alert_m: float = Field(default=10.0, ge=1.0, le=500.0)
    proximity_alert_vertical_m: float = Field(default=5.0, ge=1.0, le=200.0)
    proximity_lookahead_s: float = Field(default=30.0, ge=1.0, le=300.0)

    # --- commands and control (ADR 0011) ---
    command_timeout_s: float = Field(default=5.0, gt=0.0, le=60.0)
    command_effect_timeout_s: float = Field(default=10.0, gt=0.0, le=120.0)
    command_min_interval_s: float = Field(default=0.25, ge=0.0, le=10.0)
    confirmation_ttl_s: float = Field(default=30.0, ge=5.0, le=300.0)
    handover_timeout_s: float = Field(default=30.0, ge=5.0, le=600.0)
    control_grace_s: float = Field(default=60.0, ge=5.0, le=3600.0)
    goto_confirm_distance_m: float = Field(default=1000.0, ge=0.0, le=100_000.0)
    goto_max_distance_m: float = Field(default=10_000.0, gt=0.0, le=100_000.0)
    max_altitude_relative_m: float = Field(
        default=120.0,
        gt=0.0,
        le=1500.0,
        description="Highest altitude above home a command may ask for (regulatory ceiling).",
    )
    min_takeoff_battery_pct: float = Field(default=40.0, ge=0.0, le=100.0)

    # --- mission planning and deconfliction (ADR 0028, ADR 0029, ADR 0030) ---
    terrain_dir: Path | None = Field(
        default=None,
        description="Directory of terrain grids (scripts/fetch_region.py); default "
        "<data_dir>/terrain. Without terrain, clearance is not checked and contour searches "
        "fall back to perimeter rings.",
    )
    multirotor_speed_mps: float = Field(default=10.0, gt=0.0, le=40.0)
    fixed_wing_speed_mps: float = Field(default=18.0, gt=0.0, le=60.0)
    multirotor_endurance_s: float = Field(default=1500.0, gt=0.0, le=86_400.0)
    fixed_wing_endurance_s: float = Field(default=3600.0, gt=0.0, le=86_400.0)
    fixed_wing_max_bank_deg: float = Field(default=30.0, ge=10.0, le=60.0)
    separation_horizontal_m: float = Field(default=50.0, ge=10.0, le=1000.0)
    separation_vertical_m: float = Field(default=15.0, ge=5.0, le=300.0)
    layer_spacing_m: float = Field(default=15.0, ge=5.0, le=100.0)
    multirotor_layers: int = Field(default=3, ge=1, le=10)
    airframe_band_m: float = Field(default=30.0, ge=0.0, le=300.0)
    min_terrain_clearance_m: float = Field(default=30.0, ge=5.0, le=500.0)
    max_height_agl_m: float = Field(
        default=120.0, gt=0.0, le=1500.0, description="Regulatory ceiling above ground."
    )
    departure_interval_s: float = Field(default=10.0, ge=0.0, le=300.0)
    max_start_delay_s: float = Field(default=600.0, ge=0.0, le=3600.0)
    mission_upload_timeout_s: float = Field(
        default=60.0,
        ge=5.0,
        le=600.0,
        description="How long a mission start may take: upload, read-back, start.",
    )
    goto_spread_m: float = Field(
        default=60.0, ge=10.0, le=1000.0, description="Distance between bulk-goto points."
    )

    # --- telemetry history and WebSocket ---
    telemetry_record_interval_s: float = Field(default=1.0, ge=0.1, le=60.0)
    ws_idle_timeout_s: float = Field(default=30.0, ge=5.0, le=600.0)

    @property
    def terrain_directory(self) -> Path:
        """Where terrain grids are read from."""
        return self.terrain_dir if self.terrain_dir is not None else self.data_dir / "terrain"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (read from the environment on first call)."""
    return Settings()
