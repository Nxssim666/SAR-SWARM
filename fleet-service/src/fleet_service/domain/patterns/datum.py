"""
Patterns around a datum (the last known position): expanding square and sector search
(IAMSAR; ADR 0028). Both start at the datum, in metres, with bearings in degrees true.
"""

import math

from fleet_service.domain.patterns.frame import bearing_vector

Point = tuple[float, float]


def expanding_square(
    datum: Point, spacing_m: float, extent_m: float, bearing_deg: float
) -> list[Point]:
    """Legs of 1, 1, 2, 2, 3, 3 ... spacings, turning right 90° after each, until the square
    reaches ``extent_m`` from the datum in every direction.

    This is the IAMSAR geometry. Laps are one spacing apart except where one lap steps out
    to the next, which leaves a small pocket (about 0.05 spacing²) at the spiral's corners:
    about 0.06 · spacing / extent of the area, so 0.6 % at an extent of 10 spacings.
    """
    x, y = datum
    points = [datum]
    heading = bearing_deg
    leg = 1
    # The square is complete to (k - 1)·s/2 from the datum after the legs of length k·s:
    # fly until that reaches the extent plus half a spacing.
    last = math.ceil(2.0 * extent_m / spacing_m) + 2
    while leg <= last:
        for _ in range(2):
            dx, dy = bearing_vector(heading)
            x, y = x + dx * leg * spacing_m, y + dy * leg * spacing_m
            points.append((x, y))
            heading = (heading + 90.0) % 360.0
        leg += 1
    return points


def sector_search(
    datum: Point, radius_m: float, bearing_deg: float, second_pass: bool
) -> list[Point]:
    """VS: three equilateral triangles with a corner at the datum, 120° apart; the optional
    second pass is the same rotated 30° (so its legs bisect the first pass's)."""
    points = [datum]
    passes = [bearing_deg] + ([bearing_deg + 30.0] if second_pass else [])
    for start in passes:
        for i in range(3):
            outbound = start + i * 120.0
            for bearing in (outbound, outbound + 60.0):
                dx, dy = bearing_vector(bearing)
                points.append((datum[0] + dx * radius_m, datum[1] + dy * radius_m))
            points.append(datum)
    return points
