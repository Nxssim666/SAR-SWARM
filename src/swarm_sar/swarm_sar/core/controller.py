"""
One drone's onboard decision loop: mission phases, safety gating and setpoint generation.

``DroneController`` is transport- and autopilot-agnostic. The ROS node and
the simulator feed it the same inputs (flight-controller reports, depth
frames, peer broadcasts, missions, operator commands, target reports) and
call ``tick`` at the control rate; ``tick`` returns the setpoint to stream
to the flight controller, an optional flight-mode request, and the
messages to broadcast. Both therefore execute identical decision code.

Authority model:

* The pilot arms, takes off and switches the flight controller to offboard.
  The controller never arms, takes off or enters offboard by itself.
* While the vehicle is not in offboard, the controller streams a hold at the
  vehicle's current pose, so engaging offboard is bumpless.
* While in offboard, it flies the mission: transit through the waypoints,
  search its share of the area, track a found target. Every velocity passes
  the local planner (depth-camera obstacles, other drones) last.
* It only ever asks the flight controller for a *safer* mode (Hold, RTL,
  Land), and only while it is itself in control.

Not thread-safe: every method must be called from one thread (the ROS node
uses a single-threaded executor; the simulator is sequential).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import enum
import math
from typing import Deque, List, Optional, Tuple

from swarm_sar.core.avoidance import Neighbor
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.coverage import CoverageMap
from swarm_sar.core.depth import CameraIntrinsics, DepthFrame, DepthProjector
from swarm_sar.core.frames import CameraMount
from swarm_sar.core.geodesy import LocalProjection
from swarm_sar.core.geometry import distance, id_direction, saturate, Vec2, Vec3
from swarm_sar.core.local_planner import LocalPlanner, PlannerResult
from swarm_sar.core.messages import (check_id, CommandKind, CoverageUpdate, DroneStatus,
                                     MissionSpec, Phase, PROTOCOL_VERSION, Receipt,
                                     sequence_is_plausible, SwarmCommand, TargetReport)
from swarm_sar.core.mission import (build_mission_plan, FrameLink, geofence_violation,
                                    MissionError, MissionPlan)
from swarm_sar.core.obstacle_map import ObstacleMap
from swarm_sar.core.pose import (AttitudeReport, FlightMode, LocalPositionReport, PoseHistory,
                                 PoseSample, VehicleStatusReport)
from swarm_sar.core.search import SearchPlanner
from swarm_sar.core.supervisor import (age, Fault, FcRequest, HealthReport, lasting_faults,
                                       Supervisor, SupervisorInputs)
from swarm_sar.core.swarm import elect_tracker, extrapolate, PeerTable, TargetEstimator
from swarm_sar.core.tracking import Detection

POSE_HISTORY_S = 2.0
MAX_PENDING_DETECTIONS = 64
# A longer gap between inputs means the process stalled or the clock jumped forward.
MAX_INPUT_GAP_S = 1.0
# Waiting behind other drones counts toward "stuck" this many times more slowly.
YIELD_PATIENCE = 4.0
_COVERAGE_PHASES = 16
_ACTIVE_PHASES = (Phase.TRANSIT, Phase.SEARCH, Phase.TRACK)

# Event kinds (stable strings: they appear in logs).
PHASE_CHANGED = 'phase_changed'
ENGAGED = 'engaged'
DISENGAGED = 'disengaged'
MISSION_ACCEPTED = 'mission_accepted'
MISSION_REJECTED = 'mission_rejected'
COMMAND_APPLIED = 'command_applied'
FAULTS_CHANGED = 'faults_changed'
FRAME_RESET = 'frame_reset'
CLOCK_JUMP = 'clock_jump'
WAYPOINT_REACHED = 'waypoint_reached'
WAYPOINT_UNREACHABLE = 'waypoint_unreachable'
GOAL_UNREACHABLE = 'goal_unreachable'
FC_REQUESTED = 'fc_requested'
CAMERA_WARNING = 'camera_warning'


@dataclass(frozen=True)
class ControllerEvent:
    """Something noteworthy for logs and diagnostics."""

    kind: str
    detail: str


class SetpointKind(enum.Enum):
    """How the flight controller should interpret a setpoint."""

    POSITION = 'position'  # hold ``position`` (x, y, z) and ``heading``
    VELOCITY = 'velocity'  # fly ``velocity`` horizontally, hold ``position[2]`` and ``heading``


@dataclass(frozen=True)
class Setpoint:
    """A setpoint in local ENU."""

    kind: SetpointKind
    position: Vec3
    velocity: Vec2
    heading: float


class DepthOutcome(enum.Enum):
    """What happened to an offered depth frame."""

    PROCESSED = 'processed'
    TOO_OLD = 'too_old'
    FROM_FUTURE = 'from_future'
    NO_POSE = 'no_pose'


@dataclass(frozen=True)
class ControlOutput:
    """Everything a control tick wants done."""

    setpoint: Optional[Setpoint]      # None: send nothing (the autopilot will fail safe)
    fc_request: Optional[FcRequest]   # a flight-mode change to request now
    status: Optional[DroneStatus]     # broadcast now
    coverage: Optional[CoverageUpdate]
    health: HealthReport
    phase: Phase
    engaged: bool
    planner: Optional[PlannerResult]
    events: Tuple[ControllerEvent, ...]


@dataclass(frozen=True)
class _Goal:
    """Where the active phase wants to go, in local ENU."""

    position: Vec2
    feed_forward: Vec2
    look: Optional[float]           # camera bearing while slow; None: follow the motion
    progress_key: Optional[tuple]   # identifies the goal for stuck detection; None: no check


class ProgressMonitor:
    """Detects a goal that has not come closer for ``timeout`` seconds."""

    def __init__(self, timeout: float, min_progress: float) -> None:
        self._timeout = timeout
        self._min_progress = min_progress
        self._key: Optional[tuple] = None
        self._best = math.inf
        self._since = 0.0

    def reset(self) -> None:
        """Forget the current goal."""
        self._key = None

    def pause(self, now: float) -> None:
        """Restart the timer (time spent unable to move does not count as being stuck)."""
        self._since = now

    def shift_time(self, delta: float) -> None:
        """Move the timer by ``delta`` seconds (the companion clock was stepped)."""
        self._since += delta

    def update(self, key: tuple, gap: float, now: float, patient: bool = False) -> bool:
        """
        Record the distance to the goal ``key``; return True once progress has stalled.

        ``patient`` (waiting for other drones) stretches the timeout: queues
        clear on their own, but a deadlock must still surface eventually.
        """
        if key != self._key:
            self._key, self._best, self._since = key, gap, now
            return False
        if gap < self._best - self._min_progress:
            self._best, self._since = gap, now
            return False
        limit = self._timeout * (YIELD_PATIENCE if patient else 1.0)
        return now - self._since >= limit


class DroneController:
    """The complete onboard logic of one drone."""

    def __init__(self, drone_id: int, config: DroneConfig) -> None:
        self._id = check_id(drone_id)
        self._cfg = config
        mount = CameraMount.from_degrees(config.camera_offset, config.camera_rpy_deg)
        self._projector = DepthProjector(mount, config.depth_stride, config.depth_trusted_range,
                                         config.band_above, config.band_below,
                                         math.radians(config.bearing_bin_deg))
        self._map = ObstacleMap(config.map_resolution, config.map_size, config.map_memory)
        self._planner = LocalPlanner(config)
        self._supervisor = Supervisor(config)
        self._peers = PeerTable(self._id, config)
        self._estimator = TargetEstimator(config)
        self._history = PoseHistory(POSE_HISTORY_S)
        self._progress = ProgressMonitor(config.stuck_timeout, config.stuck_min_progress)
        # latest inputs
        self._position: Optional[LocalPositionReport] = None
        self._attitude: Optional[AttitudeReport] = None
        self._vehicle: Optional[VehicleStatusReport] = None
        self._intrinsics: Optional[CameraIntrinsics] = None
        self._last_depth: Optional[float] = None
        self._depth_valid_fraction: Optional[float] = None
        self._local: Optional[LocalProjection] = None
        self._clock: Optional[float] = None  # newest time any input carried
        # swarm radio
        self._last_peer_heard: Optional[float] = None
        self._peers_expected = False  # a peer was heard during the active mission
        # mission
        self._plan: Optional[MissionPlan] = None
        self._pending: Optional[MissionPlan] = None
        self._highest_sequence = 0
        self._rejected_sequence = 0  # newest mission that could not be accepted
        self._link: Optional[FrameLink] = None
        self._coverage: Optional[CoverageMap] = None
        self._search: Optional[SearchPlanner] = None
        self._waypoint_index = 0
        self._waypoint_stuck = False
        self._goal_mission: Optional[Vec2] = None
        # operator
        self._command_sequence = 0
        self._operator_hold = False
        self._operator_request: Optional[FcRequest] = None
        # control state
        self._phase = Phase.STANDBY
        self._engaged = False
        self._tracking = False
        self._hold_point: Optional[Vec3] = None
        self._hold_heading = 0.0
        self._last_tick: Optional[float] = None
        self._faults = Fault.NONE
        self._last_fc_request: Optional[Tuple[FcRequest, float]] = None
        self._next_status: Optional[float] = None
        self._next_coverage: Optional[float] = None
        self._next_full_coverage: Optional[float] = None
        self._detections: Deque[Detection] = deque(maxlen=MAX_PENDING_DETECTIONS)
        self._events: List[ControllerEvent] = []

    # -- read-only views ------------------------------------------------
    @property
    def drone_id(self) -> int:
        """Return this drone's id."""
        return self._id

    @property
    def config(self) -> DroneConfig:
        """Return the configuration."""
        return self._cfg

    @property
    def phase(self) -> Phase:
        """Return the phase decided by the last tick."""
        return self._phase

    @property
    def plan(self) -> Optional[MissionPlan]:
        """Return the active mission, if any."""
        return self._plan

    @property
    def coverage(self) -> Optional[CoverageMap]:
        """Return this drone's coverage map for the active mission (treat as read-only)."""
        return self._coverage

    @property
    def obstacle_map(self) -> ObstacleMap:
        """Return the obstacle map (treat as read-only)."""
        return self._map

    @property
    def estimator(self) -> TargetEstimator:
        """Return the target estimator; treat it as read-only."""
        return self._estimator

    @property
    def pose(self) -> Optional[PoseSample]:
        """Return the latest pose sample."""
        return self._history.latest

    @property
    def waypoint_index(self) -> int:
        """Return the index of the next transit waypoint."""
        return self._waypoint_index

    # -- flight-controller and sensor inputs ---------------------------------
    def on_local_position(self, report: LocalPositionReport) -> None:
        """Take a local-position report (and pair it with the latest attitude)."""
        self._observe_clock(report.stamp)
        previous = self._position
        if previous is not None and report.reset_marker != previous.reset_marker:
            self._frame_reset(f'local position reset {previous.reset_marker} -> '
                              f'{report.reset_marker}')
        self._position = report
        self._update_reference(report)
        attitude = self._attitude
        if attitude is not None and abs(report.stamp - attitude.stamp) <= self._cfg.pose_timeout:
            self._history.append(PoseSample(report.stamp, report.position, report.velocity,
                                            attitude.quaternion))

    def on_attitude(self, report: AttitudeReport) -> None:
        """Take an attitude report."""
        self._observe_clock(report.stamp)
        previous = self._attitude
        if previous is not None and report.reset_counter != previous.reset_counter:
            self._frame_reset('attitude reset')
        self._attitude = report

    def on_vehicle_status(self, report: VehicleStatusReport) -> None:
        """Take an arming/flight-mode report."""
        self._observe_clock(report.stamp)
        self._vehicle = report

    def on_depth(self, frame: DepthFrame, now: float) -> DepthOutcome:
        """Fold a depth frame into the obstacle map using the pose at the frame's time."""
        self._observe_clock(now)
        lag = now - frame.stamp
        if lag > self._cfg.max_depth_age:
            return DepthOutcome.TOO_OLD
        if lag < -self._cfg.max_clock_skew:
            return DepthOutcome.FROM_FUTURE
        pose = self._history.at(frame.stamp, self._cfg.pose_timeout)
        if pose is None:
            return DepthOutcome.NO_POSE
        if frame.intrinsics != self._intrinsics:
            self._intrinsics = frame.intrinsics
            self._check_camera(frame.intrinsics)
        scan = self._projector.process(frame, pose)
        self._map.recenter((pose.position[0], pose.position[1]))
        self._map.integrate(scan)
        self._last_depth = now
        self._depth_valid_fraction = scan.valid_fraction
        return DepthOutcome.PROCESSED

    # -- swarm and ground-station inputs -------------------------------------
    def on_peer_status(self, status: DroneStatus, now: float,
                       protocol: int = PROTOCOL_VERSION) -> Receipt:
        """Take a peer's broadcast (``protocol``: the sender's protocol version)."""
        self._observe_clock(now)
        receipt = self._peers.offer(status, now, protocol)
        if receipt is not Receipt.OWN:
            self._last_peer_heard = now  # whatever it says, the radio receives
        if receipt is Receipt.ACCEPTED and self._plan is not None:
            self._peers_expected = True
        return receipt

    def on_coverage(self, update: CoverageUpdate, now: float) -> Receipt:
        """Merge a peer's coverage update if it belongs to the active mission."""
        self._observe_clock(now)
        if update.drone_id == self._id:
            return Receipt.OWN
        self._last_peer_heard = now
        if self._plan is None or self._coverage is None \
                or update.mission_sequence != self._plan.sequence:
            return Receipt.WRONG_MISSION
        if update.stamp > now + self._cfg.max_clock_skew:
            return Receipt.FUTURE
        try:
            self._coverage.merge_cells(update.cells, update.last_seen, now)
        except ValueError:
            return Receipt.INCOMPATIBLE
        return Receipt.ACCEPTED

    def on_mission(self, spec: MissionSpec, now: float) -> Receipt:
        """
        Take a mission; it becomes active at the next tick once it passes the geofence.

        Only a higher sequence number than any seen before is considered, so
        re-deliveries are no-ops and a stale mission can never replace a
        newer one.
        """
        self._observe_clock(now)
        if spec.sequence <= self._highest_sequence:
            return Receipt.IGNORED
        if not sequence_is_plausible(spec.sequence, now, self._cfg.max_clock_skew):
            return Receipt.FUTURE
        self._highest_sequence = spec.sequence
        cfg = self._cfg
        if not cfg.min_altitude <= spec.altitude <= cfg.max_altitude:
            self._reject(spec, f'altitude {spec.altitude} m outside [{cfg.min_altitude}, '
                               f'{cfg.max_altitude}] m')
            return Receipt.INCOMPATIBLE
        try:
            self._pending = build_mission_plan(spec)
        except MissionError as exc:
            self._reject(spec, str(exc))
            return Receipt.INCOMPATIBLE
        return Receipt.ACCEPTED

    def on_command(self, command: SwarmCommand, now: float) -> Receipt:
        """Apply an operator command (each sequence number at most once)."""
        self._observe_clock(now)
        if command.sequence <= self._command_sequence:
            return Receipt.IGNORED
        if command.stamp > now + self._cfg.max_clock_skew \
                or not sequence_is_plausible(command.sequence, now, self._cfg.max_clock_skew):
            return Receipt.FUTURE
        if now - command.stamp > self._cfg.command_max_age:
            return Receipt.STALE
        self._command_sequence = command.sequence
        if not command.applies_to(self._id):
            return Receipt.IGNORED
        if command.kind is CommandKind.HOLD:
            self._operator_hold = True
        elif command.kind is CommandKind.RESUME:
            self._operator_hold = False
            self._waypoint_stuck = False
            self._progress.reset()
        elif not self._engaged:
            # The pilot (or the autopilot) is in control: their decision stands.
            self._event(COMMAND_APPLIED, f'{command.kind.name} (sequence {command.sequence}) not '
                                         'forwarded: the companion is not in control')
            return Receipt.ACCEPTED
        elif command.kind is CommandKind.RETURN_TO_LAUNCH:
            self._operator_request = FcRequest.RETURN
        else:
            self._operator_request = FcRequest.LAND
        self._event(COMMAND_APPLIED, f'{command.kind.name} (sequence {command.sequence})')
        return Receipt.ACCEPTED

    def on_target_report(self, report: TargetReport, now: float) -> Receipt:
        """Queue an onboard detection of the target for the next tick."""
        self._observe_clock(now)
        if report.confidence < self._cfg.min_detection_confidence:
            return Receipt.IGNORED
        if self._plan is None:
            return Receipt.WRONG_MISSION
        if report.stamp > now + self._cfg.max_clock_skew:
            return Receipt.FUTURE
        if now - report.stamp > self._cfg.max_detection_age:
            return Receipt.STALE
        position = self._plan.projection.to_local(report.position)
        self._detections.append(Detection.isotropic(report.stamp, position, report.std))
        return Receipt.ACCEPTED

    # -- the control tick ------------------------------------------------------
    def tick(self, now: float, overrun: bool = False) -> ControlOutput:
        """Run one control step at ``now`` (seconds on the companion clock)."""
        if not math.isfinite(now):
            raise ValueError(f'now must be finite, got {now!r}')
        self._observe_clock(now)
        cfg = self._cfg
        dt = cfg.control_period if self._last_tick is None else \
            min(max(now - self._last_tick, 0.0), 0.5)
        self._last_tick = now

        vehicle = self._vehicle
        engaged = (vehicle is not None and age(now, vehicle.stamp) <= cfg.fc_timeout
                   and vehicle.armed and vehicle.mode is FlightMode.OFFBOARD)
        if engaged != self._engaged:
            self._on_engagement_change(engaged)
        self._activate_pending()
        self._peers.expire(now)

        pose = self._history.latest
        health, escalation = self._supervisor.update(now, self._inputs(now, pose, overrun),
                                                     engaged)
        lasting = lasting_faults(health.faults)
        if lasting != self._faults:
            self._event(FAULTS_CHANGED, _describe_faults(lasting))
            self._faults = lasting

        controllable = health.can_control and pose is not None
        p_mission: Optional[Vec2] = None
        if controllable and self._link is not None and pose is not None:
            p_mission = self._link.local_to_mission((pose.position[0], pose.position[1]))
            self._advance_waypoints(p_mission)
            if engaged and self._coverage is not None:
                self._coverage.observe(p_mission, cfg.detection_range, now)
        if self._plan is not None:
            self._update_target(now, p_mission)
        self._set_phase(self._decide_phase())

        setpoint: Optional[Setpoint] = None
        planned: Optional[PlannerResult] = None
        if controllable and pose is not None:
            setpoint, planned = self._motion(now, dt, pose, health, p_mission)
        fc_request = self._fc_request(now, escalation)
        status = self._status(now, pose, health)
        coverage = self._coverage_update(now)
        events, self._events = tuple(self._events), []
        return ControlOutput(setpoint, fc_request, status, coverage, health, self._phase,
                             self._engaged, planned, events)

    # -- tick helpers ------------------------------------------------------------
    def _inputs(self, now: float, pose: Optional[PoseSample], overrun: bool
                ) -> SupervisorInputs:
        """Sample the freshness and validity of every input for the supervisor."""
        cfg = self._cfg
        vehicle, report, plan = self._vehicle, self._position, self._plan
        return SupervisorInputs(
            status_age=age(now, None if vehicle is None else vehicle.stamp),
            pose_age=age(now, None if report is None else report.stamp),
            pose_usable=report is not None and report.usable and pose is not None,
            attitude_age=age(now, None if self._attitude is None else self._attitude.stamp),
            depth_age=age(now, self._last_depth),
            depth_valid_fraction=self._depth_valid_fraction,
            global_reference=self._local is not None,
            outside_geofence=pose is not None and math.hypot(
                pose.position[0], pose.position[1]) > cfg.geofence_radius,
            altitude_mismatch=(self._engaged and pose is not None and plan is not None
                               and abs(plan.altitude - pose.position[2])
                               > cfg.max_altitude_correction),
            waypoint_unreachable=self._waypoint_stuck,
            mission_rejected=self._rejected_sequence > (0 if plan is None else plan.sequence),
            overrun=overrun,
            radio_silent=(cfg.hold_on_radio_silence and self._peers_expected
                          and age(now, self._last_peer_heard) > cfg.peer_timeout))

    def _on_engagement_change(self, engaged: bool) -> None:
        self._engaged = engaged
        self._hold_point = None
        # A mode request belongs to the engagement it was made in: once the pilot or the
        # autopilot has taken over, it is superseded, and it must not fire on a later one.
        self._operator_request = None
        self._planner.reset()
        self._progress.reset()
        self._supervisor.reset()
        if engaged:
            self._event(ENGAGED, 'flight controller in offboard: companion has control')
        else:
            self._event(DISENGAGED, 'flight controller left offboard: companion yields')

    def _decide_phase(self) -> Phase:
        if self._plan is None or not self._engaged:
            return Phase.STANDBY
        if self._operator_hold or self._waypoint_stuck:
            return Phase.HOLD
        if self._tracking:
            return Phase.TRACK
        if self._waypoint_index < len(self._plan.waypoints):
            return Phase.TRANSIT
        return Phase.SEARCH

    def _set_phase(self, phase: Phase) -> None:
        if phase is self._phase:
            return
        self._event(PHASE_CHANGED, f'{self._phase.name} -> {phase.name}')
        self._phase = phase
        self._planner.reset()
        self._progress.reset()
        if self._search is not None:
            self._search.reset()

    def _advance_waypoints(self, p_mission: Vec2) -> None:
        plan = self._plan
        if plan is None or not self._engaged or self._phase is Phase.TRACK:
            return
        while self._waypoint_index < len(plan.waypoints):
            waypoint = plan.waypoints[self._waypoint_index]
            if distance(p_mission, waypoint) > self._cfg.waypoint_radius:
                return
            self._event(WAYPOINT_REACHED, f'waypoint {self._waypoint_index}')
            self._waypoint_index += 1
            self._progress.reset()

    def _update_target(self, now: float, p_mission: Optional[Vec2]) -> None:
        plan = self._plan
        assert plan is not None
        detections = tuple(self._detections)
        self._detections.clear()
        peer_estimates = [(s.drone_id, s.estimate) for s in self._peers.active()
                          if s.estimate is not None and s.mission_sequence == plan.sequence]
        for kind, detail in self._estimator.update(now, p_mission, self._tracking, detections,
                                                   peer_estimates):
            self._event(kind, detail)
        estimate = self._estimator.estimate
        can_track = (self._engaged and p_mission is not None and not self._operator_hold
                     and not self._waypoint_stuck)
        if estimate is None or not can_track or p_mission is None:
            self._tracking = False
            return
        candidates = []
        for s in self._peers.active():
            if (s.estimate is None or s.position is None or s.phase not in _ACTIVE_PHASES
                    or s.mission_sequence != plan.sequence):
                continue
            position = extrapolate(plan.projection.to_local(s.position), s.velocity, s.stamp, now)
            candidates.append((s.drone_id, position, s.phase is Phase.TRACK))
        self._tracking = elect_tracker(self._id, p_mission, self._tracking, estimate.position,
                                       candidates, self._cfg)

    def _motion(self, now: float, dt: float, pose: PoseSample, health: HealthReport,
                p_mission: Optional[Vec2]) -> Tuple[Setpoint, Optional[PlannerResult]]:
        cfg = self._cfg
        x, y, z = pose.position
        if not self._engaged:
            # Stream the vehicle's own pose so that switching to offboard does not jump.
            self._hold_point = None
            self._planner.reset()
            return Setpoint(SetpointKind.POSITION, (x, y, z), (0.0, 0.0), pose.heading), None
        plan = self._plan
        altitude_ok = plan is not None and not health.faults & Fault.ALTITUDE_MISMATCH
        target_z = plan.altitude if (plan is not None and altitude_ok) else None
        if (plan is None or p_mission is None or not health.can_move
                or self._phase not in _ACTIVE_PHASES):
            return self._hold(now, pose, target_z), None
        goal = self._goal(now, pose, p_mission)
        if goal is None:
            return self._hold(now, pose, target_z), None
        if abs(plan.altitude - z) > cfg.altitude_tolerance:
            # Correct the altitude first; horizontally the vehicle holds.
            return self._hold(now, pose, plan.altitude), None
        self._hold_point = None
        gx, gy = goal.position
        pull = (goal.feed_forward[0] + cfg.approach_gain * (gx - x),
                goal.feed_forward[1] + cfg.approach_gain * (gy - y))
        desired = saturate(pull, cfg.max_speed)
        result = self._planner.plan(self._id, (x, y), pose.heading, desired, self._map,
                                    self._neighbors(now), now, dt, goal.look)
        if goal.progress_key is not None and self._progress.update(
                goal.progress_key, distance((x, y), goal.position), now,
                patient=result.yielding):
            self._on_stuck(now)
        return Setpoint(SetpointKind.VELOCITY, (x, y, plan.altitude), result.velocity,
                        result.heading), result

    def _goal(self, now: float, pose: PoseSample, p_mission: Vec2) -> Optional[_Goal]:
        """Return where the active phase wants to go, or None to hold."""
        plan, link = self._plan, self._link
        assert plan is not None and link is not None
        here = (pose.position[0], pose.position[1])
        if self._phase is Phase.TRANSIT:
            index = self._waypoint_index
            self._goal_mission = plan.waypoints[index]
            goal = link.mission_to_local(self._goal_mission)
            return _Goal(goal, (0.0, 0.0), _bearing(here, goal, pose.heading),
                         ('waypoint', index))
        if self._phase is Phase.SEARCH and self._search is not None \
                and self._coverage is not None:
            searchers = []
            for s in self._peers.active():
                if s.position is None or s.phase is not Phase.SEARCH \
                        or s.mission_sequence != plan.sequence:
                    continue
                searchers.append(extrapolate(plan.projection.to_local(s.position), s.velocity,
                                             s.stamp, now))
            density = self._coverage.priority(now)
            boost = self._estimator.datum_boost(now, plan.geometry)
            if boost is not None:
                density = density * boost
            search_plan = self._search.plan(p_mission, searchers, density, now)
            self._goal_mission = search_plan.goal
            goal = link.mission_to_local(search_plan.goal)
            key = ('search', round(search_plan.goal[0], 1), round(search_plan.goal[1], 1))
            return _Goal(goal, (0.0, 0.0), _bearing(here, goal, pose.heading), key)
        if self._phase is Phase.TRACK:
            estimate = self._estimator.estimate
            if estimate is None:
                return None
            tx, ty = estimate.position
            dx, dy = p_mission[0] - tx, p_mission[1] - ty
            norm = math.hypot(dx, dy)
            ux, uy = (dx / norm, dy / norm) if norm > 1e-6 else id_direction(self._id)
            standoff = self._cfg.track_standoff
            self._goal_mission = (tx + ux * standoff, ty + uy * standoff)
            push = self._spacing_push(now, here)
            vx, vy = estimate.velocity
            # The ring moves with the target; the camera follows the motion (look None),
            # because the vehicle only translates where the depth camera can see.
            return _Goal(link.mission_to_local(self._goal_mission),
                         (vx + push[0], vy + push[1]), None, None)
        return None

    def _spacing_push(self, now: float, position: Vec2) -> Vec2:
        """Push away from other trackers closer than the spacing of an even ring."""
        k = self._cfg.num_trackers
        plan = self._plan
        if k < 2 or self._local is None or plan is None:
            return (0.0, 0.0)
        spacing = 2.0 * self._cfg.track_standoff * math.sin(math.pi / k)
        px, py = 0.0, 0.0
        for s in self._peers.active():
            if s.phase is not Phase.TRACK or s.position is None \
                    or s.mission_sequence != plan.sequence:
                continue
            qx, qy = extrapolate(self._local.to_local(s.position), s.velocity, s.stamp, now)
            gap = math.hypot(position[0] - qx, position[1] - qy)
            if gap >= spacing or gap < 1e-6:
                continue
            strength = self._cfg.max_speed * (spacing - gap) / spacing
            px += strength * (position[0] - qx) / gap
            py += strength * (position[1] - qy) / gap
        return (px, py)

    def _neighbors(self, now: float) -> List[Neighbor]:
        """Return every drone to avoid, in local ENU (lost peers as stationary obstacles)."""
        local = self._local
        if local is None:
            return []
        out = []
        for s in self._peers.active():
            if s.position is not None:
                where = extrapolate(local.to_local(s.position), s.velocity, s.stamp, now)
                out.append(Neighbor(s.drone_id, where, s.velocity))
        for s in self._peers.lost():
            if s.position is not None:
                out.append(Neighbor(s.drone_id, local.to_local(s.position), (0.0, 0.0)))
        return out

    def _hold(self, now: float, pose: PoseSample, target_z: Optional[float]) -> Setpoint:
        """
        Hold where a full stop from the current velocity ends.

        The planner only ever commands speeds that can stop inside proven free
        space, so that point lies within space the camera has cleared.
        """
        self._progress.pause(now)
        self._planner.reset()
        x, y, z = pose.position
        hold_z = z if target_z is None else target_z
        if self._hold_point is None:
            vx, vy = pose.velocity[0], pose.velocity[1]
            speed = math.hypot(vx, vy)
            reach = speed / (2.0 * self._cfg.max_accel)
            self._hold_point = (x + vx * reach, y + vy * reach, hold_z)
            self._hold_heading = pose.heading
        elif self._hold_point[2] != hold_z:
            self._hold_point = (self._hold_point[0], self._hold_point[1], hold_z)
        return Setpoint(SetpointKind.POSITION, self._hold_point, (0.0, 0.0), self._hold_heading)

    def _on_stuck(self, now: float) -> None:
        cfg = self._cfg
        if self._phase is Phase.TRANSIT:
            self._waypoint_stuck = True
            self._event(WAYPOINT_UNREACHABLE,
                        f'waypoint {self._waypoint_index}: no progress for {cfg.stuck_timeout} s; '
                        'holding until the operator sends RESUME or a new mission')
        elif self._search is not None and self._goal_mission is not None:
            self._search.mark_unreachable(self._goal_mission, cfg.detection_range,
                                          now + cfg.unreachable_goal_cooldown)
            gx, gy = self._goal_mission
            self._event(GOAL_UNREACHABLE, f'search goal ({gx:.1f}, {gy:.1f}) skipped for '
                                          f'{cfg.unreachable_goal_cooldown} s')
        self._progress.reset()

    def _fc_request(self, now: float, escalation: Optional[FcRequest]) -> Optional[FcRequest]:
        if not self._engaged:
            return None
        wanted = self._operator_request or escalation
        if wanted is None:
            return None
        last = self._last_fc_request
        if last is not None and last[0] is wanted and now - last[1] < self._cfg.fc_request_period:
            return None
        self._last_fc_request = (wanted, now)
        self._event(FC_REQUESTED, wanted.value)
        return wanted

    def _status(self, now: float, pose: Optional[PoseSample],
                health: HealthReport) -> Optional[DroneStatus]:
        if not self._due(now, self._next_status):
            return None
        self._next_status = now + self._cfg.state_broadcast_period
        position = None
        velocity: Vec2 = (0.0, 0.0)
        heading = 0.0
        nearest = math.inf
        if pose is not None:
            x, y = pose.position[0], pose.position[1]
            if self._local is not None:
                position = self._local.to_geo(x, y)
            velocity = (pose.velocity[0], pose.velocity[1])
            heading = pose.heading
            nearest = self._map.nearest_obstacle((x, y), now, self._cfg.depth_trusted_range)
        plan = self._plan
        in_mission = plan is not None and self._phase in _ACTIVE_PHASES
        return DroneStatus(
            drone_id=self._id, stamp=now, position=position, velocity=velocity,
            heading=heading, phase=self._phase, health=health.level, faults=int(health.faults),
            mission_sequence=0 if plan is None else plan.sequence,
            command_sequence=self._command_sequence,
            goal=self._goal_mission if in_mission else None,
            estimate=self._estimator.estimate if plan is not None else None,
            nearest_obstacle=nearest)

    def _coverage_update(self, now: float) -> Optional[CoverageUpdate]:
        plan, coverage = self._plan, self._coverage
        if plan is None or coverage is None:
            return None
        cfg = self._cfg
        phase_offset = (self._id % _COVERAGE_PHASES) / _COVERAGE_PHASES
        if self._next_coverage is None or self._next_full_coverage is None:
            self._next_coverage = now + phase_offset * cfg.coverage_broadcast_period
            self._next_full_coverage = now + phase_offset * cfg.coverage_full_period
        if self._due(now, self._next_full_coverage):
            self._next_full_coverage = now + cfg.coverage_full_period
            self._next_coverage = now + cfg.coverage_broadcast_period
            cells, times = coverage.cells_seen_since(-math.inf)
            return CoverageUpdate(self._id, now, plan.sequence, True, cells, times)
        if self._due(now, self._next_coverage):
            self._next_coverage = now + cfg.coverage_broadcast_period
            cells, times = coverage.cells_seen_since(now - cfg.coverage_recent_window)
            if cells.size:
                return CoverageUpdate(self._id, now, plan.sequence, False, cells, times)
        return None

    # -- bookkeeping ---------------------------------------------------------------
    def _event(self, kind: str, detail: str) -> None:
        self._events.append(ControllerEvent(kind, detail))

    def _observe_clock(self, now: float) -> None:
        """
        Notice the companion clock stepping (time sync) and keep every age honest.

        A backward step would make fresh reports look older than the stored
        ones (the pose history would reject them and control would continue
        on a frozen pose) and old data look fresh. It is absorbed by moving
        every stored time by the step. A forward jump, or a stall of the
        process, needs no shifting: the data really are that old and the
        supervisor treats them as stale, but the timers that would read the
        gap as progress stalling or as a long degradation start over.
        """
        last = self._clock
        if last is not None:
            step = now - last
            if step < -self._cfg.control_period:
                self._shift_time(step)
                self._event(CLOCK_JUMP, f'clock stepped back {-step:.3f} s; times shifted')
                last = None
            elif step > MAX_INPUT_GAP_S:
                self._progress.pause(now)
                self._supervisor.reset()
                self._event(CLOCK_JUMP, f'no input for {step:.3f} s (clock step or stall)')
        self._clock = now if last is None else max(last, now)

    def _shift_time(self, delta: float) -> None:
        """Move every stored companion-clock time by ``delta`` seconds."""
        if self._position is not None:
            self._position = replace(self._position, stamp=self._position.stamp + delta)
        if self._attitude is not None:
            self._attitude = replace(self._attitude, stamp=self._attitude.stamp + delta)
        if self._vehicle is not None:
            self._vehicle = replace(self._vehicle, stamp=self._vehicle.stamp + delta)
        self._history.shift_time(delta)
        self._map.shift_time(delta)
        self._peers.shift_time(delta)
        self._estimator.shift_time(delta)
        self._supervisor.shift_time(delta)
        self._progress.shift_time(delta)
        if self._search is not None:
            self._search.shift_time(delta)
        self._detections.clear()
        shifted = [None if t is None else t + delta for t in (
            self._last_depth, self._last_peer_heard, self._last_tick, self._next_status,
            self._next_coverage, self._next_full_coverage)]
        (self._last_depth, self._last_peer_heard, self._last_tick, self._next_status,
         self._next_coverage, self._next_full_coverage) = shifted
        if self._last_fc_request is not None:
            request, when = self._last_fc_request
            self._last_fc_request = (request, when + delta)

    def _frame_reset(self, reason: str) -> None:
        """Forget what no longer lines up after the local frame jumped (obstacles, poses)."""
        self._map.clear()
        self._history.clear()
        self._planner.reset()
        self._hold_point = None
        self._last_depth = None
        self._event(FRAME_RESET, reason)

    def _update_reference(self, report: LocalPositionReport) -> None:
        reference = report.global_reference
        if reference is None:
            self._local = None
            self._link = None
            return
        if self._local is not None and self._local.reference == reference:
            return
        try:
            self._local = LocalProjection(reference)
        except ValueError as exc:
            self._local = None
            self._link = None
            self._event(FRAME_RESET, f'unusable global reference: {exc}')
            return
        if self._plan is not None:
            self._link = FrameLink(self._local, self._plan.projection)

    def _activate_pending(self) -> None:
        plan = self._pending
        if plan is None or self._local is None:
            return
        self._pending = None
        home = plan.projection.to_local(self._local.reference)
        violation = geofence_violation(plan, home, self._cfg.geofence_radius)
        if violation is not None:
            self._reject(plan.spec, violation)
            return
        cfg = self._cfg
        self._plan = plan
        self._link = FrameLink(self._local, plan.projection)
        self._coverage = CoverageMap(plan.geometry, cfg.revisit_period)
        self._search = SearchPlanner(plan.geometry, cfg.detection_range,
                                     cfg.search_distance_scale, cfg.goal_switch_ratio,
                                     cfg.arrival_radius)
        self._waypoint_index = 0
        self._waypoint_stuck = False
        self._operator_hold = False
        self._tracking = False
        self._goal_mission = None
        # A new mission is also how an operator releases a drone whose peers all left.
        self._peers_expected = False
        self._estimator.reset()
        self._detections.clear()
        self._progress.reset()
        self._next_coverage = None
        self._next_full_coverage = None
        spec = plan.spec
        self._event(MISSION_ACCEPTED,
                    f'{spec.mission_id!r} (sequence {spec.sequence}): {len(plan.waypoints)} '
                    f'waypoints, area {plan.geometry.num_valid} cells, altitude {spec.altitude} m')

    def _reject(self, spec: MissionSpec, reason: str) -> None:
        self._rejected_sequence = max(self._rejected_sequence, spec.sequence)
        pending = self._pending
        if pending is not None and pending.sequence < spec.sequence:
            # The operator has already superseded it; flying it would be a guess.
            self._pending = None
        self._event(MISSION_REJECTED,
                    f'{spec.mission_id!r} (sequence {spec.sequence}): {reason}')

    def _due(self, now: float, deadline: Optional[float]) -> bool:
        """Return True if a periodic output is due (ticks jitter by up to half a period)."""
        return deadline is None or now >= deadline - 0.5 * self._cfg.control_period

    def _check_camera(self, intrinsics: CameraIntrinsics) -> None:
        half_fov = intrinsics.min_half_fov
        if half_fov <= 0.0:
            self._event(CAMERA_WARNING, 'camera intrinsics give no horizontal field of view: '
                                        'the vehicle will not translate')
            return
        self._planner.set_field_of_view(half_fov)
        spacing = self._cfg.depth_trusted_range * self._cfg.depth_stride / intrinsics.fx
        if spacing > self._cfg.obstacle_clearance / 2.0:
            self._event(CAMERA_WARNING,
                        f'depth samples are {spacing:.2f} m apart at '
                        f'{self._cfg.depth_trusted_range} m: obstacles thinner than that can '
                        'fall between samples (reduce depth_stride)')
        # The planner's corridor is widened by half a cell diagonal (cells are tested by
        # their centres); its near edge outside the view must lie in the assumed-free disc.
        corridor = self._cfg.obstacle_clearance + self._cfg.map_resolution * math.sqrt(0.5)
        needed = corridor / math.sin(half_fov)
        if self._cfg.self_clear_radius < needed:
            self._event(CAMERA_WARNING,
                        f'self_clear_radius {self._cfg.self_clear_radius} m is below '
                        f'{needed:.2f} m for this {math.degrees(2 * half_fov):.0f} deg camera: '
                        'the vehicle may need to turn before it can move off a hover')


def _bearing(origin: Vec2, target: Vec2, fallback: float) -> float:
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    if math.hypot(dx, dy) < 1e-6:
        return fallback
    return math.atan2(dy, dx)


def _describe_faults(faults: Fault) -> str:
    names = [f.name for f in Fault if f and f in faults and f.name]
    return ', '.join(sorted(names)) if names else 'none'
