"""
The incident export bundle (M6): everything about one incident in one zip, for the
after-action review, the authorities and the archive.

    manifest.json        what, when, from which station, and each file's SHA-256
    incident.json        the incident
    search-areas.geojson, geofences.geojson, pois.geojson
    missions.json        missions with their waypoints and tasks (planned routes)
    alerts.json, commands.json   raised or issued during the incident, with outcomes
    audit.jsonl          the audit events of the incident's time span, and
    audit-chain.json     the chain's verification and head when exported
    telemetry.csv        1 Hz history of the aircraft involved

The incident's time span runs from its creation to its closure (or the export). Data is
read in short sessions; the zip is built off the event loop.
"""

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from fleet_service import __version__
from fleet_service.db.models import (
    Alert,
    AuditEvent,
    Command,
    CommandTarget,
    Geofence,
    Incident,
    Mission,
    Poi,
    SearchArea,
    Task,
    TelemetrySample,
    Waypoint,
)
from fleet_service.db.types import format_utc
from fleet_service.services import audit

TELEMETRY_COLUMNS = [c.key for c in TelemetrySample.__table__.columns if c.key != "id"]


@dataclass(frozen=True)
class Bundle:
    """The files of an export and the time span they cover."""

    incident_id: str
    files: dict[str, bytes]
    start: datetime
    end: datetime
    aircraft: list[str]


def _row(row: DeclarativeBase) -> dict[str, Any]:
    plain: dict[str, Any] = to_jsonable_python(
        {c.key: getattr(row, c.key) for c in row.__table__.columns}
    )
    return plain


def _json(value: Any) -> bytes:
    return json.dumps(to_jsonable_python(value), indent=2, ensure_ascii=False).encode()


def _features(rows: list[Any], geometry: Any) -> bytes:
    return _json(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": geometry(r), "properties": _row(r)} for r in rows
            ],
        }
    )


async def collect_ops(
    db: AsyncSession, incident: Incident, now: datetime, station: str
) -> tuple[dict[str, bytes], list[str], datetime, datetime]:
    """The operational files; returns them, the aircraft involved and the time span."""
    start, end = incident.created_at, incident.closed_at or now
    areas = (
        await db.scalars(select(SearchArea).where(SearchArea.incident_id == incident.id))
    ).all()
    fences = (await db.scalars(select(Geofence).where(Geofence.incident_id == incident.id))).all()
    pois = (await db.scalars(select(Poi).where(Poi.incident_id == incident.id))).all()
    missions = (await db.scalars(select(Mission).where(Mission.incident_id == incident.id))).all()
    mission_ids = [m.id for m in missions]
    waypoints = (
        await db.scalars(
            select(Waypoint).where(Waypoint.mission_id.in_(mission_ids)).order_by(Waypoint.seq)
        )
    ).all()
    tasks = (await db.scalars(select(Task).where(Task.mission_id.in_(mission_ids)))).all()
    alerts = (
        await db.scalars(
            select(Alert)
            .where(Alert.raised_at >= start, Alert.raised_at <= end)
            .order_by(Alert.raised_at)
        )
    ).all()
    commands = (
        await db.scalars(
            select(Command)
            .where(Command.created_at >= start, Command.created_at <= end)
            .order_by(Command.created_at)
        )
    ).all()
    targets = (
        await db.scalars(
            select(CommandTarget).where(CommandTarget.command_id.in_([c.id for c in commands]))
        )
    ).all()
    events = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.ts >= start, AuditEvent.ts <= end)
            .order_by(AuditEvent.seq)
        )
    ).all()
    chain = await audit.verify_chain(db)

    aircraft = sorted(
        {t.aircraft_id for t in tasks}
        | {t.aircraft_id for t in targets}
        | {p.aircraft_id for p in pois if p.aircraft_id}
    )
    files = {
        "incident.json": _json(_row(incident)),
        "search-areas.geojson": _features(list(areas), lambda r: r.geometry),
        "geofences.geojson": _features(list(fences), lambda r: r.geometry),
        "pois.geojson": _features(
            list(pois),
            lambda r: {"type": "Point", "coordinates": [r.longitude, r.latitude]},
        ),
        "missions.json": _json(
            [
                _row(m)
                | {
                    "waypoints": [_row(w) for w in waypoints if w.mission_id == m.id],
                    "tasks": [_row(t) for t in tasks if t.mission_id == m.id],
                }
                for m in missions
            ]
        ),
        "alerts.json": _json([_row(a) for a in alerts]),
        "commands.json": _json(
            [
                _row(c) | {"targets": [_row(t) for t in targets if t.command_id == c.id]}
                for c in commands
            ]
        ),
        "audit.jsonl": b"".join(
            json.dumps(_row(e), ensure_ascii=False).encode() + b"\n" for e in events
        ),
        "audit-chain.json": _json(
            {
                "ok": chain.ok,
                "events": chain.events,
                "head_seq": chain.head_seq,
                "head_hash": chain.head_hash,
                "broken_at_seq": chain.broken_at_seq,
                "reason": chain.reason,
                "verified_at": format_utc(now),
                "station": station,
            }
        ),
    }
    return files, aircraft, start, end


async def collect_telemetry(
    db: AsyncSession, aircraft: list[str], start: datetime, end: datetime
) -> bytes:
    """The recorded telemetry of ``aircraft`` in the span, as CSV (ts in UTC)."""
    rows = await db.scalars(
        select(TelemetrySample)
        .where(
            TelemetrySample.aircraft_id.in_(aircraft),
            TelemetrySample.ts_us >= int(start.timestamp() * 1_000_000),
            TelemetrySample.ts_us <= int(end.timestamp() * 1_000_000),
        )
        .order_by(TelemetrySample.ts_us)
    )
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(TELEMETRY_COLUMNS)
    for row in rows:
        writer.writerow(["" if (v := getattr(row, c)) is None else v for c in TELEMETRY_COLUMNS])
    return out.getvalue().encode()


def build_zip(bundle: Bundle, now: datetime, station: str) -> bytes:
    """The zip, with a manifest of every file's SHA-256 (CPU work: run it in a thread)."""
    manifest = {
        "format": "sar-gcs-incident-export/1",
        "incident_id": bundle.incident_id,
        "station": station,
        "service_version": __version__,
        "exported_at": format_utc(now),
        "span": {"start": format_utc(bundle.start), "end": format_utc(bundle.end)},
        "aircraft": bundle.aircraft,
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in sorted(bundle.files.items())
        },
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json(manifest))
        for name, data in sorted(bundle.files.items()):
            archive.writestr(name, data)
    return out.getvalue()
