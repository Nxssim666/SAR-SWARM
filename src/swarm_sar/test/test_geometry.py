"""Tests for swarm_sar.core.geometry."""

import math

import numpy as np
import pytest
from swarm_sar.core.geometry import (as_vec2, as_vec3, Bounds, clip_polygon_halfplane, distance,
                                     id_direction, normalize_polygon, point_in_polygon,
                                     points_in_polygon, polygon_area_centroid, saturate,
                                     segments_intersect, signed_area, tie_break_direction,
                                     voronoi_cell, wrap_angle)

BOUNDS = Bounds(0.0, 0.0, 100.0, 100.0)
SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


@pytest.mark.parametrize('bad', [(1.0,), (1.0, 2.0, 3.0), ('a', 1.0), (math.nan, 0.0),
                                 (0.0, math.inf), None, 5.0, 'ab'])
def test_as_vec2_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        as_vec2(bad)


def test_as_vec_accepts_numpy_and_lists():
    assert as_vec2(np.array([1, 2])) == (1.0, 2.0)
    assert as_vec3([3, 4, 5]) == (3.0, 4.0, 5.0)
    with pytest.raises(ValueError):
        as_vec3((1.0, 2.0))


def test_saturate_never_scales_up():
    assert saturate((3.0, 4.0), 10.0) == (3.0, 4.0)
    x, y = saturate((30.0, 40.0), 5.0)
    assert math.isclose(math.hypot(x, y), 5.0)
    assert saturate((0.0, 0.0), 0.0) == (0.0, 0.0)


@pytest.mark.parametrize('angle, expected', [(0.0, 0.0), (math.pi, math.pi), (-math.pi, math.pi),
                                             (3 * math.pi, math.pi), (-0.5, -0.5),
                                             (2 * math.pi + 0.25, 0.25)])
def test_wrap_angle(angle, expected):
    assert wrap_angle(angle) == pytest.approx(expected)


def test_tie_break_is_antisymmetric_unit_and_needs_distinct_ids():
    a = tie_break_direction(3, 8)
    b = tie_break_direction(8, 3)
    assert math.isclose(math.hypot(*a), 1.0)
    assert a == pytest.approx((-b[0], -b[1]))
    with pytest.raises(ValueError):
        tie_break_direction(2, 2)
    assert math.isclose(math.hypot(*id_direction(5)), 1.0)


@pytest.mark.parametrize('args', [(0, 0, 0, 1), (0, 0, 1, 0), (0, 0, math.nan, 1),
                                  (0, 0, True, 1), (0, 0, '1', 1)])
def test_bounds_validation(args):
    with pytest.raises(ValueError):
        Bounds(*args)


def test_bounds_helpers():
    assert Bounds.from_sequence([0, 1, 2, 3]).as_tuple() == (0.0, 1.0, 2.0, 3.0)
    with pytest.raises(ValueError):
        Bounds.from_sequence([0, 1, 2])
    assert Bounds.around([(1.0, 5.0), (-2.0, 3.0), (4.0, 9.0)]).as_tuple() == (-2, 3, 4, 9)
    with pytest.raises(ValueError):
        Bounds.around([])
    assert BOUNDS.clamp((-5.0, 150.0)) == (0.0, 100.0)
    assert BOUNDS.contains((100.0, 0.0))
    assert not BOUNDS.contains((100.5, 0.0))
    assert BOUNDS.contains((100.5, 0.0), margin=1.0)


def test_clip_keeps_inside_drops_outside():
    assert clip_polygon_halfplane(SQUARE, (20.0, 0.0), (1.0, 0.0)) == SQUARE
    assert clip_polygon_halfplane(SQUARE, (-1.0, 0.0), (1.0, 0.0)) == []
    half = clip_polygon_halfplane(SQUARE, (5.0, 0.0), (7.0, 0.0))
    (cx, _), area = polygon_area_centroid(half)
    assert math.isclose(area, 50.0) and math.isclose(cx, 2.5)


def test_voronoi_cells_tile_the_bounds():
    rng = np.random.default_rng(0)
    points = [tuple(p) for p in rng.uniform(0.0, 100.0, size=(15, 2))]
    total = 0.0
    for i, p in enumerate(points):
        others = [q for j, q in enumerate(points) if j != i]
        cell = voronoi_cell(p, others, BOUNDS)
        total += polygon_area_centroid(cell)[1]
        for vertex in cell:
            assert all(distance(vertex, p) <= distance(vertex, q) + 1e-6 for q in others)
    assert math.isclose(total, 100.0 * 100.0, rel_tol=1e-9)
    assert math.isclose(polygon_area_centroid(voronoi_cell((5, 5), [(5, 5)], BOUNDS))[1], 1e4)


def test_polygon_area_and_containment():
    assert signed_area(SQUARE) == 100.0
    assert signed_area(SQUARE[::-1]) == -100.0
    assert point_in_polygon((5.0, 5.0), SQUARE)
    assert not point_in_polygon((15.0, 5.0), SQUARE)
    l_shape = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
    xs, ys = np.meshgrid(np.arange(0.5, 10.0, 1.0), np.arange(0.5, 10.0, 1.0))
    inside = points_in_polygon(xs, ys, l_shape)
    assert inside.sum() == 10 * 4 + 6 * 4  # bottom strip plus left column
    assert not point_in_polygon((7.0, 7.0), l_shape)
    with pytest.raises(ValueError):
        polygon_area_centroid([])


def test_segments_intersect_including_touching_and_collinear_overlap():
    assert segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))
    assert not segments_intersect((0, 0), (1, 1), (2, 2), (3, 0))
    assert segments_intersect((0, 0), (10, 0), (10, 0), (10, 5))   # touching end point
    assert segments_intersect((0, 0), (10, 0), (5, 0), (15, 0))    # collinear overlap
    assert not segments_intersect((0, 0), (10, 0), (11, 0), (15, 0))


def test_normalize_polygon_accepts_closed_rings_and_orients_ccw():
    closed_cw = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
    result = normalize_polygon(closed_cw)
    assert len(result) == 4 and signed_area(result) > 0
    assert normalize_polygon([(0, 0), (0, 0), (10, 0), (10, 10)])[:2] == ((0, 0), (10, 0))


@pytest.mark.parametrize('vertices, fragment', [
    ([(0, 0), (1, 1)], 'at least 3'),
    ([(0, 0), (10, 10), (10, 0), (0, 10)], 'intersect'),       # bow tie
    ([(0, 0), (1, 0), (2, 0)], 'area'),                          # collinear
    ([(0, 0), (1, 0), (0, 1)], 'minimum'),                       # below min_area 25
    ([(0, 0), (math.nan, 0), (0, 10)], 'finite'),
])
def test_normalize_polygon_rejects_unusable_input(vertices, fragment):
    with pytest.raises(ValueError, match=fragment):
        normalize_polygon(vertices, min_area=25.0)
