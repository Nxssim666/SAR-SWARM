"""
Local planner: turns a desired velocity into one that is safe to fly right now.

Along each candidate direction the planner computes the speed interval that
satisfies every hard constraint at once:

1. **Static obstacles and unobserved space.** A corridor
   ``obstacle_clearance`` wide on each side must be known free (see
   ``ObstacleMap``) for at least the braking distance of the commanded
   speed, including ``reaction_time`` of latency. Unknown space counts as
   blocked, so the vehicle never flies where the camera has not recently
   looked.
2. **The camera's view.** A forward camera cannot see the vehicle's own
   surroundings, so unobserved space within ``self_clear_radius`` of where
   the vehicle last *stood still* is passable; without that it could never
   move off a hover. The disc stays where the motion began: once moving,
   only space the camera has actually seen counts (a disc that travelled
   with the vehicle let it slide past trunk flanks it had never seen).
   The vehicle also only translates in directions inside the camera's
   horizontal field of view, so a drift sideways or backwards cannot creep
   into space nobody looked at.
3. **Other drones.** One closing-speed half-plane per nearby drone
   (``avoidance.separation_constraints``); some of them force a minimum
   retreat speed.

It then picks the direction and speed that make the most progress toward
the desired velocity, with a small preference for passing on the right (so
two drones meeting head-on both swerve the same way) and a small
hysteresis (so it does not flip between two equally good detours); when
the desired velocity itself is safe it is flown unchanged. If nothing
useful is possible it stops and turns the camera: toward the goal when the
way there is merely unobserved (that is how unknown space gets observed),
toward the most promising way around when an obstacle it has seen blocks
it. If stopping itself is unsafe (a drone closing in) it takes the gentlest
escape into known free space, in any direction. Speed-ups are limited to
``max_accel``; braking never is.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

import numpy as np

from swarm_sar.core.avoidance import Neighbor, separation_constraints, speed_bounds
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.geometry import Vec2, wrap_angle
from swarm_sar.core.obstacle_map import ObstacleMap

_HYSTERESIS_ANGLE = math.radians(20.0)
_HYSTERESIS_BONUS = 1.15
_RIGHT_BIAS = 0.05
_FEASIBILITY_TOLERANCE = 1e-9


@dataclass(frozen=True)
class PlannerResult:
    """The safe command for this tick."""

    velocity: Vec2
    heading: float
    free_distance: float  # clearance-aware free distance along the commanded direction [m]
    blocked: bool         # the desired motion was impossible (stopped, turning to look)
    yielding: bool = False  # other drones, not obstacles, hold back the desired motion


def braking_speeds(distance: np.ndarray, deceleration: float, reaction_time: float) -> np.ndarray:
    """Return, per distance, the speed from which the vehicle can still stop in time."""
    d = np.maximum(distance, 0.0)
    return deceleration * (np.sqrt(reaction_time ** 2 + 2.0 * d / deceleration) - reaction_time)


def free_distances(blocked: np.ndarray, directions: np.ndarray, clearance: float,
                   lookahead: float) -> np.ndarray:
    """
    Return how far a disc of radius ``clearance`` can travel along each direction.

    ``blocked`` holds ``(N, 2)`` offsets of blocked cell centres from the
    vehicle. A cell blocks a direction if it lies ahead and within
    ``clearance`` of the path; the travel ends where the disc first touches
    it. Cells already inside the disc block every direction that is not
    moving away from them.
    """
    if blocked.shape[0] == 0:
        return np.full(directions.shape, lookahead)
    cos = np.cos(directions)[:, None]
    sin = np.sin(directions)[:, None]
    bx = blocked[None, :, 0]
    by = blocked[None, :, 1]
    along = bx * cos + by * sin
    perp = np.abs(by * cos - bx * sin)
    touching = (along > 0.0) & (perp < clearance)
    stop = along - np.sqrt(np.maximum(clearance * clearance - perp * perp, 0.0))
    stop = np.where(touching, stop, lookahead)
    return np.clip(stop.min(axis=1), 0.0, lookahead)


def _wrapped(angles: np.ndarray) -> np.ndarray:
    return (angles + math.pi) % (2.0 * math.pi) - math.pi


class LocalPlanner:
    """Direction-sampling planner over obstacle, field-of-view and separation constraints."""

    def __init__(self, config: DroneConfig) -> None:
        self._cfg = config
        self._directions = np.linspace(-math.pi, math.pi, config.planning_directions,
                                       endpoint=False)
        # Cells are tested by their centres; widen the corridor by half a cell diagonal.
        self._clearance = config.obstacle_clearance + config.map_resolution * math.sqrt(0.5)
        self._lookahead = config.depth_trusted_range
        # Mount yaw is positive to the right (FRD); ENU headings grow counter-clockwise.
        self._camera_yaw = -math.radians(config.camera_rpy_deg[2])
        self._view_half_angle: Optional[float] = None
        self._last_direction: Optional[float] = None
        self._last_speed = 0.0
        self._anchor: Optional[Vec2] = None

    @property
    def window_radius(self) -> float:
        """Return how far around the vehicle the planner inspects the map."""
        return self._lookahead + self._clearance

    @property
    def view_half_angle(self) -> Optional[float]:
        """Return the horizontal half field of view travel is limited to (None: unknown)."""
        return self._view_half_angle

    def set_field_of_view(self, half_angle: float) -> None:
        """Set the depth camera's horizontal half field of view [rad] (from its intrinsics)."""
        if not math.isfinite(half_angle) or half_angle <= 0.0:
            raise ValueError(f'half_angle must be positive, got {half_angle!r}')
        self._view_half_angle = min(float(half_angle), math.pi)

    @property
    def self_clear_center(self) -> Optional[Vec2]:
        """Return where the vehicle last stood still (centre of the assumed-free disc)."""
        return self._anchor

    def reset(self) -> None:
        """Forget hysteresis, speed history and the stand-still point (hold, frame reset, ...)."""
        self._last_direction = None
        self._last_speed = 0.0
        self._anchor = None

    def plan(self, own_id: int, position: Vec2, heading: float, desired: Vec2,
             obstacle_map: ObstacleMap, neighbors: Sequence[Neighbor], now: float, dt: float,
             look_heading: Optional[float] = None) -> PlannerResult:
        """
        Return the safe velocity and heading for this tick (local ENU).

        ``look_heading`` is where to point the camera while stopped or slow;
        by default the direction of the desired velocity.
        """
        cfg = self._cfg
        speed_wanted = min(math.hypot(desired[0], desired[1]), cfg.max_speed)
        wanted = math.atan2(desired[1], desired[0]) if speed_wanted > 1e-6 else heading
        look = wanted if look_heading is None else look_heading

        if self._anchor is None or self._last_speed <= 0.0:
            self._anchor = (float(position[0]), float(position[1]))
        blocked = obstacle_map.blocked_offsets(position, self.window_radius, now,
                                               cfg.self_clear_radius, self._anchor)
        angles = np.append(self._directions, wanted)
        units = np.column_stack([np.cos(angles), np.sin(angles)])
        free = free_distances(blocked, angles, self._clearance, self._lookahead)
        constraints = separation_constraints(own_id, position, neighbors, cfg.min_separation,
                                             cfg.max_speed, cfg.max_accel, cfg.reaction_time)
        low, separation_high = speed_bounds(units, constraints)
        static_high = braking_speeds(free, cfg.max_accel, cfg.reaction_time)
        high = np.minimum(separation_high, static_high)
        feasible = low <= high + _FEASIBILITY_TOLERANCE
        stop_ok = all(c.limit >= 0.0 for c in constraints)
        if self._view_half_angle is None:
            in_view = np.zeros(angles.shape, dtype=bool)
        else:
            in_view = (np.abs(_wrapped(angles - (heading + self._camera_yaw)))
                       <= self._view_half_angle)
        travel = feasible & in_view

        # Directions are judged by the progress they could make (the speed-up limit only
        # shapes how fast the chosen one is entered, never which one is chosen).
        offset = _wrapped(angles - wanted)
        forward = np.cos(offset) > 0.0
        preferred = np.where(forward, speed_wanted, 0.0)
        speed = np.clip(preferred, low, np.maximum(high, low))
        progress = speed * np.cos(offset)
        score = progress + _RIGHT_BIAS * speed * np.sin(-offset)
        if self._last_direction is not None:
            near = np.abs(_wrapped(angles - self._last_direction)) < _HYSTERESIS_ANGLE
            score = np.where(near & (score > 0.0), score * _HYSTERESIS_BONUS, score)
        score = np.where(travel, score, -math.inf)

        choice: Optional[int] = None
        wanted_index = angles.size - 1
        yielding = speed_wanted > 1e-6 and bool(constraints) and bool(
            separation_high[wanted_index]
            < min(static_high[wanted_index], speed_wanted) - _FEASIBILITY_TOLERANCE)
        if speed_wanted > 1e-6 and travel[wanted_index] \
                and speed[wanted_index] >= speed_wanted - _FEASIBILITY_TOLERANCE:
            choice = wanted_index  # the desired velocity is safe as it is: no detour, no bias
        elif speed_wanted > 1e-6 and travel.any():
            best = int(np.argmax(score))
            if progress[best] >= max(cfg.min_progress_speed, 1e-6):
                choice = best
        if choice is None and not stop_ok and feasible.any():
            # Standing still is unsafe (a drone is closing in): take the gentlest escape,
            # wherever the camera points; a collision is certain, an unseen obstacle is not.
            choice = int(np.argmin(np.where(feasible, low, math.inf)))
            speed[choice] = low[choice]
        if choice is None:
            self._last_direction = None
            self._last_speed = 0.0
            if speed_wanted > 1e-6:
                look = self._where_to_look(position, now, obstacle_map, angles, offset,
                                           speed_wanted, low, separation_high, look)
            return PlannerResult((0.0, 0.0), self._aim(look), float(free[-1]),
                                 speed_wanted > 1e-6, yielding)

        ramp = self._last_speed + cfg.max_accel * max(dt, 0.0)
        s = float(min(speed[choice], max(ramp, low[choice])))  # an escape is never ramped
        direction = float(angles[choice])
        velocity = (s * math.cos(direction), s * math.sin(direction))
        self._last_direction = direction
        self._last_speed = s
        out_heading = self._aim(direction if s >= cfg.yaw_follow_speed else look)
        return PlannerResult(velocity, out_heading, float(free[choice]), False, yielding)

    def _where_to_look(self, position: Vec2, now: float, obstacle_map: ObstacleMap,
                       angles: np.ndarray, offset: np.ndarray, speed_wanted: float,
                       low: np.ndarray, separation_high: np.ndarray, look: float) -> float:
        """
        Return where to point the camera while blocked.

        That is the direction that would make the most progress if the
        unobserved space there turned out to be free (only obstacles already
        seen and other drones count). It is ``look`` when the way toward the
        goal is merely unobserved; when a seen obstacle blocks it, it is the
        most promising way around, so the camera can check that detour
        instead of staring at the obstacle.
        """
        cfg = self._cfg
        seen = obstacle_map.occupied_offsets(position, self.window_radius, now)
        reach = braking_speeds(free_distances(seen, angles, self._clearance, self._lookahead),
                               cfg.max_accel, cfg.reaction_time)
        high = np.minimum(separation_high, reach)
        possible = low <= high + _FEASIBILITY_TOLERANCE
        speed = np.clip(np.where(np.cos(offset) > 0.0, speed_wanted, 0.0), low,
                        np.maximum(high, low))
        progress = np.where(possible, speed * np.cos(offset), -math.inf)
        threshold = max(cfg.min_progress_speed, 1e-6)
        if progress[-1] >= threshold:
            return look  # the way to the goal is only unobserved: look at it
        score = np.where(possible, progress + _RIGHT_BIAS * speed * np.sin(-offset), -math.inf)
        best = int(np.argmax(score))
        return float(angles[best]) if progress[best] >= threshold else look

    def _aim(self, bearing: float) -> float:
        """Return the vehicle heading that points the depth camera along ``bearing``."""
        return wrap_angle(bearing - self._camera_yaw)
