"""Terrain grids (ADR 0030): bilinear heights, and unknown stays unknown."""

import json
from pathlib import Path

import numpy as np
import pytest

from fleet_service.domain.terrain import TerrainGrid, TerrainSet

# 3 x 3 cells, 0.01° apart, north-west cell centred at (47.02 N, 8.00 E).
HEIGHTS = np.array([[100, 200, 300], [400, 500, 600], [700, 800, np.nan]], dtype=np.float32)
GRID = TerrainGrid("t", HEIGHTS, lat0=47.02, lon0=8.00, lat_step=0.01, lon_step=0.01)


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (47.02, 8.00, 100.0),  # a cell centre
        (47.02, 8.005, 150.0),  # half-way east
        (47.015, 8.00, 250.0),  # half-way south
        (47.015, 8.005, 300.0),  # the middle of four cells
        (47.00, 8.00, 700.0),  # the south-west corner cell
    ],
)
def test_heights_are_interpolated_bilinearly(lat: float, lon: float, expected: float) -> None:
    assert GRID.elevation_amsl(lat, lon) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (47.03, 8.00),  # north of the grid
        (47.00, 7.99),  # west of it
        (47.005, 8.015),  # next to the unknown cell
    ],
)
def test_outside_the_grid_or_next_to_an_unknown_cell_the_height_is_unknown(
    lat: float, lon: float
) -> None:
    assert GRID.elevation_amsl(lat, lon) is None


def test_the_vectorized_sample_agrees_with_single_points() -> None:
    lats = np.array([47.02, 47.015, 47.03, 47.005])
    lons = np.array([8.00, 8.005, 8.00, 8.015])

    sampled = TerrainSet([GRID]).sample(lats, lons)

    for lat, lon, value in zip(lats, lons, sampled, strict=True):
        single = GRID.elevation_amsl(float(lat), float(lon))
        assert (np.isnan(value) and single is None) or value == pytest.approx(single)


def test_regions_load_from_a_directory_and_bad_files_are_skipped(tmp_path: Path) -> None:
    np.save(tmp_path / "good.npy", HEIGHTS)
    header = {
        "region": "good",
        "rows": 3,
        "cols": 3,
        "lat0": 47.02,
        "lon0": 8.0,
        "lat_step": 0.01,
        "lon_step": 0.01,
    }
    (tmp_path / "good.json").write_text(json.dumps(header))
    (tmp_path / "broken.json").write_text("{not json")
    np.save(tmp_path / "wrong.npy", HEIGHTS)
    (tmp_path / "wrong.json").write_text(json.dumps({**header, "region": "wrong", "rows": 4}))

    terrain = TerrainSet.load(tmp_path)

    assert terrain.regions == ["good"]
    assert terrain.elevation_amsl(47.02, 8.0) == pytest.approx(100.0)
    assert TerrainSet.load(tmp_path / "missing").regions == []
