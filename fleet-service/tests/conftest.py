"""Shared fixtures: an app built from explicit settings and an in-process HTTP client."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.config import Settings
from fleet_service.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings isolated from the developer's environment and data directory."""
    return Settings(station_name="test-station", data_dir=tmp_path, log_json=True)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """The application under test."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client that calls the app in-process (no sockets)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
