"""
GCS-planned missions through the command pipeline (ADR 0028, ADR 0029), in simulation:
plan, start (each aircraft its own route), fly, pause, resume; and the refusals.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.domain.enums import FlightMode, Role
from live_support import Sim, confirmed, register, send, states, take

from factories import create, incident, search_area, square
from support import FakeClock

MISSIONS = "/api/v1/missions"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="test-station", data_dir=data_dir, simulation=True, command_timeout_s=0.2
    )


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


async def airborne(
    client: httpx.AsyncClient, headers: dict[str, str], sim: Sim, ids: list[str]
) -> None:
    for aircraft_id in ids:
        await confirmed(client, headers, "arm", [aircraft_id])
        await sim.fly(0.5)
        await confirmed(client, headers, "takeoff", [aircraft_id], altitude_relative_m=30.0)
        await sim.fly(0.5)
    await sim.fly(15)


@pytest.fixture
async def planned(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> dict[str, Any]:
    """Two hexacopters in the air, controlled by the operator, and a planned area search
    (a 450 x 330 m area 300 m north of them) split between them."""
    inc = await incident(client, auth[Role.SUPERVISOR])
    ids = [await register(client, auth[Role.SUPERVISOR], name) for name in ("HX-1", "HX-2")]
    for aircraft_id in ids:
        await take(client, auth[Role.OPERATOR], aircraft_id)
    await sim.fly(1)
    await airborne(client, auth[Role.OPERATOR], sim, ids)
    lat, lon = sim.vehicle(ids[0]).to_geo(0.0, 500.0)
    area = await search_area(
        client, auth[Role.OPERATOR], inc["id"], geometry=square(lat, lon, 0.0015)
    )
    mission = await create(
        client,
        "missions",
        auth[Role.OPERATOR],
        {
            "incident_id": inc["id"],
            "name": "Grid",
            "kind": "area_search",
            "search_area_id": area["id"],
            "default_altitude_relative_m": 40.0,
            "default_speed_mps": 8.0,
        },
    )
    plan = await client.post(
        f"{MISSIONS}/{mission['id']}/plan",
        json={"pattern": "parallel_track", "spacing_m": 100.0, "aircraft_ids": ids},
        headers=auth[Role.OPERATOR],
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["clear"] is True, plan.json()["conflicts"]
    return {"incident": inc, "area": area, "mission": mission, "aircraft": ids, "plan": plan.json()}


async def test_a_planned_search_is_started_flown_and_its_area_marked_in_progress(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim, planned: dict[str, Any]
) -> None:
    ids, mission_id = planned["aircraft"], planned["mission"]["id"]

    first = await send(client, auth[Role.OPERATOR], "mission_start", ids, mission_id=mission_id)
    assert first.status_code == 428  # always confirmed
    summary = first.json()["summary"]
    assert {a["aircraft_id"] for a in summary["aircraft"]} == set(ids)
    assert all(a["target"] is not None for a in summary["aircraft"])  # first waypoints shown
    outcome = await confirmed(
        client, auth[Role.OPERATOR], "mission_start", ids, mission_id=mission_id
    )
    await sim.fly(5)

    assert states(outcome) == dict.fromkeys(ids, "acked")
    assert all(sim.vehicle(a).mode is FlightMode.MISSION for a in ids)
    mission = (await client.get(f"{MISSIONS}/{mission_id}", headers=auth[Role.OBSERVER])).json()
    assert mission["status"] == "active"
    area = await client.get(
        f"/api/v1/search-areas/{planned['area']['id']}", headers=auth[Role.OBSERVER]
    )
    assert area.json()["status"] == "in_progress"
    # Each aircraft flies its own route: first a hold where it is, then its lanes.
    for task in planned["plan"]["tasks"]:
        vehicle = sim.vehicle(task["aircraft_id"])
        assert len(vehicle.mission) == len(task["waypoints"]) + 1

    await sim.fly(400)

    for aircraft_id in ids:
        vehicle = sim.vehicle(aircraft_id)
        assert vehicle.mission_index == len(vehicle.mission)  # every item flown
        assert vehicle.mode in (FlightMode.RETURN, FlightMode.LAND, FlightMode.HOLD)


async def test_pause_holds_the_mission_and_resume_continues_it(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim, planned: dict[str, Any]
) -> None:
    ids, mission_id = planned["aircraft"], planned["mission"]["id"]
    await confirmed(client, auth[Role.OPERATOR], "mission_start", ids, mission_id=mission_id)
    await sim.fly(30)
    item = sim.vehicle(ids[0]).mission_index

    paused = await confirmed(client, auth[Role.OPERATOR], "mission_pause", ids)  # bulk: confirmed
    await sim.fly(10)

    assert states(paused) == dict.fromkeys(ids, "acked")
    assert all(sim.vehicle(a).mode is FlightMode.HOLD for a in ids)
    mission = (await client.get(f"{MISSIONS}/{mission_id}", headers=auth[Role.OBSERVER])).json()
    assert mission["status"] == "paused"

    resumed = await confirmed(client, auth[Role.OPERATOR], "resume", ids)
    await sim.fly(10)

    assert states(resumed) == dict.fromkeys(ids, "acked")
    assert all(sim.vehicle(a).mode is FlightMode.MISSION for a in ids)
    assert sim.vehicle(ids[0]).mission_index >= item  # continued, not restarted
    mission = (await client.get(f"{MISSIONS}/{mission_id}", headers=auth[Role.OBSERVER])).json()
    assert mission["status"] == "active"


async def test_aircraft_without_a_planned_route_or_on_the_ground_are_not_started(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim, planned: dict[str, Any]
) -> None:
    ids, mission_id = planned["aircraft"], planned["mission"]["id"]
    extra = await register(client, auth[Role.SUPERVISOR], "HX-3")
    await take(client, auth[Role.OPERATOR], extra)
    await sim.fly(1)

    outcome = await confirmed(
        client, auth[Role.OPERATOR], "mission_start", [*ids, extra], mission_id=mission_id
    )

    by_aircraft = {t["aircraft_id"]: t for t in outcome["targets"]}
    assert by_aircraft[extra]["state"] == "rejected"
    assert by_aircraft[extra]["reason_code"] == "not-tasked"


async def test_a_mission_needs_a_plan_to_start(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim, planned: dict[str, Any]
) -> None:
    unplanned = await create(
        client,
        "missions",
        auth[Role.OPERATOR],
        {
            "incident_id": planned["incident"]["id"],
            "name": "Not yet",
            "kind": "area_search",
            "search_area_id": planned["area"]["id"],
            "default_altitude_relative_m": 40.0,
        },
    )

    response = await send(
        client,
        auth[Role.OPERATOR],
        "mission_start",
        planned["aircraft"],
        mission_id=unplanned["id"],
    )

    assert response.status_code == 200
    assert {t["reason_code"] for t in response.json()["targets"]} == {"mission-not-planned"}


async def test_a_companion_aircraft_is_flagged_when_the_autopilot_would_fly_it(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    # ADR 0028: onboard obstacle avoidance flies only swarm missions (PX4 offboard).
    companion = await register(client, auth[Role.SUPERVISOR], "SW-1", swarm_drone_id=7)
    await take(client, auth[Role.OPERATOR], companion)
    await sim.fly(1)
    await airborne(client, auth[Role.OPERATOR], sim, [companion])
    lat, lon = sim.vehicle(companion).to_geo(100.0, 100.0)

    response = await send(
        client, auth[Role.OPERATOR], "goto", [companion], target={"latitude": lat, "longitude": lon}
    )

    assert response.status_code == 428  # a 140 m goto alone would not need confirming
    summary = response.json()["summary"]
    assert "onboard obstacle avoidance is not active on 1 aircraft" in summary["reasons"]
    assert any("obstacle avoidance" in w for w in summary["aircraft"][0]["warnings"])


class TestPlanIssues:
    """A plan with conflicts: an operator cannot start it; a supervisor may, confirmed."""

    @pytest.fixture
    def settings(self, data_dir: Path) -> Settings:
        # One layer, no departure spacing, no start delays: two aircraft flying one route
        # from next to each other cannot be deconflicted.
        return Settings(
            station_name="test-station",
            data_dir=data_dir,
            simulation=True,
            command_timeout_s=0.2,
            multirotor_layers=1,
            departure_interval_s=0.0,
            max_start_delay_s=0.0,
        )

    async def test_conflicts_need_a_supervisor_who_sees_them(
        self,
        client: httpx.AsyncClient,
        auth: dict[Role, dict[str, str]],
        sim: Sim,
    ) -> None:
        inc = await incident(client, auth[Role.SUPERVISOR])
        ids = [await register(client, auth[Role.SUPERVISOR], n) for n in ("HX-1", "HX-2")]
        for aircraft_id in ids:
            await take(client, auth[Role.OPERATOR], aircraft_id)
        await sim.fly(1)
        await airborne(client, auth[Role.OPERATOR], sim, ids)
        route = await create(
            client, "missions", auth[Role.OPERATOR],
            {"incident_id": inc["id"], "name": "Road", "kind": "waypoint",
             "default_altitude_relative_m": 40.0},
        )  # fmt: skip
        a = sim.vehicle(ids[0]).to_geo(0.0, 300.0)
        b = sim.vehicle(ids[0]).to_geo(300.0, 300.0)
        await client.put(
            f"{MISSIONS}/{route['id']}/waypoints",
            json={"waypoints": [
                {"latitude": a[0], "longitude": a[1], "altitude_relative_m": 40.0},
                {"latitude": b[0], "longitude": b[1], "altitude_relative_m": 40.0},
            ]},
            headers=auth[Role.OPERATOR],
        )  # fmt: skip
        plan = await client.post(
            f"{MISSIONS}/{route['id']}/plan",
            json={"pattern": "route", "aircraft_ids": ids},
            headers=auth[Role.OPERATOR],
        )
        assert plan.json()["clear"] is False

        by_operator = await send(
            client, auth[Role.OPERATOR], "mission_start", ids, mission_id=route["id"]
        )
        assert {t["reason_code"] for t in by_operator.json()["targets"]} == {"plan-conflicts"}

        by_supervisor = await send(
            client, auth[Role.SUPERVISOR], "mission_start", ids, mission_id=route["id"]
        )
        assert by_supervisor.status_code == 428
        summary = by_supervisor.json()["summary"]
        assert summary["override"] is True
        assert summary["conflicts"]
        assert any("deconfliction" in r for r in summary["reasons"])


async def test_a_flown_mission_completes_with_its_coverage_and_its_area_searched(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim, planned: dict[str, Any]
) -> None:
    ids, mission_id = planned["aircraft"], planned["mission"]["id"]
    await confirmed(client, auth[Role.OPERATOR], "mission_start", ids, mission_id=mission_id)
    await sim.fly(60)
    midway = (
        await client.get(f"{MISSIONS}/{mission_id}/progress", headers=auth[Role.OBSERVER])
    ).json()

    await sim.fly(400)

    progress = (
        await client.get(f"{MISSIONS}/{mission_id}/progress", headers=auth[Role.OBSERVER])
    ).json()
    assert midway["status"] == "active"
    assert 0.0 < midway["coverage"] < progress["coverage"]
    assert all(t["item"] is not None and t["items"] for t in midway["tasks"])
    assert progress["status"] == "completed"
    assert progress["coverage"] >= 0.9  # swept, not a probability of detection
    assert progress["coverage_geometry"]["type"] == "MultiPolygon"
    assert {t["status"] for t in progress["tasks"]} == {"completed"}
    area = await client.get(
        f"/api/v1/search-areas/{planned['area']['id']}", headers=auth[Role.OBSERVER]
    )
    assert area.json()["status"] == "searched"
    alerts = await client.get(
        "/api/v1/alerts", params={"state": "active"}, headers=auth[Role.OBSERVER]
    )
    complete = [a for a in alerts.json()["items"] if a["kind"] == "mission_complete"]
    assert len(complete) == 1
    assert complete[0]["severity"] == "info"
    assert "swept" in complete[0]["message"]
