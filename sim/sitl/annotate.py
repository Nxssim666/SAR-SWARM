"""
Turn SITL results into GitHub Actions annotations (CI only).

Annotations are readable through the public checks API, without the authentication that
job logs and artifacts need, so anyone can see why a run failed:

- one error per failed test, with its message and the end of its traceback;
- one notice per PX4 instance, with the end of its console;
- one notice with the totals and the tests that passed.

GitHub keeps at most 10 annotations of each kind per step, hence the grouping.

    python sim/sitl/annotate.py sitl-results
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

MAX_MESSAGE = 6000
PX4_TAIL_LINES = 40


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


def annotate(kind: str, title: str, message: str) -> None:
    """Print one workflow command; GitHub turns it into an annotation."""
    if len(message) > MAX_MESSAGE:
        message = "...\n" + message[-MAX_MESSAGE:]
    print(f"::{kind} title={_escape_property(title)}::{_escape(message)}")  # noqa: T201


def report_tests(junit: Path) -> None:
    if not junit.exists():
        annotate("error", "SITL tests", f"{junit} missing: the tests did not run")
        return
    root = ET.parse(junit).getroot()  # noqa: S314 - our own pytest output
    totals: dict[str, int] = defaultdict(int)
    passed: list[str] = []
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}.{case.get('name', '')}".rsplit(".", 2)[-1]
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is not None:
            totals[problem.tag] += 1
            details = problem.text or problem.get("message") or ""
            annotate("error", f"SITL {problem.tag}: {name}", details)
        elif case.find("skipped") is not None:
            totals["skipped"] += 1
        else:
            totals["passed"] += 1
            passed.append(f"{name} ({float(case.get('time', '0')):.1f} s)")
    counts = ", ".join(f"{kind} {count}" for kind, count in sorted(totals.items()))
    annotate("notice", "SITL totals", "\n".join([counts, *passed]))


def report_px4(log: Path) -> None:
    if not log.exists():
        return
    by_container: dict[str, list[str]] = defaultdict(list)
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        container, separator, rest = line.partition("|")
        if separator:
            by_container[container.strip()].append(rest.strip())
    for container, lines in sorted(by_container.items()):
        annotate("notice", f"PX4 log tail: {container}", "\n".join(lines[-PX4_TAIL_LINES:]))


def main() -> None:
    """Annotate the results in the directory given on the command line."""
    results = Path(sys.argv[1])
    report_tests(results / "junit.xml")
    report_px4(results / "px4.log")


if __name__ == "__main__":
    main()
