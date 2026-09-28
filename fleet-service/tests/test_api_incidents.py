"""Incidents, search areas and geofences: operating-area rules and lifecycle."""

import httpx
import pytest

from fleet_service.domain.enums import Role

from factories import BASE, incident, mission, search_area, square, waypoint

INCIDENTS = "/api/v1/incidents"
AREAS = "/api/v1/search-areas"


async def test_incident_starts_active_with_base_and_radius(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    body = await incident(client, auth[Role.SUPERVISOR], base_altitude_amsl_m=420.0)

    assert body["status"] == "active"
    assert body["base"] == BASE
    assert body["operating_radius_m"] == 25_000.0
    assert body["created_by"] == user_ids[Role.SUPERVISOR]


async def test_search_area_is_measured_and_normalized(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    clockwise = square()
    clockwise["coordinates"][0].reverse()

    area = await search_area(client, auth[Role.OPERATOR], inc["id"], geometry=clockwise)

    assert area["status"] == "unassigned"
    assert area["priority"] == 3
    assert area["area_m2"] == pytest.approx(0.01 * 111_200 * 0.01 * 75_300, rel=0.02)
    assert area["geometry"]["coordinates"][0] != clockwise["coordinates"][0]  # re-oriented CCW


async def test_swapped_coordinates_are_rejected_with_a_hint(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    swapped = square()
    swapped["coordinates"][0] = [[lat, lon] for lon, lat in swapped["coordinates"][0]]

    response = await client.post(
        AREAS,
        json={"incident_id": inc["id"], "name": "Oops", "geometry": swapped},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422
    problem = response.json()
    assert problem["type"] == "urn:sar-gcs:problem:outside-operating-area"
    assert "swapped" in problem["detail"]
    assert problem["outside_indices"] == [0, 1, 2, 3]


async def test_self_intersecting_area_is_rejected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    lat, lon = BASE["latitude"], BASE["longitude"]
    bow_tie = {
        "type": "Polygon",
        "coordinates": [
            [[lon, lat], [lon + 0.01, lat + 0.01], [lon + 0.01, lat], [lon, lat + 0.01], [lon, lat]]
        ],
    }

    response = await client.post(
        AREAS,
        json={"incident_id": inc["id"], "name": "Bow tie", "geometry": bow_tie},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422
    assert "invalid polygon" in response.json()["errors"][0]["msg"]


async def test_area_in_an_unknown_incident_is_422(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.post(
        AREAS,
        json={"incident_id": "no-such-incident", "name": "A", "geometry": square()},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:sar-gcs:problem:unknown-reference"


async def test_closed_incidents_are_read_only(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    closed = await client.patch(
        f"{INCIDENTS}/{inc['id']}", json={"status": "closed"}, headers=auth[Role.SUPERVISOR]
    )

    attempts = [
        await client.patch(
            f"{INCIDENTS}/{inc['id']}", json={"name": "x"}, headers=auth[Role.SUPERVISOR]
        ),
        await client.patch(
            f"{AREAS}/{area['id']}", json={"status": "searched"}, headers=auth[Role.OPERATOR]
        ),
        await client.post(
            AREAS,
            json={"incident_id": inc["id"], "name": "B", "geometry": square()},
            headers=auth[Role.OPERATOR],
        ),
        await client.delete(f"{AREAS}/{area['id']}", headers=auth[Role.OPERATOR]),
    ]

    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] == "2026-09-28T08:00:00Z"
    for response in attempts:
        assert response.status_code == 409, response.text
        assert response.json()["type"] == "urn:sar-gcs:problem:incident-closed"


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        (["suspended", "active", "closed"], True),
        (["suspended", "closed"], True),
        (["active"], True),  # no-op
    ],
)
async def test_incident_transitions(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], path: list[str], allowed: bool
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    for status in path:
        response = await client.patch(
            f"{INCIDENTS}/{inc['id']}", json={"status": status}, headers=auth[Role.SUPERVISOR]
        )
        assert response.is_success is allowed


async def test_base_cannot_move_away_from_existing_geometry(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    await client.put(
        f"/api/v1/missions/{plan['id']}/waypoints",
        json={"waypoints": [waypoint(BASE["latitude"], BASE["longitude"])]},
        headers=auth[Role.OPERATOR],
    )

    moved = await client.patch(
        f"{INCIDENTS}/{inc['id']}",
        json={"base": {"latitude": 46.0, "longitude": 7.0}},
        headers=auth[Role.SUPERVISOR],
    )
    shrunk = await client.patch(
        f"{INCIDENTS}/{inc['id']}",
        json={"operating_radius_m": 200.0},
        headers=auth[Role.SUPERVISOR],
    )
    grown = await client.patch(
        f"{INCIDENTS}/{inc['id']}",
        json={"operating_radius_m": 30_000.0},
        headers=auth[Role.SUPERVISOR],
    )

    assert moved.status_code == 409
    assert {e["entity_id"] for e in moved.json()["entities"]} == {area["id"], plan["id"]}
    assert shrunk.status_code == 409
    assert grown.status_code == 200


async def test_only_empty_incidents_can_be_deleted(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    empty = await incident(client, auth[Role.SUPERVISOR])
    busy = await incident(client, auth[Role.SUPERVISOR], name="Busy")
    await search_area(client, auth[Role.OPERATOR], busy["id"])

    assert (
        await client.delete(f"{INCIDENTS}/{empty['id']}", headers=auth[Role.SUPERVISOR])
    ).status_code == 204
    refused = await client.delete(f"{INCIDENTS}/{busy['id']}", headers=auth[Role.SUPERVISOR])
    assert refused.status_code == 409
    assert refused.json()["type"] == "urn:sar-gcs:problem:incident-not-empty"


async def test_areas_used_by_missions_cannot_be_deleted(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    await mission(
        client, auth[Role.OPERATOR], inc["id"], kind="area_search", search_area_id=area["id"]
    )

    response = await client.delete(f"{AREAS}/{area['id']}", headers=auth[Role.OPERATOR])

    assert response.status_code == 409
    assert response.json()["type"] == "urn:sar-gcs:problem:area-in-use"


async def test_ground_team_results_can_be_recorded_on_an_area(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])

    response = await client.patch(
        f"{AREAS}/{area['id']}",
        json={"status": "searched", "notes": "Ground team 2: cleared 14:05"},
        headers=auth[Role.OPERATOR],
    )

    assert response.json()["status"] == "searched"


async def test_geofences_are_supervisor_managed_and_bounded(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    body = {
        "incident_id": inc["id"],
        "name": "Hospital helipad",
        "kind": "exclusion",
        "geometry": square(half=0.001),
    }

    by_operator = await client.post("/api/v1/geofences", json=body, headers=auth[Role.OPERATOR])
    by_supervisor = await client.post(
        "/api/v1/geofences",
        json=body | {"max_altitude_relative_m": 120.0},
        headers=auth[Role.SUPERVISOR],
    )
    far_away = await client.post(
        "/api/v1/geofences",
        json=body | {"geometry": square(lat=40.0)},
        headers=auth[Role.SUPERVISOR],
    )

    assert by_operator.status_code == 403
    assert by_supervisor.status_code == 201
    assert by_supervisor.json()["enabled"] is True
    assert far_away.status_code == 422


async def test_listing_areas_by_incident(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    first = await incident(client, auth[Role.SUPERVISOR])
    second = await incident(client, auth[Role.SUPERVISOR], name="Other")
    await search_area(client, auth[Role.OPERATOR], first["id"])
    await search_area(client, auth[Role.OPERATOR], second["id"])

    response = await client.get(
        AREAS, params={"incident_id": first["id"]}, headers=auth[Role.OBSERVER]
    )

    assert [a["incident_id"] for a in response.json()["items"]] == [first["id"]]
