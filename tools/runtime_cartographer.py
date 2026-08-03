#!/usr/bin/env python3
"""Runtime Cartographer — instrument de mesure statique du système vivant.

MISSION J1-J2 (Chief Scientist, 2026-08-01).

Cet outil est PASSIF (ADR-0007) : il lit le dépôt, ne l'exécute pas, ne le
modifie pas. Il produit un JSON de mesures brutes qui sert de source unique
aux cinq documents de cartographie.

Portée et limites — À LIRE AVANT D'INTERPRÉTER LES RÉSULTATS
------------------------------------------------------------
Ce que l'outil mesure  : le graphe d'IMPORT statique (AST), y compris les
                         imports paresseux situés dans des corps de fonction,
                         la joignabilité depuis un point d'entrée, les cycles,
                         les composantes isolées, et des compteurs syntaxiques.

Ce que l'outil NE mesure PAS : l'exécution réelle. Un module joignable par
                         import peut n'être jamais appelé (import sous `if
                         False`, branche morte, garde `try/except ImportError`).
                         Prouver l'exécution exige une trace runtime
                         (`sys.settrace` / coverage sur le VPS) — hors périmètre
                         J1-J2. Tout module classé ACTIVE est donc
                         « ATTEIGNABLE PAR IMPORT », pas « EXÉCUTÉ ».

Usage :
    python tools/runtime_cartographer.py --out artifacts/cartography.json
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    "node_modules",
    "_ARCHIVE_2026",
    "archives",
    "backups",
    "frontend",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    ".claude",
}

# Point d'entrée du moteur réel, établi par lecture de scripts/deploy_vps.sh
# (le fichier cible du mode "core") — voir CONTRADICTION-01 pour l'écart avec
# scripts/crypto_advisor.service.
RUNTIME_ENTRY_POINTS = ["core.advisor_loop"]


# ─────────────────────────────────────────────────────────────────────────────
# Découverte des modules
# ─────────────────────────────────────────────────────────────────────────────


def discover_modules() -> dict[str, Path]:
    """module dotted-name -> chemin. Seuls les .py du projet."""
    modules: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
            if not parts:
                continue
        else:
            parts[-1] = parts[-1][:-3]
        modules[".".join(parts)] = path
    return modules


def is_test_module(name: str, path: Path) -> bool:
    parts = name.split(".")
    return (
        any(p == "tests" or p.startswith("test_") for p in parts)
        or path.name.startswith("test_")
        or path.name == "conftest.py"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Extraction des imports (AST — inclut les imports paresseux)
# ─────────────────────────────────────────────────────────────────────────────


def build_suffix_index(known: set[str]) -> dict[str, list[str]]:
    """Index des suffixes de modules.

    Nécessaire car le dépôt utilise des imports par NOM NU dépendants de
    sys.path (ex. `core/advisor_loop.py:33` fait
    `from advisor_runtime_adapters import ...` et non
    `from core.advisor_runtime_adapters import ...`). Sans cet index, la façade
    runtime et tout son sous-graphe sont invisibles. Voir CONTRADICTION-02.
    """
    idx: dict[str, list[str]] = defaultdict(list)
    for mod in known:
        parts = mod.split(".")
        for i in range(len(parts)):
            idx[".".join(parts[i:])].append(mod)
    return idx


def extract_imports(
    path: Path,
    known: set[str],
    suffix_idx: dict[str, list[str]] | None = None,
    ambiguous: set[str] | None = None,
) -> tuple[set[str], set[str], int]:
    """-> (imports_projet, imports_bruts_non_resolus, nb_imports_paresseux)

    Un import est « paresseux » s'il n'est pas au niveau module (col_offset > 0),
    c.-à-d. situé dans une fonction, une méthode ou un bloc try.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set(), {"<SYNTAX_ERROR>"}, 0

    resolved: set[str] = set()
    unresolved: set[str] = set()
    lazy = 0

    def resolve(dotted: str) -> None:
        """a.b.c -> a.b -> a, puis repli sur l'index des suffixes (imports nus)."""
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in known:
                resolved.add(cand)
                return
        if suffix_idx is not None:
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                hits = suffix_idx.get(cand)
                if hits:
                    if len(hits) > 1 and ambiguous is not None:
                        ambiguous.add(cand)
                    resolved.update(hits)
                    return
        unresolved.add(parts[0])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if node.col_offset > 0:
                lazy += 1
            for alias in node.names:
                resolve(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.col_offset > 0:
                lazy += 1
            if node.level:  # import relatif — non résolu (rare dans ce dépôt)
                continue
            if node.module:
                resolve(node.module)
                for alias in node.names:
                    resolve(f"{node.module}.{alias.name}")

    return resolved, unresolved, lazy


# ─────────────────────────────────────────────────────────────────────────────
# Graphe : joignabilité, cycles, composantes
# ─────────────────────────────────────────────────────────────────────────────


def reachable_from(graph: dict[str, set[str]], roots: list[str]) -> set[str]:
    seen: set[str] = set()
    stack = [r for r in roots if r in graph]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, set()) - seen)
    return seen


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Composantes fortement connexes de taille > 1 (Tarjan itératif)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    counter = [0]
    sccs: list[list[str]] = []

    for root in list(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph.get(root, set()))))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack[root] = True
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in graph:
                    continue
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack[child] = True
                    work.append((child, iter(sorted(graph.get(child, set())))))
                    advanced = True
                    break
                if on_stack.get(child):
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1:
                    sccs.append(sorted(comp))
    return sccs


# ─────────────────────────────────────────────────────────────────────────────
# Compteurs syntaxiques (grep AST/texte, jamais estimés)
# ─────────────────────────────────────────────────────────────────────────────

TOKENS = {
    "state_machines": ("class ", ("StateMachine",)),
    "kill_switch_defs": ("class ", ("KillSwitch",)),
}


def count_authority_artifacts(modules: dict[str, Path]) -> dict:
    """Compte, avec fichier:ligne, les artefacts d'autorité."""
    out: dict[str, list] = {
        "state_machine_classes": [],
        "kill_switch_classes": [],
        "safe_mode_files": [],
        "trade_allowed_writes": [],
        "gate_classes": [],
        "decision_packet_defs": [],
    }
    for name, path in sorted(modules.items()):
        if is_test_module(name, path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        has_safe_mode = False
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("class ") and "StateMachine" in s:
                out["state_machine_classes"].append(
                    {
                        "module": name,
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "code": s[:110],
                    }
                )
            if s.startswith("class ") and "KillSwitch" in s:
                out["kill_switch_classes"].append(
                    {
                        "module": name,
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "code": s[:110],
                    }
                )
            if s.startswith("class ") and "Gate" in s:
                out["gate_classes"].append(
                    {
                        "module": name,
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "code": s[:110],
                    }
                )
            if s.startswith("class DecisionPacket"):
                out["decision_packet_defs"].append(
                    {
                        "module": name,
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "code": s[:110],
                    }
                )
            if "SAFE_MODE" in line:
                has_safe_mode = True
            # écriture de trade_allowed : affectation simple ou par clé
            stripped = s.replace(" ", "")
            if (
                stripped.startswith("trade_allowed=")
                or stripped.startswith('r["trade_allowed"]=')
                or stripped.startswith("r['trade_allowed']=")
                or '["trade_allowed"]=' in stripped
                or "['trade_allowed']=" in stripped
            ):
                if "==" in stripped.split("=", 1)[0] + "=":
                    pass
                out["trade_allowed_writes"].append(
                    {
                        "module": name,
                        "file": str(path.relative_to(ROOT)),
                        "line": i,
                        "code": s[:110],
                    }
                )
        if has_safe_mode:
            out["safe_mode_files"].append(
                {"module": name, "file": str(path.relative_to(ROOT))}
            )
    return out


def git_last_commit_map() -> dict[str, str]:
    """Date du dernier commit touchant chaque fichier — un seul appel git.

    `git log --name-only` parcourt l'historique du plus récent au plus ancien ;
    la première occurrence d'un chemin est donc sa date la plus récente.
    """
    out: dict[str, str] = {}
    try:
        r = subprocess.run(
            ["git", "log", "--name-only", "--format=@%ad", "--date=short"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception:
        return out
    current = "UNKNOWN"
    for line in r.stdout.splitlines():
        if line.startswith("@"):
            current = line[1:].strip()
        elif line.strip():
            out.setdefault(line.strip().replace("\\", "/"), current)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────


def classify(
    name: str,
    path: Path,
    *,
    runtime_reach: set[str],
    test_reach: set[str],
    entry_points: set[str],
    importers: set[str],
    has_main: bool,
) -> tuple[str, str]:
    """-> (statut, justification). Statuts : ACTIVE / ENTRYPOINT / TEST_ONLY /
    TOOL / ORPHAN."""
    if name in entry_points:
        return "ENTRYPOINT", "point d'entrée runtime déclaré"
    if is_test_module(name, path):
        return "TEST", "module de test"
    if name in runtime_reach:
        return "ACTIVE", "atteignable par import depuis le point d'entrée runtime"
    if has_main and not importers:
        return "TOOL", "script autonome (__main__), jamais importé"
    if name in test_reach:
        return "TEST_ONLY", "atteignable uniquement depuis les tests"
    if importers:
        return "ORPHAN", f"importé par {len(importers)} module(s), tous hors runtime"
    return "ORPHAN", "aucun importeur, aucun __main__"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/cartography.json")
    args = ap.parse_args()

    modules = discover_modules()
    known = set(modules)

    graph: dict[str, set[str]] = {}
    reverse: dict[str, set[str]] = defaultdict(set)
    lazy_counts: dict[str, int] = {}
    external: dict[str, set[str]] = {}

    suffix_idx = build_suffix_index(known)
    ambiguous: set[str] = set()

    for name, path in modules.items():
        deps, ext, lazy = extract_imports(path, known, suffix_idx, ambiguous)
        deps.discard(name)
        graph[name] = deps
        lazy_counts[name] = lazy
        external[name] = ext
        for d in deps:
            reverse[d].add(name)

    entry_points = set(RUNTIME_ENTRY_POINTS) & known
    runtime_reach = reachable_from(graph, sorted(entry_points))

    test_roots = [n for n, p in modules.items() if is_test_module(n, p)]
    test_reach = reachable_from(graph, test_roots) - runtime_reach

    has_main: dict[str, bool] = {}
    for name, path in modules.items():
        try:
            has_main[name] = "__main__" in path.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            has_main[name] = False

    commit_map = git_last_commit_map()

    records = []
    for name, path in sorted(modules.items()):
        status, why = classify(
            name,
            path,
            runtime_reach=runtime_reach,
            test_reach=test_reach,
            entry_points=entry_points,
            importers=reverse.get(name, set()),
            has_main=has_main[name],
        )
        records.append(
            {
                "module": name,
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "status": status,
                "justification": why,
                "imports_project": sorted(graph[name]),
                "imported_by": sorted(reverse.get(name, set())),
                "lazy_imports": lazy_counts[name],
                "loc": len(
                    path.read_text(encoding="utf-8", errors="replace").splitlines()
                ),
                "last_commit": commit_map.get(
                    str(path.relative_to(ROOT)).replace("\\", "/"), "UNTRACKED"
                ),
                "top_package": name.split(".")[0],
            }
        )

    cycles = find_cycles(graph)

    # composantes isolées : ni runtime, ni test, ni importeur
    isolated = [
        r["module"] for r in records if not r["imported_by"] and r["status"] == "ORPHAN"
    ]

    payload = {
        "meta": {
            "generated_by": "tools/runtime_cartographer.py",
            "root": str(ROOT),
            "runtime_entry_points": sorted(entry_points),
            "excluded_dirs": sorted(EXCLUDED_DIRS),
            "measurement_scope": "import statique (AST), imports paresseux inclus",
            "NOT_measured": "exécution réelle — exige une trace runtime",
        },
        "totals": {
            "modules_total": len(modules),
            "modules_runtime_reachable": len(runtime_reach),
            "modules_test_only": sum(1 for r in records if r["status"] == "TEST_ONLY"),
            "modules_tool": sum(1 for r in records if r["status"] == "TOOL"),
            "modules_orphan": sum(1 for r in records if r["status"] == "ORPHAN"),
            "modules_test": sum(1 for r in records if r["status"] == "TEST"),
            "import_cycles": len(cycles),
            "isolated_modules": len(isolated),
            "ambiguous_bare_imports": len(ambiguous),
        },
        "ambiguous_bare_imports": sorted(ambiguous),
        "authority": count_authority_artifacts(modules),
        "cycles": cycles,
        "isolated": sorted(isolated),
        "modules": records,
    }

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["totals"], indent=2))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
