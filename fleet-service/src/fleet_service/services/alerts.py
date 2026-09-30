"""
Operator alerts (ADR 0010, 0011).

Two kinds:

* **Condition alerts** mirror a state that can end (link stale/lost, battery low/critical,
  GNSS lost in flight, control orphaned). Evaluation raises them when the condition
  starts and clears them when it ends; acknowledging only says "seen".
* **Event alerts** report something that happened (a command timed out, an acked command
  never took effect). They stay until acknowledged, which clears them.

One open alert per dedupe key: a flapping condition does not spam operators, and every
raise, acknowledge and clear is audited like any other change.

M4 adds (ADR 0031):

* **Return energy**: the battery needed to fly home (distance / speed x the observed
  discharge rate, plus a reserve) against what is left: a warning at 1.2 x, critical at
  1 x. Without a known rate, position, home or battery there is no estimate, and no alert
  is made up; the battery thresholds still apply.
* **Geofence breach** (the incidents' enabled geofences), **one of two links lost**,
  **collision risk** (two aircraft predicted within ``proximity_m`` in the next
  ``lookahead_s``, from position and velocity), and **route deviation** (from the
  mission service, as an extra condition).
* **Escalation**: a warning nobody acknowledged for ``escalate_after_s`` becomes critical.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from shapely import Polygon
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import ALERTS, EventBus
from fleet_service.db.models import Alert, Geofence, Incident
from fleet_service.domain.enums import (
    Airframe,
    AlertKind,
    AlertSeverity,
    AlertState,
    IncidentStatus,
    LinkState,
)
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.domain.geofence import Fence, GeofenceSet
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.errors import Conflict, NotFound
from fleet_service.ids import new_id
from fleet_service.services import audit
from fleet_service.services.audit import Actor
from fleet_service.services.fleet import FleetRegistry
from fleet_service.services.views import AlertView

SYSTEM_ACTOR = Actor(user_id=None, username="system:alerts")
CONDITION_KINDS = frozenset(
    {
        AlertKind.LINK_STALE,
        AlertKind.LINK_LOST,
        AlertKind.BATTERY_LOW,
        AlertKind.BATTERY_CRITICAL,
        AlertKind.GPS_LOST,
        AlertKind.CONTROL_ORPHANED,
        AlertKind.ROUTE_DEVIATION,
        AlertKind.GEOFENCE_BREACH,
        AlertKind.RETURN_ENERGY,
        AlertKind.LINK_PARTIAL,
        AlertKind.DECONFLICTION_RISK,
    }
)
GEOFENCE_REFRESH = timedelta(seconds=5)
RATE_WINDOW_S = 5.0  # battery samples at least this far apart feed the discharge rate
RATE_KNOWN_AFTER_S = 30.0  # of observed flight before the rate is trusted


@dataclass
class _Drain:
    """An aircraft's observed battery discharge rate (percent per second, smoothed)."""

    ts: datetime
    pct: float
    rate: float | None = None
    observed_s: float = 0.0


@dataclass(frozen=True)
class AlertTuning:
    """The M4 alert settings (``Settings`` provides them)."""

    reserve_pct: float = 10.0
    escalate_after_s: float = 60.0
    proximity_m: float = 10.0
    proximity_vertical_m: float = 5.0
    lookahead_s: float = 30.0
    multirotor_speed_mps: float = 10.0
    fixed_wing_speed_mps: float = 18.0


@dataclass(frozen=True)
class Condition:
    """An alert that should be open."""

    kind: AlertKind
    severity: AlertSeverity
    aircraft_id: str
    message: str

    @property
    def key(self) -> str:
        """Dedupe key."""
        return f"{self.kind.value}:{self.aircraft_id}"


class AlertService:
    """Raises, clears and acknowledges alerts; keeps the open ones in memory."""

    def __init__(
        self,
        bus: EventBus,
        battery_low_pct: float,
        battery_critical_pct: float,
        tuning: AlertTuning | None = None,
    ) -> None:
        self._bus = bus
        self._battery_low = battery_low_pct
        self._battery_critical = battery_critical_pct
        self._tuning = tuning or AlertTuning()
        self._open: dict[str, Alert] = {}  # dedupe key -> active or acknowledged alert
        self._drain: dict[str, _Drain] = {}
        self._fences = GeofenceSet.of([])
        self._fences_at: datetime | None = None

    async def load(self, db: AsyncSession) -> None:
        """Pick up alerts left open before a restart."""
        rows = await db.scalars(select(Alert).where(Alert.state != AlertState.CLEARED))
        self._open = {alert.dedupe_key: alert for alert in rows.all()}

    def open_alerts(self) -> list[AlertView]:
        """Every active or acknowledged alert, oldest first."""
        return sorted(
            (AlertView.model_validate(a) for a in self._open.values()), key=lambda a: a.raised_at
        )

    def open_count(self, aircraft_id: str) -> int:
        """How many alerts are open for an aircraft."""
        return sum(1 for a in self._open.values() if a.aircraft_id == aircraft_id)

    async def raise_alert(
        self,
        db: AsyncSession,
        now: datetime,
        kind: AlertKind,
        severity: AlertSeverity,
        message: str,
        *,
        aircraft_id: str | None,
        dedupe_key: str,
    ) -> AlertView | None:
        """Open an alert unless one with the same key is already open."""
        if dedupe_key in self._open:
            return None
        alert = Alert(
            id=new_id(),
            kind=kind,
            severity=severity,
            state=AlertState.ACTIVE,
            aircraft_id=aircraft_id,
            dedupe_key=dedupe_key,
            message=message,
            raised_at=now,
            acknowledged_by=None,
            acknowledged_at=None,
            cleared_at=None,
            escalated_at=None,
        )
        db.add(alert)
        await db.flush()
        await audit.record(
            db,
            SYSTEM_ACTOR,
            now,
            "alert.raise",
            entity_type="alert",
            entity_id=alert.id,
            details={"kind": kind.value, "severity": severity.value, "message": message},
        )
        self._open[dedupe_key] = alert
        view = AlertView.model_validate(alert)
        self._bus.publish(ALERTS, view, key=alert.id)
        return view

    async def clear(self, db: AsyncSession, now: datetime, dedupe_key: str) -> None:
        """Close the open alert with this key (the condition ended)."""
        alert = self._open.pop(dedupe_key, None)
        if alert is None:
            return
        alert = await db.merge(alert)
        alert.state = AlertState.CLEARED
        alert.cleared_at = now
        await audit.record(
            db, SYSTEM_ACTOR, now, "alert.clear", entity_type="alert", entity_id=alert.id
        )
        self._bus.publish(ALERTS, AlertView.model_validate(alert), key=alert.id)

    async def acknowledge(
        self, db: AsyncSession, now: datetime, alert_id: str, actor: Actor
    ) -> AlertView:
        """An operator has seen the alert. Event alerts are then closed."""
        alert = await db.get(Alert, alert_id)
        if alert is None:
            raise NotFound(f"Alert {alert_id} does not exist.")
        if alert.state is not AlertState.ACTIVE:
            raise Conflict(f"The alert is already {alert.state.value}.", slug="alert-not-active")
        alert.acknowledged_by = actor.user_id
        alert.acknowledged_at = now
        if alert.kind in CONDITION_KINDS:
            alert.state = AlertState.ACKNOWLEDGED
            self._open[alert.dedupe_key] = alert
        else:
            alert.state = AlertState.CLEARED
            alert.cleared_at = now
            self._open.pop(alert.dedupe_key, None)
        await audit.record(
            db, actor, now, "alert.acknowledge", entity_type="alert", entity_id=alert.id
        )
        view = AlertView.model_validate(alert)
        self._bus.publish(ALERTS, view, key=alert.id)
        return view

    # --- evaluation ------------------------------------------------------------------------------

    def return_energy(self, record_airframe: Airframe, sample: TelemetrySample) -> float | None:
        """Battery percent needed to fly home now (with the reserve), or None if unknown."""
        drain = self._drain.get(sample.aircraft_id)
        if (
            drain is None
            or drain.rate is None
            or drain.observed_s < RATE_KNOWN_AFTER_S
            or sample.latitude is None
            or sample.longitude is None
            or sample.home_latitude is None
            or sample.home_longitude is None
        ):
            return None
        distance = distance_m(
            GeoPoint(latitude=sample.latitude, longitude=sample.longitude),
            GeoPoint(latitude=sample.home_latitude, longitude=sample.home_longitude),
        )
        cruise = (
            self._tuning.fixed_wing_speed_mps
            if record_airframe is Airframe.FIXED_WING
            else self._tuning.multirotor_speed_mps
        )
        speed = sample.groundspeed_mps if (sample.groundspeed_mps or 0.0) > 2.0 else cruise
        assert speed is not None  # noqa: S101 - cruise when the groundspeed is unknown
        return distance / speed * drain.rate + self._tuning.reserve_pct

    def _track_drain(self, sample: TelemetrySample) -> None:
        """Update an aircraft's discharge rate from a new sample (in flight only)."""
        if not sample.in_air or sample.battery_pct is None:
            self._drain.pop(sample.aircraft_id, None)
            return
        drain = self._drain.get(sample.aircraft_id)
        if drain is None:
            self._drain[sample.aircraft_id] = _Drain(sample.ts, sample.battery_pct)
            return
        dt = (sample.ts - drain.ts).total_seconds()
        if dt < RATE_WINDOW_S:
            return
        rate = max(0.0, (drain.pct - sample.battery_pct) / dt)
        drain.rate = rate if drain.rate is None else 0.8 * drain.rate + 0.2 * rate
        drain.observed_s += dt
        drain.ts, drain.pct = sample.ts, sample.battery_pct

    def conditions(
        self,
        registry: FleetRegistry,
        orphaned: list[str],
        extra: Sequence[Condition] = (),
    ) -> list[Condition]:
        """Every condition alert that should be open now."""
        found: list[Condition] = list(extra)
        for aircraft_id in registry.ids():
            record = registry.get(aircraft_id)
            if record is None:  # pragma: no cover - ids() and get() agree
                continue
            name = record.callsign
            if record.link is LinkState.STALE:
                found.append(
                    Condition(
                        AlertKind.LINK_STALE,
                        AlertSeverity.WARNING,
                        aircraft_id,
                        f"{name}: telemetry is stale.",
                    )
                )
            elif record.link is LinkState.LOST:
                found.append(
                    Condition(
                        AlertKind.LINK_LOST,
                        AlertSeverity.CRITICAL,
                        aircraft_id,
                        f"{name}: telemetry link lost; the aircraft follows its own "
                        "link-loss failsafe.",
                    )
                )
            sample = record.sample
            if sample is None or record.link is LinkState.LOST:
                continue
            battery = sample.battery_pct
            if battery is not None and battery < self._battery_critical:
                found.append(
                    Condition(
                        AlertKind.BATTERY_CRITICAL,
                        AlertSeverity.CRITICAL,
                        aircraft_id,
                        f"{name}: battery critical ({battery:.0f} %).",
                    )
                )
            elif battery is not None and battery < self._battery_low:
                found.append(
                    Condition(
                        AlertKind.BATTERY_LOW,
                        AlertSeverity.WARNING,
                        aircraft_id,
                        f"{name}: battery low ({battery:.0f} %).",
                    )
                )
            if sample.in_air and sample.gps_fix is not None and not sample.gps_fix.has_3d:
                found.append(
                    Condition(
                        AlertKind.GPS_LOST,
                        AlertSeverity.CRITICAL,
                        aircraft_id,
                        f"{name}: GNSS fix lost in flight; position unknown.",
                    )
                )
            self._track_drain(sample)
            needed = self.return_energy(record.airframe, sample) if sample.in_air else None
            if needed is not None and battery is not None and battery <= 1.2 * needed:
                critical = battery <= needed
                found.append(
                    Condition(
                        AlertKind.RETURN_ENERGY,
                        AlertSeverity.CRITICAL if critical else AlertSeverity.WARNING,
                        aircraft_id,
                        f"{name}: return now: about {needed:.0f} % needed to reach home, "
                        f"{battery:.0f} % left.",
                    )
                )
            if (
                sample.in_air
                and sample.latitude is not None
                and sample.longitude is not None
                and (
                    reason := self._fences.violation(
                        sample.latitude, sample.longitude, sample.altitude_relative_m
                    )
                )
            ):
                found.append(
                    Condition(
                        AlertKind.GEOFENCE_BREACH,
                        AlertSeverity.CRITICAL,
                        aircraft_id,
                        f"{name}: geofence breach: {reason}.",
                    )
                )
            if len(record.links) == 2 and record.link is LinkState.LIVE:
                down = [s.value for s, state in record.links.items() if state is not LinkState.LIVE]
                if down:
                    found.append(
                        Condition(
                            AlertKind.LINK_PARTIAL,
                            AlertSeverity.WARNING,
                            aircraft_id,
                            f"{name}: its {down[0]} link is lost; the other link is live.",
                        )
                    )
        found.extend(self._collision_risks(registry))
        for aircraft_id in orphaned:
            record = registry.get(aircraft_id)
            name = record.callsign if record else aircraft_id
            found.append(
                Condition(
                    AlertKind.CONTROL_ORPHANED,
                    AlertSeverity.WARNING,
                    aircraft_id,
                    f"{name}: its controlling operator is gone; a supervisor should reassign it.",
                )
            )
        return found

    def _collision_risks(self, registry: FleetRegistry) -> list[Condition]:
        """Aircraft in the air predicted within the proximity limits in the next seconds."""
        tuning = self._tuning
        flying = []
        for aircraft_id in registry.ids():
            record = registry.get(aircraft_id)
            s = record.sample if record else None
            if (
                record is None
                or s is None
                or not s.in_air
                or s.latitude is None
                or s.longitude is None
                or s.altitude_relative_m is None
            ):
                continue
            flying.append((aircraft_id, record.callsign, s))
        if len(flying) < 2:
            return []
        lat0 = sum(s.latitude or 0.0 for _, _, s in flying) / len(flying)
        scale = 111_320.0 * math.cos(math.radians(lat0))
        found: list[Condition] = []
        for (a, name_a, sa), (b, name_b, sb) in itertools.combinations(flying, 2):
            assert sa.latitude is not None  # noqa: S101 - filtered above
            assert sa.longitude is not None  # noqa: S101
            assert sb.latitude is not None  # noqa: S101
            assert sb.longitude is not None  # noqa: S101
            dx = (sb.longitude - sa.longitude) * scale
            dy = (sb.latitude - sa.latitude) * 111_320.0
            if math.hypot(dx, dy) > tuning.lookahead_s * 60.0 + tuning.proximity_m:
                continue  # too far apart to meet within the look-ahead
            va, vb = _velocity(sa), _velocity(sb)
            rvx, rvy = vb[0] - va[0], vb[1] - va[1]
            speed2 = rvx * rvx + rvy * rvy
            t = 0.0 if speed2 == 0.0 else -(dx * rvx + dy * rvy) / speed2
            t = min(max(t, 0.0), tuning.lookahead_s)
            closest = math.hypot(dx + rvx * t, dy + rvy * t)
            dz = abs((sb.altitude_relative_m or 0.0) - (sa.altitude_relative_m or 0.0))
            if closest < tuning.proximity_m and dz < tuning.proximity_vertical_m:
                when = "now" if t < 1.0 else f"in {t:.0f} s"
                for me, other in ((a, name_b), (b, name_a)):
                    found.append(
                        Condition(
                            AlertKind.DECONFLICTION_RISK,
                            AlertSeverity.CRITICAL,
                            me,
                            f"Collision risk with {other}: {closest:.0f} m apart {when}.",
                        )
                    )
        return found

    async def _refresh_fences(self, db: AsyncSession, now: datetime) -> None:
        if self._fences_at is not None and now - self._fences_at < GEOFENCE_REFRESH:
            return
        rows = await db.scalars(
            select(Geofence)
            .join(Incident, Incident.id == Geofence.incident_id)
            .where(Geofence.enabled.is_(True), Incident.status == IncidentStatus.ACTIVE)
        )
        self._fences = GeofenceSet.of(
            Fence(g.name, g.kind, Polygon(g.geometry["coordinates"][0]), g.max_altitude_relative_m)
            for g in rows.all()
        )
        self._fences_at = now

    async def _escalate(self, db: AsyncSession, now: datetime) -> None:
        """Warnings nobody acknowledged in time become critical (audited, published)."""
        limit = timedelta(seconds=self._tuning.escalate_after_s)
        for key, alert in list(self._open.items()):
            if (
                alert.state is not AlertState.ACTIVE
                or alert.severity is not AlertSeverity.WARNING
                or alert.escalated_at is not None
                or now - alert.raised_at < limit
            ):
                continue
            alert = await db.merge(alert)
            alert.severity, alert.escalated_at = AlertSeverity.CRITICAL, now
            self._open[key] = alert
            await audit.record(
                db, SYSTEM_ACTOR, now, "alert.escalate", entity_type="alert", entity_id=alert.id
            )
            self._bus.publish(ALERTS, AlertView.model_validate(alert), key=alert.id)

    async def evaluate(
        self,
        db: AsyncSession,
        now: datetime,
        registry: FleetRegistry,
        orphaned: list[str],
        extra: Sequence[Condition] = (),
    ) -> None:
        """Raise alerts for new conditions, clear those whose condition ended, escalate."""
        await self._refresh_fences(db, now)
        wanted = {c.key: c for c in self.conditions(registry, orphaned, extra)}
        for key, condition in wanted.items():
            if key not in self._open:
                await self.raise_alert(
                    db,
                    now,
                    condition.kind,
                    condition.severity,
                    condition.message,
                    aircraft_id=condition.aircraft_id,
                    dedupe_key=key,
                )
        for key, alert in list(self._open.items()):
            if alert.kind in CONDITION_KINDS and key not in wanted:
                await self.clear(db, now, key)
        await self._escalate(db, now)
        await db.commit()


def _velocity(s: TelemetrySample) -> tuple[float, float]:
    """East and north speed from heading and groundspeed (zero if either is unknown)."""
    if s.heading_deg is None or s.groundspeed_mps is None:
        return 0.0, 0.0
    rad = math.radians(s.heading_deg)
    return s.groundspeed_mps * math.sin(rad), s.groundspeed_mps * math.cos(rad)
