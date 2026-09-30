"""
Application factory.

Run with ``uvicorn --factory fleet_service.main:create_app`` or the
``fleet-service`` console script; tests build their own app with explicit settings,
clock and (cheap) password hasher.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.openapi.utils import get_openapi

from fleet_service import API_VERSION, __version__
from fleet_service.api import (
    aircraft,
    alerts,
    areas,
    audit_log,
    auth,
    commands,
    control,
    groups,
    incidents,
    live,
    missions,
    plans,
    pois,
    system,
    users,
    video_streams,
    ws,
)
from fleet_service.auth.passwords import Passwords
from fleet_service.clock import Clock, SystemClock
from fleet_service.config import Settings, get_settings
from fleet_service.context import AppContext
from fleet_service.db import migrate
from fleet_service.db.engine import Database
from fleet_service.errors import PROBLEM_JSON, install_error_handlers
from fleet_service.ids import new_id
from fleet_service.log import configure_logging
from fleet_service.services.runtime import Runtime

API_PREFIX = f"/api/{API_VERSION}"
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = logging.getLogger(__name__)

TAGS = [
    {"name": "system", "description": "Liveness and version; no authentication."},
    {"name": "auth", "description": "Sessions: login, logout, current user, own password."},
    {"name": "users", "description": "Operator accounts and roles."},
    {"name": "aircraft", "description": "The aircraft registry."},
    {"name": "groups", "description": "Named aircraft groups."},
    {"name": "incidents", "description": "SAR incidents and their operating areas."},
    {"name": "search areas", "description": "Areas to be searched."},
    {"name": "geofences", "description": "Inclusion and exclusion zones."},
    {"name": "missions", "description": "Missions and their waypoints."},
    {"name": "tasks", "description": "Aircraft assigned to missions."},
    {"name": "video streams", "description": "Video source configuration."},
    {"name": "live", "description": "Live fleet state, telemetry history, simulation faults."},
    {"name": "commands", "description": "Commands to aircraft, with confirmation (ADR 0011)."},
    {"name": "control", "description": "Control leases: take, release, hand over, assign."},
    {"name": "alerts", "description": "Operator alerts."},
    {"name": "audit", "description": "The tamper-evident audit trail."},
]


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    passwords: Passwords | None = None,
    start_loops: bool = True,
) -> FastAPI:
    """Build the ASGI application (``start_loops=False``: tests drive the runtime by hand)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    context = AppContext.build(settings, clock or SystemClock(), passwords or Passwords())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        report = await asyncio.to_thread(
            migrate.upgrade_all, settings.data_dir, context.clock.now()
        )
        if report.upgraded:
            log.info("database schema upgraded", extra={"upgraded": report.upgraded})
        context.db = Database(settings.data_dir)
        context.live = Runtime(settings, context.clock, context.db)
        await context.live.start(start_loops)
        try:
            yield
        finally:
            await context.live.stop()
            context.live = None
            await context.db.dispose()
            context.db = None

    app = FastAPI(
        title="SAR Fleet Service",
        summary="Ground fleet service for civilian search-and-rescue drone operations.",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    app.state.context = context
    install_error_handlers(app)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request.state.request_id = incoming if _REQUEST_ID.match(incoming) else new_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    for router in (
        system.router,
        auth.router,
        users.router,
        aircraft.router,
        groups.router,
        incidents.router,
        areas.search_areas,
        areas.geofences,
        missions.missions,
        missions.tasks,
        plans.router,
        pois.router,
        video_streams.router,
        video_streams.health_router,
        live.router,
        commands.router,
        control.router,
        alerts.router,
        audit_log.router,
        ws.router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = _problem_json_errors(
                get_openapi(
                    title=app.title,
                    version=app.version,
                    summary=app.summary,
                    routes=app.routes,
                    tags=app.openapi_tags,
                )
            )
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def _problem_json_errors(schema: dict[str, Any]) -> dict[str, Any]:
    """Document every 4xx/5xx response as ``application/problem+json`` (ADR 0013)."""
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            for status, response in operation.get("responses", {}).items():
                content = response.get("content", {})
                if status[0] in "45" and "application/json" in content:
                    content[PROBLEM_JSON] = content.pop("application/json")
    return schema
