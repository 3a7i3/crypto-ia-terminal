"""
main_v91.py — V9.1 Laboratoire Quant Autonome

Architecture complète (Phases 1-8 + Renforcements) :

  ┌─────────────────────────────────────────────────────────────────┐
  │                     INFRASTRUCTURE                              │
  │  StreamBus (WS) · HealthServer (/health) · EventBus (pub/sub)  │
  │  OpsWatchdog · SupervisionBridge · ProactiveAlerts (Telegram)   │
  │  SelfHealingBot · TelegramKillSwitch                            │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │                  ANALYSE DE MARCHÉ                              │
  │  MarketScanner → FeatureEngineer → AdvancedRegimeDetector       │
  │  MultiTimeframeScanner · WhaleRadar · MarketRadar               │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │              SIGNAL ENGINE (Phase 4)                            │
  │  LiveSignalEngine (score 0-100) → AIAdvisor (conseil texte)     │
  │  ConfidenceExplainer (breakdown score) · AdvisorOnlyMode        │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │         ÉVOLUTION STRATÉGIQUE (EvolutionEngine)                 │
  │  StrategyGenerator → GeneticOptimizer → BacktestLab             │
  │  StrategyMemoryStore · MonteCarloStressTester                   │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │           RISK GATE (Phase 7)                                   │
  │  GlobalRiskGate (5 conditions) → OrderSizer (Kelly+vol)         │
  │  SessionGuard · DrawdownGuard · RiskMonitor                     │
  │  RiskDashboardAPI (FastAPI temps réel)                          │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │                 EXÉCUTION                                       │
  │  ShadowExecutionEngine (shadow mode) → PaperTradingEngine       │
  │  ExecutionLatencyMonitor · TradeReplaySystem                    │
  │  TradePostMortem (Phase 5) → blacklist auto                     │
  └────────────────────────────┬────────────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────────────┐
  │              RAPPORT & DASHBOARDS                               │
  │  WeeklyReportAgent · DirectorDashboard · AIControlCenter        │
  └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import threading
import time
from pathlib import Path

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.main_v91")
# ── Import guard ─────────────────────────────────────────────────────────────

try:
    from quant_hedge_ai.agents.execution.arbitrage_agent import ArbitrageAgent
except ModuleNotFoundError:
    import sys

    print("\n[ERREUR] Le module 'quant_hedge_ai' est introuvable.\n")
    print("Conseil : Lancez ce script depuis la racine du projet.")
    print(
        "Exemple :\n    cd "
        + os.path.dirname(os.path.dirname(__file__))
        + "\n    .venv\\Scripts\\Activate.ps1\n    python -m quant_hedge_ai.main_v91\n"
    )
    sys.exit(1)

# ── Imports métier ────────────────────────────────────────────────────────────

from stream_bus import StreamBus

from quant_hedge_ai.advisor_only_mode import AdvisorOnlyMode
from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
from quant_hedge_ai.agents.execution.latency_monitor import ExecutionLatencyMonitor
from quant_hedge_ai.agents.execution.liquidity_agent import LiquidityAnalyzer
from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
from quant_hedge_ai.agents.execution.multi_timeframe_signal import MultiTimeframeSignal
from quant_hedge_ai.agents.execution.paper_trading_engine import PaperTradingEngine
from quant_hedge_ai.agents.execution.shadow_engine import ShadowExecutionEngine
from quant_hedge_ai.agents.execution.trade_postmortem import (
    TradePostMortem,
    TradeRecord,
)
from quant_hedge_ai.agents.execution.trade_replay import TradeReplaySystem
from quant_hedge_ai.agents.intelligence import FeatureEngineer
from quant_hedge_ai.agents.intelligence.ai_advisor import AIAdvisor
from quant_hedge_ai.agents.intelligence.confidence_explainer import ConfidenceExplainer
from quant_hedge_ai.agents.intelligence.proactive_alerts import ProactiveAlerts
from quant_hedge_ai.agents.intelligence.regime_detector import AdvancedRegimeDetector
from quant_hedge_ai.agents.intelligence.weekly_report import WeeklyReportAgent
from quant_hedge_ai.agents.market.market_scanner import MarketScanner
from quant_hedge_ai.agents.market.multi_timeframe_scanner import MultiTimeframeScanner
from quant_hedge_ai.agents.monitoring.performance_monitor import PerformanceMonitor
from quant_hedge_ai.agents.monitoring.prompt_doctor_agent import CreatePromptAgent
from quant_hedge_ai.agents.monitoring.system_monitor import SystemMonitor
from quant_hedge_ai.agents.portfolio import PortfolioBrain
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
from quant_hedge_ai.agents.quant.monte_carlo import MonteCarloSimulator
from quant_hedge_ai.agents.quant.stress_test import MonteCarloStressTester
from quant_hedge_ai.agents.research.model_builder import ModelBuilder
from quant_hedge_ai.agents.research.strategy_researcher import StrategyResearcher
from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard
from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate
from quant_hedge_ai.agents.risk.order_sizer import OrderSizer
from quant_hedge_ai.agents.risk.risk_dashboard_api import RiskDashboardAPI
from quant_hedge_ai.agents.risk.risk_monitor import RiskMonitor
from quant_hedge_ai.agents.strategy.genetic_optimizer import GeneticOptimizer
from quant_hedge_ai.agents.strategy.rl_trader import RLTrader
from quant_hedge_ai.agents.strategy.strategy_generator import StrategyGenerator
from quant_hedge_ai.agents.whales import WhaleRadar
from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine
from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore
from quant_hedge_ai.dashboard.control_center import AIControlCenter
from quant_hedge_ai.dashboard.director_dashboard import DirectorDashboard
from quant_hedge_ai.databases.strategy_scoreboard import StrategyScoreboard
from quant_hedge_ai.engine.decision_engine import DecisionEngine
from quant_hedge_ai.health_endpoint import HealthServer
from quant_hedge_ai.liquidity_map.flow_analyzer import LiquidityFlowMap
from quant_hedge_ai.market_radar import MarketRadar
from quant_hedge_ai.runtime_config import (
    RuntimeConfig,
    get_env_int,
    load_runtime_config_from_env,
)
from quant_hedge_ai.strategy_factory import StrategyFactory
from quant_hedge_ai.strategy_lab.market_db import MarketDatabase
from supervision.killswitch_hardened import KillSwitchHardened
from supervision.ops_watchdog import OpsWatchdog
from supervision.self_healing_bot import (
    SelfHealingBot,
    make_api_watchdog,
    make_websocket_watchdog,
)

# ── Imports Phase 4-8 ─────────────────────────────────────────────────────────


# ── Imports Renforcements (Idées #1-#8) ──────────────────────────────────────


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_env_int(name: str, default: int, min_value: int | None = None) -> int:
    return get_env_int(name, default, min_value=min_value)


def _start_streambus_background(bus: StreamBus) -> None:
    def _runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bus.start())
        finally:
            try:
                loop.stop()
            finally:
                loop.close()

    t = threading.Thread(target=_runner, name="streambus-loop", daemon=True)
    t.start()


# ── Boucle principale ─────────────────────────────────────────────────────────


def run_v91_system(
    max_cycles: int = 3,
    population_size: int = 300,
    sleep_seconds: int = 2,
    runtime: RuntimeConfig | None = None,
    enable_director: bool = False,
) -> None:
    """V9.1 — Système quant autonome complet (Phases 1-8)."""
    os.chdir(Path(__file__).resolve().parent)

    cfg = runtime or RuntimeConfig(
        max_cycles=max_cycles,
        population_size=population_size,
        sleep_seconds=sleep_seconds,
    )
    random.seed(cfg.seed)

    # =========================================================================
    # INFRASTRUCTURE (démarrage en premier)
    # =========================================================================

    # Health endpoint HTTP /health
    health = HealthServer(port=int(os.getenv("HEALTH_PORT", "8765")))
    health.start()
    health.update("system", {"status": "starting", "ok": True})

    # EventBus + SupervisionBridge
    try:
        from event_bus.bridge import SupervisionBridge
        from event_bus.bus import EventBus

        _bus = EventBus.get()
        _bridge = SupervisionBridge()
        _bridge.activate()
        _log.info("[Main] EventBus + SupervisionBridge actifs")
    except Exception as _e:
        _log.warning("[Main] EventBus indisponible: %s", _e)

    # Alertes Telegram proactives (Phase 8)
    alerts = ProactiveAlerts.from_env()

    # =========================================================================
    # RENFORCEMENTS #1-#8
    # =========================================================================

    # #1 — Shadow Execution Engine
    shadow_engine = ShadowExecutionEngine()

    # #4 — Latency Monitor
    latency_monitor = ExecutionLatencyMonitor(
        alert_threshold_ms=float(os.getenv("LATENCY_ALERT_MS", "500"))
    )

    # #5 — Trade Replay System
    trade_replay = TradeReplaySystem()

    # #6 — Monte Carlo Stress Tester (run une fois au démarrage)
    _stress_tester = MonteCarloStressTester(
        equity=float(os.getenv("INITIAL_CAPITAL", "100000")),
        win_rate=0.55,
        avg_win=0.015,
        avg_loss=0.010,
    )
    if os.getenv("RUN_STRESS_TEST_AT_STARTUP", "false").lower() == "true":
        _stress_report = _stress_tester.run_all(paths=500, steps=100)
        print(_stress_report.summary())

    # #7 — Confidence Explainer
    confidence_explainer = ConfidenceExplainer()

    # #8 — Self-Healing Bot
    self_healing = SelfHealingBot(global_check_interval_s=5.0)
    self_healing.start()

    # #3 — Telegram Kill Switch (démarré si token configuré)
    _tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    _tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    kill_switch: KillSwitchHardened | None = None
    if _tg_token and _tg_chat_id:
        kill_switch = KillSwitchHardened()
        kill_switch.start()
        _log.info("[Main] KillSwitchHardened actif")

    # =========================================================================
    # MARCHÉ & INTELLIGENCE
    # =========================================================================

    scanner = MarketScanner()
    feature_eng = FeatureEngineer()
    regime_detector = AdvancedRegimeDetector()
    whale_radar = WhaleRadar(threshold_usd=cfg.whale_threshold_usd)
    market_radar = MarketRadar(
        min_liquidity_usd=1_000.0,
        min_volume_usd=500.0,
        whale_threshold_usd=cfg.whale_threshold_usd,
    )

    # =========================================================================
    # SIGNAL ENGINE (Phase 4)
    # =========================================================================

    live_signal_engine = LiveSignalEngine(
        min_score=int(os.getenv("SIGNAL_MIN_SCORE", "70")),
    )
    ai_advisor = AIAdvisor(
        use_lm_studio=True,
        mode=os.getenv("AI_MODE", "auto"),
    )

    # Mode advisor-only (V9_ADVISOR_ONLY=true → pas d'ordre)
    advisor_mode = AdvisorOnlyMode.from_env(
        advisor=ai_advisor,
        alerts=alerts,
    )
    if advisor_mode.active:
        _log.warning("[Main] MODE V9_ADVISOR_ONLY actif — aucun ordre ne sera exécuté")

    # =========================================================================
    # MÉMOIRE & ÉVOLUTION STRATÉGIQUE
    # =========================================================================

    memory_store = StrategyMemoryStore()
    strategy_generator = StrategyGenerator()
    optimizer = GeneticOptimizer()
    rl_trader = RLTrader()
    strategy_factory = StrategyFactory()
    evolution_engine = EvolutionEngine(
        population_size=max(30, cfg.population_size // 5),
        memory_seed_ratio=0.3,
        generations=max(1, cfg.generations - 1),
    )

    # Multi-timeframe
    mtf_scanner = MultiTimeframeScanner(
        symbols=[s if "/" in s else s[:3] + "/" + s[3:] for s in scanner.symbols],
        timeframes=["4h", "1d"],
        refresh_every=4,
    )
    mtf_signal = MultiTimeframeSignal(min_strength=0.5, min_agreement=2)

    # =========================================================================
    # RISK MANAGEMENT (Phase 7)
    # =========================================================================

    drawdown_guard = DrawdownGuard()
    risk_monitor = RiskMonitor(max_drawdown=cfg.max_drawdown)

    global_risk_gate = GlobalRiskGate(
        min_signal_score=int(os.getenv("SIGNAL_MIN_SCORE", "70")),
        require_confirmed=True,
        max_portfolio_drawdown=cfg.max_drawdown,
        drawdown_guard=drawdown_guard,
    )

    order_sizer = OrderSizer(
        kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.25")),
        min_size_usd=float(os.getenv("MIN_ORDER_USD", "10")),
        max_size_usd=float(os.getenv("MAX_ORDER_USD", "5000")),
        vol_target=0.02,
        drawdown_guard=drawdown_guard,
    )

    # Wire shadow_engine avec risk_gate + order_sizer maintenant qu'ils existent
    shadow_engine._risk_gate = global_risk_gate
    shadow_engine._order_sizer = order_sizer

    # Register SelfHealingBot watchdog pour le StreamBus
    make_websocket_watchdog(
        self_healing,
        bus,
        reconnect_fn=lambda: _start_streambus_background(bus),
        name="streambus",
    )

    # =========================================================================
    # POST-MORTEM (Phase 5)
    # =========================================================================

    postmortem = TradePostMortem(
        memory_store=memory_store,
        signal_engine=live_signal_engine,
    )

    # =========================================================================
    # RAPPORT HEBDOMADAIRE (Phase 6)
    # =========================================================================

    weekly_agent = WeeklyReportAgent(
        postmortem=postmortem,
        memory_store=memory_store,
        advisor=ai_advisor,
    )

    # =========================================================================
    # EXÉCUTION
    # =========================================================================

    execution = ExecutionEngine.from_env()
    arbitrage = ArbitrageAgent()
    liquidity = LiquidityAnalyzer()
    paper = PaperTradingEngine()

    # #2 — Risk Dashboard (FastAPI) — démarré en background si activé
    if os.getenv("RISK_DASHBOARD_ENABLED", "false").lower() == "true":
        _dash_port = int(os.getenv("RISK_DASHBOARD_PORT", "8766"))
        risk_dashboard = RiskDashboardAPI(
            paper_engine=paper, shadow_engine=shadow_engine
        )
        risk_dashboard.run_background(port=_dash_port)

    # shadow_engine recevra risk_gate + order_sizer après leur initialisation

    flow_map = LiquidityFlowMap(opportunity_threshold=40.0)
    backtest_lab = BacktestLab()
    monte_carlo = MonteCarloSimulator()
    portfolio_brain = PortfolioBrain()
    decision_engine = DecisionEngine(
        min_sharpe=cfg.min_sharpe_for_trade,
        max_drawdown_for_trade=cfg.trade_max_drawdown,
        whale_block_threshold=cfg.whale_block_threshold,
    )
    strategy_researcher = StrategyResearcher()
    model_builder = ModelBuilder()
    perf_monitor = PerformanceMonitor()
    system_monitor = SystemMonitor()
    control_center = AIControlCenter()
    director = (
        DirectorDashboard(starting_balance=100_000.0) if enable_director else None
    )
    doctor_agent = CreatePromptAgent()
    market_db = MarketDatabase()
    scoreboard = StrategyScoreboard()

    # =========================================================================
    # STREAMBUS (WebSocket permanent)
    # =========================================================================

    bus = StreamBus(
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ARB/USDT"],
        exchange_id="binance",
        exchange_config={"enableRateLimit": True, "options": {"defaultType": "future"}},
        whale_threshold_usd=500_000,
        queue_maxsize=5000,
    )
    _start_streambus_background(bus)
    time.sleep(3)
    print(f"StreamBus prêt — {bus.stats()}")

    # =========================================================================
    # DÉMARRAGE SESSION
    # =========================================================================

    execution.start_session(equity=paper.balance)

    watchdog = OpsWatchdog.from_env()
    watchdog.enable_heartbeat(interval_seconds=3600.0)
    watchdog.notify_startup(
        mode="live" if execution._live else "paper",
        symbols=scanner.symbols,
    )

    health.update("system", {"status": "running", "ok": True})
    health.update("paper_engine", {"balance": paper.balance, "ok": True})
    health.update(
        "signal_engine", {"min_score": live_signal_engine.min_score, "ok": True}
    )
    health.update("risk_gate", {"ok": True})

    # =========================================================================
    # BOUCLE PRINCIPALE
    # =========================================================================

    cycle = 0
    _prev_doctor_health = 100.0
    _last_regime = "unknown"
    _weekly_cycle = int(os.getenv("WEEKLY_REPORT_EVERY", "168"))  # ~1 semaine

    while True:
        cycle += 1
        print(f"\n{'='*60}")
        print(f"[CYCLE {cycle}] Démarrage V9.1 ...")

        # ── 1. SCAN MARCHÉ ─────────────────────────────────────────────────────

        try:
            market = scanner.scan()
        except Exception as _scan_exc:
            _log.error("[Cycle %d] scan échoué: %s", cycle, _scan_exc)
            health.update("scanner", {"ok": False, "error": str(_scan_exc)})
            time.sleep(cfg.sleep_seconds)
            continue

        candles = market.get("candles", [])
        if not candles:
            _log.warning("[Cycle %d] Aucune bougie — cycle ignoré", cycle)
            time.sleep(cfg.sleep_seconds)
            continue

        health.update("scanner", {"ok": True, "candles": len(candles)})

        # Vérification StreamBus
        bus_age = bus.snapshot.updated_at
        if time.time() - bus_age > 30:
            _log.warning(
                "[Cycle %d] StreamBus stale (%.0fs)", cycle, time.time() - bus_age
            )
            watchdog.check_ws_staleness("StreamBus", bus_age, threshold_seconds=120.0)

        stream_snap = bus.snapshot
        market_intel = {
            "btc_price": stream_snap.get_mid_price("BTC/USDT"),
            "btc_imbalance": stream_snap.get_orderbook_imbalance("BTC/USDT"),
            "btc_spread": stream_snap.get_spread("BTC/USDT"),
            "eth_price": stream_snap.get_mid_price("ETH/USDT"),
            "whale_alerts": stream_snap.whale_alerts[-10:],
            "raw_trades": stream_snap.trades,
            "tickers": stream_snap.tickers,
        }

        market_db.save_snapshot(market)

        symbols = [c["symbol"] for c in candles]
        close_prices = [float(c["close"]) for c in candles]

        # ── 2. FEATURES & RÉGIME ───────────────────────────────────────────────

        features = feature_eng.extract_features(candles)
        anomalies = feature_eng.detect_anomalies(features)
        regime = regime_detector.classify(features, close_prices)
        suggested_strategy_type = regime_detector.suggest_strategy_type(regime)

        # Alerte Telegram si changement de régime (Phase 8)
        if regime != _last_regime:
            alerts.on_regime_change(
                symbols[0] if symbols else "?", _last_regime, regime
            )
            # Synchronise la blacklist du RiskGate selon le régime dangereux
            if regime in ("flash_crash",):
                global_risk_gate.blacklist_regime(regime)
            _last_regime = regime

        # ── 3. WHALE & RADAR ───────────────────────────────────────────────────

        whale_data = [
            whale_radar.scan(c["symbol"], float(c["volume"]), float(c["close"]))
            for c in candles
        ]
        whale_alerts_list = [alert for w in whale_data for alert in w["alerts"]]

        radar_report = market_radar.sweep(candles, features, whale_alerts_list)
        radar_summary = radar_report.as_dict()

        if cycle % cfg.display_frequency == 0:
            top_opps = radar_report.top(3)
            opp_str = (
                ", ".join(f"{o.symbol}({o.score:.0f})" for o in top_opps) or "aucune"
            )
            print(
                f"[RADAR] {radar_summary['opportunities_count']} opportunités | "
                f"risque={radar_summary['risk_level']} | top: {opp_str}"
            )

        # ── 4. LIVE SIGNAL ENGINE (Phase 4) ────────────────────────────────────

        _bt_symbol = symbols[0] if symbols else scanner.symbols[0]
        bt_data = market.get("history", {}).get(_bt_symbol, candles)

        # Score 0-100 pour le symbole principal
        live_signal = live_signal_engine.evaluate(
            symbol=_bt_symbol,
            mtf_candles={"1h": candles, "4h": bt_data},
            features=features,
            memory_sharpe=float(
                (memory_store.load_by_regime(regime, limit=1) or [{}])[0].get(
                    "sharpe", 0.0
                )
            ),
        )

        # Conseil AIAdvisor (Phase 6)
        advice = ai_advisor.explain(live_signal)
        if cycle % cfg.display_frequency == 0:
            print(f"[ADVISOR] {advice.short()}")

        health.update(
            "signal_engine",
            {
                "ok": True,
                "score": live_signal.score,
                "signal": live_signal.signal,
                "regime": regime,
            },
        )

        # ── 4b. CONFIDENCE EXPLAINER (#7) ─────────────────────────────────────

        if cycle % cfg.display_frequency == 0 and live_signal.actionable:
            explanation = confidence_explainer.explain(live_signal)
            print(explanation.render())

        # ── 5. ADVISOR-ONLY MODE (Phase 8) ─────────────────────────────────────

        # Kill switch check (#3)
        if kill_switch is not None and not kill_switch.is_execution_allowed():
            mode = "halted" if kill_switch.is_halted() else "safe_mode"
            _log.warning("[Cycle %d] KillSwitch actif — mode %s", cycle, mode)
            time.sleep(max(0, cfg.sleep_seconds))
            if cfg.max_cycles > 0 and cycle >= cfg.max_cycles:
                break
            continue

        if advisor_mode.active:
            advisor_result = advisor_mode.process_signal(live_signal, features)
            if cycle % cfg.display_frequency == 0:
                print(
                    f"[ADVISOR-ONLY] Cycle {cycle} | signal={advisor_result.signal} "
                    f"score={advisor_result.score} | would_trade={advisor_result.would_trade}"
                )
            # En mode advisor-only on skip l'exécution mais on continue le monitoring
            time.sleep(max(0, cfg.sleep_seconds))
            if cfg.max_cycles > 0 and cycle >= cfg.max_cycles:
                break
            continue

        # ── 6. ÉVOLUTION STRATÉGIQUE ───────────────────────────────────────────

        _mem_limit = max(5, cfg.population_size // 4)
        _mem_seed = [
            r.get("strategy", r)
            for r in memory_store.load_by_regime(regime, limit=_mem_limit)
            if isinstance(r, dict)
        ]
        _fresh_count = max(1, cfg.population_size - len(_mem_seed))
        population = _mem_seed + strategy_generator.generate_population(_fresh_count)
        evolved = optimizer.evolve(population, generations=cfg.generations)

        results = [backtest_lab.run_backtest(strategy=s, data=bt_data) for s in evolved]

        factory_report = strategy_factory.run(
            candles,
            target_count=max(30, min(120, cfg.population_size)),
            generations=max(1, cfg.generations - 1),
            regime=regime,
            history=bt_data,
        )
        results.extend(factory_report.approved_results)

        evo_report = evolution_engine.run_cycle(
            cycle=cycle,
            regime=regime,
            candles=bt_data,
            doctor_health=_prev_doctor_health,
        )

        flow_report = flow_map.analyze(
            candles=candles,
            whale_alerts=whale_alerts_list,
            regime=regime,
            cycle=cycle,
        )

        ranked = decision_engine.select_strategies(results, top_n=20)
        filtered = [r for r in ranked if risk_monitor.check(r)]
        top_results = filtered[:10] if filtered else ranked[:10]
        best = strategy_researcher.best(top_results)

        for strategy_result in ranked[:10]:
            strat = strategy_result.get("strategy")
            if strat is not None:
                scoreboard.add(strat, {**strategy_result, "cycle": cycle})

        scoreboard_stats = scoreboard.stats()

        # Sauvegarde mémoire
        _winners = [
            r
            for r in top_results
            if float(r.get("sharpe", 0.0)) >= cfg.min_sharpe_for_trade
        ]
        if _winners:
            memory_store.save_for_regime(regime, _winners[:10])

        # ── 7. RISK GATE (Phase 7) ─────────────────────────────────────────────

        _best_sharpe = float(best.get("sharpe", 0.0)) if best else 0.0
        _portfolio_dd = (
            max(0.0, -paper.total_pnl() / paper._initial_balance)
            if paper.balance
            else 0.0
        )

        gate_result = global_risk_gate.check(
            signal_result=live_signal,
            portfolio_drawdown=_portfolio_dd,
            order_size_usd=float(os.getenv("DEFAULT_ORDER_USD", "500")),
        )

        health.update(
            "risk_gate",
            {
                "ok": gate_result.allowed,
                "failed": len(gate_result.failed),
            },
        )

        if not gate_result.allowed:
            # Alerte Telegram (Phase 8)
            alerts.on_risk_gate_blocked(gate_result, live_signal)
            _log.warning("[Cycle %d] RiskGate BLOCK: %s", cycle, gate_result.summary())
            time.sleep(max(0, cfg.sleep_seconds))
            if cfg.max_cycles > 0 and cycle >= cfg.max_cycles:
                break
            continue

        # ── 8. ORDER SIZER (Phase 7) ───────────────────────────────────────────

        size_result = order_sizer.compute_from_signal(
            signal_result=live_signal,
            capital=paper.balance,
            win_rate=max(0.3, postmortem.summary().get("win_rate", 0.55)),
            avg_win_pct=2.0,
            avg_loss_pct=1.5,
            features=features,
            current_drawdown=_portfolio_dd,
            price=close_prices[0] if close_prices else 1.0,
        )

        # ── 9. SIGNAL MTF & EXÉCUTION ──────────────────────────────────────────

        tradable = liquidity.filter_symbols(candles)
        symbol = tradable[0] if tradable else candles[0]["symbol"]
        price = next(float(c["close"]) for c in candles if c["symbol"] == symbol)

        should_trade = decision_engine.should_trade(best, regime, whale_alerts_list)
        risk_limits = decision_engine.compute_risk_limits(
            features.get("realized_volatility", 0.02), max_risk=cfg.max_risk_per_trade
        )

        if should_trade and best:
            _best_strat = best.get("strategy", {})
            _mtf_raw = mtf_scanner.scan(cycle=cycle)
            _mtf_sym = (
                _bt_symbol
                if "/" in _bt_symbol
                else _bt_symbol[:3] + "/" + _bt_symbol[3:]
            )
            _mtf_candles = MultiTimeframeScanner.merge_base(_mtf_raw, _mtf_sym, bt_data)
            _mtf_result = mtf_signal.confirm(_best_strat, _mtf_candles)
            action = _mtf_result["signal"]
            if action == "HOLD":
                action = rl_trader.choose_action(
                    f"{regime}:{'pos' if features['momentum'] > 0 else 'neg'}"
                )
        else:
            action = rl_trader.choose_action(
                f"{regime}:{'pos' if features['momentum'] > 0 else 'neg'}"
            )
            _mtf_result = {
                "signal": action,
                "confirmed": False,
                "strength": 0.0,
                "alignment": {},
            }

        # Arbitrage override
        if arbitrage.detect(
            price, price * random.uniform(0.985, 1.02), threshold=0.012
        ):
            action = "SELL"

        # Taille finale : OrderSizer (Kelly) ou DrawdownGuard fallback
        if size_result.size_usd > 0:
            size = size_result.size_base
        else:
            dd = float(best.get("drawdown", 0.0)) if best else 0.0
            size = drawdown_guard.adjust_position_size(dd, base_size=1.0)

        # #1 — Shadow execution (log l'ordre sans l'envoyer)
        with latency_monitor.measure("signal_to_order", symbol=symbol, action=action):
            order = execution.create_order(symbol=symbol, action=action, size=size)

        shadow_engine.shadow_execute(
            signal_result=live_signal,
            live_price=price,
            capital=paper.balance,
            portfolio_drawdown=_portfolio_dd,
        )

        watchdog.on_order_result(order)
        watchdog.on_session_guard(execution._guard)

        with latency_monitor.measure("order_to_fill", symbol=symbol):
            paper_state = paper.execute(order, mark_price=price)

        if order.get("status") != "filled":
            latency_monitor.record_reject(
                order_id=str(order.get("id", "")),
                reason=str(order.get("status", "")),
            )

        # Alerte opportunité si signal fort (Phase 8)
        alerts.on_signal_opportunity(live_signal, advice)

        # ── 10. POST-MORTEM (Phase 5) ──────────────────────────────────────────

        if action in ("BUY", "SELL") and order.get("status") == "filled":
            _entry = float(order.get("price", price))
            _exit = price  # prix courant comme sortie approximative
            _pm_trade = TradeRecord(
                symbol=symbol,
                action=action,
                entry_price=_entry,
                exit_price=_exit,
                size=size,
                regime=regime,
                strategy_name=(
                    str(best.get("strategy", {}).get("entry_indicator", "unknown"))
                    if best
                    else "unknown"
                ),
                entry_score=live_signal.score,
                entry_signal_confirmed=live_signal.confirmed,
                entry_strength=live_signal.strength,
            )
            _pm_report = postmortem.analyze(_pm_trade)
            if _pm_report.blacklisted:
                _log.warning(
                    "[Cycle %d] Stratégie blacklistée: %s",
                    cycle,
                    _pm_report.blacklist_key,
                )

        health.update(
            "paper_engine",
            {
                "ok": True,
                "balance": paper.balance,
                "pnl_pct": (
                    paper.total_pnl() / paper._initial_balance * 100
                    if paper._initial_balance
                    else 0
                ),
                "n_trades": len(paper.trade_history),
            },
        )

        # ── 11. BOT DOCTOR ─────────────────────────────────────────────────────

        _prev_doctor_health = 100.0
        doctor_result_for_director = {
            "health_score": 100.0,
            "top_recommendation": "",
            "findings": [],
        }
        doctor_corrections_for_director: list[str] = []

        if cfg.doctor_telegram_enabled:
            dd_for_doctor = float(best.get("drawdown", 0.0)) if best else 0.0
            risk_level = (
                "high"
                if dd_for_doctor > 0.10
                else ("medium" if dd_for_doctor > 0.05 else "low")
            )
            doctor_input = {
                "trade_signal": action,
                "allocation": None,
                "risk_level": risk_level,
            }
            corrected_strategy, doctor_issues = (
                doctor_agent.apply_doctor_corrections_with_issues(doctor_input)
            )
            doctor_corrections_for_director = doctor_issues
            _prev_doctor_health = max(0.0, 100.0 - len(doctor_issues) * 20.0)
            doctor_agent.simulate_telegram_alerts(
                cfg.doctor_telegram_user_id, corrected_strategy
            )

            if cfg.doctor_v26_report_enabled and cycle % cfg.display_frequency == 0:
                doctor_report = doctor_agent.build_v26_compatible_report(doctor_issues)
                print(f"[Bot Doctor V26] {doctor_report}")

        # ── 12. DIRECTOR DASHBOARD ─────────────────────────────────────────────

        director_snapshot = None
        if director is not None:
            _whale_threat = max(
                (w["threat_level"] for w in whale_data), default="low", key=str.lower
            )
            director_snapshot = director.update(
                cycle=cycle,
                market_regime=regime,
                whale_flow=_whale_threat,
                suggested_strategy_type=suggested_strategy_type,
                radar_summary=radar_summary,
                strategy_factory_summary=factory_report.as_dict(),
                best_strategy=best,
                doctor_result=doctor_result_for_director,
                corrections=doctor_corrections_for_director,
                blocked_trade=not should_trade,
                paper_state=paper_state,
                trade_action=action,
                trade_symbol=symbol,
                trade_size=size,
                trade_price=price,
                evo_summary=evo_report.as_dict(),
                flow_summary=flow_report.as_dict(),
            )

        # ── 13. MONITORING & CONTROL CENTER ────────────────────────────────────

        heartbeat = system_monitor.heartbeat(cycle)
        performance = perf_monitor.summarize(top_results)
        model_info = model_builder.retrain(top_results)
        mc = monte_carlo.simulate(
            mean_return=0.0005,
            volatility=min(0.08, max(0.001, features["realized_volatility"])),
            steps=cfg.monte_carlo_steps,
            paths=cfg.monte_carlo_paths,
        )

        portfolio_allocation = portfolio_brain.compute_allocation(
            [
                {
                    "strategy_id": f"s{i}",
                    "sharpe": float(r.get("sharpe", 0.0)),
                    "drawdown": float(r.get("drawdown", 0.01)),
                    "win_rate": float(r.get("win_rate", 0.5)),
                }
                for i, r in enumerate(top_results[:10])
            ],
            features.get("realized_volatility", 0.02),
            max_strategy_weight=cfg.max_strategy_weight,
        )

        if cycle % cfg.display_frequency == 0:
            snap = paper.snapshot(mark_prices={symbol: price})
            print(
                f"[PAPER] balance={snap['balance']:,.0f} | "
                f"P&L={snap['pnl_pct']:+.2f}% | "
                f"trades={snap['n_trades']} | win_rate={snap['win_rate']:.1%} | "
                f"signal={action} | score={live_signal.score}/100 | "
                f"size=${size_result.size_usd:.0f}"
            )

            report = control_center.render_full_report(
                cycle,
                {
                    "regime": regime,
                    "strategy_type": suggested_strategy_type,
                    "momentum": features["momentum"],
                    "realized_volatility": features["realized_volatility"],
                    "anomalies": anomalies,
                    "radar": radar_summary,
                    "stream": market_intel,
                },
                {
                    "alerts": whale_alerts_list,
                    "threat_level": max(
                        (w["threat_level"] for w in whale_data),
                        default="low",
                        key=str.lower,
                    ),
                },
                best,
                scoreboard_stats,
                portfolio_allocation,
                {
                    "kelly_fraction": order_sizer.kelly_fraction,
                    "vol_target": order_sizer.vol_target,
                    "max_position": 0.3,
                },
                {
                    "should_trade": should_trade,
                    "reason": (
                        "High Sharpe + Low DD"
                        if should_trade
                        else "Conditions défavorables"
                    ),
                    "risk_limits": risk_limits,
                },
                {
                    "status": "running",
                    "agents_count": 20,
                    "strategies_gen": len(evolved),
                    "backtests_completed": len(results),
                    "model_version": model_info.get("model_version", 1),
                    "heartbeat": heartbeat,
                    "performance": performance,
                },
                flow_data=flow_report.as_dict(),
            )
            print(report)

            if director is not None and director_snapshot is not None:
                print(director.render(director_snapshot))

            print(f"[MONTECARLO] {mc}")
            print(f"[PAPER] State: {paper_state}")
            print(f"[POSTMORTEM] {postmortem.summary()}")

        # #4 — Latency summary périodique
        if cycle % cfg.display_frequency == 0:
            print(f"[LATENCY] {latency_monitor.summary_text()}")
            print(f"[SHADOW]  {shadow_engine.stats()}")

        watchdog.tick_heartbeat(
            f"cycle={cycle} signal={action} score={live_signal.score} "
            f"regime={regime} pnl={paper.total_pnl():+.2f}"
        )

        # ── 14. RAPPORT HEBDOMADAIRE (Phase 6) ────────────────────────────────

        if cycle % _weekly_cycle == 0:
            weekly_report = weekly_agent.generate()
            print(f"\n{weekly_report.text_summary}\n")
            alerts.on_weekly_report(weekly_report)

        # ── 15. STREAMBUS STATS ────────────────────────────────────────────────

        if cycle % 20 == 0:
            s = bus.stats()
            print(
                f"StreamBus — ticks: {s['tick_count']} | drops: {s['drop_count']} "
                f"({s['drop_rate']:.1%}) | queue: {s['queue_size']} | age: {s['last_update_age']:.2f}s"
            )

        if cfg.max_cycles > 0 and cycle >= cfg.max_cycles:
            break

        time.sleep(max(0, cfg.sleep_seconds))

    # ── FIN ────────────────────────────────────────────────────────────────────

    health.update("system", {"status": "stopped", "ok": False})
    health.stop()

    _log.info("[Main] Système arrêté après %d cycles", cycle)
    _log.info("[Main] Post-mortem final: %s", postmortem.summary())
    if advisor_mode.active:
        _log.info("[Main] Advisor-only: %s", advisor_mode.summary())


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_runtime_from_args() -> tuple[RuntimeConfig, bool, bool, bool]:
    parser = argparse.ArgumentParser(description="Run V9.1 autonomous quant system")
    parser.add_argument(
        "--dry-run", action="store_true", help="Valider la config et quitter"
    )
    parser.add_argument(
        "--doctor-prompt-only",
        action="store_true",
        help="Afficher le prompt Bot Doctor et quitter",
    )
    parser.add_argument("--max-cycles", type=int, help="Override V9_MAX_CYCLES")
    parser.add_argument("--population", type=int, help="Override V9_POPULATION")
    parser.add_argument("--sleep-seconds", type=int, help="Override V9_SLEEP_SECONDS")
    parser.add_argument(
        "--radar", action="store_true", help="Lancer un sweep Market Radar et quitter"
    )
    parser.add_argument(
        "--dashboard", action="store_true", help="Activer le Director Dashboard"
    )
    parser.add_argument(
        "--advisor-only",
        action="store_true",
        help="Forcer V9_ADVISOR_ONLY (analyse sans trading)",
    )
    args = parser.parse_args()

    cfg = load_runtime_config_from_env()
    if args.max_cycles is not None:
        cfg.max_cycles = max(0, args.max_cycles)
    if args.population is not None:
        cfg.population_size = max(1, args.population)
    if args.sleep_seconds is not None:
        cfg.sleep_seconds = max(0, args.sleep_seconds)
    if args.dry_run:
        cfg.dry_run = True
    if args.dashboard:
        cfg.director_dashboard_enabled = True
    if args.advisor_only:
        os.environ["V9_ADVISOR_ONLY"] = "true"

    return cfg, bool(args.doctor_prompt_only), bool(args.radar), bool(args.dashboard)


if __name__ == "__main__":
    runtime_cfg, doctor_prompt_only, radar_only, dashboard_mode = (
        _build_runtime_from_args()
    )

    if radar_only:
        from quant_hedge_ai.agents.intelligence import FeatureEngineer as _FE
        from quant_hedge_ai.agents.market.market_scanner import (
            MarketScanner as _Scanner,
        )

        _scanner = _Scanner()
        _fe = _FE()
        _candles = _scanner.scan()["candles"]
        _features = _fe.extract_features(_candles)
        _radar = MarketRadar(whale_threshold_usd=runtime_cfg.whale_threshold_usd)
        _report = _radar.sweep(_candles, _features)
        print("\n📡 AI Market Radar — Single Sweep\n")
        for opp in _report.top(10):
            print(f"  {opp.symbol:20s}  score={opp.score:5.1f}  risk={opp.risk_level}")
        print(f"\nSummary: {_report.as_dict()}")

    elif doctor_prompt_only:
        doctor_agent = CreatePromptAgent()
        print(doctor_agent.generate_prompt())

    elif runtime_cfg.dry_run:
        print("[DRY-RUN] Configuration runtime :")
        for k, v in runtime_cfg.as_dict().items():
            print(f"  - {k}: {v}")
        print("\n[DRY-RUN] Bot Doctor Prompt:")
        doctor_agent = CreatePromptAgent()
        print(doctor_agent.generate_prompt())

    else:
        _watchdog = OpsWatchdog.from_env()
        try:
            run_v91_system(runtime=runtime_cfg, enable_director=dashboard_mode)
        except KeyboardInterrupt:
            _watchdog.notify_shutdown("keyboard interrupt")
            raise
        except Exception as _exc:
            if _watchdog._notifier:
                _watchdog._notifier.crash("run_v91_system", _exc)
            raise
