"""
Building blocks shared by the REST routers: field types, PATCH models, pagination.

Input numbers and booleans are strict: ``"5"`` is not a number and ``1`` is not
``true``. Lax coercion would accept requests the published schema calls invalid.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

# Text fields: no leading/trailing whitespace, not empty.
_TRIMMED = r"^\S(?:.*\S)?$"
Name = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=_TRIMMED)]
ShortName = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=_TRIMMED)]
Notes = Annotated[str, StringConstraints(max_length=2000)]

StrictFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
StrictInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]

AltitudeRelative = Annotated[
    float,
    Field(
        strict=True,
        allow_inf_nan=False,
        ge=-500.0,
        le=1500.0,
        description="Metres above each aircraft's home position (ADR 0014).",
    ),
]
Speed = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0.0, le=60.0)]
EntityId = Annotated[str, StringConstraints(min_length=1, max_length=64)]


def optional() -> Any:
    """
    Default for a PATCH field: the field may be omitted, and omitted means "unchanged".

    Fields typed without ``None`` reject an explicit ``null``; fields typed ``X | None``
    accept ``null`` meaning "clear". Read only fields listed in ``model_fields_set``.
    """
    return Field(default=None)


class InputModel(BaseModel):
    """Base of request bodies: unknown fields are errors (a typo must not be ignored)."""

    model_config = ConfigDict(extra="forbid")


def _drop_defaults(schema: dict[str, Any], _model: type[Any]) -> None:
    # A PATCH field's default is "unchanged", not null: do not publish a default.
    for prop in schema.get("properties", {}).values():
        prop.pop("default", None)


class PatchModel(InputModel):
    """Base of PATCH bodies: every field optional; omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_drop_defaults)


class OutputModel(BaseModel):
    """Base of response bodies, built from ORM rows."""

    model_config = ConfigDict(from_attributes=True)


def patch_values(patch: BaseModel) -> dict[str, Any]:
    """Return only the fields the client sent in a PATCH body."""
    return {name: getattr(patch, name) for name in patch.model_fields_set}


def apply_values(target: object, values: Mapping[str, Any]) -> None:
    """Set attributes on an ORM row."""
    for name, value in values.items():
        setattr(target, name, value)


@dataclass(frozen=True)
class PageParams:
    """Cursor pagination parameters."""

    limit: int
    cursor: str | None


def page_params(
    limit: Annotated[int, Query(ge=1, le=500, description="Maximum items to return.")] = 100,
    cursor: Annotated[
        str | None,
        Query(max_length=64, description="Opaque cursor from a previous page's next_cursor."),
    ] = None,
) -> PageParams:
    """FastAPI dependency: read pagination parameters."""
    return PageParams(limit=limit, cursor=cursor)


async def fetch_page[R](
    db: AsyncSession,
    statement: Select[R],
    key: InstrumentedAttribute[Any],
    page: PageParams,
    *,
    descending: bool = False,
) -> tuple[Sequence[R], str | None]:
    """Run ``statement`` ordered by ``key`` after ``page.cursor``; return rows and next cursor."""
    if page.cursor is not None:
        cursor: Any = page.cursor
        if key.type.python_type is int:
            if not page.cursor.isdigit():
                return [], None
            cursor = int(page.cursor)
        statement = statement.where(key < cursor if descending else key > cursor)
    statement = statement.order_by(key.desc() if descending else key).limit(page.limit + 1)
    rows = (await db.scalars(statement)).all()
    if len(rows) <= page.limit:
        return rows, None
    rows = rows[: page.limit]
    return rows, str(getattr(rows[-1], key.key))
