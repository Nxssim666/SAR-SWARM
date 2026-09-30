"""
Fixed-wing turns (ADR 0028).

An airplane cannot reverse onto the next lane if the lanes are closer than its turn
diameter. The lanes are then flown in an order where consecutive lanes are at least
``min_gap`` lanes apart: each pass takes every ``min_gap``-th lane, and the next pass
starts from the far end. Where that is impossible (too few lanes) the turn is counted as
infeasible and the operator is told; PX4 widens such turns itself.
"""

import itertools
import math

GRAVITY = 9.80665


def turn_radius_m(speed_mps: float, max_bank_deg: float) -> float:
    """The radius of a coordinated level turn: v² / (g · tan(bank))."""
    return speed_mps**2 / (GRAVITY * math.tan(math.radians(max_bank_deg)))


def min_lane_gap(spacing_m: float, turn_radius: float) -> int:
    """How many lanes apart consecutive lanes must be for a U-turn of this radius."""
    if turn_radius <= 0.0:
        return 1
    return max(1, math.ceil(2.0 * turn_radius / spacing_m - 1e-9))


def lane_order(count: int, gap: int) -> list[int]:
    """An order visiting ``count`` lanes once, consecutive lanes ``gap`` or more apart if possible.

    Candidates, best kept (fewest tight turns, then least flying across lanes):

    - passes: from the lowest unvisited lane upwards in steps of ``gap``, each next pass
      starting at the lowest unvisited lane far enough from the last one;
    - the same passes over the residues in descending order (0, gap-1, gap-2, ...);
    - halves interleaved: 0, h, 1, h+1, ... with h = ceil(count / 2), always feasible
      once there are 2 · gap + 1 lanes, at the price of long crossings.

    With ``gap`` 1 this is the ordinary lawnmower order.
    """
    if gap <= 1 or count <= 1:
        return list(range(count))
    half = (count + 1) // 2
    halves = [lane for i in range(half) for lane in (i, i + half) if lane < count]
    descending = [lane for r in [0, *range(gap - 1, 0, -1)] for lane in range(r, count, gap)]
    candidates = [_passes(count, gap), descending, halves]

    def cost(order: list[int]) -> tuple[int, int]:
        return infeasible_turns(order, gap), sum(abs(a - b) for a, b in itertools.pairwise(order))

    return min(candidates, key=cost)


def _passes(count: int, gap: int) -> list[int]:
    left = set(range(count))
    order: list[int] = []
    current: int | None = None
    while left:
        candidates = sorted(left)
        if current is not None:
            last = current
            far = [lane for lane in candidates if abs(lane - last) >= gap]
            candidates = far or [max(candidates, key=lambda lane: abs(lane - last))]
        lane = candidates[0]
        while True:
            order.append(lane)
            left.discard(lane)
            current = lane
            nxt = lane + gap
            while nxt < count and nxt not in left:
                nxt += gap
            if nxt >= count:
                break
            lane = nxt
    return order


def infeasible_turns(order: list[int], gap: int) -> int:
    """How many consecutive lane pairs in ``order`` are closer than ``gap``."""
    return sum(1 for a, b in itertools.pairwise(order) if abs(a - b) < gap)
