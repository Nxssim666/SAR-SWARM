"""The in-process event bus: delivery classes (ADR 0008)."""

import pytest

from fleet_service.bus import EventBus, SubscriptionBrokenError


async def test_reliable_subscriptions_deliver_every_event_in_order() -> None:
    bus = EventBus()
    subscription = bus.reliable(["alerts"])

    for i in range(3):
        bus.publish("alerts", i)
    bus.publish("commands", "not subscribed")

    assert [(await subscription.get()).data for _ in range(3)] == [0, 1, 2]
    assert subscription.get_nowait() is None


async def test_a_full_reliable_queue_breaks_instead_of_dropping() -> None:
    bus = EventBus()
    subscription = bus.reliable(["alerts"], maxsize=2)

    for i in range(3):
        bus.publish("alerts", i)

    assert subscription.broken
    with pytest.raises(SubscriptionBrokenError):
        await subscription.get()


def test_latest_value_keeps_only_the_newest_per_key() -> None:
    bus = EventBus()
    subscription = bus.latest(["fleet.telemetry"])

    for i in range(5):
        bus.publish("fleet.telemetry", {"n": i}, key="a1")
    bus.publish("fleet.telemetry", {"n": 9}, key="a2")

    events = subscription.drain()
    assert sorted((e.key, e.data["n"]) for e in events) == [("a1", 4), ("a2", 9)]
    assert subscription.drain() == []


def test_closing_a_subscription_stops_delivery() -> None:
    bus = EventBus()
    subscription = bus.reliable(["alerts"])

    subscription.close()
    subscription.close()  # idempotent
    bus.publish("alerts", 1)

    assert bus.subscriber_count == 0
    assert subscription.get_nowait() is None
