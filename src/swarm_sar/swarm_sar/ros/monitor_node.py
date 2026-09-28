"""
Ground-station monitor: mission KPIs, alerts, RViz2 visualisation and an optional CSV log.

Passive: it listens to the swarm and the mission and never publishes anything
the drones consume. It alerts (WARN log) when a drone's health drops, when a
drone goes silent, and when two drones get closer than ``min_separation``.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional, TextIO, Tuple

from rclpy.node import Node
from swarm_sar.core.config import ConfigError, DroneConfig
from swarm_sar.core.geometry import Vec2
from swarm_sar.core.messages import DroneStatus, HealthLevel, sequence_is_plausible
from swarm_sar.core.metrics import CSV_COLUMNS, csv_row, MetricsSnapshot, MetricsTracker
from swarm_sar.core.mission import build_mission_plan, MissionError, MissionPlan
from swarm_sar.core.supervisor import Fault, lasting_faults
from swarm_sar.ros.codec import Codec, MessageTypes, MessageValidationError
from swarm_sar.ros.topics import (COVERAGE_GRID_TOPIC, MARKERS_TOPIC, METRICS_TOPIC,
                                  MISSION_FRAME, MISSION_TOPIC, STATUS_TOPIC)
from swarm_sar.ros.util import (broadcast_qos, declare_config, declare_float, declare_int,
                                declare_text, DEFAULT_BROADCAST_DEPTH, guarded, latched_qos,
                                now_seconds, reliable_qos, run_node)
from swarm_sar.ros.visualization import build_coverage_grid, build_markers, VizTypes


class MonitorNode(Node):
    """Publishes /swarm_sar/metrics, /swarm_sar/markers and /swarm_sar/coverage."""

    def __init__(self, **node_kwargs: Any) -> None:
        super().__init__('monitor', **node_kwargs)
        self._cfg = declare_config(self, DroneConfig)
        publish_period = declare_float(self, 'publish_period', 0.5,
                                       'Period of metrics and visualisation output [s]', 0.0)
        report_period = declare_float(self, 'report_period', 5.0,
                                      'Period of the log line and CSV row [s]', 0.0)
        csv_path = declare_text(self, 'metrics_csv', '', 'CSV file for metrics; empty = off')
        depth = declare_int(self, 'swarm_qos_depth', DEFAULT_BROADCAST_DEPTH,
                            'History depth of the shared swarm channels', 1, 10_000)

        types = MessageTypes.load()
        self._codec = Codec(types)
        self._viz = VizTypes.load()
        self._plan: Optional[MissionPlan] = None
        self._metrics: Optional[MetricsTracker] = None
        self._snapshot: Optional[MetricsSnapshot] = None
        self._health: Dict[int, Tuple[HealthLevel, int]] = {}
        self._alive: Dict[int, float] = {}
        self._csv_file: Optional[TextIO] = None
        self._csv: Optional[Any] = None
        if csv_path:
            self._open_csv(csv_path)

        self._metrics_pub = self.create_publisher(types.SwarmMetrics, METRICS_TOPIC,
                                                  reliable_qos())
        self._markers_pub = self.create_publisher(self._viz.MarkerArray, MARKERS_TOPIC,
                                                  latched_qos())
        self._grid_pub = self.create_publisher(self._viz.OccupancyGrid, COVERAGE_GRID_TOPIC,
                                               latched_qos())
        self.create_subscription(types.DroneState, STATUS_TOPIC,
                                 guarded(self, 'status')(self._on_status), broadcast_qos(depth))
        self.create_subscription(types.Mission, MISSION_TOPIC,
                                 guarded(self, 'mission')(self._on_mission), latched_qos())
        self.create_timer(publish_period, guarded(self, 'publish')(self._publish))
        self.create_timer(report_period, guarded(self, 'report')(self._report))

    def destroy_node(self) -> None:
        """Close the CSV file before the node goes away."""
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv = None
        super().destroy_node()

    def _open_csv(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self._csv_file = open(path, 'w', newline='', encoding='utf-8')
        except OSError as exc:
            raise ConfigError(f'cannot open metrics_csv {path!r}: {exc}') from exc
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow(CSV_COLUMNS)
        self._csv_file.flush()

    def _on_mission(self, msg: Any) -> None:
        try:
            spec = self._codec.decode_mission(msg)
            if self._plan is not None and spec.sequence <= self._plan.sequence:
                return
            if not sequence_is_plausible(spec.sequence, now_seconds(self),
                                         self._cfg.max_clock_skew):
                self.get_logger().error(f'ignoring mission {spec.mission_id!r}: sequence '
                                        f'{spec.sequence} is ahead of this clock')
                return
            plan = build_mission_plan(spec)
        except (MessageValidationError, MissionError) as exc:
            self.get_logger().error(f'cannot display mission: {exc}')
            return
        self._plan = plan
        cfg = self._cfg
        self._metrics = MetricsTracker(plan.geometry, cfg.detection_range, cfg.revisit_period,
                                       alive_timeout=cfg.peer_timeout,
                                       continuity_threshold=cfg.detection_range)
        self.get_logger().info(f'monitoring mission {spec.mission_id!r} (sequence '
                               f'{spec.sequence}): {plan.geometry.num_valid} cells')

    def _on_status(self, msg: Any) -> None:
        try:
            status, _ = self._codec.decode_status(msg)
        except MessageValidationError as exc:
            self.get_logger().warning(f'dropped invalid status: {exc}', throttle_duration_sec=5.0)
            return
        now = now_seconds(self)
        if status.drone_id not in self._alive:
            self.get_logger().info(f'drone {status.drone_id} online')
        self._alive[status.drone_id] = now
        self._alert_on_health(status)
        if self._metrics is not None:
            self._metrics.record(status, self._mission_position(status), now)

    def _mission_position(self, status: DroneStatus) -> Optional[Vec2]:
        if self._plan is None or status.position is None:
            return None
        return self._plan.projection.to_local(status.position)

    def _alert_on_health(self, status: DroneStatus) -> None:
        previous = self._health.get(status.drone_id)
        current = (status.health, int(lasting_faults(status.faults)))
        self._health[status.drone_id] = current
        if previous == current:
            return
        if status.health is HealthLevel.OK:
            if previous is not None and previous[0] is not HealthLevel.OK:
                self.get_logger().info(f'drone {status.drone_id} healthy again')
            return
        names = [f.name for f in Fault if f and f.name and status.faults & f]
        self.get_logger().warning(f'drone {status.drone_id} {status.health.name}: '
                                  f'{", ".join(names) or "no fault bits"}')

    def _publish(self) -> None:
        now = now_seconds(self)
        cutoff = now - self._cfg.peer_timeout
        for drone_id in [d for d, seen in self._alive.items() if seen < cutoff]:
            del self._alive[drone_id]
            self._health.pop(drone_id, None)
            self.get_logger().warning(f'drone {drone_id} silent for {self._cfg.peer_timeout} s')
        metrics = self._metrics
        if metrics is None:
            return
        self._snapshot = metrics.snapshot(now)
        s = self._snapshot
        if s.min_separation is not None and s.min_separation < self._cfg.min_separation:
            self.get_logger().warning(f'two drones are {s.min_separation:.1f} m apart '
                                      f'(minimum {self._cfg.min_separation} m)',
                                      throttle_duration_sec=2.0)
        self._metrics_pub.publish(self._codec.encode_metrics(s, now, MISSION_FRAME))
        if self._markers_pub.get_subscription_count() > 0:
            drones: List[Tuple[DroneStatus, Vec2]] = [
                (status, position) for status, position in metrics.alive(now)
                if position is not None]
            self._markers_pub.publish(build_markers(self._viz, drones, self._plan, now,
                                                    MISSION_FRAME))
        if self._grid_pub.get_subscription_count() > 0:
            self._grid_pub.publish(build_coverage_grid(
                self._viz, metrics.explored_snapshot(), metrics.geometry, now,
                self._cfg.revisit_period, now, MISSION_FRAME))

    def _report(self) -> None:
        s = self._snapshot
        if s is None:
            self.get_logger().info(f'{len(self._alive)} drone(s) online; waiting for a mission')
            return
        detail = ''
        if s.time_to_first_detection is not None:
            detail += f'  found at {s.time_to_first_detection:.1f} s'
        if s.min_separation is not None:
            detail += f'  min separation {s.min_separation:.1f} m'
        if s.min_obstacle_distance is not None:
            detail += f'  nearest obstacle {s.min_obstacle_distance:.1f} m'
        self.get_logger().info(
            f't={s.mission_time:6.1f} s  drones {s.drones_alive}  explored '
            f'{100 * s.explored_fraction:5.1f}%  fresh {100 * s.fresh_fraction:5.1f}%  '
            f'tracking {s.num_tracking}  holding {s.num_holding}  degraded {s.num_degraded}'
            f'{detail}')
        if self._csv is not None and self._csv_file is not None:
            self._csv.writerow(csv_row(s))
            self._csv_file.flush()


def main(args: Optional[List[str]] = None) -> int:
    """Run the monitor node."""
    return run_node(MonitorNode, args)
