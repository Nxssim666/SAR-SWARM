"""Process-wide collaborators of the application, created by ``create_app``."""

from dataclasses import dataclass
from datetime import timedelta

from fleet_service.auth.passwords import Passwords
from fleet_service.auth.ratelimit import FailureLimiter
from fleet_service.auth.sessions import SessionPolicy
from fleet_service.clock import Clock
from fleet_service.config import Settings
from fleet_service.db.engine import Database


@dataclass
class AppContext:
    """Everything request handlers need besides the request itself."""

    settings: Settings
    clock: Clock
    passwords: Passwords
    session_policy: SessionPolicy
    login_limiter_user: FailureLimiter
    login_limiter_ip: FailureLimiter
    db: Database | None = None  # set by the lifespan after migrations

    @classmethod
    def build(cls, settings: Settings, clock: Clock, passwords: Passwords) -> "AppContext":
        """Create the context from settings."""
        window = timedelta(seconds=settings.login_failure_window_s)
        return cls(
            settings=settings,
            clock=clock,
            passwords=passwords,
            session_policy=SessionPolicy(
                idle_timeout=timedelta(seconds=settings.session_idle_timeout_s),
                max_lifetime=timedelta(seconds=settings.session_max_lifetime_s),
            ),
            login_limiter_user=FailureLimiter(clock, settings.login_max_failures_per_user, window),
            login_limiter_ip=FailureLimiter(clock, settings.login_max_failures_per_ip, window),
        )

    def database(self) -> Database:
        """Return the open database (only valid while the app is running)."""
        if self.db is None:
            raise RuntimeError("the database is not open; is the app's lifespan running?")
        return self.db
