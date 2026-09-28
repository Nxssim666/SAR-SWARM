"""
Commands to aircraft (ADR 0011, ADR 0020).

``POST /commands`` runs the whole pipeline and answers with the per-aircraft outcome.
Risky or bulk commands first get a **428** with a server-computed summary and a
confirmation token; re-send the *identical* request with ``confirmation_token`` to
execute it. ``command_id`` is the client's idempotency key.
"""

import hashlib
import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Query, Request
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from sqlalchemy import select

from fleet_service.api.common import AltitudeRelative, EntityId, InputModel
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Command
from fleet_service.domain.commands import GotoTarget
from fleet_service.domain.enums import CommandKind
from fleet_service.domain.geo import GeoPoint
from fleet_service.errors import NotFound, problem_responses
from fleet_service.services.commands import CommandSpec, ConfirmationProblem
from fleet_service.services.views import CommandView

router = APIRouter(
    prefix="/commands", tags=["commands"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)


def _no_duplicates(ids: list[str]) -> list[str]:
    if len(set(ids)) != len(ids):
        raise ValueError("aircraft_ids must not contain duplicates")
    return ids


TakeoffAltitude = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0, le=1500.0, description="Metres above home."),
]


class _CommandRequest(InputModel):
    command_id: uuid.UUID = Field(description="Client-generated; the idempotency key.")
    aircraft_ids: Annotated[
        list[EntityId],
        AfterValidator(_no_duplicates),
        Field(min_length=1, max_length=254, json_schema_extra={"uniqueItems": True}),
    ]
    confirmation_token: Annotated[str, StringConstraints(max_length=200)] | None = Field(
        default=None, description="From a 428 answer to this exact request."
    )


class ArmCommand(_CommandRequest):
    """Arm the motors (on the ground). Always confirmed."""

    kind: Literal["arm"]


class DisarmCommand(_CommandRequest):
    """Disarm (on the ground only; never in flight)."""

    kind: Literal["disarm"]


class TakeoffCommand(_CommandRequest):
    """Take off to an altitude above home. Always confirmed."""

    kind: Literal["takeoff"]
    altitude_relative_m: TakeoffAltitude


class HoldCommand(_CommandRequest):
    """Stop and hold position (hover or loiter). Any operator, any aircraft."""

    kind: Literal["hold"]


class ResumeCommand(_CommandRequest):
    """Continue what HOLD paused."""

    kind: Literal["resume"]


class ReturnCommand(_CommandRequest):
    """Return to launch and land."""

    kind: Literal["return_to_launch"]


class LandCommand(_CommandRequest):
    """Land where the aircraft is."""

    kind: Literal["land"]


class GotoCommand(_CommandRequest):
    """Fly to a position (and altitude above home), then hold there."""

    kind: Literal["goto"]
    target: GeoPoint
    altitude_relative_m: AltitudeRelative | None = None


CommandRequest = Annotated[
    ArmCommand
    | DisarmCommand
    | TakeoffCommand
    | HoldCommand
    | ResumeCommand
    | ReturnCommand
    | LandCommand
    | GotoCommand,
    Field(discriminator="kind"),
]


class CommandList(BaseModel):
    """Recent commands, newest first."""

    items: list[CommandView]


def spec_of(body: _CommandRequest) -> CommandSpec:
    """Turn a validated request into the pipeline's input."""
    request = body.model_dump(mode="json", exclude={"confirmation_token"})
    request_hash = hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    params = {k: v for k, v in request.items() if k not in {"command_id", "aircraft_ids", "kind"}}
    goto = None
    if isinstance(body, GotoCommand):
        goto = GotoTarget(body.target.latitude, body.target.longitude, body.altitude_relative_m)
    return CommandSpec(
        command_id=str(body.command_id),
        kind=CommandKind(request["kind"]),
        aircraft_ids=tuple(body.aircraft_ids),
        params=params,
        request_hash=request_hash,
        confirmation_token=body.confirmation_token,
        takeoff_altitude_m=body.altitude_relative_m if isinstance(body, TakeoffCommand) else None,
        goto=goto,
    )


@router.post(
    "",
    responses={
        428: {
            "model": ConfirmationProblem,
            "description": "Confirmation required: re-send the same request with the token.",
        }
    },
    **requires(Permission.AIRCRAFT_HOLD),
)
async def submit_command(
    body: Annotated[CommandRequest, Body()],
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> CommandView:
    """Send a command to one or more aircraft; the answer lists every aircraft's outcome."""
    return await context.runtime().commands.submit(
        db, principal, actor(request, principal), spec_of(body)
    )


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_commands(
    db: DbSession,
    context: Context,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CommandList:
    """The most recent commands."""
    rows = (
        await db.scalars(select(Command).order_by(Command.created_at.desc()).limit(limit))
    ).all()
    service = context.runtime().commands
    return CommandList(items=[await service.view(db, row) for row in rows])


@router.get("/{command_id}", **requires(Permission.FLEET_VIEW))
async def get_command(command_id: str, db: DbSession, context: Context) -> CommandView:
    """One command and its per-aircraft outcome."""
    row = await db.get(Command, command_id)
    if row is None:
        raise NotFound(f"Command {command_id} does not exist.")
    return await context.runtime().commands.view(db, row)
