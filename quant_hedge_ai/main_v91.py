from __future__ import annotations

import argparse
import logging
import os
import random
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from quant_hedge_ai.agents.execution.arbitrage_agent import ArbitrageAgent
except ModuleNotFoundError as e:
    import os
    import sys

    print("\n[ERREUR] Le module 'quant_hedge_ai' est introuvable.\n")
    print(
        "Conseil : Lancez ce script depuis la racine du projet, pas depuis un sous-dossier."
    )
    print(
        "Exemple :\n    cd "
        + os.path.dirname(os.path.dirname(__file__))
        + "\n    .venv\\Scripts\\Activate.ps1\n    python -m quant_hedge_ai.main_v91\n"
    )
    sys.exit(1)
# === GlobalRiskGate ===
import asyncio
import threading

from global_risk_gate import GlobalRiskGate, RiskLevel, RiskThresholds
from notifications import build_telegram_bot, send_alert
from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
from quant_hedge_ai.agents.execution.liquidity_agent import LiquidityAnalyzer
from quant_hedge_ai.agents.execution.multi_timeframe_signal import \
    MultiTimeframeSignal
from quant_hedge_ai.agents.execution.paper_trading_engine import \
    PaperTradingEngine
from quant_hedge_ai.agents.execution.signal_engine import compute_signal
from quant_hedge_ai.agents.intelligence import FeatureEngineer
from quant_hedge_ai.agents.intelligence.regime_detector import \
    AdvancedRegimeDetector
from quant_hedge_ai.agents.market.market_scanner import MarketScanner
from quant_hedge_ai.agents.market.multi_timeframe_scanner import \
    MultiTimeframeScanner
from quant_hedge_ai.agents.market.orderflow_agent import OrderFlowAnalyzer
from quant_hedge_ai.agents.market.volatility_agent import VolatilityDetector
from quant_hedge_ai.agents.monitoring.performance_monitor import \
    PerformanceMonitor
from quant_hedge_ai.agents.monitoring.prompt_doctor_agent import \
    CreatePromptAgent
from quant_hedge_ai.agents.monitoring.system_monitor import SystemMonitor
from quant_hedge_ai.agents.portfolio import PortfolioBrain
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
from quant_hedge_ai.agents.quant.monte_carlo import MonteCarloSimulator
from quant_hedge_ai.agents.quant.portfolio_optimizer import PortfolioOptimizer
from quant_hedge_ai.agents.research.feature_engineer import \
    FeatureEngineer as LegacyFeatureEngineer
from quant_hedge_ai.agents.research.model_builder import ModelBuilder
from quant_hedge_ai.agents.research.paper_analyzer import PaperAnalyzer
from quant_hedge_ai.agents.research.strategy_researcher import \
    StrategyResearcher
from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard
from quant_hedge_ai.agents.risk.exposure_manager import ExposureManager
from quant_hedge_ai.agents.risk.risk_monitor import RiskMonitor
from supervision.ops_watchdog import OpsWatchdog
from quant_hedge_ai.agents.strategy.genetic_optimizer import GeneticOptimizer
from quant_hedge_ai.agents.strategy.rl_trader import RLTrader
from quant_hedge_ai.agents.strategy.strategy_generator import StrategyGenerator
from quant_hedge_ai.agents.whales import WhaleRadar
from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine
from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore
from quant_hedge_ai.dashboard.control_center import AIControlCenter
from quant_hedge_ai.dashboard.director_dashboard import DirectorDashboard
from quant_hedge_ai.databases.strategy_scoreboard import StrategyScoreboard
from quant_hedge_ai.engine.decision_engine import (DecisionEngine,
                                                   StrategyRanker)
from quant_hedge_ai.liquidity_map.flow_analyzer import LiquidityFlowMap
from quant_hedge_ai.market_radar import MarketRadar
from quant_hedge_ai.runtime_config import (RuntimeConfig, get_env_int,
                                           load_runtime_config_from_env)
from quant_hedge_ai.strategy_factory import StrategyFactory
from quant_hedge_ai.strategy_lab.market_db import MarketDatabase
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from stream_bus import StreamBus


def _get_env_int(name: str, default: int, min_value: int | None = None) -> int:
    """Wrapper rétrocompatible pour l'analyse des entiers de configuration d'exécution."""
    return get_env_int(name, default, min_value=min_value)


def _start_streambus_background(bus: StreamBus) -> None:
    """
    Démarre StreamBus dans un event loop dédié (thread daemon).
    Permet d'utiliser le reste du script en mode sync sans `asyncio.create_task`
    (qui nécessite un loop déjà running).
    """

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


def run_v91_system(
    max_cycles: int = 3,
    population_size: int = 300,
    sleep_seconds: int = 2,
    runtime: RuntimeConfig | None = None,
    enable_director: bool = False,
) -> None:
    """V9.1 - Laboratoire Quant Autonome avec Cerveau de Portefeuille IA + Radar Baleine + Couche Intelligence."""
    os.chdir(Path(__file__).resolve().parent)

    cfg = runtime or RuntimeConfig(
        max_cycles=max_cycles,
        population_size=population_size,
        sleep_seconds=sleep_seconds,
    )
    random.seed(cfg.seed)

    # ===== MARCHÉ & INTELLIGENCE =====
    scanner = MarketScanner()
    orderflow = OrderFlowAnalyzer()
    vol_detector = VolatilityDetector()
    feature_eng = FeatureEngineer()
    regime_detector = AdvancedRegimeDetector()

    # ===== RADAR BALEINE =====
    whale_radar = WhaleRadar(threshold_usd=cfg.whale_threshold_usd)

    # ===== RADAR MARCHÉ IA (NOUVEAU !) =====
    market_radar = MarketRadar(
        min_liquidity_usd=1_000.0,
        min_volume_usd=500.0,
        whale_threshold_usd=cfg.whale_threshold_usd,
    )

    # ===== GÉNÉRATION & ÉVOLUTION DE STRATÉGIE =====
    strategy_generator = StrategyGenerator()
    optimizer = GeneticOptimizer()
    rl_trader = RLTrader()
    strategy_factory = StrategyFactory()

    # ===== MÉMOIRE STRATÉGIQUE (auto-amélioration par régime) =====
    memory_store = StrategyMemoryStore()

    # ===== MULTI-TIMEFRAME (confirmation des signaux) =====
    mtf_scanner = MultiTimeframeScanner(
        symbols=[s if "/" in s else s[:3] + "/" + s[3:] for s in scanner.symbols],
        timeframes=["4h", "1d"],
        refresh_every=4,
    )
    mtf_signal = MultiTimeframeSignal(min_strength=0.5, min_agreement=2)

    # ===== MOTEUR D'ÉVOLUTION IA (NOUVEAU !) =====
    evolution_engine = EvolutionEngine(
        population_size=max(30, cfg.population_size // 5),
        memory_seed_ratio=0.3,
        generations=max(1, cfg.generations - 1),
    )

    # ===== CARTE DES FLUX DE LIQUIDITÉ (NOUVEAU !) =====
    flow_map = LiquidityFlowMap(opportunity_threshold=40.0)

    # ===== LABORATOIRE QUANT =====
    backtest_lab = BacktestLab()
    monte_carlo = MonteCarloSimulator()

    # ===== CERVEAU DE PORTEFEUILLE (NOUVEAU !) =====
    portfolio_brain = PortfolioBrain()

    # ===== MOTEUR DE DÉCISION (NOUVEAU !) =====
    decision_engine = DecisionEngine(
        min_sharpe=cfg.min_sharpe_for_trade,
        max_drawdown_for_trade=cfg.trade_max_drawdown,
        whale_block_threshold=cfg.whale_block_threshold,
    )
    ranker = StrategyRanker()

    # ===== AGENTS TRADITIONNELS =====
    paper_analyzer = PaperAnalyzer()
    legacy_feature_eng = LegacyFeatureEngineer()
    strategy_researcher = StrategyResearcher()
    model_builder = ModelBuilder()

    # ===== GESTION DES RISQUES =====
    risk_monitor = RiskMonitor(max_drawdown=cfg.max_drawdown)
    drawdown_guard = DrawdownGuard()
    exposure_manager = ExposureManager()

    # ===== EXÉCUTION =====
    execution = ExecutionEngine.from_env()
    arbitrage = ArbitrageAgent()
    liquidity = LiquidityAnalyzer()
    paper = PaperTradingEngine()

    # ===== MONITORING OPÉRATIONNEL =====
    watchdog = OpsWatchdog.from_env()
    watchdog.enable_heartbeat(interval_seconds=3600.0)

    # ===== SURVEILLANCE =====
    perf_monitor = PerformanceMonitor()
    system_monitor = SystemMonitor()
    control_center = AIControlCenter()
    director = (
        DirectorDashboard(starting_balance=100_000.0) if enable_director else None
    )
    doctor_agent = CreatePromptAgent()

    # ===== BASES DE DONNÉES =====
    market_db = MarketDatabase()
    strategy_db = StrategyDatabase()
    scoreboard = StrategyScoreboard()

    # === Initialisation StreamBus (WebSocket permanent) ===
    bus = StreamBus(
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ARB/USDT"],
        exchange_id="binance",
        exchange_config={
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        },
        whale_threshold_usd=500_000,
        queue_maxsize=5000,
    )
    _start_streambus_background(bus)
    # Attente que le snapshot soit peuplé avant le premier cycle
    time.sleep(3)
    print(f"StreamBus prêt — {bus.stats()}")

    execution.start_session(equity=paper.balance)
    watchdog.notify_startup(
        mode="live" if execution._live else "paper",
        symbols=scanner.symbols,
    )

    # === Initialisation GlobalRiskGate ===
    _telegram_bot = build_telegram_bot()
    gate = GlobalRiskGate(
        thresholds=RiskThresholds(
            drawdown_warning=-0.08,
            drawdown_critical=-0.15,
            correlation_warning=0.75,
            correlation_critical=0.90,
            vol_multiplier_warning=2.5,
            vol_multiplier_critical=4.0,
            exposure_warning=0.70,
            exposure_critical=0.90,
            cooldown_seconds=300,
            warning_size_factor=0.50,
        ),
        telegram_bot=_telegram_bot,
        baseline_vol=0.02,
    )

    cycle = 0
    _prev_doctor_health = 100.0  # suivi de la santé du doctor sur les cycles
    while True:
        cycle += 1
        print("\n[START] Démarrage du cycle V9.1 ...")

        # === GlobalRiskGate : vérification systémique ===
        try:
            snap = asyncio.run(gate.check(portfolio_brain, scoreboard, market_db))
        except RuntimeError:
            snap = asyncio.get_event_loop().run_until_complete(
                gate.check(portfolio_brain, scoreboard, market_db)
            )
        if snap.level == RiskLevel.CRITICAL:
            print(f"[RISK GATE] Cycle {cycle} bloqué — {snap.message}")
            continue  # skip complet du cycle
        execution.set_size_factor(snap.size_factor)
        paper.set_size_factor(snap.size_factor)

        # === Lecture snapshot StreamBus dans le cycle ML ===
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
        if cycle % 20 == 0:
            s = bus.stats()
            print(
                f"StreamBus stats — ticks: {s['tick_count']} | "
                f"drops: {s['drop_count']} ({s['drop_rate']:.1%}) | "
                f"queue: {s['queue_size']} | "
                f"age: {s['last_update_age']:.2f}s"
            )

        # ===== 1. SCAN MARCHÉ + INTELLIGENCE =====
        try:
            market = scanner.scan()
        except Exception as _scan_exc:
            logger.error("[Cycle %d] scanner.scan() échoué: %s — cycle ignoré", cycle, _scan_exc)
            time.sleep(cfg.sleep_seconds)
            continue

        candles = market.get("candles", [])
        if not candles:
            logger.warning("[Cycle %d] Aucune bougie reçue — cycle ignoré", cycle)
            time.sleep(cfg.sleep_seconds)
            continue

        # Vérification de fraîcheur des données StreamBus
        bus_age = bus.snapshot.updated_at
        if time.time() - bus_age > 30:
            logger.warning("[Cycle %d] StreamBus stale (%.0fs) — données WS peut-être obsolètes", cycle, time.time() - bus_age)
            watchdog.check_ws_staleness("StreamBus", bus_age, threshold_seconds=120.0)

        market_db.save_snapshot(market)
        dq = scanner.data_quality()
        if dq["real_ratio"] < 0.5 and cycle > 1:
            logger.warning(
                "[Cycle %d] Qualité données faible : %.0f%% réelles (circuit=%s)",
                cycle, dq["real_ratio"] * 100, dq["circuit_state"],
            )

        symbols = [c["symbol"] for c in candles]
        close_prices = [float(c["close"]) for c in candles]

        # Ingénierie avancée des features
        features = feature_eng.extract_features(candles)
        anomalies = feature_eng.detect_anomalies(features)

        # Détection de régime
        regime = regime_detector.classify(features, close_prices)
        suggested_strategy_type = regime_detector.suggest_strategy_type(regime)

        # Scan baleine
        whale_data = []
        for c in candles:
            whale_scan = whale_radar.scan(
                c["symbol"], float(c["volume"]), float(c["close"])
            )
            whale_data.append(whale_scan)

        whale_alerts = [alert for w in whale_data for alert in w["alerts"]]

        # ===== 1b. RADAR MARCHÉ IA (NOUVEAU !) =====
        radar_report = market_radar.sweep(candles, features, whale_alerts)
        radar_summary = radar_report.as_dict()
        if cycle % cfg.display_frequency == 0:
            top_opps = radar_report.top(3)
            opp_display = (
                ", ".join(f"{o.symbol}({o.score:.0f})" for o in top_opps) or "aucune"
            )
            print(
                f"[RADAR] Radar Marché : {radar_summary['opportunities_count']} opportunités | "
                f"risque={radar_summary['risk_level']} | flux_baleine={radar_summary['whale_flow']} | "
                f"social={radar_summary['social_sentiment']:.2f} | top : {opp_display}"
            )

        # ===== 2. GÉNÉRATION & ÉVOLUTION DE STRATÉGIE =====
        # Seed depuis la mémoire : top stratégies du régime courant (25 % de la pop)
        _mem_limit = max(5, cfg.population_size // 4)
        _mem_seed = [
            r.get("strategy", r)
            for r in memory_store.load_by_regime(regime, limit=_mem_limit)
            if isinstance(r, dict)
        ]
        _fresh_count = max(1, cfg.population_size - len(_mem_seed))
        population = _mem_seed + strategy_generator.generate_population(_fresh_count)
        evolved = optimizer.evolve(population, generations=cfg.generations)

        # ===== 3. BACKTESTING LAB =====
        # Utilise la série historique complète (200 bougies) du premier symbole
        _bt_symbol = symbols[0] if symbols else scanner.symbols[0]
        bt_data = market.get("history", {}).get(_bt_symbol, candles)
        results = [backtest_lab.run_backtest(strategy=s, data=bt_data) for s in evolved]

        # ===== 3b. AI STRATEGY FACTORY (NEW!) =====
        factory_report = strategy_factory.run(
            candles,
            target_count=max(30, min(120, cfg.population_size)),
            generations=max(1, cfg.generations - 1),
            regime=regime,
            history=bt_data,
        )
        strategy_factory_summary = factory_report.as_dict()
        results.extend(factory_report.approved_results)

        if cycle % cfg.display_frequency == 0:
            print(
                f"[FACTORY] Strategy Factory: gen={strategy_factory_summary['generated_count']} "
                f"bt={strategy_factory_summary['backtested_count']} "
                f"filt={strategy_factory_summary['filtered_count']} "
                f"approved={strategy_factory_summary['approved_count']} "
                f"blocked={strategy_factory_summary['blocked_count']} "
                f"mem_load={strategy_factory_summary.get('memory_loaded_count', 0)} "
                f"mem_save={strategy_factory_summary.get('memory_saved_count', 0)}"
            )

        # ===== 3c. AI EVOLUTION ENGINE (NEW!) =====
        evo_report = evolution_engine.run_cycle(
            cycle=cycle,
            regime=regime,
            candles=bt_data,
            doctor_health=_prev_doctor_health,
        )
        if cycle % cfg.display_frequency == 0:
            print(evolution_engine.render(evo_report))

        # ===== 3d. LIQUIDITY FLOW MAP (NEW!) =====
        flow_report = flow_map.analyze(
            candles=candles,
            whale_alerts=whale_alerts,
            regime=regime,
            cycle=cycle,
        )
        if cycle % cfg.display_frequency == 0:
            print(flow_map.render(flow_report))

        ranked = decision_engine.select_strategies(results, top_n=20)

        # ===== 4. STRATEGY SCOREBOARD (NEW!) =====
        for strategy_result in ranked[:10]:
            strategy = strategy_result.get("strategy")
            if strategy is not None:
                scoreboard.add(strategy, {**strategy_result, "cycle": cycle})

        scoreboard_stats = scoreboard.stats()

        # ===== 5. RISK FILTERING =====
        filtered = [r for r in ranked if risk_monitor.check(r)]
        top_results = filtered[:10] if filtered else ranked[:10]

        best = strategy_researcher.best(top_results)

        # Alerte Telegram si une stratégie exceptionnelle est trouvée (Sharpe > 3)
        _best_sharpe = float(best.get("sharpe", 0.0)) if best else 0.0
        if _best_sharpe >= 3.0:
            _strat = best.get("strategy", {})
            send_alert(
                f"[V9.1] Cycle {cycle} — Stratégie Sharpe {_best_sharpe:.2f}\n"
                f"Indicateur: {_strat.get('entry_indicator','?')} | "
                f"Période: {_strat.get('period','?')} | "
                f"PnL: {best.get('pnl', 0.0):.2f}% | "
                f"Win rate: {best.get('win_rate', 0.0):.1%} | "
                f"DD: {best.get('drawdown', 0.0):.2%}"
            )

        # Sauvegarder les gagnants dans la mémoire par régime (auto-amélioration)
        _winners = [
            r
            for r in top_results
            if float(r.get("sharpe", 0.0)) >= cfg.min_sharpe_for_trade
        ]
        if _winners:
            _saved = memory_store.save_for_regime(regime, _winners[:10])
            if cycle % cfg.display_frequency == 0:
                print(
                    f"[MEMORY] {_saved} stratégies sauvegardées "
                    f"(régime={regime}, sharpe_min={cfg.min_sharpe_for_trade})"
                )

        strategy_scores = [
            {
                "strategy_id": f"strat_{i}",
                "sharpe": float(r.get("sharpe", 0.0)),
                "drawdown": float(r.get("drawdown", 0.01)),
                "win_rate": float(r.get("win_rate", 0.5)),
            }
            for i, r in enumerate(top_results[:10])
        ]
        portfolio_allocation = portfolio_brain.compute_allocation(
            strategy_scores,
            features.get("realized_volatility", 0.02),
            max_strategy_weight=cfg.max_strategy_weight,
        )

        # ===== 7. DECISION ENGINE (NEW!) =====
        should_trade = decision_engine.should_trade(best, regime, whale_alerts)
        risk_limits = decision_engine.compute_risk_limits(
            features.get("realized_volatility", 0.02),
            max_risk=cfg.max_risk_per_trade,
        )

        # ===== 8. MODEL RETRAINING =====
        model_info = model_builder.retrain(top_results)

        # ===== 9. PAPER TRADING EXECUTION =====
        tradable = liquidity.filter_symbols(candles)
        symbol = tradable[0] if tradable else candles[0]["symbol"]
        price = next(float(c["close"]) for c in candles if c["symbol"] == symbol)

        # Signal multi-timeframe depuis la meilleure stratégie (ou RL en fallback)
        if should_trade and best:
            _best_strat = best.get("strategy", {})
            # Construire le dict MTF : 1h déjà en cache + 4h/1d fetchés périodiquement
            _mtf_raw = mtf_scanner.scan(cycle=cycle)
            _mtf_sym = (
                _bt_symbol
                if "/" in _bt_symbol
                else _bt_symbol[:3] + "/" + _bt_symbol[3:]
            )
            _mtf_candles = MultiTimeframeScanner.merge_base(_mtf_raw, _mtf_sym, bt_data)
            _mtf_result = mtf_signal.confirm(_best_strat, _mtf_candles)
            action = _mtf_result["signal"]  # HOLD si non confirmé
            if cycle % cfg.display_frequency == 0:
                print(f"[MTF] {mtf_signal.summary(_mtf_result)}")
            if action == "HOLD":
                action_state = (
                    f"{regime}:{'pos' if features['momentum'] > 0 else 'neg'}"
                )
                action = rl_trader.choose_action(action_state)
        else:
            action_state = f"{regime}:{'pos' if features['momentum'] > 0 else 'neg'}"
            action = rl_trader.choose_action(action_state)
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

        dd = float(best.get("drawdown", 0.0)) if best else 0.0
        size = drawdown_guard.adjust_position_size(dd, base_size=1.0)

        order = execution.create_order(symbol=symbol, action=action, size=size)
        watchdog.on_order_result(order)
        watchdog.on_session_guard(execution._guard)
        paper_state = paper.execute(order, mark_price=price)

        if cycle % cfg.display_frequency == 0:
            snap = paper.snapshot(mark_prices={symbol: price})
            print(
                f"[PAPER] balance={snap['balance']:,.0f} | "
                f"P&L={snap['pnl_pct']:+.2f}% | "
                f"trades={snap['n_trades']} | win_rate={snap['win_rate']:.1%} | "
                f"signal={action}"
            )

        # ===== 9b. DIRECTOR SUPER DASHBOARD UPDATE (NEW!) =====
        doctor_result_for_director = {
            "health_score": 100.0,
            "top_recommendation": "",
            "findings": [],
        }
        doctor_corrections_for_director: list[str] = []
        _prev_doctor_health = 100.0  # default; updated below if doctor runs

        if cfg.doctor_telegram_enabled:
            primary_allocation = next(iter(portfolio_allocation.values()), None)
            risk_level = "high" if dd > 0.10 else ("medium" if dd > 0.05 else "low")
            doctor_input = {
                "trade_signal": action,
                "allocation": primary_allocation,
                "risk_level": risk_level,
            }
            corrected_strategy, doctor_issues = (
                doctor_agent.apply_doctor_corrections_with_issues(
                    doctor_input,
                )
            )
            doctor_corrections_for_director = doctor_issues
            _prev_doctor_health = max(0.0, 100.0 - len(doctor_issues) * 20.0)

            # Envoi simulé des alertes Telegram via la méthode dédiée
            doctor_agent.simulate_telegram_alerts(
                cfg.doctor_telegram_user_id, corrected_strategy
            )

            if cfg.doctor_v26_report_enabled and cycle % cfg.display_frequency == 0:
                doctor_report = doctor_agent.build_v26_compatible_report(doctor_issues)
                print(f"[Bot Doctor V26 Report] {doctor_report}")
                if cfg.doctor_report_export_enabled:
                    exported_path = doctor_agent.export_v26_report(
                        report=doctor_report,
                        output_dir=cfg.doctor_report_export_dir,
                        cycle=cycle,
                    )
                    print(f"[Bot Doctor V26 Report] Exported JSON: {exported_path}")

            if cycle % cfg.display_frequency == 0:
                evolution = doctor_agent.build_evolution_snapshot(doctor_issues)
                print(f"[Bot Doctor Evolution] {evolution}")

            if cycle % cfg.display_frequency == 0:
                print(
                    f"[Bot Doctor] Strategy snapshot after corrections: {corrected_strategy}"
                )

        # ===== 9c. Director Dashboard update =====
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
                strategy_factory_summary=strategy_factory_summary,
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

        # ===== 10. MONITORING & CONTROL CENTER (NEW!) =====
        heartbeat = system_monitor.heartbeat(cycle)
        performance = perf_monitor.summarize(top_results)

        # Prepare control center data
        market_regime_data = {
            "regime": regime,
            "strategy_type": suggested_strategy_type,
            "momentum": features["momentum"],
            "realized_volatility": features["realized_volatility"],
            "anomalies": anomalies,
            "radar": radar_summary,
        }

        whale_radar_data = {
            "alerts": whale_alerts,
            "threat_level": max(
                (w["threat_level"] for w in whale_data), default="low", key=str.lower
            ),
        }

        decision_data = {
            "should_trade": should_trade,
            "reason": (
                "High Sharpe + Low DD"
                if should_trade
                else "Market conditions unfavorable"
            ),
            "risk_limits": risk_limits,
        }

        health_data = {
            "status": "running",
            "agents_count": 20,
            "strategies_gen": len(evolved),
            "backtests_completed": len(results),
            "model_version": model_info.get("model_version", 1),
        }

        portfolio_brain_info = {
            "kelly_fraction": 0.25,
            "vol_target": features["realized_volatility"],
            "max_position": 0.3,
        }

        # Render control center
        report = control_center.render_full_report(
            cycle,
            market_regime_data,
            whale_radar_data,
            best,
            scoreboard_stats,
            portfolio_allocation,
            portfolio_brain_info,
            decision_data,
            health_data,
            flow_data=flow_report.as_dict(),
        )

        if cycle % cfg.display_frequency == 0:
            print(report)
            if director is not None and director_snapshot is not None:
                print(director.render(director_snapshot))
        bounded_vol = min(0.08, max(0.001, features["realized_volatility"]))
        mc = monte_carlo.simulate(
            mean_return=0.0005,
            volatility=bounded_vol,
            steps=cfg.monte_carlo_steps,
            paths=cfg.monte_carlo_paths,
        )
        if cycle % cfg.display_frequency == 0:
            print(f"[MONTECARLO] MonteCarlo Results: {mc}")
            print(f"[PAPER] Paper Trading State: {paper_state}")

        watchdog.tick_heartbeat(f"cycle={cycle} signal={action} pnl={paper.total_pnl():+.2f}")

        if cfg.max_cycles > 0 and cycle >= cfg.max_cycles:
            break

        time.sleep(max(0, cfg.sleep_seconds))


def _build_runtime_from_args() -> tuple[RuntimeConfig, bool, bool, bool]:
    parser = argparse.ArgumentParser(description="Run V9.1 autonomous quant system")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print runtime config, then exit",
    )
    parser.add_argument(
        "--doctor-prompt-only",
        action="store_true",
        help="Print only the Bot Doctor prompt payload JSON, then exit",
    )
    parser.add_argument("--max-cycles", type=int, help="Override V9_MAX_CYCLES")
    parser.add_argument("--population", type=int, help="Override V9_POPULATION")
    parser.add_argument("--sleep-seconds", type=int, help="Override V9_SLEEP_SECONDS")
    parser.add_argument(
        "--radar", action="store_true", help="Run a single Market Radar sweep and exit"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Enable Director Super Dashboard output each cycle",
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

    return cfg, bool(args.doctor_prompt_only), bool(args.radar), bool(args.dashboard)


if __name__ == "__main__":
    runtime_cfg, doctor_prompt_only, radar_only, dashboard_mode = (
        _build_runtime_from_args()
    )
    if radar_only:
        from agents.intelligence import FeatureEngineer as _FE
        from agents.market.market_scanner import MarketScanner as _Scanner

        _scanner = _Scanner()
        _fe = _FE()
        _candles = _scanner.scan()["candles"]
        _features = _fe.extract_features(_candles)
        _radar = MarketRadar(whale_threshold_usd=runtime_cfg.whale_threshold_usd)
        _report = _radar.sweep(_candles, _features)
        print("\n📡 AI Market Radar — Single Sweep\n")
        for opp in _report.top(10):
            print(
                f"  {opp.symbol:20s}  score={opp.score:5.1f}  risk={opp.risk_level:6s}  "
                f"whale={opp.whale_signal:14s}  flags={opp.flags}"
            )
        print(f"\nSummary: {_report.as_dict()}")
    elif doctor_prompt_only:
        doctor_agent = CreatePromptAgent()
        print(doctor_agent.generate_prompt())
    elif runtime_cfg.dry_run:
        print("[DRY-RUN] Runtime configuration loaded:")
        for key, value in runtime_cfg.as_dict().items():
            print(f"  - {key}: {value}")

        print("\n[DRY-RUN] Bot Doctor Prompt Payload:")
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
