"""The ``fleet-service`` command line: create-admin, audit-verify, db upgrade."""

import io
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from fleet_service import cli
from fleet_service.config import get_settings


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("SARGCS_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def run_with_stdin(monkeypatch: pytest.MonkeyPatch, text: str, *argv: str) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    return cli.main(list(argv))


def test_create_admin_then_verify_audit(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    created = run_with_stdin(
        monkeypatch,
        "a-long-admin-password\n",
        "create-admin",
        "--username",
        "Chief",
        "--password-stdin",
    )
    again = run_with_stdin(
        monkeypatch,
        "a-long-admin-password\n",
        "create-admin",
        "--username",
        "chief",
        "--password-stdin",
    )
    verified = cli.main(["audit-verify"])

    assert created == 0
    assert again == 1
    assert verified == 0
    out = capsys.readouterr()
    assert "created admin 'chief'" in out.out
    assert "audit chain intact: 1 events" in out.out
    with closing(sqlite3.connect(data_dir / "ops.db")) as db:
        role, password_hash = db.execute("select role, password_hash from users").fetchone()
        actor = db.execute("select actor_username from audit_events").fetchone()[0]
    assert role == "admin"
    assert password_hash.startswith("$argon2id$")
    assert "a-long-admin-password" not in password_hash
    assert actor == "system:cli"


def test_audit_verify_detects_tampering(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_with_stdin(
        monkeypatch,
        "a-long-admin-password\n",
        "create-admin",
        "--username",
        "chief",
        "--password-stdin",
    )
    with closing(sqlite3.connect(data_dir / "ops.db")) as db:
        db.execute("update audit_events set actor_username = 'someone-else'")
        db.commit()

    assert cli.main(["audit-verify"]) == 1
    assert "AUDIT CHAIN BROKEN at seq=1" in capsys.readouterr().err


def test_create_admin_rejects_short_passwords(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = run_with_stdin(
        monkeypatch, "short\n", "create-admin", "--username", "chief", "--password-stdin"
    )

    assert code == 2
    assert not (data_dir / "ops.db").exists()


def test_db_upgrade_creates_both_databases(data_dir: Path) -> None:
    assert cli.main(["db", "upgrade"]) == 0
    assert (data_dir / "ops.db").exists()
    assert (data_dir / "telemetry.db").exists()


def test_backup_copies_the_databases_consistently_with_a_manifest(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    run_with_stdin(
        monkeypatch,
        "a-long-admin-password\n",
        "create-admin",
        "--username",
        "chief",
        "--password-stdin",
    )
    output = tmp_path_factory.mktemp("backup") / "2026-09-30"

    assert cli.main(["backup", "--output", str(output)]) == 0
    assert cli.main(["backup", "--output", str(output)]) == 1  # never into a used directory

    manifest = json.loads((output / "manifest.json").read_text())
    assert set(manifest["files"]) == {"ops.db", "telemetry.db"}
    with closing(sqlite3.connect(output / "ops.db")) as copy:
        users = copy.execute("SELECT username FROM users").fetchall()
    assert users == [("chief",)]
    monkeypatch.setenv("SARGCS_DATA_DIR", str(output))  # the copy verifies on its own
    get_settings.cache_clear()
    assert cli.main(["audit-verify"]) == 0
