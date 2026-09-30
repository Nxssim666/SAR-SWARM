"""The fleet service serving a built console itself (M6: the single-machine package)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.config import Settings
from fleet_service.main import create_app

from support import FakeClock


@pytest.fixture
def console(tmp_path: Path) -> Path:
    built = tmp_path / "dist"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text("<!doctype html><title>SAR Fleet Console</title>")
    (built / "assets" / "app.js").write_text("console.log('app');")
    (tmp_path / "secret.txt").write_text("not served")
    return built


@pytest.fixture
async def app(data_dir: Path, console: Path, clock: FakeClock) -> AsyncIterator[FastAPI]:
    settings = Settings(station_name="test-station", data_dir=data_dir, console_dir=console)
    application = create_app(
        settings, clock=clock, passwords=fast_passwords_for_tests(), start_loops=False
    )
    async with application.router.lifespan_context(application):
        yield application


async def test_the_console_and_its_assets_are_served_with_the_gateways_headers(
    client: httpx.AsyncClient,
) -> None:
    page = await client.get("/")
    asset = await client.get("/assets/app.js")

    assert page.status_code == 200
    assert "SAR Fleet Console" in page.text
    assert page.headers["cache-control"] == "no-cache"
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]


async def test_app_routes_get_the_page_and_the_api_keeps_its_own(
    client: httpx.AsyncClient,
) -> None:
    deep = await client.get("/incidents/123")
    health = await client.get("/api/v1/health")
    missing = await client.get("/api/v1/no-such-route")

    assert "SAR Fleet Console" in deep.text  # the single-page app routes it
    assert health.json()["status"] == "ok"
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"


async def test_nothing_outside_the_console_is_served(client: httpx.AsyncClient) -> None:
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = await client.get(path)
        assert "not served" not in response.text


def test_a_directory_without_a_built_console_is_refused(data_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not a built console"):
        create_app(Settings(data_dir=data_dir, console_dir=tmp_path))
