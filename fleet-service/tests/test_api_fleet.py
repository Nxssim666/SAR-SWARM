"""Aircraft registry, groups and video stream configuration."""

import httpx
import pytest
from sqlalchemy import select

from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent
from fleet_service.domain.enums import Role

from factories import aircraft, create, incident, mission

AIRCRAFT = "/api/v1/aircraft"


async def test_register_aircraft_normalizes_callsign(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    body = await aircraft(
        client,
        auth[Role.SUPERVISOR],
        "hexa-1",
        mavlink_system_id=11,
        mavlink_connection="udp://:14541",
        cruise_speed_mps=8.0,
    )

    assert body["callsign"] == "HEXA-1"
    assert body["mavlink_system_id"] == 11
    assert body["swarm_drone_id"] is None
    assert body["group_ids"] == []


@pytest.mark.parametrize(
    ("field", "first", "second"),
    [
        ("callsign", {}, {}),
        ("mavlink_system_id", {"mavlink_system_id": 7}, {"mavlink_system_id": 7}),
        ("swarm_drone_id", {"swarm_drone_id": 3}, {"swarm_drone_id": 3}),
    ],
)
async def test_identities_are_unique(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    field: str,
    first: dict[str, int],
    second: dict[str, int],
) -> None:
    await aircraft(client, auth[Role.SUPERVISOR], "FW-1", **first)
    callsign = "fw-1" if field == "callsign" else "FW-2"

    response = await client.post(
        AIRCRAFT,
        json={"callsign": callsign, "airframe": "fixed_wing", **second},
        headers=auth[Role.SUPERVISOR],
    )

    assert response.status_code == 409
    assert response.json()["field"] == field


@pytest.mark.parametrize(
    "body",
    [
        {"callsign": "X1", "airframe": "fixed_wing", "mavlink_system_id": "7"},
        {"callsign": "X1", "airframe": "fixed_wing", "mavlink_system_id": 255},
        {"callsign": "X1", "airframe": "blimp"},
        {"callsign": " X1", "airframe": "fixed_wing"},
        {"callsign": "X1", "airframe": "fixed_wing", "mavlink_connection": "http://x"},
        {"callsign": "X1", "airframe": "fixed_wing", "colour": "red"},
    ],
)
async def test_invalid_registrations_are_rejected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], body: dict[str, object]
) -> None:
    response = await client.post(AIRCRAFT, json=body, headers=auth[Role.SUPERVISOR])

    assert response.status_code == 422
    assert response.json()["type"] == "urn:sar-gcs:problem:validation-error"


async def test_patch_null_clears_links_and_omitted_fields_stay(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    created = await aircraft(
        client, auth[Role.SUPERVISOR], "HX-2", mavlink_system_id=12, notes="spare props"
    )

    response = await client.patch(
        f"{AIRCRAFT}/{created['id']}",
        json={"mavlink_system_id": None, "swarm_drone_id": 4},
        headers=auth[Role.SUPERVISOR],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mavlink_system_id"] is None
    assert body["swarm_drone_id"] == 4
    assert body["notes"] == "spare props"


async def test_aircraft_changes_are_audited_as_diffs(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], context: AppContext
) -> None:
    created = await aircraft(client, auth[Role.SUPERVISOR], "HX-3")
    await client.patch(
        f"{AIRCRAFT}/{created['id']}", json={"cruise_speed_mps": 9.5}, headers=auth[Role.SUPERVISOR]
    )

    async with context.database().ops_session() as db:
        event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "aircraft.update"))

    assert event is not None
    assert event.actor_username == "supervisor"
    assert event.entity_id == created["id"]
    # The fake clock does not move, so updated_at is unchanged: the diff is exactly one field.
    assert event.details == {"changes": {"cruise_speed_mps": [None, 9.5]}}


async def test_aircraft_with_tasks_cannot_be_deleted(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    hexa = await aircraft(client, auth[Role.SUPERVISOR], "HX-4", mavlink_system_id=14)
    inc = await incident(client, auth[Role.SUPERVISOR])
    plan = await mission(client, auth[Role.OPERATOR], inc["id"])
    await create(
        client, "tasks", auth[Role.OPERATOR], {"mission_id": plan["id"], "aircraft_id": hexa["id"]}
    )

    response = await client.delete(f"{AIRCRAFT}/{hexa['id']}", headers=auth[Role.SUPERVISOR])

    assert response.status_code == 409
    assert response.json()["type"] == "urn:sar-gcs:problem:aircraft-in-use"


async def test_groups_hold_members_as_a_set(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    a = await aircraft(client, auth[Role.SUPERVISOR], "A1")
    b = await aircraft(client, auth[Role.SUPERVISOR], "B1")
    group = await create(
        client, "groups", auth[Role.SUPERVISOR], {"name": "North team", "aircraft_ids": [a["id"]]}
    )

    replaced = await client.patch(
        f"/api/v1/groups/{group['id']}",
        json={"aircraft_ids": [b["id"], a["id"]]},
        headers=auth[Role.SUPERVISOR],
    )
    member = await client.get(f"{AIRCRAFT}/{a['id']}", headers=auth[Role.OBSERVER])

    assert replaced.json()["aircraft_ids"] == sorted([a["id"], b["id"]])
    assert member.json()["group_ids"] == [group["id"]]


async def test_group_rejects_duplicates_and_unknown_aircraft(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    a = await aircraft(client, auth[Role.SUPERVISOR], "A1")

    duplicate = await client.post(
        "/api/v1/groups",
        json={"name": "G", "aircraft_ids": [a["id"], a["id"]]},
        headers=auth[Role.SUPERVISOR],
    )
    unknown = await client.post(
        "/api/v1/groups",
        json={"name": "G", "aircraft_ids": [a["id"], "no-such-aircraft"]},
        headers=auth[Role.SUPERVISOR],
    )

    assert duplicate.status_code == 422
    assert unknown.status_code == 422
    assert unknown.json()["unknown_ids"] == ["no-such-aircraft"]


async def test_deleting_an_aircraft_removes_it_from_groups(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    a = await aircraft(client, auth[Role.SUPERVISOR], "A1")
    group = await create(
        client, "groups", auth[Role.SUPERVISOR], {"name": "G", "aircraft_ids": [a["id"]]}
    )

    await client.delete(f"{AIRCRAFT}/{a['id']}", headers=auth[Role.SUPERVISOR])

    after = await client.get(f"/api/v1/groups/{group['id']}", headers=auth[Role.OBSERVER])
    assert after.json()["aircraft_ids"] == []


# --- video streams --------------------------------------------------------------------------------

STREAMS = "/api/v1/video-streams"


async def test_video_credentials_are_never_returned_or_audited(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], context: AppContext
) -> None:
    created = await create(
        client,
        "video-streams",
        auth[Role.SUPERVISOR],
        {
            "name": "HX-1 gimbal",
            "source_url": "rtsp://viewer:s3cr3t-pw@10.0.1.11:8554/main",
            "relay_path": "hx-1",
        },
    )
    listed = await client.get(STREAMS, headers=auth[Role.OBSERVER])

    assert created["source_url"] == "rtsp://viewer:***@10.0.1.11:8554/main"
    assert "s3cr3t-pw" not in listed.text
    async with context.database().ops_session() as db:
        details: list[dict[str, object]] = list(
            (await db.scalars(select(AuditEvent.details))).all()
        )
    assert "s3cr3t-pw" not in str(details)


async def test_sending_back_a_redacted_url_is_rejected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    created = await create(
        client,
        "video-streams",
        auth[Role.SUPERVISOR],
        {"name": "Cam", "source_url": "rtsp://u:p@cam/1", "relay_path": "cam"},
    )

    response = await client.patch(
        f"{STREAMS}/{created['id']}",
        json={"source_url": created["source_url"]},
        headers=auth[Role.SUPERVISOR],
    )

    assert response.status_code == 422


async def test_relay_paths_are_unique_and_urls_without_password_are_unchanged(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    first = await create(
        client,
        "video-streams",
        auth[Role.SUPERVISOR],
        {
            "name": "Base cam",
            "source_url": "srt://10.0.0.9:9000?streamid=base",
            "relay_path": "base",
        },
    )

    clash = await client.post(
        STREAMS,
        json={"name": "Other", "source_url": "rtsp://cam/2", "relay_path": "base"},
        headers=auth[Role.SUPERVISOR],
    )

    assert first["source_url"] == "srt://10.0.0.9:9000?streamid=base"
    assert clash.status_code == 409
