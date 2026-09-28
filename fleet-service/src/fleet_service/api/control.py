"""Control leases (ADR 0011): take, release, hand over, and supervisors' assignment."""

from typing import Annotated

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, StringConstraints

from fleet_service.api.common import EntityId, InputModel
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.auth.permissions import Permission
from fleet_service.errors import NotFound, problem_responses
from fleet_service.services.runtime import Runtime
from fleet_service.services.views import LeaseView

router = APIRouter(tags=["control"], responses=problem_responses(400, 401, 403, 404, 409, 422))


class LeaseList(BaseModel):
    """Every control lease."""

    items: list[LeaseView]


class ControlAssignment(InputModel):
    """Supervisor: give control to a user (or to nobody), overriding the current holder."""

    user_id: EntityId | None
    reason: Annotated[
        str, StringConstraints(min_length=3, max_length=500, pattern=r"^\S(?:.*\S)?$")
    ]


def _require_aircraft(runtime: Runtime, aircraft_id: str) -> None:
    if runtime.registry.get(aircraft_id) is None:
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")


@router.get("/control-leases", **requires(Permission.FLEET_VIEW))
async def list_leases(context: Context) -> LeaseList:
    """Who controls which aircraft."""
    return LeaseList(items=context.runtime().leases.views())


@router.post("/aircraft/{aircraft_id}/control", **requires(Permission.AIRCRAFT_COMMAND))
async def take_control(
    aircraft_id: str, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> LeaseView:
    """Take control of an aircraft nobody controls."""
    runtime = context.runtime()
    _require_aircraft(runtime, aircraft_id)
    view = await runtime.leases.take(
        db, context.clock.now(), principal, aircraft_id, actor(request, principal)
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)
    return view


@router.delete(
    "/aircraft/{aircraft_id}/control",
    status_code=status.HTTP_204_NO_CONTENT,
    **requires(Permission.AIRCRAFT_COMMAND),
)
async def release_control(
    aircraft_id: str, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> None:
    """Give up control of an aircraft you control."""
    runtime = context.runtime()
    _require_aircraft(runtime, aircraft_id)
    await runtime.leases.release(
        db, context.clock.now(), principal, aircraft_id, actor(request, principal)
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)


@router.post("/aircraft/{aircraft_id}/control/handover", **requires(Permission.AIRCRAFT_COMMAND))
async def request_handover(
    aircraft_id: str, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> LeaseView:
    """Ask the controlling operator to hand the aircraft over (expires if unanswered)."""
    runtime = context.runtime()
    _require_aircraft(runtime, aircraft_id)
    view = await runtime.leases.request_handover(
        db, context.clock.now(), principal, aircraft_id, actor(request, principal)
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)
    return view


async def _answer(
    accept: bool,
    aircraft_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> LeaseView:
    runtime = context.runtime()
    _require_aircraft(runtime, aircraft_id)
    view = await runtime.leases.answer_handover(
        db, context.clock.now(), principal, aircraft_id, accept, actor(request, principal)
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)
    if view is None:  # pragma: no cover - answering always leaves a lease
        raise NotFound("No lease.")
    return view


@router.post(
    "/aircraft/{aircraft_id}/control/handover/accept", **requires(Permission.AIRCRAFT_COMMAND)
)
async def accept_handover(
    aircraft_id: str, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> LeaseView:
    """Controller: hand the aircraft to the operator who asked."""
    return await _answer(True, aircraft_id, request, db, context, principal)


@router.post(
    "/aircraft/{aircraft_id}/control/handover/decline", **requires(Permission.AIRCRAFT_COMMAND)
)
async def decline_handover(
    aircraft_id: str, request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> LeaseView:
    """Controller: keep the aircraft."""
    return await _answer(False, aircraft_id, request, db, context, principal)


@router.put("/aircraft/{aircraft_id}/control", **requires(Permission.CONTROL_OVERRIDE))
async def assign_control(
    aircraft_id: str,
    body: ControlAssignment,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> LeaseView | None:
    """Supervisor: assign or force control (``user_id`` null releases it). Needs a reason."""
    runtime = context.runtime()
    _require_aircraft(runtime, aircraft_id)
    view = await runtime.leases.assign(
        db, context.clock.now(), aircraft_id, body.user_id, body.reason, actor(request, principal)
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)
    return view
