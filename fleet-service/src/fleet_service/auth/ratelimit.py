"""Sliding-window limiter for failed logins (in memory: a restart resets it; acceptable)."""

import math
from collections import deque
from datetime import timedelta

from fleet_service.clock import Clock


class FailureLimiter:
    """Allow at most ``max_failures`` failures per key within ``window``."""

    def __init__(self, clock: Clock, max_failures: int, window: timedelta) -> None:
        self._clock = clock
        self._max = max_failures
        self._window = window
        self._failures: dict[str, deque[float]] = {}

    def retry_after_s(self, key: str) -> int | None:
        """Return seconds until ``key`` may try again, or None if it may try now."""
        failures = self._prune(key)
        if len(failures) < self._max:
            return None
        oldest = failures[0]
        wait = oldest + self._window.total_seconds() - self._clock.now().timestamp()
        return max(1, math.ceil(wait))

    def record_failure(self, key: str) -> None:
        """Count one failure for ``key``."""
        self._prune(key).append(self._clock.now().timestamp())

    def reset(self, key: str) -> None:
        """Forget ``key``'s failures (after a successful login)."""
        self._failures.pop(key, None)

    def _prune(self, key: str) -> deque[float]:
        cutoff = self._clock.now().timestamp() - self._window.total_seconds()
        failures = self._failures.setdefault(key, deque())
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures
