#!/usr/bin/env python3
"""
dep_mapper.py  --  Graphe oriente des dependances, cycles, orphelins & hubs.

Enrichissements v2 :
  - Distinction imports top-level vs lazy (inside functions/methods)
    -> elimine les faux positifs de cycles (ex: event_bus/bridge.py)
  - Coupling score par package (in-degree + out-degree)
  - Severite des cycles (CRITICAL si hub implique, WARNING sinon)
  - Lazy imports reportes separement

Utilisation :
  python project_os/dep_mapper.py                         # table recapitulative
  python project_os/dep_mapper.py --json                  # -> project_os/dep_graph.json
  python project_os/dep_mapper.py --cycles-only           # uniquement les cycles
  python project_os/dep_mapper.py --lazy                  # inclut les imports lazy
  python project_os/dep_mapper.py --pkg quant_hedge_ai    # sous-graphe d'un package
  python project_os/dep_mapper.py --dot                   # export Graphviz
  python project_os/dep_mapper.py --module                # granularite fichier
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".egg-info",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    "_legacy",
}


def _skip(p: Path) -> bool:
    return any(part.startswith(".") or part in SKIP_DIRS for part in p.parts)


def discover_py_files(root: Path) -> list[Path]:
    return sorted(f for f in root.rglob("*.py") if not _skip(f))


def _module_path(file_path: Path, root: Path) -> str:
    rel = file_path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _package_of(module_name: str) -> str:
    return module_name.split(".")[0]


_STDLIB_CACHE: set[str] | None = None


def _stdlib_names() -> set[str]:
    global _STDLIB_CACHE
    if _STDLIB_CACHE is None:
        _STDLIB_CACHE = (
            set(sys.stdlib_module_names)
            if hasattr(sys, "stdlib_module_names")
            else set()
        )
        if not _STDLIB_CACHE:
            _STDLIB_CACHE = set(sys.builtin_module_names)
    return _STDLIB_CACHE


# ---------------------------------------------------------------------------
# Import extraction — top-level vs lazy
# ---------------------------------------------------------------------------


def _collect_import_names(
    nodes: list[ast.stmt], root: Path, file_path: Path
) -> set[str]:
    """Extract import names from a flat list of AST statements."""
    stdlib = _stdlib_names()
    result: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in stdlib:
                    result.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level:
                current_mod = _module_path(file_path, root)
                parts = current_mod.split(".")
                up = node.level
                if up <= len(parts):
                    base = parts[:-up]
                    resolved = ".".join(base + ([node.module] if node.module else []))
                else:
                    resolved = node.module
            else:
                resolved = node.module
            top = resolved.split(".")[0]
            if top not in stdlib:
                result.add(resolved)
    return result


def extract_imports(
    file_path: Path, root: Path, include_lazy: bool = False
) -> set[str]:
    """
    Return import names from file_path.

    By default only top-level (module-scope) imports are returned.
    Set include_lazy=True to also include imports inside functions/classes.

    Rationale: lazy imports inside methods (e.g. inside try/except of a
    classmethod) are intentionally deferred to break circular dependencies
    at runtime. Including them in the static graph produces false-positive
    cycles.
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    # Top-level = direct children of ast.Module
    top_level = _collect_import_names(tree.body, root, file_path)

    if not include_lazy:
        return top_level

    # Lazy = all imports minus top-level
    all_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                t = alias.name.split(".")[0]
                if t not in _stdlib_names():
                    all_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                t = node.module.split(".")[0]
                if t not in _stdlib_names():
                    all_imports.add(node.module)
    return all_imports


def extract_lazy_imports(file_path: Path, root: Path) -> set[str]:
    """Return only the lazy (non-top-level) imports for a file."""
    all_imps = extract_imports(file_path, root, include_lazy=True)
    top_imps = extract_imports(file_path, root, include_lazy=False)
    return all_imps - top_imps


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def resolve_local(imported_name: str, known_modules: set[str]) -> str | None:
    parts = imported_name.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in known_modules:
            return candidate
    return None


def resolve_top(imported_name: str, known_packages: set[str]) -> str | None:
    top = imported_name.split(".")[0]
    return top if top in known_packages else None


# ---------------------------------------------------------------------------
# Cycle detection (Tarjan SCC)
# ---------------------------------------------------------------------------


def tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True
        for w in graph.get(v, set()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1 or v in graph.get(v, set()):
                sccs.append(scc)

    for v in list(graph.keys()):
        if v not in index:
            strongconnect(v)
    return sccs


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_hubs(graph: dict[str, set[str]]) -> list[dict[str, Any]]:
    dependants: dict[str, int] = defaultdict(int)
    for src, targets in graph.items():
        for tgt in targets:
            dependants[tgt] += 1
    all_nodes = set(graph.keys()) | set(dependants.keys())
    return sorted(
        [
            {
                "module": m,
                "dependants": dependants.get(m, 0),
                "dependencies": len(graph.get(m, set())),
                "coupling_score": dependants.get(m, 0) + len(graph.get(m, set())),
            }
            for m in all_nodes
        ],
        key=lambda x: -x["dependants"],
    )


def find_orphans(graph: dict[str, set[str]], all_modules: set[str]) -> list[str]:
    has_deps = {m for m, d in graph.items() if d}
    is_depended: set[str] = set()
    for targets in graph.values():
        is_depended.update(targets)
    return sorted(all_modules - has_deps - is_depended)


def annotate_cycle_severity(
    cycles: list[list[str]], hubs: list[dict[str, Any]], top_n: int = 5
) -> list[dict[str, Any]]:
    """Tag each cycle CRITICAL if it involves a top hub, WARNING otherwise."""
    top_hub_names = {h["module"] for h in hubs[:top_n]}
    annotated = []
    for cycle in cycles:
        involves_hub = any(m in top_hub_names for m in cycle)
        annotated.append(
            {
                "members": sorted(cycle),
                "severity": "CRITICAL" if involves_hub else "WARNING",
                "size": len(cycle),
            }
        )
    return sorted(annotated, key=lambda x: (x["severity"] == "WARNING", -x["size"]))


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------


def build_report(
    root: Path,
    scope: str | None = None,
    package_level: bool = True,
    include_lazy: bool = False,
) -> dict[str, Any]:
    files = discover_py_files(root)
    known_modules = {_module_path(f, root) for f in files}
    packages = {m.split(".")[0] for m in known_modules if "." in m}

    graph_pkg: dict[str, set[str]] = defaultdict(set)
    graph_mod: dict[str, set[str]] = defaultdict(set)
    lazy_pkg: dict[str, set[str]] = defaultdict(set)  # lazy-only edges

    for f in files:
        source_mod = _module_path(f, root)
        source_pkg = _package_of(source_mod)

        top_imports = extract_imports(f, root, include_lazy=False)
        lazy_imports = extract_lazy_imports(f, root) if include_lazy else set()

        for imp in top_imports:
            local_mod = resolve_local(imp, known_modules)
            if local_mod:
                graph_mod[source_mod].add(local_mod)
            local_pkg = resolve_top(imp, packages)
            if local_pkg and local_pkg != source_pkg:
                graph_pkg[source_pkg].add(local_pkg)

        for imp in lazy_imports:
            local_pkg = resolve_top(imp, packages)
            if local_pkg and local_pkg != source_pkg:
                lazy_pkg[source_pkg].add(local_pkg)

    for k in list(graph_mod):
        graph_mod[k].discard(k)
    for k in list(graph_pkg):
        graph_pkg[k].discard(k)

    if scope:
        scope_graph: dict[str, set[str]] = {}
        target_modules = {m for m in known_modules if m.startswith(scope)}
        for mod in target_modules:
            deps = {d for d in graph_mod.get(mod, set()) if d.startswith(scope)}
            if deps:
                scope_graph[mod] = deps
        graph: dict[str, set[str]] = scope_graph
        all_nodes = set(scope_graph.keys()) | {
            d for v in scope_graph.values() for d in v
        }
    elif package_level:
        graph = dict(graph_pkg)
        all_nodes = set(graph.keys()) | {d for v in graph.values() for d in v}
    else:
        graph = dict(graph_mod)
        all_nodes = set(graph.keys()) | {d for v in graph.values() for d in v}

    cycles_raw = tarjan_scc(graph)
    hubs = compute_hubs(graph)
    cycles = annotate_cycle_severity(cycles_raw, hubs)
    orphans = find_orphans(graph, all_nodes)

    # Lazy edges that would create cycles if included (informational)
    lazy_cycle_candidates: list[str] = []
    for src, targets in lazy_pkg.items():
        for tgt in targets:
            if tgt in graph and src in (graph.get(tgt) or set()):
                lazy_cycle_candidates.append(f"{src} <-> {tgt} (lazy in {src})")

    return {
        "metadata": {
            "total_files": len(files),
            "total_modules": len(known_modules),
            "total_packages": len(packages),
            "scope": scope or ("package" if package_level else "module"),
            "include_lazy": include_lazy,
        },
        "graph": {k: sorted(v) for k, v in sorted(graph.items())},
        "cycles": cycles,
        "lazy_cycle_candidates": lazy_cycle_candidates,
        "hubs": hubs[:20],
        "orphans": orphans,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _print_table(report: dict[str, Any]) -> None:
    r = report["metadata"]
    print("=" * 65)
    print(
        f"  Dep Mapper -- {r.get('scope', 'package')} level"
        + (" [+lazy]" if r.get("include_lazy") else "")
    )
    print(
        f"  {r['total_files']} fichiers  |  {r['total_modules']} modules  |  {r['total_packages']} packages"
    )
    print("=" * 65)

    cycles = report["cycles"]
    critical = [c for c in cycles if c["severity"] == "CRITICAL"]
    warnings = [c for c in cycles if c["severity"] == "WARNING"]
    print(
        f"\n  Cycles : {len(cycles)}  (CRITICAL: {len(critical)}, WARNING: {len(warnings)})"
    )
    for c in cycles:
        tag = "[CRIT]" if c["severity"] == "CRITICAL" else "[WARN]"
        print(f"    {tag}  {' -> '.join(c['members'])}")

    lazy_cands = report.get("lazy_cycle_candidates", [])
    if lazy_cands:
        print(f"\n  Lazy-import pseudo-cycles ({len(lazy_cands)}) :")
        for lc in lazy_cands:
            print(f"    [lazy]  {lc}")

    hubs = report["hubs"]
    print(f"\n  Top hubs (dependants) :")
    if hubs:
        print(f"    {'Module':<35} {'In':>4} {'Out':>4} {'Coupling':>8}")
        print(f"    {'-'*35} {'-'*4} {'-'*4} {'-'*8}")
        for h in hubs[:10]:
            print(
                f"    {h['module']:<35} {h['dependants']:>4} {h['dependencies']:>4} {h['coupling_score']:>8}"
            )

    orphans = report["orphans"]
    print(f"\n  Modules orphelins : {len(orphans)}")
    for o in orphans[:12]:
        print(f"    . {o}")
    if len(orphans) > 12:
        print(f"    ... et {len(orphans) - 12} autres")

    g = report["graph"]
    n_edges = sum(len(v) for v in g.values())
    print(f"\n  Graphe : {len(g)} noeuds, {n_edges} aretes")
    print("=" * 65)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    root = Path.cwd()
    scope = None
    package_level = True
    output_json = False
    cycles_only = False
    dot_export = False
    mod_level = False
    include_lazy = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            output_json = True
        elif a == "--cycles-only":
            cycles_only = True
        elif a == "--dot":
            dot_export = True
        elif a == "--module":
            mod_level = True
            package_level = False
        elif a == "--lazy":
            include_lazy = True
        elif a == "--pkg" and i + 1 < len(args):
            scope = args[i + 1]
            i += 1
        elif a == "--root" and i + 1 < len(args):
            root = Path(args[i + 1])
            i += 1
        i += 1

    report = build_report(
        root,
        scope=scope,
        package_level=(package_level and not mod_level),
        include_lazy=include_lazy,
    )

    if cycles_only:
        cycles = report["cycles"]
        lazy_cands = report.get("lazy_cycle_candidates", [])
        if cycles:
            print(f"{len(cycles)} cycle(s) detecte(s):\n")
            for c in cycles:
                tag = "[CRITICAL]" if c["severity"] == "CRITICAL" else "[WARNING]"
                print(f"  {tag}  {' -> '.join(c['members'])}\n")
        else:
            print("Aucun cycle (imports top-level).")
        if lazy_cands:
            print(f"\n{len(lazy_cands)} lazy-import pseudo-cycle(s) (non bloquants):")
            for lc in lazy_cands:
                print(f"  [lazy]  {lc}")
        return

    if dot_export:
        lines = [
            "digraph G {",
            '  rankdir="LR";',
            '  node [shape="box", style="rounded"];',
        ]
        for src, targets in report["graph"].items():
            for tgt in targets:
                lines.append(f'  "{src}" -> "{tgt}";')
        lines.append("}")
        out_path = root / "project_os" / "dep_graph.dot"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"-> {out_path}")
        return

    if output_json:
        out_path = root / "project_os" / "dep_graph.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        def set_default(obj: Any) -> Any:
            if isinstance(obj, set):
                return sorted(obj)
            raise TypeError

        out_path.write_text(
            json.dumps(report, indent=2, default=set_default), encoding="utf-8"
        )
        print(f"-> {out_path}")
        return

    _print_table(report)


if __name__ == "__main__":
    main()
