"""
Control leases (ADR 0011, ADR 0020): at most one controlling operator per aircraft.

* Take control of an unassigned aircraft; release it.
* Handover: another operator asks, the holder accepts or declines. A request that is not
  answered within the timeout expires. Control never moves without the holder's answer,
  except when a supervisor assigns or forces it, which needs a reason and is audited.
* Presence: an in-memory record of when each user was last seen (any authenticated
  request, any WebSocket message). A holder unseen for the grace period makes the lease
  *orphaned*: supervisors are alerted, the aircraft keeps doing what it was doing, and
  nothing is ever commanded because someone went away. The lease is *held* again as soon
  as the holder is back.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.auth.permissions import Permission, has_permission
from fleet_service.auth.principal import Principal
from fleet_service.bus import CONTROL, EventBus
from fleet_service.db.models import ControlLease, User
from fleet_service.domain.enums import LeaseState
from fleet_service.errors import Conflict, Forbidden, InvalidRequest
from fleet_service.services import audit
from fleet_service.services.audit import Actor
from fleet_service.services.views import ControlChange, HandoverRequestView, LeaseView, UserRef


@dataclass
class Presence:
    """When each user was last seen by this ground station."""

    _seen: dict[str, datetime] = field(default_factory=dict)

    def touch(self, user_id: str, now: datetime) -> None:
        """Record that ``user_id`` is here."""
        self._seen[user_id] = now

    def last_seen(self, user_id: str) -> datetime | None:
        """When ``user_id`` was last seen, if ever since startup."""
        return self._seen.get(user_id)


@dataclass
class _Lease:
    aircraft_id: str
    holder: UserRef
    state: LeaseState
    acquired_at: datetime
    requested_by: UserRef | None = None
    requested_at: datetime | None = None


def _ref(user: User) -> UserRef:
    return UserRef(user_id=user.id, username=user.username, display_name=user.display_name)


class LeaseService:
    """Owns the control leases; the database row mirrors the in-memory lease."""

    def __init__(
        self,
        bus: EventBus,
        presence: Presence,
        handover_timeout: timedelta,
        grace: timedelta,
    ) -> None:
        self._bus = bus
        self.presence = presence
        self._handover_timeout = handover_timeout
        self._grace = grace
        self._leases: dict[str, _Lease] = {}
        self._started_at: datetime | None = None

    async def load(self, db: AsyncSession, now: datetime) -> None:
        """Load leases at startup. Holders get a full grace period to reconnect."""
        self._started_at = now
        users = {u.id: u for u in (await db.scalars(select(User))).all()}
        for row in (await db.scalars(select(ControlLease))).all():
            holder = users[row.holder_user_id]
            requester = users.get(row.pending_request_by or "")
            self._leases[row.aircraft_id] = _Lease(
                aircraft_id=row.aircraft_id,
                holder=_ref(holder),
                state=row.state,
                acquired_at=row.acquired_at,
                requested_by=_ref(requester) if requester else None,
                requested_at=row.pending_request_at,
            )

    # --- queries -------------------------------------------------------------------------------

    def holder_id(self, aircraft_id: str) -> str | None:
        """Who controls the aircraft, if anyone."""
        lease = self._leases.get(aircraft_id)
        return lease.holder.user_id if lease else None

    def view(self, aircraft_id: str) -> LeaseView | None:
        """The lease of an aircraft, if any."""
        lease = self._leases.get(aircraft_id)
        if lease is None:
            return None
        request = None
        if lease.requested_by is not None and lease.requested_at is not None:
            request = HandoverRequestView(
                requested_by=lease.requested_by,
                requested_at=lease.requested_at,
                expires_at=lease.requested_at + self._handover_timeout,
            )
        return LeaseView(
            aircraft_id=lease.aircraft_id,
            holder=lease.holder,
            state=lease.state,
            acquired_at=lease.acquired_at,
            pending_request=request,
        )

    def views(self) -> list[LeaseView]:
        """Every lease."""
        return [v for aircraft_id in self._leases if (v := self.view(aircraft_id))]

    def orphaned(self) -> list[str]:
        """Aircraft whose controller is gone."""
        return [a for a, lease in self._leases.items() if lease.state is LeaseState.ORPHANED]

    def forget(self, aircraft_id: str) -> None:
        """Drop the lease of a deleted aircraft (its row went with the aircraft)."""
        self._leases.pop(aircraft_id, None)

    # --- changes ---------------------------------------------------------------------------------

    async def take(
        self, db: AsyncSession, now: datetime, principal: Principal, aircraft_id: str, actor: Actor
    ) -> LeaseView:
        """Take control of an aircraft nobody controls (no-op if already yours)."""
        lease = self._leases.get(aircraft_id)
        if lease is not None:
            if lease.holder.user_id == principal.user_id:
                return self._require_view(aircraft_id)
            raise Conflict(
                f"{lease.holder.display_name} controls this aircraft; request a handover.",
                slug="control-held",
                extensions={"holder": lease.holder.model_dump()},
            )
        holder = UserRef(
            user_id=principal.user_id,
            username=principal.username,
            display_name=principal.display_name,
        )
        await self._set_holder(db, now, aircraft_id, holder, actor, "control.take", {})
        return self._require_view(aircraft_id)

    async def release(
        self, db: AsyncSession, now: datetime, principal: Principal, aircraft_id: str, actor: Actor
    ) -> None:
        """Give up control (holder only)."""
        lease = self._leases.get(aircraft_id)
        if lease is None or lease.holder.user_id != principal.user_id:
            raise Conflict("You do not control this aircraft.", slug="not-controller")
        await self._clear(db, now, aircraft_id, actor, "control.release", {})

    async def request_handover(
        self, db: AsyncSession, now: datetime, principal: Principal, aircraft_id: str, actor: Actor
    ) -> LeaseView:
        """Ask the current controller to hand the aircraft over."""
        lease = self._leases.get(aircraft_id)
        if lease is None:
            raise Conflict(
                "Nobody controls this aircraft; take control instead.", slug="no-controller"
            )
        if lease.holder.user_id == principal.user_id:
            raise Conflict("You already control this aircraft.", slug="already-controller")
        if lease.requested_by is not None:
            raise Conflict(
                f"{lease.requested_by.display_name} already asked for this aircraft.",
                slug="handover-pending",
            )
        lease.requested_by = UserRef(
            user_id=principal.user_id,
            username=principal.username,
            display_name=principal.display_name,
        )
        lease.requested_at = now
        await self._persist(db, lease)
        await self._audit_publish(db, now, actor, "control.handover_request", aircraft_id, {})
        return self._require_view(aircraft_id)

    async def answer_handover(
        self,
        db: AsyncSession,
        now: datetime,
        principal: Principal,
        aircraft_id: str,
        accept: bool,
        actor: Actor,
    ) -> LeaseView | None:
        """The controller accepts (control moves) or declines (it stays)."""
        lease = self._leases.get(aircraft_id)
        if lease is None or lease.holder.user_id != principal.user_id:
            raise Conflict("You do not control this aircraft.", slug="not-controller")
        requester = lease.requested_by
        if requester is None:
            raise Conflict("There is no pending handover request.", slug="no-handover-request")
        if not accept:
            lease.requested_by, lease.requested_at = None, None
            await self._persist(db, lease)
            await self._audit_publish(
                db,
                now,
                actor,
                "control.handover_decline",
                aircraft_id,
                {"requested_by": requester.user_id},
            )
            return self._require_view(aircraft_id)
        await self._set_holder(
            db,
            now,
            aircraft_id,
            requester,
            actor,
            "control.handover_accept",
            {"from": principal.user_id, "to": requester.user_id},
        )
        return self._require_view(aircraft_id)

    async def assign(
        self,
        db: AsyncSession,
        now: datetime,
        aircraft_id: str,
        user_id: str | None,
        reason: str,
        actor: Actor,
    ) -> LeaseView | None:
        """Supervisor: give control to ``user_id`` (or nobody), overriding any holder."""
        previous = self.holder_id(aircraft_id)
        details = {"reason": reason, "previous_holder": previous}
        if user_id is None:
            if aircraft_id in self._leases:
                await self._clear(db, now, aircraft_id, actor, "control.assign", details)
            return None
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            raise InvalidRequest(
                f"User {user_id} does not exist or is inactive.", slug="unknown-reference"
            )
        if not has_permission(user.role, Permission.AIRCRAFT_COMMAND):
            raise Forbidden(f"{user.display_name}'s role cannot command aircraft.")
        await self._set_holder(
            db, now, aircraft_id, _ref(user), actor, "control.assign", {**details, "to": user_id}
        )
        return self._require_view(aircraft_id)

    async def evaluate(self, db: AsyncSession, now: datetime) -> None:
        """Expire unanswered handover requests; orphan leases of absent holders, and back."""
        for lease in list(self._leases.values()):
            if (
                lease.requested_at is not None
                and now >= lease.requested_at + self._handover_timeout
            ):
                requester = lease.requested_by
                lease.requested_by, lease.requested_at = None, None
                await self._persist(db, lease)
                await self._audit_publish(
                    db,
                    now,
                    audit.Actor(None, "system:control"),
                    "control.handover_expire",
                    lease.aircraft_id,
                    {"requested_by": requester.user_id if requester else None},
                )
            seen = self.presence.last_seen(lease.holder.user_id) or self._started_at
            present = seen is not None and now - seen < self._grace
            state = LeaseState.HELD if present else LeaseState.ORPHANED
            if state is not lease.state:
                lease.state = state
                await self._persist(db, lease)
                action = "control.orphan" if state is LeaseState.ORPHANED else "control.restore"
                await self._audit_publish(
                    db, now, audit.Actor(None, "system:control"), action, lease.aircraft_id, {}
                )
        await db.commit()

    # --- internals -------------------------------------------------------------------------------

    def _require_view(self, aircraft_id: str) -> LeaseView:
        view = self.view(aircraft_id)
        if view is None:  # pragma: no cover - callers just created the lease
            raise RuntimeError(f"no lease for {aircraft_id}")
        return view

    async def _set_holder(
        self,
        db: AsyncSession,
        now: datetime,
        aircraft_id: str,
        holder: UserRef,
        actor: Actor,
        action: str,
        details: Mapping[str, object],
    ) -> None:
        lease = _Lease(
            aircraft_id=aircraft_id, holder=holder, state=LeaseState.HELD, acquired_at=now
        )
        self._leases[aircraft_id] = lease
        self.presence.touch(holder.user_id, now)  # a new holder gets a full grace period
        await self._persist(db, lease)
        await self._audit_publish(
            db, now, actor, action, aircraft_id, {**details, "holder": holder.user_id}
        )

    async def _clear(
        self,
        db: AsyncSession,
        now: datetime,
        aircraft_id: str,
        actor: Actor,
        action: str,
        details: Mapping[str, object],
    ) -> None:
        self._leases.pop(aircraft_id, None)
        await db.execute(delete(ControlLease).where(ControlLease.aircraft_id == aircraft_id))
        await self._audit_publish(db, now, actor, action, aircraft_id, {**details, "holder": None})

    async def _persist(self, db: AsyncSession, lease: _Lease) -> None:
        await db.merge(
            ControlLease(
                aircraft_id=lease.aircraft_id,
                holder_user_id=lease.holder.user_id,
                state=lease.state,
                acquired_at=lease.acquired_at,
                holder_seen_at=self.presence.last_seen(lease.holder.user_id) or lease.acquired_at,
                pending_request_by=lease.requested_by.user_id if lease.requested_by else None,
                pending_request_at=lease.requested_at,
            )
        )

    async def _audit_publish(
        self,
        db: AsyncSession,
        now: datetime,
        actor: Actor,
        action: str,
        aircraft_id: str,
        details: Mapping[str, object],
    ) -> None:
        await audit.record(
            db, actor, now, action, entity_type="aircraft", entity_id=aircraft_id, details=details
        )
        change = ControlChange(aircraft_id=aircraft_id, change=action, lease=self.view(aircraft_id))
        self._bus.publish(CONTROL, change, key=aircraft_id)
