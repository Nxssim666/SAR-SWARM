"""Reading the audit trail through the API; every mutation leaves a verifiable record."""

import httpx

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
