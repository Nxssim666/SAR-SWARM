"""
The station's own health (M6): space left on the data disk.

A full disk would stop the operational database, and with it commands and the audit
trail, in the middle of an incident. So the station warns early (``disk_low``), and when
space is critical it stops writing telemetry history, by far the largest writer, while
the operational database and the audit trail go on. An unreadable free space is shown as
unknown, never as plenty (ADR 0002, S7).
"""

import shutil
from pathlib import Path

from fleet_service.domain.enums import AlertKind, AlertSeverity
from fleet_service.services.alerts import Condition

MB = 1024 * 1024


def free_bytes(directory: Path) -> int | None:
    """Free space on the disk holding ``directory`` (None: it could not be read)."""
    try:
        return shutil.disk_usage(directory).free
    except OSError:
        return None


def disk_condition(free: int | None, warn_mb: int, critical_mb: int) -> Condition | None:
    """The ``disk_low`` alert that should be open, if any."""
    if free is None:
        return Condition(
            AlertKind.DISK_LOW,
            AlertSeverity.WARNING,
            None,
            "Free space on the data disk is unknown.",
            key_suffix="station",
        )
    if free >= warn_mb * MB:
        return None
    critical = free < critical_mb * MB
    message = f"Only {free / MB:.0f} MB free on the data disk."
    if critical:
        message += " Telemetry history is paused; export and purge old data."
    return Condition(
        AlertKind.DISK_LOW,
        AlertSeverity.CRITICAL if critical else AlertSeverity.WARNING,
        None,
        message,
        key_suffix="station",
    )


def recording_allowed(free: int | None, critical_mb: int) -> bool:
    """Whether telemetry history may be written (unknown space: yes, and alerted)."""
    return free is None or free >= critical_mb * MB
