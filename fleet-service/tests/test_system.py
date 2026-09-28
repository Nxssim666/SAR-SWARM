"""System endpoints and application wiring."""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from fleet_service import __version__
from fleet_service.config import Settings
from fleet_service.log import JsonFormatter


async def test_health_reports_ok_and_current_utc_time(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    server_time = datetime.fromisoformat(body["server_time"])
    assert server_time.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - server_time) < timedelta(seconds=5)


async def test_version_reports_service_api_and_station(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "service": "fleet-service",
        "version": __version__,
        "api_version": "v1",
        "station_name": "test-station",
    }


async def test_openapi_is_served_under_versioned_prefix(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"/api/v1/health", "/api/v1/version"} <= set(paths)


async def test_unknown_path_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARGCS_STATION_NAME", "base-camp")
    monkeypatch.setenv("SARGCS_PORT", "9001")

    settings = Settings()

    assert settings.station_name == "base-camp"
    assert settings.port == 9001
    assert settings.host == "127.0.0.1"  # loopback unless explicitly exposed


def test_settings_reject_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARGCS_PORT", "70000")

    with pytest.raises(ValueError, match="port"):
        Settings()


def test_json_formatter_emits_one_line_with_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"name": "fleet", "levelname": "WARNING", "msg": "link lost %s", "args": ("A7",)}
    )
    record.aircraft_id = "A7"

    line = JsonFormatter().format(record)

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["msg"] == "link lost A7"
    assert payload["level"] == "WARNING"
    assert payload["aircraft_id"] == "A7"
    assert payload["ts"].endswith("+00:00")
