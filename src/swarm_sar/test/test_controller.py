"""Tests for swarm_sar.core.controller: the onboard decision loop, input by input."""

import dataclasses
import math

import numpy as np
import pytest
from swarm_sar.core import controller as ctl
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.controller import DepthOutcome, DroneController, SetpointKind
from swarm_sar.core.depth import CameraIntrinsics, DepthFrame
from swarm_sar.core.frames import level_attitude
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.messages import (CommandKind, CoverageUpdate, DroneStatus, HealthLevel,
                                     MissionSpec, Phase, Receipt, SwarmCommand, TargetReport)
from swarm_sar.core.pose import (AttitudeReport, FlightMode, LocalPositionReport,
                                 VehicleStatusReport)
from swarm_sar.core.supervisor import Fault, FcRequest

ORIGIN = GeoPoint(47.397742, 8.545594)
FRAME = LocalProjection(ORIGIN)
WIDTH, HEIGHT = 64, 36
FX = (WIDTH / 2.0) / math.tan(math.radians(87.0) / 2.0)
K = CameraIntrinsics(WIDTH, HEIGHT, FX, FX, (WIDTH - 1) / 2.0, (HEIGHT - 1) / 2.0)
OPEN = 20.0   # every pixel beyond the trusted range: free space, no obstacle
SQUARE = ((30.0, -40.0), (110.0, -40.0), (110.0, 40.0), (30.0, 40.0))
DT = 0.1


def config_for(**overrides):
    """Return a config for the small test camera (every pixel, like the simulator)."""
    return DroneConfig(depth_stride=1, **overrides)


def mission(sequence=1, waypoints=((15.0, 0.0),), altitude=10.0, area=SQUARE):
    return MissionSpec(sequence=sequence, mission_id=f'm{sequence}', origin=ORIGIN,
                       altitude=altitude, grid_resolution=5.0,
                       waypoints=tuple(FRAME.to_geo(x, y) for x, y in waypoints),
                       area=tuple(FRAME.to_geo(x, y) for x, y in area))


class Rig:
    """Feeds a controller what a flight controller and camera would, tick by tick."""

    def __init__(self, config=None, drone_id=0, mode=FlightMode.OFFBOARD):
        self.c = DroneController(drone_id, config or config_for())
        self.t = 0.0
        self.position = [0.0, 0.0, 10.0]
        self.velocity = (0.0, 0.0, 0.0)
        self.heading = 0.0
        self.armed = True
        self.mode = mode
        self.home = ORIGIN
        self.reset_marker = (0, 0, 0)
        self.depth = OPEN
        self.pose_link = True
        self.fc_link = True
        self.move = False
        self.events = []
        self.status = None

    def feed(self):
        t = self.t
        if self.fc_link:
            self.c.on_vehicle_status(VehicleStatusReport(t, self.armed, self.mode))
        if self.pose_link:
            self.c.on_attitude(AttitudeReport(t, level_attitude(self.heading), 0))
            self.c.on_local_position(LocalPositionReport(
                t, tuple(self.position), self.velocity, True, True, True, True, False,
                self.home, self.reset_marker))
        if self.depth is not None:
            image = np.full((HEIGHT, WIDTH), self.depth, dtype=np.float32)
            self.c.on_depth(DepthFrame(t, image, K), t)

    def tick(self, steps=1, **kwargs):
        out = None
        for _ in range(steps):
            self.feed()
            out = self.c.tick(self.t, **kwargs)
            self.events.extend(out.events)
            if out.status is not None:
                self.status = out.status
            if self.move and out.setpoint is not None:
                sp = out.setpoint
                if sp.kind is SetpointKind.VELOCITY:
                    self.position[0] += sp.velocity[0] * DT
                    self.position[1] += sp.velocity[1] * DT
                    self.velocity = (sp.velocity[0], sp.velocity[1], 0.0)
                else:
                    self.position = list(sp.position)
                    self.velocity = (0.0, 0.0, 0.0)
                self.heading = sp.heading
            self.t = round(self.t + DT, 9)
        return out

    def kinds(self):
        return [e.kind for e in self.events]


def engaged_rig(config=None, spec=None, **kwargs):
    rig = Rig(config, **kwargs)
    rig.c.on_mission(spec or mission(), 0.0)
    rig.tick()
    return rig


def test_streams_a_hold_at_the_current_pose_until_engaged():
    rig = Rig(mode=FlightMode.OTHER)
    rig.position = [3.0, -2.0, 7.0]
    rig.heading = 0.4
    out = rig.tick()
    assert not out.engaged and out.phase is Phase.STANDBY and out.fc_request is None
    assert out.setpoint.kind is SetpointKind.POSITION
    assert out.setpoint.position == (3.0, -2.0, 7.0)
    assert out.setpoint.heading == pytest.approx(0.4)
    assert out.status is not None and out.status.phase is Phase.STANDBY


def test_engagement_is_announced_and_holds_the_stopping_point_without_a_mission():
    rig = Rig()
    rig.velocity = (2.0, 0.0, 0.0)
    out = rig.tick()
    assert out.engaged and ctl.ENGAGED in rig.kinds()
    assert out.setpoint.kind is SetpointKind.POSITION
    stop = 2.0 * 2.0 / (2.0 * rig.c.config.max_accel)
    assert out.setpoint.position == pytest.approx((stop, 0.0, 10.0))
    rig.mode = FlightMode.HOLD
    out = rig.tick()
    assert not out.engaged and ctl.DISENGAGED in rig.kinds()


def test_mission_is_accepted_and_the_drone_transits_toward_the_waypoint():
    rig = Rig()
    assert rig.c.on_mission(mission(), 0.0) is Receipt.ACCEPTED
    out = rig.tick(5)
    assert ctl.MISSION_ACCEPTED in rig.kinds()
    assert out.phase is Phase.TRANSIT and rig.c.plan.sequence == 1
    assert out.setpoint.kind is SetpointKind.VELOCITY
    assert out.setpoint.velocity[0] > 0.0 and abs(out.setpoint.velocity[1]) < 1e-9
    assert out.setpoint.position[2] == 10.0
    assert rig.status.goal == pytest.approx((15.0, 0.0), abs=1e-6)


def test_the_drone_flies_its_waypoints_then_searches():
    rig = engaged_rig()
    rig.move = True
    rig.tick(40)
    assert ctl.WAYPOINT_REACHED in rig.kinds()
    assert rig.c.phase is Phase.SEARCH and rig.c.waypoint_index == 1


def test_mission_sequence_rules():
    rig = Rig()
    assert rig.c.on_mission(mission(2), 0.0) is Receipt.ACCEPTED
    assert rig.c.on_mission(mission(2), 0.0) is Receipt.IGNORED  # re-delivery
    assert rig.c.on_mission(mission(1), 0.0) is Receipt.IGNORED  # older
    out = rig.tick()
    assert rig.c.plan.sequence == 2
    assert rig.c.on_mission(mission(3, altitude=500.0), 0.1) is Receipt.INCOMPATIBLE
    out = rig.tick()
    assert ctl.MISSION_REJECTED in rig.kinds() and out.health.faults & Fault.MISSION_REJECTED
    assert rig.c.plan.sequence == 2  # the rejected mission did not replace the active one
    bowtie = ((30.0, 0.0), (60.0, 30.0), (60.0, 0.0), (30.0, 30.0))
    assert rig.c.on_mission(mission(4, area=bowtie), 0.2) is Receipt.INCOMPATIBLE
    assert rig.c.on_mission(mission(5), 0.2) is Receipt.ACCEPTED
    out = rig.tick()
    assert rig.c.plan.sequence == 5 and not out.health.faults & Fault.MISSION_REJECTED


def test_a_rejected_mission_supersedes_an_older_pending_one():
    # Regression: the older pending mission was activated and cleared the rejection fault,
    # so the swarm flew a mission the operator had already replaced, with no fault shown.
    rig = Rig()
    rig.c.on_mission(mission(1), 0.0)
    rig.c.on_mission(mission(2, altitude=500.0), 0.0)
    out = rig.tick()
    assert rig.c.plan is None and out.health.faults & Fault.MISSION_REJECTED
    assert out.phase is Phase.STANDBY


def test_mission_outside_the_geofence_is_rejected_at_activation():
    rig = Rig(config_for(geofence_radius=50.0))
    assert rig.c.on_mission(mission(), 0.0) is Receipt.ACCEPTED
    rig.tick()
    assert rig.c.plan is None
    assert any(e.kind == ctl.MISSION_REJECTED and 'geofence' in e.detail for e in rig.events)


def test_mission_waits_for_a_global_reference():
    rig = Rig()
    rig.home = None
    rig.c.on_mission(mission(), 0.0)
    out = rig.tick()
    assert rig.c.plan is None and out.health.faults & Fault.NO_GLOBAL_REFERENCE
    assert rig.status.position is None
    assert out.setpoint.kind is SetpointKind.POSITION  # holds: it cannot know where to go
    rig.home = ORIGIN
    rig.tick()
    assert rig.c.plan is not None


def test_depth_frame_outcomes():
    rig = Rig()
    image = np.full((HEIGHT, WIDTH), OPEN, dtype=np.float32)
    assert rig.c.on_depth(DepthFrame(0.0, image, K), 0.0) is DepthOutcome.NO_POSE
    rig.tick()
    cfg = rig.c.config
    now = rig.t
    rig.feed()
    assert rig.c.on_depth(DepthFrame(now - cfg.max_depth_age - 0.01, image, K), now) is \
        DepthOutcome.TOO_OLD
    assert rig.c.on_depth(DepthFrame(now + cfg.max_clock_skew + 0.01, image, K), now) is \
        DepthOutcome.FROM_FUTURE
    assert rig.c.on_depth(DepthFrame(now, image, K), now) is DepthOutcome.PROCESSED


def test_camera_warnings():
    rig = Rig(DroneConfig(depth_stride=8, self_clear_radius=0.9))
    rig.tick()
    warnings = [e.detail for e in rig.events if e.kind == ctl.CAMERA_WARNING]
    assert any('depth_stride' in w for w in warnings)
    assert any('self_clear_radius' in w for w in warnings)
    blind = Rig()
    image = np.full((HEIGHT, WIDTH), OPEN, dtype=np.float32)
    lopsided = CameraIntrinsics(WIDTH, HEIGHT, FX, FX, -5.0, 17.5)
    blind.feed()
    blind.c.on_depth(DepthFrame(0.0, image, lopsided), 0.0)
    out = blind.c.tick(0.0)
    assert any('no horizontal field of view' in e.detail for e in out.events)


def test_pose_loss_stops_setpoints_and_requests_hold_at_a_limited_rate():
    rig = engaged_rig()
    rig.pose_link = False
    rig.depth = None
    outs = [rig.tick() for _ in range(15)]
    lost = [o for o in outs if o.health.level is HealthLevel.CRITICAL]
    assert lost and all(o.setpoint is None for o in lost)
    requests = [i for i, o in enumerate(outs) if o.fc_request is not None]
    assert requests and all(outs[i].fc_request is FcRequest.HOLD for i in requests)
    period_ticks = round(rig.c.config.fc_request_period / DT)
    assert np.all(np.diff(requests) >= period_ticks)  # resent, but not every tick
    assert lost[0].health.faults & Fault.POSE_STALE


def test_depth_loss_holds_then_hands_over_to_the_autopilot():
    config = config_for(degraded_escalation_time=2.0)
    rig = engaged_rig(config)
    rig.tick(3)
    rig.depth = None
    outs = [rig.tick() for _ in range(30)]
    blind = [o for o in outs if o.health.faults & Fault.DEPTH_STALE]
    assert blind and all(o.setpoint.kind is SetpointKind.POSITION for o in blind)
    first_request = next(i for i, o in enumerate(outs) if o.fc_request is not None)
    first_blind = outs.index(blind[0])
    assert (first_request - first_blind) * DT == pytest.approx(2.0, abs=0.15)
    assert outs[first_request].fc_request is FcRequest.HOLD


def test_frame_reset_forgets_obstacles_and_poses():
    rig = engaged_rig()
    rig.depth = 5.0  # a wall ahead
    rig.tick()
    assert math.isfinite(rig.c.obstacle_map.nearest_obstacle((0.0, 0.0), rig.t, 10.0))
    rig.depth = None
    rig.reset_marker = (1, 0, 0)
    out = rig.tick()
    assert ctl.FRAME_RESET in rig.kinds()
    assert rig.c.obstacle_map.nearest_obstacle((0.0, 0.0), rig.t, 10.0) == math.inf
    assert out.health.faults & Fault.DEPTH_STALE


def test_operator_hold_and_resume():
    rig = engaged_rig()
    rig.tick(2)
    assert rig.c.on_command(SwarmCommand(1, CommandKind.HOLD, rig.t), rig.t) is Receipt.ACCEPTED
    out = rig.tick(2)
    assert out.phase is Phase.HOLD and out.setpoint.kind is SetpointKind.POSITION
    assert rig.status.command_sequence == 1
    assert rig.c.on_command(SwarmCommand(1, CommandKind.RESUME, rig.t), rig.t) is \
        Receipt.IGNORED  # same sequence: applied at most once
    assert rig.c.on_command(SwarmCommand(2, CommandKind.RESUME, rig.t), rig.t) is \
        Receipt.ACCEPTED
    assert rig.tick().phase is Phase.TRANSIT


def test_command_age_skew_and_addressing():
    rig = engaged_rig()
    cfg = rig.c.config
    now = rig.t
    stale = SwarmCommand(1, CommandKind.HOLD, now - cfg.command_max_age - 1.0)
    future = SwarmCommand(1, CommandKind.HOLD, now + cfg.max_clock_skew + 1.0)
    assert rig.c.on_command(stale, now) is Receipt.STALE
    assert rig.c.on_command(future, now) is Receipt.FUTURE
    other = SwarmCommand(1, CommandKind.HOLD, now, frozenset({7}))
    assert rig.c.on_command(other, now) is Receipt.IGNORED
    out = rig.tick(2)
    assert out.phase is Phase.TRANSIT and rig.status.command_sequence == 1  # acknowledged


def test_return_to_launch_is_requested_while_in_control():
    rig = engaged_rig()
    rig.c.on_command(SwarmCommand(1, CommandKind.RETURN_TO_LAUNCH, rig.t), rig.t)
    outs = [rig.tick() for _ in range(12)]
    requests = [o.fc_request for o in outs if o.fc_request is not None]
    assert requests == [FcRequest.RETURN, FcRequest.RETURN]  # resent once per second
    rig.mode = FlightMode.RETURN
    assert rig.tick().fc_request is None
    rig.c.on_command(SwarmCommand(2, CommandKind.LAND, rig.t), rig.t)
    assert rig.tick().fc_request is None  # not in control: the autopilot's RTL stands


def test_mode_request_does_not_outlive_its_engagement():
    # Regression: an RTL received while the pilot flew fired when offboard was engaged later.
    rig = Rig(mode=FlightMode.OTHER)
    rig.c.on_mission(mission(), 0.0)
    rig.tick()
    assert rig.c.on_command(SwarmCommand(1, CommandKind.RETURN_TO_LAUNCH, rig.t), rig.t) is \
        Receipt.ACCEPTED
    assert any('not forwarded' in e.detail for e in rig.tick().events)
    rig.mode = FlightMode.OFFBOARD
    outs = [rig.tick() for _ in range(5)]
    assert all(o.fc_request is None for o in outs)
    assert outs[-1].phase is Phase.TRANSIT


def test_target_reports_are_filtered_then_tracked():
    rig = Rig()
    now = rig.t
    far = FRAME.to_geo(20.0, 0.0)
    assert rig.c.on_target_report(TargetReport(now, far, 1.0, 0.9), now) is \
        Receipt.WRONG_MISSION
    rig.c.on_mission(mission(waypoints=()), 0.0)
    rig.tick()
    now = rig.t
    cfg = rig.c.config
    assert rig.c.on_target_report(TargetReport(now, far, 1.0, 0.1), now) is Receipt.IGNORED
    assert rig.c.on_target_report(TargetReport(now - cfg.max_detection_age - 0.1, far, 1.0,
                                               0.9), now) is Receipt.STALE
    assert rig.c.on_target_report(TargetReport(now + 1.0, far, 1.0, 0.9), now) is \
        Receipt.FUTURE
    assert rig.c.on_target_report(TargetReport(now, far, 1.0, 0.9), now) is Receipt.ACCEPTED
    out = rig.tick()
    assert rig.c.estimator.estimate.position == pytest.approx((20.0, 0.0), abs=1e-6)
    assert out.phase is Phase.TRACK  # alone and within recruit_radius: it tracks
    rig.tick(2)
    assert rig.status.estimate is not None
    goal = rig.status.goal
    assert math.hypot(goal[0] - 20.0, goal[1]) == pytest.approx(cfg.track_standoff, abs=0.5)


def test_peer_coverage_is_merged_only_for_the_active_mission():
    rig = Rig()
    update = CoverageUpdate(3, 0.0, 1, False, [0, 1], [0.0, 0.0])
    assert rig.c.on_coverage(update, 0.0) is Receipt.WRONG_MISSION
    rig.c.on_mission(mission(), 0.0)
    rig.tick()
    assert rig.c.on_coverage(dataclasses.replace(update, drone_id=0), 0.1) is Receipt.OWN
    assert rig.c.on_coverage(dataclasses.replace(update, mission_sequence=2), 0.1) is \
        Receipt.WRONG_MISSION
    assert rig.c.on_coverage(dataclasses.replace(update, stamp=5.0), 0.1) is Receipt.FUTURE
    bad = CoverageUpdate(3, 0.0, 1, False, [10 ** 6], [0.0])
    assert rig.c.on_coverage(bad, 0.1) is Receipt.INCOMPATIBLE
    assert rig.c.on_coverage(update, 0.1) is Receipt.ACCEPTED
    assert np.isfinite(rig.c.coverage.last_seen.reshape(-1)[:2]).all()


def test_broadcast_cadence():
    config = config_for()
    rig = engaged_rig(config, spec=mission(waypoints=()), drone_id=4)
    rig.move = True
    outs = [rig.tick() for _ in range(250)]
    statuses = [i for i, o in enumerate(outs) if o.status is not None]
    assert np.all(np.diff(statuses) == 2)  # every state_broadcast_period (0.2 s)
    full = [i for i, o in enumerate(outs) if o.coverage is not None and o.coverage.full]
    sparse = [i for i, o in enumerate(outs) if o.coverage is not None and not o.coverage.full]
    assert full and np.all(np.diff(full) == 200)  # every coverage_full_period (20 s)
    assert len(sparse) >= 15
    last = outs[sparse[-1]].coverage
    assert last.mission_sequence == 1 and last.last_seen.min() >= \
        rig.t - config.coverage_recent_window - 1.0


def test_altitude_is_corrected_before_moving_and_refused_when_too_far():
    rig = Rig()
    rig.position[2] = 9.0  # 1 m low: correct it first
    rig.c.on_mission(mission(), 0.0)
    out = rig.tick(2)
    assert out.setpoint.kind is SetpointKind.POSITION and out.setpoint.position[2] == 10.0
    far = Rig()
    far.position[2] = 4.0  # 6 m low: the camera cannot vouch for that climb
    far.c.on_mission(mission(), 0.0)
    out = far.tick(2)
    assert out.health.faults & Fault.ALTITUDE_MISMATCH
    assert out.setpoint.kind is SetpointKind.POSITION and out.setpoint.position[2] == 4.0


def test_a_blocked_waypoint_ends_in_hold_until_resume():
    config = config_for(stuck_timeout=2.0)
    rig = engaged_rig(config)
    rig.depth = 1.0  # a wall right ahead, and the rig never turns
    outs = [rig.tick() for _ in range(40)]
    assert ctl.WAYPOINT_UNREACHABLE in rig.kinds()
    assert outs[-1].phase is Phase.HOLD
    assert outs[-1].health.level is HealthLevel.DEGRADED
    assert all(o.fc_request is None for o in outs)  # attention fault: no escalation
    rig.c.on_command(SwarmCommand(1, CommandKind.RESUME, rig.t), rig.t)
    assert rig.tick().phase is Phase.TRANSIT


def test_a_blocked_search_goal_is_skipped():
    config = config_for(stuck_timeout=2.0)
    rig = engaged_rig(config, spec=mission(waypoints=()))
    rig.depth = 1.0
    rig.tick(40)
    assert ctl.GOAL_UNREACHABLE in rig.kinds()
    assert rig.c.phase is Phase.SEARCH


def test_new_mission_clears_hold_and_stuck_state():
    rig = engaged_rig()
    rig.c.on_command(SwarmCommand(1, CommandKind.HOLD, rig.t), rig.t)
    assert rig.tick().phase is Phase.HOLD
    rig.c.on_mission(mission(2), rig.t)
    assert rig.tick().phase is Phase.TRANSIT


def test_peers_are_heard_through_the_peer_table():
    rig = engaged_rig()
    peer = DroneStatus(9, rig.t, FRAME.to_geo(5.0, 0.0), (0.0, 0.0), 0.0, Phase.SEARCH,
                       HealthLevel.OK, 0, 1, 0)
    assert rig.c.on_peer_status(peer, rig.t) is Receipt.ACCEPTED
    assert rig.c.on_peer_status(peer, rig.t, protocol=1) is Receipt.INCOMPATIBLE
    out = rig.tick()
    assert out.planner is not None and out.planner.yielding  # a drone 5 m ahead


def test_overrun_is_reported_and_time_must_be_finite():
    rig = Rig()
    assert rig.tick(overrun=True).health.faults & Fault.CONTROL_OVERRUN
    with pytest.raises(ValueError):
        rig.c.tick(math.nan)


def peer_status(rig, drone_id=9, where=(40.0, 30.0)):
    return DroneStatus(drone_id, rig.t, FRAME.to_geo(*where), (0.0, 0.0), 0.0, Phase.SEARCH,
                       HealthLevel.OK, 0, 1, 0)


def test_losing_every_peer_holds_and_then_hands_over():
    config = config_for(degraded_escalation_time=2.0)
    rig = engaged_rig(config)
    for _ in range(5):
        rig.c.on_peer_status(peer_status(rig), rig.t)
        out = rig.tick()
    assert not out.health.faults & Fault.RADIO_SILENT
    outs = [rig.tick() for _ in range(45)]
    silent = [o for o in outs if o.health.faults & Fault.RADIO_SILENT]
    assert silent and all(o.setpoint.kind is SetpointKind.POSITION for o in silent)
    first = outs.index(silent[0])
    assert first * DT == pytest.approx(config.peer_timeout, abs=0.15)
    requests = [i for i, o in enumerate(outs) if o.fc_request is FcRequest.HOLD]
    assert requests and (requests[0] - first) * DT == pytest.approx(2.0, abs=0.15)
    # Hearing any peer again clears it; so does a new mission (the operator's way out when
    # the other drones have left for good).
    rig.c.on_peer_status(peer_status(rig), rig.t)
    assert not rig.tick().health.faults & Fault.RADIO_SILENT
    rig.tick(20)
    rig.c.on_mission(mission(2), rig.t)
    assert not rig.tick().health.faults & Fault.RADIO_SILENT


def test_a_drone_that_never_had_peers_is_not_radio_silent():
    rig = engaged_rig()
    assert not rig.tick(30).health.faults & Fault.RADIO_SILENT


def test_radio_silence_hold_can_be_disabled():
    rig = engaged_rig(config_for(hold_on_radio_silence=False))
    rig.c.on_peer_status(peer_status(rig), rig.t)
    out = rig.tick(30)
    assert not out.health.faults & Fault.RADIO_SILENT
    assert out.setpoint.kind is SetpointKind.VELOCITY


def test_silent_peers_are_still_avoided_where_they_were_last_heard():
    rig = engaged_rig()
    rig.c.on_peer_status(peer_status(rig, where=(5.0, 0.0)), rig.t)
    out = None
    for _ in range(30):  # 3 s: the peer at 5 m is lost; another one keeps talking
        rig.c.on_peer_status(peer_status(rig, drone_id=11, where=(-60.0, 0.0)), rig.t)
        out = rig.tick()
    assert out.planner is not None and out.planner.yielding


def test_sequences_ahead_of_the_clock_are_refused():
    # Regression: one forged sequence near the maximum locked a drone out of every later
    # mission and command until restart.
    rig = Rig()
    assert rig.c.on_mission(mission(10 ** 15), 0.0) is Receipt.FUTURE
    assert rig.c.on_mission(mission(3), 0.0) is Receipt.ACCEPTED
    rig.tick()
    forged = SwarmCommand(10 ** 15, CommandKind.HOLD, rig.t)
    assert rig.c.on_command(forged, rig.t) is Receipt.FUTURE
    assert rig.c.on_command(SwarmCommand(4, CommandKind.HOLD, rig.t), rig.t) is \
        Receipt.ACCEPTED


def test_backward_clock_step_is_absorbed():
    # Regression: after the clock stepped back, every new pose was "older" than the last
    # one and was dropped, so the controller kept flying on a frozen pose.
    rig = engaged_rig()
    rig.move = True
    rig.tick(20)
    before = rig.c.pose.position
    rig.t -= 10.0
    outs = [rig.tick() for _ in range(10)]
    assert ctl.CLOCK_JUMP in rig.kinds()
    assert rig.c.pose.stamp == pytest.approx(rig.t - DT)
    assert rig.c.pose.position[0] > before[0]  # the pose keeps following the vehicle
    assert all(o.health.level is HealthLevel.OK for o in outs)
    assert all(o.setpoint.kind is SetpointKind.VELOCITY for o in outs[1:])


def test_input_gap_does_not_count_as_being_stuck():
    rig = engaged_rig(config_for(stuck_timeout=2.0))
    rig.tick(5)
    rig.t += 5.0  # a stall or a forward clock step
    out = rig.tick()
    assert ctl.CLOCK_JUMP in rig.kinds()
    assert ctl.WAYPOINT_UNREACHABLE not in rig.kinds() and out.fc_request is None
    assert out.phase is Phase.TRANSIT


def test_progress_monitor_is_patient_with_queues_but_not_forever():
    monitor = ctl.ProgressMonitor(timeout=10.0, min_progress=1.0)
    assert not monitor.update(('goal',), 20.0, 0.0)
    assert not monitor.update(('goal',), 20.0, 11.0, patient=True)
    assert monitor.update(('goal',), 20.0, 11.0)
    assert monitor.update(('goal',), 20.0, 10.0 * ctl.YIELD_PATIENCE, patient=True)
    assert not monitor.update(('goal',), 18.5, 50.0)  # progress restarts the timer


def test_per_tick_overruns_are_reported_but_not_logged_as_fault_changes():
    rig = engaged_rig()
    rig.tick(3)
    rig.events.clear()
    outs = [rig.tick(overrun=(i % 2 == 0)) for i in range(6)]
    assert any(o.health.faults & Fault.CONTROL_OVERRUN for o in outs)
    assert ctl.FAULTS_CHANGED not in rig.kinds()


def test_waiting_behind_a_drone_is_not_a_blocked_waypoint_until_patience_runs_out():
    # Regression: drones queueing at a shared waypoint were declared stuck after
    # stuck_timeout and parked in HOLD until an operator intervened.
    config = config_for(stuck_timeout=2.0)
    rig = engaged_rig(config)
    queue = []
    for _ in range(int(3 * config.stuck_timeout / DT)):
        rig.c.on_peer_status(peer_status(rig, where=(3.2, 0.0)), rig.t)
        queue.append(rig.tick())
    assert all(o.planner.yielding for o in queue[5:])
    assert ctl.WAYPOINT_UNREACHABLE not in rig.kinds()
    for _ in range(int(ctl.YIELD_PATIENCE * config.stuck_timeout / DT)):
        rig.c.on_peer_status(peer_status(rig, where=(3.2, 0.0)), rig.t)
        rig.tick()
    assert ctl.WAYPOINT_UNREACHABLE in rig.kinds()  # a deadlock still surfaces
