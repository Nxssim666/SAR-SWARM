"""Reading the audit trail through the API; every mutation leaves a verifiable record."""

import csv
import io
import json

import httpx
from sqlalchemy import text

from fleet_service.context import AppContext
from fleet_service.domain.enums import Role
from fleet_service.services.audit import verify_chain

from factories import aircraft, incident, search_area

AUDIT = "/api/v1/audit"


async def test_every_mutation_is_audited_and_the_chain_verifies(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], context: AppContext
) -> None:
    inc = await incident(client, auth[Role.SUPERVISOR])
    area = await search_area(client, auth[Role.OPERATOR], inc["id"])
    await client.patch(
        f"/api/v1/search-areas/{area['id']}", json={"priority": 1}, headers=auth[Role.OPERATOR]
    )
    await aircraft(client, auth[Role.SUPERVISOR], "HX-1")

    response = await client.get(AUDIT, headers=auth[Role.SUPERVISOR])

    actions = [e["action"] for e in response.json()["items"]]
    assert actions[:4] == [
        "aircraft.create",
        "search_area.update",
        "search_area.create",
        "incident.create",
    ]
    update = response.json()["items"][1]
    assert update["actor_username"] == "operator"
    assert update["details"] == {"changes": {"priority": [3, 1]}}
    assert len(update["request_id"]) == 36
    async with context.database().ops_session() as db:
        assert (await verify_chain(db)).ok


async def test_audit_filters_and_newest_first_pagination(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    for callsign in ("A1", "A2", "A3"):
        await aircraft(client, auth[Role.SUPERVISOR], callsign)

    page1 = await client.get(
        AUDIT, params={"action": "aircraft.", "limit": 2}, headers=auth[Role.SUPERVISOR]
    )
    page2 = await client.get(
        AUDIT,
        params={"action": "aircraft.", "limit": 2, "cursor": page1.json()["next_cursor"]},
        headers=auth[Role.SUPERVISOR],
    )
    logins = await client.get(AUDIT, params={"action": "auth."}, headers=auth[Role.SUPERVISOR])

    seqs = [e["seq"] for e in page1.json()["items"] + page2.json()["items"]]
    assert seqs == sorted(seqs, reverse=True)
    assert len(seqs) == 3
    assert page2.json()["next_cursor"] is None
    assert {e["action"] for e in logins.json()["items"]} == {"auth.login"}


async def test_action_filter_is_a_literal_prefix(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.get(AUDIT, params={"action": "auth_%"}, headers=auth[Role.SUPERVISOR])

    assert response.json()["items"] == []


async def test_operators_cannot_read_the_audit_trail(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.get(AUDIT, headers=auth[Role.OPERATOR])

    assert response.status_code == 403


async def test_the_chain_status_reports_the_head_or_where_it_breaks(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], context: AppContext
) -> None:
    await aircraft(client, auth[Role.SUPERVISOR], "HX-1")

    intact = (await client.get(f"{AUDIT}/verify", headers=auth[Role.SUPERVISOR])).json()
    async with context.database().ops_session() as db:
        await db.execute(text("UPDATE audit_events SET action = 'x' WHERE seq = 1"))
        await db.commit()
    broken = (await client.get(f"{AUDIT}/verify", headers=auth[Role.SUPERVISOR])).json()

    assert intact["ok"] is True
    assert intact["events"] >= 2  # the logins and the aircraft
    assert intact["head_hash"] is not None
    assert broken["ok"] is False
    assert broken["broken_at_seq"] == 1
    assert broken["head_hash"] is None


async def test_an_export_carries_the_selected_events_and_is_itself_audited(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    for callsign in ("A1", "A2"):
        await aircraft(client, auth[Role.SUPERVISOR], callsign)

    as_csv = await client.get(
        f"{AUDIT}/export", params={"action": "aircraft."}, headers=auth[Role.SUPERVISOR]
    )
    as_jsonl = await client.get(
        f"{AUDIT}/export",
        params={"action": "aircraft.", "format": "jsonl"},
        headers=auth[Role.SUPERVISOR],
    )
    latest = (await client.get(AUDIT, params={"limit": 1}, headers=auth[Role.SUPERVISOR])).json()

    assert as_csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in as_csv.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert [r["action"] for r in rows] == ["aircraft.create", "aircraft.create"]  # oldest first
    assert json.loads(rows[0]["details"])["after"]["callsign"] == "A1"
    lines = [json.loads(line) for line in as_jsonl.text.splitlines()]
    assert [e["seq"] for e in lines] == [int(r["seq"]) for r in rows]
    assert all(e["hash"] and e["prev_hash"] for e in lines)
    export = latest["items"][0]
    assert export["action"] == "audit.export"
    assert export["details"] == {
        "format": "jsonl",
        "events": 2,
        "filters": {"action": "aircraft."},
    }


async def test_operators_cannot_verify_or_export(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    for path in ("/verify", "/export"):
        response = await client.get(f"{AUDIT}{path}", headers=auth[Role.OPERATOR])
        assert response.status_code == 403
