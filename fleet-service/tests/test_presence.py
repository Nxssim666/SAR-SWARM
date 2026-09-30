"""Who is connected (M5): users heard in the last 30 seconds, with their roles."""

import httpx

from fleet_service.context import AppContext
from fleet_service.domain.enums import Role

from support import FakeClock


async def test_presence_lists_users_heard_recently_with_their_role(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    user_ids: dict[Role, str],
    context: AppContext,
    clock: FakeClock,
) -> None:
    presence = context.runtime().presence
    presence.touch(user_ids[Role.OPERATOR], clock.now())
    clock.advance(seconds=20)
    presence.touch(user_ids[Role.SUPERVISOR], clock.now())

    both = (await client.get("/api/v1/presence", headers=auth[Role.OBSERVER])).json()
    clock.advance(seconds=15)  # the operator was last heard 35 s ago
    one = (await client.get("/api/v1/presence", headers=auth[Role.OBSERVER])).json()

    # Any authenticated request counts as being here, so the observer asking is listed first.
    assert [(p["user"]["username"], p["role"]) for p in both["users"]] == [
        ("observer", "observer"),
        ("supervisor", "supervisor"),
        ("operator", "operator"),
    ]
    assert [p["user"]["username"] for p in one["users"]] == ["observer", "supervisor"]


async def test_signed_in_users_who_went_quiet_are_not_listed(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], clock: FakeClock
) -> None:
    clock.advance(seconds=31)  # every role signed in (the auth fixture), then fell silent

    response = await client.get("/api/v1/presence", headers=auth[Role.OBSERVER])

    assert [p["user"]["username"] for p in response.json()["users"]] == ["observer"]
