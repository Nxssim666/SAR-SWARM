"""Geospatial validation (ADR 0014), including the swapped-coordinate guard."""

import math
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from pydantic import ValidationError

from fleet_service.domain.geo import (
    MAX_POLYGON_VERTICES,
    GeoPoint,
    PolygonGeoJSON,
    distance_m,
    outside_operating_area,
)

from factories import BASE, square

BASE_POINT = GeoPoint(**BASE)


def polygon(ring: list[list[float]]) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [ring]}


def regular_polygon(lat: float, lon: float, radius_deg: float, n: int) -> list[list[float]]:
    ring = [
        [
            lon + radius_deg * math.cos(2 * math.pi * i / n),
            lat + radius_deg * math.sin(2 * math.pi * i / n),
        ]
        for i in range(n)
    ]
    return [*ring, ring[0]]


# --- points --------------------------------------------------------------------------------


def test_point_requires_explicit_keys() -> None:
    with pytest.raises(ValidationError):
        GeoPoint.model_validate([47.3, 8.5])


@pytest.mark.parametrize(
    "value",
    [
        {"latitude": 91.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 181.0},
        {"latitude": math.nan, "longitude": 0.0},
        {"latitude": "47.3", "longitude": 8.5},
        {"latitude": 47.3, "longitude": 8.5, "altitude": 3.0},
    ],
)
def test_point_rejects_invalid_values(value: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        GeoPoint.model_validate(value)


def test_geodesic_distance_of_one_degree_of_latitude() -> None:
    a = GeoPoint(latitude=47.0, longitude=8.0)
    b = GeoPoint(latitude=48.0, longitude=8.0)

    assert distance_m(a, b) == pytest.approx(111_200, rel=0.002)


# --- polygons --------------------------------------------------------------------------------


def test_valid_square_round_trips_and_is_counter_clockwise() -> None:
    area = PolygonGeoJSON.model_validate(square())

    assert area.coordinates == PolygonGeoJSON.model_validate(area.model_dump()).coordinates
    assert len(area.vertices()) == 4


def test_clockwise_ring_is_normalized_to_counter_clockwise() -> None:
    ccw = square()["coordinates"][0]
    cw = list(reversed(ccw))

    area = PolygonGeoJSON.model_validate(polygon(cw))

    # Shoelace sum is positive for a counter-clockwise ring.
    ring = area.coordinates[0]
    signed = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring))
    assert signed > 0


def test_area_of_a_one_kilometre_square() -> None:
    half_lat = 500 / 111_200  # degrees of latitude for 500 m
    half_lon = half_lat / math.cos(math.radians(BASE["latitude"]))
    lat, lon = BASE["latitude"], BASE["longitude"]
    ring = [
        [lon - half_lon, lat - half_lat],
        [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat],
        [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]

    assert PolygonGeoJSON.model_validate(polygon(ring)).area_m2() == pytest.approx(1e6, rel=0.01)


@pytest.mark.parametrize(
    ("ring", "reason"),
    [
        ([[0, 0], [1, 0], [1, 1], [0, 1]], "not closed"),
        ([[0, 0], [1, 0], [0, 0]], "too few positions"),
        ([[0, 0], [1, 0], [1, 0], [0, 0]], "two distinct vertices"),
        ([[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]], "self-intersecting bow tie"),
        ([[0, 0], [1, 1], [2, 2], [0, 0]], "zero area"),
        ([[179, 0], [-179, 0], [-179, 1], [179, 1], [179, 0]], "crosses the antimeridian"),
        ([[0, 0, 5], [1, 0, 5], [1, 1, 5], [0, 0, 5]], "positions with altitude"),
    ],
)
def test_invalid_polygons_are_rejected(ring: list[list[float]], reason: str) -> None:
    with pytest.raises(ValidationError):
        PolygonGeoJSON.model_validate(polygon(ring))


def test_holes_are_rejected() -> None:
    outer = square(half=0.01)["coordinates"][0]
    inner = square(half=0.001)["coordinates"][0]

    with pytest.raises(ValidationError):
        PolygonGeoJSON.model_validate({"type": "Polygon", "coordinates": [outer, inner]})


def test_vertex_limit_matches_the_onboard_protocol() -> None:
    at_limit = regular_polygon(BASE["latitude"], BASE["longitude"], 0.01, MAX_POLYGON_VERTICES)
    over = regular_polygon(BASE["latitude"], BASE["longitude"], 0.01, MAX_POLYGON_VERTICES + 1)

    assert len(PolygonGeoJSON.model_validate(polygon(at_limit)).vertices()) == 256
    with pytest.raises(ValidationError):
        PolygonGeoJSON.model_validate(polygon(over))


# --- operating area, swapped coordinates --------------------------------------------------------

lats = st.floats(min_value=-60.0, max_value=60.0)
lons = st.floats(min_value=-170.0, max_value=170.0)
radii_deg = st.floats(min_value=0.001, max_value=0.1)
sides = st.integers(min_value=3, max_value=24)


@given(lat=lats, lon=lons, r=radii_deg, n=sides)
def test_small_polygons_around_the_base_are_inside_the_operating_area(
    lat: float, lon: float, r: float, n: int
) -> None:
    area = PolygonGeoJSON.model_validate(polygon(regular_polygon(lat, lon, r, n)))
    base = GeoPoint(latitude=lat, longitude=lon)

    assert outside_operating_area(area.vertices(), base, radius_m=25_000) == []


@given(lat=lats, lon=lons, r=radii_deg, n=sides)
def test_swapped_coordinates_never_pass_as_inside(lat: float, lon: float, r: float, n: int) -> None:
    base = GeoPoint(latitude=lat, longitude=lon)
    swapped_centre_is_far = abs(lat - lon) > 1.0  # otherwise the swap moves the area < ~100 km
    assume(swapped_centre_is_far)
    ring = regular_polygon(lat, lon, r, n)
    swapped = [[y, x] for x, y in ring]  # [lat, lon] sent where GeoJSON wants [lon, lat]

    try:
        area = PolygonGeoJSON.model_validate(polygon(swapped))
    except ValidationError:
        return  # structurally impossible (e.g. latitude beyond 90): rejected either way
    assert outside_operating_area(area.vertices(), base, radius_m=25_000) != []
