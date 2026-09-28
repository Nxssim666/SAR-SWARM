"""Column types shared by both databases."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Dialect, Enum, String
from sqlalchemy.types import TypeDecorator

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"  # fixed width, so text order is time order


def format_utc(value: datetime) -> str:
    """Aware datetime -> fixed-width UTC text. Naive datetimes are ambiguous and rejected."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime cannot be stored; use an aware UTC datetime")
    return value.astimezone(UTC).strftime(_FORMAT)


def parse_utc(value: str) -> datetime:
    """Fixed-width UTC text -> aware datetime."""
    return datetime.strptime(value, _FORMAT).replace(tzinfo=UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """
    An aware datetime stored as fixed-width ISO 8601 UTC text (``2026-09-28T10:00:00.000000Z``).

    Naive datetimes are rejected: a timestamp without a zone is ambiguous in an audit trail.
    """

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        """Convert to UTC text."""
        return None if value is None else format_utc(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        """Parse UTC text back into an aware datetime."""
        return None if value is None else parse_utc(value)


def enum_type[E: StrEnum](enum_cls: type[E]) -> Enum:
    """Store an enum by value as VARCHAR; new values need no migration."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )
