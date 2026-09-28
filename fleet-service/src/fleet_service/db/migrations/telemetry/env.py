"""Alembic environment of telemetry.db."""

from fleet_service.db.migrations.env_common import run
from fleet_service.db.models import TelemetryBase

run(TelemetryBase.metadata)
