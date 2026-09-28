"""
Shared fixtures.

Each test gets its own copy of databases migrated once per session, an app running
its real lifespan (migration check, engines), a fake clock, a cheap password hasher,
and one logged-in user per role.
"""

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db import migrate
from fleet_service.db.engine import OPS_DB, TELEMETRY_DB
from fleet_service.domain.enums import Role
from fleet_service.main import create_app

from support import START, FakeClock, bearer, insert_user, login


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Databases at the newest schema, built once per test session."""
    template = tmp_path_factory.mktemp("template")
    migrate.upgrade_all(template, START)
    return template


@pytest.fixture
def data_dir(tmp_path: Path, migrated_template: Path) -> Path:
    """A private, migrated data directory."""
    for name in (OPS_DB, TELEMETRY_DB):
        shutil.copy(migrated_template / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Settings isolated from the developer's environment."""
    return Settings(station_name="test-station", data_dir=data_dir, log_json=True)


@pytest.fixture
def clock() -> FakeClock:
    """The app's clock."""
    return FakeClock()


@pytest.fixture
async def app(settings: Settings, clock: FakeClock) -> AsyncIterator[FastAPI]:
    """The application, with its lifespan running."""
    application = create_app(settings, clock=clock, passwords=fast_passwords_for_tests())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def context(app: FastAPI) -> AppContext:
    """The running app's context (database, clock, hasher)."""
    ctx: AppContext = app.state.context
    return ctx


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client that calls the app in-process."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def user_ids(context: AppContext) -> dict[Role, str]:
    """One active user per role, named after the role."""
    return {role: await insert_user(context, role.value, role) for role in Role}


@pytest.fixture
async def auth(client: httpx.AsyncClient, user_ids: dict[Role, str]) -> dict[Role, dict[str, str]]:
    """Authorization headers of a fresh session per role."""
    return {role: bearer(await login(client, role.value)) for role in user_ids}
