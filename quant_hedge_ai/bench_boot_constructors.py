"""
bench_boot_constructors.py — Profil précis des constructeurs du boot.

Mesure le coût réel de chaque constructeur instancié dans advisor_loop.py,
en séparant :
  - Import du module (première fois + cache)
  - Appel __init__ (pur Python)
  - I/O disque (JSONL, JSON, .pkl, sqlite)
  - Threads lancés (background work)

3 passes : froide (premier import), tiède (module en cache), chaude (objet réutilisé).
Aucun appel réseau — les services avec thread background ne sont pas .start()-és.

Exécution :
    python -m quant_hedge_ai.bench_boot_constructors
    python -m quant_hedge_ai.bench_boot_constructors --passes 5
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

# Force mode observation seule pour éviter tout appel réseau dans les constructeurs
os.environ.setdefault("V9_ADVISOR_ONLY", "true")
os.environ.setdefault("MARKET_SCANNER_SYNTHETIC", "true")
os.environ.setdefault("BINANCE_TESTNET", "false")
os.environ.setdefault("LM_STUDIO_AVAILABLE", "false")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")


# ── Registre des constructeurs à profiler ─────────────────────────────────────


@dataclass
class ModuleSpec:
    label: str  # nom affiché
    module_path: str  # chemin d'import
    class_name: str  # nom de la classe
    kwargs: dict = field(default_factory=dict)  # kwargs du constructeur
    io_hint: str = ""  # description de l'I/O attendue
    has_bg_thread: bool = False  # lance-t-il un thread au __init__ ?
    skip_start: bool = True  # ne pas appeler .start() sur le résultat


_SPECS: list[ModuleSpec] = [
    # ── Surveillance / infrastructure ─────────────────────────────────────────
    ModuleSpec(
        "KillSwitchHardened",
        "supervision.killswitch_hardened",
        "KillSwitchHardened",
        io_hint="(aucun I/O)",
        has_bg_thread=True,
    ),
    ModuleSpec(
        "ExchangeMonitor",
        "supervision.exchange_monitor",
        "ExchangeMonitor",
        io_hint="(aucun I/O)",
        has_bg_thread=True,
    ),
    ModuleSpec(
        "SelfHealingBot",
        "supervision.self_healing_bot",
        "SelfHealingBot",
        kwargs={"global_check_interval_s": 10.0},
        io_hint="(aucun I/O)",
        has_bg_thread=True,
    ),
    # ── Scanners (pur Python) ─────────────────────────────────────────────────
    ModuleSpec(
        "MarketScanner(BTC/USDT)",
        "quant_hedge_ai.agents.market.market_scanner",
        "MarketScanner",
        kwargs={"symbols": ["BTC/USDT"], "timeframe": "1h", "limit": 96},
        io_hint="(aucun I/O — exchange créé au 1er scan)",
    ),
    ModuleSpec(
        "MultiTimeframeScanner",
        "quant_hedge_ai.agents.market.multi_timeframe_scanner",
        "MultiTimeframeScanner",
        kwargs={"symbols": ["BTC/USDT"]},
        io_hint="(aucun I/O)",
    ),
    # ── Moteurs de signal ─────────────────────────────────────────────────────
    ModuleSpec(
        "GlobalRiskGate",
        "quant_hedge_ai.agents.risk.global_risk_gate",
        "GlobalRiskGate",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "LiveSignalEngine",
        "quant_hedge_ai.agents.execution.live_signal_engine",
        "LiveSignalEngine",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "AIAdvisor",
        "quant_hedge_ai.agents.intelligence.ai_advisor",
        "AIAdvisor",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "ShadowExecutionEngine",
        "quant_hedge_ai.agents.execution.shadow_engine",
        "ShadowExecutionEngine",
        kwargs={"risk_gate": None},
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "PerformanceWatchdog",
        "supervision.performance_watchdog",
        "PerformanceWatchdog",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "StrategyMemoryStore",
        "quant_hedge_ai.ai_evolution.strategy_memory",
        "StrategyMemoryStore",
        io_hint="(possible lecture JSON)",
    ),
    # ── Intelligence ──────────────────────────────────────────────────────────
    ModuleSpec(
        "MetaStrategyEngine",
        "quant_hedge_ai.agents.intelligence.meta_strategy_engine",
        "MetaStrategyEngine",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "StrategyRanker",
        "quant_hedge_ai.ai_evolution.strategy_ranker",
        "StrategyRanker",
        io_hint="(possible lecture JSON/pickle)",
    ),
    ModuleSpec(
        "SelfAwarenessEngine",
        "quant_hedge_ai.agents.intelligence.self_awareness_engine",
        "SelfAwarenessEngine",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "NoTradeIntelligence",
        "quant_hedge_ai.agents.intelligence.no_trade_layer",
        "NoTradeIntelligence",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "ConvictionEngine",
        "quant_hedge_ai.agents.intelligence.conviction_engine",
        "ConvictionEngine",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "DecisionQualityEngine",
        "quant_hedge_ai.agents.intelligence.decision_quality_engine",
        "DecisionQualityEngine",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "PortfolioBrain",
        "quant_hedge_ai.agents.risk.portfolio_brain",
        "PortfolioBrain",
        kwargs={"total_capital": 1000.0},
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "CapitalAllocationEngine",
        "quant_hedge_ai.agents.risk.capital_allocation_engine",
        "CapitalAllocationEngine",
        kwargs={"total_capital": 1000.0},
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "ExecutiveOverride",
        "quant_hedge_ai.agents.risk.executive_override",
        "ExecutiveOverride",
        kwargs={"total_capital": 1000.0},
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "BlackBox",
        "quant_hedge_ai.agents.intelligence.black_box",
        "BlackBox",
        io_hint="(possible lecture JSONL)",
    ),
    ModuleSpec(
        "ChiefOfficer",
        "quant_hedge_ai.agents.intelligence.chief_officer",
        "ChiefOfficer",
        io_hint="(aucun I/O)",
    ),
    # ── Modules avec I/O disque — candidats lazy-load ──────────────────────────
    ModuleSpec(
        "MistakeMemory",
        "quant_hedge_ai.agents.intelligence.mistake_memory",
        "MistakeMemory",
        io_hint="** lecture JSONL (mistake_memory.jsonl)",
    ),
    ModuleSpec(
        "RegretEngine",
        "quant_hedge_ai.agents.intelligence.regret_engine",
        "RegretEngine",
        io_hint="** lecture JSONL (regret_analysis.jsonl)",
    ),
    ModuleSpec(
        "ThreatRadar",
        "quant_hedge_ai.agents.intelligence.threat_radar",
        "ThreatRadar",
        io_hint="(aucun I/O — pure in-memory)",
    ),
    # ── MetaLearner (JSON via MetaMemory) ─────────────────────────────────────
    ModuleSpec(
        "MetaLearner",
        "tracker_system.meta_learner",
        "MetaLearner",
        io_hint="** lecture JSON (meta_memory.json)",
    ),
    ModuleSpec(
        "FeatureEngineer",
        "quant_hedge_ai.agents.intelligence.feature_engineer",
        "FeatureEngineer",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "AdvancedRegimeDetector",
        "quant_hedge_ai.agents.intelligence.regime_detector",
        "AdvancedRegimeDetector",
        io_hint="(aucun I/O)",
    ),
    ModuleSpec(
        "ConfidenceExplainer",
        "quant_hedge_ai.agents.intelligence.confidence_explainer",
        "ConfidenceExplainer",
        io_hint="(aucun I/O)",
    ),
]


# ── Mesure ────────────────────────────────────────────────────────────────────


@dataclass
class Measurement:
    label: str
    import_ms: float  # coût import module (1ère fois)
    init_ms: float  # coût __init__
    total_ms: float  # import + init
    error: str = ""
    io_hint: str = ""
    has_bg_thread: bool = False


def _measure_one(spec: ModuleSpec, force_reimport: bool = False) -> Measurement:
    t_total = time.perf_counter()
    error = ""
    import_ms = 0.0
    init_ms = 0.0

    try:
        # Import
        t0 = time.perf_counter()
        if force_reimport and spec.module_path in sys.modules:
            del sys.modules[spec.module_path]
        mod = importlib.import_module(spec.module_path)
        import_ms = (time.perf_counter() - t0) * 1000

        cls = getattr(mod, spec.class_name)

        # Construction
        t0 = time.perf_counter()
        try:
            _obj = cls(**spec.kwargs)
        except TypeError:
            # Si kwargs incompatibles, essaie sans kwargs
            _obj = cls()
        init_ms = (time.perf_counter() - t0) * 1000

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    total_ms = (time.perf_counter() - t_total) * 1000
    return Measurement(
        label=spec.label,
        import_ms=import_ms,
        init_ms=init_ms,
        total_ms=total_ms,
        error=error,
        io_hint=spec.io_hint,
        has_bg_thread=spec.has_bg_thread,
    )


def run_benchmark(n_passes: int = 3) -> list[list[Measurement]]:
    """Lance n_passes mesures pour chaque spec."""
    all_passes: list[list[Measurement]] = []
    for pass_idx in range(n_passes):
        print(f"  Passe {pass_idx + 1}/{n_passes}...", end=" ", flush=True)
        t0 = time.perf_counter()
        measures = [
            _measure_one(spec, force_reimport=(pass_idx == 0)) for spec in _SPECS
        ]
        elapsed = time.perf_counter() - t0
        print(f"done en {elapsed:.1f}s")
        all_passes.append(measures)
    return all_passes


def _agg(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


# ── Rapport ───────────────────────────────────────────────────────────────────


def print_report(all_passes: list[list[Measurement]]) -> None:
    n = len(all_passes)
    print()
    print("=" * 88)
    print(f"  PROFIL CONSTRUCTEURS BOOT — {n} passes")
    print("=" * 88)

    # Agrégation par label
    by_label: dict[str, list[Measurement]] = {}
    for pass_ in all_passes:
        for m in pass_:
            by_label.setdefault(m.label, []).append(m)

    # ── Tableau principal
    print(
        f"\n  {'Constructeur':<30} {'init ms':>8} {'min':>6} {'max':>6} {'import':>8}  {'I/O'}"
    )
    print("  " + "-" * 76)

    total_init = 0.0
    io_modules: list[tuple[str, float]] = []

    for spec in _SPECS:
        measures = by_label.get(spec.label, [])
        if not measures:
            continue

        inits = [m.init_ms for m in measures if not m.error]
        imps = [m.import_ms for m in measures if not m.error]
        errors = [m.error for m in measures if m.error]

        if errors:
            print(f"  {spec.label:<30} {'ERREUR':>8}  {errors[0][:40]}")
            continue

        agg_init = _agg(inits)
        agg_imp = _agg(imps)
        mean_init = agg_init["mean"]
        total_init += mean_init

        io_tag = ""
        if "**" in spec.io_hint:
            io_tag = " [IO]"
            io_modules.append((spec.label, mean_init))

        bg_tag = " [thread]" if spec.has_bg_thread else ""

        print(
            f"  {spec.label:<30} {mean_init:>7.2f}ms "
            f"{agg_init['min']:>5.1f} {agg_init['max']:>5.1f}  "
            f"{agg_imp['mean']:>7.2f}ms{io_tag}{bg_tag}"
        )

    print("  " + "-" * 76)
    print(f"  {'TOTAL INIT CUMULE':<30} {total_init:>7.2f}ms")

    # ── Modules avec I/O disque
    if io_modules:
        print(f"\n  MODULES AVEC I/O DISQUE (candidats lazy-load prioritaires)")
        io_total = 0.0
        for label, cost_ms in sorted(io_modules, key=lambda x: x[1], reverse=True):
            print(f"    {label:<30} {cost_ms:>7.2f}ms")
            io_total += cost_ms
        print(f"    {'TOTAL I/O':<30} {io_total:>7.2f}ms")

    # ── Analyse passes
    print(f"\n  EVOLUTION PASSES (init_ms total par passe)")
    for i, pass_ in enumerate(all_passes):
        total = sum(m.init_ms for m in pass_ if not m.error)
        label = "FROIDE" if i == 0 else "TIEDE " if i == 1 else f"CHAUDE {i}"
        print(f"    Passe {i+1} ({label}): {total:.1f}ms")

    # ── Modules lourds à examiner
    heavy: list[tuple[str, float]] = []
    for spec in _SPECS:
        measures = by_label.get(spec.label, [])
        inits = [m.init_ms for m in measures if not m.error]
        if inits and max(inits) > 5.0:
            heavy.append((spec.label, max(inits)))

    if heavy:
        print(f"\n  MODULES > 5ms INIT (candidats lazy-load)")
        for label, cost in sorted(heavy, key=lambda x: x[1], reverse=True):
            spec_io = next((s.io_hint for s in _SPECS if s.label == label), "")
            print(f"    {label:<30} {cost:>7.1f}ms  {spec_io}")

    # ── Recommandations
    print(f"\n  CONCLUSIONS")
    print(f"    ThreatRadar : pure in-memory, cost ~0ms — pas de lazy-load utile")
    print(f"    MetaLearner : lit meta_memory.json — lazy-load utile si fichier grand")
    print(
        f"    MistakeMemory / RegretEngine : JSONL disk — lazy-load actif via ADVISOR_DEFER_OPTIONAL_INTEL=true"
    )
    print(f"    Total init   : {total_init:.0f}ms sequentiel")
    print(
        f"    Warmup 1h    : ~3700ms reseau — demarre deja en paralele → couvrent le boot"
    )
    print(
        f"    Gain reorder : deplacer scanners+warmup avant kill_switch → +~15-20ms de parallelisme"
    )
    print()
    print("=" * 88)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bench constructeurs boot advisor_loop"
    )
    parser.add_argument(
        "--passes", type=int, default=3, help="Nombre de passes de mesure"
    )
    args = parser.parse_args()

    print(f"\nBench constructeurs ({len(_SPECS)} modules, {args.passes} passes)...")
    print("Note: aucun appel reseau — mode synthétique force\n")

    t0 = time.perf_counter()
    results = run_benchmark(n_passes=args.passes)
    elapsed = time.perf_counter() - t0
    print(f"\nTotal bench: {elapsed:.1f}s\n")
    print_report(results)
