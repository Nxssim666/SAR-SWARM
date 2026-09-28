"""
The WebSocket endpoint ``/api/v1/ws`` (ADR 0013, ADR 0020); messages in ``ws_messages``.

Authentication is the first message, never the URL or a cookie: tokens stay out of
access logs, and a malicious page cannot ride on a browser's credentials (cross-site
WebSocket hijacking). A connection never holds a database session; it opens short ones
to authenticate, re-check the session, and read snapshots.

Telemetry is coalesced per client (latest state per aircraft, at the requested rate).
Alerts, commands and control changes are reliable: if a client cannot keep up, the
connection is closed with 4429 rather than silently skipping events.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from fleet_service.api.ws_messages import (
    CLOSE_BAD_MESSAGE,
    CLOSE_FORBIDDEN,
    CLOSE_TIMEOUT,
    CLOSE_TOO_SLOW,
    CLOSE_UNAUTHENTICATED,
    AlertEvent,
    AlertsSnapshot,
    AlertsSnapshotData,
    AuthMessage,
    ClientMessage,
    CommandEvent,
    CommandsSnapshot,
    CommandsSnapshotData,
    ControlEvent,
    ControlSnapshot,
    ControlSnapshotData,
    ErrorMessage,
    PingMessage,
    PongMessage,
    ServerMessage,
    SessionEndedMessage,
    SubscribeMessage,
    TelemetryBatch,
    TelemetryEvent,
    TelemetrySnapshot,
    Topic,
    UnsubscribeMessage,
    WelcomeMessage,
)
from fleet_service.auth.permissions import Permission, permissions_for
from fleet_service.auth.principal import Principal
from fleet_service.auth.sessions import resolve_session
from fleet_service.bus import (
    ALERTS,
    COMMANDS,
    CONTROL,
    SESSIONS,
    TELEMETRY,
    Event,
    LatestValueSubscription,
    SubscriptionBrokenError,
)
from fleet_service.context import AppContext
from fleet_service.db.models import Command
from fleet_service.services.views import UserRef

router = APIRouter()
log = logging.getLogger(__name__)

AUTH_TIMEOUT_S = 5.0
SESSION_CHECK_S = 10.0
RECENT_COMMANDS = 20
RELIABLE_QUEUE = 1000
_CLIENT = TypeAdapter[Any](ClientMessage)


class _CloseConnectionError(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


async def _authenticate(context: AppContext, token: str) -> Principal | None:
    async with context.database().ops_session() as db:
        resolved = await resolve_session(db, token, context.clock.now(), context.session_policy)
        if resolved is None:
            return None
        session, user = resolved
        await db.commit()
    return Principal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        session_id=session.id,
        session_expires_at=session.expires_at,
    )


class Connection:
    """One authenticated console."""

    def __init__(self, websocket: WebSocket, context: AppContext, principal: Principal, token: str):
        self.ws = websocket
        self.context = context
        self.runtime = context.runtime()
        self.principal = principal
        self._token = token
        self._seq = 0
        self._send_lock = asyncio.Lock()
        self._telemetry: LatestValueSubscription | None = None
        self._telemetry_period = 0.25
        self._topics: set[Topic] = set()
        self._reliable = self.runtime.bus.reliable([SESSIONS], maxsize=RELIABLE_QUEUE)
        self._last_heard = context.clock.now()

    # --- sending -------------------------------------------------------------------------------

    async def send(self, model_type: type[ServerMessage], **fields: Any) -> None:
        """Send a server message with the next sequence number."""
        async with self._send_lock:
            self._seq += 1
            message = model_type(seq=self._seq, ts=self.context.clock.now(), **fields)
            await self.ws.send_text(message.model_dump_json())

    # --- lifecycle -----------------------------------------------------------------------------

    async def run(self) -> None:
        """Serve the connection until the client leaves or it must be closed."""
        self._heard()
        await self.send(
            WelcomeMessage,
            user=UserRef(
                user_id=self.principal.user_id,
                username=self.principal.username,
                display_name=self.principal.display_name,
            ),
            role=self.principal.role,
            permissions=permissions_for(self.principal.role),
            session_expires_at=self.principal.session_expires_at,
            simulation=self.context.settings.simulation,
        )
        tasks = [
            asyncio.create_task(self._read(), name="ws-read"),
            asyncio.create_task(self._forward_reliable(), name="ws-reliable"),
            asyncio.create_task(self._forward_telemetry(), name="ws-telemetry"),
            asyncio.create_task(self._watch_session(), name="ws-session"),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                error = task.exception()
                if isinstance(error, _CloseConnectionError):
                    if error.code == CLOSE_UNAUTHENTICATED:
                        with contextlib.suppress(Exception):
                            await self.send(SessionEndedMessage, reason=error.reason)
                    await self.ws.close(code=error.code, reason=error.reason)
                elif error is not None and not isinstance(error, WebSocketDisconnect):
                    log.error("websocket task failed", exc_info=error)
                    await self.ws.close(code=1011)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._reliable.close()
            if self._telemetry is not None:
                self._telemetry.close()

    def _heard(self) -> None:
        now = self.context.clock.now()
        self._last_heard = now
        self.runtime.presence.touch(self.principal.user_id, now)

    # --- client messages -------------------------------------------------------------------------

    async def _read(self) -> None:
        while True:
            raw = await self.ws.receive_text()
            self._heard()
            try:
                message = _CLIENT.validate_json(raw)
            except ValidationError as exc:
                await self.send(
                    ErrorMessage, code="invalid-message", message=str(exc.errors()[0]["msg"])
                )
                continue
            if isinstance(message, PingMessage):
                await self.send(PongMessage)
            elif isinstance(message, SubscribeMessage):
                await self._subscribe(message)
            elif isinstance(message, UnsubscribeMessage):
                self._unsubscribe(set(message.topics))
            elif isinstance(message, AuthMessage):
                await self.send(
                    ErrorMessage, code="already-authenticated", message="Already authenticated."
                )

    async def _subscribe(self, message: SubscribeMessage) -> None:
        new = [t for t in message.topics if t not in self._topics]
        self._topics |= set(new)
        self._telemetry_period = 1.0 / message.telemetry_hz
        self._rebuild_reliable()
        # Subscribe first, then snapshot: an event in between arrives twice, never zero times.
        if "fleet.telemetry" in new:
            self._telemetry = self.runtime.bus.latest([TELEMETRY])
            await self.send(
                TelemetrySnapshot, data=TelemetryBatch(aircraft=self.runtime.registry.snapshot())
            )
        if "alerts" in new:
            await self.send(
                AlertsSnapshot, data=AlertsSnapshotData(alerts=self.runtime.alerts.open_alerts())
            )
        if "commands" in new:
            async with self.context.database().ops_session() as db:
                rows = (
                    await db.scalars(
                        select(Command).order_by(Command.created_at.desc()).limit(RECENT_COMMANDS)
                    )
                ).all()
                views = [await self.runtime.commands.view(db, row) for row in rows]
            await self.send(CommandsSnapshot, data=CommandsSnapshotData(commands=views))
        if "control" in new:
            await self.send(
                ControlSnapshot, data=ControlSnapshotData(leases=self.runtime.leases.views())
            )

    def _unsubscribe(self, topics: set[Topic]) -> None:
        self._topics -= topics
        if "fleet.telemetry" in topics and self._telemetry is not None:
            self._telemetry.close()
            self._telemetry = None
        self._rebuild_reliable()

    def _rebuild_reliable(self) -> None:
        wanted = {SESSIONS} | {t for t in self._topics if t != "fleet.telemetry"}
        if wanted == set(self._reliable.topics):
            return
        # Keep queued events: move them into the replacement subscription.
        replacement = self.runtime.bus.reliable(wanted, maxsize=RELIABLE_QUEUE)
        while (event := self._reliable.get_nowait()) is not None:
            if event.topic in wanted:
                replacement.offer(event)
        self._reliable.close()
        self._reliable = replacement

    # --- server events -------------------------------------------------------------------------

    async def _forward_reliable(self) -> None:
        while True:
            subscription = self._reliable
            try:
                event = await asyncio.wait_for(subscription.get(), timeout=0.5)
            except TimeoutError:
                continue  # the subscription may have been replaced; look again
            except SubscriptionBrokenError:
                raise _CloseConnectionError(
                    CLOSE_TOO_SLOW, "too slow: reconnect and resync"
                ) from None
            await self._forward(event)

    async def _forward(self, event: Event) -> None:
        if event.topic == SESSIONS:
            data = event.data
            ended = data.get("session_id") == self.principal.session_id or (
                data.get("user_id") == self.principal.user_id
                and data.get("keep_session_id") != self.principal.session_id
            )
            if ended:
                raise _CloseConnectionError(CLOSE_UNAUTHENTICATED, "session revoked")
        elif event.topic == ALERTS:
            await self.send(AlertEvent, data=event.data)
        elif event.topic == COMMANDS:
            await self.send(CommandEvent, data=event.data)
        elif event.topic == CONTROL:
            await self.send(ControlEvent, data=event.data)

    async def _forward_telemetry(self) -> None:
        while True:
            await asyncio.sleep(self._telemetry_period)
            subscription = self._telemetry
            if subscription is None:
                continue
            events = subscription.drain()
            aircraft = [
                view for e in events if (view := self.runtime.registry.live(str(e.key))) is not None
            ]
            if aircraft:
                await self.send(TelemetryEvent, data=TelemetryBatch(aircraft=aircraft))

    async def _watch_session(self) -> None:
        idle_limit = timedelta(seconds=self.context.settings.ws_idle_timeout_s)
        while True:
            await asyncio.sleep(SESSION_CHECK_S)
            if self.context.clock.now() - self._last_heard > idle_limit:
                raise _CloseConnectionError(CLOSE_TIMEOUT, "no message from the client; send pings")
            if await _authenticate(self.context, self._token) is None:
                raise _CloseConnectionError(CLOSE_UNAUTHENTICATED, "session ended")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Live telemetry, alerts, commands and control changes (see ``ws_messages``)."""
    context: AppContext = websocket.app.state.context
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_S)
    except TimeoutError:
        await websocket.close(code=CLOSE_TIMEOUT, reason="authenticate within 5 s")
        return
    except WebSocketDisconnect:
        return
    try:
        message = _CLIENT.validate_json(raw)
    except ValidationError:
        message = None
    if not isinstance(message, AuthMessage):
        await websocket.close(code=CLOSE_BAD_MESSAGE, reason="the first message must be auth")
        return
    principal = await _authenticate(context, message.token)
    if principal is None:
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason="invalid or expired session")
        return
    if not principal.can(Permission.FLEET_VIEW):  # pragma: no cover - every role has it today
        await websocket.close(code=CLOSE_FORBIDDEN, reason="not permitted")
        return
    with contextlib.suppress(WebSocketDisconnect):
        await Connection(websocket, context, principal, message.token).run()
