"""
Relay access control (M6, ADR 0036): only signed-in consoles play video, and only the
streams they asked the fleet service for.

``POST /video-streams/{id}/view`` answers a **ticket**: an HMAC over the relay path, the
viewer and an expiry, signed with a key that lives in the fleet service's memory. The
console sends it as ``Authorization: Bearer <ticket>`` with every WHEP and LL-HLS request.
MediaMTX asks the fleet service about every read and publish (``authMethod: http``), and
``decide`` answers:

* **read** (WebRTC, HLS, RTSP): a valid ticket for exactly this path;
* **publish** (a camera pushing RTSP/SRT): the configured publisher credentials, if any;
* anything else: no.

Tickets survive nothing: a restart of the fleet service invalidates them, and consoles ask
again. A ticket cannot be revoked before it expires (``video_ticket_ttl_s``).
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qs

TICKET_VERSION = "v1"


@dataclass(frozen=True)
class RelayRequest:
    """What MediaMTX asks (its HTTP auth request, the fields used)."""

    action: str
    path: str
    protocol: str
    user: str
    password: str
    token: str
    query: str
    ip: str


class Tickets:
    """Issues and checks viewing tickets."""

    def __init__(self, ttl: timedelta, key: bytes | None = None) -> None:
        self._ttl = ttl
        self._key = key or secrets.token_bytes(32)  # tickets end with the process, by design

    def issue(self, relay_path: str, user_id: str, now: datetime) -> tuple[str, datetime]:
        """A ticket for ``relay_path`` and when it expires."""
        expires = now + self._ttl
        body = f"{TICKET_VERSION}.{_b64(relay_path)}.{_b64(user_id)}.{int(expires.timestamp())}"
        return f"{body}.{self._sign(body)}", expires

    def check(self, ticket: str, relay_path: str, now: datetime) -> str | None:
        """The viewer's user id if ``ticket`` is valid for ``relay_path`` now, else None."""
        try:
            version, path, user, expiry, signature = ticket.split(".")
            body = f"{version}.{path}.{user}.{expiry}"
            if version != TICKET_VERSION or not hmac.compare_digest(signature, self._sign(body)):
                return None
            if _unb64(path) != relay_path or int(expiry) < now.timestamp():
                return None
            return _unb64(user)
        except ValueError:
            return None

    def _sign(self, body: str) -> str:
        digest = hmac.new(self._key, body.encode(), hashlib.sha256).digest()
        return _b64(digest)


@dataclass(frozen=True)
class Publisher:
    """Credentials a camera or aircraft uses to push into the relay (None: pushing refused)."""

    user: str
    password: str


def decide(
    request: RelayRequest, tickets: Tickets, publisher: Publisher | None, now: datetime
) -> tuple[bool, str]:
    """Whether the relay may serve ``request``, and why (for the log)."""
    if request.action in ("read", "playback"):
        ticket = request.token or _query_ticket(request.query)
        if not ticket:
            return False, "no ticket"
        user = tickets.check(ticket, request.path, now)
        if user is None:
            return False, "invalid or expired ticket"
        return True, f"ticket of user {user}"
    if request.action == "publish":
        if publisher is None:
            return False, "publishing is not configured"
        same_user = hmac.compare_digest(request.user.encode(), publisher.user.encode())
        same_password = hmac.compare_digest(request.password.encode(), publisher.password.encode())
        if same_user and same_password:
            return True, "publisher credentials"
        return False, "wrong publisher credentials"
    return False, f"action {request.action!r} is not allowed"


def _query_ticket(query: str) -> str:
    """A ticket passed as ``?ticket=`` (players that cannot set headers)."""
    return parse_qs(query).get("ticket", [""])[0]


def _b64(value: str | bytes) -> str:
    raw = value.encode() if isinstance(value, str) else value
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode()
