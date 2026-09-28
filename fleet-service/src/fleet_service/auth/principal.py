"""The authenticated user of a request or WebSocket connection."""

from dataclasses import dataclass
from datetime import datetime

from fleet_service.auth.permissions import Permission, has_permission
from fleet_service.domain.enums import Role


@dataclass(frozen=True)
class Principal:
    """Who is acting, with which role, in which session."""

    user_id: str
    username: str
    display_name: str
    role: Role
    session_id: str
    session_expires_at: datetime

    def can(self, permission: Permission) -> bool:
        """Return True if this principal holds ``permission``."""
        return has_permission(self.role, permission)
