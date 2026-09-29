"""The swarm simulation for CI accepts ground-sequenced missions and commands (epoch clock)."""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in (ROOT / 'src' / 'swarm_sar', ROOT / 'sim' / 'swarm'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from swarm_sar.core.geodesy import GeoPoint  # noqa: E402
from swarm_sar.core.messages import CommandKind, MissionSpec, Phase, SwarmCommand  # noqa: E402
from swarm_sim import build  # noqa: E402

NOW = 1_790_000_000.0


def run(sim, seconds):
    """Step for ``seconds``; return each drone's newest broadcast state (every 0.2 s)."""
    latest = {}
    for _ in range(int(round(seconds / sim.drone_config.control_period))):
        sim.step()
        latest.update((s.drone_id, s) for s in sim.statuses())
    return latest


def square_mission(sim, sequence, altitude=4.0):
    origin = sim.projection.reference
    corners = [(-20.0, 20.0), (20.0, 20.0), (20.0, 60.0), (-20.0, 60.0)]
    area = tuple(sim.projection.to_geo(e, n) for e, n in corners)
    return MissionSpec(sequence=sequence, mission_id='gcs', origin=GeoPoint(
        origin.latitude, origin.longitude), altitude=altitude, grid_resolution=5.0,
        waypoints=(), area=area)


@pytest.fixture
def sim():
    return build(3, seed=1, epoch=NOW)


def test_the_clock_is_the_unix_epoch(sim):
    states = run(sim, 1.0)

    assert sim.time == pytest.approx(NOW + 1.0)
    assert sorted(states) == [0, 1, 2]
    assert all(s.stamp > NOW for s in states.values())


def test_a_ground_mission_replaces_the_simulator_s_own(sim):
    run(sim, 1.0)
    sequence = int(sim.time * 1000)

    sim.send(square_mission(sim, sequence))
    states = run(sim, 1.0)

    assert {s.mission_sequence for s in states.values()} == {sequence}
    assert {s.phase for s in states.values()} <= {Phase.TRANSIT, Phase.SEARCH}


def test_a_ground_hold_is_applied_and_acknowledged(sim):
    run(sim, 1.0)
    sequence = int(sim.time * 1000)

    sim.send(SwarmCommand(sequence, CommandKind.HOLD, sim.time, frozenset({0, 1, 2})))
    states = run(sim, 1.0)

    assert {s.command_sequence for s in states.values()} == {sequence}
    assert {s.phase for s in states.values()} == {Phase.HOLD}


def test_a_sequence_ahead_of_the_drones_clock_is_ignored(sim):
    run(sim, 1.0)
    before = {s.drone_id: s.mission_sequence for s in run(sim, 0.2).values()}

    sim.send(square_mission(sim, int((sim.time + 10.0) * 1000)))
    states = run(sim, 1.0)

    assert {i: s.mission_sequence for i, s in states.items()} == before
