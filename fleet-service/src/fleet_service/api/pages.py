"""The list envelope: ``{items, next_cursor}``."""

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    """One page of a list; pass ``next_cursor`` back as ``cursor`` for the next page."""

    items: list[T]
    next_cursor: str | None = Field(description="Null when this is the last page.")
