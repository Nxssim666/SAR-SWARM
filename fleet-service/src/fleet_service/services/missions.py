"""
Mission execution progress (ADR 0028): per-aircraft progress, area coverage, completion,
and route deviation. Tick-driven (``Runtime.evaluate``), with the tick's short session.

- **Progress** is what each autopilot reports: the item flown and the item count (PX4
  reports the count once the last item is done). A task whose aircraft reports that is
  completed; a mission whose tasks are all completed (or failed or cancelled) is
  completed, its search area marked searched, and a mission-complete alert raised.
- **Coverage** is the track each aircraft flew in mission mode, widened by its sweep width
  (the lane spacing), united, clipped to the search area, as a share of it. It is what
  was flown over, not a probability of detection.
- **Route deviation**: an aircraft in mission mode farther than ``DEVIATION_M`` (or its
  sweep width, if larger) from the leg it is flying, for ``DEVIATION_S``, is reported as a
  condition alert (cleared when it is back).

Progress is published on the ``missions`` topic at most once a second per mission.
GCS-planned missions only: a swarm reports its own phases (ADR 0003).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from shapely import LineString, Point, Polygon, unary_union
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import MISSIONS, EventBus
from fleet_service.db.models import Mission, SearchArea, Task
from fleet_service.domain.enums import (
    AlertKind,
    AlertSeverity,
    FlightMode,
    MissionKind,
    MissionStatus,
    SearchAreaStatus,
    TaskStatus,
)
from fleet_service.domain.patterns import LocalFrame
from fleet_service.services import audit
from fleet_service.services.alerts import AlertService, Condition
from fleet_service.services.audit import Actor
from fleet_service.services.fleet import FleetRegistry
from fleet_service.services.views import MissionProgressView, TaskProgressView

SYSTEM_ACTOR = Actor(user_id=None, username="system:missions")
PUBLISH_EVERY = timedelta(seconds=1)
DEVIATION_M = 25.0
DEVIATION_S = 5.0
RUNNING = (MissionStatus.ACTIVE, MissionStatus.PAUSED)
FINISHED_TASKS = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


@dataclass
class _Track:
    """One aircraft's part of a running mission."""

    task_id: str
    aircraft_id: str
    route: list[tuple[float, float]]  # metric, as uploaded: the start hold first
    sweep_m: float
    last: tuple[float, float] | None = None
    off_route_since: datetime | None = None
    status: TaskStatus = TaskStatus.ACTIVE


@dataclass
class _Running:
    """A running mission's cached geometry and coverage."""

    mission_id: str
    frame: LocalFrame
    area: Polygon | None
    tracks: dict[str, _Track]  # aircraft id -> its track
    swept: list[BaseGeometry] = field(default_factory=list)
    covered: BaseGeometry | None = None
    published_at: datetime | None = None
    dirty: bool = True
    status: MissionStatus | None = None


class MissionService:
    """Follows running GCS missions: progress, coverage, completion, route deviation."""

    def __init__(self, bus: EventBus, alerts: AlertService, registry: FleetRegistry) -> None:
        self._bus = bus
        self._alerts = alerts
        self._registry = registry
        self._running: dict[str, _Running] = {}
        self._deviations: list[Condition] = []

    # --- queries --------------------------------------------------------------------------------

    def deviations(self) -> list[Condition]:
        """Route-deviation conditions found by the last evaluation."""
        return list(self._deviations)

    def coverage_geometry(self, mission: Mission) -> dict[str, Any] | None:
        """The swept area as GeoJSON (WGS84): live while running, saved once finished."""
        running = self._running.get(mission.id)
        if running is None:
            result = (mission.plan or {}).get("result") or {}
            geometry: dict[str, Any] | None = result.get("coverage_geometry")
            return geometry
        if running.covered is None or running.covered.is_empty:
            return None
        return _geojson(running.covered, running.frame)

    async def progress(self, db: AsyncSession, mission: Mission) -> MissionProgressView:
        """A mission's progress as the API shows it."""
        tasks = (await db.scalars(select(Task).where(Task.mission_id == mission.id))).all()
        running = self._running.get(mission.id)
        saved = (mission.plan or {}).get("result") or {}
        return MissionProgressView(
            mission_id=mission.id,
            incident_id=mission.incident_id,
            name=mission.name,
            kind=mission.kind,
            status=mission.status,
            coverage=self._coverage(running) if running else saved.get("coverage"),
            tasks=[self._task_view(t) for t in tasks if t.status is not TaskStatus.CANCELLED],
            updated_at=mission.updated_at,
        )

    async def snapshot(self, db: AsyncSession) -> list[MissionProgressView]:
        """Every running or planned GCS mission's progress (the WebSocket snapshot)."""
        rows = await db.scalars(
            select(Mission).where(
                Mission.status.in_((*RUNNING, MissionStatus.PLANNED)),
                Mission.kind != MissionKind.SWARM_AREA,
            )
        )
        return [await self.progress(db, m) for m in rows.all()]

    # --- evaluation (tick) ------------------------------------------------------------------------

    async def evaluate(self, db: AsyncSession, now: datetime) -> None:
        """Advance every running mission from the latest telemetry."""
        registry = self._registry
        missions = (
            await db.scalars(
                select(Mission).where(
                    Mission.status.in_(RUNNING), Mission.kind != MissionKind.SWARM_AREA
                )
            )
        ).all()
        for gone in set(self._running) - {m.id for m in missions}:
            del self._running[gone]
        deviations: list[Condition] = []
        changed = False
        for mission in missions:
            running = self._running.get(mission.id)
            if running is None:
                running = await self._load(db, mission)
                self._running[mission.id] = running
            if running.status is not mission.status:  # started, paused or resumed
                running.status, running.dirty = mission.status, True
            for track in running.tracks.values():
                if track.status is not TaskStatus.ACTIVE:
                    continue
                record = registry.get(track.aircraft_id)
                sample = record.sample if record else None
                if sample is None or sample.latitude is None or sample.longitude is None:
                    continue
                here = running.frame.xy(sample.longitude, sample.latitude)
                in_mission = sample.flight_mode is FlightMode.MISSION
                if in_mission and track.last is not None and track.last != here:
                    running.swept.append(LineString([track.last, here]).buffer(track.sweep_m / 2))
                    running.dirty = True
                track.last = here if in_mission else None
                deviation = self._deviation(track, sample.mission_item, here, in_mission, now)
                if deviation is not None and record is not None:
                    deviations.append(
                        Condition(
                            AlertKind.ROUTE_DEVIATION,
                            AlertSeverity.WARNING,
                            track.aircraft_id,
                            f"{record.callsign}: {deviation:.0f} m off its planned route.",
                        )
                    )
                done = (
                    sample.mission_items is not None
                    and sample.mission_item is not None
                    and sample.mission_item >= sample.mission_items
                )
                if done:
                    await self._complete_task(db, now, track)
                    running.dirty = changed = True
            if running.swept:  # fold the new track pieces in once per tick
                pieces = [running.covered] if running.covered is not None else []
                running.covered = unary_union([*pieces, *running.swept])
                running.swept.clear()
            if all(t.status in FINISHED_TASKS for t in running.tracks.values()):
                await self._complete_mission(db, now, mission, running)
                changed = True
            if running.dirty and (
                running.published_at is None or now - running.published_at >= PUBLISH_EVERY
            ):
                self._bus.publish(MISSIONS, await self.progress(db, mission), key=mission.id)
                running.published_at, running.dirty = now, False
        self._deviations = deviations
        if changed:
            await db.commit()

    def publish(self, view: MissionProgressView) -> None:
        """Announce a mission change made elsewhere (planned, started, paused)."""
        self._bus.publish(MISSIONS, view, key=view.mission_id)

    # --- helpers --------------------------------------------------------------------------------

    async def _load(self, db: AsyncSession, mission: Mission) -> _Running:
        area = await db.get(SearchArea, mission.search_area_id) if mission.search_area_id else None
        tasks = (
            await db.scalars(
                select(Task).where(
                    Task.mission_id == mission.id, Task.status != TaskStatus.CANCELLED
                )
            )
        ).all()
        anchor = (
            area.geometry["coordinates"][0][0]
            if area is not None
            else next(
                ([t.route[0]["longitude"], t.route[0]["latitude"]] for t in tasks if t.route),
                [0.0, 0.0],
            )
        )
        frame = LocalFrame(anchor[1], anchor[0])
        polygon = frame.polygon(area.geometry["coordinates"][0]) if area is not None else None
        tracks = {}
        for task in tasks:
            points = [frame.xy(w["longitude"], w["latitude"]) for w in task.route or []]
            sweep = float((task.plan or {}).get("sweep_width_m") or 0.0) or float(
                (mission.plan or {}).get("spacing_m") or 50.0
            )
            tracks[task.aircraft_id] = _Track(
                task_id=task.id,
                aircraft_id=task.aircraft_id,
                route=points,
                sweep_m=sweep,
                status=task.status,
            )
        return _Running(mission.id, frame, polygon, tracks)

    def _deviation(
        self,
        track: _Track,
        item: int | None,
        here: tuple[float, float],
        in_mission: bool,
        now: datetime,
    ) -> float | None:
        """Metres off the leg being flown, once it has lasted ``DEVIATION_S``; else None."""
        if not in_mission or item is None or item == 0 or not track.route:
            track.off_route_since = None  # item 0: climbing or waiting where it started
            return None
        # The uploaded route starts with a hold where the aircraft was: item 0. The planned
        # waypoint i is item i + 1; the leg flown to item k starts at item k - 1.
        target = min(max(item - 1, 0), len(track.route) - 1)
        previous = max(target - 1, 0)
        leg = (
            LineString([track.route[previous], track.route[target]])
            if previous != target
            else Point(track.route[target])
        )
        off = float(leg.distance(Point(here)))
        if off <= max(DEVIATION_M, track.sweep_m):
            track.off_route_since = None
            return None
        if track.off_route_since is None:
            track.off_route_since = now
        if now - track.off_route_since < timedelta(seconds=DEVIATION_S):
            return None
        return off

    async def _complete_task(self, db: AsyncSession, now: datetime, track: _Track) -> None:
        task = await db.get(Task, track.task_id)
        track.status = TaskStatus.COMPLETED
        if task is None or task.status is not TaskStatus.ACTIVE:
            return
        task.status, task.updated_at = TaskStatus.COMPLETED, now
        await audit.record(
            db, SYSTEM_ACTOR, now, "task.complete", entity_type="task", entity_id=task.id
        )

    async def _complete_mission(
        self, db: AsyncSession, now: datetime, mission: Mission, running: _Running
    ) -> None:
        coverage = self._coverage(running)
        geometry = (
            _geojson(running.covered, running.frame)
            if running.covered is not None and not running.covered.is_empty
            else None
        )
        # Kept with the mission: the result outlives the in-memory tracking.
        mission.plan = {
            **(mission.plan or {}),
            "result": {"coverage": coverage, "coverage_geometry": geometry},
        }
        mission.status, mission.updated_at = MissionStatus.COMPLETED, now
        if mission.search_area_id is not None:
            area = await db.get(SearchArea, mission.search_area_id)
            if area is not None:
                area.status, area.updated_at = SearchAreaStatus.SEARCHED, now
        await audit.record(
            db,
            SYSTEM_ACTOR,
            now,
            "mission.complete",
            entity_type="mission",
            entity_id=mission.id,
            details={"coverage": coverage},
        )
        covered = f": {coverage:.0%} of the area swept" if coverage is not None else ""
        await self._alerts.raise_alert(
            db,
            now,
            AlertKind.MISSION_COMPLETE,
            AlertSeverity.INFO,
            f"Mission {mission.name} complete{covered}.",
            aircraft_id=None,
            dedupe_key=f"mission_complete:{mission.id}",
        )
        self._bus.publish(MISSIONS, await self.progress(db, mission), key=mission.id)
        running.published_at, running.dirty = now, False

    @staticmethod
    def _coverage(running: _Running) -> float | None:
        if running.area is None or running.area.area <= 0.0:
            return None
        if running.covered is None:
            return 0.0
        return round(float(running.covered.intersection(running.area).area / running.area.area), 4)

    def _task_view(self, task: Task) -> TaskProgressView:
        live = self._registry.get(task.aircraft_id)
        sample = live.sample if live is not None else None
        running = task.status is TaskStatus.ACTIVE and sample is not None
        return TaskProgressView(
            task_id=task.id,
            aircraft_id=task.aircraft_id,
            callsign=live.callsign if live is not None else task.aircraft_id,
            status=task.status,
            item=sample.mission_item if running and sample is not None else None,
            items=sample.mission_items if running and sample is not None else None,
        )


def _geojson(geometry: BaseGeometry, frame: LocalFrame) -> dict[str, Any]:
    """A metric (Multi)Polygon as a GeoJSON MultiPolygon in WGS84."""
    parts = [geometry] if isinstance(geometry, Polygon) else list(getattr(geometry, "geoms", ()))
    polygons = []
    for part in parts:
        if not isinstance(part, Polygon) or part.is_empty:
            continue
        rings = [part.exterior, *part.interiors]
        polygons.append([[list(frame.lonlat(x, y)) for x, y in ring.coords] for ring in rings])
    return {"type": "MultiPolygon", "coordinates": polygons}
