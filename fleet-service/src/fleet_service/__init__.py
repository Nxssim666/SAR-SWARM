"""Ground fleet service for civilian search-and-rescue drone operations."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fleet-service")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0+unknown"

API_VERSION = "v1"
