"""Time source. Injected everywhere so tests control expiry, rate limits and timestamps."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Anything that tells the current UTC time."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)
