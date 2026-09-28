"""UUIDv7 generation."""

import time
import uuid

from fleet_service.ids import new_id, uuid7


def test_uuid7_has_version_7_and_rfc_variant() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_embeds_the_current_millisecond_timestamp() -> None:
    now_ms = time.time_ns() // 1_000_000

    embedded_ms = uuid7().int >> 80

    # The generator is process-monotonic, so it may be slightly ahead, never behind.
    assert now_ms <= embedded_ms < now_ms + 5_000


def test_ids_are_strictly_increasing_within_one_millisecond() -> None:
    ids = [uuid7(unix_ms=1_790_000_000_000) for _ in range(1000)]

    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_ids_never_go_backwards_when_the_clock_does() -> None:
    later = uuid7(unix_ms=1_790_000_005_000)
    earlier_clock = uuid7(unix_ms=1_790_000_000_000)

    assert earlier_clock > later


def test_new_id_is_a_canonical_uuid_string() -> None:
    text = new_id()

    assert str(uuid.UUID(text)) == text
