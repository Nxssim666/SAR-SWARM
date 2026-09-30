"""
Bulk goto (ADR 0029): several aircraft to one datum, each to its own point.

Points lie on a hexagonal lattice around the datum, ``spacing_m`` apart (the datum
itself first, then ring after ring), so no two aircraft share a target. Aircraft are
matched to points shortest-pair first, which keeps their paths from crossing where it
can; aircraft whose position is unknown take the points left over. The caller layers
their altitudes and checks the flights in 4D (``deconfliction``).
"""

import math
from collections.abc import Mapping

from fleet_service.domain.patterns.frame import LocalFrame

LatLon = tuple[float, float]


def lattice(count: int, spacing_m: float) -> list[tuple[float, float]]:
    """``count`` hexagonal-lattice offsets (metres), nearest to the origin first."""
    points = [(0.0, 0.0)]
    ring = 1
    while len(points) < count:
        corners = [
            (
                ring * spacing_m * math.cos(math.radians(60 * k)),
                ring * spacing_m * math.sin(math.radians(60 * k)),
            )
            for k in range(6)
        ]
        for k in range(6):
            a, b = corners[k], corners[(k + 1) % 6]
            for step in range(ring):  # ``ring`` points per side, the corner first
                f = step / ring
                points.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        ring += 1
    return points[:count]


def spread_targets(
    datum: LatLon, starts: Mapping[str, LatLon | None], spacing_m: float
) -> dict[str, LatLon]:
    """Each aircraft's own point near ``datum``: (latitude, longitude) per aircraft id."""
    frame = LocalFrame(*datum)
    cx, cy = frame.xy(datum[1], datum[0])
    offsets = lattice(len(starts), spacing_m)
    free = {i: (cx + dx, cy + dy) for i, (dx, dy) in enumerate(offsets)}
    known = {a: frame.xy(p[1], p[0]) for a, p in starts.items() if p is not None}
    pairs = sorted(
        (math.dist(position, point), aircraft, i)
        for aircraft, position in known.items()
        for i, point in free.items()
    )
    chosen: dict[str, tuple[float, float]] = {}
    for _, aircraft, i in pairs:
        if aircraft in chosen or i not in free:
            continue
        chosen[aircraft] = free.pop(i)
    for aircraft in starts:  # unknown positions: what is left, nearest to the datum first
        if aircraft not in chosen:
            chosen[aircraft] = free.pop(min(free))
    result = {}
    for aircraft, (x, y) in chosen.items():
        lon, lat = frame.lonlat(x, y)
        result[aircraft] = (round(lat, 7), round(lon, 7))
    return result
