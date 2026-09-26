#!/usr/bin/env python3
"""
research_boundary_auditor — outil de MESURE statique, lecture seule.

Objet : vérifier mécaniquement, sur des chemins donnés, les invariants
déclarés par la doctrine Research Lab (#237/#239) et par ADR-0007
(passivité des observers) :

  1. `runtime_coupling`   — import d'une surface runtime/mutable interdite
                            à un moteur de replay offline (durable store,
                            authority runtime, advisor_loop, simulateur,
                            exécution, DIPStore, réseau, Telegram,
                            subprocess).
  2. `nondeterminism`     — horloge murale, uuid aléatoire, PID, hostname,
                            random : interdits dans une identité de run
                            déterministe (`research_run_id`).
  3. `evidence_erasure`   — `... or 0` / `.get(..., 0)` : transforme un
                            UNKNOWN/UNRESOLVED en 0 mesuré, ce qui viole
                            « UNKNOWN != 0 ».
  4. `silent_except`      — `except Exception: pass` : perte de fait sans
                            trace.
  5. `nonfinite_json`     — `json.dump(s)` sans `allow_nan=False` : peut
                            sérialiser NaN/Infinity, non canonique pour un
                            digest SHA-256 reproductible.
  6. `package_cycles`     — cycles d'import simples entre sous-paquets d'un
                            même paquet (complète tests/test_architecture.py
                            qui ne couvre que `src/`).

L'outil n'importe RIEN du projet : il fait de l'AST pur (stdlib), n'écrit
aucun fichier du dépôt et ne touche ni runtime, ni PPL, ni PAPER, ni VPS.
Il ne rend aucun verdict de gouvernance : il produit des faits localisés
(fichier:ligne) qu'un humain classe REUSABLE / ADAPTER_REQUIRED / FORBIDDEN.

Usage :
    python tools/research_boundary_auditor.py paper_trading financial_institute
    python tools/research_boundary_auditor.py --json src/backtest
    python tools/research_boundary_auditor.py --cycles src core
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent

SKIP_PARTS = {"__pycache__", "_ARCHIVE_2026", "_old", "_legacy", "node_modules", ".venv"}

NONDET_CALLS = {
    "time.time",
    "time.monotonic",
    "time.perf_counter",
    "time.time_ns",
    "datetime.now",
    "datetime.utcnow",
    "date.today",
    "uuid.uuid1",
    "uuid.uuid4",
    "os.getpid",
    "socket.gethostname",
    "random.random",
    "random.randint",
    "random.choice",
    "random.uniform",
}
NONDET_BARE = {"now_us", "utcnow", "monotonic_ns"}

FORBIDDEN_RUNTIME = (
    "advisor_loop",
    "ppl_authority_runtime",
    "ppl_authority_gate",
    "durable_event_store",
    "mexc_simulator",
    "execution_engine",
    "telegram",
    "requests",
    "httpx",
    "ccxt",
    "websocket",
    "websockets",
    "aiohttp",
    "subprocess",
    "smtplib",
    "dip.core.store",
    "DIPStore",
)


def iter_py(paths: Iterable[str]) -> Iterator[Path]:
    for raw in paths:
        p = (ROOT / raw) if not Path(raw).is_absolute() else Path(raw)
        if p.is_file() and p.suffix == ".py":
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if SKIP_PARTS.isdisjoint(f.parts):
                    yield f


def dotted(node: ast.AST) -> str:
    parts: List[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def imported_modules(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        base = node.module or ""
        return [base] + [f"{base}.{a.name}" if base else a.name for a in node.names]
    return []


def scan_file(path: Path) -> Dict[str, List[str]]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - I/O dépend de l'environnement
        return {"unreadable": [f"{path}: {exc}"]}
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return {"syntax_error": [f"{path}:{exc.lineno}: {exc.msg}"]}

    out: Dict[str, List[str]] = defaultdict(list)
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            tail = ".".join(name.split(".")[-2:])
            if name in NONDET_CALLS or tail in NONDET_CALLS or name.split(".")[-1] in NONDET_BARE:
                out["nondeterminism"].append(f"{rel}:{node.lineno}: {name}()")
            if dotted(node.func).endswith(("json.dump", "json.dumps")):
                if "allow_nan" not in {kw.arg for kw in node.keywords}:
                    out["nonfinite_json"].append(
                        f"{rel}:{node.lineno}: json dump sans allow_nan=False"
                    )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) == 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in (0, 0.0)
                and not isinstance(node.args[1].value, bool)
            ):
                out["evidence_erasure"].append(
                    f"{rel}:{node.lineno}: .get(..., {node.args[1].value!r}) masque UNKNOWN"
                )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in imported_modules(node):
                pieces = module.split(".")
                for bad in FORBIDDEN_RUNTIME:
                    if module == bad or bad in pieces or module.endswith("." + bad):
                        out["runtime_coupling"].append(f"{rel}:{node.lineno}: importe {module}")
                        break
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            last = node.values[-1]
            if (
                isinstance(last, ast.Constant)
                and last.value in (0, 0.0)
                and not isinstance(last.value, bool)
            ):
                out["evidence_erasure"].append(
                    f"{rel}:{node.lineno}: `... or {last.value!r}` masque UNKNOWN"
                )
        elif isinstance(node, ast.ExceptHandler):
            broad = node.type is None or (
                isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
            )
            silent = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
            if broad and silent:
                out["silent_except"].append(f"{rel}:{node.lineno}: except large silencieux")

    return dict(out)


def package_cycles(package: str) -> List[Tuple[str, str]]:
    edges: Dict[str, Set[str]] = defaultdict(set)
    for f in iter_py([package]):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        module = f.relative_to(ROOT).as_posix()[:-3].replace("/", ".")
        source_sub = ".".join(module.split(".")[:2])
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            for t in targets:
                sub = ".".join(t.split(".")[:2])
                if "." in sub and sub.split(".")[0] == package and sub != source_sub:
                    edges[source_sub].add(sub)
    found = {
        tuple(sorted((a, b)))
        for a, outs in edges.items()
        for b in outs
        if a in edges.get(b, set())
    }
    return sorted(found)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="fichiers ou répertoires à auditer (relatifs au dépôt)")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--cycles", action="store_true", help="chercher aussi les cycles d'import par paquet")
    parser.add_argument("--per-file", action="store_true", help="détailler par fichier au lieu d'agréger")
    args = parser.parse_args(argv)

    files = list(iter_py(args.paths))
    per_file: Dict[str, Dict[str, List[str]]] = {}
    aggregated: Dict[str, List[str]] = defaultdict(list)
    for f in files:
        findings = scan_file(f)
        rel = f.relative_to(ROOT).as_posix() if f.is_relative_to(ROOT) else f.as_posix()
        per_file[rel] = findings
        for key, items in findings.items():
            aggregated[key].extend(items)

    report: Dict[str, object] = {
        "files_scanned": len(files),
        "counts": {k: len(v) for k, v in sorted(aggregated.items())},
        "findings": {k: sorted(v) for k, v in sorted(aggregated.items())},
    }
    if args.per_file:
        report["per_file"] = {
            k: {kk: len(vv) for kk, vv in v.items()} for k, v in sorted(per_file.items())
        }
    if args.cycles:
        roots = sorted({p.split("/")[0] for p in args.paths if (ROOT / p.split("/")[0]).is_dir()})
        report["package_cycles"] = {r: [list(c) for c in package_cycles(r)] for r in roots}

    if args.json:
        print(json.dumps(report, indent=1, ensure_ascii=False))
        return 0

    print(f"research_boundary_auditor — {len(files)} fichier(s) analysé(s)")
    if not aggregated:
        print("  aucun signal (surface conforme aux invariants scannés)")
    for key, items in sorted(aggregated.items()):
        print(f"\n== {key} ({len(items)})")
        for item in sorted(items):
            print(f"   {item}")
    if args.per_file:
        print("\n== par fichier")
        for rel, findings in sorted(per_file.items()):
            summary = ", ".join(f"{k}={len(v)}" for k, v in sorted(findings.items())) or "CLEAN"
            print(f"   {rel}: {summary}")
    if args.cycles:
        print("\n== cycles d'import")
        for pkg, cycles in sorted(report["package_cycles"].items()):  # type: ignore[union-attr]
            print(f"   {pkg}: {cycles or 'aucun'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
