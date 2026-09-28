"""
Errors as RFC 9457 problem details (``application/problem+json``), ADR 0013.

Domain code raises a ``ProblemError`` subclass; the handlers here turn it, request
validation failures and plain HTTP errors into problem documents. ``type`` is
``urn:sar-gcs:problem:<slug>`` for errors with SAR-specific meaning and ``about:blank``
for plain HTTP errors.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:sar-gcs:problem:"

log = logging.getLogger(__name__)


class FieldError(BaseModel):
    """One invalid input value."""

    loc: list[str | int] = Field(description="Where the value is: body, query, path, header.")
    msg: str
    type: str


class Problem(BaseModel):
    """RFC 9457 problem details. Extension members depend on ``type``."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="about:blank", examples=[f"{PROBLEM_TYPE_PREFIX}conflict"])
    title: str
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = Field(
        default=None, description="Present on validation errors: each invalid value."
    )


class ProblemError(Exception):
    """Base class of errors reported to clients as problem details."""

    status = 500
    slug = "internal-error"
    title = "Internal error"

    def __init__(
        self,
        detail: str,
        *,
        slug: str | None = None,
        extensions: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if slug is not None:
            self.slug = slug
        self.extensions = dict(extensions or {})
        self.headers = dict(headers or {})


class Unauthorized(ProblemError):
    """No valid session: the client must log in."""

    status, slug, title = 401, "unauthenticated", "Authentication required"

    def __init__(self, detail: str, **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(detail, **kwargs)


class Forbidden(ProblemError):
    """Authenticated, but not allowed to do this."""

    status, slug, title = 403, "forbidden", "Not permitted"


class NotFound(ProblemError):
    """The addressed resource does not exist."""

    status, slug, title = 404, "not-found", "Resource not found"


class Conflict(ProblemError):
    """The request conflicts with the current state (ADR 0013)."""

    status, slug, title = 409, "conflict", "Conflict with current state"


class InvalidRequest(ProblemError):
    """Well-formed, but semantically invalid (bad reference, outside operating area, ...)."""

    status, slug, title = 422, "invalid-request", "Invalid request"


class TooManyRequests(ProblemError):
    """Rate limited; retry after the given number of seconds."""

    status, slug, title = 429, "rate-limited", "Too many requests"

    def __init__(self, detail: str, *, retry_after_s: int) -> None:
        super().__init__(
            detail,
            extensions={"retry_after_s": retry_after_s},
            headers={"Retry-After": str(retry_after_s)},
        )


def problem_response(
    status: int,
    title: str,
    detail: str | None,
    *,
    type_: str = "about:blank",
    instance: str | None = None,
    extensions: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response."""
    body: dict[str, Any] = {"type": type_, "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = instance
    body.update(extensions or {})
    return JSONResponse(
        jsonable_encoder(body), status_code=status, media_type=PROBLEM_JSON, headers=headers
    )


def _field_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    # Never echo ``input``: it can hold passwords or other submitted secrets.
    return [
        {
            "loc": list(e.get("loc", ())),
            "msg": str(e.get("msg", "")),
            "type": str(e.get("type", "")),
        }
        for e in errors
    ]


async def _problem_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ProblemError):  # registered for this type only
        raise exc
    return problem_response(
        exc.status,
        exc.title,
        exc.detail,
        type_=PROBLEM_TYPE_PREFIX + exc.slug,
        instance=request.url.path,
        extensions=exc.extensions,
        headers=exc.headers,
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for this type only
        raise exc
    return problem_response(
        422,
        "Invalid request",
        "One or more values are invalid.",
        type_=PROBLEM_TYPE_PREFIX + "validation-error",
        instance=request.url.path,
        extensions={"errors": _field_errors(exc.errors())},
    )


async def _http_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for this type only
        raise exc
    headers = dict(exc.headers or {})
    if exc.status_code == 405:
        headers["Allow"] = ", ".join(sorted(_allowed_methods(request)))
    return problem_response(
        exc.status_code,
        _reason(exc.status_code),
        str(exc.detail) if exc.detail else None,
        instance=request.url.path,
        headers=headers,
    )


def _allowed_methods(request: Request) -> set[str]:
    """
    Every method the addressed resource supports, taken from the published OpenAPI paths.

    FastAPI registers one route per method set, and Starlette's 405 names only the first
    route whose path matched; the OpenAPI document is the public, complete answer.
    """
    table: list[tuple[re.Pattern[str], set[str]]] | None = getattr(
        request.app.state, "allow_table", None
    )
    if table is None:
        table = [
            (_path_regex(path), {method.upper() for method in operations})
            for path, operations in request.app.openapi().get("paths", {}).items()
        ]
        request.app.state.allow_table = table
    path = request.url.path
    return {method for regex, methods in table if regex.match(path) for method in methods}


def _path_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}/]+\})", template)
    return re.compile(
        "^" + "".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts) + "$"
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return problem_response(500, "Internal error", None, instance=request.url.path)


def _reason(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def install_error_handlers(app: FastAPI) -> None:
    """Register the problem+json handlers on ``app``."""
    app.add_exception_handler(ProblemError, _problem_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries documenting problem+json errors for ``statuses``."""
    descriptions = {
        400: "The request body could not be parsed (not valid JSON or not UTF-8).",
        401: "Missing, invalid or expired session.",
        403: "The session's role lacks the required permission.",
        404: "The resource does not exist.",
        409: "The request conflicts with the current state.",
        422: "Invalid input: malformed, out of range, or semantically invalid.",
        429: "Too many attempts; see Retry-After.",
    }
    return {
        status: {
            "model": Problem,
            "description": descriptions.get(status, _reason(status)),
        }
        for status in statuses
    }
