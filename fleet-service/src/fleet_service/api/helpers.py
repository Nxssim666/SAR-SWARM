"""Lookup and commit helpers shared by the resource routers."""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.db.models import Incident
from fleet_service.domain.enums import IncidentStatus
from fleet_service.domain.geo import GeoPoint, describe_outside, outside_operating_area
from fleet_service.errors import Conflict, InvalidRequest, NotFound


async def get_or_404[M](db: AsyncSession, model: type[M], entity_id: str, label: str) -> M:
    """Return the row with ``entity_id`` or raise 404."""
    row = await db.get(model, entity_id)
    if row is None:
        raise NotFound(f"{label} {entity_id} does not exist.")
    return row


async def get_reference[M](db: AsyncSession, model: type[M], entity_id: str, field: str) -> M:
    """Return the row a request body refers to, or raise 422 (the body is what is wrong)."""
    row = await db.get(model, entity_id)
    if row is None:
        raise InvalidRequest(
            f"{field} refers to {entity_id}, which does not exist.",
            slug="unknown-reference",
            extensions={"field": field},
        )
    return row


def ensure_incident_open(incident: Incident) -> None:
    """Closed incidents are read-only (their record is final)."""
    if incident.status is IncidentStatus.CLOSED:
        raise Conflict(
            f"Incident {incident.id} is closed; its data can no longer change.",
            slug="incident-closed",
        )


def incident_base(incident: Incident) -> GeoPoint:
    """The incident's base as a point."""
    return GeoPoint(latitude=incident.base_latitude, longitude=incident.base_longitude)


def ensure_inside_operating_area(incident: Incident, points: list[GeoPoint], what: str) -> None:
    """Raise 422 if any point lies outside the incident's operating area (ADR 0014)."""
    outside = outside_operating_area(points, incident_base(incident), incident.operating_radius_m)
    if outside:
        raise InvalidRequest(
            describe_outside(outside, what),
            slug="outside-operating-area",
            extensions={"outside_indices": outside},
        )


async def commit_or_conflict(db: AsyncSession, detail: str, **extensions: Any) -> None:
    """Commit; a uniqueness or reference race detected by the database becomes a 409."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(detail, extensions=extensions) from exc
