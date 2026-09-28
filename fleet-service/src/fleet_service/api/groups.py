"""Named aircraft groups, for selection and bulk tasking."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import AfterValidator, AwareDatetime, Field
from sqlalchemy import select

from fleet_service.api.common import (
    EntityId,
    InputModel,
    Notes,
    OutputModel,
    PageParams,
    PatchModel,
    ShortName,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import commit_or_conflict, get_or_404
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Aircraft, AircraftGroup
from fleet_service.errors import Conflict, InvalidRequest, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

router = APIRouter(
    prefix="/groups", tags=["groups"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)


def _no_duplicates(ids: list[str]) -> list[str]:
    if len(set(ids)) != len(ids):
        raise ValueError("aircraft_ids must not contain duplicates")
    return ids


AircraftIds = Annotated[
    list[EntityId],
    AfterValidator(_no_duplicates),
    Field(max_length=254, json_schema_extra={"uniqueItems": True}),
]


class GroupOut(OutputModel):
    """A named set of aircraft."""

    id: str
    name: str
    description: str | None
    aircraft_ids: list[str]
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, group: AircraftGroup) -> "GroupOut":
        """Build from a row."""
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            aircraft_ids=sorted(a.id for a in group.members),
            created_at=group.created_at,
            updated_at=group.updated_at,
        )


class GroupPage(Page[GroupOut]):
    """A page of groups."""


class GroupCreate(InputModel):
    """A new group."""

    name: ShortName
    description: Notes | None = None
    aircraft_ids: AircraftIds = Field(default_factory=list)


class GroupUpdate(PatchModel):
    """Fields to change; ``aircraft_ids`` replaces the whole membership."""

    name: ShortName = optional()
    description: Notes | None = optional()
    aircraft_ids: AircraftIds = optional()


async def _resolve_members(db: DbSession, ids: list[str]) -> list[Aircraft]:
    found = list((await db.scalars(select(Aircraft).where(Aircraft.id.in_(ids)))).all())
    unknown = sorted(set(ids) - {a.id for a in found})
    if unknown:
        raise InvalidRequest(
            f"Unknown aircraft: {', '.join(unknown)}.",
            slug="unknown-reference",
            extensions={"field": "aircraft_ids", "unknown_ids": unknown},
        )
    return found


async def _ensure_name_free(db: DbSession, name: str, exclude_id: str) -> None:
    if await db.scalar(
        select(AircraftGroup.id).where(AircraftGroup.name == name, AircraftGroup.id != exclude_id)
    ):
        raise Conflict(f"A group named {name!r} exists.", slug="group-name-taken")


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_groups(
    db: DbSession, page: Annotated[PageParams, Depends(page_params)]
) -> GroupPage:
    """List groups."""
    rows, cursor = await fetch_page(db, select(AircraftGroup), AircraftGroup.id, page)
    return GroupPage(items=[GroupOut.of(g) for g in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.FLEET_MANAGE))
async def create_group(
    body: GroupCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> GroupOut:
    """Create a group."""
    await _ensure_name_free(db, body.name, "")
    members = await _resolve_members(db, body.aircraft_ids)
    now = context.clock.now()
    group = AircraftGroup(
        id=new_id(), name=body.name, description=body.description, created_at=now, updated_at=now
    )
    group.members = members
    db.add(group)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "group.create",
        entity_type="group",
        entity_id=group.id,
        details={"after": GroupOut.of(group).model_dump(mode="json")},
    )
    await commit_or_conflict(db, f"A group named {body.name!r} exists.")
    return GroupOut.of(group)


@router.get("/{group_id}", **requires(Permission.FLEET_VIEW))
async def get_group(group_id: str, db: DbSession) -> GroupOut:
    """One group."""
    return GroupOut.of(await get_or_404(db, AircraftGroup, group_id, "Group"))


@router.patch("/{group_id}", **requires(Permission.FLEET_MANAGE))
async def update_group(
    group_id: str,
    body: GroupUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> GroupOut:
    """Rename a group or replace its members."""
    group = await get_or_404(db, AircraftGroup, group_id, "Group")
    values = patch_values(body)
    if "name" in values:
        await _ensure_name_free(db, values["name"], group.id)
    before = GroupOut.of(group).model_dump(mode="json")
    now = context.clock.now()
    if "aircraft_ids" in values:
        group.members = await _resolve_members(db, values.pop("aircraft_ids"))
    for name, value in values.items():
        setattr(group, name, value)
    group.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "group.update",
        entity_type="group",
        entity_id=group.id,
        details={"changes": audit.changes(before, GroupOut.of(group).model_dump(mode="json"))},
    )
    await commit_or_conflict(db, "A group with this name exists.")
    return GroupOut.of(group)


@router.delete(
    "/{group_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.FLEET_MANAGE)
)
async def delete_group(
    group_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Delete a group (its aircraft are unaffected)."""
    group = await get_or_404(db, AircraftGroup, group_id, "Group")
    before = GroupOut.of(group).model_dump(mode="json")
    now = context.clock.now()
    await db.delete(group)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "group.delete",
        entity_type="group",
        entity_id=group_id,
        details={"before": before},
    )
    await db.commit()
