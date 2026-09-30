"""
Preflight reports (M6, ADR 0035): each aircraft's failsafe parameters, read over its link
and checked against the station's policy (``domain.preflight``).

Reading takes radio time, so a report is kept for ``max_age`` and reused (an arm followed
by a takeoff reads once). Reads of the same aircraft are shared. Nothing here holds a
database session: the command pipeline commits before it asks (ADR 0019).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from fleet_service.clock import Clock
from fleet_service.domain.preflight import (
    PREFLIGHT_PARAMETERS,
    Finding,
    PreflightPolicy,
    Severity,
    check,
)
from fleet_service.drivers.base import ParameterReader
from fleet_service.services.fleet import FleetRegistry


@dataclass(frozen=True)
class PreflightReport:
    """One aircraft's parameters as read at ``checked_at``, and what the policy found."""

    aircraft_id: str
    checked_at: datetime
    values: dict[str, float | None]
    findings: tuple[Finding, ...]

    @property
    def blocking(self) -> list[Finding]:
        """Findings that block arm and takeoff."""
        return [f for f in self.findings if f.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        """Findings shown in the confirmation only."""
        return [f for f in self.findings if f.severity is Severity.WARN]


class PreflightService:
    """Reads, checks and remembers each aircraft's failsafe configuration."""

    def __init__(
        self,
        registry: FleetRegistry,
        policy: PreflightPolicy,
        clock: Clock,
        *,
        timeout_s: float,
        max_age: timedelta,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._clock = clock
        self._timeout_s = timeout_s
        self._max_age = max_age
        self._reports: dict[str, PreflightReport] = {}
        self._reading: dict[str, asyncio.Task[PreflightReport]] = {}

    def last(self, aircraft_id: str) -> PreflightReport | None:
        """The newest report, however old."""
        return self._reports.get(aircraft_id)

    async def report(self, aircraft_id: str, *, fresh: bool = False) -> PreflightReport:
        """A report no older than ``max_age`` (``fresh``: read now)."""
        cached = self._reports.get(aircraft_id)
        if (
            not fresh
            and cached is not None
            and self._clock.now() - cached.checked_at <= self._max_age
        ):
            return cached
        task = self._reading.get(aircraft_id)
        if task is None:
            task = asyncio.create_task(self._read(aircraft_id), name=f"preflight-{aircraft_id}")
            self._reading[aircraft_id] = task
            task.add_done_callback(lambda _: self._reading.pop(aircraft_id, None))
        return await asyncio.shield(task)

    async def reports(
        self, aircraft_ids: list[str], *, fresh: bool = False
    ) -> dict[str, PreflightReport]:
        """Reports for several aircraft, read concurrently."""
        results = await asyncio.gather(*(self.report(a, fresh=fresh) for a in aircraft_ids))
        return dict(zip(aircraft_ids, results, strict=True))

    def forget(self, aircraft_id: str) -> None:
        """Drop an aircraft's report (unregistered, or its link changed)."""
        self._reports.pop(aircraft_id, None)

    async def _read(self, aircraft_id: str) -> PreflightReport:
        record = self._registry.get(aircraft_id)
        driver = record.driver if record is not None else None
        values: dict[str, float | None] = {}
        if isinstance(driver, ParameterReader):
            try:
                values = await asyncio.wait_for(
                    driver.read_parameters(PREFLIGHT_PARAMETERS), self._timeout_s
                )
            except TimeoutError:
                values = {}
        values = {name: values.get(name) for name in PREFLIGHT_PARAMETERS}
        report = PreflightReport(
            aircraft_id=aircraft_id,
            checked_at=self._clock.now(),
            values=values,
            findings=tuple(check(values, self._policy)),
        )
        self._reports[aircraft_id] = report
        return report
