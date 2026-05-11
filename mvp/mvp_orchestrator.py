"""
mvp_orchestrator.py — MVP Orchestrator

Boucle principale du système hedge fund MVP.
Simple. Lisible. Chaque étape est explicite.

Pipeline par cycle :
  1. Fetch candles
  2. MarketStateEngine → "quel marché ?"
  3. SignalEngineMVP   → "quel signal ?"
  4. RiskEngineMVP     → "combien risquer ?"
  5. ExecutionEngineMVP→ "comment exécuter ?"
  6. Monitor positions  → SL/TP atteint ?
  7. PostTradeLearning  → "qu'est-ce qu'on apprend ?"

Telegram : rapport KPIs toutes les 30 min + alertes immédiates.

Usage:
    python mvp/mvp_orchestrator.py
    python mvp/mvp_orchestrator.py --interval 60 --paper
    python mvp/mvp_orchestrator.py --symbols BTC/USDT ETH/USDT --capital 500
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Garantit que le projet root est dans sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.makedirs("logs", exist_ok=True)

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("MVP_LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/mvp_orchestrator.log", encoding="utf-8"),
    ],
)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("mvp")

from mvp.market_state_engine  import MarketStateEngine
from mvp.signal_engine_mvp    import SignalEngineMVP
from mvp.risk_engine_mvp      import RiskEngineMVP
from mvp.execution_engine_mvp import ExecutionEngineMVP, ExecutionResult
from mvp.post_trade_learning  import PostTradeLearning
from mvp.trade_logger         import log_signal
from tracker_system.core.event_writer import record_entry_from_mvp, record_exit_from_mvp


SYMBOLS_DEFAULT = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
REPORT_EVERY    = 6     # rapport KPIs tous les 6 cycles (30 min si interval=300s)


# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": text[:4096]},
            timeout=10,
        )
    except Exception as exc:
        log.debug("Telegram error: %s", exc)


# ── Fetch candles ─────────────────────────────────────────────────────────────

def _fetch_candles(exchange, symbol: str, timeframe: str, limit: int = 100) -> list:
    try:
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as exc:
        log.warning("[Fetch] %s %s: %s", symbol, timeframe, exc)
        return []


# ── Cycle principal ───────────────────────────────────────────────────────────

def run_cycle(
    symbols: list[str],
    exchange,
    market_engine: MarketStateEngine,
    signal_engine: SignalEngineMVP,
    risk_engine: RiskEngineMVP,
    exec_engine: ExecutionEngineMVP,
    learning: PostTradeLearning,
    open_trades: dict,     # symbol → ExecutionResult
    open_states: dict,     # symbol → (signal_type, regime, entry_features, entry_ts)
    cycle: int,
    paper_mode: bool,
) -> None:

    for symbol in symbols:
        try:
            _process_symbol(
                symbol, exchange, market_engine, signal_engine,
                risk_engine, exec_engine, learning,
                open_trades, open_states, cycle, paper_mode,
            )
        except Exception as exc:
            log.error("[Cycle] %s erreur: %s", symbol, exc, exc_info=True)


def _process_symbol(
    symbol, exchange, market_engine, signal_engine,
    risk_engine, exec_engine, learning,
    open_trades, open_states, cycle, paper_mode,
) -> None:

    # ── Fetch candles ─────────────────────────────────────────────────────
    c1h = _fetch_candles(exchange, symbol, "1h", 100)
    c4h = _fetch_candles(exchange, symbol, "4h", 60)

    if len(c1h) < 30:
        log.debug("[%s] pas assez de candles (%d)", symbol, len(c1h))
        return

    current_price = float(c1h[-1][4]) if c1h else 0.0

    # ── 1. MarketStateEngine ──────────────────────────────────────────────
    state = market_engine.analyze(
        symbol=symbol,
        candles_1h=c1h,
        candles_4h=c4h,
    )
    log.debug("[MarketState] %s", state.summary())

    # ── 2. Monitor positions ouvertes ─────────────────────────────────────
    if symbol in open_trades:
        # Accumule le price_path pour le backtester (max 150 points)
        path = open_states[symbol].setdefault("price_path", [])
        path.append(current_price)
        if len(path) > 150:
            path.pop(0)

        entry_result = open_trades[symbol]
        should_exit, exit_reason = exec_engine.check_exit(symbol, entry_result.direction, current_price, entry_result)
        if should_exit:
            _close_trade(symbol, current_price, exit_reason, open_trades, open_states, risk_engine, learning)
            return

    # ── Pas de nouveau signal si déjà en position ─────────────────────────
    if symbol in open_trades:
        return

    # ── 3. SignalEngine ───────────────────────────────────────────────────
    if not state.is_tradeable():
        log.debug("[%s] marché non tradeable (conf=%.0%)", symbol, state.global_confidence)
        return

    signal = signal_engine.best_signal(symbol, c1h, state, c4h)
    if signal is None or not signal.actionable:
        return

    log.info("[Signal] %s | %s %s score=%.0f conf=%.0%%",
             symbol, signal.signal_type.value, signal.direction, signal.score, signal.confidence)

    log_signal(
        symbol=symbol, signal_type=signal.signal_type.value,
        direction=signal.direction, score=signal.score,
        confidence=signal.confidence, price=current_price,
        regime=state.trend, trade_allowed=True,
    )

    # ── 4. RiskEngine ─────────────────────────────────────────────────────
    atr_pct = float(state.inputs.get("atr_pct", 0.01))
    recent_wr = _get_win_rate(learning, signal.signal_type.value)

    risk = risk_engine.evaluate(
        symbol=symbol,
        direction=signal.direction,
        signal_score=signal.score,
        signal_confidence=signal.confidence,
        atr_pct=atr_pct,
        win_rate_history=recent_wr,
    )

    if not risk.allowed:
        log.info("[Risk] %s BLOQUÉ: %s", symbol, risk.reason)
        return

    log.info("[Risk] %s AUTORISÉ: %s", symbol, risk.reason)

    # ── 5. ExecutionEngine ────────────────────────────────────────────────
    result = exec_engine.execute(
        symbol=symbol,
        direction=signal.direction,
        size_usd=risk.size_usd,
        signal_score=signal.score,
        atr_pct=atr_pct,
        current_price=current_price,
    )

    if result.status != "executed":
        log.warning("[Exec] %s REJETÉ: %s", symbol, result.reason)
        return

    # Enregistrement
    open_trades[symbol] = result
    open_states[symbol] = {
        "signal_type": signal.signal_type.value,
        "regime": state.trend,
        "features": signal.features_used,
        "entry_ts": time.time(),
        "entry_score": signal.score,
        "entry_confidence": signal.confidence,
        "expected_slippage_bps": result.estimated_slippage_bps,
    }
    risk_engine.register_open(symbol, signal.direction, risk.size_usd, result.entry_price)

    record_entry_from_mvp(
        symbol=symbol, direction=signal.direction,
        signal_type=signal.signal_type.value, regime=state.trend,
        entry_price=result.entry_price, size_usd=risk.size_usd,
        stop_loss=result.stop_loss_price, take_profit=result.take_profit_price,
        score=signal.score, confidence=signal.confidence,
        atr_pct=atr_pct, paper=paper_mode,
    )

    msg = (
        f"TRADE OUVERT — {symbol}\n"
        f"Direction : {signal.direction.upper()}\n"
        f"Signal    : {signal.signal_type.value} (score={signal.score:.0f})\n"
        f"Marché    : {state.trend} / {state.pressure} / {state.volatility}\n"
        f"Prix      : {result.entry_price:.4f}\n"
        f"SL        : {result.stop_loss_price:.4f}\n"
        f"TP        : {result.take_profit_price:.4f}\n"
        f"RR        : {result.risk_reward:.1f}\n"
        f"Taille    : ${risk.size_usd:.2f} ({risk.size_pct_capital:.1%})\n"
        f"Mode      : {'PAPER' if paper_mode else 'LIVE'}"
    )
    log.info(msg)
    _tg(msg)


def _close_trade(
    symbol: str,
    exit_price: float,
    exit_reason: str,
    open_trades: dict,
    open_states: dict,
    risk_engine: RiskEngineMVP,
    learning: PostTradeLearning,
) -> None:
    entry_result = open_trades.pop(symbol, None)
    state_info   = open_states.pop(symbol, {})
    if entry_result is None:
        return

    entry_price = entry_result.entry_price
    direction   = entry_result.direction
    size_usd    = entry_result.executed_size_usd
    fee_usd     = entry_result.total_fee_usd
    duration    = (time.time() - state_info.get("entry_ts", time.time())) / 60.0

    pnl_pct = ((exit_price - entry_price) / entry_price) if direction == "long" else (
               (entry_price - exit_price) / entry_price)
    pnl_usd = size_usd * pnl_pct - fee_usd

    # Slippage réel (approximation)
    actual_slip = abs(exit_price - entry_price) / entry_price * 10000 * 0.1

    risk_engine.register_close(symbol, pnl_usd, pnl_pct)

    rec = learning.record(
        symbol=symbol,
        direction=direction,
        signal_type=state_info.get("signal_type", "unknown"),
        regime=state_info.get("regime", "unknown"),
        entry_price=entry_price,
        exit_price=exit_price,
        size_usd=size_usd,
        entry_score=state_info.get("entry_score", 0),
        entry_confidence=state_info.get("entry_confidence", 0),
        duration_minutes=duration,
        expected_slippage_bps=state_info.get("expected_slippage_bps", 0),
        actual_slippage_bps=actual_slip,
        fee_usd=fee_usd,
        entry_features=state_info.get("features"),
    )

    record_exit_from_mvp(
        symbol=symbol, direction=direction,
        signal_type=state_info.get("signal_type", "unknown"),
        regime=state_info.get("regime", "unknown"),
        entry_price=entry_price, exit_price=exit_price,
        size_usd=size_usd, pnl_usd=pnl_usd, pnl_pct=pnl_pct,
        exit_reason=exit_reason, duration_minutes=duration,
        attribution=rec.attribution, fee_usd=fee_usd,
        price_path=state_info.get("price_path", []),
    )

    emoji = "GAIN" if pnl_usd > 0 else "PERTE"
    msg = (
        f"TRADE FERME [{emoji}] — {symbol}\n"
        f"PnL : {pnl_usd:+.4f}$ ({pnl_pct*100:+.2f}%)\n"
        f"Exit: {exit_reason}\n"
        f"Attribution: {rec.attribution}\n"
        f"{rec.lesson if rec.lesson else ''}"
    )
    log.info(msg)
    _tg(msg)


def _get_win_rate(learning: PostTradeLearning, signal_type: str) -> float | None:
    pnls = learning._signal_pnl.get(signal_type, [])
    if len(pnls) < 10:
        return None
    return sum(1 for p in pnls if p > 0) / len(pnls)


def _send_kpi_report(learning: PostTradeLearning, risk_engine: RiskEngineMVP) -> None:
    kpis   = learning.kpis()
    status = risk_engine.status()
    lessons = learning.recent_lessons(3)

    msg = (
        f"KPIs MVP — {time.strftime('%H:%M')}\n"
        f"{kpis.summary()}\n\n"
        f"Capital : ${status['capital_usd']:.2f} (peak ${status['peak_capital']:.2f})\n"
        f"Drawdown: {status['drawdown_pct']:.2f}%\n"
        f"Positions: {status['open_positions']}\n"
        f"Meilleur régime : {kpis.best_regime}\n"
        f"Meilleur signal : {kpis.best_signal}\n"
    )
    if lessons:
        msg += "\nLecons recentes:\n" + "\n".join(f"• {lesson}" for lesson in lessons)
    if status["trading_halted"]:
        msg += "\nALERTE: TRADING HALTE (hard drawdown atteint)"
    log.info("[KPI] %s", kpis.summary())
    _tg(msg)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MVP Orchestrator")
    parser.add_argument("--interval", type=int, default=300, help="Secondes entre cycles")
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS_DEFAULT)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--paper", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", default=False)
    args = parser.parse_args()

    paper_mode = not args.live

    log.info("=" * 60)
    log.info("MVP ORCHESTRATOR — %s", "PAPER" if paper_mode else "LIVE")
    log.info("Symboles  : %s", args.symbols)
    log.info("Capital   : $%.2f", args.capital)
    log.info("Interval  : %ds", args.interval)
    log.info("=" * 60)

    # ── Initialisation exchange ───────────────────────────────────────────
    try:
        import ccxt
        exchange = ccxt.binance({
            "apiKey":    os.getenv("BINANCE_API_KEY", ""),
            "secret":    os.getenv("BINANCE_SECRET", ""),
            "options":   {"defaultType": "future"},
            "enableRateLimit": True,
        })
        exchange.load_markets()
        log.info("Exchange Binance Futures connecté")
    except Exception as exc:
        log.warning("Exchange non disponible: %s — mode paper seulement", exc)
        exchange = None
        paper_mode = True

    # ── Instanciation des 5 moteurs ──────────────────────────────────────
    signal_engine = SignalEngineMVP()
    learning      = PostTradeLearning(signal_engine=signal_engine)
    market_engine = MarketStateEngine()
    risk_engine   = RiskEngineMVP(capital_usd=args.capital)
    exec_engine   = ExecutionEngineMVP(
        exchange=exchange,
        paper_mode=paper_mode,
    )

    open_trades: dict[str, ExecutionResult] = {}
    open_states: dict = {}
    cycle = 0

    _tg(f"MVP démarré — {len(args.symbols)} symboles — capital ${args.capital:.0f}")

    while True:
        cycle += 1
        t_start = time.time()
        log.info("── Cycle %d ──", cycle)

        run_cycle(
            symbols=args.symbols,
            exchange=exchange,
            market_engine=market_engine,
            signal_engine=signal_engine,
            risk_engine=risk_engine,
            exec_engine=exec_engine,
            learning=learning,
            open_trades=open_trades,
            open_states=open_states,
            cycle=cycle,
            paper_mode=paper_mode,
        )

        if cycle % REPORT_EVERY == 0:
            _send_kpi_report(learning, risk_engine)

        elapsed = time.time() - t_start
        sleep_time = max(0, args.interval - elapsed)
        log.debug("Cycle terminé en %.1fs, prochain dans %.0fs", elapsed, sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
