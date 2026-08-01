"""Invariants du package `observation/accounts/` — ADR-0019 §Invariants.

La passivité de l'observateur n'est pas une intention de docstring : elle est
rendue **vérifiable**. Ces tests inspectent la surface publique et l'arbre
syntaxique des modules, sans jamais instancier de client.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import observation.accounts as pkg

# Méthodes d'ordre et de mouvement de fonds interdites (OBS-A).
FORBIDDEN = (
    "create_order",
    "cancel_order",
    "edit_order",
    "transfer",
    "withdraw",
    "create_limit_order",
    "create_market_order",
    "place_order",
    "cancel_all_orders",
    "set_leverage",
)

# Racines du chemin de décision — aucun import ne doit y mener (OBS-C).
ENGINE_ROOTS = ("core", "src.engine", "src.telegram", "risk", "paper_trading", "dip")


def _package_dir() -> Path:
    return Path(pkg.__file__).parent


def _modules():
    """Modules du package, résolus à l'exécution (jamais figés à l'import)."""
    return [
        importlib.import_module(f"{pkg.__name__}.{m.name}")
        for m in pkgutil.iter_modules([str(_package_dir())])
    ]


def _sources():
    return [(p.name, p.read_text(encoding="utf-8")) for p in _package_dir().glob("*.py")]


def _trees():
    return [(name, ast.parse(src)) for name, src in _sources()]


def _module_level_imports(tree):
    """Imports exécutés au chargement — donc hors corps de fonction.

    Un `import` sous un `try:` ou un `if` reste un import au boot : seul le
    corps d'une fonction le rend paresseux.
    """
    lazy = {
        id(node)
        for func in ast.walk(tree)
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(func)
    }
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in lazy
    ]


def _imported_names(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    return [node.module or ""]


# ── OBS-A — aucune méthode d'ordre exposée ──────────────────────────────────


@pytest.mark.parametrize("name", FORBIDDEN)
def test_obs_a_surface_publique_sans_methode_dordre(name):
    assert not hasattr(pkg, name)
    for module in _modules():
        assert not hasattr(module, name), f"{module.__name__} expose {name}"


def test_obs_a_aucune_methode_dordre_definie_ni_appelee():
    for name, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name not in FORBIDDEN, f"{name} définit {node.name}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN, f"{name} appelle .{node.attr}"


def test_obs_a_exports_publics_tous_en_lecture():
    assert all(
        n.startswith("collect_") or n[0].isupper() or n == "reconcile_position_ids"
        for n in pkg.__all__
    )


# ── OBS-C — zéro import du moteur ───────────────────────────────────────────


def test_obs_c_zero_import_moteur():
    for name, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for root in _imported_names(node):
                head = root.split(".")[0]
                assert head not in ENGINE_ROOTS, f"{name} importe {root}"
                assert not root.startswith(ENGINE_ROOTS), f"{name} importe {root}"


# ── OBS-E — chemins résolus à l'exécution (DS-001) ──────────────────────────


def test_obs_e_aucun_chemin_ni_reglage_fige_au_module():
    """Contre-modèle à ne pas suivre : `infra/multi_exchange_feed.py:26-27`."""
    for name, tree in _trees():
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    called = ast.unparse(sub.func)
                    assert "getenv" not in called, f"{name} : env figé à l'import"
                    assert called.split(".")[-1] != "Path", f"{name} : chemin figé"


def test_obs_e_les_seuils_sont_relus_a_chaque_appel(monkeypatch):
    from observation.accounts import _common

    monkeypatch.setenv("OBS_ACCOUNTS_DUST_QTY", "42")
    assert _common.dust_thresholds()[0] == 42.0  # après l'import, pas avant


# ── OBS-F — imports lourds paresseux ────────────────────────────────────────


def test_obs_f_ccxt_jamais_importe_au_module():
    """Modèle suivi : `observability/real_accounts.py:80`.

    Un import sous `try:` ou `if` au niveau module compte comme un import au
    boot : seul le corps d'une fonction rend l'import paresseux.
    """
    for name, tree in _trees():
        for node in _module_level_imports(tree):
            assert "ccxt" not in _imported_names(node), f"{name} importe ccxt au boot"


def test_obs_f_ccxt_est_bien_importe_quelque_part_paresseusement():
    # Le collecteur sait construire un client : la garantie porte sur le
    # MOMENT de l'import, pas sur son absence.
    sources = dict(_sources())
    assert "import ccxt" in sources["_common.py"]


def test_obs_f_le_package_simporte_sans_ccxt():
    # ccxt n'est pas installé dans cet environnement : l'import réussit quand
    # même, ce qui prouve que rien n'en dépend au boot.
    importlib.reload(pkg)


# ── OBS-I — aucune alerte, aucun verdict, aucune détection ──────────────────


def test_obs_i_aucun_canal_de_notification():
    interdits = ("telegram", "requests", "smtplib", "urllib", "http.client", "socket")
    for name, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for mod in _imported_names(node):
                assert not mod.startswith(interdits), f"{name} importe {mod}"


def test_obs_i_aucun_envoi_ni_alerte_dans_le_code():
    verbes = ("send_message", "send_alert", "notify", "alert", "sendMessage")
    for name, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Attribute) and node.attr in verbes:
                pytest.fail(f"{name} appelle .{node.attr} — Phase B interdite")
            if isinstance(node, ast.Name) and node.id in verbes:
                pytest.fail(f"{name} référence {node.id} — Phase B interdite")


def test_obs_i_aucun_champ_de_verdict_dans_les_structures():
    verdicts = ("anomaly", "alert", "verdict", "diagnostic", "suspicious", "severity")
    for name in pkg.__all__:
        obj = getattr(pkg, name)
        for field_name in getattr(obj, "__dataclass_fields__", {}):
            assert not any(v in field_name for v in verdicts), f"{name}.{field_name}"
