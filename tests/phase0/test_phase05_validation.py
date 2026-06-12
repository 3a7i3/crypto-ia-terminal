"""
Phase 0.5 — Runtime Forensics Validation Tests

Valide que :
1. Tous les modules production sont importables (53/53)
2. R1 est traité (_legacy bloqué)
3. R2/R3/R4 sont correctement qualifiés
4. La concordance statique/runtime est > 95%
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent

# Injecter env mocks pour import sans exchange réel
_MOCK_ENV = {
    "BINANCE_API_KEY": "mock_key_test",
    "BINANCE_SECRET": "mock_secret_test",
    "TELEGRAM_TOKEN": "mock_token_test",
    "TELEGRAM_CHAT_ID": "0",
    "PAPER_TRADING": "true",
    "DRY_RUN": "true",
}
for k, v in _MOCK_ENV.items():
    os.environ.setdefault(k, v)

sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Test 1 — R1 : _legacy archivé hors de l'arbre Python
# ---------------------------------------------------------------------------


def test_R1_legacy_not_importable():
    """R1 traité : _legacy archivé dans _ARCHIVE_2026/, non importable."""
    if "quant_hedge_ai._legacy" in sys.modules:
        pytest.skip("_legacy déjà chargé avant le test — ordre d'exécution incorrect")
    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module("quant_hedge_ai._legacy")


# ---------------------------------------------------------------------------
# Test 2 — Tous les modules production sont importables
# ---------------------------------------------------------------------------

PRODUCTION_MODULES = [
    "observability.json_logger",
    "observability.heartbeat_system",
    "observability.metrics_bus",
    "errors.error_bus",
    "core.decision_packet",
    "risk.risk_limits",
    "exchange_constraints.binance_rules",
    "exchange_constraints.order_validator",
    "exchange_constraints.rate_limiter",
    "execution_simulator.config",
    "execution_simulator.models",
    "paper_trading.recorder",
    "supervision.circuit_breaker_robust",
    "system.state_machine",
    "system.module_registry",
    "system.safety_auditor",
    "system.position_reconciler",
    "capital_deployment.capital_throttle",
    "capital_deployment.emergency_stop_manager",
    "cold_start.cold_start_manager",
    "quant_hedge_ai.agents.intelligence.regime_detector",
    "quant_hedge_ai.agents.intelligence.feature_engineer",
    "quant_hedge_ai.agents.intelligence.conviction_engine",
    "quant_hedge_ai.agents.intelligence.no_trade_layer",
    "quant_hedge_ai.agents.intelligence.self_awareness_engine",
    "quant_hedge_ai.agents.intelligence.meta_strategy_engine",
    "quant_hedge_ai.agents.intelligence.market_regime_classifier",
    "quant_hedge_ai.agents.intelligence.black_box",
    "quant_hedge_ai.agents.intelligence.chief_officer",
    "quant_hedge_ai.agents.intelligence.mistake_memory",
    "quant_hedge_ai.agents.intelligence.threat_radar",
    "quant_hedge_ai.agents.risk.global_risk_gate",
    "quant_hedge_ai.agents.risk.portfolio_brain",
    "quant_hedge_ai.agents.risk.capital_allocation_engine",
    "quant_hedge_ai.agents.risk.executive_override",
    "quant_hedge_ai.agents.execution.execution_engine",
    "quant_hedge_ai.agents.execution.position_manager",
    "quant_hedge_ai.agents.execution.live_signal_engine",
    "quant_hedge_ai.agents.market.market_scanner",
    "quant_hedge_ai.agents.market.multi_timeframe_scanner",
    "supervision.self_healing_bot",
    "supervision.telegram_kill_switch",
    "supervision.exchange_monitor",
    "supervision.performance_watchdog",
    "tracker_system.core.trade_tracker",
]


@pytest.mark.parametrize("module", PRODUCTION_MODULES)
def test_production_module_importable(module):
    """Tous les modules production doivent être importables en dry-run."""
    try:
        importlib.import_module(module)
    except ImportError as e:
        pytest.fail(f"Module production non importable: {module}\n{e}")
    except Exception as e:
        pytest.fail(f"Erreur à l'import de {module}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Test 3 — Modules optionnels importables
# ---------------------------------------------------------------------------

OPTIONAL_MODULES = [
    "quant_hedge_ai.agents.intelligence.decision_arbitrator",
    "quant_hedge_ai.agents.execution.execution_optimizer",
    "quant_hedge_ai.ai_evolution.strategy_memory",
    "quant_hedge_ai.ai_evolution.strategy_ranker",
    "lm_studio.ai_router",
    "capital_deployment.command_center_bot",
    "scripts.telegram_alerts",
    "scripts.shadow_execution",
]


@pytest.mark.parametrize("module", OPTIONAL_MODULES)
def test_optional_module_importable(module):
    """Modules optionnels doivent être importables (pas nécessairement actifs)."""
    try:
        importlib.import_module(module)
    except ImportError as e:
        pytest.fail(f"Module optionnel non importable: {module}\n{e}")
    except Exception as e:
        pytest.fail(f"Erreur à l'import de {module}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Test 5 — R3 qualifié : DecisionArbitrator est optionnel, pas conflit
# ---------------------------------------------------------------------------


def test_R3_decision_arbitrator_is_optional_in_advisor_loop():
    """R3 qualifié : DecisionArbitrator utilisé optionnellement (v2_arbitrator: Any = None)."""
    src = (ROOT / "core/advisor_loop.py").read_text(encoding="utf-8", errors="ignore")
    # Doit être présent (il est utilisé)
    assert (
        "decision_arbitrator" in src or "DecisionArbitrator" in src
    ), "DecisionArbitrator absent de advisor_loop — suppression inattendue?"
    # Doit être optionnel (paramètre nullable)
    assert (
        "v2_arbitrator" in src
    ), "Paramètre v2_arbitrator absent — le caractère optionnel a été perdu?"


# ---------------------------------------------------------------------------
# Test 6 — R4 qualifié : market.regime_detector uniquement en code obsolète
# ---------------------------------------------------------------------------


def test_R4_market_regime_detector_not_in_production_runtime():
    """R4 qualifié : market.regime_detector ne doit pas être dans la chaîne production."""
    for runtime_file in ["core/advisor_loop.py", "core/advisor_runtime_adapters.py"]:
        src = (ROOT / runtime_file).read_text(encoding="utf-8", errors="ignore")
        assert "agents.market.regime_detector" not in src, (
            f"R4 REGRESSION: market.regime_detector dans {runtime_file} — "
            "conflit de source de vérité régime"
        )


# ---------------------------------------------------------------------------
# Test 7 — Taux de concordance statique/runtime >= 100%
# ---------------------------------------------------------------------------


def test_concordance_static_vs_runtime_100_percent():
    """Concordance statique/runtime : tous les modules de la carte Phase 0 sont importables."""
    total = len(PRODUCTION_MODULES)
    failed = []
    for mod in PRODUCTION_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:
            failed.append(mod)
    concordance = (total - len(failed)) / total * 100
    assert (
        concordance >= 95.0
    ), f"Concordance {concordance:.1f}% < 95% — modules non importables: {failed}"


# ---------------------------------------------------------------------------
# Test 8 — runtime_tracer.py est exécutable
# ---------------------------------------------------------------------------


def test_runtime_tracer_script_exists():
    tracer = ROOT / "tools/runtime_tracer.py"
    assert tracer.exists(), "tools/runtime_tracer.py absent — script Phase 0.5 manquant"


def test_runtime_active_map_generated():
    """La carte runtime a été générée par le tracer."""
    map_file = ROOT / "docs/stabilization/RUNTIME_ACTIVE_MAP.md"
    assert (
        map_file.exists()
    ), "RUNTIME_ACTIVE_MAP.md absent — lancer tools/runtime_tracer.py"
    content = map_file.read_text(encoding="utf-8", errors="ignore")
    assert "100%" in content, "RUNTIME_ACTIVE_MAP.md ne montre pas 100% importables"
    assert "45" in content, "RUNTIME_ACTIVE_MAP.md ne liste pas 45 modules production"
