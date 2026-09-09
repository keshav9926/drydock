"""The dependency direction of §23.2, enforced by an `ast` walk over every module's imports.

Anything not allowed here is forbidden. Stdlib only — an import-linter dependency to check that we
have few dependencies would be its own joke.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# package -> the keel packages it may import (itself always allowed)
ALLOWED: dict[str, set[str]] = {
    "core": set(),
    "events": {"core"},
    "journal": {"core", "events"},
    "providers": {"core"},
    "state": {"core", "events", "journal"},
    "runtime": {"core", "events", "journal", "state", "providers"},
    "effects": {"core", "events", "journal", "state", "runtime", "providers"},
    "replay": {"core", "events", "journal", "state", "runtime", "providers"},
    "orchestration": {"core", "events", "journal", "state", "runtime"},
    "approvals": {"core", "events", "journal", "state", "runtime"},
    # agents/ holds reference *programs*. A program is app code by definition: it names its own
    # Keel, so it imports the public client like any user module would.
    "agents": {"core", "events", "journal", "state", "runtime", "effects", "replay", "providers", "client"},
    "cli": {"core", "events", "journal", "state", "runtime", "effects", "replay", "agents", "client"},
    "api": {"core", "events", "journal", "state", "runtime", "effects", "replay", "client"},
    "client": {"core", "events", "journal", "state", "runtime", "effects", "replay", "orchestration", "approvals", "agents", "providers"},
}

IO_MODULES = {"asyncio", "psycopg", "psycopg_pool", "httpx", "socket", "subprocess", "urllib"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _modules(pkg: str) -> list[Path]:
    return sorted((ROOT / pkg).rglob("*.py"))


def _package_of(path: Path) -> str:
    rel = path.relative_to(ROOT / "keel")
    return "client" if len(rel.parts) == 1 else rel.parts[0]


def test_keel_never_imports_crashproof() -> None:
    """Keel must be installable and correct without the harness; the harness is a client."""
    for path in _modules("keel"):
        offenders = {n for n in _imports(path) if n.split(".")[0] == "crashproof"}
        assert not offenders, f"{path}: keel must never import crashproof ({offenders})"


def test_dependency_direction() -> None:
    for path in _modules("keel"):
        pkg = _package_of(path)
        allowed = ALLOWED.get(pkg, set()) | {pkg}
        for name in _imports(path):
            parts = name.split(".")
            if parts[0] != "keel" or len(parts) == 1:
                continue
            target = "client" if parts[1] == "client" else parts[1]
            assert target in allowed, f"{path}: {pkg} may not import keel.{target}"


def test_state_is_pure() -> None:
    """`keel/state` has no I/O imports: projections are pure folds, and VERIFY and the TUI fold
    the same code (§23.3)."""
    for path in _modules("keel/state"):
        offenders = {n for n in _imports(path) if n.split(".")[0] in IO_MODULES}
        assert not offenders, f"{path}: state must stay a pure fold ({offenders})"


def test_only_one_module_imports_anthropic() -> None:
    for path in _modules("keel"):
        if path.name == "anthropic.py":
            continue
        assert "anthropic" not in {n.split(".")[0] for n in _imports(path)}, path


def test_crashproof_touches_keel_in_two_modules_only() -> None:
    allowed = {"adapters/keel.py", "faults/injectors/hook.py"}
    for path in _modules("crashproof"):
        rel = path.relative_to(ROOT / "crashproof").as_posix()
        if rel in allowed:
            continue
        offenders = {n for n in _imports(path) if n.split(".")[0] == "keel"}
        assert not offenders, f"{path}: crashproof touches keel only in {sorted(allowed)}"
