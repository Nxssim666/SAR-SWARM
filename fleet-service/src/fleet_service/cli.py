"""
``fleet-service`` command line.

    fleet-service [serve]                      run the API server (default)
    fleet-service create-admin --username U    create the first admin (password prompted)
    fleet-service export-openapi [--output P]  write the OpenAPI document
    fleet-service db upgrade                   migrate both databases now
    fleet-service db revision --database ops -m "message"   (development) new migration
    fleet-service audit-verify                 check the audit hash chain; exit 1 if broken

Passwords are never command-line arguments (they would show in the process list and
shell history): they are prompted, or read from stdin with ``--password-stdin``.
"""

import argparse
import asyncio
import getpass
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select

from fleet_service.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, Passwords
from fleet_service.clock import SystemClock
from fleet_service.config import Settings, get_settings
from fleet_service.db import migrate
from fleet_service.db.engine import Database
from fleet_service.db.models import User
from fleet_service.domain.enums import Role
from fleet_service.ids import new_id
from fleet_service.services import audit

# docs/api/openapi.json in a source checkout (src/fleet_service/cli.py -> repository root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PATH = _REPO_ROOT / "docs" / "api" / "openapi.json"


def build_parser() -> argparse.ArgumentParser:
    """The argument parser."""
    parser = argparse.ArgumentParser(
        prog="fleet-service",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the API server (default)")

    admin = sub.add_parser("create-admin", help="create an admin account")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name", default=None)
    admin.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin (one line)"
    )

    export = sub.add_parser("export-openapi", help="write the OpenAPI document")
    export.add_argument("--output", type=Path, default=None, help="default: docs/api/openapi.json")

    db = sub.add_parser("db", help="database maintenance")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="migrate both databases to the newest schema")
    revision = db_sub.add_parser("revision", help="autogenerate a migration (development)")
    revision.add_argument("--database", choices=["ops", "telemetry"], required=True)
    revision.add_argument("-m", "--message", required=True)

    sub.add_parser("audit-verify", help="verify the audit hash chain")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; return the exit code."""
    args = build_parser().parse_args(argv)
    command = args.command or "serve"
    if command == "serve":
        return serve(get_settings())
    if command == "create-admin":
        return create_admin(get_settings(), args.username, args.display_name, args.password_stdin)
    if command == "export-openapi":
        return export_openapi(args.output)
    if command == "db" and args.db_command == "upgrade":
        migrate.upgrade_all(get_settings().data_dir, SystemClock().now())
        print("databases are at the newest schema")
        return 0
    if command == "db" and args.db_command == "revision":
        with tempfile.TemporaryDirectory() as scratch:
            migrate.autogenerate_revision(args.database, args.message, Path(scratch))
        return 0
    if command == "audit-verify":
        return audit_verify(get_settings())
    raise AssertionError(f"unhandled command {command}")  # pragma: no cover


def serve(settings: Settings) -> int:
    """Run uvicorn with the application factory."""
    import uvicorn

    uvicorn.run(
        "fleet_service.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,  # create_app configures logging
        proxy_headers=True,
    )
    return 0


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise ValueError("the passwords do not match")
    return first


def create_admin(
    settings: Settings, username: str, display_name: str | None, password_stdin: bool
) -> int:
    """Create an active admin account; refuse if the username exists."""
    username = username.lower()
    try:
        password = _read_password(password_stdin)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        print(
            f"error: the password must have {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} "
            "characters",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_create_admin(settings, username, display_name or username, password))


async def _create_admin(settings: Settings, username: str, display_name: str, password: str) -> int:
    now = SystemClock().now()
    migrate.upgrade_all(settings.data_dir, now)
    password_hash = await Passwords().hash(password)
    database = Database(settings.data_dir)
    try:
        async with database.ops_session() as db:
            if await db.scalar(select(User.id).where(User.username == username)):
                print(f"error: user {username!r} exists", file=sys.stderr)
                return 1
            user = User(
                id=new_id(),
                username=username,
                display_name=display_name,
                role=Role.ADMIN,
                password_hash=password_hash,
                is_active=True,
                created_at=now,
                updated_at=now,
                last_login_at=None,
            )
            db.add(user)
            await db.flush()
            await audit.record(
                db,
                audit.CLI_ACTOR,
                now,
                "user.create",
                entity_type="user",
                entity_id=user.id,
                details={"after": {"username": username, "role": Role.ADMIN.value}},
            )
            await db.commit()
    finally:
        await database.dispose()
    print(f"created admin {username!r}")
    return 0


def export_openapi(output: Path | None) -> int:
    """Write the OpenAPI document (deterministic JSON, trailing newline)."""
    from fleet_service.main import create_app

    with tempfile.TemporaryDirectory() as scratch:
        app = create_app(Settings(data_dir=Path(scratch), log_json=False))
        document = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    target = output or DEFAULT_OPENAPI_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


def audit_verify(settings: Settings) -> int:
    """Verify the audit chain; print the head so it can be recorded elsewhere."""
    return asyncio.run(_audit_verify(settings))


async def _audit_verify(settings: Settings) -> int:
    database = Database(settings.data_dir)
    try:
        async with database.ops_session() as db:
            report = await audit.verify_chain(db)
    finally:
        await database.dispose()
    if report.ok:
        print(
            f"audit chain intact: {report.events} events; "
            f"head seq={report.head_seq} hash={report.head_hash}"
        )
        return 0
    print(
        f"AUDIT CHAIN BROKEN at seq={report.broken_at_seq}: {report.reason} "
        f"({report.events} events verified before it)",
        file=sys.stderr,
    )
    return 1
