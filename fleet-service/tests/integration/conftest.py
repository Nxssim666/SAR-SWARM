"""
Fixtures of the integration tests: the fleet service on the real clock, with its loops
running and real links, driven over REST (and WebSocket) as a console would.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.clock import SystemClock
from fleet_service.config import Settings
from fleet_service.domain.enums import Role
from fleet_service.main import create_app
from link_support import Station

from support import bearer, login


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="sitl",
        data_dir=data_dir,
        mavlink_links=True,
        link_stale_after_s=2.0,
        link_lost_after_s=6.0,
        command_timeout_s=5.0,
        command_effect_timeout_s=20.0,
        confirmation_ttl_s=60.0,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings, clock=SystemClock(), passwords=fast_passwords_for_tests(), start_loops=True
    )
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def station(client: httpx.AsyncClient, user_ids: dict[Role, str]) -> Station:
    del user_ids  # the users must exist before logging in
    return Station(client, bearer(await login(client, Role.SUPERVISOR.value)))
