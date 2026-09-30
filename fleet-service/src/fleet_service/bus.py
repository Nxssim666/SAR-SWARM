"""
In-process event bus (ADR 0008). NATS replaces the transport in M2b behind this interface.

Two delivery classes, chosen by the subscriber:

* ``ReliableSubscription``: every event, in order, through a bounded queue. If the
  consumer falls behind and the queue fills, the subscription is marked *broken*
  instead of silently dropping events; the consumer must resync (the WebSocket closes
  with 4429 and the console reloads).
* ``LatestValueSubscription``: only the newest event per (topic, key), for telemetry,
  where an old position is worth nothing once a newer one exists.

``publish`` never blocks and never awaits: it is called from driver callbacks and
request handlers alike.
"""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Topics.
TELEMETRY = "fleet.telemetry"  # key: aircraft id; data: live aircraft state
ALERTS = "alerts"
COMMANDS = "commands"
CONTROL = "control"
MISSIONS = "missions"  # key: mission id; data: mission progress
POIS = "pois"  # key: poi id; data: point of interest
SESSIONS = "sessions"  # key: session id; data: {"revoked": True}
TOPICS = (TELEMETRY, ALERTS, COMMANDS, CONTROL, MISSIONS, POIS)


@dataclass(frozen=True, slots=True)
class Event:
    """Something that happened."""

    topic: str
    key: str | None
    data: Any


class _Subscription:
    def __init__(self, bus: "EventBus", topics: Iterable[str]) -> None:
        self.bus = bus
        self.topics = frozenset(topics)

    def offer(self, event: Event) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def close(self) -> None:
        """Stop receiving events."""
        self.bus.unsubscribe(self)


class ReliableSubscription(_Subscription):
    """Every event, in order; broken (not lossy) when the consumer cannot keep up."""

    def __init__(self, bus: "EventBus", topics: Iterable[str], maxsize: int) -> None:
        super().__init__(bus, topics)
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.broken = False

    def offer(self, event: Event) -> None:
        """Queue ``event``, or mark the subscription broken if the queue is full."""
        if self.broken:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.broken = True

    def pending(self) -> int:
        """Number of queued events."""
        return self._queue.qsize()

    async def get(self) -> Event:
        """The next event (raises ``SubscriptionBroken`` once events were lost)."""
        if self.broken:
            raise SubscriptionBrokenError
        return await self._queue.get()

    def get_nowait(self) -> Event | None:
        """The next event, or None if none is queued."""
        if self.broken:
            raise SubscriptionBrokenError
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class LatestValueSubscription(_Subscription):
    """The newest event per (topic, key); older ones are replaced, by design."""

    def __init__(self, bus: "EventBus", topics: Iterable[str]) -> None:
        super().__init__(bus, topics)
        self._latest: dict[tuple[str, str | None], Event] = {}
        self._changed = asyncio.Event()

    def offer(self, event: Event) -> None:
        """Remember ``event`` as the newest for its key."""
        self._latest[(event.topic, event.key)] = event
        self._changed.set()

    def drain(self) -> list[Event]:
        """Return and forget the newest events since the last drain."""
        events = list(self._latest.values())
        self._latest.clear()
        self._changed.clear()
        return events

    async def wait(self) -> None:
        """Wait until at least one event is pending."""
        await self._changed.wait()


class SubscriptionBrokenError(Exception):
    """A reliable subscription overflowed; the consumer must resync."""


class EventBus:
    """Fan-out of events to subscriptions, in the publisher's task."""

    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []

    def publish(self, topic: str, data: Any, key: str | None = None) -> None:
        """Deliver an event to every subscription of ``topic``."""
        event = Event(topic, key, data)
        for subscription in tuple(self._subscriptions):
            if topic in subscription.topics:
                subscription.offer(event)

    def reliable(self, topics: Iterable[str], maxsize: int = 1000) -> ReliableSubscription:
        """Subscribe with reliable, in-order delivery."""
        subscription = ReliableSubscription(self, topics, maxsize)
        self._subscriptions.append(subscription)
        return subscription

    def latest(self, topics: Iterable[str]) -> LatestValueSubscription:
        """Subscribe to the newest value per key."""
        subscription = LatestValueSubscription(self, topics)
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: _Subscription) -> None:
        """Remove a subscription (idempotent)."""
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    @property
    def subscriber_count(self) -> int:
        """Number of live subscriptions."""
        return len(self._subscriptions)
