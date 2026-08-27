"""Régressions ciblées — vrais bugs de correction extraits du bruit lint.

Ces tests gardent des défauts réels (pas cosmétiques) trouvés via F821/F811
et corrigés dans le PR chore(bugs). Ils sont AST-only : pas besoin d'importer
les modules lourds (main_v91 est un orphelin lab, dashboard_api dépend de
FastAPI) — on vérifie la propriété structurelle directement sur la source.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str) -> ast.Module:
    return ast.parse((_ROOT / rel).read_text(encoding="utf-8"))


def _find_func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"fonction {name!r} introuvable")


class TestMainV91BusOrdering:
    """quant_hedge_ai/main_v91.py — `bus` était utilisé (l.348) avant son
    assignation (l.416) → UnboundLocalError au run de run_v91_system.
    """

    def test_bus_not_used_before_assignment(self):
        fn = _find_func(_load("quant_hedge_ai/main_v91.py"), "run_v91_system")

        first_store = None
        first_load = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id == "bus":
                if isinstance(node.ctx, ast.Store) and first_store is None:
                    first_store = node.lineno
                elif isinstance(node.ctx, ast.Load) and first_load is None:
                    first_load = node.lineno

        assert first_store is not None, "`bus` n'est jamais assigné"
        # Toute lecture de `bus` doit survenir APRÈS sa première assignation.
        if first_load is not None:
            assert first_store <= first_load, (
                f"`bus` lu à la ligne {first_load} avant assignation "
                f"ligne {first_store} — use-before-assignment de retour"
            )


class TestDashboardApiNoDuplicateRoute:
    """scripts/dashboard_api.py — un merge foireux avait laissé un bloc mort
    (après `return`, référençant `m`/`symbol` indéfinis) puis une route
    `/api/status` dupliquée. On garantit une seule définition d'api_status.
    """

    def test_single_api_status(self):
        tree = _load("scripts/dashboard_api.py")
        defs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "api_status"
        ]
        assert len(defs) == 1, (
            f"{len(defs)} définitions d'api_status — la route dupliquée est revenue"
        )

    def test_no_undefined_m_symbol_leftover(self):
        # Le bloc mort référençait `m` et `symbol` non liés. Après nettoyage,
        # api_status ne doit contenir aucune de ces variables libres.
        fn = _find_func(_load("scripts/dashboard_api.py"), "api_status")
        assigned = {
            t.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
            for t in [node]
        }
        loaded = {
            node.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        # `m` et `symbol` ne doivent plus apparaître comme noms libres.
        assert "m" not in (loaded - assigned)
        assert "symbol" not in (loaded - assigned)
