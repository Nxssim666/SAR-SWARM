"""
Mission plans over the API (ADR 0028, ADR 0029): dry runs, saving, and refusals.

Simulation mode gives the aircraft positions and homes, as live telemetry would.
"""

import asyncio
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent, Mission
from fleet_service.domain.enums import Role
from fleet_service.domain.patterns.spacing import lane_spacing_m
from live_support import Sim, register

from factories import BASE, create, incident, mission, search_area, square, waypoint
from support import FakeClock

MISSIONS = "/api/v1/missions"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def setup(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> dict[str, Any]:
    """An incident, a 1.1 km square area, an area-search mission, three aircraft."""
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    search = await create(
        client,
        "missions",
        auth[Role.OPERATOR],
        {
            "incident_id": inc["id"],
            "name": "Grid",
            "kind": "area_search",
            "search_area_id": area["id"],
            "default_altitude_relative_m": 60.0,
        },
    )
    ids = [
        await register(client, auth[Role.SUPERVISOR], "HX-1"),
        await register(client, auth[Role.SUPERVISOR], "HX-2"),
        await register(client, auth[Role.SUPERVISOR], "FW-1", airframe="fixed_wing"),
    ]
    await sim.fly(1)
    return {"incident": inc, "area": area, "mission": search, "aircraft": ids}


async def post_plan(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    mission_id: str,
    body: dict[str, Any],
    dry_run: bool = False,
) -> httpx.Response:
    return await client.post(
        f"{MISSIONS}/{mission_id}/plan",
        params={"dry_run": "true"} if dry_run else None,
        json=body,
        headers=headers,
    )


async def test_a_dry_run_splits_the_area_covers_it_and_saves_nothing(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], setup: dict[str, Any]
) -> None:
    mission_id = setup["mission"]["id"]

    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        mission_id,
        {"pattern": "parallel_track", "spacing_m": 60.0, "aircraft_ids": setup["aircraft"]},
        dry_run=True,
    )

    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["dry_run"] is True
    assert plan["clear"] is True, plan["conflicts"]
    assert plan["coverage"] >= 0.99
    assert sorted(t["callsign"] for t in plan["tasks"]) == ["FW-1", "HX-1", "HX-2"]
    strips = sum(t["strip_area_m2"] for t in plan["tasks"])
    assert strips == pytest.approx(plan["area_m2"], rel=1e-3)
    # The airplane flies a band above the multirotors' layers.
    layers = {t["callsign"]: t["layer_m"] for t in plan["tasks"]}
    assert layers["FW-1"] >= max(layers["HX-1"], layers["HX-2"]) + 30.0
    saved = await client.get(f"{MISSIONS}/{mission_id}/plan", headers=auth[Role.OBSERVER])
    assert saved.json()["type"] == "urn:sar-gcs:problem:no-plan"
    status = await client.get(f"{MISSIONS}/{mission_id}", headers=auth[Role.OBSERVER])
    assert status.json()["status"] == "draft"


async def test_saving_a_plan_gives_each_task_its_route_and_audits_it(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    setup: dict[str, Any],
) -> None:
    mission_id = setup["mission"]["id"]

    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        mission_id,
        {"pattern": "creeping_line", "spacing_m": 80.0, "aircraft_ids": setup["aircraft"][:2]},
    )

    assert response.status_code == 200, response.text
    saved = await client.get(f"{MISSIONS}/{mission_id}/plan", headers=auth[Role.OBSERVER])
    assert saved.json()["tasks"] == response.json()["tasks"]
    status = await client.get(f"{MISSIONS}/{mission_id}", headers=auth[Role.OBSERVER])
    assert status.json()["status"] == "planned"
    tasks = await client.get(
        "/api/v1/tasks", params={"mission_id": mission_id}, headers=auth[Role.OBSERVER]
    )
    assert sorted(t["aircraft_id"] for t in tasks.json()["items"]) == sorted(setup["aircraft"][:2])
    async with context.database().ops_session() as db:
        row = await db.scalar(select(AuditEvent).where(AuditEvent.action == "mission.plan"))
    assert row is not None
    assert row.details["clear"] is True

    # Planning again with one aircraft drops the other's pending task.
    again = await post_plan(
        client,
        auth[Role.OPERATOR],
        mission_id,
        {"pattern": "parallel_track", "spacing_m": 80.0, "aircraft_ids": setup["aircraft"][:1]},
    )
    assert again.status_code == 200, again.text
    tasks = await client.get(
        "/api/v1/tasks", params={"mission_id": mission_id}, headers=auth[Role.OBSERVER]
    )
    assert [t["aircraft_id"] for t in tasks.json()["items"]] == setup["aircraft"][:1]


async def test_the_spacing_can_come_from_the_camera_footprint(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], setup: dict[str, Any]
) -> None:
    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        setup["mission"]["id"],
        {
            "pattern": "parallel_track",
            "footprint": {"hfov_deg": 70.0, "overlap": 0.3},
            "aircraft_ids": setup["aircraft"][:1],
        },
        dry_run=True,
    )

    assert response.json()["spacing_m"] == pytest.approx(lane_spacing_m(60.0, 70.0, 0.3), abs=0.01)


async def test_a_waypoint_route_is_given_to_every_aircraft_on_separate_layers(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], setup: dict[str, Any]
) -> None:
    route = await mission(client, auth[Role.OPERATOR], setup["incident"]["id"])
    lat, lon = BASE["latitude"], BASE["longitude"]
    await client.put(
        f"{MISSIONS}/{route['id']}/waypoints",
        json={"waypoints": [waypoint(lat + 0.004, lon), waypoint(lat + 0.004, lon + 0.006)]},
        headers=auth[Role.OPERATOR],
    )

    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        route["id"],
        {"pattern": "route", "aircraft_ids": setup["aircraft"][:2]},
        dry_run=True,
    )

    plan = response.json()
    first, second = plan["tasks"]
    assert [(w["latitude"], w["longitude"]) for w in first["waypoints"]] == [
        (w["latitude"], w["longitude"]) for w in second["waypoints"]
    ]
    separated = (first["layer_m"], first["start_delay_s"]) != (
        second["layer_m"],
        second["start_delay_s"],
    )
    assert separated
    assert plan["clear"] is True, plan["conflicts"]


@pytest.mark.parametrize(
    ("change", "slug"),
    [
        ({"pattern": "route"}, "pattern-mismatch"),
        ({"spacing_m": None}, "spacing-required"),
        ({"pattern": "sector", "radius_m": 300.0}, "one-aircraft-pattern"),
        ({"aircraft_ids": None}, "no-aircraft"),
    ],
)
async def test_plans_that_cannot_be_made_are_refused_with_a_slug(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    setup: dict[str, Any],
    change: dict[str, Any],
    slug: str,
) -> None:
    body = {"pattern": "parallel_track", "spacing_m": 60.0, "aircraft_ids": setup["aircraft"]}
    body = {k: v for k, v in (body | change).items() if v is not None}

    response = await post_plan(client, auth[Role.OPERATOR], setup["mission"]["id"], body, True)

    assert response.status_code == 422, response.text
    assert response.json()["type"] == f"urn:sar-gcs:problem:{slug}"


async def test_swarm_missions_are_planned_by_the_swarm(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], setup: dict[str, Any]
) -> None:
    swarm = await create(
        client,
        "missions",
        auth[Role.OPERATOR],
        {
            "incident_id": setup["incident"]["id"],
            "name": "Swarm",
            "kind": "swarm_area",
            "search_area_id": setup["area"]["id"],
            "default_altitude_relative_m": 60.0,
        },
    )

    response = await post_plan(
        client, auth[Role.OPERATOR], swarm["id"], {"pattern": "parallel_track", "spacing_m": 60.0}
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:sar-gcs:problem:swarm-plans-onboard"


async def test_a_mission_changed_while_planning_is_not_overwritten(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_id = setup["mission"]["id"]
    real = asyncio.to_thread

    async def planning_while_someone_edits(fn: Callable[..., Any], *args: Any) -> Any:
        async with context.database().ops_session() as db:
            row = await db.get(Mission, mission_id)
            assert row is not None
            row.name = "Renamed meanwhile"
            row.updated_at = context.clock.now().replace(microsecond=1)
            await db.commit()
        return await real(fn, *args)

    monkeypatch.setattr(asyncio, "to_thread", planning_while_someone_edits)

    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        mission_id,
        {"pattern": "parallel_track", "spacing_m": 60.0, "aircraft_ids": setup["aircraft"][:1]},
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:sar-gcs:problem:plan-stale"


async def test_areas_are_planned_in_their_own_incident_only(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], setup: dict[str, Any]
) -> None:
    # A far square, still inside the 25 km operating radius: planning works there too.
    far = await search_area(
        client,
        auth[Role.OPERATOR],
        setup["incident"]["id"],
        name="Sector B",
        geometry=square(BASE["latitude"] + 0.05, BASE["longitude"], 0.004),
    )
    mission_b = await create(
        client,
        "missions",
        auth[Role.OPERATOR],
        {
            "incident_id": setup["incident"]["id"],
            "name": "Far grid",
            "kind": "area_search",
            "search_area_id": far["id"],
            "default_altitude_relative_m": 60.0,
        },
    )

    response = await post_plan(
        client,
        auth[Role.OPERATOR],
        mission_b["id"],
        {"pattern": "expanding_square", "spacing_m": 60.0, "aircraft_ids": setup["aircraft"][:1]},
        dry_run=True,
    )

    assert response.status_code == 200, response.text
    assert "centre" in " ".join(response.json()["tasks"][0]["notes"])


class TestContourOnASlope:
    """Contour searches split along the contours (bands of height), not the area's axis."""

    @pytest.fixture
    def settings(self, data_dir: Path) -> Settings:
        # A plane rising 10 m per 100 m eastwards around the base: contours run north-south.
        terrain = data_dir / "slope"
        terrain.mkdir()
        rows, cols, step = 200, 300, 0.0003
        lon_m = 111_320 * math.cos(math.radians(BASE["latitude"])) * step
        heights = np.tile(np.arange(cols, dtype=np.float32) * lon_m * 0.1 + 400.0, (rows, 1))
        np.save(terrain / "slope.npy", heights)
        (terrain / "slope.json").write_text(
            json.dumps(
                {
                    "region": "slope",
                    "rows": rows,
                    "cols": cols,
                    "lat0": BASE["latitude"] + rows * step / 2,
                    "lon0": BASE["longitude"] - cols * step / 2,
                    "lat_step": step,
                    "lon_step": step,
                }
            )
        )
        return Settings(
            station_name="test-station", data_dir=data_dir, simulation=True, terrain_dir=terrain
        )

    async def test_each_aircraft_gets_a_band_of_heights_with_whole_contours(
        self,
        client: httpx.AsyncClient,
        auth: dict[Role, dict[str, str]],
        setup: dict[str, Any],
    ) -> None:
        # A wide, shallow area (1.1 km east-west, 450 m north-south): its long axis runs
        # across the contours, which is exactly how contours must not be split.
        wide = await search_area(
            client,
            auth[Role.OPERATOR],
            setup["incident"]["id"],
            name="Slope",
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [BASE["longitude"] - 0.0075, BASE["latitude"] - 0.002],
                        [BASE["longitude"] + 0.0075, BASE["latitude"] - 0.002],
                        [BASE["longitude"] + 0.0075, BASE["latitude"] + 0.002],
                        [BASE["longitude"] - 0.0075, BASE["latitude"] + 0.002],
                        [BASE["longitude"] - 0.0075, BASE["latitude"] - 0.002],
                    ]
                ],
            },
        )
        contour = await create(
            client,
            "missions",
            auth[Role.OPERATOR],
            {
                "incident_id": setup["incident"]["id"],
                "name": "Contours",
                "kind": "area_search",
                "search_area_id": wide["id"],
                "default_altitude_relative_m": 40.0,
            },
        )

        response = await post_plan(
            client,
            auth[Role.OPERATOR],
            contour["id"],
            {
                "pattern": "contour",
                "spacing_m": 60.0,
                "height_agl_m": 50.0,
                "aircraft_ids": setup["aircraft"][:2],
            },
            dry_run=True,
        )

        assert response.status_code == 200, response.text
        for task in response.json()["tasks"]:
            assert task["fallback"] is False
            lons = [w["longitude"] for w in task["waypoints"]]
            # A band of heights on this slope is a band of longitudes.
            assert max(lons) - min(lons) < 0.0075 + 1e-6
