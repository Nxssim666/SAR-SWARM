"""Shared fixtures; also makes the package importable when pytest runs from a checkout."""

import pathlib
import sys

import pytest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from swarm_sar.core.config import DroneConfig, SimConfig  # noqa: E402
from swarm_sar.core.geodesy import GeoPoint  # noqa: E402

ORIGIN = GeoPoint(47.397742, 8.545594)  # PX4 SITL default home


def pytest_configure(config):
    """Register the marker for long closed-loop simulations."""
    config.addinivalue_line('markers', 'slow: closed-loop simulation (tens of seconds)')


@pytest.fixture
def drone_config():
    """Return the default drone configuration."""
    return DroneConfig()


@pytest.fixture
def sim_drone_config():
    """Return the drone configuration used with the synthetic camera (full-resolution depth)."""
    return DroneConfig(depth_stride=1)


@pytest.fixture
def sim_config():
    """Return the default simulated world."""
    return SimConfig()
