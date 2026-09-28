"""Alembic environment of ops.db."""

from fleet_service.db.migrations.env_common import run
from fleet_service.db.models import OpsBase

run(OpsBase.metadata)
