"""Login, sessions, logout, password changes, rate limiting (ADR 0009)."""

import httpx
from sqlalchemy import select, text

from fleet_service.auth.sessions import hash_token
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent, UserSession
from fleet_service.domain.enums import Role

from support import PASSWORD, FakeClock, bearer, insert_user, login

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


async def audit_actions(context: AppContext) -> list[str]:
    async with context.database().ops_session() as db:
        return list((await db.scalars(select(AuditEvent.action).order_by(AuditEvent.seq))).all())


async def test_login_returns_a_session_with_permissions(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)

    response = await client.post(LOGIN, json={"username": "ALICE", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "alice"
    assert body["permissions"] == [
        "fleet.view",
        "missions.plan",
        "alerts.ack",
        "aircraft.hold",
        "aircraft.command",
    ]
    assert body["expires_at"] == "2026-09-28T20:00:00Z"  # 12 h after the fake clock's start
    assert "password_hash" not in body["user"]
    assert await audit_actions(context) == ["auth.login"]


async def test_only_the_token_hash_is_stored(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)

    token = await login(client, "alice")

    async with context.database().ops_session() as db:
        stored = (await db.scalars(select(UserSession.token_hash))).all()
        dump = "\n".join(str(r) for r in (await db.execute(text("select * from sessions"))).all())
    assert stored == [hash_token(token)]
    assert token not in dump


async def test_bad_credentials_get_one_generic_answer_and_are_audited(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)
    await insert_user(context, "bob", Role.OPERATOR, is_active=False)

    responses = [
        await client.post(LOGIN, json={"username": "alice", "password": "wrong-password"}),
        await client.post(LOGIN, json={"username": "nobody", "password": PASSWORD}),
        await client.post(LOGIN, json={"username": "bob", "password": PASSWORD}),
    ]

    assert {r.status_code for r in responses} == {401}
    assert {r.json()["detail"] for r in responses} == {"Invalid username or password."}
    assert all(r.headers["content-type"] == "application/problem+json" for r in responses)
    assert await audit_actions(context) == ["auth.login_failed"] * 3
    async with context.database().ops_session() as db:
        reasons = [e.details["reason"] for e in (await db.scalars(select(AuditEvent))).all()]
    assert reasons == ["bad_password", "unknown_user", "inactive_user"]


async def test_failed_logins_are_rate_limited_per_username(
    client: httpx.AsyncClient, context: AppContext, clock: FakeClock
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)
    for _ in range(5):
        bad = await client.post(LOGIN, json={"username": "alice", "password": "wrong-password"})
        assert bad.status_code == 401

    blocked = await client.post(LOGIN, json={"username": "alice", "password": PASSWORD})

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "300"
    assert blocked.json()["retry_after_s"] == 300
    clock.advance(seconds=301)
    assert (await client.post(LOGIN, json={"username": "alice", "password": PASSWORD})).is_success


async def test_missing_or_garbage_token_is_401_with_challenge(client: httpx.AsyncClient) -> None:
    missing = await client.get(ME)
    garbage = await client.get(ME, headers=bearer("sgcs_not-a-real-token"))

    for response in (missing, garbage):
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["type"] == "urn:sar-gcs:problem:unauthenticated"


async def test_me_reports_user_permissions_and_expiry(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.get(ME, headers=auth[Role.SUPERVISOR])

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "supervisor"
    assert "audit.read" in body["permissions"]
    assert "users.manage" not in body["permissions"]
    assert body["session_expires_at"] == "2026-09-28T20:00:00Z"


async def test_idle_sessions_expire(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], clock: FakeClock
) -> None:
    clock.advance(hours=3, minutes=59)
    assert (await client.get(ME, headers=auth[Role.OPERATOR])).status_code == 200

    clock.advance(hours=4, seconds=1)  # 4 h after the last use

    assert (await client.get(ME, headers=auth[Role.OPERATOR])).status_code == 401


async def test_sessions_end_after_one_shift_even_when_used(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], clock: FakeClock
) -> None:
    for _ in range(11):
        clock.advance(hours=1)
        assert (await client.get(ME, headers=auth[Role.OPERATOR])).status_code == 200

    clock.advance(hours=1)

    assert (await client.get(ME, headers=auth[Role.OPERATOR])).status_code == 401


async def test_logout_revokes_only_that_session(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)
    laptop, tablet = bearer(await login(client, "alice")), bearer(await login(client, "alice"))

    response = await client.post("/api/v1/auth/logout", headers=laptop)

    assert response.status_code == 204
    assert (await client.get(ME, headers=laptop)).status_code == 401
    assert (await client.get(ME, headers=tablet)).status_code == 200


async def test_password_change_requires_the_current_password(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)
    headers = bearer(await login(client, "alice"))

    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong-password", "new_password": "a-new-long-password"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["type"] == "urn:sar-gcs:problem:invalid-credentials"
    assert "auth.password_change_failed" in await audit_actions(context)


async def test_password_change_revokes_other_sessions(
    client: httpx.AsyncClient, context: AppContext
) -> None:
    await insert_user(context, "alice", Role.OPERATOR)
    current, other = bearer(await login(client, "alice")), bearer(await login(client, "alice"))

    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "a-new-long-password"},
        headers=current,
    )

    assert response.status_code == 204
    assert (await client.get(ME, headers=current)).status_code == 200
    assert (await client.get(ME, headers=other)).status_code == 401
    assert (
        await client.post(LOGIN, json={"username": "alice", "password": PASSWORD})
    ).status_code == 401
    assert await login(client, "alice", "a-new-long-password")


async def test_new_password_must_be_long_enough(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "Tiny7pw"},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "new_password"]
    assert "Tiny7pw" not in response.text  # submitted secrets are never echoed
