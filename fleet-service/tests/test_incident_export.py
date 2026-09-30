"""The incident export bundle (M6): one zip with everything about an incident."""

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.domain.enums import Role
from live_support import Sim, confirmed, register, take

from factories import create, incident, mission, search_area
from support import FakeClock


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


async def test_the_bundle_holds_the_incident_its_trail_and_its_telemetry(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    clock: FakeClock,
) -> None:
    supervisor, operator = auth[Role.SUPERVISOR], auth[Role.OPERATOR]
    sim = Sim(context.runtime(), clock)
    case = await incident(client, supervisor)
    await search_area(client, supervisor, case["id"])
    plan = await mission(client, supervisor, case["id"])
    hexa = await register(client, supervisor, "HX-1")
    other = await register(client, supervisor, "HX-2")  # not involved: no telemetry exported
    await create(client, "tasks", supervisor, {"mission_id": plan["id"], "aircraft_id": hexa})
    await take(client, operator, hexa)
    await sim.fly(1)
    await confirmed(client, operator, "arm", [hexa])
    for _ in range(3):
        await sim.fly(1)
        await context.runtime().record()

    response = await client.get(f"/api/v1/incidents/{case['id']}/export", headers=supervisor)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert f"incident-{case['id']}-" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert set(manifest["files"]) == {
        "incident.json",
        "search-areas.geojson",
        "geofences.geojson",
        "pois.geojson",
        "missions.json",
        "alerts.json",
        "commands.json",
        "audit.jsonl",
        "audit-chain.json",
        "telemetry.csv",
    }
    for name, entry in manifest["files"].items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == entry["sha256"]
    assert manifest["aircraft"] == [hexa]
    assert json.loads(archive.read("incident.json"))["name"] == case["name"]
    areas = json.loads(archive.read("search-areas.geojson"))
    assert areas["features"][0]["geometry"]["type"] == "Polygon"
    missions = json.loads(archive.read("missions.json"))
    assert [t["aircraft_id"] for t in missions[0]["tasks"]] == [hexa]
    commands = json.loads(archive.read("commands.json"))
    assert [(c["kind"], c["targets"][0]["state"]) for c in commands] == [("arm", "verified")]
    actions = [json.loads(line)["action"] for line in archive.read("audit.jsonl").splitlines()]
    assert "incident.create" in actions
    assert actions[-1] == "incident.export"
    assert json.loads(archive.read("audit-chain.json"))["ok"] is True
    rows = list(csv.DictReader(io.StringIO(archive.read("telemetry.csv").decode())))
    assert len(rows) >= 3
    assert {r["aircraft_id"] for r in rows} == {hexa}
    assert other not in {r["aircraft_id"] for r in rows}


async def test_only_those_who_read_the_audit_trail_may_export(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    case = await incident(client, auth[Role.SUPERVISOR])

    denied = await client.get(f"/api/v1/incidents/{case['id']}/export", headers=auth[Role.OPERATOR])
    missing = await client.get("/api/v1/incidents/nope/export", headers=auth[Role.SUPERVISOR])

    assert denied.status_code == 403
    assert missing.status_code == 404
