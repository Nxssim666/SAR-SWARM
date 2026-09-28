"""Account management: create, update, deactivate, reset; last-admin protection."""

import httpx

from fleet_service.domain.enums import Role

from support import PASSWORD, bearer, login

USERS = "/api/v1/users"


async def test_admin_creates_users_with_normalized_usernames(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.post(
        USERS,
        json={
            "username": "Carol.M",
            "display_name": "Carol M",
            "role": "operator",
            "password": PASSWORD,
        },
        headers=auth[Role.ADMIN],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "carol.m"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body
    assert await login(client, "carol.m")


async def test_usernames_are_unique_ignoring_case(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.post(
        USERS,
        json={
            "username": "OPERATOR",
            "display_name": "Dup",
            "role": "observer",
            "password": PASSWORD,
        },
        headers=auth[Role.ADMIN],
    )

    assert response.status_code == 409
    assert response.json()["type"] == "urn:sar-gcs:problem:username-taken"


async def test_supervisors_see_users_but_cannot_manage_them(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    listed = await client.get(USERS, headers=auth[Role.SUPERVISOR])
    created = await client.post(
        USERS,
        json={"username": "dave", "display_name": "Dave", "role": "admin", "password": PASSWORD},
        headers=auth[Role.SUPERVISOR],
    )

    assert listed.status_code == 200
    assert {u["username"] for u in listed.json()["items"]} == {r.value for r in Role}
    assert created.status_code == 403
    assert created.json()["required_permission"] == "users.manage"


async def test_deactivation_revokes_sessions_immediately(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    response = await client.patch(
        f"{USERS}/{user_ids[Role.OPERATOR]}", json={"is_active": False}, headers=auth[Role.ADMIN]
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await client.get("/api/v1/auth/me", headers=auth[Role.OPERATOR])).status_code == 401
    failed = await client.post(
        "/api/v1/auth/login", json={"username": "operator", "password": PASSWORD}
    )
    assert failed.status_code == 401


async def test_role_change_takes_effect_on_the_next_request(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    await client.patch(
        f"{USERS}/{user_ids[Role.OBSERVER]}", json={"role": "supervisor"}, headers=auth[Role.ADMIN]
    )

    response = await client.get(USERS, headers=auth[Role.OBSERVER])

    assert response.status_code == 200


async def test_the_last_active_admin_cannot_be_demoted_or_deactivated(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    admin = f"{USERS}/{user_ids[Role.ADMIN]}"

    demoted = await client.patch(admin, json={"role": "operator"}, headers=auth[Role.ADMIN])
    deactivated = await client.patch(admin, json={"is_active": False}, headers=auth[Role.ADMIN])

    for response in (demoted, deactivated):
        assert response.status_code == 409
        assert response.json()["type"] == "urn:sar-gcs:problem:last-admin"


async def test_an_admin_can_step_down_once_another_admin_exists(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    await client.patch(
        f"{USERS}/{user_ids[Role.SUPERVISOR]}", json={"role": "admin"}, headers=auth[Role.ADMIN]
    )

    response = await client.patch(
        f"{USERS}/{user_ids[Role.ADMIN]}", json={"role": "supervisor"}, headers=auth[Role.ADMIN]
    )

    assert response.status_code == 200


async def test_admin_password_reset_revokes_the_users_sessions(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    response = await client.post(
        f"{USERS}/{user_ids[Role.OPERATOR]}/password",
        json={"new_password": "temporary-password-1"},
        headers=auth[Role.ADMIN],
    )

    assert response.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=auth[Role.OPERATOR])).status_code == 401
    assert bearer(await login(client, "operator", "temporary-password-1"))


async def test_patch_rejects_null_for_non_nullable_fields(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    response = await client.patch(
        f"{USERS}/{user_ids[Role.OPERATOR]}", json={"display_name": None}, headers=auth[Role.ADMIN]
    )

    assert response.status_code == 422


async def test_users_cannot_be_deleted(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], user_ids: dict[Role, str]
) -> None:
    response = await client.delete(f"{USERS}/{user_ids[Role.OPERATOR]}", headers=auth[Role.ADMIN])

    assert response.status_code == 405


async def test_user_list_paginates_in_creation_order(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    first = await client.get(USERS, params={"limit": 3}, headers=auth[Role.ADMIN])
    second = await client.get(
        USERS, params={"limit": 3, "cursor": first.json()["next_cursor"]}, headers=auth[Role.ADMIN]
    )

    names = [u["username"] for u in first.json()["items"] + second.json()["items"]]
    assert names == [r.value for r in Role]  # the fixture creates them in role order
    assert second.json()["next_cursor"] is None
