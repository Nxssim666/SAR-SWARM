"""Missions, waypoints and tasks: planning rules and lifecycle."""

from typing import Any

import httpx
import pytest

from fleet_service.domain.enums import Role

from factories import BASE, aircraft, create, incident, mission, search_area, waypoint

MISSIONS = "/api/v1/missions"
TASKS = "/api/v1/tasks"


@pytest.fixture
async def inc(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]) -> dict[str, Any]:
    return await incident(client, auth[Role.SUPERVISOR])


async def test_area_missions_need_a_search_area_of_the_same_incident(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    other = await incident(client, auth[Role.SUPERVISOR], name="Other")
    foreign = await search_area(client, auth[Role.OPERATOR], other["id"])
    body = {
        "incident_id": inc["id"],
        "name": "Grid",
        "kind": "area_search",
        "default_altitude_relative_m": 80.0,
    }

    missing = await client.post(MISSIONS, json=body, headers=auth[Role.OPERATOR])
    mismatched = await client.post(
        MISSIONS, json=body | {"search_area_id": foreign["id"]}, headers=auth[Role.OPERATOR]
    )

    assert missing.json()["type"] == "urn:sar-gcs:problem:search-area-required"
    assert mismatched.json()["type"] == "urn:sar-gcs:problem:reference-mismatch"


async def test_waypoints_replace_the_route_in_order(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    lat, lon = BASE["latitude"], BASE["longitude"]
    url = f"{MISSIONS}/{plan['id']}/waypoints"

    first = await client.put(
        url,
        json={"waypoints": [waypoint(lat, lon), waypoint(lat + 0.001, lon)]},
        headers=auth[Role.OPERATOR],
    )
    second = await client.put(
        url,
        json={
            "waypoints": [
                waypoint(lat, lon + 0.002, 40.0),
                {**waypoint(lat, lon), "loiter_s": 30.0},
            ]
        },
        headers=auth[Role.OPERATOR],
    )
    read = await client.get(url, headers=auth[Role.OBSERVER])
    summary = await client.get(f"{MISSIONS}/{plan['id']}", headers=auth[Role.OBSERVER])

    assert first.status_code == 200
    assert second.status_code == 200
    points = read.json()["waypoints"]
    assert [p["seq"] for p in points] == [0, 1]
    assert points[0]["altitude_relative_m"] == 40.0
    assert points[1]["loiter_s"] == 30.0
    assert summary.json()["waypoint_count"] == 2


async def test_waypoints_outside_the_operating_area_are_rejected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])

    response = await client.put(
        f"{MISSIONS}/{plan['id']}/waypoints",
        json={
            "waypoints": [waypoint(BASE["latitude"], BASE["longitude"]), waypoint(8.5456, 47.3977)]
        },
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422
    assert response.json()["outside_indices"] == [1]


async def test_swarm_missions_follow_the_onboard_waypoint_limit(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    plan = await mission(
        client, auth[Role.OPERATOR], inc["id"], kind="swarm_area", search_area_id=area["id"]
    )
    route = [waypoint(BASE["latitude"] + i * 1e-4, BASE["longitude"]) for i in range(65)]

    response = await client.put(
        f"{MISSIONS}/{plan['id']}/waypoints", json={"waypoints": route}, headers=auth[Role.OPERATOR]
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:sar-gcs:problem:too-many-waypoints"


@pytest.mark.parametrize(
    ("steps", "final_status"),
    [
        (["planned"], 200),
        (["planned", "draft"], 200),
        (["planned", "aborted"], 200),
        (["aborted", "draft"], 409),
        (["active"], 409),
        (["completed"], 409),
    ],
)
async def test_mission_status_transitions(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    inc: dict[str, Any],
    steps: list[str],
    final_status: int,
) -> None:
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    for status in steps:
        response = await client.patch(
            f"{MISSIONS}/{plan['id']}", json={"status": status}, headers=auth[Role.OPERATOR]
        )

    assert response.status_code == final_status


async def test_aborted_missions_are_frozen_but_can_be_renamed(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    url = f"{MISSIONS}/{plan['id']}"
    await client.patch(url, json={"status": "aborted"}, headers=auth[Role.OPERATOR])

    renamed = await client.patch(
        url, json={"name": "Ridge sweep (weather)"}, headers=auth[Role.OPERATOR]
    )
    replanned = await client.patch(
        url, json={"default_altitude_relative_m": 90.0}, headers=auth[Role.OPERATOR]
    )
    rerouted = await client.put(
        f"{url}/waypoints", json={"waypoints": []}, headers=auth[Role.OPERATOR]
    )
    deleted = await client.delete(url, headers=auth[Role.OPERATOR])

    assert renamed.status_code == 200
    for response in (replanned, rerouted):
        assert response.json()["type"] == "urn:sar-gcs:problem:mission-not-editable"
    assert deleted.json()["type"] == "urn:sar-gcs:problem:mission-not-deletable"


async def test_tasks_require_a_compatible_link(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    mavlink_only = await aircraft(
        client, auth[Role.SUPERVISOR], "FW-1", airframe="fixed_wing", mavlink_system_id=21
    )
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    swarm = await mission(
        client, auth[Role.OPERATOR], inc["id"], kind="swarm_area", search_area_id=area["id"]
    )
    route = await mission(client, auth[Role.OPERATOR], inc["id"])

    refused = await client.post(
        TASKS,
        json={"mission_id": swarm["id"], "aircraft_id": mavlink_only["id"]},
        headers=auth[Role.OPERATOR],
    )
    accepted = await client.post(
        TASKS,
        json={
            "mission_id": route["id"],
            "aircraft_id": mavlink_only["id"],
            "altitude_relative_m": 120.0,
        },
        headers=auth[Role.OPERATOR],
    )
    duplicate = await client.post(
        TASKS,
        json={"mission_id": route["id"], "aircraft_id": mavlink_only["id"]},
        headers=auth[Role.OPERATOR],
    )

    assert refused.json()["type"] == "urn:sar-gcs:problem:aircraft-incompatible"
    assert accepted.status_code == 201
    assert accepted.json()["status"] == "pending"
    assert duplicate.json()["type"] == "urn:sar-gcs:problem:task-exists"


async def test_tasks_can_be_cancelled_but_not_revived(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    hexa = await aircraft(client, auth[Role.SUPERVISOR], "HX-1", mavlink_system_id=11)
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    task = await create(
        client, "tasks", auth[Role.OPERATOR], {"mission_id": plan["id"], "aircraft_id": hexa["id"]}
    )
    url = f"{TASKS}/{task['id']}"

    cancelled = await client.patch(url, json={"status": "cancelled"}, headers=auth[Role.OPERATOR])
    revived = await client.patch(url, json={"status": "pending"}, headers=auth[Role.OPERATOR])
    activated = await client.patch(url, json={"status": "active"}, headers=auth[Role.OPERATOR])

    assert cancelled.json()["status"] == "cancelled"
    assert revived.status_code == 409
    assert activated.status_code == 409


async def test_deleting_a_draft_mission_removes_its_tasks(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    hexa = await aircraft(client, auth[Role.SUPERVISOR], "HX-1", mavlink_system_id=11)
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    task = await create(
        client, "tasks", auth[Role.OPERATOR], {"mission_id": plan["id"], "aircraft_id": hexa["id"]}
    )

    deleted = await client.delete(f"{MISSIONS}/{plan['id']}", headers=auth[Role.OPERATOR])

    assert deleted.status_code == 204
    assert (
        await client.get(f"{TASKS}/{task['id']}", headers=auth[Role.OBSERVER])
    ).status_code == 404
    aircraft_free = await client.delete(
        f"/api/v1/aircraft/{hexa['id']}", headers=auth[Role.SUPERVISOR]
    )
    assert aircraft_free.status_code == 204


async def test_observers_can_read_plans_but_not_change_them(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])

    read = await client.get(f"{MISSIONS}/{plan['id']}", headers=auth[Role.OBSERVER])
    write = await client.patch(
        f"{MISSIONS}/{plan['id']}", json={"name": "x"}, headers=auth[Role.OBSERVER]
    )

    assert read.status_code == 200
    assert write.status_code == 403
