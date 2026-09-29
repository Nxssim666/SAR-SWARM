"""An aircraft with a MAVLink and a swarm link (ADR 0025): merged telemetry, routed commands."""

from dataclasses import replace
from datetime import timedelta
from typing import cast

from fleet_service.domain.commands import AUTOPILOT_COMMANDS, SWARM_COMMANDS
from fleet_service.domain.enums import CommandKind, FlightMode, GpsFix, LinkSource
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import CommandResult, DriverCommand, TelemetrySink
from fleet_service.drivers.swarm import LinkedDriver, SwarmDriver
from test_swarm_rules import AUTOPILOT, SWARM_ONLY

from support import START, FakeClock

FRESH = timedelta(seconds=3)


class FakeDriver:
    """Records what it is asked to do; delivers samples when told to."""

    def __init__(self, source: str, capabilities: frozenset[CommandKind]) -> None:
        self.source = source
        self.capabilities = capabilities
        self.sink: TelemetrySink | None = None
        self.executed: list[CommandKind] = []

    def start(self, sink: TelemetrySink) -> None:
        self.sink = sink

    def stop(self) -> None:
        self.sink = None

    def deliver(self, sample: TelemetrySample) -> None:
        assert self.sink is not None
        self.sink(sample)

    async def execute(self, command: DriverCommand) -> CommandResult:
        self.executed.append(command.kind)
        return CommandResult.ack()


def linked(clock: FakeClock) -> tuple[LinkedDriver, FakeDriver, FakeDriver, list[TelemetrySample]]:
    mavlink = FakeDriver("mavlink", AUTOPILOT_COMMANDS)
    swarm = FakeDriver("swarm", SWARM_COMMANDS)
    driver = LinkedDriver(mavlink, cast(SwarmDriver, swarm), clock, FRESH)
    received: list[TelemetrySample] = []
    driver.start(received.append)
    return driver, mavlink, swarm, received


def at(sample: TelemetrySample, clock: FakeClock) -> TelemetrySample:
    return replace(sample, ts=clock.now())


async def test_safe_commands_go_to_the_companion_while_it_is_heard() -> None:
    clock = FakeClock(START)
    driver, mavlink, swarm, _ = linked(clock)
    mavlink.deliver(at(AUTOPILOT, clock))
    swarm.deliver(at(SWARM_ONLY, clock))

    for kind in (CommandKind.HOLD, CommandKind.RESUME, CommandKind.LAND, CommandKind.ARM):
        await driver.execute(DriverCommand(kind))

    assert swarm.executed == [CommandKind.HOLD, CommandKind.RESUME, CommandKind.LAND]
    assert mavlink.executed == [CommandKind.ARM]


async def test_without_the_companion_hold_goes_to_the_autopilot_and_resume_cannot() -> None:
    clock = FakeClock(START)
    driver, mavlink, swarm, _ = linked(clock)
    swarm.deliver(at(SWARM_ONLY, clock))
    clock.advance(seconds=10)
    mavlink.deliver(at(AUTOPILOT, clock))

    hold = await driver.execute(DriverCommand(CommandKind.HOLD))
    resume = await driver.execute(DriverCommand(CommandKind.RESUME))

    assert mavlink.executed == [CommandKind.HOLD]
    assert swarm.executed == []
    assert hold.reason is None
    assert resume.reason is not None
    assert "swarm link" in resume.reason
    assert CommandKind.RESUME not in driver.capabilities  # rejected before dispatch
    assert CommandKind.HOLD in driver.capabilities


async def test_samples_are_merged_and_each_link_s_last_sample_is_known() -> None:
    clock = FakeClock(START)
    driver, mavlink, swarm, received = linked(clock)

    mavlink.deliver(at(AUTOPILOT, clock))
    swarm.deliver(at(SWARM_ONLY, clock))

    merged = received[-1]
    assert merged.source == "mavlink+swarm"
    assert merged.gps_fix is GpsFix.FIX_3D
    assert merged.flight_mode is FlightMode.OFFBOARD
    assert merged.swarm == SWARM_ONLY.swarm
    assert driver.last_heard() == {LinkSource.MAVLINK: START, LinkSource.SWARM: START}
