#!/usr/bin/env python3
"""
Run every lint, type check, test and build in the repository, on Windows or Linux.

    python scripts/check.py                    # everything
    python scripts/check.py --fast             # skip the onboard closed-loop simulation tests
    python scripts/check.py --only service,console

Suites: ``onboard`` (existing swarm_sar packages), ``service`` (fleet-service),
``console`` (fleet-console). Every step runs even if an earlier one fails, so one
run reports everything; the exit status is non-zero if any step failed.

Tools: uv is used from PATH or as ``python -m uv``. Node.js is used from PATH, or
from the repo-local ``.tools`` venv (``nodejs-wheel``) if present; see
docs/runbooks/dev-setup.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = ("onboard", "service", "console")


@dataclass
class Result:
    suite: str
    step: str
    ok: bool
    seconds: float


def uv_command() -> list[str]:
    """Return how to invoke uv: the executable on PATH, else the module."""
    exe = shutil.which("uv")
    return [exe] if exe else [sys.executable, "-m", "uv"]


def node_environment() -> dict[str, str]:
    """
    Return an environment whose PATH finds a real ``node`` and ``npm``.

    The ``nodejs-wheel`` console-script shims re-launch node through Python, which breaks
    tools that fork node workers (Vitest), so the real binary's directory goes first.
    """
    env = dict(os.environ)
    tools = ROOT / ".tools"
    if not tools.is_dir():
        return env
    extra: list[str] = []
    binaries = [p for name in ("node.exe", "node")
                for p in tools.rglob(f"nodejs_wheel/**/{name}") if p.is_file()]
    if binaries:
        extra.append(str(min(binaries, key=lambda p: len(p.parts)).parent))
    scripts = tools / ("Scripts" if os.name == "nt" else "bin")
    extra.append(str(scripts))
    env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


def run(results: list[Result], suite: str, step: str, argv: list[str], cwd: Path,
        env: dict[str, str] | None = None) -> bool:
    """Run one step, stream its output, and record the outcome."""
    print(f"\n=== [{suite}] {step}: {' '.join(argv)}", flush=True)
    resolved = shutil.which(argv[0], path=(env or os.environ).get("PATH")) or argv[0]
    start = time.monotonic()
    try:
        ok = subprocess.run([resolved, *argv[1:]], cwd=cwd, env=env, check=False).returncode == 0
    except FileNotFoundError:
        print(f"!!! {argv[0]} not found", flush=True)
        ok = False
    results.append(Result(suite, step, ok, time.monotonic() - start))
    return ok


def check_onboard(results: list[Result], fast: bool) -> None:
    argv = [*uv_command(), "run", "--no-project", "--with-requirements",
            "requirements-standalone.txt", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if fast:
        argv += ["-m", "not slow"]
    run(results, "onboard", "pytest", argv, ROOT)


def check_service(results: list[Result]) -> None:
    uv = uv_command()
    cwd = ROOT / "fleet-service"
    if not run(results, "service", "sync", [*uv, "sync", "--locked"], cwd):
        return
    # sim/ and the console's E2E backend share the service's environment and rules.
    python_dirs = [".", "../sim", "../fleet-console/e2e"]
    run(results, "service", "ruff check", [*uv, "run", "ruff", "check", *python_dirs], cwd)
    run(results, "service", "ruff format",
        [*uv, "run", "ruff", "format", "--check", *python_dirs], cwd)
    # The swarm bridge (ROS package, onboard style) is linted with its own rules.
    run(results, "service", "ruff bridge",
        [*uv, "run", "ruff", "check", "--config", "../src/sar_gcs_bridge/ruff.toml",
         "../src/sar_gcs_bridge"], cwd)
    run(results, "service", "mypy", [*uv, "run", "mypy"], cwd)
    env = dict(os.environ)
    if nats_server_found():
        env["SARGCS_REQUIRE_NATS"] = "1"  # found: the NATS tests must run, not skip
    else:
        print("!!! nats-server not found (NATS_SERVER_BIN, PATH or .tools/nats): "
              "the NATS tests will be skipped", flush=True)
    run(results, "service", "pytest", [*uv, "run", "pytest", "-q"], cwd, env)


def nats_server_found() -> bool:
    """Whether the fleet-service NATS tests can start a nats-server (tests/nats_support.py)."""
    candidates = [os.environ.get("NATS_SERVER_BIN"), shutil.which("nats-server"),
                  str(ROOT / ".tools" / "nats" / "nats-server.exe"),
                  str(ROOT / ".tools" / "nats" / "nats-server")]
    return any(c and Path(c).is_file() for c in candidates)


def check_console(results: list[Result]) -> None:
    env = node_environment()
    cwd = ROOT / "fleet-console"
    if not (cwd / "node_modules").is_dir() and not run(
        results, "console", "npm ci", ["npm", "ci", "--no-audit", "--no-fund"], cwd, env
    ):
        return
    for script in ("lint", "format:check", "typecheck", "test", "build"):
        run(results, "console", script, ["npm", "run", "-s", script], cwd, env)
    # Playwright E2E against the fleet service in simulation mode (e2e/backend.py); needs
    # Playwright's Chromium (npx playwright install chromium).
    # E2E_GPU=1: measure the map on this machine's GPU (the fps target is for a GPU); CI runners
    # have none, and report their software-rendering figure instead.
    uv = " ".join(f'"{part}"' if " " in part else part for part in uv_command())
    env = dict(env, UV=uv, E2E_GPU=env.get("E2E_GPU", "1"))
    run(results, "console", "e2e", ["npm", "run", "-s", "e2e"], cwd, env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default=",".join(SUITES),
                        help=f"comma-separated suites to run (default: {','.join(SUITES)})")
    parser.add_argument("--fast", action="store_true",
                        help="skip slow tests (onboard closed-loop simulation)")
    args = parser.parse_args()
    selected = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = sorted(set(selected) - set(SUITES))
    if unknown:
        parser.error(f"unknown suites: {', '.join(unknown)}")

    results: list[Result] = []
    if "onboard" in selected:
        check_onboard(results, args.fast)
    if "service" in selected:
        check_service(results)
    if "console" in selected:
        check_console(results)

    print("\n=== summary")
    for r in results:
        print(f"  {'PASS' if r.ok else 'FAIL'}  {r.suite:<8} {r.step:<14} {r.seconds:6.1f} s")
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
