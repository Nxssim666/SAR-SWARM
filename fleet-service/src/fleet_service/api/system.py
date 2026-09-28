"""System endpoints: liveness and version. Unauthenticated by design (used by health checks)."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, ConfigDict

from fleet_service import API_VERSION, __version__
from fleet_service.api.deps import Context

router = APIRouter(tags=["system"])


class Health(BaseModel):
    """Liveness of the service. ``server_time`` lets clients detect clock skew."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    server_time: AwareDatetime


class VersionInfo(BaseModel):
    """What is running, for operators and bug reports."""

    model_config = ConfigDict(extra="forbid")

    service: Literal["fleet-service"]
    version: str
    api_version: str
    station_name: str
    simulation: bool


@router.get("/health")
async def health() -> Health:
    """Report that the service is up."""
    return Health(status="ok", server_time=datetime.now(UTC))


@router.get("/version")
async def version(context: Context) -> VersionInfo:
    """Report the service and API versions and the ground station's name."""
    return VersionInfo(
        service="fleet-service",
        version=__version__,
        api_version=API_VERSION,
        station_name=context.settings.station_name,
        simulation=context.settings.simulation,
    )
