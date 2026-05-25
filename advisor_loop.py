"""
advisor_loop.py — Boucle d'observation multi-symboles en mode ADVISOR ONLY.

Analyse BTC/USDT, ETH/USDT, SOL/USDT, DOGE/USDT toutes les 5 minutes.
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
import logging
import os
import smtplib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
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


load_dotenv(override=True)

P6_SAFE_MODE: bool = os.environ.get("P6_SAFE_MODE", "false").lower() in (
    "true",
    "1",
    "yes",
)

logging.basicConfig(
    level=getattr(logging, os.getenv("V9_LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            "logs/advisor_loop.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("advisor_loop")

# ── Observability integration (non-blocking — graceful if layers not ready) ──
try:
    from errors.error_bus import ErrorCategory, ErrorSeverity, error_bus
    from observability.heartbeat_system import heartbeat_system
    from observability.metrics_bus import metrics_bus
    from system.module_registry import ModulePriority, module_registry

    _OBS_AVAILABLE = True
except Exception:
    _OBS_AVAILABLE = False

# P2 Operational Closure — execution constraints + simulation pipeline
import json as _json

try:
    import exchange_constraints.binance_rules as _binance_rules_mod
    from exchange_constraints.order_validator import OrderValidator as _OrderValidator
    from exchange_constraints.rate_limiter import OrderRateLimiter as _OrderRateLimiter
    from execution_simulator.config import (
        binance_usdt_futures_simulator as _binance_sim_factory,
    )
    from execution_simulator.models import MarketSnapshot as _MarketSnapshot
    from execution_simulator.models import OrderIntent as _OrderIntent

    _EXEC_CONSTRAINTS_AVAILABLE = True
except Exception:
    _EXEC_CONSTRAINTS_AVAILABLE = False

SYMBOLS_DEFAULT = [
    # Core majors — leaders structurels, capturent le régime global
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    # High-beta momentum — impulsions, liquidations, flow émotionnel
    "DOGE/USDT",
    "PEPE/USDT",
    "WIF/USDT",
    "BONK/USDT",
    # Infrastructure / IA / narratives — souvent décorrélés de BTC
    "LINK/USDT",
    "NEAR/USDT",
    "TAO/USDT",
    "FET/USDT",
    # Market structure / DeFi — réactions macro différentes
    "XRP/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "AAVE/USDT",
    # Stress / volatility — tests slippage et robustesse
    "LTC/USDT",
    "BCH/USDT",
    "SUI/USDT",
    "INJ/USDT",
]
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_BEHAVIOR_CHAT = os.getenv("TELEGRAM_BEHAVIOR_CHAT_ID", "")
NOTIFY_EVERY = int(os.getenv("ADVISOR_NOTIFY_EVERY", "3"))
MTF_REFRESH_EVERY = int(os.getenv("ADVISOR_MTF_REFRESH_EVERY", "12"))
ADVISOR_1H_LIMIT = int(os.getenv("ADVISOR_1H_LIMIT", "96"))
ADVISOR_PREWARM_1H = (
    os.getenv(
        "ADVISOR_PREWARM_1H",
        os.getenv("ADVISOR_WARMUP", "true"),
    ).lower()
    == "true"
)
# Prewarm MTF optionnel (4h + 1d) en parallèle du bootstrap.
# Ne s'active que si ADVISOR_PREWARM_1H est aussi actif (même executor).
# Désactivé par défaut — activer avec ADVISOR_PREWARM_MTF=true.
ADVISOR_PREWARM_MTF = (
    os.getenv("ADVISOR_PREWARM_MTF", "false").lower() == "true" and ADVISOR_PREWARM_1H
)
ADVISOR_LIVE_EXECUTION_BOOTSTRAP = (
    os.getenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false").lower() == "true"
)
ADVISOR_BACKGROUND_POSITION_WATCH = (
    os.getenv("ADVISOR_BACKGROUND_POSITION_WATCH", "false").lower() == "true"
)
ADVISOR_DEFER_OPTIONAL_INTEL = (
    os.getenv("ADVISOR_DEFER_OPTIONAL_INTEL", "true").lower() == "true"
)
ADVISOR_DEFER_POST_CYCLE_SERVICES = (
    os.getenv("ADVISOR_DEFER_POST_CYCLE_SERVICES", "true").lower() == "true"
)
ADVISOR_STARTUP_LIGHT = os.getenv("ADVISOR_STARTUP_LIGHT", "false").lower() == "true"
ADVISOR_THREAT_RADAR_EVERY = max(1, int(os.getenv("ADVISOR_THREAT_RADAR_EVERY", "1")))
ADVISOR_CYCLE_BUDGET_SECONDS = float(os.getenv("ADVISOR_CYCLE_BUDGET_SECONDS", "0"))
ADVISOR_LOAD_SHED_CYCLES = max(1, int(os.getenv("ADVISOR_LOAD_SHED_CYCLES", "1")))
# Warmup persistant : thread daemon qui maintient le cache OHLCV chaud entre les cycles.
# Active avec ADVISOR_PERSISTENT_WARMUP=true ; ne remplace pas ADVISOR_PREWARM_1H.
ADVISOR_PERSISTENT_WARMUP = (
    os.getenv("ADVISOR_PERSISTENT_WARMUP", "false").lower() == "true"
)
# Session primer — pre-create the CCXT exchange and call load_markets() in a daemon thread
# launched BEFORE scanner creation so exchange_init + load_markets overlap the full bootstrap.
# Prewarm threads then skip directly to fetch_ohlcv(), saving up to ~650ms from cycle 1.
ADVISOR_SESSION_PRIMER = os.getenv("ADVISOR_SESSION_PRIMER", "true").lower() == "true"


def _session_primer_config() -> JSONDict:
    _futures_exchanges = {"krakenfutures", "binanceusdm", "bybit", "okx"}
    _exch = os.getenv("EXCHANGE_ID", "binance").lower()
    _default_type = "swap" if _exch in _futures_exchanges else "spot"
    return {
        "enableRateLimit": True,
        "options": {
            "defaultType": _default_type,
            "adjustForTimeDifference": os.getenv(
                "MARKET_SCANNER_ADJUST_TIME", "false"
            ).lower()
            == "true",
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
            markets_ready = scanner_cls._get_exchange_markets_ready(key)
            if not markets_ready.is_set():
                with exchange_call_lock:
                    if not markets_ready.is_set():
                        exchange.load_markets()
                        markets_ready.set()

        elapsed = time.perf_counter() - t0
        t_lm_ms = elapsed * 1000 - t_init_ms
        if trace:
            log.info(
                "[SessionPrimer] exchange_init=%.0fms load_markets=%.0fms total=%.0fms",
                t_init_ms,
                t_lm_ms,
                elapsed * 1000,
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


def _send_email(subject: str, body: str) -> None:
    """Envoie un email de notification via SMTP (config .env)."""
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    from_addr = os.getenv("EMAIL_FROM_ADDR", "")
    smtp_pass = os.getenv("EMAIL_SMTP_PASS", "")
    to_addr = os.getenv("EMAIL_TO_ADDR", "")
    if not all([smtp_server, from_addr, smtp_pass, to_addr]):
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[Crypto AI] {subject}"
        msg["From"] = from_addr
        msg["To"] = to_addr
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as srv:
            srv.starttls()
            srv.login(from_addr, smtp_pass)
            srv.sendmail(from_addr, [to_addr], msg.as_string())
        log.info("[Email] Envoyé : %s", subject)
    except Exception as exc:
        log.warning("[Email] Échec : %s", exc)


def _telegram_behavior(text: str) -> None:
    """Canal comportemental — [BEHAVIOR], transitions, REGIME_MISMATCH, BSM."""
    chat = TELEGRAM_BEHAVIOR_CHAT or TELEGRAM_CHAT  # fallback canal principal
    if not TELEGRAM_TOKEN or not chat:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram behavior erreur: %s", r.text)
    except Exception as exc:
        log.warning("Telegram behavior indisponible: %s", exc)


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
    sl_factor_override: float | None = None,
    tp_factor_override: float | None = None,
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
        mtf_data = scanners["mtf"][symbol].scan(cycle=cycle)
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
            features.update(
                {
                    "ob_imbalance": market_snapshot.order_book_imbalance,
                    "funding_rate": market_snapshot.funding_rate,
                    "funding_velocity": market_snapshot.funding_velocity,
                    "liquidation_risk": market_snapshot.liquidation_risk_score,
                    "whale_score": market_snapshot.whale_accumulation_score,
                }
            )
        if micro_report:
            features.update(
                {
                    "micro_pressure": micro_report.directional_pressure,
                    "micro_spread_bps": micro_report.spread_bps,
                    "execution_risk": micro_report.execution_risk,
                }
            )

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
                transition_forecast = v2_regime_predictor.forecast(
                    symbol, regime_probs, features
                )
                if transition_forecast.crash_risk:
                    log.warning("[V2/RegimePredictor] %s — CRASH RISK détecté", symbol)
            except Exception as _exc_v2:
                log.debug("[V2/RegimePredictor] %s skip: %s", symbol, _exc_v2)

    # MetaLearner — recommandation exit selon régime + volatilité
    ml_decision = None
    if meta_learner:
        volatility = float(features.get("atr_ratio", features.get("volatility", 0.015)))
        ml_decision = meta_learner.find_best(
            {"regime": regime, "volatility": volatility}
        )
        if ml_decision:
            log.debug(
                "[MetaLearner] %s → exit=%s tp=%s sl=%s",
                regime,
                ml_decision.get("exit_type"),
                ml_decision.get("tp"),
                ml_decision.get("sl"),
            )

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
            # Filtrer les entrées sans stratégie nommée (données de test/garbage)
            valid_sharpes = [
                s.get("sharpe", 0)
                for s in stored
                if s.get("strategy")
                and isinstance(s.get("strategy"), dict)
                and s["strategy"].get("name")
                and s.get("sharpe", 0) > 0
            ]
            memory_sharpe = max(valid_sharpes, default=None)
        # Plafond sanity : Sharpe > 5.0 est irréaliste → probablement données de test
        if memory_sharpe and memory_sharpe > 5.0:
            memory_sharpe = None
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
                sl_factor_override=sl_factor_override,
                tp_factor_override=tp_factor_override,
            )
        # Ajuster la taille d'ordre selon la personnalité
        order_size_usd = meta_engine.effective_order_size(order_size_usd, personality)

    # Signal
    with watchdog.measure("signal"):
        signal = engine.evaluate(
            symbol, mtf_candles, features=features, memory_sharpe=memory_sharpe
        )
    log.info(
        "[FLOW] %s SIGNAL → %s score=%d actionable=%s",
        symbol,
        signal.signal,
        signal.score,
        signal.actionable,
    )

    # ── DecisionPacket — pipeline souverain parallèle ────────────────────────
    # Dual track : le packet traverse les 4 couches dans l'ordre du lifecycle.
    # Les variables legacy (gate_result, pb_verdict…) pilotent encore les décisions.
    # Ce bloc produit l'audit trail complet + prépare la migration future.
    _dp = None
    try:
        from quant_hedge_ai.agents.execution.live_signal_engine import (
            _to_decision_packet,
        )

        _dp = _to_decision_packet(signal, cycle_id=str(cycle))
        if conviction_engine and _dp:
            conviction_engine.enrich_packet(
                _dp,
                candles_1h,
                memory_sharpe,
                personality_name=personality.name if personality else "unknown",
            )
    except Exception as _dp_exc:
        log.debug("[DecisionPacket] init/enrich: %s", _dp_exc)
        _dp = None

    # ── Validation Meta-Strategy ───────────────────────────────────────────────
    meta_allowed = True
    meta_reason = "OK"
    if meta_engine and personality:
        meta_allowed, meta_reason = meta_engine.validate_signal(
            signal.signal, signal.score, signal.confirmed, personality
        )

    # Risk gate
    with watchdog.measure("risk"):
        gate_result = gate.check(
            signal, portfolio_drawdown=0.0, order_size_usd=order_size_usd
        )
    if _dp and not _dp.is_terminal() and hasattr(gate, "check_packet"):
        try:
            gate.check_packet(
                _dp, portfolio_drawdown=0.0, order_size_usd=order_size_usd
            )
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] check_packet: %s", _dp_exc)

    # ── TEST MODE — réduire seuil de score pour forcer des trades faibles ──
    min_score_override = float(os.getenv("GATE_MIN_SCORE_OVERRIDE", "0"))
    signal_to_execute = signal.signal  # Default: use original signal
    if min_score_override > 0 and signal.score >= min_score_override:
        # Override gate pour mode test — permet de trader avec score < 70
        gate_result.allowed = True
        # Force BUY signal pour tester (pas HOLD)
        if signal.signal == "HOLD":
            signal_to_execute = "BUY"
            log.info(
                "[GATE_OVERRIDE] Score %.0f >= override %.0f → force BUY (was HOLD)",
                signal.score,
                min_score_override,
            )
        else:
            signal_to_execute = signal.signal

    log.info(
        "[FLOW] %s GATE → %s",
        symbol,
        (
            "OK"
            if gate_result.allowed
            else f"BLOQUÉ({getattr(gate_result, 'reason', '?')})"
        ),
    )

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
            log.warning(
                "[SelfAwareness] Trading bloqué — niveau: %s",
                awareness_state.level.name,
            )

    # ── Conviction Engine ─────────────────────────────────────────────────────
    conviction = None
    if conviction_engine:
        with watchdog.measure("conviction"):
            conviction = conviction_engine.evaluate(
                signal,
                features,
                candles_1h,
                regime,
                memory_sharpe,
                personality_name=personality.name if personality else "unknown",
            )
            if conviction.blocks_trade():
                log.info(
                    "[Conviction] Trade bloqué — conviction minimale (score=%.0f)",
                    conviction.score,
                )

    # ── No-Trade Intelligence check ───────────────────────────────────────────
    no_trade_verdict = None
    if no_trade_layer and signal.actionable:
        with watchdog.measure("no_trade"):
            no_trade_verdict = no_trade_layer.check(
                signal,
                candles_1h,
                features,
                regime,
                personality_name=personality.name if personality else "unknown",
            )

    # ── Mistake Memory — vérification avant trade ─────────────────────────────
    mm_check = None
    if mistake_memory and signal.actionable:
        with watchdog.measure("mistake_memory"):
            mm_check = mistake_memory.check_before_trade(
                symbol=symbol,
                signal=signal.signal,
                score=signal.score,
                regime=regime,
                features=features,
                consecutive_losses=consecutive_losses,
                conviction_level=conviction.level.value if conviction else "medium",
                signal_age_sec=time.time() - signal.timestamp,
            )
            if mm_check.blocked:
                log.info("[MistakeMemory] Trade bloqué: %s", mm_check.reason)

    # ── Portfolio Brain — risque portefeuille global ──────────────────────────
    # La taille effective inclut le facteur conviction AVANT le check portfolio
    # pour que portfolio_brain évalue la taille réellement exécutée.
    _pb_size = order_size_usd * (conviction.size_factor if conviction else 1.0)
    pb_verdict = None
    if portfolio_brain and signal.actionable:
        with watchdog.measure("portfolio_brain"):
            pb_verdict = portfolio_brain.check_new_trade(
                symbol=symbol,
                action=signal.signal,
                size_usd=_pb_size,
                regime=regime,
                open_positions=open_positions_list,
                leverage=1,
                conviction_score=conviction.score if conviction else 50.0,
            )
            if not pb_verdict.allowed:
                log.info("[PortfolioBrain] Bloqué: %s", pb_verdict.reason)
            elif pb_verdict.size_factor < 1.0:
                order_size_usd = order_size_usd * pb_verdict.size_factor
                log.debug(
                    "[PortfolioBrain] Taille réduite ×%.2f → $%.2f",
                    pb_verdict.size_factor,
                    order_size_usd,
                )
    if _dp and _dp.lifecycle_state.value == "RISK_EVALUATED" and portfolio_brain:
        try:
            portfolio_brain.approve_packet(_dp, open_positions_list, order_size_usd)
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] approve_packet: %s", _dp_exc)

    # ── Capital Allocation Engine — taille optimale Kelly/EV/vol ─────────────
    allocation = None
    if (
        capital_engine
        and signal.actionable
        and (pb_verdict is None or pb_verdict.allowed)
    ):
        with watchdog.measure("capital_engine"):
            # Récupère les stats depuis le ranker si disponible
            cae_stats: JSONDict = {}
            if ranker:
                strategy_key = (
                    "btc_momentum"
                    if "BTC" in symbol
                    else ("eth_volatility" if "ETH" in symbol else "sol_experimental")
                )
                cae_stats = capital_engine.stats_from_ranker(
                    ranker, strategy_key, regime
                )
            volatility = float(
                features.get("atr_ratio", features.get("volatility", 0.015))
            )
            allocation = capital_engine.allocate(
                base_size_usd=order_size_usd,
                win_rate=cae_stats.get("win_rate", 0.50),
                avg_win_pct=cae_stats.get("avg_win_pct", 0.03),
                avg_loss_pct=cae_stats.get("avg_loss_pct", 0.02),
                volatility=volatility,
                conviction_factor=conviction.size_factor if conviction else 1.0,
                regime=regime,
                leverage=1,
                n_trades_history=cae_stats.get("n_trades_history", 0),
            )
            if allocation.size_usd > 0:
                order_size_usd = allocation.size_usd
                log.debug(
                    "[CAE] Taille allouée: $%.2f | kelly=%.4f ev=%.5f",
                    allocation.size_usd,
                    allocation.kelly_fraction,
                    allocation.ev_score,
                )
            else:
                log.info("[CAE] Allocation refusée: %s", allocation.reason)

    if _dp and _dp.lifecycle_state.value == "APPROVED":
        try:
            from core.decision_packet import (
                DecisionState,
                ReasoningCategory,
                ReasoningSeverity,
            )

            _dp.add_agent("capital_engine")
            if allocation and allocation.size_usd > 0:
                _dp.features["os_size_usd"] = round(allocation.size_usd, 2)
                _dp.features["os_kelly"] = getattr(allocation, "kelly_fraction", 0.0)
                _dp.add_reasoning(
                    "capital_engine",
                    f"Kelly={getattr(allocation,'kelly_fraction',0):.3f}"
                    f" ev={getattr(allocation,'ev_score',0):.4f}"
                    f" → ${allocation.size_usd:.2f}",
                    confidence_impact=0.0,
                    category=ReasoningCategory.SIZING,
                )
                _dp.transition_to(
                    DecisionState.EXECUTION_PENDING,
                    "capital_engine",
                    f"Sizing: ${allocation.size_usd:.2f}",
                )
            else:
                reason = (
                    getattr(allocation, "reason", "allocation refusée")
                    if allocation is not None
                    else (
                        "capital_engine non initialisé"
                        if not capital_engine
                        else (
                            "signal non actionable"
                            if not signal.actionable
                            else "portfolio_brain bloqué"
                        )
                    )
                )
                _dp.add_reasoning(
                    "capital_engine",
                    f"Sizing refusé: {reason}",
                    confidence_impact=-20.0,
                    category=ReasoningCategory.SIZING,
                    severity=ReasoningSeverity.WARNING,
                )
                _dp.reject("capital_engine", f"Sizing refusé: {reason}")
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] sizing: %s", _dp_exc)

    # ── Executive Override — commandement suprême ─────────────────────────────
    eo_verdict = None
    if executive_override and signal.actionable:
        eo_verdict = executive_override.check_trade(
            size_usd=order_size_usd,
            conviction_score=conviction.score if conviction else 50.0,
        )
        if not eo_verdict.allowed:
            log.warning("[ExecutiveOverride] VETO: %s", eo_verdict.reason)
        elif eo_verdict.size_factor < 1.0:
            order_size_usd = order_size_usd * eo_verdict.size_factor
            log.info(
                "[ExecutiveOverride] %s — taille x%.0f%%",
                eo_verdict.level.name,
                eo_verdict.size_factor * 100,
            )

    # ── V2 : Decision Arbitrator — consensus pondéré multi-agents ────────────
    arbitration_result = None
    if v2_arbitrator and signal.actionable:
        try:
            from quant_hedge_ai.agents.intelligence.v2.decision_arbitrator import (
                AgentVote,
            )

            arb_votes = [
                AgentVote(
                    "global_risk_gate",
                    1.0 if gate_result.allowed else -1.0,
                    veto=not gate_result.allowed,
                ),
                AgentVote(
                    "conviction_engine",
                    ((conviction.score / 100.0) * 2 - 1) if conviction else 0.0,
                ),
                AgentVote(
                    "no_trade_layer",
                    (
                        0.0
                        if no_trade_verdict is None
                        else (1.0 if bool(no_trade_verdict) else -0.6)
                    ),
                ),
                AgentVote(
                    "portfolio_brain",
                    0.0 if pb_verdict is None else (1.0 if bool(pb_verdict) else -0.8),
                ),
                AgentVote("meta_strategy", 0.8 if meta_allowed else -0.5),
                AgentVote(
                    "mistake_memory",
                    0.0 if mm_check is None else (0.5 if bool(mm_check) else -0.7),
                ),
                AgentVote(
                    "executive_override",
                    0.0 if eo_verdict is None else (1.0 if bool(eo_verdict) else -1.0),
                    veto=(eo_verdict is not None and not bool(eo_verdict)),
                ),
                AgentVote(
                    "threat_radar",
                    (
                        0.0
                        if radar_report is None
                        else (0.5 if radar_report.trade_allowed else -0.8)
                    ),
                ),
            ]
            # Enrichir avec signaux V2
            if micro_report:
                side_pressure = (
                    micro_report.directional_pressure
                    if signal.signal == "long"
                    else -micro_report.directional_pressure
                )
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
    if (
        v2_timing_engine
        and signal.actionable
        and (arbitration_result is None or arbitration_result.size_multiplier > 0)
    ):
        try:
            spread = micro_report.spread_bps if micro_report else 5.0
            imbalance = micro_report.imbalance if micro_report else 0.0
            atr = float(features.get("atr_pct", features.get("atr_ratio", 0.01)))
            urgency = float(signal.score) / 100.0 if hasattr(signal, "score") else 0.5
            timing_signal = v2_timing_engine.evaluate(
                symbol, signal.signal, spread, imbalance, atr, urgency
            )
            if not timing_signal.execute_now:
                log.debug("[V2/Timing] %s — attendre: %s", symbol, timing_signal.reason)
        except Exception as _exc_v2:
            log.debug("[V2/Timing] skip: %s", _exc_v2)

    # Décision finale d'autorisation
    _awareness_ok = awareness_engine is None or awareness_engine.is_safe_to_trade()
    _conviction_ok = conviction is None or not conviction.blocks_trade()
    _notrade_ok = no_trade_verdict is None or bool(no_trade_verdict)
    _pb_ok = pb_verdict is None or pb_verdict.allowed
    _cae_ok = allocation is None or bool(allocation)
    _mm_ok = mm_check is None or bool(mm_check)
    _eo_ok = eo_verdict is None or bool(eo_verdict)
    _radar_ok = radar_report is None or radar_report.trade_allowed

    # ── FORCE_TEST_EXECUTION — bypass all checks except gate/signal ──
    force_test_execution = os.getenv("FORCE_TEST_EXECUTION", "false").lower() == "true"
    if (
        force_test_execution
        and gate_result.allowed
        and signal.score >= min_score_override
    ):
        meta_allowed = (
            True  # bypass meta-strategy (sinon MEAN_REVERSION exige score>=72)
        )
        _awareness_ok = True
        _conviction_ok = True
        _notrade_ok = True
        _pb_ok = True
        _cae_ok = True
        _mm_ok = True
        _eo_ok = True
        _radar_ok = True
        # Restaure la taille d'ordre si elle a ete reduite a 0 par
        # meta_strategy (TRADING BLOQUE) ou conviction (size_factor=0).
        # Sinon les logs affichent $0.00 et l'execution_engine fallback
        # sur min_notional Binance (~5$) au lieu d'EXEC_MAX_ORDER_USD.
        if order_size_usd <= 0:
            order_size_usd = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
        log.info(
            "[FORCE_TEST_EXECUTION] Bypass all layers — signal only (size=$%.2f)",
            order_size_usd,
        )

    # V2 arbitration : si disponible, son verdict remplace la logique dispersée
    if arbitration_result is not None:
        from quant_hedge_ai.agents.intelligence.v2.decision_arbitrator import (
            ArbitrationDecision,
        )

        _arb_ok = arbitration_result.decision not in (
            ArbitrationDecision.REJECT,
            ArbitrationDecision.EMERGENCY_EXIT,
        )
        if arbitration_result.size_multiplier > 0 and _arb_ok:
            order_size_usd = order_size_usd * arbitration_result.size_multiplier
    else:
        _arb_ok = True
    trade_allowed = (
        meta_allowed
        and gate_result.allowed
        and _awareness_ok
        and _conviction_ok
        and _notrade_ok
        and _pb_ok
        and _cae_ok
        and _mm_ok
        and _eo_ok
        and _radar_ok
        and _arb_ok
    )
    if signal.actionable:
        _flow_blockers = ", ".join(
            filter(
                None,
                [
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
                ],
            )
        )
        _alloc_str = (
            f" alloc=${allocation.size_usd:.0f}"
            if allocation and allocation.size_usd > 0
            else ""
        )
        log.info(
            "[FLOW] %s VERDICT → %s%s%s",
            symbol,
            "TRADE_OK" if trade_allowed else "BLOQUÉ",
            _alloc_str,
            f" [{_flow_blockers}]" if _flow_blockers else "",
        )

    # ── Regret Engine — enregistre les refus potentiellement rentables ─────────
    if regret_engine and signal.actionable and not trade_allowed:
        refused_by_list: list[str] = []
        if not _eo_ok:
            refused_by_list.append("executive_override")
        if not _mm_ok:
            refused_by_list.append("mistake_memory")
        if not _pb_ok:
            refused_by_list.append("portfolio_brain")
        if not _conviction_ok:
            refused_by_list.append("conviction")
        if not _notrade_ok:
            refused_by_list.append("no_trade")
        if not _awareness_ok:
            refused_by_list.append("awareness")
        if not meta_allowed:
            refused_by_list.append("meta_strategy")
        if not gate_result.allowed:
            refused_by_list.append("gate")
        if not _radar_ok:
            refused_by_list.append("threat_radar")
        regret_engine.register_candidate(
            symbol=symbol,
            signal=signal.signal,
            score=signal.score,
            regime=regime,
            price=prix,
            refused_by=refused_by_list,
            cycle=cycle,
            conviction_level=conviction.level.value if conviction else "medium",
        )

    # ── Decision Quality — évaluation avant exécution ─────────────────────────
    dq_record = None
    if dqe and signal.actionable:
        dq_record = dqe.evaluate_decision(
            signal,
            conviction_score=conviction.score if conviction else 50.0,
            conviction_level=conviction.level.value if conviction else "medium",
            regime=regime,
            personality_name=personality.name if personality else "unknown",
            no_trade_score=(
                no_trade_verdict.rejection_score if no_trade_verdict else 0.0
            ),
            meta_allowed=meta_allowed,
            gate_allowed=gate_result.allowed,
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
    conv_str = (
        f" | conv: {conviction.level.value}({conviction.score:.0f})"
        if conviction
        else ""
    )
    aw_str = f" | aware: {awareness_state.level.name}" if awareness_state else ""
    pb_str = f" | pb: {pb_verdict.size_factor:.2f}" if pb_verdict else ""
    cae_str = (
        f" | cae: ${allocation.size_usd:.0f}"
        if allocation and allocation.size_usd > 0
        else ""
    )
    mm_str = " | mm: BLOQUE" if mm_check and mm_check.blocked else ""
    eo_str = (
        f" | eo: {eo_verdict.level.name}"
        if eo_verdict and eo_verdict.level.value > 0
        else ""
    )
    log.info(
        "  %s | $%.2f | score: %d/100 | %s | regime: %s | perso: %s | gate: %s%s%s%s%s%s%s",
        symbol,
        prix,
        signal.score,
        signal.signal,
        regime,
        persona_name,
        "OK" if trade_allowed else "BLOQUE",
        conv_str,
        aw_str,
        pb_str,
        cae_str,
        mm_str,
        eo_str,
    )

    # ── Persistance DecisionPacket ────────────────────────────────────────────
    # Rotation quotidienne : DP_LOG_PATH explicite → utilisé tel quel (compat).
    # Sinon : DP_LOG_DIR/decision_packets_YYYY-MM-DD.jsonl (UTC).
    if _dp and _dp.lifecycle_state.value != "CREATED":
        try:
            import json as _json
            from datetime import datetime as _dt
            from pathlib import Path as _Path

            _explicit = os.getenv("DP_LOG_PATH")
            if _explicit:
                _dp_path = _Path(_explicit)
            else:
                _log_dir = _Path(os.getenv("DP_LOG_DIR", "databases"))
                _date = _dt.utcnow().strftime("%Y-%m-%d")
                _dp_path = _log_dir / f"decision_packets_{_date}.jsonl"
            _dp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_dp_path, "a", encoding="utf-8") as _f:
                _f.write(_json.dumps(_dp.to_dict(), ensure_ascii=False) + "\n")
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] log: %s", _dp_exc)

    return {
        "symbol": symbol,
        "prix": prix,
        "signal": signal,
        "gate": gate_result,
        "advice": advice,
        "explanation": explanation,
        "shadow": shadow_trade,
        "personality": personality,
        "meta_allowed": meta_allowed,
        "meta_reason": meta_reason,
        "conviction": conviction,
        "no_trade_verdict": no_trade_verdict,
        "awareness_state": awareness_state,
        "pb_verdict": pb_verdict,
        "allocation": allocation,
        "mm_check": mm_check,
        "eo_verdict": eo_verdict,
        "dq_record": dq_record,
        "trade_allowed": trade_allowed,
        "blockers": _flow_blockers if signal.actionable else "",
        "order_size": order_size_usd,
        "regime": regime,
        "features": features,
        "radar_report": radar_report,
        "ml_decision": ml_decision,
        "n_1h": len(candles_1h),
        "n_4h": len(mtf_candles.get("4h", [])),
        "n_1d": len(mtf_candles.get("1d", [])),
        "signal_to_execute": signal_to_execute,
        "decision_packet": _dp,
    }


# ── Construction messages Telegram ───────────────────────────────────────────

_SIGNAL_ICON = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}
_REGIME_FR = {
    "bull_trend": "Tendance haussiere",
    "bear_trend": "Tendance baissiere",
    "sideways": "Range lateral",
    "high_volatility_regime": "Haute volatilite",
    "flash_crash": "KRACH ECLAIR",
    "unknown": "Indetermine",
}
_SCORE_BAR = [
    (85, "FORT"),
    (70, "BON"),
    (50, "MOYEN"),
    (30, "FAIBLE"),
    (0, "TRES FAIBLE"),
]


def _score_label(score: int) -> str:
    for threshold, label in _SCORE_BAR:
        if score >= threshold:
            return label
    return "TRES FAIBLE"


def _build_summary(
    results: list[AnalysisResult], cycle: int, min_score: int = 70
) -> str:
    """Message de rapport périodique — toutes les N cycles."""
    lines = [f"Crypto AI Terminal — Rapport cycle {cycle}", ""]

    for r in results:
        s = r["signal"]
        g = r["gate"]
        a = r["advice"]
        icon = _SIGNAL_ICON.get(s.signal, "?")
        regime = _REGIME_FR.get(s.regime, s.regime)
        label = _score_label(s.score)
        gate_s = "PRET" if g.allowed else "BLOQUE"
        comps = s.components

        persona = r.get("personality")
        p_name = persona.name if persona else "N/A"
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
        lines.append(
            f"TRADING ACTIF — ordres Futures Demo executes sur signaux >= {min_score}"
        )
    return "\n".join(lines)


def _build_alert(r: AnalysisResult, cycle: int) -> str:
    """Message d'alerte immédiate — signal actionable détecté."""
    s = r["signal"]
    g = r["gate"]
    a = r["advice"]
    sh = r.get("shadow")
    ex = r.get("explanation")
    icon = _SIGNAL_ICON.get(s.signal, "?")
    regime = _REGIME_FR.get(s.regime, s.regime)
    comps = s.components

    lines = [
        f"SIGNAL ACTIONABLE — Cycle {cycle}",
        "",
        f"{icon} {r['symbol']} | ${r['prix']:.2f}",
        f"Score: {s.score}/100 | {s.signal}",
        f"Regime: {regime} | Confirme: {s.confirmed}",
        f"Force: {s.strength:.0%}",
        "",
        "Scores detail:",
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
            "SHADOW EXECUTION (simule, pas envoye):",
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
                "ORDRE FUTURES DEMO PLACE:",
                f"  ID:         {fut.get('id', '?')}",
                f"  Notionnel:  ${fut.get('usd_size', 0):.2f}",
                f"  Statut:     {fut.get('status', '?')}",
            ]
        elif mode == "paper":
            lines += [
                "",
                "ORDRE PAPER PLACE (simulation locale):",
                f"  Cote:       {r.get('signal', {}).side if hasattr(r.get('signal', None), 'side') else '?'}",
                f"  Taille:     ${r.get('order_size', 0):.2f}",
            ]
        elif mode == "futures_failed":
            lines += [
                "",
                f"ORDRE FUTURES ECHOUE: {fut.get('error', '?')}",
            ]
    else:
        advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
        blockers = r.get("blockers", "")
        if advisor_only:
            suffix = "Mode observation — aucun ordre place"
        elif blockers:
            suffix = f"Bloque par: {blockers} — aucun ordre place"
        else:
            suffix = "Gate bloquee ou safe mode — aucun ordre place"
        lines += ["", suffix]

    lines += [
        "",
        f"Analyse: {str(a.text)[:250]}",
    ]
    return "\n".join(lines)


def _build_guide() -> str:
    """Guide d'interprétation envoyé au démarrage."""
    _threshold = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
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
        f"Alerte immediate si score >= {_threshold}."
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

    _t_main_start = (
        time.perf_counter()
    )  # référence pour comparaison bootstrap / cycle 1
    bootstrap_profile: list[tuple[str, float]] = []

    def _profile_bootstrap_step(label: str, fn: Any) -> Any:
        started = time.perf_counter()
        try:
            return fn()
        finally:
            bootstrap_profile.append((label, time.perf_counter() - started))

    log.info("=== ADVISOR LOOP DEMARRE ===")
    log.info(
        "Symboles: %s | Intervalle: %ds | Notify every: %d cycles",
        symbols,
        interval,
        NOTIFY_EVERY,
    )

    if _OBS_AVAILABLE:
        try:
            module_registry.register(
                "advisor_loop",
                priority=ModulePriority.HIGH,
                heartbeat_timeout_sec=max(interval * 2, 120),
            )
            heartbeat_system.register(
                "advisor_loop", timeout_sec=max(interval * 2, 120)
            )
        except Exception:
            pass

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
        _exchange_id = os.getenv(
            "MARKET_SCANNER_EXCHANGE", os.getenv("EXCHANGE_ID", "binance")
        )
        # MARKET_SCANNER_TESTNET prioritaire — OHLCV publics = vrai exchange
        _scanner_testnet_env = os.getenv("MARKET_SCANNER_TESTNET", "").lower()
        if _scanner_testnet_env in ("true", "false"):
            _testnet = _scanner_testnet_env == "true"
        else:
            _testnet = os.getenv("EXCHANGE_TESTNET", "false").lower() == "true"
        _trace_primer = (
            os.getenv("MARKET_SCANNER_TRACE_TIMINGS", "false").lower() == "true"
        )
        try:
            _scanner_cls = runtime.MarketScanner  # class reference, not instance
            _primer_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="SessionPrimer"
            )
            _t_primer_start = time.perf_counter()
            _primer_future = _primer_executor.submit(
                _prime_exchange_session,
                _exchange_id,
                _testnet,
                _scanner_cls,
                trace=_trace_primer,
            )
            log.info(
                "[SessionPrimer] Lancé en avance (exchange=%s testnet=%s) "
                "— exchange_init + load_markets en parallèle du bootstrap",
                _exchange_id,
                _testnet,
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
            "1h": {
                sym: runtime.MarketScanner(
                    symbols=[sym], timeframe="1h", limit=ADVISOR_1H_LIMIT
                )
                for sym in symbols
            },
            "mtf": {
                sym: runtime.MultiTimeframeScanner(
                    symbols=[sym], refresh_every=MTF_REFRESH_EVERY
                )
                for sym in symbols
            },
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
    defer_post_cycle_services = advisor_only and (
        ADVISOR_DEFER_POST_CYCLE_SERVICES or startup_light
    )
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
        max_workers = max(
            1,
            min(
                len(symbols) + n_mtf_slots,
                int(
                    os.getenv(
                        "ADVISOR_PREWARM_MAX_WORKERS",
                        str(len(symbols) + n_mtf_slots or 1),
                    )
                ),
            ),
        )
        prewarm_executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="AdvisorWarm"
        )
        _t_warmup_start = time.perf_counter()
        prewarm_futures = {
            sym: prewarm_executor.submit(scanners["1h"][sym].scan)
            for sym in symbols
            if hasattr(scanners["1h"][sym], "scan")
        }
        if prewarm_futures:
            log.info(
                "[Warmup] Prechauffage 1h lance EN AVANCE pour %d symbole(s) (avant services boot)",
                len(prewarm_futures),
            )
        if prewarm_mtf_enabled:
            prewarm_mtf_futures = {
                sym: prewarm_executor.submit(scanners["mtf"][sym].scan)
                for sym in symbols
                if hasattr(scanners["mtf"][sym], "scan")
            }
            if prewarm_mtf_futures:
                log.info(
                    "[Warmup] Prechauffage MTF (4h+1d) lance en background",
                )
        if not prewarm_futures and not prewarm_mtf_futures:
            prewarm_executor.shutdown(wait=False, cancel_futures=True)
            prewarm_executor = None

    # Kill switch — état partagé entre thread Telegram et boucle principale
    _halt_requested = {"value": False}
    _awareness_ref: dict = {"engine": None}  # rempli après création awareness_engine

    def _on_stop_all():
        _halt_requested["value"] = True
        log.critical("[main] STOP_ALL recu — la boucle va s'arreter au prochain cycle")

    def _on_close_all():
        _halt_requested["value"] = True
        log.critical("[main] CLOSE_ALL recu — la boucle va s'arreter au prochain cycle")

    def _on_resume():
        if _awareness_ref["engine"] is not None:
            _awareness_ref["engine"].reset()
            log.info("[main] /RESUME — SelfAwareness reset (retour a OK)")

    kill_switch = _profile_bootstrap_step(
        "kill_switch",
        lambda: runtime.TelegramKillSwitch(
            on_stop_all=_on_stop_all,
            on_close_all=_on_close_all,
            on_resume=_on_resume,
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
        log.info(
            "[Startup] ExchangeMonitor differe apres le cycle 1 (observation seule)"
        )
    else:
        _start_exchange_monitor()

    # Self-healing bot — surveille les composants critiques
    healer = _profile_bootstrap_step(
        "self_healing",
        lambda: runtime.SelfHealingBot(global_check_interval_s=10.0),
    )

    # Composant 1 : exchange
    def _exchange_restart() -> None:
        log.warning("[SelfHeal] Exchange unhealthy — tentative de reconnexion")
        try:
            ok = exec_engine.reconnect()
            if ok:
                log.info("[SelfHeal] Exchange reconnecté avec succès")
            else:
                log.error("[SelfHeal] Reconnexion échouée — bot en mode dégradé")
        except Exception as exc:
            log.exception("[SelfHeal] Reconnexion exception: %s", exc)

    def _exchange_health_check() -> bool:
        # Tolère les timeouts transitoires du testnet — ne déclenche une reconnexion
        # qu'après 3 échecs consécutifs pour éviter les faux positifs.
        if not exchange_monitor.is_healthy():
            snap = exchange_monitor.snapshot()
            failures = snap.get("consecutive_failures", 0)
            if failures < 3:
                return True  # transitoire, pas encore critique
            err = snap.get("last_error") or f"ping KO ({failures} échecs)"
            raise RuntimeError(err)
        return True

    _profile_bootstrap_step(
        "self_healing.register_exchange",
        lambda: healer.register_simple(
            "exchange",
            health_fn=_exchange_health_check,
            restart_fn=_exchange_restart,
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
        lambda: healer.register_simple(
            "lm_studio", health_fn=_lm_health, restart_fn=_lm_restart
        ),
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
                lambda: CacheWarmer(
                    scanner=None, symbols=symbols, timeframes=["1h", "4h", "1d"]
                ),
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
        exec_engine = _profile_bootstrap_step(
            "execution_engine", runtime.ExecutionEngine
        )
        has_futures = False
        futures_bal = 0.0
    else:
        exec_engine = _profile_bootstrap_step(
            "execution_engine.from_env", runtime.ExecutionEngine.from_env
        )
        has_futures = exec_engine.has_futures_demo()
        futures_bal = exec_engine.fetch_futures_balance() if has_futures else 0.0

    # Lire le capital réel disponible (balance USDT testnet ou .env fallback)
    real_capital = exec_engine.fetch_available_capital()

    # P2: Refresh exchange rules from live API + init execution pipeline
    if _EXEC_CONSTRAINTS_AVAILABLE:
        try:
            _binance_rules_mod.refresh_from_exchange()
            log.info("[P2] Règles exchange rafraîchies depuis l'API Binance live")
        except Exception as _ref_exc:
            log.warning(
                "[P2] refresh_from_exchange() échoué (snapshot statique utilisé): %s",
                _ref_exc,
            )
        _order_validator = _OrderValidator()
        _rate_limiter = _OrderRateLimiter()
        _exec_sim = _binance_sim_factory()
        os.makedirs("logs/execution_audit", exist_ok=True)
    else:
        _order_validator = _rate_limiter = _exec_sim = None

    max_order = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
    order_size = min(
        max_order, real_capital * float(os.getenv("V9_MAX_POSITION_WEIGHT", "0.05"))
    )
    log.info(
        "Capital disponible: $%.2f | Taille ordre: $%.2f (max $%.2f)",
        real_capital,
        order_size,
        max_order,
    )

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
        log.info(
            "[SubaccountManager] Initialisé — positions seront synchronisées vers dashboard"
        )
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
        side = (
            "BUY" if getattr(pos, "side", None) and pos.side.value == "long" else "SELL"
        )
        return {
            "id": str(
                getattr(pos, "order_id", "")
                or f"{pos.symbol}_{int(getattr(pos, 'opened_at', time.time()) * 1000)}"
            ),
            "symbol": pos.symbol,
            "side": side,
            "entry_price": float(pos.entry_price),
            "size": float(pos.size_usd),
            "timestamp": float(getattr(pos, "opened_at", time.time())),
            "regime": getattr(pos, "regime", "unknown"),
            "confidence": float(getattr(pos, "signal_score", 0.0)),
            "max_price": float(getattr(pos, "highest_price", pos.entry_price)),
            "min_price": float(getattr(pos, "lowest_price", pos.entry_price)),
            "price_path": [
                float(pos.entry_price),
                float(
                    getattr(pos, "current_price", pos.entry_price) or pos.entry_price
                ),
            ],
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
            log.warning(
                "[TrackerSystem] refresh échoué après %s: %s", event_name, tracker_exc
            )

    def _build_position_from_execution(
        order_result: JSONDict,
        result_row: AnalysisResult,
        symbol: str,
        action: str,
        effective_size: float,
    ) -> Any:
        personality = result_row.get("personality")
        feat = result_row.get("features", {})
        atr_val = float(feat.get("atr", 0.0))
        vol_val = float(feat.get("atr_ratio", feat.get("volatility", 0.0)))
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
                tp_pct=(
                    (result_row.get("ml_decision") or {}).get("tp")
                    or (personality.tp_pct if personality else 0.04)
                ),
                sl_pct=(
                    (result_row.get("ml_decision") or {}).get("sl")
                    or (personality.sl_pct if personality else 0.02)
                ),
                trailing=(
                    (result_row.get("ml_decision") or {}).get("trail_pct")
                    or (personality.trailing_pct if personality else 0.0)
                ),
                atr=atr_val,
                volatility=vol_val,
                regime=result_row.get("regime", "unknown"),
            )
        else:
            from quant_hedge_ai.agents.execution.position_manager import (
                PositionSide as _PS,
            )

            pos = Position(
                symbol=symbol,
                side=_PS.LONG if action.upper() == "BUY" else _PS.SHORT,
                entry_price=entry_price,
                size_usd=effective_size,
                qty=qty,
                subaccount="main",
            )

        pos.signal_score = result_row["signal"].score
        pos.conviction_level = (
            result_row["conviction"].level.value
            if result_row.get("conviction")
            else "medium"
        )
        pos.signal_age_sec = time.time() - result_row["signal"].timestamp
        raw_features = result_row.get("features")
        pos.entry_features = raw_features if isinstance(raw_features, dict) else {}
        pos.subaccount = (
            "btc_momentum"
            if "BTC" in symbol
            else ("eth_volatility" if "ETH" in symbol else "sol_experimental")
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
                        unit.position_manager.add_position(pos, silent=True)
                        log.debug(
                            "[SubaccountManager SYNC] Position enregistrée dans %s",
                            subaccount_name,
                        )
                except Exception as _sync_exc:
                    log.debug("[SubaccountManager SYNC] Failed: %s", _sync_exc)
            try:
                import json as _json
                import os as _os

                _snap_path: str = _os.path.join("databases", "positions_snapshot.json")
                _snap_tmp: str = _snap_path + ".tmp"
                _snap_positions: list[dict[str, Any]] = _snapshot_list(
                    pos_manager.snapshot()
                )
                _snap_data: dict[str, Any] = {
                    "ts": time.time(),
                    "positions": _snap_positions,
                }
                with open(_snap_tmp, "w", encoding="utf-8") as _sf:
                    _json.dump(_snap_data, _sf)
                _os.replace(_snap_tmp, _snap_path)
            except Exception as _snap_exc:
                log.debug("[SNAPSHOT] write échoué: %s", _snap_exc)
            try:
                tracker_open_position(
                    symbol=symbol,
                    side=action,
                    price=float(
                        getattr(
                            pos, "entry_price", _to_float(result_row.get("prix", 0.0))
                        )
                    ),
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
                log.warning(
                    "[TrackerSystem] open échoué pour %s: %s", symbol, tracker_exc
                )
            # ── PaperTradeRecorder — source de vérité entry ───────────────────
            try:
                from paper_trading.recorder import get_recorder as _get_recorder

                _get_recorder().record_open(
                    trade_id=str(getattr(pos, "order_id", "") or id(pos)),
                    symbol=symbol,
                    side=action,
                    price=float(
                        getattr(
                            pos, "entry_price", _to_float(result_row.get("prix", 0.0))
                        )
                    ),
                    size_usd=float(effective_size),
                    regime=result_row.get("regime", "unknown"),
                    score=int(_to_float(getattr(result_row.get("signal"), "score", 0))),
                    order_id=str(getattr(pos, "order_id", "")),
                    mode=str(order_result.get("mode", "futures_demo")),
                )
            except Exception as _rec_exc:
                log.debug("[PaperRecorder] open échoué: %s", _rec_exc)
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
                    log.debug(
                        "[SubaccountManager SYNC] Position fermée dans %s",
                        subaccount_name,
                    )
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
            log.warning(
                "[TrackerSystem] finalize échoué pour %s: %s", pos.symbol, tracker_exc
            )

        # ── PaperTradeRecorder — source de vérité exit ───────────────────────
        try:
            from paper_trading.recorder import get_recorder as _get_recorder

            _get_recorder().record_close(
                trade_id=str(getattr(pos, "order_id", "") or id(pos)),
                exit_price=float(getattr(pos, "current_price", 0.0) or pos.entry_price),
                pnl_usd=float(getattr(pos, "pnl_usd", 0.0) or 0.0),
                pnl_pct=float(getattr(pos, "pnl_pct", 0.0) or 0.0),
                reason=getattr(reason, "value", str(reason)),
                opened_at=float(getattr(pos, "opened_at", 0.0) or 0.0),
                symbol=str(getattr(pos, "symbol", "")),
                side=getattr(
                    getattr(pos, "side", None), "value", str(getattr(pos, "side", ""))
                ),
                size_usd=float(getattr(pos, "size_usd", 0.0) or 0.0),
                mode=str(getattr(pos, "mode", "futures_demo")),
            )
        except Exception as _rec_exc:
            log.debug("[PaperRecorder] close échoué: %s", _rec_exc)

        sign = "+" if pos.pnl_usd >= 0 else ""
        _telegram(
            f"POSITION FERMEE — {reason.value.upper()}\n"
            f"{pos.side.value.upper()} {pos.symbol}\n"
            f"Entry: ${pos.entry_price:.2f} | Exit: ${pos.current_price:.2f}\n"
            f"PnL: {sign}${pos.pnl_usd:.2f} ({sign}{pos.pnl_pct:.2%})\n"
            f"Subcompte: {pos.subaccount}"
        )

    pos_manager.on_close(_on_position_close)

    if P6_SAFE_MODE:
        log.warning(
            "[P6] SAFE MODE ACTIF — boucles adaptatives désactivées (threshold fixe)"
        )
    else:
        log.info("[P6] Mode adaptatif — ATE + RegimeSmoother + REGIME_MISMATCH actifs")

    _gate_min_score = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
    _gate_require_confirmed = (
        os.getenv("GATE_REQUIRE_CONFIRMED", "true").lower() == "true"
    )
    gate = _profile_bootstrap_step(
        "global_risk_gate",
        lambda: runtime.GlobalRiskGate(
            min_signal_score=_gate_min_score,
            require_confirmed=_gate_require_confirmed,
            safe_mode=P6_SAFE_MODE,
        ),
    )
    engine = _profile_bootstrap_step("live_signal_engine", runtime.LiveSignalEngine)
    advisor = _profile_bootstrap_step("ai_advisor", runtime.AIAdvisor)
    shadow = _profile_bootstrap_step(
        "shadow_execution", lambda: runtime.ShadowExecutionEngine(risk_gate=gate)
    )
    watchdog = _profile_bootstrap_step(
        "performance_watchdog", runtime.PerformanceWatchdog
    )
    memory = _profile_bootstrap_step(
        "strategy_memory_store", runtime.StrategyMemoryStore
    )

    # Meta-Strategy Engine — personnalité adaptée au régime
    meta_engine = _profile_bootstrap_step(
        "meta_strategy",
        lambda: runtime.MetaStrategyEngine(safe_mode=P6_SAFE_MODE),
    )

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
    _awareness_ref["engine"] = awareness_engine  # expose pour /RESUME callback

    # No-Trade Intelligence — refus intelligents
    no_trade_layer = _profile_bootstrap_step(
        "no_trade_intelligence", runtime.NoTradeIntelligence
    )

    # Conviction Engine — 4 niveaux de conviction
    conviction_engine = _profile_bootstrap_step(
        "conviction_engine", runtime.ConvictionEngine
    )

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
            mistake_memory = _profile_bootstrap_step(
                "mistake_memory", runtime.MistakeMemory
            )
            mm_stats = _stats_dict(mistake_memory.stats())
            log.info(
                "[MistakeMemory] %d erreurs memorisees | %d regles actives",
                int(mm_stats.get("total", 0) or 0),
                int(mm_stats.get("rules_active", 0) or 0),
            )
        return mistake_memory

    if not (advisor_only and defer_optional_intel):
        _get_mistake_memory()

    # Executive Override — commandement supreme (domine toutes les couches)
    def _on_override_change(
        old_level: Any, new_level: Any, triggers: list[str]
    ) -> None:
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
            total_capital=real_capital,
            on_level_change=_on_override_change,
        ),
    )

    # Black Box Recorder — boite noire indestructible
    black_box = _profile_bootstrap_step("black_box", runtime.BlackBox)
    black_box.record_system_event(
        "DEMARRAGE", f"capital={real_capital:.0f} mode={trading_mode}"
    )

    regret_engine: Any = None

    def _get_regret_engine() -> Any:
        nonlocal regret_engine
        if regret_engine is None:
            regret_engine = _profile_bootstrap_step(
                "regret_engine", runtime.RegretEngine
            )
            regret_record_count, regret_candidate_count = _get_regret_counts(
                regret_engine
            )
            log.info(
                "[RegretEngine] %d records charges | %d candidats en attente",
                regret_record_count,
                regret_candidate_count,
            )
        return regret_engine

    if not (advisor_only and defer_optional_intel):
        _get_regret_engine()

    chief_officer: Any = None

    def _get_chief_officer() -> Any:
        nonlocal chief_officer
        if chief_officer is None:
            chief_officer = _profile_bootstrap_step(
                "chief_officer", runtime.ChiefOfficer
            )
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
                sharpe=(
                    max(0.0, pos.pnl_pct / max(0.001, abs(pos.pnl_pct)))
                    if pos.pnl_pct
                    else 0.0
                ),
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
                side_signal = (
                    "BUY"
                    if getattr(pos, "side", None) and pos.side.value == "long"
                    else "SELL"
                )
                _get_mistake_memory().record_trade_result(
                    order_id=pos.order_id,
                    symbol=pos.symbol,
                    signal=side_signal,
                    score=getattr(pos, "signal_score", 70),
                    regime=pos_regime,
                    conviction_level=getattr(pos, "conviction_level", "medium"),
                    pnl_pct=pos.pnl_pct,
                    context_features=getattr(pos, "entry_features", {}),
                    signal_age_sec=getattr(pos, "signal_age_sec", 0.0),
                    consecutive_losses=_consecutive_losses["value"],
                    exit_reason=getattr(pos, "close_reason", ""),
                    personality=getattr(pos, "subaccount", ""),
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
            # Libère la protection same_direction après fermeture de position
            # (last_loss_time couvre déjà la re-entry immédiate après perte)
            last_trade_signal.pop(pos.symbol, None)
            # Alimenter l'Override avec les métriques de session
            try:
                pm_stats_live = _stats_dict(pos_manager.stats())
                open_pnl_pct = _to_float(pm_stats_live.get("open_pnl_usd", 0.0)) / max(
                    1.0, real_capital
                )
                executive_override.update(
                    loss_streak=_consecutive_losses["value"],
                    open_pnl_pct=open_pnl_pct,
                    daily_loss_pct=max(
                        0.0,
                        -_to_float(pm_stats_live.get("total_pnl_usd", 0.0))
                        / max(1.0, real_capital),
                    ),
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
                    wins = sum(1 for p in buf if p > 0)
                    win_rate = wins / len(buf)
                    avg_pnl = sum(buf) / len(buf)
                    sharpe = avg_pnl * win_rate * 10
                    trailing = getattr(pos, "trailing", 0) or 0
                    exit_type = "trailing" if trailing > 0 else "tp_sl"
                    meta_learner.learn(
                        context={
                            "regime": pos_regime,
                            "volatility": getattr(pos, "volatility", 0.015),
                        },
                        decision={
                            "exit_type": exit_type,
                            "tp": getattr(pos, "tp_pct", 0.04),
                            "sl": getattr(pos, "sl_pct", 0.02),
                            "trail_pct": trailing or None,
                        },
                        performance={
                            "sharpe": round(sharpe, 4),
                            "win_rate": round(win_rate, 4),
                            "avg_pnl": round(avg_pnl, 6),
                            "n_trades": len(buf),
                        },
                    )
                    log.info(
                        "[MetaLearner] Apprentissage %s: exit=%s wr=%.0f%% sharpe=%.3f n=%d",
                        pos_regime,
                        exit_type,
                        win_rate * 100,
                        sharpe,
                        len(buf),
                    )
                    buf.clear()
            except Exception as _mle:
                log.debug("[MetaLearner] learn échoué: %s", _mle)

        except Exception as _re:
            log.debug("[Feedback] record échoué: %s", _re)

    pos_manager.on_close(_on_position_close_rank)

    _consecutive_losses = {"value": 0}  # compteur partagé entre cycles

    # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
    # #1 Cooldown après perte (5 min)
    last_loss_time: dict[str, float] = {}
    # #2 Pas de re-entry même direction
    last_trade_signal: dict[str, str] = {}
    # #3 Max 10 trades par heure
    trades_this_hour: dict[str, list[float]] = {}

    _t_bootstrap_end = time.perf_counter()
    _send_email(
        "Système démarré",
        f"Crypto AI Terminal démarré avec succès.\n"
        f"Symboles : {symbols}\n"
        f"Intervalle : {interval}s\n"
        f"Bootstrap : {_t_bootstrap_end - _t_main_start:.1f}s",
    )

    cycle = 0
    consecutive_errors = 0
    _clean_exit = False
    shed_optional_until_cycle = 0
    # ── Boucle de rétroaction adaptative ──────────────────────────────────────
    # _adaptive_regime : régime stable (confirmé sur N cycles consécutifs)
    # _regime_votes    : fenêtre glissante des N dernières observations
    # _activity_tracker: métriques d'inactivité du capital
    _adaptive_regime: str = "unknown"
    _regime_votes: list = []  # dernières N observations de régime
    _REGIME_STABILITY = int(
        os.getenv("REGIME_STABILITY_WINDOW", "3")
    )  # cycles à confirmer
    _last_mismatch_cycle: int = 0  # cooldown REGIME_MISMATCH

    # P7 — Risk Governor + Capital Throttle + Exposure Manager
    try:
        from quant_hedge_ai.agents.risk.capital_throttle import (
            CapitalThrottle as _CTCls,
        )
        from quant_hedge_ai.agents.risk.exposure_manager import (
            DynamicExposureManager as _DEMCls,
        )
        from quant_hedge_ai.agents.risk.risk_governor import RiskGovernor as _RGCls

        _risk_governor: Any = _RGCls()
        _capital_throttle: Any = _CTCls()
        _dyn_exposure: Any = _DEMCls(real_capital)
        log.info(
            "[P7] RiskGovernor + CapitalThrottle + DynamicExposureManager initialisés"
        )
    except Exception as _p7_exc:
        log.warning("[P7] Composants indisponibles: %s", _p7_exc)
        _risk_governor = None
        _capital_throttle = None
        _dyn_exposure = None

    # P6 — Adaptive Core
    _ate: Any = _profile_bootstrap_step(
        "adaptive_threshold_engine",
        lambda: runtime.AdaptiveThresholdEngine(safe_mode=P6_SAFE_MODE),
    )
    _regime_smoother: Any = _profile_bootstrap_step(
        "regime_transition_smoother",
        lambda: runtime.RegimeTransitionSmoother(safe_mode=P6_SAFE_MODE),
    )
    _regime_tracker: Any = _profile_bootstrap_step(
        "regime_state_tracker", runtime.RegimeStateTracker
    )
    try:
        from quant_hedge_ai.agents.intelligence.activity_tracker import (
            ActivityTracker as _ActivityTrackerCls,
        )

        _activity_tracker: Any = _ActivityTrackerCls()
    except Exception:
        _activity_tracker = None

    try:
        from quant_hedge_ai.agents.intelligence.behavioral_stability_monitor import (
            BehavioralStabilityMonitor as _BSMCls,
        )

        _stability_monitor: Any = _BSMCls(
            threshold_baseline=int(os.getenv("SIGNAL_MIN_SCORE", "70"))
        )
    except Exception:
        _stability_monitor = None

    # ── Initialisation unique des composants d'observabilité ─────────────────
    try:
        from system.position_reconciler import PositionReconciler as _RecCls
        from system.state_machine import get_state_machine as _get_sm_boot

        _sm_boot = _get_sm_boot()
        # Amorcer last_successful_order_at si des positions existent déjà au boot
        if (
            hasattr(pos_manager, "get_open_positions")
            and pos_manager.get_open_positions()
        ):
            _sm_boot.update_heartbeat(
                n_signals=0,
                n_orders=1,
                exchange_ok=True,
                open_positions=len(pos_manager.get_open_positions()),
            )
        _position_reconciler = _RecCls(_get_exchange_futures(exec_engine), pos_manager)
    except Exception as _obs_boot_exc:
        log.debug("[Observability] init boot échoué: %s", _obs_boot_exc)
        _position_reconciler = None

    while True:
        cycle += 1
        cycle_completed = False
        shed_optional_work = cycle <= shed_optional_until_cycle

        if _OBS_AVAILABLE:
            try:
                heartbeat_system.beat("advisor_loop")
                module_registry.heartbeat("advisor_loop")
            except Exception:
                pass

        # ── Kill switch check ──────────────────────────────────────────────────
        if kill_switch.is_halted() or _halt_requested["value"]:
            log.critical("[main] Kill switch actif — boucle suspendue")
            _telegram(
                "Boucle suspendue par Kill Switch. Envoyer /RESUME pour reprendre."
            )
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
                # Attendre les futures avec un timeout court par future (non-bloquant).
                # Si un fetch est lent, on continue sans lui — cycle 1 fetche à la volée.
                warmup_timeout = float(os.getenv("ADVISOR_PREWARM_TIMEOUT", "12"))
                from concurrent.futures import FIRST_COMPLETED as _FC
                from concurrent.futures import wait as _fut_wait

                all_futures = list(prewarm_futures.values()) + list(
                    prewarm_mtf_futures.values()
                )
                _deadline = time.perf_counter() + warmup_timeout
                _remaining = list(all_futures)
                while _remaining and time.perf_counter() < _deadline:
                    _done, _remaining = _fut_wait(
                        _remaining,
                        timeout=min(2.0, _deadline - time.perf_counter()),
                        return_when=_FC,
                    )
                    for _f in _done:
                        try:
                            _f.result()
                        except Exception as exc:
                            log.warning("[Warmup] Prechauffage echoue: %s", exc)
                if _remaining:
                    log.info(
                        "[Warmup] %d fetch(s) incomplet(s) — cycle 1 fetche a la volee",
                        len(_remaining),
                    )
                    for _f in _remaining:
                        _f.cancel()
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

            # ── Runtime config — rechargement à chaud chaque cycle ────────────
            try:
                import json as _rtjson
                from pathlib import Path as _rtPath

                _rt_path = _rtPath("databases/runtime_config.json")
                if _rt_path.exists():
                    _rt = _rtjson.loads(_rt_path.read_text(encoding="utf-8"))
                    _RT_KEYS = {
                        "GATE_MIN_SCORE_OVERRIDE",
                        "FORCE_TEST_EXECUTION",
                        "EXEC_MAX_ORDER_USD",
                        "SIGNAL_MIN_SCORE",
                        "EO_DD_VETO",
                        "EO_DD_RECOVERY",
                        "EXCHANGE_HEARTBEAT_S",
                    }
                    for _k, _v in _rt.items():
                        if _k in _RT_KEYS:
                            os.environ[_k] = (
                                str(_v).lower() if isinstance(_v, bool) else str(_v)
                            )
            except Exception as _rt_exc:
                log.debug("[RuntimeConfig] Erreur rechargement: %s", _rt_exc)

            # ── P6 — Adaptive Core : ATE + RegimeSmoother — AVANT scoring ────
            # L'ATE calcule le delta PID (I+D) toutes les 6 cycles (anti-oscil.)
            # puis gate.set_adaptive_delta remplace l'ancien accumulation naïf.
            if _ate is not None and cycle % 6 == 0 and cycle > 1:
                try:
                    _re_raw = 0
                    if regret_engine is not None:
                        _pm_fb = _stats_dict(pos_manager.stats())
                        _closed_trades = int(_pm_fb.get("closed_trades", 0))
                        # Neutraliser le signal winrate si pas assez de trades fermés
                        # (évite que win_rate=0% au démarrage lève le threshold)
                        if _closed_trades >= 5:
                            _winrate_exec = float(_pm_fb.get("win_rate", 0.5))
                        else:
                            _winrate_exec = 0.5  # neutre — pas assez de données
                        _re_raw = regret_engine.get_threshold_delta(
                            current_regime=_adaptive_regime,
                            winrate_executed=_winrate_exec,
                        )
                    _ate_delta = _ate.update(_adaptive_regime, _re_raw)
                    gate.set_adaptive_delta(_ate_delta)
                    if _stability_monitor is not None:
                        _stability_monitor.on_threshold_delta(_ate_delta)
                    if _re_raw != 0 or _ate_delta != 0:
                        log.info(
                            "[P6/ATE] Cycle %d régime=%s raw=%+d → ate_delta=%+d",
                            cycle,
                            _adaptive_regime,
                            _re_raw,
                            _ate_delta,
                        )
                except Exception as _ate_exc:
                    log.debug("[P6/ATE] Erreur: %s", _ate_exc)

            # RegimeSmoother : avance la rampe + câblage threshold/SL vers gate
            _smoothed_sl: float | None = None
            _smoothed_tp: float | None = None
            if _regime_smoother is not None:
                try:
                    _regime_smoother.update(_adaptive_regime)
                    if _regime_smoother.in_transition:
                        _from_r = _regime_smoother._state.from_regime
                        _to_r = _adaptive_regime
                        _old_thr = gate._effective_min_score(_from_r)
                        _new_thr = gate._effective_min_score(_to_r)
                        _s_thr = _regime_smoother.smooth_int(_old_thr, _new_thr)
                        gate.set_transition_threshold(_s_thr)
                        # Factors SL/TP via configs régime
                        try:
                            from quant_hedge_ai.agents.intelligence.market_regime_classifier import (  # noqa: E501
                                MarketRegimeClassifier as _SMRC,
                            )

                            _smrc = _SMRC()
                            _old_cfg = _smrc.get_config(_from_r)
                            _new_cfg = _smrc.get_config(_to_r)
                            _smoothed_sl = _regime_smoother.smooth_float(
                                _old_cfg.sl_factor_atr, _new_cfg.sl_factor_atr
                            )
                            _smoothed_tp = _regime_smoother.smooth_float(
                                _old_cfg.tp_factor_atr, _new_cfg.tp_factor_atr
                            )
                        except Exception:
                            pass
                        log.info(
                            "[TRANSITION] %s→%s %d/%d (%.0f%%) "
                            "| thr %d→%d smoothed=%d "
                            "| SL×%.2f→%.2f smoothed=%.2f",
                            _from_r,
                            _to_r,
                            _regime_smoother._state.elapsed,
                            _regime_smoother._state.duration,
                            _regime_smoother.progress * 100,
                            _old_thr,
                            _new_thr,
                            _s_thr,
                            _old_cfg.sl_factor_atr if _smoothed_sl else 0,
                            _new_cfg.sl_factor_atr if _smoothed_sl else 0,
                            _smoothed_sl or 0,
                        )
                    else:
                        gate.set_transition_threshold(None)
                except Exception as _smth_exc:
                    log.debug("[RegimeSmoother] Erreur câblage: %s", _smth_exc)

            # ── P7 — RiskGovernor + CapitalThrottle — AVANT exécution ────────
            _rg_snapshot = None
            if _risk_governor is not None:
                try:
                    _ct_factor = (
                        _capital_throttle.update(real_capital)
                        if _capital_throttle is not None
                        else 1.0
                    )
                    _rg_snapshot = _risk_governor.update(
                        cycle=cycle,
                        drawdown_pct=(
                            _capital_throttle.drawdown_pct if _capital_throttle else 0.0
                        ),
                        consecutive_losses=_consecutive_losses.get("value", 0),
                        atr_current=float(
                            # ATR moyen du dernier cycle (stocké dans _atr_last)
                            getattr(main, "_atr_last", 0.0)
                            if False
                            else 0.0
                        ),
                        cycle_pnl_pct=float(
                            (_pm_fb or {}).get("last_pnl_pct", 0.0)
                            if "_pm_fb" in dir()
                            else 0.0
                        ),
                        regime=_adaptive_regime,
                    )
                    # Appliquer le delta threshold du governor sur le gate
                    if _rg_snapshot.threshold_delta != 0:
                        gate.set_governor_delta(_rg_snapshot.threshold_delta)
                    else:
                        gate.set_governor_delta(0)
                    if _rg_snapshot.state != "normal":
                        log.info(
                            "[P7/RiskGov] état=%s size×%.2f thr%+d trades=%s vol_em=%s",
                            _rg_snapshot.state,
                            _rg_snapshot.size_multiplier,
                            _rg_snapshot.threshold_delta,
                            _rg_snapshot.allow_new_trades,
                            _rg_snapshot.vol_emergency,
                        )
                except Exception as _rg_exc:
                    log.debug("[P7/RiskGov] Erreur: %s", _rg_exc)

            results: list[AnalysisResult] = []
            for sym in symbols:
                r = analyze_symbol(
                    sym,
                    scanners,
                    engine,
                    gate,
                    advisor,
                    shadow,
                    watchdog,
                    memory,
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
                    portfolio_brain=portfolio_brain,
                    capital_engine=capital_engine,
                    mistake_memory=(
                        None
                        if advisor_only and defer_optional_intel
                        else _get_mistake_memory()
                    ),
                    executive_override=executive_override,
                    black_box=black_box,
                    regret_engine=(
                        None
                        if advisor_only and defer_optional_intel
                        else _get_regret_engine()
                    ),
                    threat_radar=(
                        threat_radar
                        if (
                            not shed_optional_work
                            and (
                                threat_radar_every <= 1
                                or cycle % threat_radar_every == 0
                            )
                        )
                        else None
                    ),
                    meta_learner=meta_learner,
                    runtime=runtime,
                    sl_factor_override=_smoothed_sl,
                    tp_factor_override=_smoothed_tp,
                )
                results.append(r)
                # ── Exécution réelle/paper ─────────────────────────────────────
                r["futures_result"] = None
                # Taille effective : depuis CAE si disponible, sinon order_size global
                allocation = r.get("allocation")
                effective_size = (
                    allocation.size_usd
                    if allocation and allocation.size_usd > 0
                    else r.get("order_size", order_size)
                )

                # ── P7 — Appliquer RiskGovernor + CapitalThrottle ────────────
                if _rg_snapshot is not None:
                    _rg_size_mul = _rg_snapshot.size_multiplier * (
                        _ct_factor if "_ct_factor" in dir() else 1.0
                    )
                    effective_size = effective_size * _rg_size_mul
                    if (
                        not _rg_snapshot.allow_new_trades
                        and r["signal"].signal != "HOLD"
                    ):
                        r["futures_result"] = {
                            "mode": "risk_governor_blocked",
                            "reason": f"état={_rg_snapshot.state}"
                            + (" vol_emergency" if _rg_snapshot.vol_emergency else ""),
                        }
                        r["trade_allowed"] = False
                        log.info(
                            "[P7] Trade bloqué %s — %s",
                            sym,
                            r["futures_result"]["reason"],
                        )

                # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
                # Vérification AVANT exécution
                protection_blocks = []
                current_time = time.time()
                current_signal = r["signal"].signal

                # #1 Cooldown après perte (5 min = 300s)
                if sym in last_loss_time:
                    time_since_loss = current_time - last_loss_time[sym]
                    if time_since_loss < 300:
                        protection_blocks.append(
                            f"cooldown_loss({time_since_loss:.0f}s)"
                        )

                # #2 Pas de re-entry même direction
                if sym in last_trade_signal:
                    if last_trade_signal[sym] == current_signal:
                        protection_blocks.append(f"same_direction({current_signal})")

                # #3 Max 10 trades par heure
                now = current_time
                hour_ago = now - 3600
                if sym not in trades_this_hour:
                    trades_this_hour[sym] = []
                trades_this_hour[sym] = [
                    t for t in trades_this_hour[sym] if t > hour_ago
                ]
                if len(trades_this_hour[sym]) >= 10:
                    protection_blocks.append(
                        f"max_trades_1h({len(trades_this_hour[sym])})"
                    )

                if protection_blocks:
                    log.info(
                        "[PROTECTION] %s BLOQUE par: %s",
                        sym,
                        " | ".join(protection_blocks),
                    )
                    if r["signal"].actionable:
                        _existing = r.get("blockers", "")
                        _prot_str = "protection(" + "|".join(protection_blocks) + ")"
                        r["blockers"] = (
                            (_existing + ", " + _prot_str) if _existing else _prot_str
                        )

                # ── Test mode check: allow execution even if signal.actionable=False if gate override ──
                gate_override_active = (
                    r.get("signal_to_execute") is not None
                    and r.get("signal_to_execute") != r["signal"].signal
                )

                if (
                    (r["signal"].actionable or gate_override_active)
                    and r.get("trade_allowed", r["gate"].allowed)
                    and not advisor_only
                    and not kill_switch.is_safe_mode()
                    and not protection_blocks  # ← CRITICAL: skip si protections activées
                ):
                    try:
                        # Use signal_to_execute if available (test mode override), else original signal
                        signal_action = r.get("signal_to_execute", r["signal"].signal)
                        _ref_price = float(r.get("prix", 0.0))
                        _side = "buy" if signal_action in ("buy", "long") else "sell"
                        _validated = True
                        _sim_fill_dict: dict = {}

                        # 0. Hard limits — filet de sécurité absolu (P5.4)
                        try:
                            from risk_limits import HardLimitBreached, check_hard_limits

                            _open_count = (
                                len(pos_manager.get_open_positions())
                                if hasattr(pos_manager, "get_open_positions")
                                else 0
                            )
                            check_hard_limits(
                                order_size_usd=effective_size,
                                capital_usd=max(real_capital, 1.0),
                                current_drawdown_pct=(
                                    float(r.get("gate", {}).get("drawdown_pct", 0.0))
                                    if hasattr(r.get("gate"), "get")
                                    else 0.0
                                ),
                                open_positions=_open_count,
                                consecutive_losses=int(
                                    _consecutive_losses.get("value", 0)
                                ),
                            )
                        except HardLimitBreached as _hlb:
                            log.warning("[HARD_LIMIT] %s %s", sym, _hlb)
                            r["futures_result"] = {
                                "mode": "hard_limit_breached",
                                "reason": str(_hlb),
                            }
                            _validated = False
                        except Exception:
                            pass  # hard limits non disponibles — non bloquant

                        # A. OrderValidator — validate + adjust qty before exchange
                        # Only apply Binance rules when actually on a Binance exchange
                        _is_binance_exchange = (
                            "binance" in os.getenv("ACTIVE_EXCHANGE", "").lower()
                        )
                        if (
                            _EXEC_CONSTRAINTS_AVAILABLE
                            and _order_validator is not None
                            and _is_binance_exchange
                        ):
                            try:
                                _sym_clean = sym.replace("/", "")
                                _sym_info = (
                                    _binance_rules_mod.BINANCE_FUTURES_SYMBOLS.get(
                                        _sym_clean
                                    )
                                )
                                if _sym_info is not None and _ref_price > 0:
                                    _qty_base = effective_size / _ref_price
                                    _validation = _order_validator.validate(
                                        _sym_info, _qty_base, _ref_price, "market"
                                    )
                                    if not _validation.is_valid:
                                        log.warning(
                                            "[VALIDATION] %s rejeté: %s",
                                            sym,
                                            _validation.rejection_reason,
                                        )
                                        r["futures_result"] = {
                                            "mode": "validation_rejected",
                                            "reason": _validation.rejection_reason,
                                        }
                                        _validated = False
                                    elif _validation.size_was_adjusted:
                                        effective_size = (
                                            _validation.adjusted_size * _ref_price
                                        )
                                        log.info(
                                            "[VALIDATION] %s qty ajustée → %.4f (%.2f USD)",
                                            sym,
                                            _validation.adjusted_size,
                                            effective_size,
                                        )
                            except Exception as _ve:
                                log.debug("[VALIDATION] erreur non-bloquante: %s", _ve)

                        # B. RateLimiter — wait before sending to exchange
                        if (
                            _validated
                            and _EXEC_CONSTRAINTS_AVAILABLE
                            and _rate_limiter is not None
                        ):
                            _rl_ok = _rate_limiter.wait_and_acquire(
                                "POST /fapi/v1/order", timeout_s=5.0
                            )
                            if not _rl_ok:
                                log.warning(
                                    "[RATE_LIMIT] %s timeout — ordre annulé", sym
                                )
                                _validated = False

                        # C. ExecutionSimulator — fill réaliste pour audit pré-envoi
                        if (
                            _validated
                            and _EXEC_CONSTRAINTS_AVAILABLE
                            and _exec_sim is not None
                            and _ref_price > 0
                        ):
                            try:
                                _qty_base = max(0.001, effective_size / _ref_price)
                                _intent = _OrderIntent(
                                    symbol=sym.replace("/", ""),
                                    side=_side,
                                    size=_qty_base,
                                    order_type="market",
                                    signal_price=_ref_price,
                                    timestamp=time.time(),
                                )
                                _snapshot = _MarketSnapshot(
                                    symbol=sym.replace("/", ""),
                                    price=_ref_price,
                                    volume_24h=float(
                                        r.get("features", {}).get(
                                            "volume_24h", 1_000_000.0
                                        )
                                    ),
                                    volatility_pct=float(
                                        r.get("features", {}).get("atr_ratio", 1.0)
                                    ),
                                    timestamp=time.time(),
                                )
                                _sim = _exec_sim.execute(_intent, _snapshot)
                                _sim_fill_dict = {
                                    "fill_price": round(_sim.fill_price, 4),
                                    "slippage_bps": round(_sim.slippage_bps, 2),
                                    "latency_ms": round(_sim.latency_ms, 1),
                                    "fee_usd": round(_sim.fee_usd, 4),
                                    "is_partial": _sim.is_partial,
                                    "is_rejected": _sim.is_rejected,
                                }
                                r["simulated_fill"] = _sim_fill_dict
                            except Exception as _se:
                                log.debug("[SIM] erreur non-bloquante: %s", _se)

                        # D. Audit log — une ligne JSONL par ordre tenté
                        if _validated and _EXEC_CONSTRAINTS_AVAILABLE:
                            try:
                                _audit = {
                                    "ts": time.time(),
                                    "symbol": sym,
                                    "side": _side,
                                    "intent": {
                                        "size_usd": round(effective_size, 4),
                                        "price": _ref_price,
                                    },
                                    "validated": True,
                                    "adjusted": {
                                        "size_usd": round(effective_size, 4),
                                        "price": _ref_price,
                                    },
                                    "simulated_fill": _sim_fill_dict,
                                }
                                with open(
                                    "logs/execution_audit/audit.jsonl",
                                    "a",
                                    encoding="utf-8",
                                ) as _af:
                                    _af.write(_json.dumps(_audit) + "\n")
                            except Exception:
                                pass

                        if _validated:
                            if exec_engine.has_futures_demo():
                                fut = _stats_dict(
                                    exec_engine.create_futures_order(
                                        sym, signal_action, effective_size
                                    )
                                )
                                exec_label = "FUTURES DEMO"
                            else:
                                fut = _stats_dict(
                                    exec_engine.create_order(
                                        sym, signal_action, effective_size
                                    )
                                )
                                exec_label = "EXECUTION"
                            fut_mode = str(fut.get("mode", ""))
                            fut_id = str(fut.get("id", ""))
                            r["futures_result"] = fut
                            log.info(
                                "[FLOW] %s EXECUTION → %s $%.2f",
                                sym,
                                exec_label,
                                effective_size,
                            )
                            log.info(
                                "[%s] %s %s $%.2f → mode=%s id=%s",
                                exec_label,
                                signal_action,
                                sym,
                                effective_size,
                                fut_mode,
                                fut_id,
                            )
                            _pos_registered = _register_position_from_execution(
                                fut,
                                r,
                                sym,
                                signal_action,
                                effective_size,
                            )
                            if _pos_registered:
                                log.info(
                                    "[FLOW] %s POSITION → registered mode=%s",
                                    sym,
                                    fut_mode,
                                )
                                # ── PROTECTIONS: Enregistre le trade pour tracking ──
                                last_trade_signal[sym] = signal_action
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

                # Vérification TP/SL avec le prix spot du cycle courant.
                # Toujours actif : en futures_demo sur Kraken testnet SOL/XRP, les prix testnet
                # suivent le spot réel — le _watch_loop retourne 503 trop souvent pour être fiable.
                try:
                    prix_live = float(r.get("prix", 0.0))
                    if prix_live > 0:
                        pos_manager.update_price_and_check(sym, prix_live)
                except Exception as _tpsl_exc:
                    log.warning("[TP/SL] check échoué pour %s: %s", sym, _tpsl_exc)

                # Métriques par symbole
                if _OBS_AVAILABLE:
                    try:
                        metrics_bus.record(
                            "advisor_loop", "signal_score", float(r["signal"].score)
                        )
                        if r["signal"].actionable:
                            metrics_bus.increment("advisor_loop", "signals_actionable")
                        if r.get("trade_allowed"):
                            metrics_bus.increment("advisor_loop", "trades_approved")
                        if r.get("futures_result") and r["futures_result"].get(
                            "mode"
                        ) not in ("futures_failed", "live_failed", None):
                            metrics_bus.increment("advisor_loop", "trades_executed")
                    except Exception:
                        pass

                # Alerte immédiate si signal actionable (sauf si safe mode)
                if r["signal"].actionable and not kill_switch.is_safe_mode():
                    log.info(
                        "SIGNAL ACTIONABLE: %s score=%d %s",
                        sym,
                        r["signal"].score,
                        r["signal"].signal,
                    )
                    _telegram(_build_alert(r, cycle))
                elif r["signal"].actionable and kill_switch.is_safe_mode():
                    log.info(
                        "SIGNAL ACTIONABLE (safe mode — non envoye): %s score=%d",
                        sym,
                        r["signal"].score,
                    )

            # ── Post-cycle: régime dominant + métriques d'activité ───────────
            # Régime : mise à jour seulement si N cycles consécutifs identiques
            # (évite l'oscillation TREND→SIDEWAYS→TREND en 15 min).
            if results:
                _obs = results[0].get("regime", _adaptive_regime)
                # P6 — RegimeStateTracker : confidence + entropy (post-scoring)
                if _regime_tracker is not None:
                    try:
                        _rpkt = _regime_tracker.update(_obs)
                        if cycle % 12 == 0:
                            log.info(
                                "[P6/RegimeTracker] %s conf=%.0f%% entropy=%.2f dur=%dc",
                                _rpkt.regime,
                                _rpkt.confidence * 100,
                                _rpkt.entropy,
                                _rpkt.duration_cycles,
                            )
                    except Exception:
                        pass
                _regime_votes.append(_obs)
                if len(_regime_votes) > _REGIME_STABILITY:
                    _regime_votes = _regime_votes[-_REGIME_STABILITY:]
                if (
                    len(_regime_votes) == _REGIME_STABILITY
                    and len(set(_regime_votes)) == 1
                    and _regime_votes[0] != _adaptive_regime
                ):
                    _new_regime = _regime_votes[0]
                    log.info(
                        "[RegimeStability] Transition confirmée: %s → %s (%d cycles)",
                        _adaptive_regime,
                        _new_regime,
                        _REGIME_STABILITY,
                    )
                    _telegram_behavior(
                        f"🔄 TRANSITION RÉGIME — {_adaptive_regime} → {_new_regime}\n"
                        f"Confirmée sur {_REGIME_STABILITY} cycles consécutifs"
                    )
                    _adaptive_regime = _new_regime
            if _activity_tracker is not None:
                try:
                    _open_pos_count = len(pos_manager.get_open())
                    _any_refused = any(
                        r.get("signal") is not None
                        and r["signal"].actionable
                        and not r.get("trade_allowed", True)
                        for r in results
                    )
                    _any_executed = any(
                        r.get("futures_result") is not None
                        and r["futures_result"].get("mode")
                        not in (None, "futures_failed", "live_failed")
                        for r in results
                    )
                    _activity_tracker.record_cycle(
                        has_position=_open_pos_count > 0,
                        signal_refused=_any_refused,
                        signal_executed=_any_executed,
                    )
                    if cycle % 12 == 0:
                        log.info(_activity_tracker.summary())
                    # P6 — REGIME_MISMATCH: capital gelé → baisser threshold (désactivé en safe mode)
                    _mismatch_cooldown = int(
                        os.getenv("REGIME_MISMATCH_COOLDOWN", "15")
                    )
                    if (
                        not P6_SAFE_MODE
                        and regret_engine is not None
                        and cycle % 3 == 0
                        and (cycle - _last_mismatch_cycle) >= _mismatch_cooldown
                        and (
                            awareness_engine is None
                            or awareness_engine.is_safe_to_trade()
                        )
                    ):
                        _at = _activity_tracker.metrics()
                        if _at.cycles_since_last_trade > 30:
                            gate.apply_regret_delta(-1)
                            _regime_votes.clear()  # force recalcul classifieur
                            _last_mismatch_cycle = cycle
                            if _stability_monitor is not None:
                                try:
                                    _stability_monitor.on_mismatch()
                                except Exception:
                                    pass
                            _mm_msg = (
                                f"⚙️ REGIME_MISMATCH — {_at.cycles_since_last_trade} cycles sans trade"
                                f" ({_at.inactivity_ratio:.0%} inactif)\n"
                                f"→ threshold -1 | reset classifieur"
                            )
                            log.warning(
                                "[ActivityTracker] REGIME_MISMATCH: %d cycles sans trade "
                                "(inactivite=%.0f%%) → threshold -1, regime reset",
                                _at.cycles_since_last_trade,
                                _at.inactivity_ratio * 100,
                            )
                            _telegram_behavior(_mm_msg)
                except Exception:
                    pass

            if _stability_monitor is not None:
                try:
                    _eff_threshold = gate.min_signal_score + getattr(
                        gate, "_regret_delta", 0
                    )
                    _traded_sym = next(
                        (
                            r.get("symbol", "")
                            for r in results
                            if r.get("futures_result") is not None
                            and r["futures_result"].get("mode")
                            not in (None, "futures_failed", "live_failed")
                        ),
                        "",
                    )
                    _stability_monitor.record_cycle(
                        regime=_adaptive_regime,
                        threshold=_eff_threshold,
                        strategy_name=_traded_sym,
                        trade_executed=bool(_traded_sym),
                    )
                    # V2 — scores acceptés (signaux ayant passé le gate)
                    for _r in results:
                        if _r.get("trade_allowed") and _r.get("signal") is not None:
                            try:
                                _stability_monitor.on_score_accepted(
                                    int(_r["signal"].score)
                                )
                            except Exception:
                                pass
                    _bsm_violations = _stability_monitor.check_invariants()
                    if _bsm_violations:
                        for _viol in _bsm_violations:
                            log.warning("[BSM] Invariante violee: %s", _viol)
                        # Router violation critique vers canal comportemental
                        _bsm_state = _stability_monitor.behavioral_state().value
                        if _bsm_state in ("oscillating", "degraded"):
                            _telegram_behavior(
                                f"⚠️ BSM ALERTE — état={_bsm_state}\n"
                                + "\n".join(f"  • {v}" for v in _bsm_violations)
                            )
                    if cycle % 12 == 0:
                        log.info("[BSM] %s", _stability_monitor.summary_line())
                    # V3 — log [BEHAVIOR] toutes les 50 cycles
                    if cycle % 50 == 0:
                        _bh_line = _stability_monitor.behavior_log()
                        log.info(_bh_line)
                        _telegram_behavior(f"📊 {_bh_line}")
                except Exception:
                    pass

            # ── Rapport timing bootstrap vs cycle 1 ──────────────────────────
            if cycle == 1:
                _t_cycle_1_end = time.perf_counter()
                t_bootstrap_s = _t_bootstrap_end - _t_main_start
                t_warmup_s = (
                    (_t_warmup_end - _t_warmup_start)
                    if (_t_warmup_start and _t_warmup_end)
                    else 0.0
                )
                t_cycle_1_s = _t_cycle_1_end - _t_cycle_start
                t_total_s = _t_cycle_1_end - _t_main_start
                # Session primer: collect elapsed and estimate cycle-1 gain.
                t_primer_s = 0.0
                if _primer_future is not None:
                    try:
                        t_primer_s = float(_primer_future.result(timeout=0))
                    except Exception:
                        t_primer_s = (
                            (time.perf_counter() - _t_primer_start)
                            if _t_primer_start
                            else 0.0
                        )
                    finally:
                        if _primer_executor is not None:
                            _primer_executor.shutdown(wait=False)
                log.info(
                    "[Timing] Bootstrap=%.1fs | Primer=%.1fs | Warmup=%.1fs"
                    " | Cycle1=%.1fs | Total=%.1fs | Cache_1h=%s",
                    t_bootstrap_s,
                    t_primer_s,
                    t_warmup_s,
                    t_cycle_1_s,
                    t_total_s,
                    "CHAUD" if prewarm_1h_enabled else "FROID",
                )
                if bootstrap_profile:
                    bootstrap_detail = " | ".join(
                        f"{name}={duration:.2f}s"
                        for name, duration in sorted(
                            bootstrap_profile, key=lambda item: item[1], reverse=True
                        )
                    )
                    log.info("[Timing] Bootstrap detail: %s", bootstrap_detail)
                if ADVISOR_SESSION_PRIMER and t_primer_s > 0:
                    log.info(
                        "[Timing] Gain SessionPrimer: exchange_init + load_markets (%.1fs)"
                        " effectués en parallèle du bootstrap — ~%.0fms économisés sur le cycle 1",
                        t_primer_s,
                        t_primer_s * 1000,
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
                try:
                    _eff_score = gate._effective_min_score(_adaptive_regime)
                    msg = _build_summary(results, cycle, min_score=_eff_score)
                    # Indiquer safe mode dans le rapport
                    if kill_switch.is_safe_mode():
                        msg += "\n\n[SAFE MODE] Alertes actions suspendues."
                    # Etat exchange monitor
                    ex = _stats_dict(exchange_monitor.snapshot())
                    if not ex.get("healthy", True):
                        msg += (
                            f"\n\nEXCHANGE HORS LIGNE — {ex.get('consecutive_failures', 0)} echecs\n"
                            f"Derniere erreur: {ex.get('last_error', '?')}"
                        )
                    else:
                        msg += f"\n\nExchange: OK ({_to_float(ex.get('last_latency_ms', 0)):.0f}ms | uptime {_to_float(ex.get('uptime_pct', 0)):.1f}%)"
                    # Stats positions ouvertes
                    pm_stats = _stats_dict(pos_manager.stats())
                    if (
                        pm_stats.get("open_count", 0) > 0
                        or pm_stats.get("closed_count", 0) > 0
                    ):
                        msg += (
                            f"\n\nPOSITIONS:\n"
                            f"  Ouvertes:   {pm_stats.get('open_count', 0)} | PnL ouvert: {_to_float(pm_stats.get('open_pnl_usd', 0)):+.2f}$\n"
                            f"  Fermees:    {pm_stats.get('closed_count', 0)} | PnL realise: {_to_float(pm_stats.get('total_pnl_usd', 0)):+.2f}$\n"
                            f"  Win rate:   {_to_float(pm_stats.get('win_rate', 0.0)):.0%}"
                        )
                        # Détail positions ouvertes
                        for snap in _snapshot_list(pos_manager.snapshot()):
                            dist = snap.get("liq_dist_pct", 100)
                            liq_warn = f" LIQ RISK {dist:.0f}%!" if dist < 10 else ""
                            msg += (
                                f"\n  {snap.get('side', '?').upper()} {snap.get('symbol', '?')} "
                                f"entry=${_to_float(snap.get('entry', 0)):.0f} | PnL {_to_float(snap.get('pnl_usd', 0)):+.1f}$ "
                                f"({_to_float(snap.get('pnl_pct', 0)):+.1f}%){liq_warn}"
                            )

                    # Ajouter stats shadow si des trades ont été simulés
                    shadow_stats = _stats_dict(shadow.stats())
                    if shadow_stats.get("n_trades", 0) > 0:
                        msg += (
                            f"\n\nSHADOW STATS ({shadow_stats.get('n_trades', 0)} trades simules):\n"
                            f"  Slippage moy: {_to_float(shadow_stats.get('avg_slippage_pct', 0)):.3f}%\n"
                            f"  Latence moy:  {_to_float(shadow_stats.get('avg_latency_ms', 0)):.1f}ms\n"
                            f"  Par regime:   {shadow_stats.get('by_regime', '?')}"
                        )

                    # Executive Override — état du commandement
                    eo_snap = _stats_dict(executive_override.metrics_snapshot())
                    eo_lvl = eo_snap.get("level", "CLEAR")
                    if eo_lvl != "CLEAR":
                        msg += (
                            f"\n\nCOMMANDEMENT OVERRIDE: {eo_lvl}"
                            f"\n  DD: -{_to_float(eo_snap.get('drawdown_pct', 0)):.1f}%"
                            f" | Daily: -{_to_float(eo_snap.get('daily_loss_pct', 0)):.1f}%"
                            f" | Streak: {eo_snap.get('loss_streak', 0)}"
                            f" | Taille: x{_to_float(eo_snap.get('size_factor', 1.0)):.0%}"
                        )
                    else:
                        msg += "\n\nCOMMANDEMENT: CLEAR | Taille x100%"

                    # Mistake Memory — dernières erreurs + règles actives
                    mm = _get_mistake_memory()
                    mm_stats = _stats_dict(mm.stats())
                    if mm_stats.get("total", 0) > 0:
                        last_errors = cast(list[str], mm.explain_last_mistakes(3))
                        rules = cast(list[str], mm.active_rules_summary())
                        msg += (
                            f"\n\nMISTAKE MEMORY ({mm_stats.get('total', 0)} trades | "
                            f"erreur rate: {_to_float(mm_stats.get('error_rate', 0)):.0%} | "
                            f"{mm_stats.get('rules_active', 0)} règles actives)"
                        )
                        for err in last_errors:
                            msg += f"\n  {err}"
                        for rule in rules[:3]:
                            msg += f"\n  REGLE: {rule}"

                    # Portfolio Brain — santé globale du portefeuille
                    pb_health = _stats_dict(
                        portfolio_brain.portfolio_health(pos_manager.get_open())
                    )
                    msg += (
                        f"\n\nPORTFOLIO BRAIN:"
                        f"\n  Exposition: {_to_float(pb_health.get('total_exposure_pct', 0)):.1f}%"
                        f" | Libre: ${_to_float(pb_health.get('free_capital', 0)):.0f}"
                        f"\n  Positions: {pb_health.get('n_positions', 0)}"
                        f" | Corr risk: {_to_float(pb_health.get('correlation_risk', 0)):.1f}%"
                        f"\n  PnL ouvert: {_to_float(pb_health.get('open_pnl_usd', 0)):+.2f}$"
                    )

                    # AI Chief Officer — briefing de synthese
                    awareness_current = (
                        awareness_engine.evaluate() if awareness_engine else None
                    )
                    coo_brief = _get_chief_officer().briefing(
                        cycle=cycle,
                        symbols=symbols,
                        results=results,
                        pos_manager=pos_manager,
                        awareness_state=awareness_current,
                        override=executive_override,
                        regret_engine=regret_engine,
                        mistake_memory=mistake_memory,
                        ranker=ranker,
                        meta_engine=meta_engine,
                        black_box=black_box,
                        activity_tracker=_activity_tracker,
                        stability_monitor=_stability_monitor,
                    )

                    # Alertes probation stratégies (une seule fois par seuil)
                    try:
                        for _prob_msg in ranker.check_probation_alerts():
                            _telegram(f"PROBATION STRATEGIE\n{_prob_msg}")
                    except Exception:
                        pass
                    if coo_brief:
                        _telegram(coo_brief)

                    # Meta-Strategy + Ranker — personnalité active + top stratégies
                    current_personality = meta_engine.current_personality()
                    if current_personality is not None:
                        p = current_personality
                        msg += (
                            f"\n\nMETA-STRATEGY: {p.name}"
                            f"\n  Taille: x{p.order_size_factor:.1f} | "
                            f"TP:{p.tp_pct:.1%} SL:{p.sl_pct:.1%}"
                        )
                    top3 = cast(list[JSONDict], ranker.leaderboard(3))
                    if top3:
                        msg += "\n\nTOP STRATEGIES:"
                        for i, s in enumerate(top3, 1):
                            msg += (
                                f"\n  #{i} {s.get('name', '?')}/{s.get('regime', '?')} "
                                f"score={_to_float(s.get('composite', 0)):.0f} wr={_to_float(s.get('win_rate', 0.0)):.0%} "
                                f"sharpe={_to_float(s.get('avg_sharpe', 0.0)):.2f}"
                            )
                    _telegram(msg)
                    log.info(
                        "[RAPPORT] Telegram envoye — cycle %d (%d symboles)",
                        cycle,
                        len(results),
                    )
                except Exception as report_exc:
                    log.warning("[RAPPORT] Erreur construction rapport: %s", report_exc)

            # ── Snapshot live — écrit databases/live_snapshot.json chaque cycle ──
            try:
                from pathlib import Path as _Path

                from quant_hedge_ai.dashboard.live_snapshot import (
                    write_snapshot as _write_snap,
                )

                _cycle_elapsed_ms = round(
                    (time.perf_counter() - _t_cycle_start) * 1000, 1
                )

                # Refusal breakdown — compte combien de fois chaque couche a bloqué
                _refusal_tally: dict[str, int] = {}
                _regime_tally: dict[str, int] = {}
                _n_actionable = 0
                _n_traded = 0
                for _r in results:
                    _sig = _r["signal"]
                    _regime_tally[_sig.regime] = _regime_tally.get(_sig.regime, 0) + 1
                    if _sig.actionable:
                        _n_actionable += 1
                    if _r.get("trade_allowed"):
                        _n_traded += 1
                    if not _r.get("trade_allowed") and _sig.actionable:
                        for _layer in [
                            ("gate", not _r["gate"].allowed),
                            (
                                "conviction",
                                not (getattr(_r.get("conviction"), "ok", True)),
                            ),
                            ("meta", not _r.get("meta_allowed", True)),
                            (
                                "no_trade",
                                not (
                                    getattr(_r.get("no_trade_verdict"), "allow", True)
                                ),
                            ),
                            (
                                "awareness",
                                not (getattr(_r.get("awareness_state"), "ok", True)),
                            ),
                            (
                                "portfolio",
                                not (getattr(_r.get("pb_verdict"), "allow", True)),
                            ),
                            (
                                "exec_override",
                                not (getattr(_r.get("eo_verdict"), "allow", True)),
                            ),
                            (
                                "threat_radar",
                                _r.get("radar_report")
                                and not getattr(_r.get("radar_report"), "safe", True),
                            ),
                        ]:
                            if _layer[1]:
                                _refusal_tally[_layer[0]] = (
                                    _refusal_tally.get(_layer[0], 0) + 1
                                )

                _snap_data = {
                    "ts": time.time(),
                    "cycle": cycle,
                    "capital": real_capital,
                    "safe_mode": kill_switch.is_safe_mode(),
                    "cycle_duration_ms": _cycle_elapsed_ms,
                    "n_symbols": len(results),
                    "n_actionable": _n_actionable,
                    "n_traded": _n_traded,
                    "n_refused": _n_actionable - _n_traded,
                    "refusal_breakdown": _refusal_tally,
                    "regime_distribution": _regime_tally,
                    "exchange": exchange_monitor.snapshot(),
                    "positions": _snapshot_list(pos_manager.snapshot()),
                    "symbols": [
                        {
                            "symbol": r["symbol"],
                            "prix": r.get("prix", 0.0),
                            "signal": r["signal"].signal,
                            "score": r["signal"].score,
                            "actionable": r["signal"].actionable,
                            "regime": r["signal"].regime,
                            "confirmed": r["signal"].confirmed,
                            "gate_allowed": r["gate"].allowed,
                            "gate_reason": getattr(r["gate"], "reason", ""),
                            "trade_allowed": r.get("trade_allowed"),
                            "conviction_level": (
                                r["conviction"].level.value
                                if r.get("conviction")
                                else None
                            ),
                            "conviction_score": (
                                r["conviction"].score if r.get("conviction") else None
                            ),
                            "personality": (
                                r["personality"].name if r.get("personality") else None
                            ),
                            "signal_to_execute": r.get("signal_to_execute"),
                            "futures_result": r.get("futures_result"),
                            # ── Indicateurs techniques enrichis ──────────────
                            "rsi": r.get("features", {}).get("rsi"),
                            "atr_ratio": r.get("features", {}).get("atr_ratio"),
                            "bb_pct": r.get("features", {}).get("bb_pct"),
                            "macd_bullish": r.get("features", {}).get("macd_bullish"),
                            "ema_bullish": r.get("features", {}).get("ema_bullish"),
                            "bb_squeeze": r.get("features", {}).get("bb_squeeze"),
                            "vwap_dist": r.get("features", {}).get("vwap_dist"),
                            "n_candles_1h": r.get("n_1h", 0),
                        }
                        for r in results
                    ],
                }
                _write_snap(_snap_data, _Path("databases/live_snapshot.json"))

                # ── JSONL persistence — une ligne par cycle ──────────────────
                import datetime as _dt_mod
                import json as _json_mod

                _jsonl_path = _Path("databases/cycle_data.jsonl")
                try:
                    if (
                        _jsonl_path.exists()
                        and _jsonl_path.stat().st_size > 50 * 1024 * 1024
                    ):
                        _archive = (
                            _jsonl_path.parent
                            / f"cycle_data.{_dt_mod.date.today().strftime('%Y%m%d')}.jsonl"
                        )
                        _jsonl_path.rename(_archive)
                        log.info("[CycleData] Rotation → %s", _archive.name)
                    with _jsonl_path.open("a", encoding="utf-8") as _jf:
                        _jf.write(_json_mod.dumps(_snap_data, default=str) + "\n")
                except Exception as _jl_exc:
                    log.debug("[CycleData] Erreur écriture JSONL: %s", _jl_exc)

                # ── SystemStateMachine heartbeat ─────────────────────────────
                try:
                    from system.state_machine import get_state_machine as _get_sm

                    _ex_ok = bool(exchange_monitor.snapshot().get("uptime_pct", 0) > 0)
                    _open_cnt = (
                        len(pos_manager.get_open_positions())
                        if hasattr(pos_manager, "get_open_positions")
                        else 0
                    )
                    _sm_alerts = _get_sm().update_heartbeat(
                        n_signals=_n_actionable,
                        n_orders=_n_traded,
                        exchange_ok=_ex_ok,
                        open_positions=_open_cnt,
                    )
                    for _alert_key, _alert_msg in _sm_alerts.items():
                        log.warning("[SystemState] %s: %s", _alert_key, _alert_msg)
                        if _alert_key == "STALL":
                            _telegram(
                                f"[ALERTE] Pipeline execution bloque\n{_alert_msg}"
                            )
                except Exception as _sm_exc:
                    log.debug("[SystemState] heartbeat échoué: %s", _sm_exc)

                # ── Position Reconciliation (toutes les heures) ───────────────
                try:
                    if (
                        _position_reconciler is not None
                        and _position_reconciler.should_reconcile()
                    ):
                        _rec_report = _position_reconciler.reconcile()
                        if _rec_report.has_drift:
                            _has_ghost = bool(_rec_report.ghost_positions)
                            _log_fn = log.critical if _has_ghost else log.warning
                            _log_fn("[Reconciler] DRIFT: %s", _rec_report.summary())
                            if _has_ghost:
                                _telegram(
                                    f"[ALERTE] Reconciliation positions\n{_rec_report.summary()}"
                                )
                except Exception as _rec_exc:
                    log.debug("[Reconciler] erreur non-bloquante: %s", _rec_exc)

            except Exception as _snap_exc:
                log.debug("[LiveSnapshot] Erreur: %s", _snap_exc)

            # Watchdog fin de cycle
            watchdog.end_cycle(cycle)
            cycle_completed = True

            # ── Heartbeat Telegram compact (toutes les N cycles ≈ 15 min) ────
            _hb_every = int(os.getenv("HEARTBEAT_CYCLES", "3"))
            if cycle % _hb_every == 0:
                try:
                    import resource as _res

                    _ram_mb = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss // 1024
                except Exception:
                    _ram_mb = 0
                _hb_regime = _adaptive_regime or "?"
                _hb_state = "OK"
                if awareness_engine is not None:
                    try:
                        _hb_state = awareness_engine.evaluate().level.name
                    except Exception:
                        pass
                _hb_capital = real_capital
                _hb_pos = (
                    len(pos_manager.get_open_positions())
                    if hasattr(pos_manager, "get_open_positions")
                    else 0
                )
                _hb_msg = (
                    f"[ALIVE] Cycle {cycle}\n"
                    f"Regime: {_hb_regime} | State: {_hb_state}\n"
                    f"Capital: ${_hb_capital:,.0f} | Pos: {_hb_pos}\n"
                    f"RAM: {_ram_mb}MB"
                )
                _telegram(_hb_msg)
                log.info("[Heartbeat] %s", _hb_msg.replace("\n", " | "))

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
            _clean_exit = True
            break
        except Exception as exc:
            consecutive_errors += 1
            log.error("Erreur cycle %d: %s", cycle, exc, exc_info=True)
            if _OBS_AVAILABLE:
                try:
                    sev = (
                        ErrorSeverity.CRITICAL
                        if consecutive_errors >= 3
                        else ErrorSeverity.HIGH
                    )
                    error_bus.emit(
                        module="advisor_loop",
                        error=exc,
                        category=ErrorCategory.SYSTEM,
                        severity=sev,
                        context={
                            "cycle": cycle,
                            "consecutive_errors": consecutive_errors,
                        },
                    )
                    module_registry.report_error("advisor_loop", str(exc))
                except Exception:
                    pass
            if consecutive_errors >= 5:
                _crash_msg = (
                    f"CRASH — 5 erreurs consecutives au cycle {cycle}\n"
                    f"Derniere: {type(exc).__name__}: {exc}\n"
                    f"Le systeme va s'arreter. Verifier logs/advisor_loop.log"
                )
                _telegram(_crash_msg)
                _send_email(
                    f"CRASH cycle {cycle}",
                    _crash_msg,
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

    if not _clean_exit:
        log.critical("[main] Sortie anormale — sys.exit(1)")
        sys.exit(1)


if __name__ == "__main__":
    _env_symbols = os.getenv("V9_SYMBOLS", "")
    _symbols_from_env = (
        _env_symbols.split() if _env_symbols.strip() else SYMBOLS_DEFAULT
    )

    parser = argparse.ArgumentParser(description="Advisor loop multi-symboles")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--symbols", nargs="+", default=_symbols_from_env)
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args()
    main(symbols=args.symbols, interval=args.interval, max_cycles=args.max_cycles)
