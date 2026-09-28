"""System endpoints: liveness and version. Unauthenticated by design (used by health checks)."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict

from fleet_service import API_VERSION, __version__
from fleet_service.config import Settings

router = APIRouter(tags=["system"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


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


@router.get("/health")
async def health() -> Health:
    """Report that the service is up."""
    return Health(status="ok", server_time=datetime.now(UTC))


@router.get("/version")
async def version(settings: Annotated[Settings, Depends(_settings)]) -> VersionInfo:
    """Report the service and API versions and the ground station's name."""
    return VersionInfo(
        service="fleet-service",
        version=__version__,
        api_version=API_VERSION,
        station_name=settings.station_name,
    )
