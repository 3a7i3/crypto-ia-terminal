#!/usr/bin/env python3
"""
default_path_audit.py — Garde-fou CI de la règle DS-001 (ADR-0008)

Sprint S4-C. Scanne le dépôt (AST, aucune exécution du code audité) et
détecte les violations de DS-001 ainsi que la règle renforcée :

    « Aucun module ne doit provoquer d'effet de bord sur le système
      de fichiers lors de son import. »

Détections et sévérités :
  CRITICAL  effet de bord filesystem à l'import : open()/mkdir()/
            sqlite3.connect()/write_text()/FileHandler() au niveau module
  CRITICAL  défaut de signature contenant un chemin de données
            (ex: def save(self, path="databases/x.jsonl"))
  HIGH      constante de module dépendant de l'environnement
            (ex: _PATH = Path(os.getenv("X", "databases/x.jsonl")))
  MEDIUM    constante de module = chemin de données littéral
  MEDIUM    Path(__file__) au niveau module (ancrage chdir-immune)
  INFO      os.getenv de *_PATH/*_DIR au niveau module (hors Path)

Usage :
  python scripts/default_path_audit.py [racine] [--fail-on HIGH]
Exit : 0 = propre, 1 = violations >= seuil, 2 = erreur.

Baseline : les violations connues et acceptées (en attente de correctif
code) peuvent être listées dans scripts/default_path_audit_baseline.txt
(une par ligne, format "chemin/fichier.py:ligne") — elles sont alors
rapportées mais n'entraînent pas d'échec.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Répertoires de données considérés sensibles dans les chemins littéraux
DATA_PREFIXES = ("databases/", "cache/", "logs/", "reports/", "results/")

# Répertoires exclus du scan
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "_ARCHIVE_2026",
    "_old",
    "_legacy",
    "archives",
    ".pytest_cache",
    "dist",
    "build",
}
# Les tests et conftest ont le droit de manipuler chemins/env
EXCLUDE_FILE_HINTS = (
    "test_",
    "conftest",
)

SEVERITY_ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "INFO": 0}

# Appels considérés comme effets de bord filesystem
SIDE_EFFECT_CALLS = {
    "open",
    "mkdir",
    "makedirs",
    "connect",
    "write_text",
    "write_bytes",
    "touch",
    "unlink",
    "rename",
    "replace",
    "FileHandler",
    "RotatingFileHandler",
    "TimedRotatingFileHandler",
    "basicConfig",
}


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _contains_data_path_literal(node: ast.AST) -> str | None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub.value.startswith(DATA_PREFIXES):
                return sub.value
    return None


def _contains_call(node: ast.AST, names: set[str]) -> str | None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_name(sub) in names:
            return _call_name(sub)
    return None


def _contains_file_anchor(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "__file__":
            return True
    return False


class Finding:
    def __init__(self, severity: str, path: Path, line: int, message: str):
        self.severity, self.path, self.line, self.message = (
            severity,
            path,
            line,
            message,
        )

    @property
    def key(self) -> str:
        return f"{self.path.as_posix()}:{self.line}"

    def __str__(self) -> str:
        return f"[{self.severity:<8}] {self.key}\n            {self.message}"


def audit_module_level(tree: ast.Module, path: Path) -> list[Finding]:
    """Analyse les nœuds de niveau module (imports exécutés)."""
    findings: list[Finding] = []
    # niveau module = body direct + corps des if de niveau module
    top_nodes: list[ast.stmt] = []
    stack = list(tree.body)
    while stack:
        n = stack.pop(0)
        top_nodes.append(n)
        if isinstance(n, (ast.If, ast.Try)):
            stack = (
                n.body + getattr(n, "orelse", []) + getattr(n, "finalbody", []) + stack
            )

    for node in top_nodes:
        # Effet de bord à l'import : appel direct en expression ou dans
        # une assignation de niveau module
        if isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign)):
            side = _contains_call(node, SIDE_EFFECT_CALLS)
            if side:
                # sign_state etc. faux positifs possibles — on cible fichier
                findings.append(
                    Finding(
                        "CRITICAL",
                        path,
                        node.lineno,
                        f"effet de bord filesystem potentiel à l'import: "
                        f"{side}() au niveau module (règle DS-001 renforcée)",
                    )
                )
                continue

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is None:
                continue
            lit = _contains_data_path_literal(value)
            has_getenv = _contains_call(value, {"getenv", "environ"}) or any(
                isinstance(s, ast.Subscript)
                and isinstance(getattr(s.value, "attr", None), str)
                for s in ast.walk(value)
            )
            has_path = _contains_call(value, {"Path"})
            if lit and has_getenv and has_path:
                findings.append(
                    Finding(
                        "HIGH",
                        path,
                        node.lineno,
                        f"constante de module figée à l'import depuis l'env "
                        f"(défaut: '{lit}') — monkeypatch.setenv inopérant "
                        f"(DS-001 variante 2)",
                    )
                )
            elif lit and has_path:
                findings.append(
                    Finding(
                        "MEDIUM",
                        path,
                        node.lineno,
                        f"constante de module = chemin de données '{lit}' "
                        f"(DS-001 variante 2, sans env)",
                    )
                )
            elif has_path and _contains_file_anchor(value):
                findings.append(
                    Finding(
                        "MEDIUM",
                        path,
                        node.lineno,
                        "Path(__file__) au niveau module — ancrage absolu "
                        "immune au chdir (DS-001 variante 3) ; acceptable "
                        "en lecture seule, à vérifier si écrit",
                    )
                )
            elif has_getenv and lit is None:
                # env var de chemin sans Path — informatif
                for sub in ast.walk(value):
                    if (
                        isinstance(sub, ast.Call)
                        and _call_name(sub) == "getenv"
                        and sub.args
                        and isinstance(sub.args[0], ast.Constant)
                        and isinstance(sub.args[0].value, str)
                        and sub.args[0].value.endswith(("_PATH", "_DIR", "_FILE"))
                    ):
                        findings.append(
                            Finding(
                                "INFO",
                                path,
                                node.lineno,
                                f"env de chemin '{sub.args[0].value}' lue à "
                                f"l'import — vérifier qu'elle n'est pas "
                                f"figée pour la durée du process",
                            )
                        )
                        break
    return findings


def audit_signature_defaults(tree: ast.Module, path: Path) -> list[Finding]:
    """Défauts de signature contenant un chemin de données (variante 1)."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in list(node.args.defaults) + [
            d for d in node.args.kw_defaults if d is not None
        ]:
            lit = _contains_data_path_literal(default)
            if lit:
                findings.append(
                    Finding(
                        "CRITICAL",
                        path,
                        node.lineno,
                        f"défaut de signature '{lit}' dans "
                        f"{node.name}() — non injectable, figé à la "
                        f"définition (DS-001 variante 1)",
                    )
                )
    return findings


def should_scan(path: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    if any(h in path.name for h in EXCLUDE_FILE_HINTS):
        return False
    return path.suffix == ".py"


def load_baseline(root: Path) -> set[str]:
    bl = root / "scripts" / "default_path_audit_baseline.txt"
    if not bl.exists():
        return set()
    return {
        line.strip()
        for line in bl.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument(
        "--fail-on",
        default="HIGH",
        choices=["CRITICAL", "HIGH", "MEDIUM", "INFO"],
        help="sévérité minimale entraînant exit 1 (défaut: HIGH)",
    )
    args = ap.parse_args()
    root = Path(args.root).resolve()
    threshold = SEVERITY_ORDER[args.fail_on]
    baseline = load_baseline(root)

    findings: list[Finding] = []
    scanned = 0
    for py in sorted(root.rglob("*.py")):
        if not should_scan(py.relative_to(root)):
            continue
        scanned += 1
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = py.relative_to(root)
        findings += audit_module_level(tree, rel)
        findings += audit_signature_defaults(tree, rel)

    findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.key))

    print("=" * 62)
    print("DEFAULT PATH AUDIT — règle DS-001 (ADR-0008)")
    print(f"Racine   : {root}")
    print(f"Fichiers : {scanned} scannés")
    print("=" * 62)

    active = [f for f in findings if f.key not in baseline]
    baselined = [f for f in findings if f.key in baseline]

    for f in active:
        print(f)
    if baselined:
        print(f"\n-- baseline ({len(baselined)} acceptées temporairement) --")
        for f in baselined:
            print(f"  [{f.severity}] {f.key}")

    failing = [f for f in active if SEVERITY_ORDER[f.severity] >= threshold]
    counts = {}
    for f in active:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    summary = (
        ", ".join(
            f"{k}={v}"
            for k, v in sorted(counts.items(), key=lambda kv: -SEVERITY_ORDER[kv[0]])
        )
        or "aucune"
    )
    print(f"\nViolations actives : {summary}")
    print(f"RÉSULTAT : {'FAIL' if failing else 'PASS'} " f"(seuil: {args.fail_on})")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
