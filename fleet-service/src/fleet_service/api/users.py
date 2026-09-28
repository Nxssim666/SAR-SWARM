"""Operator accounts (ADR 0009). Users are never deleted, only deactivated."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import AwareDatetime, StringConstraints, field_validator
from sqlalchemy import func, select

from fleet_service.api.common import (
    InputModel,
    OutputModel,
    PageParams,
    PatchModel,
    StrictBool,
    apply_values,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import (
    Context,
    CurrentPrincipal,
    DbSession,
    actor,
    announce_session_end,
    requires,
)
from fleet_service.api.helpers import commit_or_conflict, get_or_404
from fleet_service.api.pages import Page
from fleet_service.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from fleet_service.auth.permissions import Permission
from fleet_service.auth.sessions import revoke_user_sessions
from fleet_service.db.models import User
from fleet_service.domain.enums import Role
from fleet_service.errors import Conflict, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

router = APIRouter(
    prefix="/users", tags=["users"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)

Username = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$"),
]
DisplayName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, pattern=r"^\S(?:.*\S)?$")
]
Password = Annotated[
    str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]


class UserOut(OutputModel):
    """An operator account (never includes credentials)."""

    id: str
    username: str
    display_name: str
    role: Role
    is_active: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_login_at: AwareDatetime | None


class UserPage(Page[UserOut]):
    """A page of users."""


class UserCreate(InputModel):
    """A new account. The username is stored lower-case."""

    username: Username
    display_name: DisplayName
    role: Role
    password: Password

    @field_validator("username")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class UserUpdate(PatchModel):
    """Fields to change; omitted fields are unchanged."""

    display_name: DisplayName = optional()
    role: Role = optional()
    is_active: StrictBool = optional()


class PasswordReset(InputModel):
    """An administrator sets a new password; the user's sessions are revoked."""

    new_password: Password


def user_snapshot(user: User) -> dict[str, object]:
    """JSON snapshot for audit diffs."""
    return UserOut.model_validate(user).model_dump(mode="json")


@router.get("", **requires(Permission.USERS_VIEW))
async def list_users(db: DbSession, page: Annotated[PageParams, Depends(page_params)]) -> UserPage:
    """List accounts in creation order."""
    rows, cursor = await fetch_page(db, select(User), User.id, page)
    return UserPage(items=[UserOut.model_validate(u) for u in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.USERS_MANAGE))
async def create_user(
    body: UserCreate, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> UserOut:
    """Create an account."""
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise Conflict(f"Username {body.username!r} is taken.", slug="username-taken")
    await db.commit()  # end the transaction before the slow hash (ADR 0019)
    password_hash = await context.passwords.hash(body.password)
    now = context.clock.now()
    user = User(
        id=new_id(),
        username=body.username,
        display_name=body.display_name,
        role=body.role,
        password_hash=password_hash,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    db.add(user)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "user.create",
        entity_type="user",
        entity_id=user.id,
        details={"after": user_snapshot(user)},
    )
    await commit_or_conflict(db, f"Username {body.username!r} is taken.")
    return UserOut.model_validate(user)


@router.get("/{user_id}", **requires(Permission.USERS_VIEW))
async def get_user(user_id: str, db: DbSession) -> UserOut:
    """One account."""
    return UserOut.model_validate(await get_or_404(db, User, user_id, "User"))


@router.patch("/{user_id}", **requires(Permission.USERS_MANAGE))
async def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> UserOut:
    """Change display name, role or active flag. Deactivation revokes the user's sessions."""
    user = await get_or_404(db, User, user_id, "User")
    values = patch_values(body)
    loses_admin = (
        user.role is Role.ADMIN
        and user.is_active
        and (values.get("role", Role.ADMIN) is not Role.ADMIN or values.get("is_active") is False)
    )
    if loses_admin:
        other_admins = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN, User.is_active.is_(True), User.id != user.id)
        )
        if not other_admins:
            raise Conflict(
                "This is the last active admin; create another admin first.", slug="last-admin"
            )
    before = user_snapshot(user)
    now = context.clock.now()
    apply_values(user, values)
    user.updated_at = now
    if values.get("is_active") is False:
        await revoke_user_sessions(db, user.id, now)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "user.update",
        entity_type="user",
        entity_id=user.id,
        details={"changes": audit.changes(before, user_snapshot(user))},
    )
    await db.commit()
    if values.get("is_active") is False:
        announce_session_end(context, user_id=user.id)
    return UserOut.model_validate(user)


@router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    **requires(Permission.USERS_MANAGE),
)
async def reset_password(
    user_id: str,
    body: PasswordReset,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Set a new password for a user and revoke all of their sessions."""
    await get_or_404(db, User, user_id, "User")
    await db.commit()
    password_hash = await context.passwords.hash(body.new_password)
    user = await get_or_404(db, User, user_id, "User")
    now = context.clock.now()
    user.password_hash = password_hash
    user.updated_at = now
    await revoke_user_sessions(db, user.id, now)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "user.password_reset",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    announce_session_end(context, user_id=user.id)
