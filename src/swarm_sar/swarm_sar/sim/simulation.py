"""
Closed loop: the real ``DroneController`` flying simulated vehicles through a simulated forest.

Per control period, every drone receives what its real counterpart would:
flight-controller reports, a synthetic depth frame, detections from its
search camera, and the broadcasts its radio heard during the previous
period (one period of latency, so update order cannot bias the outcome).
The controller's setpoints and mode requests drive a PX4-like autopilot.

Failure injection (``DroneFaults``) switches off a drone's depth camera,
radio or autopilot link mid-run, which is how the tests check that each of
those failures ends in a stopped, held vehicle rather than a collision.

Ground truth (trees, target, true positions) is only used for scoring.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
import math
from typing import Callable, Deque, List, Optional, Set, Tuple, Union

import numpy as np

from swarm_sar.core.config import ConfigError, DroneConfig, SimConfig
from swarm_sar.core.controller import ControllerEvent, ControlOutput, DroneController
from swarm_sar.core.depth import DepthFrame
from swarm_sar.core.frames import CameraMount, level_attitude, quat_to_matrix
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.geometry import Bounds, Vec2
from swarm_sar.core.messages import (CoverageUpdate, DroneStatus, MissionSpec, Phase,
                                     SwarmCommand)
from swarm_sar.core.metrics import MetricsSnapshot, MetricsSummary, MetricsTracker
from swarm_sar.core.mission import build_mission_plan, MissionPlan
from swarm_sar.core.pose import FlightMode
from swarm_sar.sim.depth_camera import pinhole_intrinsics, SyntheticDepthCamera
from swarm_sar.sim.radio import Delivery, RadioModel
from swarm_sar.sim.rng import (drone_stream, make_rng, STREAM_DETECTOR, STREAM_FOREST,
                               STREAM_RADIO, STREAM_TARGET)
from swarm_sar.sim.vehicle import SimAutopilot, SimVehicle
from swarm_sar.sim.world import (Forest, mission_spec, sample_in_polygon, SearchDetector,
                                 spawn_positions, Target)

MAX_SIM_DRONES = 100
MAX_EVENT_LOG = 100_000
_AIRBORNE_ALTITUDE = 0.5
_TARGET_MIN_DISTANCE = 20.0

Broadcast = Union[DroneStatus, CoverageUpdate]
GroundMessage = Union[MissionSpec, SwarmCommand]


@dataclass
class DroneFaults:
    """Failure-injection switches for one simulated drone."""

    depth: bool = True    # the depth camera delivers frames
    radio: bool = True    # the drone transmits and receives swarm traffic
    fc_link: bool = True  # companion <-> autopilot link (reports in, setpoints out)


@dataclass
class SimDrone:
    """One simulated drone: controller, autopilot, camera and injected faults."""

    drone_id: int
    controller: DroneController
    autopilot: SimAutopilot
    camera: SyntheticDepthCamera
    mount: CameraMount
    faults: DroneFaults = field(default_factory=DroneFaults)
    last_output: Optional[ControlOutput] = None
    in_contact: bool = False

    @property
    def position(self) -> np.ndarray:
        """Return the true world position."""
        return self.autopilot.vehicle.position

    @property
    def airborne(self) -> bool:
        """Return True while the vehicle is armed and off the ground."""
        return self.autopilot.armed and self.position[2] > _AIRBORNE_ALTITUDE


@dataclass(frozen=True)
class DroneView:
    """What a renderer needs to draw one drone."""

    drone_id: int
    position: Vec2
    heading: float
    phase: Phase
    healthy: bool
    goal: Optional[Vec2]
    estimate_position: Optional[Vec2]
    estimate_covariance: Optional[np.ndarray]


@dataclass(frozen=True)
class Frame:
    """A renderable snapshot of the simulation."""

    time: float
    drones: Tuple[DroneView, ...]
    target: Vec2
    explored: np.ndarray
    metrics: MetricsSnapshot


@dataclass(frozen=True)
class SimReport:
    """Mission KPIs plus ground-truth safety results."""

    summary: MetricsSummary
    tree_collisions: int
    drone_collisions: int
    min_tree_clearance: float
    min_true_separation: float
    failsafes: int


class Simulation:
    """The swarm, the forest, the target and the radio in one process."""

    def __init__(self, drone_config: DroneConfig, sim_config: SimConfig, num_drones: int,
                 seed: int, forest: Optional[Forest] = None,
                 mission: Optional[MissionSpec] = None, engage_at: float = 0.0) -> None:
        if isinstance(num_drones, bool) or not isinstance(num_drones, int):
            raise ValueError(f'num_drones must be an int, got {num_drones!r}')
        if not 1 <= num_drones <= MAX_SIM_DRONES:
            raise ValueError(f'num_drones must be in [1, {MAX_SIM_DRONES}], got {num_drones}')
        self.drone_config = drone_config
        self.sim_config = sim_config
        self._dt = drone_config.control_period
        self._step_index = 0
        origin = GeoPoint(sim_config.origin_latitude, sim_config.origin_longitude)
        self.projection = LocalProjection(origin)
        self.mission = mission if mission is not None else mission_spec(sim_config)
        self.plan: MissionPlan = build_mission_plan(self.mission)
        launch = spawn_positions(num_drones, sim_config.spawn_spacing)
        launch_radius = max(math.hypot(*p) for p in launch)

        if forest is None:
            points = list(self.plan.area) + list(self.plan.waypoints) + [(0.0, 0.0)]
            box = Bounds.around(points)
            box = Bounds(box.xmin - 10.0, box.ymin - 10.0, box.xmax + 10.0, box.ymax + 10.0)
            keep_out = [((0.0, 0.0), sim_config.clearing_radius + launch_radius)]
            keep_out += [(w, drone_config.waypoint_radius + 2.0) for w in self.plan.waypoints]
            forest = Forest.random(box, sim_config.tree_density, sim_config.tree_radius, keep_out,
                                   make_rng(seed, STREAM_FOREST))
        self.forest = forest

        target_rng = make_rng(seed, STREAM_TARGET)
        start = sample_in_polygon(self.plan.area, target_rng)
        for _ in range(100):
            if math.hypot(*start) >= _TARGET_MIN_DISTANCE:
                break
            start = sample_in_polygon(self.plan.area, target_rng)
        self.target = Target(self.plan.area, sim_config.target_speed, target_rng, start)
        self._detector = SearchDetector(drone_config.detection_range,
                                        sim_config.detection_noise_std,
                                        sim_config.detection_probability, self.projection)
        self._detector_rng = make_rng(seed, STREAM_DETECTOR)
        self._radio = RadioModel(sim_config.radio_range, sim_config.packet_loss)
        self._radio_rng = make_rng(seed, STREAM_RADIO)

        intrinsics = pinhole_intrinsics(sim_config.camera_width, sim_config.camera_height,
                                        math.radians(sim_config.camera_hfov_deg))
        spacing = (drone_config.depth_trusted_range * drone_config.depth_stride / intrinsics.fx)
        if spacing > 2.0 * sim_config.tree_radius[0]:
            raise ConfigError(
                f'the simulated camera samples every {spacing:.2f} m at '
                f'{drone_config.depth_trusted_range} m, too coarse to see the thinnest trunk '
                f'({2.0 * sim_config.tree_radius[0]:.2f} m): raise camera_width or use '
                'depth_stride 1 in simulation')
        mount = CameraMount.from_degrees(drone_config.camera_offset, drone_config.camera_rpy_deg)
        mode = FlightMode.OFFBOARD if engage_at <= 0.0 else FlightMode.OTHER
        self.drones: List[SimDrone] = []
        for drone_id, (x, y) in enumerate(launch):
            vehicle = SimVehicle((x, y, sim_config.altitude), 0.0, sim_config.vehicle_max_accel,
                                 math.radians(sim_config.vehicle_yaw_rate_deg),
                                 sim_config.vehicle_climb_rate)
            autopilot = SimAutopilot(vehicle, (x, y, 0.0), self.projection.to_geo(x, y),
                                     armed=True, mode=mode)
            camera = SyntheticDepthCamera(intrinsics, sim_config.camera_max_range,
                                          sim_config.depth_noise, sim_config.depth_dropout,
                                          make_rng(seed, drone_stream(drone_id)))
            self.drones.append(SimDrone(drone_id, DroneController(drone_id, drone_config),
                                        autopilot, camera, mount))
        self._engage_at = engage_at
        self._ground: List[Tuple[float, GroundMessage]] = [(0.0, self.mission)]
        self._in_flight: List[Tuple[Tuple[float, float], int, Broadcast]] = []
        self._metrics = MetricsTracker(self.plan.geometry, drone_config.detection_range,
                                       drone_config.revisit_period,
                                       alive_timeout=drone_config.peer_timeout,
                                       continuity_threshold=drone_config.detection_range)
        self._last_snapshot: Optional[MetricsSnapshot] = None
        self.events: Deque[Tuple[float, int, ControllerEvent]] = deque(maxlen=MAX_EVENT_LOG)
        self.receipts: Counter = Counter()
        self.tree_collisions = 0
        self.drone_collisions = 0
        self.min_tree_clearance = math.inf
        self.min_true_separation = math.inf
        self._touching: Set[Tuple[int, int]] = set()

    @property
    def time(self) -> float:
        """Return the current simulated time, an exact multiple of the control period."""
        return self._step_index * self._dt

    def send(self, message: GroundMessage, at: Optional[float] = None) -> None:
        """Schedule a ground-station message (mission or command) for delivery."""
        self._ground.append((self.time if at is None else at, message))

    def step(self) -> MetricsSnapshot:
        """Advance the whole world by one control period."""
        now = self.time
        self._deliver_radio(now)
        self._deliver_ground(now)
        if self._engage_at > 0.0 and abs(now - self._engage_at) < self._dt / 2.0:
            for drone in self.drones:
                drone.autopilot.engage(FlightMode.OFFBOARD)
        target = self.target.position
        for drone in self.drones:
            self._sense(drone, now, target)
        outgoing: List[Tuple[Tuple[float, float], int, Broadcast]] = []
        for drone in self.drones:
            out = drone.controller.tick(now)
            drone.last_output = out
            self.events.extend((now, drone.drone_id, e) for e in out.events)
            ap = drone.autopilot
            if drone.faults.fc_link:
                if out.setpoint is not None:
                    ap.offer_setpoint(out.setpoint, now)
                if out.fc_request is not None:
                    ap.request(out.fc_request)
            where = (float(drone.position[0]), float(drone.position[1]))
            if out.status is not None:
                self._metrics.record(out.status, self._mission_position(out.status), now)
                if drone.faults.radio:
                    outgoing.append((where, drone.drone_id, out.status))
            if out.coverage is not None and drone.faults.radio:
                outgoing.append((where, drone.drone_id, out.coverage))
        for drone in self.drones:
            drone.autopilot.link_up = drone.faults.fc_link
            drone.autopilot.step(now, self._dt)
        self.target.step(self._dt)
        self._metrics.record_target(self.target.position)
        snapshot = self._metrics.snapshot(now)
        self._score_safety()
        self._in_flight = outgoing
        self._last_snapshot = snapshot
        self._step_index += 1
        return snapshot

    def run(self, duration: float,
            on_step: Optional[Callable[['Simulation', MetricsSnapshot], None]] = None
            ) -> SimReport:
        """Run for ``duration`` simulated seconds and return the report."""
        if not (math.isfinite(duration) and duration > 0):
            raise ValueError(f'duration must be positive, got {duration!r}')
        for _ in range(int(round(duration / self._dt))):
            snapshot = self.step()
            if on_step is not None:
                on_step(self, snapshot)
        return self.report()

    def report(self) -> SimReport:
        """Return KPIs and safety results so far."""
        return SimReport(self._metrics.summary(), self.tree_collisions, self.drone_collisions,
                         self.min_tree_clearance, self.min_true_separation,
                         sum(d.autopilot.failsafes for d in self.drones))

    def frame(self) -> Frame:
        """Return a renderable snapshot as of the last completed step."""
        if self._last_snapshot is None:
            raise RuntimeError('frame() called before the first step()')
        views = []
        for drone in self.drones:
            out = drone.last_output
            status = out.status if out is not None else None
            estimate = drone.controller.estimator.estimate
            views.append(DroneView(
                drone.drone_id, (float(drone.position[0]), float(drone.position[1])),
                drone.autopilot.vehicle.heading, drone.controller.phase,
                out is not None and out.health.can_move,
                None if status is None else status.goal,
                None if estimate is None else estimate.position,
                None if estimate is None else np.array(estimate.position_covariance)))
        return Frame(self.time - self._dt, tuple(views), self.target.position,
                     self._metrics.explored_snapshot(), self._last_snapshot)

    # -- internals ---------------------------------------------------------------
    def _mission_position(self, status: DroneStatus) -> Optional[Vec2]:
        return None if status.position is None else self.projection.to_local(status.position)

    def _deliver_radio(self, now: float) -> None:
        for sender_xy, sender_id, message in self._in_flight:
            for drone in self.drones:
                if drone.drone_id == sender_id or not drone.faults.radio:
                    continue
                fate = self._radio.deliver(sender_xy, drone.position, self._radio_rng)
                if fate is not Delivery.DELIVERED:
                    self.receipts[fate.value] += 1
                    continue
                if isinstance(message, DroneStatus):
                    receipt = drone.controller.on_peer_status(message, now)
                else:
                    receipt = drone.controller.on_coverage(message, now)
                self.receipts[receipt.value] += 1

    def _deliver_ground(self, now: float) -> None:
        due = [m for t, m in self._ground if t <= now + 1e-9]
        self._ground = [(t, m) for t, m in self._ground if t > now + 1e-9]
        for message in due:
            for drone in self.drones:
                if not drone.faults.radio:
                    continue
                if isinstance(message, MissionSpec):
                    receipt = drone.controller.on_mission(message, now)
                else:
                    receipt = drone.controller.on_command(message, now)
                self.receipts[receipt.value] += 1

    def _sense(self, drone: SimDrone, now: float, target: Vec2) -> None:
        ap = drone.autopilot
        controller = drone.controller
        if drone.faults.fc_link:
            controller.on_vehicle_status(ap.status(now))
            controller.on_attitude(ap.attitude(now))
            controller.on_local_position(ap.local_position(now))
        if drone.faults.depth and ap.armed:
            rotation = quat_to_matrix(level_attitude(ap.vehicle.heading))
            camera_position = drone.position + rotation @ np.asarray(drone.mount.offset_frd)
            image = drone.camera.render(camera_position, rotation @ drone.mount.r_frd_optical,
                                        self.forest)
            controller.on_depth(DepthFrame(now, image, drone.camera.intrinsics), now)
        if drone.airborne:
            xy = (float(drone.position[0]), float(drone.position[1]))
            report = self._detector.sense(xy, target, now, self._detector_rng)
            if report is not None:
                controller.on_target_report(report, now)

    def _score_safety(self) -> None:
        radius = self.sim_config.drone_radius
        airborne = [d for d in self.drones if d.airborne]
        for drone in airborne:
            clearance = self.forest.clearance(drone.position[:2], float(drone.position[2]))
            self.min_tree_clearance = min(self.min_tree_clearance, clearance)
            contact = clearance < radius
            if contact and not drone.in_contact:
                self.tree_collisions += 1
            drone.in_contact = contact
        touching = set()
        for i, a in enumerate(airborne):
            for b in airborne[i + 1:]:
                gap = float(np.linalg.norm(a.position - b.position))
                self.min_true_separation = min(self.min_true_separation, gap)
                if gap < 2.0 * radius:
                    pair = (a.drone_id, b.drone_id)
                    touching.add(pair)
                    if pair not in self._touching:
                        self.drone_collisions += 1
        self._touching = touching


def check_sim_arguments(num_drones: int, duration: float) -> None:
    """Validate run arguments shared by the CLI and the tests."""
    if not 1 <= num_drones <= MAX_SIM_DRONES:
        raise ConfigError(f'num_drones must be in [1, {MAX_SIM_DRONES}]')
    if not (math.isfinite(duration) and duration > 0):
        raise ConfigError('duration must be positive')
