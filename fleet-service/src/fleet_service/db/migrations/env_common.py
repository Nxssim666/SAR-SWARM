"""Shared body of both Alembic ``env.py`` files."""

from alembic import context
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool


def _configure_and_run(connection: Connection, metadata: MetaData) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_as_batch=True,  # SQLite cannot ALTER most things; batch mode recreates tables
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run(metadata: MetaData) -> None:
    """Run migrations for ``metadata`` online (offline SQL generation is not supported)."""
    if context.is_offline_mode():
        raise RuntimeError("offline migrations are not supported; run against a database file")
    url = context.config.get_main_option("sqlalchemy.url")
    if url is None:
        raise RuntimeError("sqlalchemy.url is not configured")
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            _configure_and_run(connection, metadata)
    finally:
        engine.dispose()
