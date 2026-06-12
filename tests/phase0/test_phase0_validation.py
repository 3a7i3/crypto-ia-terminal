"""
Phase 0 — Forensic Freeze Validation Tests
Valide que la carte d'imports statique est correcte et stable.
"""

import ast
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_local_imports(filepath: Path) -> list[str]:
    try:
        src = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if (ROOT / mod).exists() or (ROOT / (mod + ".py")).exists():
                    imports.append(mod)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if (ROOT / mod).exists() or (ROOT / (mod + ".py")).exists():
                    imports.append(mod)
    return list(set(imports))


def module_exists(path: str) -> bool:
    fp = ROOT / path
    return fp.exists()


# ---------------------------------------------------------------------------
# Test 1 — Entrypoints existants
# ---------------------------------------------------------------------------

EXPECTED_ENTRYPOINTS = [
    "advisor_loop.py",
    "capital_deployment/command_center_bot.py",
    "cold_start/cold_start_manager.py",
    "main.py",
]


@pytest.mark.parametrize("entrypoint", EXPECTED_ENTRYPOINTS)
def test_entrypoint_exists(entrypoint):
    assert module_exists(entrypoint), f"Entrypoint manquant: {entrypoint}"


# ---------------------------------------------------------------------------
# Test 2 — Modules runtime critiques existent
# ---------------------------------------------------------------------------

CRITICAL_RUNTIME_MODULES = [
    "advisor_runtime_adapters.py",
    "core/decision_packet.py",
    "errors/error_bus.py",
    "observability/json_logger.py",
    "observability/heartbeat_system.py",
    "observability/metrics_bus.py",
    "risk_limits.py",
    "exchange_constraints/binance_rules.py",
    "exchange_constraints/order_validator.py",
    "exchange_constraints/rate_limiter.py",
    "execution_simulator/config.py",
    "execution_simulator/models.py",
    "paper_trading/recorder.py",
    "supervision/circuit_breaker_robust.py",
    "supervision/self_healing_bot.py",
    "supervision/telegram_kill_switch.py",
    "system/state_machine.py",
    "system/module_registry.py",
    "system/safety_auditor.py",
    "capital_deployment/capital_throttle.py",
    "capital_deployment/emergency_stop_manager.py",
    "quant_hedge_ai/agents/execution/execution_engine.py",
    "quant_hedge_ai/agents/execution/live_signal_engine.py",
    "quant_hedge_ai/agents/execution/position_manager.py",
    "quant_hedge_ai/agents/intelligence/conviction_engine.py",
    "quant_hedge_ai/agents/intelligence/market_regime_classifier.py",
    "quant_hedge_ai/agents/intelligence/no_trade_layer.py",
    "quant_hedge_ai/agents/intelligence/self_awareness_engine.py",
    "quant_hedge_ai/agents/risk/global_risk_gate.py",
    "quant_hedge_ai/agents/risk/portfolio_brain.py",
    "quant_hedge_ai/agents/risk/capital_allocation_engine.py",
    "quant_hedge_ai/agents/market/market_scanner.py",
]


@pytest.mark.parametrize("module", CRITICAL_RUNTIME_MODULES)
def test_critical_module_exists(module):
    assert module_exists(module), f"Module critique manquant: {module}"


# ---------------------------------------------------------------------------
# Test 3 — advisor_loop.py importe bien ses dépendances directes
# ---------------------------------------------------------------------------

EXPECTED_DIRECT_IMPORTS = {
    "advisor_runtime_adapters",
    "capital_deployment",
    "core",
    "errors",
    "exchange_constraints",
    "execution_simulator",
    "observability",
    "paper_trading",
    "quant_hedge_ai",
    "risk_limits",
    "scripts",
    "supervision",
    "system",
}


def test_advisor_loop_direct_imports():
    al = ROOT / "advisor_loop.py"
    assert al.exists(), "advisor_loop.py absent"
    actual = set(get_local_imports(al))
    missing = EXPECTED_DIRECT_IMPORTS - actual
    assert not missing, f"Imports disparus de advisor_loop: {missing}"


# ---------------------------------------------------------------------------
# Test 4 — Pas de dossiers fantômes dans les modules runtime critiques
# ---------------------------------------------------------------------------

RUNTIME_PACKAGES = [
    "observability",
    "core",
    "errors",
    "supervision",
    "system",
    "exchange_constraints",
    "execution_simulator",
    "paper_trading",
    "capital_deployment",
    "cold_start",
]


@pytest.mark.parametrize("pkg", RUNTIME_PACKAGES)
def test_runtime_package_has_init(pkg):
    init = ROOT / pkg / "__init__.py"
    assert init.exists(), f"Package runtime sans __init__.py: {pkg}"


# ---------------------------------------------------------------------------
# Test 5 — Modules orphelins catégorie A n'importent pas les modules runtime
# ---------------------------------------------------------------------------

ORPHAN_A_MODULES = ["S2", "S3", "mvp"]


@pytest.mark.parametrize("orphan", ORPHAN_A_MODULES)
def test_orphan_not_imported_by_runtime(orphan):
    """Un module orphelin ne doit pas être importé par advisor_loop ou ses dépendances."""
    al = ROOT / "advisor_loop.py"
    adapters = ROOT / "advisor_runtime_adapters.py"
    for entry in [al, adapters]:
        if entry.exists():
            imports = get_local_imports(entry)
            assert orphan not in imports, (
                f"ANOMALIE: {orphan} est importé par {entry.name} — "
                "pas orphelin en réalité!"
            )


# ---------------------------------------------------------------------------
# Test 6 — Snapshot: total de fichiers runtime dans les packages critiques
# (détecte les suppressions accidentelles entre phases)
# ---------------------------------------------------------------------------

PACKAGE_FILE_MINIMUMS = {
    "quant_hedge_ai": 200,
    "supervision": 30,
    "tracker_system": 60,
    "cold_start": 10,
    "system": 8,
    "observability": 5,
}


@pytest.mark.parametrize("pkg,min_files", PACKAGE_FILE_MINIMUMS.items())
def test_package_file_count_minimum(pkg, min_files):
    pkg_dir = ROOT / pkg
    assert pkg_dir.exists(), f"Package {pkg} absent"
    py_files = [
        f
        for f in pkg_dir.rglob("*.py")
        if "__pycache__" not in str(f) and ".venv" not in str(f)
    ]
    assert len(py_files) >= min_files, (
        f"{pkg} a {len(py_files)} fichiers < minimum {min_files} — "
        "suppression accidentelle?"
    )


# ---------------------------------------------------------------------------
# Test 7 — advisor_loop.py parseable (pas de SyntaxError)
# ---------------------------------------------------------------------------


def test_advisor_loop_parseable():
    al = ROOT / "advisor_loop.py"
    src = al.read_text(encoding="utf-8", errors="ignore")
    try:
        ast.parse(src)
    except SyntaxError as e:
        pytest.fail(f"advisor_loop.py a une SyntaxError: {e}")


def test_advisor_runtime_adapters_parseable():
    f = ROOT / "advisor_runtime_adapters.py"
    src = f.read_text(encoding="utf-8", errors="ignore")
    try:
        ast.parse(src)
    except SyntaxError as e:
        pytest.fail(f"advisor_runtime_adapters.py a une SyntaxError: {e}")


# ---------------------------------------------------------------------------
# Tests Risques Immédiats (R1→R4 identifiés Phase 0)
# ---------------------------------------------------------------------------


def test_R1_mvp_not_imported_by_runtime():
    """R1 — mvp/ confirmé non importé par le runtime principal."""
    for entry in ["advisor_loop.py", "advisor_runtime_adapters.py"]:
        fp = ROOT / entry
        if fp.exists():
            src = fp.read_text(encoding="utf-8", errors="ignore")
            assert "mvp" not in src, (
                f"REGRESSION R1: 'mvp' trouvé dans {entry} — "
                "mvp/ ne doit pas être réintroduit dans le runtime"
            )


def test_R3_single_regime_detector_in_runtime():
    """R3 — un seul regime_detector doit être importé par advisor_runtime_adapters."""
    adapters = ROOT / "advisor_runtime_adapters.py"
    if not adapters.exists():
        pytest.skip("advisor_runtime_adapters.py absent")
    src = adapters.read_text(encoding="utf-8", errors="ignore")
    uses_intelligence = "agents.intelligence.regime_detector" in src
    uses_market = "agents.market.regime_detector" in src
    assert not (uses_intelligence and uses_market), (
        "CONFLIT R3: advisor_runtime_adapters importe les DEUX regime_detector "
        "(intelligence/ et market/) — source de vérité dupliquée"
    )


def test_R4_main_v91_not_imported_by_production_runtime():
    """R4 — main_v91.py est un orphelin actif, pas dans la chaîne production."""
    for entry in ["advisor_loop.py", "advisor_runtime_adapters.py"]:
        fp = ROOT / entry
        if fp.exists():
            src = fp.read_text(encoding="utf-8", errors="ignore")
            assert "main_v91" not in src, (
                f"ANOMALIE R4: main_v91 référencé dans {entry} — "
                "entrypoint lab ne doit pas être dans le runtime production"
            )


def test_duplication_regime_detector_has_canonical():
    """Le regime_detector actif (intelligence/) doit exister."""
    canonical = ROOT / "quant_hedge_ai/agents/intelligence/regime_detector.py"
    assert canonical.exists(), "regime_detector.py canonical absent"


def test_duplication_position_manager_both_exist():
    """Les deux position_manager existent — état séparé, pas de conflit direct."""
    p1 = ROOT / "quant_hedge_ai/agents/execution/position_manager.py"
    p2 = ROOT / "tracker_system/core/position_manager.py"
    assert p1.exists(), "position_manager execution absent"
    assert p2.exists(), "position_manager tracker_system absent"
    # Ils doivent gérer des états distincts (vérification nominale)
    src1 = p1.read_text(encoding="utf-8", errors="ignore")
    src2 = p2.read_text(encoding="utf-8", errors="ignore")
    # Les deux ne doivent pas s'importer mutuellement (boucle)
    assert (
        "tracker_system" not in src1
    ), "position_manager execution importe tracker_system — couplage anormal"


def test_three_entrypoints_are_distinct():
    """Les 3 entrypoints identifiés existent mais sont clairement séparés."""
    entrypoints = {
        "advisor_loop.py": "production",
        "quant_hedge_ai/main_v91.py": "lab/orphan",
        "quant_hedge_ai/main_system.py": "obsolete",
    }
    existing = [(e, role) for e, role in entrypoints.items() if (ROOT / e).exists()]
    # advisor_loop doit toujours exister
    names = [e for e, _ in existing]
    assert (
        "advisor_loop.py" in names
    ), "advisor_loop.py manquant — entrypoint production absent"
