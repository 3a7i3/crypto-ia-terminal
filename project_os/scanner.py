"""
project_os/scanner.py — Static inventory of all project modules.

For each .py file: path, package, local/third-party deps, import status.

Usage:
    python project_os/scanner.py                  # table, syntax check only (fast)
    python project_os/scanner.py --check-imports  # full import validation (slow)
    python project_os/scanner.py --json           # write inventory.json
    python project_os/scanner.py --all            # include test files
    python project_os/scanner.py --pkg audit      # filter by package
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "k8s",
    "deploy",
    "archives",
    "archive_results",
    "results",
    "reports",
    "sim_summaries",
    "tickets",
    "artifacts",
    "checkpoints",
    "cache",
    "logs",
    "data",
    "databases",
    "feedback_logs",
    "install",
    ".mypy_cache",
    ".pytest_cache",
    "quant-hedge-ai",
    "docs",
    "frontend",
}

# Top-level names that are part of this project (auto-completed in scan_project)
_LOCAL_ROOTS: set[str] = set()

STDLIB: set[str] = sys.stdlib_module_names  # type: ignore[attr-defined]

STATUS_ICON = {
    "OK": "[OK]",
    "SYNTAX_ERROR": "[SYNTAX_ERR]",
    "IMPORT_ERROR": "[IMPORT_ERR]",
    "SKIPPED": "[-]",
}


@dataclass
class ModuleRecord:
    path: str
    package: str
    lines: int
    local_deps: list[str] = field(default_factory=list)
    third_party_deps: list[str] = field(default_factory=list)
    status: str = "SKIPPED"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_local_roots(root: Path) -> set[str]:
    """Collect top-level package dirs + root-level .py stems."""
    roots: set[str] = set()
    for p in root.iterdir():
        if p.is_dir() and (p / "__init__.py").exists():
            roots.add(p.name)
        elif p.suffix == ".py":
            roots.add(p.stem)
    return roots


def _classify(name: str) -> str:
    root = name.split(".")[0]
    if root in STDLIB:
        return "stdlib"
    if root in _LOCAL_ROOTS:
        return "local"
    return "third_party"


def _extract_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.append(node.module)
    return names


def _deps(source: str) -> tuple[list[str], list[str]]:
    local, third = [], []
    seen: set[str] = set()
    for imp in _extract_imports(source):
        root = imp.split(".")[0]
        if root in seen:
            continue
        seen.add(root)
        kind = _classify(imp)
        if kind == "local":
            local.append(root)
        elif kind == "third_party":
            third.append(root)
    return sorted(set(local)), sorted(set(third))


def _syntax_ok(source: str) -> tuple[bool, Optional[str]]:
    try:
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


def _import_check(rel: Path) -> tuple[str, Optional[str]]:
    """Run a subprocess import test. Returns (status, error)."""
    mod = str(rel).replace("\\", "/").replace("/", ".").removesuffix(".py")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, r'{ROOT}'); import {mod}",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(ROOT),
    )
    if result.returncode == 0:
        return "OK", None
    stderr = (result.stderr or "").strip().splitlines()
    last = stderr[-1] if stderr else "unknown"
    return "IMPORT_ERROR", last


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------


def scan_file(py_file: Path, check_imports: bool) -> ModuleRecord:
    rel = py_file.relative_to(ROOT)
    package = rel.parts[0] if len(rel.parts) > 1 else "root"
    source = py_file.read_text(encoding="utf-8", errors="replace")
    lines = source.count("\n") + 1
    local_deps, third_party_deps = _deps(source)

    ok, err = _syntax_ok(source)
    if not ok:
        return ModuleRecord(
            path=str(rel),
            package=package,
            lines=lines,
            local_deps=local_deps,
            third_party_deps=third_party_deps,
            status="SYNTAX_ERROR",
            error=err,
        )

    if check_imports:
        status, error = _import_check(rel)
    else:
        status, error = "OK", None

    return ModuleRecord(
        path=str(rel),
        package=package,
        lines=lines,
        local_deps=local_deps,
        third_party_deps=third_party_deps,
        status=status,
        error=error,
    )


def scan_project(
    root: Path = ROOT,
    include_tests: bool = False,
    check_imports: bool = False,
    pkg_filter: Optional[str] = None,
) -> list[ModuleRecord]:
    global _LOCAL_ROOTS
    _LOCAL_ROOTS = _build_local_roots(root)

    records: list[ModuleRecord] = []
    for py_file in sorted(root.rglob("*.py")):
        parts = py_file.relative_to(root).parts

        # Skip excluded dirs
        if any(p in SKIP_DIRS for p in parts):
            continue

        # Skip test files unless requested
        if not include_tests:
            if (
                py_file.name.startswith("test_")
                or any(p in ("tests", "test") for p in parts)
                or py_file.stem.startswith("test_")
            ):
                continue

        rel = py_file.relative_to(root)
        package = parts[0] if len(parts) > 1 else "root"

        if pkg_filter and package != pkg_filter:
            continue

        record = scan_file(py_file, check_imports=check_imports)
        records.append(record)

    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_table(records: list[ModuleRecord]) -> None:
    W_PATH, W_PKG, W_STATUS = 58, 20, 14

    header = f"{'PATH':<{W_PATH}} {'PKG':<{W_PKG}} {'STATUS':<{W_STATUS}} {'LINES':>5}  LOCAL DEPS"
    print(f"\n{header}")
    print("-" * 130)

    current_pkg = None
    for r in sorted(records, key=lambda x: (x.package, x.path)):
        if r.package != current_pkg:
            if current_pkg is not None:
                print()
            current_pkg = r.package

        icon = STATUS_ICON.get(r.status, r.status)
        local_str = ", ".join(r.local_deps[:6])
        if len(r.local_deps) > 6:
            local_str += f" +{len(r.local_deps) - 6}"
        print(
            f"  {r.path:<{W_PATH}} {r.package:<{W_PKG}} {icon:<{W_STATUS}} {r.lines:>5}  {local_str}"
        )

    total = len(records)
    ok = sum(1 for r in records if r.status == "OK")
    syntax_err = sum(1 for r in records if r.status == "SYNTAX_ERROR")
    import_err = sum(1 for r in records if r.status == "IMPORT_ERROR")
    skipped = sum(1 for r in records if r.status == "SKIPPED")

    print("\n" + "-" * 130)
    print(
        f"  TOTAL {total}  |  OK {ok}  |  SYNTAX_ERR {syntax_err}"
        f"  |  IMPORT_ERR {import_err}  |  SKIPPED {skipped}"
    )

    errors = [r for r in records if r.status in {"SYNTAX_ERROR", "IMPORT_ERROR"}]
    if errors:
        print("\n  BROKEN MODULES:")
        for r in errors:
            print(f"    [{r.status}] {r.path}")
            if r.error:
                print(f"      → {r.error}")


def write_json(records: list[ModuleRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(r) for r in records], indent=2),
        encoding="utf-8",
    )
    print(f"\n  Written -> {output.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Static inventory of project modules")
    parser.add_argument(
        "--check-imports",
        action="store_true",
        help="Validate each module by subprocess import (slow)",
    )
    parser.add_argument(
        "--all", dest="include_tests", action="store_true", help="Include test files"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write JSON inventory (default: project_os/inventory.json)",
    )
    parser.add_argument(
        "--output",
        default="project_os/inventory.json",
        help="JSON output path (relative to project root)",
    )
    parser.add_argument(
        "--pkg",
        dest="pkg_filter",
        default=None,
        help="Filter by package name (e.g. --pkg audit)",
    )
    args = parser.parse_args()

    mode = "import check ON" if args.check_imports else "syntax check only"
    print(f"Scanning {ROOT.name}/ ({mode})…")

    records = scan_project(
        include_tests=args.include_tests,
        check_imports=args.check_imports,
        pkg_filter=args.pkg_filter,
    )

    print_table(records)

    if args.json:
        write_json(records, ROOT / args.output)


if __name__ == "__main__":
    main()
