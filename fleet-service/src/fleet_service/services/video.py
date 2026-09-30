"""
Video stream health (ADR 0012, M5). The fleet service polls the video relay's (MediaMTX)
API and keeps, per registered stream, whether video is actually flowing:

* **live**: the relay has the path ready and its received bytes grew since the last poll;
* **stalled**: ready, but no new bytes for ``stall_after_s`` (a frozen picture);
* **offline**: the relay has no ready path for it;
* **unknown**: the relay could not be asked, or the stream has not been polled yet. Unknown
  is never shown as live (ADR 0002, S7).

An enabled stream that is not live for ``down_after_s`` is a ``video_down`` condition alert
(cleared when it is live again). Health lives in memory, like live telemetry; polling
happens outside any database session (ADR 0019).

The registry is the source of truth for where video comes from: each poll also
**reconciles** the relay's path configuration (``plan_reconcile``): an enabled stream's
path is added with its source, pulled continuously (so its health is known even when
nobody watches: an on-demand pull would look offline until someone did), or updated if
the source changed; a disabled stream's path is removed. Paths the relay publishes
itself (``source: publisher``, e.g. the mock video) are left alone, as are paths of
streams deleted while the fleet service was down (it cannot tell them from paths an
administrator added by hand). The relay keeps API changes in memory only, so
reconciling every poll also restores them after a relay restart.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx

from fleet_service.domain.enums import AlertKind, AlertSeverity
from fleet_service.services.alerts import Condition

log = logging.getLogger(__name__)


class StreamState(StrEnum):
    """Whether video is flowing through the relay."""

    LIVE = "live"
    STALLED = "stalled"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RelayPath:
    """What the relay says about one path."""

    name: str
    ready: bool
    bytes_received: int | None
    readers: int | None


@dataclass(frozen=True)
class StreamInfo:
    """A registered stream, as the monitor needs it."""

    stream_id: str
    name: str
    relay_path: str
    aircraft_id: str | None
    enabled: bool
    source_url: str = ""  # credentials included: only ever sent to the relay


PULL_SCHEMES = ("rtsp://", "rtsps://", "srt://", "udp://", "rtp://")


@dataclass(frozen=True)
class RelayChange:
    """One change to the relay's path configuration."""

    action: str  # "add", "replace" or "delete"
    path: str
    source: str | None = None


def plan_reconcile(
    streams: Sequence[StreamInfo], configured: Mapping[str, str]
) -> list[RelayChange]:
    """What to change so the relay pulls every enabled stream from its registered source."""
    changes = []
    for stream in streams:
        current = configured.get(stream.relay_path)
        ours = current is not None and current.startswith(PULL_SCHEMES)
        if stream.enabled and stream.source_url:
            if current is None:
                changes.append(RelayChange("add", stream.relay_path, stream.source_url))
            elif ours and current != stream.source_url:
                changes.append(RelayChange("replace", stream.relay_path, stream.source_url))
        elif not stream.enabled and ours and current == stream.source_url:
            changes.append(RelayChange("delete", stream.relay_path))
    return changes


@dataclass
class StreamHealth:
    """The monitor's view of one stream."""

    state: StreamState
    since: datetime | None  # when it entered this state
    readers: int | None
    bitrate_kbps: float | None
    checked_at: datetime | None
    bytes_received: int | None = None
    bytes_changed_at: datetime | None = None


def parse_paths(document: Mapping[str, Any]) -> list[RelayPath]:
    """MediaMTX ``GET /v3/paths/list``; tolerant of field names across versions."""
    paths = []
    for item in document.get("items") or []:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            continue
        ready = item.get("ready", item.get("online", False))
        received = item.get("bytesReceived", item.get("inboundBytes"))
        readers = item.get("readers")
        paths.append(
            RelayPath(
                name=item["name"],
                ready=bool(ready),
                bytes_received=int(received) if isinstance(received, int | float) else None,
                readers=len(readers) if isinstance(readers, list) else None,
            )
        )
    return paths


Fetch = Callable[[], Awaitable[list[RelayPath]]]


class RelayConfig:
    """The relay's path configuration over the MediaMTX API."""

    def __init__(self, api_url: str, timeout_s: float = 2.0) -> None:
        self._base = api_url.rstrip("/") + "/v3/config/paths"
        self._timeout = timeout_s

    async def sources(self) -> dict[str, str]:
        """Configured paths and their sources ("publisher" for pushed or self-made video)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base}/list", params={"itemsPerPage": 1000})
            response.raise_for_status()
            items = response.json().get("items") or []
        return {i["name"]: str(i.get("source") or "") for i in items if isinstance(i, dict)}

    async def apply(self, change: RelayChange) -> None:
        """Make one change."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if change.action == "delete":
                response = await client.delete(f"{self._base}/delete/{change.path}")
            else:
                body = {"source": change.source, "sourceOnDemand": False}
                verb = "add" if change.action == "add" else "replace"
                response = await client.post(f"{self._base}/{verb}/{change.path}", json=body)
            response.raise_for_status()


def mediamtx_fetch(api_url: str, timeout_s: float = 2.0) -> Fetch:
    """A fetch function for a MediaMTX API base URL (e.g. http://127.0.0.1:9997)."""

    async def fetch() -> list[RelayPath]:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(f"{api_url.rstrip('/')}/v3/paths/list")
            response.raise_for_status()
            return parse_paths(response.json())

    return fetch


class VideoMonitor:
    """Polls the relay and derives each stream's health and video_down conditions."""

    def __init__(
        self,
        fetch: Fetch,
        *,
        config: RelayConfig | None = None,
        stall_after_s: float = 3.0,
        down_after_s: float = 5.0,
    ):
        self._fetch = fetch
        self._config = config
        self._stall_after = timedelta(seconds=stall_after_s)
        self._down_after = timedelta(seconds=down_after_s)
        self._streams: dict[str, StreamInfo] = {}
        self._health: dict[str, StreamHealth] = {}

    def set_streams(self, streams: Sequence[StreamInfo]) -> None:
        """The registered streams (read from the database by the caller)."""
        self._streams = {s.stream_id: s for s in streams}
        for gone in set(self._health) - set(self._streams):
            del self._health[gone]

    def health(self, stream_id: str) -> StreamHealth:
        """A stream's health; unknown until polled."""
        return self._health.get(stream_id) or StreamHealth(
            StreamState.UNKNOWN, None, None, None, None
        )

    async def reconcile(self) -> list[RelayChange]:
        """Bring the relay's paths in line with the registry; the changes made."""
        if self._config is None:
            return []
        try:
            changes = plan_reconcile(list(self._streams.values()), await self._config.sources())
            for change in changes:
                await self._config.apply(change)
                log.info("video relay path %s: %s", change.path, change.action)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            log.warning("video relay configuration not updated: %s", error)
            return []
        return changes

    async def poll(self, now: datetime) -> None:
        """Ask the relay once and update every stream."""
        await self.reconcile()
        try:
            paths: dict[str, RelayPath] | None = {p.name: p for p in await self._fetch()}
        except (httpx.HTTPError, ValueError) as error:
            log.warning("video relay not reachable: %s", error)
            paths = None
        for stream in self._streams.values():
            self._update(
                stream, None if paths is None else paths.get(stream.relay_path), paths is None, now
            )

    def _update(
        self, stream: StreamInfo, path: RelayPath | None, unreachable: bool, now: datetime
    ) -> None:
        previous = self._health.get(stream.stream_id)
        bitrate = None
        changed_at = previous.bytes_changed_at if previous else None
        received = path.bytes_received if path else None
        if path is None or unreachable:
            state = StreamState.UNKNOWN if unreachable else StreamState.OFFLINE
        elif not path.ready:
            state = StreamState.OFFLINE
        else:
            grew = (
                previous is not None
                and previous.bytes_received is not None
                and received is not None
                and received > previous.bytes_received
            )
            if grew and previous is not None and previous.checked_at is not None:
                seconds = (now - previous.checked_at).total_seconds()
                if seconds > 0 and previous.bytes_received is not None and received is not None:
                    bitrate = (received - previous.bytes_received) * 8 / 1000 / seconds
                changed_at = now
            elif changed_at is None:
                changed_at = now  # first sight of a ready path: give it the stall window
            state = (
                StreamState.LIVE
                if changed_at is not None and now - changed_at < self._stall_after
                else StreamState.STALLED
            )
        since = previous.since if previous and previous.state is state else now
        self._health[stream.stream_id] = StreamHealth(
            state=state,
            since=since,
            readers=path.readers if path else None,
            bitrate_kbps=bitrate,
            checked_at=now,
            bytes_received=received,
            bytes_changed_at=changed_at,
        )

    def conditions(self, now: datetime) -> list[Condition]:
        """``video_down`` for each enabled stream not live for ``down_after_s``."""
        found = []
        for stream in self._streams.values():
            if not stream.enabled:
                continue
            health = self._health.get(stream.stream_id)
            if health is None or health.state is StreamState.LIVE or health.since is None:
                continue
            if now - health.since < self._down_after:
                continue
            reason = {
                StreamState.STALLED: "the picture is frozen (no new data)",
                StreamState.OFFLINE: "the relay has no video from it",
                StreamState.UNKNOWN: "the video relay is not reachable",
            }[health.state]
            found.append(
                Condition(
                    AlertKind.VIDEO_DOWN,
                    AlertSeverity.WARNING,
                    stream.aircraft_id,
                    f"Video {stream.name}: {reason}.",
                    key_suffix=stream.stream_id,
                )
            )
        return found
