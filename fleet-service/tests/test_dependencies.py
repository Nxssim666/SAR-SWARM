"""
Every third-party module the service imports is a runtime dependency (M6).

Found in M6: ``services/video.py`` imported httpx, which only the dev group installed, so the
production image (``uv sync --no-dev``) would have failed at startup. The tests could not
see it: they run with the dev group.
"""

import ast
import re
import sys
from importlib.metadata import PackageNotFoundError, packages_distributions, requires
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "fleet_service"


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _runtime_closure() -> set[str]:
    """The distributions ``fleet-service`` needs at run time, transitively (with extras)."""
    wanted: list[tuple[str, frozenset[str]]] = [("fleet-service", frozenset())]
    seen: set[str] = set()
    while wanted:
        name, extras = wanted.pop()
        key = _normalize(name)
        if key in seen and not extras:
            continue
        seen.add(key)
        try:
            specs = requires(name) or []
        except PackageNotFoundError:
            continue
        for spec in specs:
            match = re.match(r"^([A-Za-z0-9._-]+)(\[([^\]]+)\])?", spec)
            if match is None:
                continue
            marker = spec.split(";", 1)[1] if ";" in spec else ""
            extra = re.search(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
            if extra and extra.group(1) not in extras:
                continue
            if "sys_platform" in marker or "python_version" in marker or "platform" in marker:
                pass  # platform-specific dependencies count wherever they apply
            child_extras = frozenset(e.strip() for e in (match.group(3) or "").split(",") if e)
            wanted.append((match.group(1), child_extras))
    return seen


def _imported_top_level_modules() -> set[str]:
    modules: set[str] = set()
    for path in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules - set(sys.stdlib_module_names) - {"fleet_service"}


def test_every_imported_package_is_a_runtime_dependency() -> None:
    runtime = _runtime_closure()
    owners = packages_distributions()

    missing = {
        module: owners.get(module, ["?"])
        for module in _imported_top_level_modules()
        if not any(_normalize(d) in runtime for d in owners.get(module, []))
    }

    assert missing == {}, "imported by the service but not a runtime dependency (uv add ...)"
