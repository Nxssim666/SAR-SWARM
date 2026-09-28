"""Tests for swarm_sar.core.coverage."""

import math

import numpy as np
import pytest
from swarm_sar.core.coverage import CoverageMap, grid_geometry, GridGeometry, NEVER_SEEN
from swarm_sar.core.geometry import Bounds

BOUNDS = Bounds(0.0, 0.0, 100.0, 100.0)
TRIANGLE = ((0.0, 0.0), (100.0, 0.0), (0.0, 100.0))


def test_geometry_tiles_exactly_when_divisible():
    g = GridGeometry(Bounds(0.0, 0.0, 300.0, 300.0), 6.0)
    assert g.shape == (50, 50) and g.size == 2500 and g.num_valid == 2500
    assert g.center_of(0, 0) == (3.0, 3.0)


def test_geometry_masks_cells_outside_bounds_and_polygon():
    g = GridGeometry(BOUNDS, 11.0)  # 10 columns, the last centred at 104.5
    assert not g.valid[9, 0] and g.valid[8, 8] and g.num_valid == 81
    tri = GridGeometry(BOUNDS, 10.0, TRIANGLE)
    assert tri.valid[0, 0] and not tri.valid[9, 9]
    assert tri.num_valid == 45  # centres strictly below the diagonal x + y < 100
    with pytest.raises(ValueError, match='finer'):
        GridGeometry(BOUNDS, 10.0, ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))


def test_geometry_equality_includes_the_polygon_and_is_cached():
    g = GridGeometry(BOUNDS, 10.0)
    assert g == GridGeometry(BOUNDS, 10.0) and hash(g) == hash(GridGeometry(BOUNDS, 10.0))
    assert g != GridGeometry(BOUNDS, 10.0, TRIANGLE)
    assert grid_geometry(BOUNDS, 10.0, TRIANGLE) is grid_geometry(BOUNDS, 10.0, TRIANGLE)
    assert g.index_of((-50.0, 1000.0)) == (0, 9)
    with pytest.raises(ValueError):
        g.cx[0, 0] = 1.0


@pytest.mark.parametrize('cell', [0.0, -1.0, math.nan, 0.01])
def test_geometry_rejects_bad_cell_sizes(cell):
    with pytest.raises(ValueError):
        GridGeometry(BOUNDS, cell)


def test_observe_marks_cells_inside_the_footprint_only():
    m = CoverageMap(GridGeometry(BOUNDS, 10.0), revisit_period=10.0)
    m.observe((50.0, 50.0), radius=10.0, t=3.0)
    seen = np.isfinite(m.last_seen)
    assert seen.sum() == 4 and seen[4, 4] and seen[5, 5] and not seen[3, 4]
    tiny = CoverageMap(GridGeometry(BOUNDS, 10.0), revisit_period=10.0)
    tiny.observe((50.0, 50.0), radius=0.1, t=1.0)
    assert np.isfinite(tiny.last_seen).sum() == 1


def test_observe_outside_the_area_marks_nothing():
    # Regression: v1 clamped the drone's own cell into the grid, so a drone in transit far
    # outside the area marked the nearest edge cell as searched.
    m = CoverageMap(GridGeometry(BOUNDS, 10.0), revisit_period=10.0)
    m.observe((-200.0, 50.0), radius=10.0, t=1.0)
    m.observe((105.0, 50.0), radius=2.0, t=1.0)
    assert not np.isfinite(m.last_seen).any()


@pytest.mark.parametrize('position, radius, t', [((math.nan, 0.0), 1.0, 0.0),
                                                 ((0.0, 0.0), -1.0, 0.0),
                                                 ((0.0, 0.0), 1.0, math.inf)])
def test_observe_rejects_invalid_input(position, radius, t):
    m = CoverageMap(GridGeometry(BOUNDS, 10.0), revisit_period=10.0)
    with pytest.raises(ValueError):
        m.observe(position, radius, t)


def test_priority_rises_from_zero_to_one_and_ignores_invalid_cells():
    g = GridGeometry(BOUNDS, 10.0, TRIANGLE)
    m = CoverageMap(g, revisit_period=20.0)
    assert m.priority(0.0)[g.valid].min() == 1.0
    assert m.priority(0.0)[~g.valid].max() == 0.0
    m.observe((5.0, 5.0), radius=1.0, t=0.0)
    assert m.priority(10.0)[0, 0] == pytest.approx(0.5)


def test_sparse_merge_takes_newest_clamps_future_and_handles_duplicates():
    g = GridGeometry(BOUNDS, 10.0)
    m = CoverageMap(g, 10.0)
    m.observe((5.0, 5.0), 1.0, t=2.0)
    cells = np.array([0, 0, 99, 55])
    times = np.array([4.0, 3.0, 500.0, 1.0])
    assert m.merge_cells(cells, times, now=5.0) == 4
    flat = m.last_seen.reshape(-1)
    assert flat[0] == 4.0 and flat[99] == 5.0 and flat[55] == 1.0


def test_sparse_merge_is_idempotent_and_commutative():
    g = GridGeometry(BOUNDS, 10.0)
    rng = np.random.default_rng(1)
    a = (rng.choice(100, 30, replace=False), rng.uniform(0, 10, 30))
    b = (rng.choice(100, 30, replace=False), rng.uniform(0, 10, 30))
    one, two = CoverageMap(g, 10.0), CoverageMap(g, 10.0)
    for cells, times in (a, b, b):
        one.merge_cells(cells, times, 10.0)
    for cells, times in (b, a):
        two.merge_cells(cells, times, 10.0)
    np.testing.assert_array_equal(one.last_seen, two.last_seen)


@pytest.mark.parametrize('cells, times, fragment', [
    (np.array([100]), np.array([1.0]), 'outside'),
    (np.array([-1]), np.array([1.0]), 'outside'),
    (np.array([1]), np.array([math.nan]), 'finite'),
    (np.array([1, 2]), np.array([1.0]), 'same length'),
    (np.array([1.5]), np.array([1.0]), 'integers'),
])
def test_sparse_merge_rejects_bad_updates_whole(cells, times, fragment):
    m = CoverageMap(GridGeometry(BOUNDS, 10.0), 10.0)
    with pytest.raises(ValueError, match=fragment):
        m.merge_cells(cells, times, 1.0)
    assert not np.isfinite(m.last_seen).any()


def test_cells_seen_since_round_trips_through_a_peer():
    g = GridGeometry(BOUNDS, 10.0, TRIANGLE)
    source, sink = CoverageMap(g, 10.0), CoverageMap(g, 10.0)
    source.observe((15.0, 15.0), 12.0, t=1.0)
    source.observe((45.0, 15.0), 12.0, t=6.0)
    recent_cells, recent_times = source.cells_seen_since(5.0)
    assert recent_times.min() >= 5.0 and recent_cells.dtype == np.uint32
    sink.merge_cells(*source.cells_seen_since(-math.inf), now=10.0)
    np.testing.assert_array_equal(np.where(g.valid, source.last_seen, NEVER_SEEN),
                                  np.where(g.valid, sink.last_seen, NEVER_SEEN))


def test_seen_fraction_counts_only_observed_valid_cells():
    m = CoverageMap(GridGeometry(BOUNDS, 10.0), 10.0)
    assert m.seen_fraction(0.0) == 0.0
    m.observe((5.0, 5.0), 1.0, t=0.0)
    m.observe((95.0, 95.0), 1.0, t=50.0)
    assert m.seen_fraction(50.0) == pytest.approx(2 / 100)
    assert m.seen_fraction(50.0, window=10.0) == pytest.approx(1 / 100)
    snap = m.snapshot()
    with pytest.raises(ValueError):
        snap[0, 0] = 1.0
