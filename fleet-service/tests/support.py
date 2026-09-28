"""Test helpers shared by fixtures and tests (importable, unlike conftest)."""

from datetime import UTC, datetime, timedelta

import httpx

from fleet_service.context import AppContext
from fleet_service.db.models import User
from fleet_service.domain.enums import Role
from fleet_service.ids import new_id

PASSWORD = "correct-horse-battery"
START = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


class FakeClock:
    """A clock that moves only when told to."""

    def __init__(self, start: datetime = START) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


async def insert_user(
    context: AppContext,
    username: str,
    role: Role,
    *,
    password: str = PASSWORD,
    is_active: bool = True,
) -> str:
    """Create a user directly in the database; return its id."""
    now = context.clock.now()
    user = User(
        id=new_id(),
        username=username,
        display_name=username.title(),
        role=role,
        password_hash=await context.passwords.hash(password),
        is_active=is_active,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    async with context.database().ops_session() as db:
        db.add(user)
        await db.commit()
    return user.id


async def login(client: httpx.AsyncClient, username: str, password: str = PASSWORD) -> str:
    """Log in; return the bearer token."""
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["token"]
    return token


def bearer(token: str) -> dict[str, str]:
    """Authorization header for ``token``."""
    return {"Authorization": f"Bearer {token}"}
