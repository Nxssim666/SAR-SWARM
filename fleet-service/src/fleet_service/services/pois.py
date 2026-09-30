"""
Points of interest and survivor sightings (M4).

Operators mark points of interest through the API. Swarm drones report survivor
sightings (the onboard "target" estimate, ADR 0003) in their telemetry; each new sighting
becomes a point of interest of the incident the aircraft is working for, and raises a
critical alert once. Repeated reports of the same sighting (the same aircraft, within
``SAME_SIGHTING_M`` of the last one, or within ``SAME_SIGHTING_S``) update that point
instead of adding new ones, so a drone circling a person does not flood the map.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import POIS, EventBus
from fleet_service.db.models import Incident, Mission, Poi, Task
from fleet_service.domain.enums import (
    AlertKind,
    AlertSeverity,
    IncidentStatus,
    PoiKind,
    PoiStatus,
    TaskStatus,
)
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.ids import new_id
from fleet_service.services import audit
from fleet_service.services.alerts import AlertService
from fleet_service.services.audit import Actor
from fleet_service.services.fleet import FleetRegistry
from fleet_service.services.views import PoiView

SYSTEM_ACTOR = Actor(user_id=None, username="system:sightings")
SAME_SIGHTING_M = 25.0
SAME_SIGHTING_S = 60.0


@dataclass
class _Last:
    poi_id: str
    latitude: float
    longitude: float
    stamp: datetime


class PoiService:
    """Publishes point-of-interest changes and turns sightings into points of interest."""

    def __init__(self, bus: EventBus, alerts: AlertService) -> None:
        self._bus = bus
        self._alerts = alerts
        self._last: dict[str, _Last] = {}  # aircraft id -> its latest sighting's POI

    def publish(self, poi: Poi) -> PoiView:
        """Announce a created or changed point of interest."""
        view = PoiView.model_validate(poi)
        self._bus.publish(POIS, view, key=poi.id)
        return view

    async def evaluate(self, db: AsyncSession, now: datetime, registry: FleetRegistry) -> None:
        """Record new survivor sightings from the aircraft's telemetry."""
        changed = False
        for aircraft_id in registry.ids():
            record = registry.get(aircraft_id)
            sample = record.sample if record is not None else None
            sighting = sample.swarm.survivor_sighting if sample and sample.swarm else None
            if record is None or sighting is None:
                continue
            last = self._last.get(aircraft_id)
            if last is not None and sighting.stamp <= last.stamp:
                continue  # already recorded
            here = GeoPoint(latitude=sighting.latitude, longitude=sighting.longitude)
            same = last is not None and (
                distance_m(here, GeoPoint(latitude=last.latitude, longitude=last.longitude))
                <= SAME_SIGHTING_M
                or sighting.stamp - last.stamp <= timedelta(seconds=SAME_SIGHTING_S)
            )
            if same and last is not None:
                poi = await db.get(Poi, last.poi_id)
                if poi is not None:
                    poi.latitude, poi.longitude = sighting.latitude, sighting.longitude
                    poi.uncertainty_m = sighting.std_m
                    poi.reported_at = sighting.stamp
                    poi.updated_at = now
                    self._last[aircraft_id] = _Last(
                        poi.id, sighting.latitude, sighting.longitude, sighting.stamp
                    )
                    self.publish(poi)
                    changed = True
                    continue
            incident_id = await self._incident_of(db, aircraft_id)
            where = (
                f"{sighting.latitude:.5f} N, {sighting.longitude:.5f} E (±{sighting.std_m:.0f} m)"
            )
            if incident_id is None:
                await self._alerts.raise_alert(
                    db,
                    now,
                    AlertKind.SURVIVOR_SIGHTING,
                    AlertSeverity.CRITICAL,
                    f"{record.callsign} reports a possible survivor at {where}; no active "
                    "incident to record it in.",
                    aircraft_id=aircraft_id,
                    dedupe_key=f"survivor_sighting:{aircraft_id}:{sighting.stamp.isoformat()}",
                )
                self._last[aircraft_id] = _Last(
                    "", sighting.latitude, sighting.longitude, sighting.stamp
                )
                changed = True
                continue
            poi = Poi(
                id=new_id(),
                incident_id=incident_id,
                kind=PoiKind.SURVIVOR_SIGHTING,
                status=PoiStatus.NEW,
                latitude=sighting.latitude,
                longitude=sighting.longitude,
                uncertainty_m=sighting.std_m,
                aircraft_id=aircraft_id,
                reported_at=sighting.stamp,
                notes=None,
                created_by=None,
                created_at=now,
                updated_at=now,
            )
            db.add(poi)
            await db.flush()
            await audit.record(
                db,
                SYSTEM_ACTOR,
                now,
                "poi.sighting",
                entity_type="poi",
                entity_id=poi.id,
                details={"aircraft_id": aircraft_id, "position": [poi.latitude, poi.longitude]},
            )
            await self._alerts.raise_alert(
                db,
                now,
                AlertKind.SURVIVOR_SIGHTING,
                AlertSeverity.CRITICAL,
                f"{record.callsign} reports a possible survivor at {where}.",
                aircraft_id=aircraft_id,
                dedupe_key=f"survivor_sighting:{poi.id}",
            )
            self._last[aircraft_id] = _Last(poi.id, poi.latitude, poi.longitude, sighting.stamp)
            self.publish(poi)
            changed = True
        if changed:
            await db.commit()

    @staticmethod
    async def _incident_of(db: AsyncSession, aircraft_id: str) -> str | None:
        """The incident of the aircraft's active task, else the only active incident."""
        tasked = await db.scalar(
            select(Mission.incident_id)
            .join(Task, Task.mission_id == Mission.id)
            .where(Task.aircraft_id == aircraft_id, Task.status == TaskStatus.ACTIVE)
            .limit(1)
        )
        if tasked is not None:
            return str(tasked)
        active = (
            await db.scalars(select(Incident.id).where(Incident.status == IncidentStatus.ACTIVE))
        ).all()
        return str(active[0]) if len(active) == 1 else None
