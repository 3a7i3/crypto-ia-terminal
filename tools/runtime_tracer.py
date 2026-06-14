"""
runtime_tracer.py — Phase 0.5 Runtime Forensics
Capture tous les imports réels lors du chargement de la chaîne production,
sans connexion exchange (dry-run via mock env).

Usage:
    python tools/runtime_tracer.py
    python tools/runtime_tracer.py --output docs/stabilization/RUNTIME_ACTIVE_MAP.md
"""

import argparse
import importlib
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Injecter des env vars factices pour éviter les crash exchange
_MOCK_ENV = {
    "MEXC_API_KEY": "mock_key_tracer",
    "MEXC_API_SECRET": "mock_secret_tracer",
    "TELEGRAM_TOKEN": "mock_token_tracer",
    "TELEGRAM_CHAT_ID": "0",
    "PAPER_TRADING": "true",
    "DRY_RUN": "true",
    "LOG_LEVEL": "WARNING",
}
for k, v in _MOCK_ENV.items():
    os.environ.setdefault(k, v)

sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Import tracer via sys.meta_path hook
# ---------------------------------------------------------------------------


class ImportTracer:
    def __init__(self, root: Path):
        self.root = root
        self.loaded: dict[str, str] = {}  # module_name -> file_path
        self.load_order: list[str] = []
        self.failed: dict[str, str] = {}  # module_name -> error

    def find_module(self, name, path=None):
        return None  # laisser Python trouver le module

    def find_spec(self, name, path, target=None):
        return None  # hook seulement, pas d'interception

    def exec_module(self, module):
        pass


def trace_imports(modules_to_load: list[str], root: Path) -> dict:
    """Charge chaque module et enregistre ce qui s'est réellement importé."""
    loaded_before = set(sys.modules.keys())
    results = {}

    for mod_name in modules_to_load:
        before = set(sys.modules.keys())
        try:
            importlib.import_module(mod_name)
            after = set(sys.modules.keys())
            new_mods = after - before
            local_new = [
                m
                for m in new_mods
                if any(
                    m.startswith(pkg)
                    for pkg in [
                        "quant_hedge_ai",
                        "advisor",
                        "capital_deployment",
                        "cold_start",
                        "core",
                        "errors",
                        "exchange_constraints",
                        "execution_simulator",
                        "observability",
                        "paper_trading",
                        "risk_limits",
                        "scripts",
                        "supervision",
                        "system",
                        "tracker_system",
                        "lm_studio",
                        "event_bus",
                        "audit",
                        "crypto",
                        "meta_learning",
                        "market_data",
                        "pieuvre",
                    ]
                )
            ]
            results[mod_name] = {"status": "OK", "pulled_in": sorted(local_new)}
        except ImportError as e:
            results[mod_name] = {"status": f"ImportError: {e}", "pulled_in": []}
        except Exception as e:
            results[mod_name] = {
                "status": f"Error: {type(e).__name__}: {e}",
                "pulled_in": [],
            }

    return results


PRODUCTION_MODULES = [
    # Niveau 1 — imports directs advisor_loop
    "observability.json_logger",
    "observability.heartbeat_system",
    "observability.metrics_bus",
    "errors.error_bus",
    "core.decision_packet",
    "risk_limits",
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
    # Niveau 2 — via advisor_runtime_adapters
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


def generate_map(results: dict, label: str) -> list[str]:
    lines = []
    ok = [(m, r) for m, r in results.items() if r["status"] == "OK"]
    err = [(m, r) for m, r in results.items() if r["status"] != "OK"]
    lines.append(f"\n### {label} — {len(ok)}/{len(results)} importables\n")
    lines.append("| Module | Status | Dépendances chargées |")
    lines.append("|--------|--------|---------------------|")
    for mod, res in results.items():
        status = "OK" if res["status"] == "OK" else f"FAIL"
        n_deps = len(res["pulled_in"])
        err_detail = "" if res["status"] == "OK" else f" `{res['status'][:60]}`"
        lines.append(f"| `{mod}` | {status}{err_detail} | +{n_deps} modules |")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    print("Phase 0.5 — Runtime Tracer")
    print(f"Root: {ROOT}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Chargement des modules production...\n")

    prod_results = trace_imports(PRODUCTION_MODULES, ROOT)
    opt_results = trace_imports(OPTIONAL_MODULES, ROOT)

    prod_ok = sum(1 for r in prod_results.values() if r["status"] == "OK")
    opt_ok = sum(1 for r in opt_results.values() if r["status"] == "OK")

    print(f"Production: {prod_ok}/{len(prod_results)} OK")
    print(f"Optionnel:  {opt_ok}/{len(opt_results)} OK")

    # Modules qui ont échoué
    print("\nECHECS PRODUCTION:")
    for mod, res in prod_results.items():
        if res["status"] != "OK":
            print(f"  FAIL: {mod}")
            print(f"    {res['status'][:100]}")

    # Générer le document Markdown
    output_lines = [
        f"# RUNTIME ACTIVE MAP — Phase 0.5",
        f"> Généré : {datetime.now().strftime('%Y-%m-%d %H:%M')} | Méthode : import réel (dry-run)",
        f"> Env : PAPER_TRADING=true, DRY_RUN=true, mocks exchange",
        f"",
        f"## Résumé",
        f"| Catégorie | Importables | Total | Taux |",
        f"|-----------|------------|-------|------|",
        f"| Production | {prod_ok} | {len(prod_results)} | {prod_ok/len(prod_results)*100:.0f}% |",
        f"| Optionnel | {opt_ok} | {len(opt_results)} | {opt_ok/len(opt_results)*100:.0f}% |",
        f"",
        f"## Interprétation",
        f"Un module FAIL signifie qu'il ne peut pas être importé dans le process courant.",
        f"Causes possibles : connexion exchange requise, dépendance absente, SyntaxError.",
        f"",
    ]
    output_lines += generate_map(prod_results, "Modules Production")
    output_lines += generate_map(opt_results, "Modules Optionnels")

    # Comparaison statique vs runtime
    output_lines += [
        "",
        "## Concordance Statique vs Runtime",
        "| Métrique | Phase 0 (statique) | Phase 0.5 (runtime) |",
        "|---------|-------------------|---------------------|",
        f"| Modules production analysés | {len(PRODUCTION_MODULES)} | {len(PRODUCTION_MODULES)} |",
        f"| Importables | — | {prod_ok} ({prod_ok/len(PRODUCTION_MODULES)*100:.0f}%) |",
        f"| Modules optionnels | {len(OPTIONAL_MODULES)} | {opt_ok} importables |",
    ]

    md_content = "\n".join(output_lines)

    output_path = args.output or str(ROOT / "docs/stabilization/RUNTIME_ACTIVE_MAP.md")
    Path(output_path).write_text(md_content, encoding="utf-8")
    print(f"\nMap générée : {output_path}")
    return prod_ok, len(prod_results)


if __name__ == "__main__":
    main()
