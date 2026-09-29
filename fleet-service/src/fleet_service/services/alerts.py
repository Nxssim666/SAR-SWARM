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
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import ALERTS, EventBus
from fleet_service.db.models import Alert
from fleet_service.domain.enums import AlertKind, AlertSeverity, AlertState, LinkState
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
    }
)


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

    def __init__(self, bus: EventBus, battery_low_pct: float, battery_critical_pct: float) -> None:
        self._bus = bus
        self._battery_low = battery_low_pct
        self._battery_critical = battery_critical_pct
        self._open: dict[str, Alert] = {}  # dedupe key -> active or acknowledged alert

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

    def conditions(self, registry: FleetRegistry, orphaned: list[str]) -> list[Condition]:
        """Every condition alert that should be open now."""
        found: list[Condition] = []
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

    async def evaluate(
        self, db: AsyncSession, now: datetime, registry: FleetRegistry, orphaned: list[str]
    ) -> None:
        """Raise alerts for new conditions and clear those whose condition ended."""
        wanted = {c.key: c for c in self.conditions(registry, orphaned)}
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
        await db.commit()
