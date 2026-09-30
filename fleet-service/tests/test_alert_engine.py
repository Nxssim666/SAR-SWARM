"""
The M4 alert rules (ADR 0031): return energy, the second link, collision risk, geofence
breach and escalation. The pure rules run on hand-made telemetry; escalation and the
geofence in simulation.
"""

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.bus import EventBus
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.domain.enums import (
    Airframe,
    AlertKind,
    AlertSeverity,
    FlightMode,
    GpsFix,
    LinkSource,
    LinkState,
    Role,
)
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.services.alerts import AlertService, AlertTuning
from fleet_service.services.fleet import FleetRegistry, LiveRecord
from live_support import Sim, confirmed, register, take

from factories import BASE, create, incident, square
from support import FakeClock

T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
HOME = (47.3977, 8.5456)


def sample(aircraft_id: str = "a", **fields: object) -> TelemetrySample:
    base: dict[str, object] = {
        "aircraft_id": aircraft_id,
        "ts": T0,
        "source": "mock",
        "latitude": HOME[0],
        "longitude": HOME[1],
        "altitude_amsl_m": 530.0,
        "altitude_relative_m": 30.0,
        "heading_deg": 0.0,
        "groundspeed_mps": 0.0,
        "climb_rate_mps": 0.0,
        "battery_pct": 80.0,
        "battery_v": 24.0,
        "gps_fix": GpsFix.FIX_3D,
        "satellites": 14,
        "flight_mode": FlightMode.HOLD,
        "armed": True,
        "in_air": True,
        "home_latitude": HOME[0],
        "home_longitude": HOME[1],
    }
    return TelemetrySample(**(base | fields))  # type: ignore[arg-type]


def registry_with(*records: LiveRecord) -> FleetRegistry:
    registry = FleetRegistry(
        EventBus(), timedelta(seconds=3), timedelta(seconds=15), lambda _: None
    )
    for record in records:
        registry.add(record)
    return registry


def record(s: TelemetrySample, **fields: object) -> LiveRecord:
    live = LiveRecord(s.aircraft_id, s.aircraft_id.upper(), Airframe.MULTIROTOR_HEXA)
    live.sample, live.link = s, LinkState.LIVE
    for name, value in fields.items():
        setattr(live, name, value)
    return live


# --- return energy -------------------------------------------------------------------------------


def drained(
    service: AlertService, s: TelemetrySample, seconds: int, rate: float
) -> TelemetrySample:
    """Feed ``seconds`` of flight at ``rate`` %/s; return the last sample."""
    current = s
    for k in range(0, seconds + 1, 5):
        current = dataclasses.replace(
            s,
            ts=T0 + timedelta(seconds=k),
            battery_pct=s.battery_pct - rate * k,  # type: ignore[operator]
        )
        service._track_drain(current)
    return current


def test_return_energy_is_distance_over_speed_times_the_observed_drain_plus_reserve() -> None:
    service = AlertService(EventBus(), 30.0, 15.0, AlertTuning(reserve_pct=10.0))
    # 2 km north of home, 10 m/s: 200 s home; draining 0.1 %/s -> 20 % + 10 % reserve.
    far = sample(latitude=HOME[0] + 2000 / 111_320, groundspeed_mps=10.0)

    last = drained(service, far, 60, 0.1)

    assert service.return_energy(Airframe.MULTIROTOR_HEXA, last) == pytest.approx(30.0, abs=0.3)


@pytest.mark.parametrize(
    ("change", "seconds"),
    [
        ({}, 20),  # observed for too short a time: the rate is not trusted yet
        ({"home_latitude": None, "home_longitude": None}, 60),  # home unknown
        ({"latitude": None, "longitude": None}, 60),  # position unknown
    ],
)
def test_without_its_inputs_there_is_no_return_estimate(
    change: dict[str, object], seconds: int
) -> None:
    service = AlertService(EventBus(), 30.0, 15.0)
    last = drained(service, sample("a", **change), seconds, 0.1)

    assert service.return_energy(Airframe.MULTIROTOR_HEXA, last) is None


@pytest.mark.parametrize(
    ("battery", "severity"),
    [(40.0, None), (35.0, AlertSeverity.WARNING), (29.0, AlertSeverity.CRITICAL)],
)
def test_return_now_warns_at_one_point_two_times_the_need_and_is_critical_below_it(
    battery: float, severity: AlertSeverity | None
) -> None:
    service = AlertService(EventBus(), 20.0, 10.0, AlertTuning(reserve_pct=10.0))
    far = sample(latitude=HOME[0] + 2000 / 111_320, groundspeed_mps=10.0, battery_pct=battery + 6)
    last = drained(service, far, 60, 0.1)  # ends at ``battery``, needing 30 %

    found = [
        c
        for c in service.conditions(registry_with(record(last)), [])
        if c.kind is AlertKind.RETURN_ENERGY
    ]

    assert [c.severity for c in found] == ([severity] if severity else [])
    if found:
        assert "return now" in found[0].message


# --- two links -----------------------------------------------------------------------------------


def test_losing_one_of_two_links_is_a_warning_while_the_other_is_live() -> None:
    service = AlertService(EventBus(), 30.0, 15.0)
    s = sample()
    both = record(s, links={LinkSource.MAVLINK: LinkState.LIVE, LinkSource.SWARM: LinkState.LIVE})
    one = record(
        dataclasses.replace(s, aircraft_id="b"),
        links={LinkSource.MAVLINK: LinkState.LIVE, LinkSource.SWARM: LinkState.LOST},
    )

    found = service.conditions(registry_with(both, one), [])

    partial = [c for c in found if c.kind is AlertKind.LINK_PARTIAL]
    assert [c.aircraft_id for c in partial] == ["b"]
    assert "swarm link is lost" in partial[0].message


# --- collision risk ------------------------------------------------------------------------------


def east(metres: float) -> float:
    return HOME[1] + metres / (111_320 * 0.6772)  # cos(47.4°)


@pytest.mark.parametrize(
    ("a", "b", "risk"),
    [
        # Head-on along the same line, 200 m apart at 10 m/s each: meet in 10 s.
        ({"heading_deg": 90.0, "groundspeed_mps": 10.0},
         {"longitude": east(200), "heading_deg": 270.0, "groundspeed_mps": 10.0}, True),
        # Flying apart.
        ({"heading_deg": 270.0, "groundspeed_mps": 10.0},
         {"longitude": east(200), "heading_deg": 90.0, "groundspeed_mps": 10.0}, False),
        # Hovering 15 m apart, at a launch site: close, but not closing.
        ({}, {"longitude": east(15)}, False),
        # Head-on, but 20 m apart vertically.
        ({"heading_deg": 90.0, "groundspeed_mps": 10.0},
         {"longitude": east(200), "heading_deg": 270.0, "groundspeed_mps": 10.0,
          "altitude_relative_m": 50.0}, False),
    ],
)  # fmt: skip
def test_collision_risk_from_position_and_velocity(
    a: dict[str, object], b: dict[str, object], risk: bool
) -> None:
    service = AlertService(EventBus(), 30.0, 15.0)
    first, second = record(sample("a", **a)), record(sample("b", **b))

    found = [
        c
        for c in service.conditions(registry_with(first, second), [])
        if c.kind is AlertKind.DECONFLICTION_RISK
    ]

    assert sorted(c.aircraft_id for c in found) == (["a", "b"] if risk else [])
    if risk:
        assert all(c.severity is AlertSeverity.CRITICAL for c in found)


# --- in simulation: escalation and geofence breach -----------------------------------------------


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


async def active_alerts(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> dict[str, dict[str, object]]:
    response = await client.get("/api/v1/alerts", params={"state": "active"}, headers=headers)
    return {a["kind"]: a for a in response.json()["items"]}


async def test_a_warning_nobody_acknowledges_becomes_critical(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    hexa = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await sim.fly(1)
    assert sim.runtime.simulator is not None
    sim.runtime.simulator.drivers[hexa].inject(battery_pct=25.0)

    await sim.fly(30)
    early = (await active_alerts(client, auth[Role.OBSERVER]))["battery_low"]
    await sim.fly(31)
    late = (await active_alerts(client, auth[Role.OBSERVER]))["battery_low"]

    assert early["severity"] == "warning"
    assert early["escalated_at"] is None
    assert late["severity"] == "critical"
    assert late["escalated_at"] is not None


async def test_flying_into_an_exclusion_zone_raises_a_geofence_breach(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    hexa = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await take(client, auth[Role.OPERATOR], hexa)
    await sim.fly(1)
    await confirmed(client, auth[Role.OPERATOR], "arm", [hexa])
    await sim.fly(0.5)
    await confirmed(client, auth[Role.OPERATOR], "takeoff", [hexa], altitude_relative_m=30.0)
    await sim.fly(15)
    inc = await incident(client, auth[Role.SUPERVISOR])
    # An exclusion zone appears over where the aircraft is (a new hazard, say).
    await create(
        client,
        "geofences",
        auth[Role.SUPERVISOR],
        {
            "incident_id": inc["id"],
            "name": "Crane",
            "kind": "exclusion",
            "geometry": square(BASE["latitude"], BASE["longitude"], 0.001),
        },
    )

    await sim.fly(6)  # geofences are re-read every 5 s

    alerts = await active_alerts(client, auth[Role.OBSERVER])
    assert alerts["geofence_breach"]["severity"] == "critical"
    assert "Crane" in str(alerts["geofence_breach"]["message"])
