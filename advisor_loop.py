"""
advisor_loop.py — Boucle d'observation multi-symboles en mode ADVISOR ONLY.

Analyse BTC/USDT, ETH/USDT, SOL/USDT toutes les 5 minutes.
Envoie un rapport Telegram toutes les 15 min (cycle 3, 6, 9...).
Alerte immédiate si un signal actionable est détecté (score >= 70).
Watchdog surveille les latences et auto-heal si dégradation.

Usage:
    python advisor_loop.py
    python advisor_loop.py --interval 300   # 5 min (défaut)
    python advisor_loop.py --interval 60    # 1 min (debug)
    python advisor_loop.py --symbols BTC/USDT ETH/USDT
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import sys
import time
from typing import Any, cast

from advisor_runtime_adapters import AdvisorRuntime, load_advisor_runtime

# IMPORTANT : créer logs/ avant FileHandler
os.makedirs("logs", exist_ok=True)

import requests
from dotenv import load_dotenv

JSONDict = dict[str, Any]
Candle = dict[str, Any]
Candles = list[Candle]
MTFCandles = dict[str, Candles]
AnalysisResult = dict[str, Any]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stats_dict(value: Any) -> JSONDict:
    return cast(JSONDict, value if isinstance(value, dict) else {})


def _snapshot_list(value: Any) -> list[JSONDict]:
    return cast(list[JSONDict], value if isinstance(value, list) else [])


def _get_exchange_futures(exec_engine: Any) -> Any:
    return getattr(exec_engine, "_exchange_futures", None)


def _get_regret_counts(regret_engine: Any) -> tuple[int, int]:
    records = cast(list[Any], getattr(regret_engine, "_records", []))
    candidates = cast(list[Any], getattr(regret_engine, "_candidates", []))
    return len(records), len(candidates)

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("V9_LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/advisor_loop.log", encoding="utf-8"),
    ],
)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("advisor_loop")

SYMBOLS_DEFAULT = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
NOTIFY_EVERY    = int(os.getenv("ADVISOR_NOTIFY_EVERY", "3"))
MTF_REFRESH_EVERY = int(os.getenv("ADVISOR_MTF_REFRESH_EVERY", "12"))
ADVISOR_1H_LIMIT = int(os.getenv("ADVISOR_1H_LIMIT", "96"))
ADVISOR_PREWARM_1H = os.getenv(
    "ADVISOR_PREWARM_1H",
    os.getenv("ADVISOR_WARMUP", "true"),
).lower() == "true"
# Prewarm MTF optionnel (4h + 1d) en parallèle du bootstrap.
# Ne s'active que si ADVISOR_PREWARM_1H est aussi actif (même executor).
# Désactivé par défaut — activer avec ADVISOR_PREWARM_MTF=true.
ADVISOR_PREWARM_MTF = (
    os.getenv("ADVISOR_PREWARM_MTF", "false").lower() == "true"
    and ADVISOR_PREWARM_1H
)
ADVISOR_LIVE_EXECUTION_BOOTSTRAP = os.getenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false").lower() == "true"
ADVISOR_BACKGROUND_POSITION_WATCH = os.getenv("ADVISOR_BACKGROUND_POSITION_WATCH", "false").lower() == "true"
ADVISOR_DEFER_OPTIONAL_INTEL = os.getenv("ADVISOR_DEFER_OPTIONAL_INTEL", "true").lower() == "true"
ADVISOR_DEFER_POST_CYCLE_SERVICES = os.getenv("ADVISOR_DEFER_POST_CYCLE_SERVICES", "true").lower() == "true"
ADVISOR_STARTUP_LIGHT = os.getenv("ADVISOR_STARTUP_LIGHT", "false").lower() == "true"
ADVISOR_THREAT_RADAR_EVERY = max(1, int(os.getenv("ADVISOR_THREAT_RADAR_EVERY", "1")))
ADVISOR_CYCLE_BUDGET_SECONDS = float(os.getenv("ADVISOR_CYCLE_BUDGET_SECONDS", "0"))
ADVISOR_LOAD_SHED_CYCLES = max(1, int(os.getenv("ADVISOR_LOAD_SHED_CYCLES", "1")))
# Warmup persistant : thread daemon qui maintient le cache OHLCV chaud entre les cycles.
# Active avec ADVISOR_PERSISTENT_WARMUP=true ; ne remplace pas ADVISOR_PREWARM_1H.
ADVISOR_PERSISTENT_WARMUP = os.getenv("ADVISOR_PERSISTENT_WARMUP", "false").lower() == "true"
# Session primer — pre-create the CCXT exchange and call load_markets() in a daemon thread
# launched BEFORE scanner creation so exchange_init + load_markets overlap the full bootstrap.
# Prewarm threads then skip directly to fetch_ohlcv(), saving up to ~650ms from cycle 1.
ADVISOR_SESSION_PRIMER = os.getenv("ADVISOR_SESSION_PRIMER", "true").lower() == "true"


def _session_primer_config() -> JSONDict:
    return {
        "enableRateLimit": True,
        "options": {
            "defaultType": "spot",
            "adjustForTimeDifference": os.getenv(
                "MARKET_SCANNER_ADJUST_TIME", "false"
            ).lower() == "true",
            "connectionPoolSize": int(os.getenv("MARKET_SCANNER_POOL_SIZE", "8")),
        },
    }


def _prime_exchange_session(
    exchange_id: str,
    testnet: bool,
    scanner_cls: Any,
    *,
    trace: bool = False,
) -> float:
    """
    Pre-create the shared CCXT exchange and call load_markets() — runs in a daemon
    thread started before scanner creation so that both steps overlap with the
    bootstrap sequence.  Returns elapsed seconds for the timing report.
    """
    import threading as _threading
    t0 = time.perf_counter()
    key = (exchange_id, testnet)
    try:
        import ccxt  # type: ignore[import]

        config = _session_primer_config()
        exchange = getattr(ccxt, exchange_id)(config)
        t_init_ms = (time.perf_counter() - t0) * 1000
        if testnet:
            exchange.set_sandbox_mode(True)

        # Inject into pool before load_markets so concurrent scanner threads
        # block on exchange_call_lock (inside _ensure_markets_loaded) rather
        # than racing to create a second exchange object.
        with scanner_cls._exchange_pool_lock:
            if key not in scanner_cls._exchange_pool:
                scanner_cls._exchange_pool[key] = exchange
                scanner_cls._exchange_call_locks.setdefault(key, _threading.Lock())
                scanner_cls._exchange_markets_ready.setdefault(key, _threading.Event())
                scanner_cls._exchange_created_at[key] = time.monotonic()
                scanner_cls._exchange_generation.setdefault(key, 0)
                injected = True
            else:
                injected = False

        if injected:
            exchange_call_lock = scanner_cls._get_exchange_call_lock(key)
            markets_ready      = scanner_cls._get_exchange_markets_ready(key)
            if not markets_ready.is_set():
                with exchange_call_lock:
                    if not markets_ready.is_set():
                        exchange.load_markets()
                        markets_ready.set()

        elapsed   = time.perf_counter() - t0
        t_lm_ms   = elapsed * 1000 - t_init_ms
        if trace:
            log.info(
                "[SessionPrimer] exchange_init=%.0fms load_markets=%.0fms total=%.0fms",
                t_init_ms, t_lm_ms, elapsed * 1000,
            )
        return elapsed
    except Exception as exc:
        log.warning("[SessionPrimer] échec (non bloquant): %s", exc)
        return time.perf_counter() - t0


# ── Telegram ──────────────────────────────────────────────────────────────────

def _telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram erreur: %s", r.text)
    except Exception as exc:
        log.warning("Telegram indisponible: %s", exc)


# ── Analyse d'un symbole ──────────────────────────────────────────────────────

def analyze_symbol(
    symbol: str,
    scanners: dict[str, dict[str, Any]],
    engine: Any,
    gate: Any,
    advisor: Any,
    shadow: Any,
    watchdog: Any,
    memory: Any,
    cycle: int,
    order_size_usd: float = 50.0,
    meta_engine: Any = None,
    ranker: Any = None,
    open_positions: list[Any] | None = None,
    consecutive_losses: int = 0,
    no_trade_layer: Any = None,
    conviction_engine: Any = None,
    awareness_engine: Any = None,
    dqe: Any = None,
    portfolio_brain: Any = None,
    capital_engine: Any = None,
    mistake_memory: Any = None,
    executive_override: Any = None,
    black_box: Any = None,
    regret_engine: Any = None,
    threat_radar: Any = None,
    # ── V2 modules (optionnels, enrichissement progressif) ──────────────
    v2_data_unifier: Any = None,
    v2_microstructure: Any = None,
    v2_hmm_regime: Any = None,
    v2_regime_predictor: Any = None,
    v2_arbitrator: Any = None,
    v2_feature_store: Any = None,
    v2_learning: Any = None,
    v2_degradation_monitor: Any = None,
    v2_onchain: Any = None,
    v2_flow_tracker: Any = None,
    v2_slippage_predictor: Any = None,
    v2_execution_optimizer: Any = None,
    v2_timing_engine: Any = None,
    meta_learner: Any = None,
    runtime: AdvisorRuntime | None = None,
) -> AnalysisResult:
    runtime = runtime or load_advisor_runtime()
    MultiTimeframeScanner = runtime.MultiTimeframeScanner
    FeatureEngineer = runtime.FeatureEngineer
    AdvancedRegimeDetector = runtime.AdvancedRegimeDetector
    ConfidenceExplainer = runtime.ConfidenceExplainer

    # Scan 1h
    with watchdog.measure(f"scan_1h_{symbol}"):
        market = scanners["1h"][symbol].scan()
        candles_1h: Candles = cast(
            Candles,
            (
            market.get("history", {}).get(symbol)
            or market.get("candles", {}).get(symbol)
            or []
            ),
        )

    # Scan MTF (4h + 1d)
    with watchdog.measure(f"scan_mtf_{symbol}"):
        mtf_data    = scanners["mtf"][symbol].scan(cycle=cycle)
        mtf_scanner_cls = MultiTimeframeScanner
        mtf_candles: MTFCandles = cast(
            MTFCandles,
            mtf_scanner_cls.merge_base(mtf_data, symbol, candles_1h),
        )

    # ── V2 : Data Unification (enrichit le MarketSnapshot) ───────────────────
    market_snapshot = None
    if v2_data_unifier and candles_1h:
        try:
            market_snapshot = v2_data_unifier.unify(symbol, candles_1h)
        except Exception as _exc_v2:
            log.debug("[V2/DataUnifier] %s skip: %s", symbol, _exc_v2)

    # ── V2 : Microstructure Engine ────────────────────────────────────────────
    micro_report = None
    if v2_microstructure:
        try:
            micro_report = v2_microstructure.analyze(symbol)
        except Exception as _exc_v2:
            log.debug("[V2/Microstructure] %s skip: %s", symbol, _exc_v2)

    # Features + regime
    with watchdog.measure("features"):
        feature_engineer = FeatureEngineer()
        features: JSONDict = cast(
            JSONDict,
            feature_engineer.extract_features(candles_1h) if candles_1h else {},
        )

        # Enrichissement V2 : features microstructure + on-chain
        if market_snapshot:
            features.update({
                "ob_imbalance":       market_snapshot.order_book_imbalance,
                "funding_rate":       market_snapshot.funding_rate,
                "funding_velocity":   market_snapshot.funding_velocity,
                "liquidation_risk":   market_snapshot.liquidation_risk_score,
                "whale_score":        market_snapshot.whale_accumulation_score,
            })
        if micro_report:
            features.update({
                "micro_pressure":     micro_report.directional_pressure,
                "micro_spread_bps":   micro_report.spread_bps,
                "execution_risk":     micro_report.execution_risk,
            })

        try:
            regime_detector = AdvancedRegimeDetector()
            regime = regime_detector.classify(features) if features else "unknown"
        except Exception:
            regime = "unknown"

        # ── V2 : HMM Regime (distribution probabiliste) ──────────────────────
        regime_probs = None
        if v2_hmm_regime and features:
            try:
                regime_probs = v2_hmm_regime.predict(symbol, features)
                # Mise à jour du snapshot avec les probabilités HMM
                if market_snapshot and regime_probs:
                    market_snapshot.regime_bull_prob = regime_probs.bull
                    market_snapshot.regime_bear_prob = regime_probs.bear
                    market_snapshot.regime_chop_prob = regime_probs.chop
                    market_snapshot.regime_volatility_prob = regime_probs.high_vol
                    # Raffinement du régime avec HMM si confiance suffisante
                    if regime_probs.confidence >= 0.50:
                        regime = regime_probs.dominant
            except Exception as _exc_v2:
                log.debug("[V2/HMM] %s skip: %s", symbol, _exc_v2)

        # ── V2 : Regime Transition Predictor ─────────────────────────────────
        transition_forecast = None
        if v2_regime_predictor and regime_probs:
            try:
                transition_forecast = v2_regime_predictor.forecast(symbol, regime_probs, features)
                if transition_forecast.crash_risk:
                    log.warning("[V2/RegimePredictor] %s — CRASH RISK détecté", symbol)
            except Exception as _exc_v2:
                log.debug("[V2/RegimePredictor] %s skip: %s", symbol, _exc_v2)

    # MetaLearner — recommandation exit selon régime + volatilité
    ml_decision = None
    if meta_learner:
        volatility = float(features.get("atr_ratio", features.get("volatility", 0.015)))
        ml_decision = meta_learner.find_best({"regime": regime, "volatility": volatility})
        if ml_decision:
            log.debug("[MetaLearner] %s → exit=%s tp=%s sl=%s",
                      regime, ml_decision.get("exit_type"),
                      ml_decision.get("tp"), ml_decision.get("sl"))

    # Threat Radar — feed candles + check environnement
    radar_report = None
    if threat_radar and candles_1h:
        threat_radar.feed_candles(symbol, candles_1h)
        radar_report = threat_radar.scan_sync([symbol])
        if radar_report.threats:
            log.info("[ThreatRadar] %s: %s", symbol, radar_report.summary)

    # Normalisation de open_positions (accepte int ou list)
    if open_positions is None:
        open_positions = []
    open_positions_list: list[Any] = open_positions
    open_positions_count = len(open_positions_list)

    # Meilleur Sharpe mémorisé — depuis ranker en priorité, sinon memory store
    memory_sharpe = None
    try:
        if ranker:
            memory_sharpe = ranker.best_sharpe(regime) or None
        if not memory_sharpe:
            stored = memory.load_by_regime(regime, limit=10)
            memory_sharpe = max((s.get("sharpe", 0) for s in stored), default=None)
    except Exception:
        memory_sharpe = None

    # ── Meta-Strategy Engine — personnalité adaptée au régime ─────────────────
    personality = None
    if meta_engine:
        with watchdog.measure("meta_strategy"):
            personality = meta_engine.select(
                regime=regime,
                features=features,
                memory_sharpe=memory_sharpe,
                consecutive_losses=consecutive_losses,
                open_positions=open_positions_count,
            )
        # Ajuster la taille d'ordre selon la personnalité
        order_size_usd = meta_engine.effective_order_size(order_size_usd, personality)

    # Signal
    with watchdog.measure("signal"):
        signal = engine.evaluate(symbol, mtf_candles, features=features,
                                 memory_sharpe=memory_sharpe)
    log.info("[FLOW] %s SIGNAL → %s score=%d actionable=%s",
             symbol, signal.signal, signal.score, signal.actionable)

    # ── Validation Meta-Strategy ───────────────────────────────────────────────
    meta_allowed = True
    meta_reason  = "OK"
    if meta_engine and personality:
        meta_allowed, meta_reason = meta_engine.validate_signal(
            signal.signal, signal.score, signal.confirmed, personality
        )

    # Risk gate
    with watchdog.measure("risk"):
        gate_result = gate.check(signal, portfolio_drawdown=0.0, order_size_usd=order_size_usd)
    log.info("[FLOW] %s GATE → %s",
             symbol, "OK" if gate_result.allowed else f"BLOQUÉ({getattr(gate_result, 'reason', '?')})")

    # Advisor
    with watchdog.measure("advisor"):
        advice = advisor.explain(signal)

    # Confidence explainer — décomposition détaillée du score
    explanation = ConfidenceExplainer().explain(signal)

    prix = float(candles_1h[-1].get("close", 0)) if candles_1h else 0.0

    # ── Self-Awareness check ──────────────────────────────────────────────────
    awareness_state = None
    if awareness_engine:
        awareness_state = awareness_engine.evaluate()
        if not awareness_engine.is_safe_to_trade():
            log.warning("[SelfAwareness] Trading bloqué — niveau: %s", awareness_state.level.name)

    # ── Conviction Engine ─────────────────────────────────────────────────────
    conviction = None
    if conviction_engine:
        with watchdog.measure("conviction"):
            conviction = conviction_engine.evaluate(
                signal, features, candles_1h, regime, memory_sharpe,
                personality_name=personality.name if personality else "unknown",
            )
            if conviction.blocks_trade():
                log.info("[Conviction] Trade bloqué — conviction minimale (score=%.0f)", conviction.score)

    # ── No-Trade Intelligence check ───────────────────────────────────────────
    no_trade_verdict = None
    if no_trade_layer and signal.actionable:
        with watchdog.measure("no_trade"):
            no_trade_verdict = no_trade_layer.check(
                signal, candles_1h, features, regime,
                personality_name=personality.name if personality else "unknown",
            )

    # ── Mistake Memory — vérification avant trade ─────────────────────────────
    mm_check = None
    if mistake_memory and signal.actionable:
        with watchdog.measure("mistake_memory"):
            mm_check = mistake_memory.check_before_trade(
                symbol             = symbol,
                signal             = signal.signal,
                score              = signal.score,
                regime             = regime,
                features           = features,
                consecutive_losses = consecutive_losses,
                conviction_level   = conviction.level.value if conviction else "medium",
                signal_age_sec     = time.time() - signal.timestamp,
            )
            if mm_check.blocked:
                log.info("[MistakeMemory] Trade bloqué: %s", mm_check.reason)

    # ── Portfolio Brain — risque portefeuille global ──────────────────────────
    pb_verdict = None
    if portfolio_brain and signal.actionable:
        with watchdog.measure("portfolio_brain"):
            pb_verdict = portfolio_brain.check_new_trade(
                symbol          = symbol,
                action          = signal.signal,
                size_usd        = order_size_usd,
                regime          = regime,
                open_positions  = open_positions_list,
                leverage        = 1,
                conviction_score = conviction.score if conviction else 50.0,
            )
            if not pb_verdict.allowed:
                log.info("[PortfolioBrain] Bloqué: %s", pb_verdict.reason)
            elif pb_verdict.size_factor < 1.0:
                order_size_usd = order_size_usd * pb_verdict.size_factor
                log.debug("[PortfolioBrain] Taille réduite ×%.2f → $%.2f", pb_verdict.size_factor, order_size_usd)

    # ── Capital Allocation Engine — taille optimale Kelly/EV/vol ─────────────
    allocation = None
    if capital_engine and signal.actionable and (pb_verdict is None or pb_verdict.allowed):
        with watchdog.measure("capital_engine"):
            # Récupère les stats depuis le ranker si disponible
            cae_stats: JSONDict = {}
            if ranker:
                strategy_key = "btc_momentum" if "BTC" in symbol else (
                    "eth_volatility" if "ETH" in symbol else "sol_experimental"
                )
                cae_stats = capital_engine.stats_from_ranker(ranker, strategy_key, regime)
            volatility = float(features.get("atr_ratio", features.get("volatility", 0.015)))
            allocation = capital_engine.allocate(
                base_size_usd    = order_size_usd,
                win_rate         = cae_stats.get("win_rate",         0.50),
                avg_win_pct      = cae_stats.get("avg_win_pct",      0.03),
                avg_loss_pct     = cae_stats.get("avg_loss_pct",     0.02),
                volatility       = volatility,
                conviction_factor = conviction.size_factor if conviction else 1.0,
                regime           = regime,
                leverage         = 1,
                n_trades_history = cae_stats.get("n_trades_history", 0),
            )
            if allocation.size_usd > 0:
                order_size_usd = allocation.size_usd
                log.debug("[CAE] Taille allouée: $%.2f | kelly=%.4f ev=%.5f",
                          allocation.size_usd, allocation.kelly_fraction, allocation.ev_score)
            else:
                log.info("[CAE] Allocation refusée: %s", allocation.reason)

    # ── Executive Override — commandement suprême ─────────────────────────────
    eo_verdict = None
    if executive_override and signal.actionable:
        eo_verdict = executive_override.check_trade(
            size_usd         = order_size_usd,
            conviction_score = conviction.score if conviction else 50.0,
        )
        if not eo_verdict.allowed:
            log.warning("[ExecutiveOverride] VETO: %s", eo_verdict.reason)
        elif eo_verdict.size_factor < 1.0:
            order_size_usd = order_size_usd * eo_verdict.size_factor
            log.info("[ExecutiveOverride] %s — taille x%.0f%%",
                     eo_verdict.level.name, eo_verdict.size_factor * 100)

    # ── V2 : Decision Arbitrator — consensus pondéré multi-agents ────────────
    arbitration_result = None
    if v2_arbitrator and signal.actionable:
        try:
            from quant_hedge_ai.agents.intelligence.v2.decision_arbitrator import AgentVote
            arb_votes = [
                AgentVote("global_risk_gate",  1.0 if gate_result.allowed else -1.0, veto=not gate_result.allowed),
                AgentVote("conviction_engine", ((conviction.score / 100.0) * 2 - 1) if conviction else 0.0),
                AgentVote("no_trade_layer",    0.0 if no_trade_verdict is None else (1.0 if bool(no_trade_verdict) else -0.6)),
                AgentVote("portfolio_brain",   0.0 if pb_verdict is None else (1.0 if bool(pb_verdict) else -0.8)),
                AgentVote("meta_strategy",     0.8 if meta_allowed else -0.5),
                AgentVote("mistake_memory",    0.0 if mm_check is None else (0.5 if bool(mm_check) else -0.7)),
                AgentVote("executive_override", 0.0 if eo_verdict is None else (1.0 if bool(eo_verdict) else -1.0),
                          veto=(eo_verdict is not None and not bool(eo_verdict))),
                AgentVote("threat_radar",      0.0 if radar_report is None else (0.5 if radar_report.trade_allowed else -0.8)),
            ]
            # Enrichir avec signaux V2
            if micro_report:
                side_pressure = micro_report.directional_pressure if signal.signal == "long" else -micro_report.directional_pressure
                arb_votes.append(AgentVote("microstructure", side_pressure * 0.7))
            if regime_probs:
                if signal.signal == "long":
                    regime_vote = regime_probs.bull - regime_probs.bear
                else:
                    regime_vote = regime_probs.bear - regime_probs.bull
                arb_votes.append(AgentVote("hmm_regime", regime_vote))
            if transition_forecast and transition_forecast.crash_risk:
                arb_votes.append(AgentVote("hmm_regime", -0.9, veto=True))

            arbitration_result = v2_arbitrator.arbitrate(arb_votes)
            log.debug("[V2/Arbitrator] %s: %s", symbol, arbitration_result.reasoning)
        except Exception as _exc_v2:
            log.debug("[V2/Arbitrator] skip: %s", _exc_v2)

    # ── V2 : Timing Engine — attendre le bon moment d'exécution ──────────────
    timing_signal = None
    if v2_timing_engine and signal.actionable and (arbitration_result is None or arbitration_result.size_multiplier > 0):
        try:
            spread = micro_report.spread_bps if micro_report else 5.0
            imbalance = micro_report.imbalance if micro_report else 0.0
            atr = float(features.get("atr_pct", 0.01))
            urgency = float(signal.score) / 100.0 if hasattr(signal, "score") else 0.5
            timing_signal = v2_timing_engine.evaluate(symbol, signal.signal, spread, imbalance, atr, urgency)
            if not timing_signal.execute_now:
                log.debug("[V2/Timing] %s — attendre: %s", symbol, timing_signal.reason)
        except Exception as _exc_v2:
            log.debug("[V2/Timing] skip: %s", _exc_v2)

    # Décision finale d'autorisation
    _awareness_ok  = awareness_engine is None or awareness_engine.is_safe_to_trade()
    _conviction_ok = conviction is None or not conviction.blocks_trade()
    _notrade_ok    = no_trade_verdict is None or bool(no_trade_verdict)
    _pb_ok         = pb_verdict is None or bool(pb_verdict)
    _cae_ok        = allocation is None or bool(allocation)
    _mm_ok         = mm_check is None or bool(mm_check)
    _eo_ok         = eo_verdict is None or bool(eo_verdict)
    _radar_ok      = radar_report is None or radar_report.trade_allowed
    # V2 arbitration : si disponible, son verdict remplace la logique dispersée
    if arbitration_result is not None:
        from quant_hedge_ai.agents.intelligence.v2.decision_arbitrator import ArbitrationDecision
        _arb_ok = arbitration_result.decision not in (ArbitrationDecision.REJECT, ArbitrationDecision.EMERGENCY_EXIT)
        if arbitration_result.size_multiplier > 0 and _arb_ok:
            order_size_usd = order_size_usd * arbitration_result.size_multiplier
    else:
        _arb_ok = True
    trade_allowed = (meta_allowed and gate_result.allowed and _awareness_ok and _conviction_ok
                     and _notrade_ok and _pb_ok and _cae_ok and _mm_ok and _eo_ok and _radar_ok and _arb_ok)
    if signal.actionable:
        _flow_blockers = ", ".join(filter(None, [
            "meta" if not meta_allowed else "",
            "gate" if not gate_result.allowed else "",
            "awareness" if not _awareness_ok else "",
            "conviction" if not _conviction_ok else "",
            "no_trade" if not _notrade_ok else "",
            "portfolio" if not _pb_ok else "",
            "cae" if not _cae_ok else "",
            "mistake_mem" if not _mm_ok else "",
            "exec_override" if not _eo_ok else "",
            "radar" if not _radar_ok else "",
            "arbitrator" if not _arb_ok else "",
        ]))
        _alloc_str = f" alloc=${allocation.size_usd:.0f}" if allocation and allocation.size_usd > 0 else ""
        log.info("[FLOW] %s VERDICT → %s%s%s",
                 symbol,
                 "TRADE_OK" if trade_allowed else "BLOQUÉ",
                 _alloc_str,
                 f" [{_flow_blockers}]" if _flow_blockers else "")

    # ── Regret Engine — enregistre les refus potentiellement rentables ─────────
    if regret_engine and signal.actionable and not trade_allowed:
        refused_by_list: list[str] = []
        if not _eo_ok:          refused_by_list.append("executive_override")
        if not _mm_ok:          refused_by_list.append("mistake_memory")
        if not _pb_ok:          refused_by_list.append("portfolio_brain")
        if not _conviction_ok:  refused_by_list.append("conviction")
        if not _notrade_ok:     refused_by_list.append("no_trade")
        if not _awareness_ok:   refused_by_list.append("awareness")
        if not meta_allowed:    refused_by_list.append("meta_strategy")
        if not gate_result.allowed: refused_by_list.append("gate")
        if not _radar_ok:           refused_by_list.append("threat_radar")
        regret_engine.register_candidate(
            symbol           = symbol,
            signal           = signal.signal,
            score            = signal.score,
            regime           = regime,
            price            = prix,
            refused_by       = refused_by_list,
            cycle            = cycle,
            conviction_level = conviction.level.value if conviction else "medium",
        )

    # ── Decision Quality — évaluation avant exécution ─────────────────────────
    dq_record = None
    if dqe and signal.actionable:
        dq_record = dqe.evaluate_decision(
            signal,
            conviction_score  = conviction.score if conviction else 50.0,
            conviction_level  = conviction.level.value if conviction else "medium",
            regime            = regime,
            personality_name  = personality.name if personality else "unknown",
            no_trade_score    = no_trade_verdict.rejection_score if no_trade_verdict else 0.0,
            meta_allowed      = meta_allowed,
            gate_allowed      = gate_result.allowed,
        )

    # Shadow execution — simule l'ordre sans l'envoyer
    shadow_trade = None
    if signal.actionable and trade_allowed:
        with watchdog.measure("shadow"):
            eff_size = order_size_usd
            if conviction:
                eff_size = order_size_usd * conviction.size_factor
            if awareness_engine:
                eff_size *= awareness_engine.effective_size_factor()
            shadow_trade = shadow.shadow_execute(
                signal,
                live_price=prix,
                capital=max(1.0, eff_size),
            )
            if shadow_trade:
                log.info("[SHADOW] %s", shadow_trade.summary())

    persona_name = personality.name if personality else "N/A"
    conv_str     = f" | conv: {conviction.level.value}({conviction.score:.0f})" if conviction else ""
    aw_str       = f" | aware: {awareness_state.level.name}" if awareness_state else ""
    pb_str       = f" | pb: {pb_verdict.size_factor:.2f}" if pb_verdict else ""
    cae_str      = f" | cae: ${allocation.size_usd:.0f}" if allocation and allocation.size_usd > 0 else ""
    mm_str       = f" | mm: BLOQUE" if mm_check and mm_check.blocked else ""
    eo_str       = f" | eo: {eo_verdict.level.name}" if eo_verdict and eo_verdict.level.value > 0 else ""
    log.info(
        "  %s | $%.2f | score: %d/100 | %s | regime: %s | perso: %s | gate: %s%s%s%s%s%s%s",
        symbol, prix, signal.score, signal.signal,
        regime, persona_name,
        "OK" if trade_allowed else "BLOQUE",
        conv_str, aw_str, pb_str, cae_str, mm_str, eo_str,
    )

    return {
        "symbol":           symbol,
        "prix":             prix,
        "signal":           signal,
        "gate":             gate_result,
        "advice":           advice,
        "explanation":      explanation,
        "shadow":           shadow_trade,
        "personality":      personality,
        "meta_allowed":     meta_allowed,
        "meta_reason":      meta_reason,
        "conviction":       conviction,
        "no_trade_verdict": no_trade_verdict,
        "awareness_state":  awareness_state,
        "pb_verdict":       pb_verdict,
        "allocation":       allocation,
        "mm_check":         mm_check,
        "eo_verdict":       eo_verdict,
        "dq_record":        dq_record,
        "trade_allowed":    trade_allowed,
        "order_size":       order_size_usd,
        "regime":           regime,
        "features":         features,
        "radar_report":     radar_report,
        "ml_decision":      ml_decision,
        "n_1h":             len(candles_1h),
        "n_4h":             len(mtf_candles.get("4h", [])),
        "n_1d":             len(mtf_candles.get("1d", [])),
    }


# ── Construction messages Telegram ───────────────────────────────────────────

_SIGNAL_ICON = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}
_REGIME_FR = {
    "bull_trend":             "Tendance haussiere",
    "bear_trend":             "Tendance baissiere",
    "sideways":               "Range lateral",
    "high_volatility_regime": "Haute volatilite",
    "flash_crash":            "KRACH ECLAIR",
    "unknown":                "Indetermine",
}
_SCORE_BAR = [
    (85, "FORT"),
    (70, "BON"),
    (50, "MOYEN"),
    (30, "FAIBLE"),
    (0,  "TRES FAIBLE"),
]

def _score_label(score: int) -> str:
    for threshold, label in _SCORE_BAR:
        if score >= threshold:
            return label
    return "TRES FAIBLE"


def _build_summary(results: list[AnalysisResult], cycle: int) -> str:
    """Message de rapport périodique — toutes les N cycles."""
    lines = [f"Crypto AI Terminal — Rapport cycle {cycle}", ""]

    for r in results:
        s      = r["signal"]
        g      = r["gate"]
        a      = r["advice"]
        icon   = _SIGNAL_ICON.get(s.signal, "?")
        regime = _REGIME_FR.get(s.regime, s.regime)
        label  = _score_label(s.score)
        gate_s = "PRET" if g.allowed else "BLOQUE"
        comps  = s.components

        persona  = r.get("personality")
        p_name   = persona.name if persona else "N/A"
        p_factor = f"x{persona.order_size_factor:.1f}" if persona else ""
        lines += [
            f"{icon} {r['symbol']} | ${r['prix']}",
            f"   Score: {s.score}/100 ({label}) | {s.signal}",
            f"   Regime: {regime} | Perso: {p_name} {p_factor}",
            f"   MTF: {comps.get('mtf',0):.0f}/40 | "
            f"Regime: {comps.get('regime',0):.0f}/25 | "
            f"Data: {comps.get('data_quality',0):.0f}/15 | "
            f"Mem: {comps.get('memory',0):.0f}/20",
            f"   Gate: {gate_s} | Risque: {a.risk_level} | Confiance: {a.confidence}",
            "",
        ]

    if os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true":
        lines.append("Mode observation — aucun ordre place")
    else:
        lines.append("TRADING ACTIF — ordres Futures Demo executes sur signaux >= 70")
    return "\n".join(lines)


def _build_alert(r: AnalysisResult, cycle: int) -> str:
    """Message d'alerte immédiate — signal actionable détecté."""
    s      = r["signal"]
    g      = r["gate"]
    a      = r["advice"]
    sh     = r.get("shadow")
    ex     = r.get("explanation")
    icon   = _SIGNAL_ICON.get(s.signal, "?")
    regime = _REGIME_FR.get(s.regime, s.regime)
    comps  = s.components

    lines = [
        f"SIGNAL ACTIONABLE — Cycle {cycle}",
        "",
        f"{icon} {r['symbol']} | ${r['prix']:.2f}",
        f"Score: {s.score}/100 | {s.signal}",
        f"Regime: {regime} | Confirme: {s.confirmed}",
        f"Force: {s.strength:.0%}",
        "",
        f"Scores detail:",
        f"  MTF:     {comps.get('mtf',0):.1f}/40",
        f"  Regime:  {comps.get('regime',0):.1f}/25",
        f"  Donnees: {comps.get('data_quality',0):.1f}/15",
        f"  Memoire: {comps.get('memory',0):.1f}/20",
        "",
        f"Gate: {'PRET A TRADER' if g.allowed else 'BLOQUE — ' + ' | '.join(g.failed)}",
        f"Risque: {a.risk_level} | Confiance: {a.confidence}",
    ]

    # Explication du score si disponible
    if ex:
        verdict_clean = ex.verdict.encode("ascii", errors="replace").decode("ascii")
        lines += [
            "",
            f"Verdict: {verdict_clean}",
            f"Niveau confiance: {ex.confidence_level}",
        ]
        if ex.penalties:
            pen_str = " | ".join(
                p[0].encode("ascii", errors="replace").decode("ascii")
                for p in ex.penalties[:2]
            )
            lines.append(f"Alertes: {pen_str}")
        if ex.bonuses:
            bon_str = " | ".join(
                b[0].encode("ascii", errors="replace").decode("ascii")
                for b in ex.bonuses[:2]
            )
            lines.append(f"Points forts: {bon_str}")

    # Données shadow si disponibles
    if sh:
        lines += [
            "",
            f"SHADOW EXECUTION (simule, pas envoye):",
            f"  Prix signal:   ${sh.signal_price:.2f}",
            f"  Prix fill sim: ${sh.simulated_fill_price:.2f}",
            f"  Slippage:      {sh.slippage_pct:.3f}%",
            f"  Taille:        {sh.size:.6f} ({r['symbol'].split('/')[0]})",
            f"  Notionnel:     ${sh.notional:.2f}",
            f"  Latence:       {sh.signal_to_order_ms:.1f}ms",
            f"  ID:            {sh.id}",
        ]

    # Futures result si un ordre a été exécuté
    fut = r.get("futures_result")
    if fut:
        mode = fut.get("mode", "?")
        if mode == "futures_demo":
            lines += [
                "",
                f"ORDRE FUTURES DEMO PLACE:",
                f"  ID:         {fut.get('id', '?')}",
                f"  Notionnel:  ${fut.get('usd_size', 0):.2f}",
                f"  Statut:     {fut.get('status', '?')}",
            ]
        elif mode == "futures_failed":
            lines += [
                "",
                f"ORDRE FUTURES ECHOUE: {fut.get('error', '?')}",
            ]
    else:
        advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
        lines += [
            "",
            "Mode observation — aucun ordre place" if advisor_only
            else "Gate bloquee ou safe mode — aucun ordre place",
        ]

    lines += [
        "",
        f"Analyse: {str(a.text)[:250]}",
    ]
    return "\n".join(lines)


def _build_guide() -> str:
    """Guide d'interprétation envoyé au démarrage."""
    return (
        "Crypto AI Terminal — Guide de lecture\n"
        "\n"
        "SCORE (0-100):\n"
        "  85-100 : FORT    — signal tres fiable\n"
        "  70-84  : BON     — signal actionable\n"
        "  50-69  : MOYEN   — signal a surveiller\n"
        "  0-49   : FAIBLE  — pas d'action\n"
        "\n"
        "SIGNAL:\n"
        "  BUY  : le bot recommanderait un achat\n"
        "  SELL : le bot recommanderait une vente\n"
        "  HOLD : attendre, pas de signal clair\n"
        "\n"
        "GATE:\n"
        "  PRET     : toutes les conditions passent\n"
        "  BLOQUE   : une condition echoue (score, confirmation, regime)\n"
        "\n"
        "REGIME:\n"
        "  Tendance haussiere : BTC monte clairement\n"
        "  Range lateral      : BTC consolide (normal)\n"
        "  Haute volatilite   : mouvements brusques\n"
        "  KRACH ECLAIR       : danger — pas de trade\n"
        "\n"
        "SCORES DETAIL:\n"
        "  MTF (40pts)    : alignement 1h+4h+1d\n"
        "  Regime (25pts) : contexte de marche\n"
        "  Donnees (15pts): qualite des bougies\n"
        "  Memoire (20pts): historique strategies\n"
        "\n"
        "Rapport toutes les 15 min.\n"
        "Alerte immediate si score >= 70."
    )


# ── Boucle principale ─────────────────────────────────────────────────────────

def main(
    symbols: list[str],
    interval: int = 300,
    max_cycles: int | None = None,
    runtime: AdvisorRuntime | None = None,
) -> None:
    runtime = runtime or load_advisor_runtime()

    os.makedirs("logs", exist_ok=True)
    os.makedirs("databases/shadow_execution", exist_ok=True)

    _t_main_start = time.perf_counter()   # référence pour comparaison bootstrap / cycle 1
    bootstrap_profile: list[tuple[str, float]] = []

    def _profile_bootstrap_step(label: str, fn: Any) -> Any:
        started = time.perf_counter()
        try:
            return fn()
        finally:
            bootstrap_profile.append((label, time.perf_counter() - started))

    log.info("=== ADVISOR LOOP DEMARRE ===")
    log.info("Symboles: %s | Intervalle: %ds | Notify every: %d cycles",
             symbols, interval, NOTIFY_EVERY)

    # ── Session primer — lancé AVANT la création des scanners ─────────────────
    # Crée l'exchange CCXT et appelle load_markets() dans un thread daemon.
    # Démarré en tout premier pour maximiser le chevauchement avec le reste
    # du bootstrap (services, exec_engine, modules intel).
    # Quand les threads prewarm démarrent, ils trouvent l'exchange et les markets
    # déjà prêts → ils sautent directement à fetch_ohlcv() (~650ms gagnés).
    _t_primer_start: float | None = None
    _primer_future: Any = None
    _primer_executor: ThreadPoolExecutor | None = None
    if ADVISOR_SESSION_PRIMER:
        _exchange_id  = os.getenv("MARKET_SCANNER_EXCHANGE", "binance")
        _testnet      = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
        _trace_primer = os.getenv("MARKET_SCANNER_TRACE_TIMINGS", "false").lower() == "true"
        try:
            _scanner_cls = runtime.MarketScanner  # class reference, not instance
            _primer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SessionPrimer")
            _t_primer_start  = time.perf_counter()
            _primer_future   = _primer_executor.submit(
                _prime_exchange_session,
                _exchange_id, _testnet, _scanner_cls,
                trace=_trace_primer,
            )
            log.info(
                "[SessionPrimer] Lancé en avance (exchange=%s testnet=%s) "
                "— exchange_init + load_markets en parallèle du bootstrap",
                _exchange_id, _testnet,
            )
        except Exception as _pe:
            log.warning("[SessionPrimer] Impossible de lancer: %s", _pe)
            _primer_future = None

    # ── Warmup anticipé — AVANT tous les services non-critiques ───────────────
    # Les scanners ne dépendent que de runtime.MarketScanner (pur Python).
    # On les crée ici et on lance immédiatement les futures 1h en background
    # pour que le fetch HTTP Binance tourne EN PARALLELE du reste du boot
    # (kill_switch, exchange_monitor, healer, exec_engine, modules intel).
    # Gain mesuré : overlap max avec les 3-4s de boot non-réseau.
    scanners: dict[str, dict[str, Any]] = _profile_bootstrap_step(
        "scanners",
        lambda: {
            "1h":  {sym: runtime.MarketScanner(symbols=[sym], timeframe="1h", limit=ADVISOR_1H_LIMIT) for sym in symbols},
            "mtf": {sym: runtime.MultiTimeframeScanner(symbols=[sym], refresh_every=MTF_REFRESH_EVERY) for sym in symbols},
        },
    )
    prewarm_executor: ThreadPoolExecutor | None = None
    prewarm_futures: dict[str, Any] = {}
    prewarm_mtf_futures: dict[str, Any] = {}
    _t_warmup_start: float | None = None
    _t_warmup_end: float | None = None
    advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
    startup_light = advisor_only and ADVISOR_STARTUP_LIGHT
    prewarm_1h_enabled = ADVISOR_PREWARM_1H
    prewarm_mtf_enabled = ADVISOR_PREWARM_MTF and not startup_light
    live_execution_bootstrap = ADVISOR_LIVE_EXECUTION_BOOTSTRAP and not startup_light
    background_position_watch = ADVISOR_BACKGROUND_POSITION_WATCH and not startup_light
    defer_optional_intel = ADVISOR_DEFER_OPTIONAL_INTEL or startup_light
    defer_post_cycle_services = advisor_only and (ADVISOR_DEFER_POST_CYCLE_SERVICES or startup_light)
    persistent_warmup_enabled = ADVISOR_PERSISTENT_WARMUP and not startup_light
    threat_radar_every = max(ADVISOR_THREAT_RADAR_EVERY, 3 if startup_light else 1)
    cycle_budget_seconds = ADVISOR_CYCLE_BUDGET_SECONDS
    load_shed_cycles = ADVISOR_LOAD_SHED_CYCLES

    if startup_light:
        log.info(
            "[StartupLight] Actif — prewarm_mtf=%s persistent_warmup=%s threat_radar_every=%d",
            "off",
            "off",
            threat_radar_every,
        )

    if prewarm_1h_enabled:
        n_mtf_slots = len(symbols) if prewarm_mtf_enabled else 0
        max_workers = max(1, min(
            len(symbols) + n_mtf_slots,
            int(os.getenv("ADVISOR_PREWARM_MAX_WORKERS", str(len(symbols) + n_mtf_slots or 1)))
        ))
        prewarm_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AdvisorWarm")
        _t_warmup_start = time.perf_counter()
        prewarm_futures = {
            sym: prewarm_executor.submit(scanners["1h"][sym].scan)
            for sym in symbols
            if hasattr(scanners["1h"][sym], "scan")
        }
        if prewarm_futures:
            log.info("[Warmup] Prechauffage 1h lance EN AVANCE pour %d symbole(s) (avant services boot)",
                     len(prewarm_futures))
        if prewarm_mtf_enabled:
            prewarm_mtf_futures = {
                sym: prewarm_executor.submit(scanners["mtf"][sym].scan)
                for sym in symbols
                if hasattr(scanners["mtf"][sym], "scan")
            }
            if prewarm_mtf_futures:
                log.info("[Warmup] Prechauffage MTF (4h+1d) lance en background",
                         )
        if not prewarm_futures and not prewarm_mtf_futures:
            prewarm_executor.shutdown(wait=False, cancel_futures=True)
            prewarm_executor = None

    # Kill switch — état partagé entre thread Telegram et boucle principale
    _halt_requested = {"value": False}

    def _on_stop_all():
        _halt_requested["value"] = True
        log.critical("[main] STOP_ALL recu — la boucle va s'arreter au prochain cycle")

    def _on_close_all():
        _halt_requested["value"] = True
        log.critical("[main] CLOSE_ALL recu — la boucle va s'arreter au prochain cycle")

    kill_switch = _profile_bootstrap_step(
        "kill_switch",
        lambda: runtime.TelegramKillSwitch(
            on_stop_all=_on_stop_all,
            on_close_all=_on_close_all,
        ),
    )
    kill_switch_started = False

    def _start_kill_switch() -> None:
        nonlocal kill_switch_started
        if not kill_switch_started:
            _profile_bootstrap_step("kill_switch.start", kill_switch.start)
            kill_switch_started = True

    if defer_post_cycle_services:
        log.info("[Startup] KillSwitch differe apres le cycle 1 (observation seule)")
    else:
        _start_kill_switch()

    # Exchange monitor — surveillance connexion Binance en background
    exchange_monitor = _profile_bootstrap_step(
        "exchange_monitor",
        lambda: runtime.ExchangeMonitor(
            on_offline=lambda: log.warning("[main] Exchange hors ligne signalé"),
            on_recovered=lambda: log.info("[main] Exchange rétabli"),
        ),
    )
    exchange_monitor_started = False

    def _start_exchange_monitor() -> None:
        nonlocal exchange_monitor_started
        if not exchange_monitor_started:
            _profile_bootstrap_step("exchange_monitor.start", exchange_monitor.start)
            exchange_monitor_started = True

    if defer_post_cycle_services:
        log.info("[Startup] ExchangeMonitor differe apres le cycle 1 (observation seule)")
    else:
        _start_exchange_monitor()

    # Self-healing bot — surveille les composants critiques
    healer = _profile_bootstrap_step(
        "self_healing",
        lambda: runtime.SelfHealingBot(global_check_interval_s=10.0),
    )

    # Composant 1 : exchange
    _profile_bootstrap_step(
        "self_healing.register_exchange",
        lambda: healer.register_simple(
            "exchange",
            health_fn=exchange_monitor.is_healthy,
            restart_fn=lambda: log.warning("[SelfHeal] Exchange unhealthy — aucun restart auto possible"),
        ),
    )
    # Composant 2 : LM Studio (non bloquant — le bot fonctionne sans)
    def _lm_health() -> bool:
        try:
            import requests as _r
            r = _r.get("http://localhost:1234/v1/models", timeout=3)
            return r.status_code == 200
        except Exception:
            return True  # LM Studio optionnel — pas de restart si absent
    def _lm_restart() -> None:
        log.warning("[SelfHeal] LM Studio inaccessible — bascule déterministe")
        os.environ["LM_STUDIO_AVAILABLE"] = "false"
    _profile_bootstrap_step(
        "self_healing.register_lm_studio",
        lambda: healer.register_simple("lm_studio", health_fn=_lm_health, restart_fn=_lm_restart),
    )
    healer_started = False

    def _start_healer() -> None:
        nonlocal healer_started
        if not healer_started:
            _profile_bootstrap_step("self_healing.start", healer.start)
            healer_started = True

    if defer_post_cycle_services:
        log.info("[Startup] SelfHealing differe apres le cycle 1 (observation seule)")
    else:
        _start_healer()

    # Warmup persistant — maintient le cache OHLCV chaud entre les cycles
    _persistent_warmer: Any = None
    if persistent_warmup_enabled:
        try:
            from quant_hedge_ai.persistent_warmup import CacheWarmer
            _persistent_warmer = _profile_bootstrap_step(
                "persistent_warmup",
                lambda: CacheWarmer(scanner=None, symbols=symbols, timeframes=["1h", "4h", "1d"]),
            )
            _profile_bootstrap_step("persistent_warmup.start", _persistent_warmer.start)
            log.info("[PersistentWarmup] daemon demarre pour %d symboles", len(symbols))
        except Exception as _pw_exc:
            log.warning("[PersistentWarmup] echec demarrage: %s", _pw_exc)

    # Init modules
    Position = runtime.Position
    tracker_finalize_position = runtime.tracker_finalize_position
    tracker_open_position = runtime.tracker_open_position
    tracker_run_cycle = runtime.tracker_run_cycle

    if advisor_only and not live_execution_bootstrap:
        exec_engine = _profile_bootstrap_step("execution_engine", runtime.ExecutionEngine)
        has_futures = False
        futures_bal = 0.0
    else:
        exec_engine = _profile_bootstrap_step("execution_engine.from_env", runtime.ExecutionEngine.from_env)
        has_futures = exec_engine.has_futures_demo()
        futures_bal = exec_engine.fetch_futures_balance() if has_futures else 0.0

    # Lire le capital réel disponible (balance USDT testnet ou .env fallback)
    real_capital = exec_engine.fetch_available_capital()
    max_order    = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
    order_size   = min(max_order, real_capital * float(os.getenv("V9_MAX_POSITION_WEIGHT", "0.05")))
    log.info("Capital disponible: $%.2f | Taille ordre: $%.2f (max $%.2f)",
             real_capital, order_size, max_order)

    trading_mode = (
        "OBSERVATION ONLY (V9_ADVISOR_ONLY=true)"
        if advisor_only
        else f"TRADING ACTIF - Futures Demo ({'CONNECTE $%.0f USDT' % futures_bal if has_futures else 'NON DISPONIBLE'})"
    )

    log.info("Mode: %s", trading_mode)

    _telegram(
        f"Crypto AI Terminal demarre\n"
        f"Symboles: {', '.join(symbols)}\n"
        f"Intervalle: {interval}s | Rapport: toutes les {interval * NOTIFY_EVERY // 60} min\n"
        f"Capital: ${real_capital:.0f} | Ordre max: ${order_size:.0f}\n"
        f"Mode: {trading_mode}\n"
        f"Kill Switch: actif | Exchange Monitor: actif\n"
        f"Self-Healing: actif | Watchdog: actif\n"
        f"Portfolio Brain: actif | Capital Engine: actif (Kelly+EV+Vol)"
    )

    _telegram(_build_guide())

    # SubaccountManager — sync positions vers dashboard
    sub_manager = None
    try:
        from quant_hedge_ai.agents.execution.subaccount_manager import SubaccountManager
        sub_manager = SubaccountManager.from_env()
        log.info("[SubaccountManager] Initialisé — positions seront synchronisées vers dashboard")
    except Exception as _sm_exc:
        log.warning("[SubaccountManager] Non disponible: %s", _sm_exc)

    # Position Manager — surveille les positions ouvertes (TP/SL/trailing)
    pos_manager = _profile_bootstrap_step(
        "position_manager",
        lambda: runtime.PositionManager(
            exchange=_get_exchange_futures(exec_engine),
            paper_mode=advisor_only or not has_futures,
        ),
    )
    if not advisor_only or background_position_watch:
        _profile_bootstrap_step("position_manager.start", pos_manager.start)
    else:
        log.info("[PositionManager] Désactivé en observation seule")

    def _tracker_payload_from_position(pos: Any) -> dict[str, Any]:
        side = "BUY" if getattr(pos, "side", None) and pos.side.value == "long" else "SELL"
        return {
            "id": str(getattr(pos, "order_id", "") or f"{pos.symbol}_{int(getattr(pos, 'opened_at', time.time()) * 1000)}"),
            "symbol": pos.symbol,
            "side": side,
            "entry_price": float(pos.entry_price),
            "size": float(pos.size_usd),
            "timestamp": float(getattr(pos, "opened_at", time.time())),
            "regime": getattr(pos, "regime", "unknown"),
            "confidence": float(getattr(pos, "signal_score", 0.0)),
            "max_price": float(getattr(pos, "highest_price", pos.entry_price)),
            "min_price": float(getattr(pos, "lowest_price", pos.entry_price)),
            "price_path": [float(pos.entry_price), float(getattr(pos, "current_price", pos.entry_price) or pos.entry_price)],
            "subaccount": getattr(pos, "subaccount", "default"),
            "leverage": int(getattr(pos, "leverage", 1)),
            "qty": float(getattr(pos, "qty", 0.0)),
            "tp_pct": float(getattr(pos, "tp_pct", 0.0)),
            "sl_pct": float(getattr(pos, "sl_pct", 0.0)),
            "trailing_pct": float(getattr(pos, "trailing_pct", 0.0)),
            "atr": float(getattr(pos, "atr", 0.0)),
            "volatility": float(getattr(pos, "volatility", 0.0)),
        }

    def _refresh_tracker_artifacts(event_name: str) -> None:
        try:
            tracker_run_cycle(run_optimizer=False)
        except Exception as tracker_exc:
            log.warning("[TrackerSystem] refresh échoué après %s: %s", event_name, tracker_exc)

    def _build_position_from_execution(
        order_result: JSONDict,
        result_row: AnalysisResult,
        symbol: str,
        action: str,
        effective_size: float,
    ) -> Any:
        personality = result_row.get("personality")
        feat        = result_row.get("features", {})
        atr_val     = float(feat.get("atr", 0.0))
        vol_val     = float(feat.get("atr_ratio", feat.get("volatility", 0.0)))
        entry_price = _to_float(
            order_result.get("price")
            or order_result.get("average")
            or _stats_dict(order_result.get("info")).get("avgPrice"),
            _to_float(result_row.get("prix", 0.0)),
        )
        qty = _to_float(
            order_result.get("amount")
            or order_result.get("filled")
            or order_result.get("qty"),
            0.0,
        )
        if qty <= 0 and entry_price > 0:
            qty = effective_size / entry_price

        normalized_result = dict(order_result)
        if entry_price > 0 and not normalized_result.get("price"):
            normalized_result["price"] = entry_price
        if qty > 0 and not normalized_result.get("amount"):
            normalized_result["amount"] = qty

        if hasattr(Position, "from_futures_order"):
            pos = Position.from_futures_order(
                normalized_result,
                symbol,
                action,
                effective_size,
                tp_pct=(result_row["ml_decision"].get("tp") or (personality.tp_pct if personality else 0.04)),
                sl_pct=(result_row["ml_decision"].get("sl") or (personality.sl_pct if personality else 0.02)),
                trailing=(result_row["ml_decision"].get("trail_pct") or (personality.trailing_pct if personality else 0.0)),
                atr=atr_val,
                volatility=vol_val,
                regime=result_row.get("regime", "unknown"),
            )
        else:
            from quant_hedge_ai.agents.execution.position_manager import PositionSide as _PS
            pos = Position(
                symbol=symbol,
                side=_PS.LONG if action.upper() == "BUY" else _PS.SHORT,
                entry_price=entry_price,
                size_usd=effective_size,
                qty=qty,
                subaccount="main",
            )

        pos.signal_score     = result_row["signal"].score
        pos.conviction_level = result_row["conviction"].level.value if result_row.get("conviction") else "medium"
        pos.signal_age_sec   = time.time() - result_row["signal"].timestamp
        pos.subaccount = "btc_momentum" if "BTC" in symbol else (
            "eth_volatility" if "ETH" in symbol else "sol_experimental"
        )
        return pos

    def _register_position_from_execution(
        order_result: JSONDict,
        result_row: AnalysisResult,
        symbol: str,
        action: str,
        effective_size: float,
    ) -> bool:
        result_mode = str(order_result.get("mode", ""))
        if result_mode not in {"futures_demo", "paper", "live"}:
            return False

        try:
            executive_override.record_trade()
        except Exception:
            pass

        try:
            pos = _build_position_from_execution(
                order_result,
                result_row,
                symbol,
                action,
                effective_size,
            )
            pos_manager.add_position(pos)
            # ── Sync vers SubaccountManager pour dashboard ──────────────────
            if sub_manager:
                try:
                    subaccount_name = getattr(pos, "subaccount", "default")
                    unit = sub_manager.get(subaccount_name)
                    if unit and unit.position_manager:
                        unit.position_manager.add_position(pos)
                        log.debug("[SubaccountManager SYNC] Position enregistrée dans %s", subaccount_name)
                except Exception as _sync_exc:
                    log.debug("[SubaccountManager SYNC] Failed: %s", _sync_exc)
            try:
                import json as _json
                import os as _os
                _snap_path: str = _os.path.join("databases", "positions_snapshot.json")
                _snap_tmp: str  = _snap_path + ".tmp"
                _snap_positions: list[dict[str, Any]] = _snapshot_list(pos_manager.snapshot())
                _snap_data: dict[str, Any] = {"ts": time.time(), "positions": _snap_positions}
                with open(_snap_tmp, "w", encoding="utf-8") as _sf:
                    _json.dump(_snap_data, _sf)
                _os.replace(_snap_tmp, _snap_path)
            except Exception as _snap_exc:
                log.debug("[SNAPSHOT] write échoué: %s", _snap_exc)
            try:
                tracker_open_position(
                    symbol=symbol,
                    side=action,
                    price=float(getattr(pos, "entry_price", _to_float(result_row.get("prix", 0.0)))),
                    size=float(effective_size),
                    regime=result_row.get("regime", "unknown"),
                    confidence=float(result_row["signal"].score),
                    id=str(getattr(pos, "order_id", "")),
                    timestamp=float(getattr(pos, "opened_at", time.time())),
                    subaccount=getattr(pos, "subaccount", "default"),
                    leverage=int(getattr(pos, "leverage", 1)),
                    qty=float(getattr(pos, "qty", 0.0)),
                    tp_pct=float(getattr(pos, "tp_pct", 0.0)),
                    sl_pct=float(getattr(pos, "sl_pct", 0.0)),
                    trailing_pct=float(getattr(pos, "trailing_pct", 0.0)),
                    atr=float(getattr(pos, "atr", 0.0)),
                    volatility=float(getattr(pos, "volatility", 0.0)),
                    source="advisor_loop",
                )
                _refresh_tracker_artifacts("open")
            except Exception as tracker_exc:
                log.warning("[TrackerSystem] open échoué pour %s: %s", symbol, tracker_exc)
            _consecutive_losses["value"] = 0
            return True
        except Exception as pos_exc:
            log.warning("[POSITION] add échoué: %s", pos_exc)
            return False

    def _on_position_close(pos: Any, reason: Any) -> None:
        # ── Sync fermeture vers SubaccountManager ──────────────────────────
        if sub_manager:
            try:
                subaccount_name = getattr(pos, "subaccount", "default")
                unit = sub_manager.get(subaccount_name)
                if unit and unit.position_manager:
                    unit.position_manager.close_position(pos.symbol, reason)
                    log.debug("[SubaccountManager SYNC] Position fermée dans %s", subaccount_name)
            except Exception as _sync_exc:
                log.debug("[SubaccountManager SYNC close] Failed: %s", _sync_exc)
        try:
            tracker_finalize_position(
                str(getattr(pos, "order_id", "")),
                float(getattr(pos, "current_price", 0.0) or pos.entry_price),
                getattr(reason, "value", str(reason)),
                fallback_position=_tracker_payload_from_position(pos),
            )
            _refresh_tracker_artifacts("close")
        except Exception as tracker_exc:
            log.warning("[TrackerSystem] finalize échoué pour %s: %s", pos.symbol, tracker_exc)

        sign = "+" if pos.pnl_usd >= 0 else ""
        _telegram(
            f"POSITION FERMEE — {reason.value.upper()}\n"
            f"{pos.side.value.upper()} {pos.symbol}\n"
            f"Entry: ${pos.entry_price:.2f} | Exit: ${pos.current_price:.2f}\n"
            f"PnL: {sign}${pos.pnl_usd:.2f} ({sign}{pos.pnl_pct:.2%})\n"
            f"Subcompte: {pos.subaccount}"
        )

    pos_manager.on_close(_on_position_close)

    gate     = _profile_bootstrap_step("global_risk_gate", runtime.GlobalRiskGate)
    engine   = _profile_bootstrap_step("live_signal_engine", runtime.LiveSignalEngine)
    advisor  = _profile_bootstrap_step("ai_advisor", runtime.AIAdvisor)
    shadow   = _profile_bootstrap_step("shadow_execution", lambda: runtime.ShadowExecutionEngine(risk_gate=gate))
    watchdog = _profile_bootstrap_step("performance_watchdog", runtime.PerformanceWatchdog)
    memory   = _profile_bootstrap_step("strategy_memory_store", runtime.StrategyMemoryStore)

    # Meta-Strategy Engine — personnalité adaptée au régime
    meta_engine = _profile_bootstrap_step("meta_strategy", runtime.MetaStrategyEngine)

    # Strategy Ranker — notation et auto-promotion/rétrogradation
    ranker = _profile_bootstrap_step("strategy_ranker", runtime.StrategyRanker)

    # Self-Awareness Engine — détection dérive comportementale/perf/infra
    def _on_awareness_change(state: Any) -> None:
        if state.level >= runtime.DangerLevel.WARNING:
            drifts_msg = " | ".join(d.message for d in state.active_drifts[:3])
            _telegram(
                f"SELF-AWARENESS — {state.level.name}\n"
                f"Taille: x{state.size_factor:.1f} | Safe mode: {state.safe_mode}\n"
                f"Dérives: {drifts_msg}"
            )

    awareness_engine = _profile_bootstrap_step(
        "self_awareness",
        lambda: runtime.SelfAwarenessEngine(on_level_change=_on_awareness_change),
    )

    # No-Trade Intelligence — refus intelligents
    no_trade_layer = _profile_bootstrap_step("no_trade_intelligence", runtime.NoTradeIntelligence)

    # Conviction Engine — 4 niveaux de conviction
    conviction_engine = _profile_bootstrap_step("conviction_engine", runtime.ConvictionEngine)

    # Decision Quality Engine — note qualité indépendamment du résultat
    dqe = _profile_bootstrap_step("decision_quality", runtime.DecisionQualityEngine)

    # Portfolio Brain — risque global du portefeuille (corrélation, concentration, exposition)
    portfolio_brain = _profile_bootstrap_step(
        "portfolio_brain",
        lambda: runtime.PortfolioBrain(total_capital=real_capital),
    )

    # Capital Allocation Engine — taille optimale par Kelly/EV/volatilité
    capital_engine = _profile_bootstrap_step(
        "capital_engine",
        lambda: runtime.CapitalAllocationEngine(total_capital=real_capital),
    )

    mistake_memory: Any = None

    def _get_mistake_memory() -> Any:
        nonlocal mistake_memory
        if mistake_memory is None:
            mistake_memory = _profile_bootstrap_step("mistake_memory", runtime.MistakeMemory)
            mm_stats = _stats_dict(mistake_memory.stats())
            log.info("[MistakeMemory] %d erreurs memorisees | %d regles actives",
                     int(mm_stats.get("total", 0) or 0), int(mm_stats.get("rules_active", 0) or 0))
        return mistake_memory

    if not (advisor_only and defer_optional_intel):
        _get_mistake_memory()

    # Executive Override — commandement supreme (domine toutes les couches)
    def _on_override_change(old_level: Any, new_level: Any, triggers: list[str]) -> None:
        trigger_str = " | ".join(triggers[:3])
        _telegram(
            f"EXECUTIVE OVERRIDE — {old_level.name} -> {new_level.name}\n"
            f"Triggers: {trigger_str}\n"
            f"Taille: x{_SIZE_FACTORS_MAP.get(new_level.value, 0):.0%}"
        )

    _SIZE_FACTORS_MAP = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.10, 4: 0.0}
    executive_override = _profile_bootstrap_step(
        "executive_override",
        lambda: runtime.ExecutiveOverride(
            total_capital    = real_capital,
            on_level_change  = _on_override_change,
        ),
    )

    # Black Box Recorder — boite noire indestructible
    black_box = _profile_bootstrap_step("black_box", runtime.BlackBox)
    black_box.record_system_event("DEMARRAGE", f"capital={real_capital:.0f} mode={trading_mode}")

    regret_engine: Any = None

    def _get_regret_engine() -> Any:
        nonlocal regret_engine
        if regret_engine is None:
            regret_engine = _profile_bootstrap_step("regret_engine", runtime.RegretEngine)
            regret_record_count, regret_candidate_count = _get_regret_counts(regret_engine)
            log.info("[RegretEngine] %d records charges | %d candidats en attente",
                     regret_record_count, regret_candidate_count)
        return regret_engine

    if not (advisor_only and defer_optional_intel):
        _get_regret_engine()

    chief_officer: Any = None

    def _get_chief_officer() -> Any:
        nonlocal chief_officer
        if chief_officer is None:
            chief_officer = _profile_bootstrap_step("chief_officer", runtime.ChiefOfficer)
        return chief_officer

    threat_radar = _profile_bootstrap_step("threat_radar", runtime.ThreatRadar)
    log.info("[ThreatRadar] initialise")

    # MetaLearner — sélection exit par régime (Phase 1)
    meta_learner = _profile_bootstrap_step("meta_learner", runtime.MetaLearner)
    log.info("[MetaLearner] %d entrées en mémoire", len(meta_learner.memory))
    _meta_pnl_buffer: dict[str, list[float]] = {}

    def _stop_runtime_services() -> None:
        kill_switch.stop()
        exchange_monitor.stop()
        healer.stop()
        if prewarm_executor is not None:
            prewarm_executor.shutdown(wait=False, cancel_futures=False)
        pos_manager.stop()

    # Callback PositionManager → enregistre le résultat dans le ranker
    def _on_position_close_rank(pos: Any, reason: Any) -> None:
        try:
            pos_regime = getattr(pos, "regime", "unknown")
            # Ranker
            ranker.record_trade(
                strategy_name=pos.subaccount,
                regime=pos_regime,
                pnl_pct=pos.pnl_pct,
                sharpe=max(0.0, pos.pnl_pct / max(0.001, abs(pos.pnl_pct))) if pos.pnl_pct else 0.0,
                drawdown=max(0.0, -pos.pnl_pct) if pos.pnl_pct < 0 else 0.0,
            )
            # Meta-strategy
            meta_engine.record_trade_result(
                regime=pos_regime,
                personality=pos.subaccount,
                pnl_pct=pos.pnl_pct,
            )
            # Self-Awareness — nourrit le détecteur de dérive
            awareness_engine.record_trade(
                pnl_pct=pos.pnl_pct,
                regime=pos_regime,
                personality=pos.subaccount,
                order_size=pos.size_usd,
            )
            # Decision Quality — ferme la décision associée
            dqe.close_decision(pos.order_id, pos.pnl_pct)
            # Mistake Memory — analyse l'erreur et génère des règles
            try:
                side_signal = "BUY" if getattr(pos, "side", None) and pos.side.value == "long" else "SELL"
                _get_mistake_memory().record_trade_result(
                    order_id           = pos.order_id,
                    symbol             = pos.symbol,
                    signal             = side_signal,
                    score              = getattr(pos, "signal_score", 70),
                    regime             = pos_regime,
                    conviction_level   = getattr(pos, "conviction_level", "medium"),
                    pnl_pct            = pos.pnl_pct,
                    context_features   = {},
                    signal_age_sec     = getattr(pos, "signal_age_sec", 0.0),
                    consecutive_losses = _consecutive_losses["value"],
                )
            except Exception as _me:
                log.debug("[MistakeMemory] record échoué: %s", _me)
            # Mise à jour compteur pertes consécutives + Executive Override
            if pos.pnl_pct < 0:
                _consecutive_losses["value"] += 1
                # ── PROTECTIONS: Enregistre SL pour cooldown ──
                last_loss_time[pos.symbol] = time.time()
            else:
                _consecutive_losses["value"] = 0
            # Alimenter l'Override avec les métriques de session
            try:
                pm_stats_live = _stats_dict(pos_manager.stats())
                open_pnl_pct  = _to_float(pm_stats_live.get("open_pnl_usd", 0.0)) / max(1.0, real_capital)
                executive_override.update(
                    loss_streak     = _consecutive_losses["value"],
                    open_pnl_pct    = open_pnl_pct,
                    daily_loss_pct  = max(0.0, -_to_float(pm_stats_live.get("total_pnl_usd", 0.0)) / max(1.0, real_capital)),
                )
            except Exception:
                pass
            # Black Box — fermeture position
            try:
                black_box.record_position_closed(pos, reason)
            except Exception:
                pass
            # MetaLearner — accumule PnL par régime, apprend tous les 5 trades
            try:
                buf = _meta_pnl_buffer.setdefault(pos_regime, [])
                buf.append(pos.pnl_pct)
                if len(buf) >= 5:
                    wins     = sum(1 for p in buf if p > 0)
                    win_rate = wins / len(buf)
                    avg_pnl  = sum(buf) / len(buf)
                    sharpe   = avg_pnl * win_rate * 10
                    trailing = getattr(pos, "trailing", 0) or 0
                    exit_type = "trailing" if trailing > 0 else "tp_sl"
                    meta_learner.learn(
                        context    = {"regime": pos_regime,
                                      "volatility": getattr(pos, "volatility", 0.015)},
                        decision   = {"exit_type": exit_type,
                                      "tp": getattr(pos, "tp_pct", 0.04),
                                      "sl": getattr(pos, "sl_pct", 0.02),
                                      "trail_pct": trailing or None},
                        performance = {"sharpe": round(sharpe, 4),
                                       "win_rate": round(win_rate, 4),
                                       "avg_pnl": round(avg_pnl, 6),
                                       "n_trades": len(buf)},
                    )
                    log.info("[MetaLearner] Apprentissage %s: exit=%s wr=%.0f%% sharpe=%.3f n=%d",
                             pos_regime, exit_type, win_rate * 100, sharpe, len(buf))
                    buf.clear()
            except Exception as _mle:
                log.debug("[MetaLearner] learn échoué: %s", _mle)

        except Exception as _re:
            log.debug("[Feedback] record échoué: %s", _re)

    pos_manager.on_close(_on_position_close_rank)

    _consecutive_losses = {"value": 0}   # compteur partagé entre cycles

    # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
    # #1 Cooldown après perte (5 min)
    last_loss_time: dict[str, float] = {}
    # #2 Pas de re-entry même direction
    last_trade_signal: dict[str, str] = {}
    # #3 Max 10 trades par heure
    trades_this_hour: dict[str, list[float]] = {}

    _t_bootstrap_end = time.perf_counter()

    cycle = 0
    consecutive_errors = 0
    shed_optional_until_cycle = 0

    while True:
        cycle += 1
        cycle_completed = False
        shed_optional_work = cycle <= shed_optional_until_cycle

        # ── Kill switch check ──────────────────────────────────────────────────
        if kill_switch.is_halted() or _halt_requested["value"]:
            log.critical("[main] Kill switch actif — boucle suspendue")
            _telegram("Boucle suspendue par Kill Switch. Envoyer /RESUME pour reprendre.")
            # Attendre que l'opérateur envoie /RESUME
            while kill_switch.is_halted() or _halt_requested["value"]:
                time.sleep(5)
                if not kill_switch.is_halted():
                    _halt_requested["value"] = False
                    break
            log.info("[main] Kill switch levé — reprise boucle")
            _telegram("Kill Switch leve — reprise du cycle normal.")
            continue

        # ── Safe mode check ────────────────────────────────────────────────────
        if kill_switch.is_safe_mode():
            log.warning("[main] Cycle %d — SAFE MODE actif (observation seule)", cycle)

        log.info("--- Cycle %d ---", cycle)
        _t_cycle_start = time.perf_counter()
        try:
            if cycle == 1 and (prewarm_futures or prewarm_mtf_futures):
                warmup_timeout = float(os.getenv("ADVISOR_PREWARM_TIMEOUT", "30"))
                for sym, future in prewarm_futures.items():
                    try:
                        future.result(timeout=warmup_timeout)
                    except Exception as exc:
                        log.warning("[Warmup] %s prechauffage 1h echoue: %s", sym, exc)
                for sym, future in prewarm_mtf_futures.items():
                    try:
                        future.result(timeout=warmup_timeout)
                    except Exception as exc:
                        log.warning("[Warmup] %s prechauffage MTF echoue: %s", sym, exc)
                _t_warmup_end = time.perf_counter()
                prewarm_futures.clear()
                prewarm_mtf_futures.clear()

            # Maintenance ranker — oublie les stratégies stales
            ranker.auto_demote()

            # Mise à jour du capital réel en début de cycle (balance live)
            try:
                fresh_capital = exec_engine.fetch_available_capital()
                if fresh_capital > 0:
                    real_capital = fresh_capital
                    portfolio_brain.update_capital(real_capital)
                    capital_engine.update_capital(real_capital)
            except Exception:
                pass

            results: list[AnalysisResult] = []
            for sym in symbols:
                r = analyze_symbol(
                    sym, scanners, engine, gate, advisor, shadow, watchdog, memory,
                    cycle,
                    order_size_usd=order_size,
                    meta_engine=meta_engine,
                    ranker=ranker,
                    open_positions=pos_manager.get_open(),
                    consecutive_losses=_consecutive_losses["value"],
                    no_trade_layer=no_trade_layer,
                    conviction_engine=conviction_engine,
                    awareness_engine=awareness_engine,
                    dqe=dqe,
                    portfolio_brain     = portfolio_brain,
                    capital_engine      = capital_engine,
                    mistake_memory      = (None if advisor_only and defer_optional_intel else _get_mistake_memory()),
                    executive_override  = executive_override,
                    black_box           = black_box,
                    regret_engine       = (None if advisor_only and defer_optional_intel else _get_regret_engine()),
                    threat_radar        = (
                        threat_radar
                        if (
                            not shed_optional_work
                            and (threat_radar_every <= 1 or cycle % threat_radar_every == 0)
                        )
                        else None
                    ),
                    meta_learner        = meta_learner,
                    runtime             = runtime,
                )
                results.append(r)
                # ── Exécution réelle/paper ─────────────────────────────────────
                r["futures_result"] = None
                # Taille effective : depuis CAE si disponible, sinon order_size global
                allocation = r.get("allocation")
                effective_size = allocation.size_usd if allocation and allocation.size_usd > 0 else r.get("order_size", order_size)

                # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
                # Vérification AVANT exécution
                protection_blocks = []
                current_time = time.time()
                current_signal = r["signal"].signal

                # #1 Cooldown après perte (5 min = 300s)
                if sym in last_loss_time:
                    time_since_loss = current_time - last_loss_time[sym]
                    if time_since_loss < 300:
                        protection_blocks.append(f"cooldown_loss({time_since_loss:.0f}s)")

                # #2 Pas de re-entry même direction
                if sym in last_trade_signal:
                    if last_trade_signal[sym] == current_signal:
                        protection_blocks.append(f"same_direction({current_signal})")

                # #3 Max 10 trades par heure
                now = current_time
                hour_ago = now - 3600
                if sym not in trades_this_hour:
                    trades_this_hour[sym] = []
                trades_this_hour[sym] = [t for t in trades_this_hour[sym] if t > hour_ago]
                if len(trades_this_hour[sym]) >= 10:
                    protection_blocks.append(f"max_trades_1h({len(trades_this_hour[sym])})")

                if protection_blocks:
                    log.info("[PROTECTION] %s BLOQUE par: %s", sym, " | ".join(protection_blocks))

                if (
                    r["signal"].actionable
                    and r.get("trade_allowed", r["gate"].allowed)
                    and not advisor_only
                    and not kill_switch.is_safe_mode()
                    and not protection_blocks  # ← CRITICAL: skip si protections activées
                ):
                    try:
                        if exec_engine.has_futures_demo():
                            fut = _stats_dict(exec_engine.create_futures_order(
                                sym, r["signal"].signal, effective_size
                            ))
                            exec_label = "FUTURES DEMO"
                        else:
                            fut = _stats_dict(exec_engine.create_order(
                                sym, r["signal"].signal, effective_size
                            ))
                            exec_label = "EXECUTION"
                        fut_mode = str(fut.get("mode", ""))
                        fut_id = str(fut.get("id", ""))
                        r["futures_result"] = fut
                        log.info("[FLOW] %s EXECUTION → %s $%.2f", sym, exec_label, effective_size)
                        log.info(
                            "[%s] %s %s $%.2f → mode=%s id=%s",
                            exec_label,
                            r["signal"].signal, sym, effective_size,
                            fut_mode, fut_id,
                        )
                        _pos_registered = _register_position_from_execution(
                            fut,
                            r,
                            sym,
                            r["signal"].signal,
                            effective_size,
                        )
                        if _pos_registered:
                            log.info("[FLOW] %s POSITION → registered mode=%s", sym, fut_mode)
                            # ── PROTECTIONS: Enregistre le trade pour tracking ──
                            last_trade_signal[sym] = r["signal"].signal
                            trades_this_hour[sym].append(current_time)
                        elif fut_mode in {"futures_failed", "live_failed"}:
                            _consecutive_losses["value"] += 1
                    except Exception as _fe:
                        log.error("[EXECUTION] Erreur ordre %s: %s", sym, _fe)
                        _consecutive_losses["value"] += 1

                # Black Box — enregistre chaque décision
                try:
                    r["futures_result"] = r.get("futures_result")  # assure la clé
                    black_box.record_decision(r, cycle)
                except Exception:
                    pass

                # Mise à jour ATR live dans le PositionManager (TP/SL adaptatifs)
                try:
                    feat = r.get("features", {})
                    atr_val = float(feat.get("atr", 0.0))
                    vol_val = float(feat.get("atr_ratio", feat.get("volatility", 0.0)))
                    if atr_val > 0:
                        pos_manager.update_market_data(sym, atr_val, vol_val)
                except Exception:
                    pass

                # Vérification TP/SL avec le prix live du cycle courant.
                # Indispensable en paper_mode où _fetch_price() retourne None
                # et le thread _watch_loop ne peut pas obtenir de prix.
                try:
                    prix_live = float(r.get("prix", 0.0))
                    if prix_live > 0:
                        pos_manager.update_price_and_check(sym, prix_live)
                except Exception as _tpsl_exc:
                    log.warning("[TP/SL] check échoué pour %s: %s", sym, _tpsl_exc)

                # Alerte immédiate si signal actionable (sauf si safe mode)
                if r["signal"].actionable and not kill_switch.is_safe_mode():
                    log.info("SIGNAL ACTIONABLE: %s score=%d %s",
                             sym, r["signal"].score, r["signal"].signal)
                    _telegram(_build_alert(r, cycle))
                elif r["signal"].actionable and kill_switch.is_safe_mode():
                    log.info("SIGNAL ACTIONABLE (safe mode — non envoye): %s score=%d",
                             sym, r["signal"].score)

            # ── Rapport timing bootstrap vs cycle 1 ──────────────────────────
            if cycle == 1:
                _t_cycle_1_end = time.perf_counter()
                t_bootstrap_s = _t_bootstrap_end - _t_main_start
                t_warmup_s    = (_t_warmup_end - _t_warmup_start) if (_t_warmup_start and _t_warmup_end) else 0.0
                t_cycle_1_s   = _t_cycle_1_end - _t_cycle_start
                t_total_s     = _t_cycle_1_end - _t_main_start
                # Session primer: collect elapsed and estimate cycle-1 gain.
                t_primer_s = 0.0
                if _primer_future is not None:
                    try:
                        t_primer_s = float(_primer_future.result(timeout=0))
                    except Exception:
                        t_primer_s = (
                            (time.perf_counter() - _t_primer_start)
                            if _t_primer_start else 0.0
                        )
                    finally:
                        if _primer_executor is not None:
                            _primer_executor.shutdown(wait=False)
                log.info(
                    "[Timing] Bootstrap=%.1fs | Primer=%.1fs | Warmup=%.1fs"
                    " | Cycle1=%.1fs | Total=%.1fs | Cache_1h=%s",
                    t_bootstrap_s, t_primer_s, t_warmup_s, t_cycle_1_s, t_total_s,
                    "CHAUD" if prewarm_1h_enabled else "FROID",
                )
                if bootstrap_profile:
                    bootstrap_detail = " | ".join(
                        f"{name}={duration:.2f}s"
                        for name, duration in sorted(bootstrap_profile, key=lambda item: item[1], reverse=True)
                    )
                    log.info("[Timing] Bootstrap detail: %s", bootstrap_detail)
                if ADVISOR_SESSION_PRIMER and t_primer_s > 0:
                    log.info(
                        "[Timing] Gain SessionPrimer: exchange_init + load_markets (%.1fs)"
                        " effectués en parallèle du bootstrap — ~%.0fms économisés sur le cycle 1",
                        t_primer_s, t_primer_s * 1000,
                    )
                if prewarm_1h_enabled:
                    log.info(
                        "[Timing] Gain warmup: cycle 1 a profite du cache 1h"
                        " (warmup %.1fs effectue en parallele du bootstrap)",
                        t_warmup_s,
                    )

            # Regret Engine — évaluer les candidats en attente
            try:
                if regret_engine is not None:
                    current_prices = {r["symbol"]: r.get("prix", 0.0) for r in results}
                    new_regrets = regret_engine.evaluate_pending(current_prices, cycle)
                    for reg in new_regrets:
                        _telegram(
                            f"REGRET DETECTE: {reg.symbol} {reg.signal} "
                            f"score={reg.score} | move={reg.move_pct:.2%}\n"
                            f"Refuse par: {' | '.join(reg.refused_by)}\n"
                            f"Gain potentiel manque: {reg.potential_pnl_pct:.2%}"
                        )
            except Exception:
                pass

            # Executive Override — mise à jour capital live
            try:
                executive_override.update(capital_current=real_capital)
            except Exception:
                pass

            consecutive_errors = 0

            # Rapport périodique toutes les N cycles
            if cycle % NOTIFY_EVERY == 0:
                msg = _build_summary(results, cycle)
                # Indiquer safe mode dans le rapport
                if kill_switch.is_safe_mode():
                    msg += "\n\n[SAFE MODE] Alertes actions suspendues."
                # Etat exchange monitor
                ex = _stats_dict(exchange_monitor.snapshot())
                if not ex["healthy"]:
                    msg += (
                        f"\n\nEXCHANGE HORS LIGNE — {ex['consecutive_failures']} echecs\n"
                        f"Derniere erreur: {ex['last_error']}"
                    )
                else:
                    msg += f"\n\nExchange: OK ({ex['last_latency_ms']:.0f}ms | uptime {ex['uptime_pct']:.1f}%)"
                # Stats positions ouvertes
                pm_stats = _stats_dict(pos_manager.stats())
                if pm_stats["open_count"] > 0 or pm_stats["closed_count"] > 0:
                    msg += (
                        f"\n\nPOSITIONS:\n"
                        f"  Ouvertes:   {pm_stats['open_count']} | PnL ouvert: {pm_stats['open_pnl_usd']:+.2f}$\n"
                        f"  Fermees:    {pm_stats['closed_count']} | PnL realise: {pm_stats['total_pnl_usd']:+.2f}$\n"
                        f"  Win rate:   {pm_stats['win_rate']:.0%}"
                    )
                    # Détail positions ouvertes
                    for snap in _snapshot_list(pos_manager.snapshot()):
                        dist = snap["liq_dist_pct"]
                        liq_warn = f" LIQ RISK {dist:.0f}%!" if dist < 10 else ""
                        msg += (
                            f"\n  {snap['side'].upper()} {snap['symbol']} "
                            f"entry=${snap['entry']:.0f} | PnL {snap['pnl_usd']:+.1f}$ "
                            f"({snap['pnl_pct']:+.1f}%){liq_warn}"
                        )

                # Ajouter stats shadow si des trades ont été simulés
                shadow_stats = _stats_dict(shadow.stats())
                if shadow_stats.get("n_trades", 0) > 0:
                    msg += (
                        f"\n\nSHADOW STATS ({shadow_stats['n_trades']} trades simules):\n"
                        f"  Slippage moy: {shadow_stats['avg_slippage_pct']:.3f}%\n"
                        f"  Latence moy:  {shadow_stats['avg_latency_ms']:.1f}ms\n"
                        f"  Par regime:   {shadow_stats['by_regime']}"
                    )

                # Executive Override — état du commandement
                try:
                    eo_snap = _stats_dict(executive_override.metrics_snapshot())
                    eo_lvl  = eo_snap.get("level", "CLEAR")
                    if eo_lvl != "CLEAR":
                        msg += (
                            f"\n\nCOMMANDEMENT OVERRIDE: {eo_lvl}"
                            f"\n  DD: -{eo_snap['drawdown_pct']:.1f}%"
                            f" | Daily: -{eo_snap['daily_loss_pct']:.1f}%"
                            f" | Streak: {eo_snap['loss_streak']}"
                            f" | Taille: x{eo_snap['size_factor']:.0%}"
                        )
                    else:
                        msg += f"\n\nCOMMANDEMENT: CLEAR | Taille x100%"
                except Exception:
                    pass

                # Mistake Memory — dernières erreurs + règles actives
                try:
                    mm = _get_mistake_memory()
                    mm_stats = _stats_dict(mm.stats())
                    if mm_stats.get("total", 0) > 0:
                        last_errors = cast(list[str], mm.explain_last_mistakes(3))
                        rules       = cast(list[str], mm.active_rules_summary())
                        msg += (
                            f"\n\nMISTAKE MEMORY ({mm_stats['total']} trades | "
                            f"erreur rate: {mm_stats['error_rate']:.0%} | "
                            f"{mm_stats['rules_active']} règles actives)"
                        )
                        for err in last_errors:
                            msg += f"\n  {err}"
                        for rule in rules[:3]:
                            msg += f"\n  REGLE: {rule}"
                except Exception:
                    pass

                # Portfolio Brain — santé globale du portefeuille
                try:
                    pb_health = _stats_dict(portfolio_brain.portfolio_health(pos_manager.get_open()))
                    msg += (
                        f"\n\nPORTFOLIO BRAIN:"
                        f"\n  Exposition: {pb_health['total_exposure_pct']:.1f}%"
                        f" | Libre: ${pb_health['free_capital']:.0f}"
                        f"\n  Positions: {pb_health['n_positions']}"
                        f" | Corr risk: {pb_health['correlation_risk']:.1f}%"
                        f"\n  PnL ouvert: {pb_health['open_pnl_usd']:+.2f}$"
                    )
                except Exception:
                    pass

                # AI Chief Officer — briefing de synthese
                try:
                    awareness_current = awareness_engine.evaluate() if awareness_engine else None
                    coo_brief = _get_chief_officer().briefing(
                        cycle           = cycle,
                        symbols         = symbols,
                        results         = results,
                        pos_manager     = pos_manager,
                        awareness_state = awareness_current,
                        override        = executive_override,
                        regret_engine   = regret_engine,
                        mistake_memory  = mistake_memory,
                        ranker          = ranker,
                        meta_engine     = meta_engine,
                        black_box       = black_box,
                    )
                    if coo_brief:
                        _telegram(coo_brief)
                except Exception:
                    pass

                # Meta-Strategy + Ranker — personnalité active + top stratégies
                current_personality = meta_engine.current_personality()
                if current_personality is not None:
                    p = current_personality
                    msg += (
                        f"\n\nMETA-STRATEGY: {p.name}"
                        f"\n  Taille: x{p.order_size_factor:.1f} | "
                        f"TP:{p.tp_pct:.0%} SL:{p.sl_pct:.0%}"
                    )
                top3 = cast(list[JSONDict], ranker.leaderboard(3))
                if top3:
                    msg += "\n\nTOP STRATEGIES:"
                    for i, s in enumerate(top3, 1):
                        msg += (
                            f"\n  #{i} {s['name']}/{s['regime']} "
                            f"score={s['composite']:.0f} wr={s['win_rate']:.0%} "
                            f"sharpe={s['avg_sharpe']:.2f}"
                        )
                _telegram(msg)

            # Watchdog fin de cycle
            watchdog.end_cycle(cycle)
            cycle_completed = True

            cycle_elapsed = time.perf_counter() - _t_cycle_start
            if cycle_budget_seconds > 0 and cycle_elapsed > cycle_budget_seconds:
                shed_optional_until_cycle = max(
                    shed_optional_until_cycle,
                    cycle + load_shed_cycles,
                )
                log.info(
                    "[LoadBudget] Cycle %d hors budget %.2fs > %.2fs — travaux optionnels reduits jusqu'au cycle %d",
                    cycle,
                    cycle_elapsed,
                    cycle_budget_seconds,
                    shed_optional_until_cycle,
                )

        except KeyboardInterrupt:
            log.info("Arret manuel.")
            _stop_runtime_services()
            _telegram("Crypto AI Terminal arrete manuellement.")
            break
        except Exception as exc:
            consecutive_errors += 1
            log.error("Erreur cycle %d: %s", cycle, exc, exc_info=True)
            if consecutive_errors >= 5:
                _telegram(
                    f"ALERTE — 5 erreurs consecutives\n"
                    f"Derniere: {exc}\n"
                    f"Verifier logs/advisor_loop.log"
                )
                log.critical("Trop d'erreurs, arret.")
                _stop_runtime_services()
                break

        if max_cycles is not None and cycle >= max_cycles:
            log.info("Max cycles atteint (%d) — arrêt propre.", max_cycles)
            _stop_runtime_services()
            break

        if cycle == 1 and cycle_completed and defer_post_cycle_services:
            _start_kill_switch()
            _start_exchange_monitor()
            _start_healer()

        log.info("Prochain cycle dans %ds...", interval)
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Advisor loop multi-symboles")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--symbols",  nargs="+", default=SYMBOLS_DEFAULT)
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args()
    main(symbols=args.symbols, interval=args.interval, max_cycles=args.max_cycles)
