"""
project_os/test_scanner.py — Test coverage scanner (static, no pytest needed).

Enrichissements v2 :
  - Orphan test files (tests qui ne couvrent aucun module connu)
  - Cross-ref hubs non couverts (modules critiques sans tests)
  - Comptage @pytest.mark.parametrize (variantes de tests)
  - Resolution d'imports amelioree (prefix, stem, package-root)

Usage:
    python project_os/test_scanner.py                # table, all packages
    python project_os/test_scanner.py --uncovered    # only uncovered modules
    python project_os/test_scanner.py --pkg audit    # filter by package
    python project_os/test_scanner.py --json         # write test_coverage.json
    python project_os/test_scanner.py --tests-only   # list test files + targets
    python project_os/test_scanner.py --orphans      # test files sans cible connue
    python project_os/test_scanner.py --hubs         # modules hubs non couverts
"""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "project_os" / "inventory.json"
DEP_GRAPH = ROOT / "project_os" / "dep_graph.json"

SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    "quant-hedge-ai",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TestFile:
    path: str
    test_count: int
    class_count: int
    parametrize_count: int  # @pytest.mark.parametrize decorators found
    targets: list[str]  # resolved production module paths
    raw_imports: list[str]  # all imported module names (for debug)
    is_orphan: bool = False  # True if no target resolved


@dataclass
class ModuleCoverage:
    path: str
    package: str
    lines: int
    dependants: int = 0  # from dep_graph.json (hub metric)
    test_files: list[str] = field(default_factory=list)
    test_count: int = 0
    parametrize_variants: int = 0
    status: str = "UNCOVERED"  # COVERED | PARTIAL | UNCOVERED


# ---------------------------------------------------------------------------
# Helpers — file collection
# ---------------------------------------------------------------------------


def _collect_test_files() -> list[Path]:
    results: list[Path] = []
    for f in sorted(ROOT.rglob("test_*.py")):
        parts = f.relative_to(ROOT).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        results.append(f)
    return results


# ---------------------------------------------------------------------------
# Helpers — AST parsing
# ---------------------------------------------------------------------------


def _count_parametrize(tree: ast.AST) -> int:
    """Count @pytest.mark.parametrize decorators (each = extra test variants)."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # pytest.mark.parametrize(...) or mark.parametrize(...)
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Attribute) and func.attr == "parametrize":
                    count += 1
    return count


def _parse_test_file(f: Path) -> TestFile:
    rel = str(f.relative_to(ROOT))
    source = f.read_text(encoding="utf-8", errors="replace")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return TestFile(
            path=rel,
            test_count=0,
            class_count=0,
            parametrize_count=0,
            targets=[],
            raw_imports=[],
        )

    test_fns = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    )
    test_classes = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test")
    )
    parametrize = _count_parametrize(tree)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imported.append(node.module)

    return TestFile(
        path=rel,
        test_count=test_fns,
        class_count=test_classes,
        parametrize_count=parametrize,
        targets=[],  # filled later after resolution
        raw_imports=imported,
    )


# ---------------------------------------------------------------------------
# Helpers — import resolution (v2 improved)
# ---------------------------------------------------------------------------


def _import_to_path(imp: str, known_paths: set[str]) -> Optional[str]:
    """
    Resolve an import string to a known relative file path.
    Strategy (in order):
      1. Direct dot->slash match:     'audit.decision_ledger' -> 'audit/decision_ledger.py'
      2. Unique stem match:           last segment = filename stem, if unique
      3. Prefix package match:        first segment -> package/__init__.py
      4. Partial prefix scan:         longest matching prefix in known_paths
    """
    # 1. Direct
    candidate = imp.replace(".", "/") + ".py"
    if candidate in known_paths:
        return candidate

    parts = imp.split(".")

    # 2. Unique stem match on last segment
    stem = parts[-1]
    stem_matches = [p for p in known_paths if Path(p).stem == stem]
    if len(stem_matches) == 1:
        return stem_matches[0]

    # 3. Package-root fallback when importing a sub-symbol: 'audit.decision_ledger'
    #    -> look for 'audit/decision_ledger.py' already handled above,
    #    -> then 'audit/__init__.py'
    pkg_init = parts[0] + "/__init__.py"
    if pkg_init in known_paths and len(parts) == 1:
        return pkg_init

    # 4. Longest prefix: try progressively shorter dot-paths
    for length in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:length]) + ".py"
        if candidate in known_paths:
            return candidate
        init_candidate = "/".join(parts[:length]) + "/__init__.py"
        if init_candidate in known_paths:
            return init_candidate

    return None


def _infer_target_from_name(test_path: str, known_paths: set[str]) -> Optional[str]:
    """
    Naming convention fallback: test_foo_bar.py -> foo_bar.py or foo/bar.py
    Also tries common prefixes like test_phase3_foo -> foo.py
    """
    stem = Path(test_path).stem
    if not stem.startswith("test_"):
        return None
    target_stem = stem[5:]  # strip 'test_'

    # Exact stem match
    matches = [p for p in known_paths if Path(p).stem == target_stem]
    if len(matches) == 1:
        return matches[0]

    # Underscore -> slash: 'foo_bar' -> 'foo/bar.py'
    slashed = target_stem.replace("_", "/") + ".py"
    if slashed in known_paths:
        return slashed

    # Strip common numeric prefixes: 'phase3_foo' -> 'foo'
    parts = target_stem.split("_")
    if len(parts) > 1 and parts[0].replace("phase", "").replace("p", "").isdigit():
        trimmed = "_".join(parts[1:])
        matches2 = [p for p in known_paths if Path(p).stem == trimmed]
        if len(matches2) == 1:
            return matches2[0]

    return None


# ---------------------------------------------------------------------------
# Hub data loader
# ---------------------------------------------------------------------------


def _load_hub_dependants() -> dict[str, int]:
    """Return {package_name: dependant_count} from dep_graph.json if available."""
    if not DEP_GRAPH.exists():
        return {}
    try:
        data = json.loads(DEP_GRAPH.read_text(encoding="utf-8"))
        return {h["module"]: h["dependants"] for h in data.get("hubs", [])}
    except (json.JSONDecodeError, KeyError):
        return {}


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------


def load_inventory() -> list[dict]:
    if not INVENTORY.exists():
        raise FileNotFoundError(
            f"{INVENTORY} not found — run: python project_os/scanner.py --json"
        )
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def scan_tests(
    pkg_filter: Optional[str] = None,
) -> tuple[list[TestFile], list[ModuleCoverage]]:
    inventory = load_inventory()
    hub_dependants = _load_hub_dependants()

    # Production modules only (no test files, no project_os internals)
    prod_modules = [
        r
        for r in inventory
        if not Path(r["path"]).name.startswith("test_") and r["package"] != "project_os"
    ]
    if pkg_filter:
        prod_modules = [r for r in prod_modules if r["package"] == pkg_filter]

    known_paths: set[str] = {r["path"].replace("\\", "/") for r in prod_modules}

    coverage: dict[str, ModuleCoverage] = {
        r["path"].replace("\\", "/"): ModuleCoverage(
            path=r["path"].replace("\\", "/"),
            package=r["package"],
            lines=r.get("lines", 0),
            dependants=hub_dependants.get(r["package"], 0),
        )
        for r in prod_modules
    }

    test_files: list[TestFile] = []
    for f in _collect_test_files():
        tf = _parse_test_file(f)

        # Resolve imports -> production module paths
        resolved: set[str] = set()
        for imp in tf.raw_imports:
            p = _import_to_path(imp, known_paths)
            if p:
                resolved.add(p)

        # Fallback: naming convention
        if not resolved:
            p = _infer_target_from_name(tf.path, known_paths)
            if p:
                resolved.add(p)

        tf.targets = sorted(resolved)
        tf.is_orphan = len(resolved) == 0

        # Update coverage records
        for prod_path in resolved:
            if prod_path in coverage:
                cov = coverage[prod_path]
                if tf.path not in cov.test_files:
                    cov.test_files.append(tf.path)
                    cov.test_count += tf.test_count
                    cov.parametrize_variants += tf.parametrize_count

        test_files.append(tf)

    # Compute status
    for cov in coverage.values():
        if cov.test_count >= 5:
            cov.status = "COVERED"
        elif cov.test_count > 0:
            cov.status = "PARTIAL"
        else:
            cov.status = "UNCOVERED"

    return test_files, list(coverage.values())


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_coverage_table(
    modules: list[ModuleCoverage],
    show_uncovered_only: bool = False,
) -> None:
    if show_uncovered_only:
        modules = [m for m in modules if m.status == "UNCOVERED"]

    STATUS_ICON = {"COVERED": "[OK]", "PARTIAL": "[~]", "UNCOVERED": "[MISSING]"}
    W_PATH, W_PKG, W_ST = 56, 18, 10

    print(
        f"\n{'PATH':<{W_PATH}} {'PKG':<{W_PKG}} {'STATUS':<{W_ST}} {'TESTS':>6} {'PARAM':>5}  TEST FILES"
    )
    print("-" * 130)

    current_pkg = None
    for m in sorted(modules, key=lambda x: (x.package, x.path)):
        if m.package != current_pkg:
            if current_pkg is not None:
                print()
            current_pkg = m.package

        icon = STATUS_ICON.get(m.status, m.status)
        files_str = ", ".join(Path(t).name for t in m.test_files[:3])
        if len(m.test_files) > 3:
            files_str += f" +{len(m.test_files) - 3}"
        param_str = f"+{m.parametrize_variants}" if m.parametrize_variants else "-"

        print(
            f"  {m.path:<{W_PATH}} {m.package:<{W_PKG}} {icon:<{W_ST}}"
            f" {m.test_count:>6} {param_str:>5}  {files_str}"
        )

    total = len(modules)
    covered = sum(1 for m in modules if m.status == "COVERED")
    partial = sum(1 for m in modules if m.status == "PARTIAL")
    uncovered = sum(1 for m in modules if m.status == "UNCOVERED")
    pct = round(100 * (covered + partial) / total, 1) if total else 0
    total_fns = sum(m.test_count for m in modules)
    total_param = sum(m.parametrize_variants for m in modules)

    print("\n" + "-" * 130)
    print(
        f"  TOTAL {total}  |  COVERED {covered}  |  PARTIAL {partial}"
        f"  |  UNCOVERED {uncovered}  |  COVERAGE {pct}%"
        f"  |  TESTS {total_fns} (+{total_param} variants)"
    )


def print_orphans_table(test_files: list[TestFile]) -> None:
    orphans = [tf for tf in test_files if tf.is_orphan]
    print(f"\n  Orphan test files : {len(orphans)} (no resolved production target)")
    if not orphans:
        print("  (none)")
        return
    print(f"\n  {'TEST FILE':<65} {'TESTS':>6}")
    print("  " + "-" * 75)
    for tf in sorted(orphans, key=lambda x: x.path):
        print(f"  {tf.path:<65} {tf.test_count:>6}")


def print_hubs_uncovered(modules: list[ModuleCoverage], top_n: int = 15) -> None:
    """Modules with high hub score (many dependants) that are not covered."""
    uncovered_hubs = [
        m for m in modules if m.status in ("UNCOVERED", "PARTIAL") and m.dependants > 0
    ]
    uncovered_hubs.sort(key=lambda x: (-x.dependants, x.path))

    print(
        f"\n  Uncovered hubs (modules with dependants, no/partial tests) : {len(uncovered_hubs)}"
    )
    if not uncovered_hubs:
        print("  (none — all hubs are covered)")
        return
    print(f"\n  {'PATH':<55} {'PKG':<18} {'STATUS':<10} {'DEP':>4} {'TESTS':>6}")
    print("  " + "-" * 100)
    for m in uncovered_hubs[:top_n]:
        print(
            f"  {m.path:<55} {m.package:<18} {m.status:<10}"
            f" {m.dependants:>4} {m.test_count:>6}"
        )
    if len(uncovered_hubs) > top_n:
        print(f"  ... et {len(uncovered_hubs) - top_n} autres")


def print_test_files_table(test_files: list[TestFile]) -> None:
    W_PATH = 60
    print(f"\n{'TEST FILE':<{W_PATH}} {'TESTS':>6} {'PARAM':>5} {'ORPHAN':>6}  TARGETS")
    print("-" * 130)
    for tf in sorted(test_files, key=lambda x: x.path):
        orphan = "YES" if tf.is_orphan else "-"
        tgts = ", ".join(Path(t).name for t in tf.targets[:3])
        if len(tf.targets) > 3:
            tgts += f" +{len(tf.targets) - 3}"
        param_str = f"+{tf.parametrize_count}" if tf.parametrize_count else "-"
        print(
            f"  {tf.path:<{W_PATH}} {tf.test_count:>6} {param_str:>5} {orphan:>6}  {tgts}"
        )

    total_fns = sum(tf.test_count for tf in test_files)
    total_param = sum(tf.parametrize_count for tf in test_files)
    orphan_cnt = sum(1 for tf in test_files if tf.is_orphan)
    print("-" * 130)
    print(
        f"  {len(test_files)} files  |  {total_fns} tests"
        f"  |  +{total_param} variants  |  {orphan_cnt} orphans"
    )


def write_json(
    test_files: list[TestFile],
    modules: list[ModuleCoverage],
    output: Path,
) -> None:
    covered = sum(1 for m in modules if m.status == "COVERED")
    partial = sum(1 for m in modules if m.status == "PARTIAL")
    uncovered = sum(1 for m in modules if m.status == "UNCOVERED")
    total = len(modules)

    payload = {
        "summary": {
            "total_modules": total,
            "covered": covered,
            "partial": partial,
            "uncovered": uncovered,
            "coverage_pct": round(100 * (covered + partial) / total, 1) if total else 0,
            "total_test_files": len(test_files),
            "orphan_test_files": sum(1 for tf in test_files if tf.is_orphan),
            "total_test_functions": sum(tf.test_count for tf in test_files),
            "total_parametrize_variants": sum(
                tf.parametrize_count for tf in test_files
            ),
        },
        "uncovered_hubs": [
            {"path": m.path, "package": m.package, "dependants": m.dependants}
            for m in sorted(modules, key=lambda x: -x.dependants)
            if m.status in ("UNCOVERED", "PARTIAL") and m.dependants > 0
        ],
        "modules": [asdict(m) for m in sorted(modules, key=lambda x: x.path)],
        "test_files": [asdict(tf) for tf in sorted(test_files, key=lambda x: x.path)],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  Written -> {output.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Static test coverage scanner")
    parser.add_argument(
        "--uncovered", action="store_true", help="Show only uncovered modules"
    )
    parser.add_argument(
        "--pkg",
        dest="pkg_filter",
        default=None,
        help="Filter by package (e.g. --pkg audit)",
    )
    parser.add_argument(
        "--tests-only",
        action="store_true",
        help="List test files with targets and orphan status",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="Show orphan test files (no resolved target)",
    )
    parser.add_argument(
        "--hubs",
        action="store_true",
        help="Show uncovered hub modules (high dependants)",
    )
    parser.add_argument("--json", action="store_true", help="Write test_coverage.json")
    parser.add_argument(
        "--output",
        default="project_os/test_coverage.json",
        help="JSON output path (relative to project root)",
    )
    args = parser.parse_args()

    print("Scanning tests...")
    test_files, modules = scan_tests(pkg_filter=args.pkg_filter)

    if args.tests_only:
        print_test_files_table(test_files)
    elif args.orphans:
        print_orphans_table(test_files)
    elif args.hubs:
        print_hubs_uncovered(modules)
    else:
        print_coverage_table(modules, show_uncovered_only=args.uncovered)
        if not args.uncovered:
            print_orphans_table(test_files)

    if args.json:
        write_json(test_files, modules, ROOT / args.output)


if __name__ == "__main__":
    main()
