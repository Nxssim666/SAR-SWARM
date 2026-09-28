"""
Application factory.

Run with ``uvicorn --factory fleet_service.main:create_app`` or the
``fleet-service`` console script; tests build their own app with explicit settings.
"""

from fastapi import FastAPI

from fleet_service import API_VERSION, __version__
from fleet_service.api import system
from fleet_service.config import Settings, get_settings
from fleet_service.log import configure_logging

API_PREFIX = f"/api/{API_VERSION}"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="SAR Fleet Service",
        summary="Ground fleet service for civilian search-and-rescue drone operations.",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(system.router, prefix=API_PREFIX)
    return app
