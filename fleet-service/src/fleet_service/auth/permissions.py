"""
Permission catalogue v1 (ADR 0018). Handlers check permissions, never role names.

Roles are hierarchical: a role has every permission of the roles below it.
"""

from enum import StrEnum

from fleet_service.domain.enums import ROLE_RANK, Role


class Permission(StrEnum):
    """Something a session may be allowed to do."""

    FLEET_VIEW = "fleet.view"
    MISSIONS_PLAN = "missions.plan"
    FLEET_MANAGE = "fleet.manage"
    INCIDENTS_MANAGE = "incidents.manage"
    GEOFENCES_MANAGE = "geofences.manage"
    USERS_VIEW = "users.view"
    AUDIT_READ = "audit.read"
    USERS_MANAGE = "users.manage"


# Operations that need a valid session but no particular permission (logout, me, password).
AUTHENTICATED = "authenticated"
# Operations anyone may call (health, version, login).
PUBLIC = "public"

MINIMUM_ROLE: dict[Permission, Role] = {
    Permission.FLEET_VIEW: Role.OBSERVER,
    Permission.MISSIONS_PLAN: Role.OPERATOR,
    Permission.FLEET_MANAGE: Role.SUPERVISOR,
    Permission.INCIDENTS_MANAGE: Role.SUPERVISOR,
    Permission.GEOFENCES_MANAGE: Role.SUPERVISOR,
    Permission.USERS_VIEW: Role.SUPERVISOR,
    Permission.AUDIT_READ: Role.SUPERVISOR,
    Permission.USERS_MANAGE: Role.ADMIN,
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Return True if ``role`` grants ``permission``."""
    return ROLE_RANK[role] >= ROLE_RANK[MINIMUM_ROLE[permission]]


def permissions_for(role: Role) -> list[Permission]:
    """Return every permission ``role`` grants, in catalogue order."""
    return [p for p in Permission if has_permission(role, p)]
