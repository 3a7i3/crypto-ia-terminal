"""Garde de passivité (ADR-0007, #286) : aucun import croisé avec le runtime.

1. Le paquet n'importe que la bibliothèque standard et lui-même.
2. Aucun module du chemin de décision/exécution n'importe le paquet.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "observability" / "signals_indicators"
OWN = "observability.signals_indicators"
RUNTIME_DIRS = ("quant_hedge_ai", "core", "paper_trading", "src", "financial_institute", "risk", "runtime")


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_package_imports_only_stdlib_and_itself():
    stdlib = set(sys.stdlib_module_names)
    for py in PKG.rglob("*.py"):
        for name in _imports(py):
            top = name.split(".")[0]
            assert name.startswith(OWN) or top in stdlib or top == "__future__", (py.name, name)


def test_runtime_never_imports_package():
    offenders = []
    for d in RUNTIME_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "signals_indicators" in text:
                offenders.append(str(py.relative_to(ROOT)))
    assert offenders == []
