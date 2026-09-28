"""
Authorization matrix (ADR 0015): every operation in the OpenAPI document, for every role.

The permission each operation enforces is published as ``x-permission`` by the same
code that enforces it (``api.deps.requires``). This test checks behaviour against that
publication: no token -> 401; a role without the permission -> 403; a role with it ->
never 401/403 (a dummy request then fails later, typically 404 or 422). It also fails
if any operation other than the explicit public ones lacks ``x-permission``.
"""

import re
import tempfile
from pathlib import Path

import httpx
import pytest

from fleet_service.auth.permissions import AUTHENTICATED, Permission, has_permission
from fleet_service.config import Settings
from fleet_service.domain.enums import Role
from fleet_service.main import create_app

from support import bearer, login

PUBLIC = {
    ("get", "/api/v1/health"),
    ("get", "/api/v1/version"),
    ("post", "/api/v1/auth/login"),
}
DUMMY_ID = "00000000-0000-7000-8000-000000000000"

_SCHEMA = create_app(Settings(data_dir=Path(tempfile.gettempdir()) / "sargcs-unused")).openapi()
OPERATIONS = [
    (method, path, operation.get("x-permission"))
    for path, operations in _SCHEMA["paths"].items()
    for method, operation in operations.items()
]
PROTECTED = [op for op in OPERATIONS if (op[0], op[1]) not in PUBLIC]


def test_public_operations_are_exactly_the_expected_ones() -> None:
    unmarked = {(method, path) for method, path, permission in OPERATIONS if permission is None}

    assert unmarked == PUBLIC


def test_every_protected_operation_declares_a_known_permission() -> None:
    known = {p.value for p in Permission} | {AUTHENTICATED}

    assert {permission for _, _, permission in PROTECTED} <= known


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    PROTECTED,
    ids=[f"{m.upper()} {p}" for m, p, _ in PROTECTED],
)
async def test_operation_enforces_its_published_permission(
    client: httpx.AsyncClient,
    user_ids: dict[Role, str],
    method: str,
    path: str,
    permission: str,
) -> None:
    url = re.sub(r"\{[^}]+\}", DUMMY_ID, path)
    body: dict[str, object] | None = {} if method in {"post", "put", "patch"} else None

    anonymous = await client.request(method.upper(), url, json=body)
    assert anonymous.status_code == 401, anonymous.text

    for role in Role:
        headers = bearer(await login(client, role.value))  # fresh: logout revokes its session
        response = await client.request(method.upper(), url, json=body, headers=headers)
        allowed = permission == AUTHENTICATED or has_permission(role, Permission(permission))
        if allowed:
            assert response.status_code not in {401, 403}, (role, response.text)
        else:
            assert response.status_code == 403, (role, response.text)
            assert response.json()["required_permission"] == permission
