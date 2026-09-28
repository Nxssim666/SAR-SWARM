"""Tests for swarm_sar.core.geodesy (PX4-compatible local projection)."""

import math

import pytest
from swarm_sar.core.geodesy import EARTH_RADIUS_M, GeoPoint, LocalProjection

ZURICH = GeoPoint(47.397742, 8.545594)


def test_geo_point_validation():
    assert GeoPoint(10, 20).latitude == 10.0
    for lat, lon in ((91.0, 0.0), (0.0, 181.0), (math.nan, 0.0), (True, 0.0), ('1', 0.0)):
        with pytest.raises(ValueError):
            GeoPoint(lat, lon)


def test_projection_matches_px4_reference_values():
    # One arc-degree of latitude on PX4's sphere is R * pi / 180 metres north.
    projection = LocalProjection(GeoPoint(0.0, 0.0))
    east, north = projection.to_local(GeoPoint(1.0, 0.0))
    assert east == pytest.approx(0.0, abs=1e-6)
    assert north == pytest.approx(EARTH_RADIUS_M * math.pi / 180.0, rel=1e-9)
    east, north = projection.to_local(GeoPoint(0.0, 1.0))
    assert east == pytest.approx(EARTH_RADIUS_M * math.pi / 180.0, rel=1e-9)
    assert north == pytest.approx(0.0, abs=1e-6)
    # At 47.4 degrees north, a small longitude step shrinks by cos(latitude).
    east, _ = LocalProjection(ZURICH).to_local(GeoPoint(ZURICH.latitude,
                                                        ZURICH.longitude + 0.001))
    expected = EARTH_RADIUS_M * math.radians(0.001) * math.cos(math.radians(ZURICH.latitude))
    assert east == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize('east, north', [(0.0, 0.0), (100.0, -250.0), (-3000.0, 4000.0),
                                         (0.001, 0.0)])
def test_round_trip_is_exact(east, north):
    projection = LocalProjection(ZURICH)
    back = projection.to_local(projection.to_geo(east, north))
    assert back == pytest.approx((east, north), abs=1e-6)


def test_axes_point_east_and_north():
    projection = LocalProjection(ZURICH)
    east_point = projection.to_geo(50.0, 0.0)
    north_point = projection.to_geo(0.0, 50.0)
    assert east_point.longitude > ZURICH.longitude
    assert east_point.latitude == pytest.approx(ZURICH.latitude, abs=1e-6)
    assert north_point.latitude > ZURICH.latitude


def test_projection_wraps_the_date_line_and_rejects_poles():
    projection = LocalProjection(GeoPoint(0.0, 179.9999))
    across = projection.to_geo(50.0, 0.0)
    assert -180.0 <= across.longitude < -179.9
    assert projection.to_local(across) == pytest.approx((50.0, 0.0), abs=1e-6)
    with pytest.raises(ValueError, match='pole'):
        LocalProjection(GeoPoint(89.0, 0.0))
    with pytest.raises(ValueError):
        LocalProjection(ZURICH).to_geo(math.nan, 0.0)


def test_equality_follows_the_reference():
    assert LocalProjection(ZURICH) == LocalProjection(GeoPoint(47.397742, 8.545594))
    assert LocalProjection(ZURICH) != LocalProjection(GeoPoint(47.0, 8.0))
    assert len({LocalProjection(ZURICH), LocalProjection(ZURICH)}) == 1
