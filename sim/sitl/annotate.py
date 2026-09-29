"""
Turn integration results (SITL, scale, swarm) into GitHub Actions annotations.

Annotations are readable through the public checks API, without the authentication that
job logs and artifacts need, so anyone can see why a run failed:

- one error per failed test, with its message and the end of its traceback;
- one notice per PX4 instance, with the end of its console (for a large fleet, only the
  instances that logged the most errors);
- one notice with the totals and the tests that passed;
- for scale runs: the measurements (``scale-report.json``) and the containers' CPU and
  memory (``docker-stats.txt``, sampled by the workflow).

GitHub keeps at most 10 annotations of each kind per step, hence the grouping.

    python sim/sitl/annotate.py sitl-results
"""

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

MAX_MESSAGE = 3800  # GitHub cuts annotation messages at about 4 KB
PX4_TAIL_LINES = 40
MAX_PX4_TAILS = 6  # GitHub keeps 10 notices per step; leave room for the others
_UNITS = {
    "B": 1 / 2**20,
    "KiB": 1 / 1024,
    "kB": 1 / 1024,
    "MiB": 1.0,
    "MB": 1.0,
    "GiB": 1024.0,
    "GB": 1024.0,
}


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
        annotate("error", "Tests", f"{junit} missing: the tests did not run")
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
            annotate("error", f"Test {problem.tag}: {name}", details)
        elif case.find("skipped") is not None:
            totals["skipped"] += 1
        else:
            totals["passed"] += 1
            passed.append(f"{name} ({float(case.get('time', '0')):.1f} s)")
    counts = ", ".join(f"{kind} {count}" for kind, count in sorted(totals.items()))
    annotate("notice", "Test totals", "\n".join([counts, *passed]))


def report_px4(log: Path) -> None:
    if not log.exists():
        return
    by_container: dict[str, list[str]] = defaultdict(list)
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        container, separator, rest = line.partition("|")
        if separator:
            by_container[container.strip()].append(rest.strip())
    chosen = sorted(by_container)
    if len(chosen) > MAX_PX4_TAILS:
        errors = {c: sum("ERROR" in line for line in by_container[c]) for c in chosen}
        chosen = sorted(sorted(chosen, key=lambda c: -errors[c])[:MAX_PX4_TAILS])
    for container in chosen:
        lines = by_container[container]
        annotate("notice", f"Log tail: {container}", "\n".join(lines[-PX4_TAIL_LINES:]))


def report_scale(report: Path) -> None:
    if not report.exists():
        return
    data = json.loads(report.read_text(encoding="utf-8"))
    tracking = data.get("tracking")
    if tracking:
        per_aircraft = tracking.pop("per_aircraft", {})
        worst = sorted(per_aircraft.items(), key=lambda kv: -(kv[1]["max_gap_s"] or 0.0))[:5]
        tracking["worst_gaps"] = {name: a["max_gap_s"] for name, a in worst}
    annotate("notice", "Scale measurements", json.dumps(data, indent=1))


def _mib(text: str) -> float:
    number = text.rstrip("KMGiBk")
    return float(number) * _UNITS.get(text[len(number) :], 1.0)


def report_docker_stats(stats: Path) -> None:
    """Totals over all containers per sample (``name,cpu%,used / limit`` lines; ``#`` stamps)."""
    if not stats.exists():
        return
    samples: list[tuple[float, float, int]] = []
    cpu = mem = 0.0
    count = 0
    for line in [*stats.read_text(encoding="utf-8").splitlines(), "#"]:
        if line.startswith("#"):
            if count:
                samples.append((cpu, mem, count))
            cpu = mem = 0.0
            count = 0
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        cpu += float(parts[1].rstrip("%") or 0.0)
        mem += _mib(parts[2].split("/")[0].strip())
        count += 1
    if not samples:
        return
    cpus = [s[0] for s in samples]
    mems = [s[1] for s in samples]
    annotate(
        "notice",
        "Container resources",
        f"{len(samples)} samples of {max(s[2] for s in samples)} containers\n"
        f"CPU total: mean {sum(cpus) / len(cpus):.0f} %, max {max(cpus):.0f} % "
        "(100 % = one core)\n"
        f"memory total: mean {sum(mems) / len(mems):.0f} MiB, max {max(mems):.0f} MiB",
    )


def main() -> None:
    """Annotate the results in the directory given on the command line."""
    results = Path(sys.argv[1])
    report_tests(results / "junit.xml")
    report_px4(results / "px4.log")
    report_scale(results / "scale-report.json")
    report_docker_stats(results / "docker-stats.txt")


if __name__ == "__main__":
    main()
