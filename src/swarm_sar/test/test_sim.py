"""
Closed-loop tests: the real controller flying simulated vehicles, cameras and radios.

These are the end-to-end safety checks: whatever the mission logic does, no
drone may touch a tree or another drone, and every injected failure must end
in a stopped vehicle under autopilot authority.
"""

import math

import numpy as np
import pytest
from swarm_sar.core import controller as ctl
from swarm_sar.core.config import ConfigError, DroneConfig, SimConfig
from swarm_sar.core.messages import CommandKind, Phase, SwarmCommand
from swarm_sar.core.pose import FlightMode
from swarm_sar.core.supervisor import Fault
from swarm_sar.sim.simulation import check_sim_arguments, MAX_SIM_DRONES, Simulation
from swarm_sar.sim.world import Forest

CFG = DroneConfig(depth_stride=1)


def event_kinds(sim):
    return [event.kind for _, _, event in sim.events]


def speed(drone):
    return float(np.hypot(*drone.autopilot.vehicle.velocity[:2]))


@pytest.mark.slow
def test_forest_mission_is_flown_safely_and_completely():
    sim = Simulation(CFG, SimConfig(), num_drones=4, seed=11)
    report = sim.run(150.0)
    assert report.tree_collisions == 0 and report.drone_collisions == 0
    # The configured clearance holds against ground truth (small allowance for the
    # vehicle's tracking lag); v1-style free-space leaks showed up here as 0.71-0.76 m.
    assert report.min_tree_clearance >= CFG.obstacle_clearance - 0.05
    assert report.min_true_separation >= 0.95 * CFG.min_separation
    assert report.failsafes == 0
    assert report.summary.explored_fraction >= 0.9
    assert report.summary.time_to_first_detection is not None
    assert ctl.WAYPOINT_UNREACHABLE not in event_kinds(sim)


def test_depth_failure_ends_in_a_stop_and_an_autopilot_hold():
    sim = Simulation(CFG, SimConfig(), 1, seed=3, forest=Forest.empty())
    sim.run(10.0)
    drone = sim.drones[0]
    assert speed(drone) > 1.0
    before = drone.position.copy()
    drone.faults.depth = False
    sim.run(CFG.depth_timeout + 1.0)
    assert drone.last_output.setpoint.kind is ctl.SetpointKind.POSITION  # holding
    sim.run(CFG.degraded_escalation_time)
    assert drone.autopilot.mode is FlightMode.HOLD  # handed over, not a failsafe
    assert sim.report().failsafes == 0
    stop = CFG.max_speed * CFG.depth_timeout + CFG.max_speed ** 2 / (2 * CFG.max_accel)
    assert float(np.hypot(*(drone.position - before)[:2])) <= stop
    assert speed(drone) < 0.05


def test_autopilot_link_loss_triggers_the_offboard_failsafe():
    sim = Simulation(CFG, SimConfig(), 1, seed=3, forest=Forest.empty())
    sim.run(10.0)
    drone = sim.drones[0]
    drone.faults.fc_link = False
    sim.run(5.0)
    assert drone.autopilot.mode is FlightMode.HOLD and sim.report().failsafes == 1
    assert drone.last_output.setpoint is None  # the companion stopped streaming
    assert not drone.last_output.health.can_control
    assert speed(drone) < 0.05


def test_radio_failure_ends_in_a_hold_and_the_others_carry_on():
    sim = Simulation(CFG, SimConfig(), 4, seed=5)
    sim.run(40.0)
    mute = sim.drones[0]
    assert speed(mute) > 1.0
    mute.faults.radio = False
    sim.run(CFG.peer_timeout + 3.0)
    assert mute.last_output.health.faults & Fault.RADIO_SILENT
    assert speed(mute) < 0.1  # it cannot deconflict any more: it stops
    sim.run(CFG.degraded_escalation_time)
    assert mute.autopilot.mode is FlightMode.HOLD  # and hands over to the autopilot
    others = [d for d in sim.drones if d is not mute]
    assert all(d.controller.phase in (Phase.SEARCH, Phase.TRACK) for d in others)
    report = sim.run(30.0)
    assert report.drone_collisions == 0 and report.tree_collisions == 0
    assert report.min_true_separation >= 0.95 * CFG.min_separation


def test_hold_resume_and_targeted_return_to_launch():
    sim = Simulation(CFG, SimConfig(), 2, seed=3, forest=Forest.empty())
    sim.run(5.0)
    sim.send(SwarmCommand(1, CommandKind.HOLD, sim.time))
    sim.run(3.0)
    assert all(d.controller.phase is Phase.HOLD and speed(d) < 0.1 for d in sim.drones)
    sim.send(SwarmCommand(2, CommandKind.RESUME, sim.time))
    sim.run(3.0)
    assert all(d.controller.phase is Phase.TRANSIT and speed(d) > 0.5 for d in sim.drones)
    sim.send(SwarmCommand(3, CommandKind.RETURN_TO_LAUNCH, sim.time, frozenset({1})))
    sim.run(3.0)
    assert sim.drones[0].autopilot.mode is FlightMode.OFFBOARD
    assert sim.drones[1].autopilot.mode is FlightMode.RETURN
    assert sim.drones[1].controller.phase is Phase.STANDBY  # yielded to the autopilot
    sim.run(60.0)
    home = sim.drones[1].autopilot.home
    assert not sim.drones[1].autopilot.armed
    assert float(np.hypot(*(sim.drones[1].position - home)[:2])) < 1.5


def test_engagement_is_bumpless():
    sim = Simulation(CFG, SimConfig(), 2, seed=3, forest=Forest.empty(), engage_at=3.0)
    start = [d.position.copy() for d in sim.drones]
    sim.run(2.9)
    assert all(np.allclose(d.position, s, atol=1e-6) for d, s in zip(sim.drones, start))
    assert all(d.controller.phase is Phase.STANDBY for d in sim.drones)
    sim.run(5.0)
    assert all(d.controller.phase is Phase.TRANSIT for d in sim.drones)
    assert ctl.ENGAGED in event_kinds(sim)


def test_lossy_radio_keeps_drones_apart():
    sim = Simulation(CFG, SimConfig(packet_loss=0.3), 4, seed=5)
    report = sim.run(60.0)
    assert sim.receipts['lost'] > 0
    assert report.drone_collisions == 0 and report.tree_collisions == 0
    assert report.min_true_separation >= 0.95 * CFG.min_separation


def test_runs_are_deterministic_per_seed():
    def trajectory(seed):
        sim = Simulation(CFG, SimConfig(), 2, seed=seed)
        sim.run(8.0)
        return np.array([d.position for d in sim.drones]), sim.forest.centers

    first, forest_a = trajectory(7)
    second, forest_b = trajectory(7)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(forest_a, forest_b)
    other, forest_c = trajectory(8)
    assert not np.array_equal(forest_a, forest_c)


def test_frame_snapshot():
    sim = Simulation(CFG, SimConfig(), 2, seed=1, forest=Forest.empty())
    with pytest.raises(RuntimeError):
        sim.frame()
    sim.run(1.0)
    frame = sim.frame()
    assert len(frame.drones) == 2 and frame.time == pytest.approx(0.9)
    assert frame.explored.shape == sim.plan.geometry.shape


def test_argument_validation():
    for count in (0, MAX_SIM_DRONES + 1, True, 2.0):
        with pytest.raises(ValueError):
            Simulation(CFG, SimConfig(), count, seed=1)
    with pytest.raises(ConfigError, match='depth_stride'):
        Simulation(DroneConfig(depth_stride=4), SimConfig(), 1, seed=1)
    with pytest.raises(ConfigError):
        check_sim_arguments(0, 10.0)
    with pytest.raises(ConfigError):
        check_sim_arguments(2, math.nan)
    sim = Simulation(CFG, SimConfig(), 1, seed=1, forest=Forest.empty())
    with pytest.raises(ValueError):
        sim.run(0.0)
