"""
API contract (ADR 0013): the committed OpenAPI document matches the code, every error
is documented as problem+json, and the running API conforms to the document
(Schemathesis property-based tests, positive and negative data).
"""

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import schemathesis
from fastapi import FastAPI
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from schemathesis import CheckFunction
from schemathesis.python import asgi as schemathesis_asgi
from schemathesis.specs.openapi.checks import positive_data_acceptance

from fleet_service import cli
from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.config import Settings
from fleet_service.db.engine import OPS_DB, TELEMETRY_DB, Database
from fleet_service.db.models import User
from fleet_service.domain.enums import Role
from fleet_service.ids import new_id
from fleet_service.main import create_app

from support import PASSWORD, START, bearer

COMMITTED_SPEC = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def test_committed_openapi_matches_the_code(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    cli.main(["export-openapi", "--output", str(generated)])

    assert COMMITTED_SPEC.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), (
        "docs/api/openapi.json is stale: run `fleet-service export-openapi` and commit the result"
    )


def test_every_error_response_is_documented_as_problem_json(tmp_path: Path) -> None:
    schema = create_app(Settings(data_dir=tmp_path)).openapi()

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if status.startswith(("4", "5")):
                    assert list(response["content"]) == ["application/problem+json"], (
                        method,
                        path,
                        status,
                    )


# --- Schemathesis ---------------------------------------------------------------------------


async def _insert_admin(data_dir: Path) -> None:
    database = Database(data_dir)
    try:
        async with database.ops_session() as db:
            db.add(
                User(
                    id=new_id(),
                    username="admin",
                    display_name="Admin",
                    role=Role.ADMIN,
                    password_hash=await fast_passwords_for_tests().hash(PASSWORD),
                    is_active=True,
                    created_at=START,
                    updated_at=START,
                    last_login_at=None,
                )
            )
            await db.commit()
    finally:
        await database.dispose()


@pytest.fixture(scope="module")
def contract_app(
    tmp_path_factory: pytest.TempPathFactory, migrated_template: Path
) -> Iterator[FastAPI]:
    data_dir = tmp_path_factory.mktemp("contract")
    for name in (OPS_DB, TELEMETRY_DB):
        shutil.copy(migrated_template / name, data_dir / name)
    asyncio.run(_insert_admin(data_dir))
    yield create_app(Settings(data_dir=data_dir), passwords=fast_passwords_for_tests())
    schemathesis_asgi.shutdown_lifespans()


@pytest.fixture(scope="module")
def api_schema(contract_app: FastAPI) -> schemathesis.BaseSchema:
    schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", contract_app)
    # Logging out would end the session the rest of the run authenticates with.
    return schema.exclude(path="/api/v1/auth/logout")


@pytest.fixture(scope="module")
def admin_headers(contract_app: FastAPI, api_schema: schemathesis.BaseSchema) -> dict[str, str]:
    with schemathesis_asgi.get_client(cast("Any", contract_app)) as http:
        response = http.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    response.raise_for_status()
    return bearer(response.json()["token"])


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@hypothesis_settings(max_examples=15, deadline=None, suppress_health_check=list(HealthCheck))
def test_api_conforms_to_its_openapi_document(
    case: schemathesis.Case[Any], admin_headers: dict[str, str]
) -> None:
    # positive_data_acceptance is excluded on purpose: schema-valid requests are still
    # rightly refused by rules JSON Schema cannot express (polygon validity, operating
    # area, references to existing entities, state transitions). Every other check runs:
    # no 5xx, documented status codes/content types/schemas, negative data rejected,
    # authentication enforced.
    case.call_and_validate(
        headers=admin_headers, excluded_checks=[cast("CheckFunction", positive_data_acceptance)]
    )
