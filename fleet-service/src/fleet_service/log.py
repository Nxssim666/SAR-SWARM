"""
Logging setup: one JSON object per line on stderr, UTC timestamps.

JSON lines are what an incident review greps and what a log shipper ingests;
the human-readable format is for interactive development only.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else was passed with ``extra=`` and is logged as a field.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Format a record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the JSON line for ``record``."""
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, json_lines: bool) -> None:
    """Route the root logger (and uvicorn's) to stderr in the chosen format."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter()
        if json_lines
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
