"""
Video stream configuration (ADR 0012). Source URLs may carry camera credentials; they
are stored but never returned or audited: responses show the password as ``***``.

M5: each stream's health as the relay reports it (``/video-health``: not under
``/video-streams/``, where it would read as a stream id), and
``POST /video-streams/{id}/view``, which a console calls before playing a stream: it
answers where to play it (WHEP, and LL-HLS as the fallback) and audits the viewing.

M6: the answer carries a viewing ticket, and the relay asks ``/internal/video-auth`` about
every request (ADR 0036), so only signed-in consoles play.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from fleet_service.api.common import (
    EntityId,
    InputModel,
    Name,
    OutputModel,
    PageParams,
    PatchModel,
    StrictBool,
    apply_values,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import commit_or_conflict, get_or_404, get_reference
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Aircraft, VideoStream
from fleet_service.domain.enums import VideoCodec
from fleet_service.errors import Conflict, Forbidden, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit
from fleet_service.services.video import StreamState
from fleet_service.services.video_access import RelayRequest, decide

router = APIRouter(
    prefix="/video-streams",
    tags=["video streams"],
    responses=problem_responses(400, 401, 403, 404, 409, 422),
)

# Streams' health at the relay, beside the collection rather than inside it.
health_router = APIRouter(tags=["video streams"], responses=problem_responses(401, 403))
# Service-to-service (the relay's auth hook), outside the public API and its contract.
internal_router = APIRouter()
log = logging.getLogger(__name__)

REDACTED = "***"


def _split_password(url: str) -> tuple[str, str, str | None, str]:
    """Split ``scheme://user:password@rest`` into (scheme://, user, password, @rest)."""
    scheme, sep, rest = url.partition("://")
    authority_end = len(rest)
    for stop in "/?#":
        index = rest.find(stop)
        if index != -1:
            authority_end = min(authority_end, index)
    authority, tail = rest[:authority_end], rest[authority_end:]
    if "@" not in authority:
        return scheme + sep, "", None, rest
    userinfo, host = authority.rsplit("@", 1)
    user, colon, password = userinfo.partition(":")
    return scheme + sep, user, password if colon else None, "@" + host + tail


def redact_url(url: str) -> str:
    """Replace the password in a URL's userinfo with ``***``."""
    prefix, user, password, rest = _split_password(url)
    if password is None:
        return url
    return f"{prefix}{user}:{REDACTED}{rest}"


def _reject_redacted(url: str) -> str:
    if _split_password(url)[2] == REDACTED:
        raise ValueError(
            "the URL contains the redaction marker *** as password; send the real password "
            "or omit source_url to keep the stored one"
        )
    return url


SourceUrl = Annotated[
    str,
    StringConstraints(max_length=500, pattern=r"^(rtsp|rtsps|srt|udp|rtp)://\S+$"),
    AfterValidator(_reject_redacted),
]
RelayPath = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class VideoStreamOut(OutputModel):
    """A video source; the source URL's password is redacted."""

    id: str
    aircraft_id: str | None
    name: str
    source_url: str
    relay_path: str
    codec: VideoCodec
    enabled: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, stream: VideoStream) -> "VideoStreamOut":
        """Build from a row, redacting credentials."""
        out = cls.model_validate(stream)
        return out.model_copy(update={"source_url": redact_url(stream.source_url)})


class VideoStreamPage(Page[VideoStreamOut]):
    """A page of video streams."""


class VideoStreamCreate(InputModel):
    """A new video source. ``relay_path`` is its path on the video relay."""

    aircraft_id: EntityId | None = None
    name: Name
    source_url: SourceUrl
    relay_path: RelayPath
    codec: VideoCodec = VideoCodec.H264
    enabled: StrictBool = True


class VideoStreamUpdate(PatchModel):
    """Fields to change."""

    aircraft_id: EntityId | None = optional()
    name: Name = optional()
    source_url: SourceUrl = optional()
    relay_path: RelayPath = optional()
    codec: VideoCodec = optional()
    enabled: StrictBool = optional()


def _snapshot(stream: VideoStream) -> dict[str, object]:
    return VideoStreamOut.of(stream).model_dump(mode="json")


async def _ensure_path_free(db: DbSession, relay_path: str, exclude_id: str) -> None:
    if await db.scalar(
        select(VideoStream.id).where(
            VideoStream.relay_path == relay_path, VideoStream.id != exclude_id
        )
    ):
        raise Conflict(f"Relay path {relay_path!r} is in use.", slug="relay-path-taken")


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_video_streams(
    db: DbSession, page: Annotated[PageParams, Depends(page_params)]
) -> VideoStreamPage:
    """List video sources."""
    rows, cursor = await fetch_page(db, select(VideoStream), VideoStream.id, page)
    return VideoStreamPage(items=[VideoStreamOut.of(s) for s in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.FLEET_MANAGE))
async def create_video_stream(
    body: VideoStreamCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> VideoStreamOut:
    """Register a video source."""
    if body.aircraft_id is not None:
        await get_reference(db, Aircraft, body.aircraft_id, "aircraft_id")
    await _ensure_path_free(db, body.relay_path, "")
    now = context.clock.now()
    stream = VideoStream(id=new_id(), **body.model_dump(), created_at=now, updated_at=now)
    db.add(stream)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "video_stream.create",
        entity_type="video_stream",
        entity_id=stream.id,
        details={"after": _snapshot(stream)},
    )
    await commit_or_conflict(db, f"Relay path {body.relay_path!r} is in use.")
    return VideoStreamOut.of(stream)


class StreamHealthOut(OutputModel):
    """How a stream is doing at the relay; ``unknown`` when the relay cannot be asked."""

    stream_id: str
    relay_path: str
    state: StreamState
    since: AwareDatetime | None
    readers: int | None
    bitrate_kbps: float | None
    checked_at: AwareDatetime | None


class StreamHealthList(OutputModel):
    """Every registered stream's health; ``monitored`` is false without a relay API."""

    monitored: bool
    streams: list[StreamHealthOut]


@health_router.get("/video-health", **requires(Permission.FLEET_VIEW))
async def video_health(db: DbSession, context: Context) -> StreamHealthList:
    """Each stream's state at the relay: live, stalled, offline or unknown."""
    rows = (await db.scalars(select(VideoStream).order_by(VideoStream.name))).all()
    monitor = context.runtime().video
    streams = []
    for row in rows:
        health = monitor.health(row.id) if monitor is not None else None
        streams.append(
            StreamHealthOut(
                stream_id=row.id,
                relay_path=row.relay_path,
                state=health.state if health else StreamState.UNKNOWN,
                since=health.since if health else None,
                readers=health.readers if health else None,
                bitrate_kbps=health.bitrate_kbps if health else None,
                checked_at=health.checked_at if health else None,
            )
        )
    return StreamHealthList(monitored=monitor is not None, streams=streams)


class ViewTicket(OutputModel):
    """Where a console plays a stream: WHEP (WebRTC) first, LL-HLS if WebRTC fails."""

    stream_id: str
    name: str
    whep_url: str
    hls_url: str
    ticket: str = Field(
        description="Send as `Authorization: Bearer <ticket>` with every WHEP and HLS request; "
        "the relay asks the fleet service (M6, ADR 0036)."
    )
    expires_at: AwareDatetime = Field(description="Ask again after this.")


@router.post("/{stream_id}/view", **requires(Permission.FLEET_VIEW))
async def view_video_stream(
    stream_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> ViewTicket:
    """Start viewing a stream: its playback URLs; the viewing is audited (ADR 0012)."""
    stream = await get_or_404(db, VideoStream, stream_id, "Video stream")
    if not stream.enabled:
        raise Conflict(f"Video stream {stream.name} is disabled.", slug="stream-disabled")
    await audit.record(
        db,
        actor(request, principal),
        context.clock.now(),
        "video.view",
        entity_type="video_stream",
        entity_id=stream.id,
        details={"relay_path": stream.relay_path, "aircraft_id": stream.aircraft_id},
    )
    await db.commit()
    base = context.settings.video_base_path.rstrip("/")
    ticket, expires = context.runtime().video_tickets.issue(
        stream.relay_path, principal.user_id, context.clock.now()
    )
    return ViewTicket(
        stream_id=stream.id,
        name=stream.name,
        whep_url=f"{base}/webrtc/{stream.relay_path}/whep",
        hls_url=f"{base}/hls/{stream.relay_path}/index.m3u8",
        ticket=ticket,
        expires_at=expires,
    )


class RelayAuthRequest(BaseModel):
    """MediaMTX's HTTP auth request (its schema, not ours: unknown fields are ignored so a
    relay upgrade that adds one does not lock every viewer out)."""

    model_config = ConfigDict(extra="ignore")

    action: str
    path: str = ""
    protocol: str = ""
    user: str = ""
    password: str = ""
    token: str = ""
    query: str = ""
    ip: str = ""


@internal_router.post("/internal/video-auth", status_code=204, include_in_schema=False)
async def relay_auth(body: RelayAuthRequest, context: Context) -> Response:
    """Asked by the relay about every read and publish (M6, ADR 0036); 204 allows.

    Unauthenticated by design: the relay calls it on the internal network, and the gateway
    never forwards ``/api/v1/internal/*``. It reveals nothing but yes or no.
    """
    runtime = context.runtime()
    allowed, why = decide(
        RelayRequest(**body.model_dump()),
        runtime.video_tickets,
        runtime.video_publisher,
        context.clock.now(),
    )
    if not allowed:
        log.warning(
            "relay refused %s of %s over %s from %s: %s",
            body.action,
            body.path,
            body.protocol,
            body.ip,
            why,
        )
        raise Forbidden(f"The relay may not serve this: {why}.", slug="video-access-denied")
    return Response(status_code=204)


@router.get("/{stream_id}", **requires(Permission.FLEET_VIEW))
async def get_video_stream(stream_id: str, db: DbSession) -> VideoStreamOut:
    """One video source."""
    return VideoStreamOut.of(await get_or_404(db, VideoStream, stream_id, "Video stream"))


@router.patch("/{stream_id}", **requires(Permission.FLEET_MANAGE))
async def update_video_stream(
    stream_id: str,
    body: VideoStreamUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> VideoStreamOut:
    """Change a video source."""
    stream = await get_or_404(db, VideoStream, stream_id, "Video stream")
    values = patch_values(body)
    if values.get("aircraft_id") is not None:
        await get_reference(db, Aircraft, values["aircraft_id"], "aircraft_id")
    if "relay_path" in values:
        await _ensure_path_free(db, values["relay_path"], stream.id)
    before = _snapshot(stream)
    now = context.clock.now()
    apply_values(stream, values)
    stream.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "video_stream.update",
        entity_type="video_stream",
        entity_id=stream.id,
        details={"changes": audit.changes(before, _snapshot(stream))},
    )
    await commit_or_conflict(db, "The relay path is in use.")
    return VideoStreamOut.of(stream)


@router.delete(
    "/{stream_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.FLEET_MANAGE)
)
async def delete_video_stream(
    stream_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Remove a video source."""
    stream = await get_or_404(db, VideoStream, stream_id, "Video stream")
    before = _snapshot(stream)
    now = context.clock.now()
    await db.delete(stream)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "video_stream.delete",
        entity_type="video_stream",
        entity_id=stream_id,
        details={"before": before},
    )
    await db.commit()
