"""
Paper Arena V1 — ETH/USDT 4h RSI 15/85
Mission : répondre à une seule question scientifique.
  L'edge observé en recherche survit-il à des données réelles ?

Env vars requis :
  PAPER_ARENA_TG_TOKEN   — token Telegram bot dédié
  PAPER_ARENA_TG_CHAT_ID — chat id destinataire
"""

import logging
import random
import time
from typing import Optional

from src.agent.rsi_extreme_strategy import RSIExtremeStrategy
from src.backtest.mexc_feed import fetch_mexc_candles

from .paper_gate import gate_passed, gate_status
from .paper_metrics import PaperMetrics
from .paper_position_manager import PaperPositionManager
from .paper_report import notify_entry, notify_exit, notify_summary

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
SYMBOL = "ETHUSDT"
INTERVAL = "4h"
RSI_PERIOD = 14
RSI_OVERSOLD = 15.0
RSI_OVERBOUGHT = 85.0
POSITION_SIZE_USDT = 1_000.0
INITIAL_EQUITY = 10_000.0
POLL_INTERVAL_S = 300  # 5 min — suffisant pour 4h bars
WARMUP_CANDLES = 100
SUMMARY_EVERY_N = 10  # rapport Telegram tous les N trades

# ENL light (miroir exact de ENLConfig.light)
_ENL_SPREAD_BPS = 5.0
_ENL_SLIPPAGE_SIGMA = 0.001
_rng = random.Random()


# ── ENL friction ──────────────────────────────────────────────────────────────
def _enl_fill(price: float, side: str) -> tuple[float, float]:
    """Retourne (exec_price, friction_cost) — réplique NoisyExchange ENL light."""
    half_spread = price * (_ENL_SPREAD_BPS / 10_000) / 2
    slip = abs(_rng.gauss(0, price * _ENL_SLIPPAGE_SIGMA))
    friction = half_spread + slip
    exec_price = (price + friction) if side == "buy" else (price - friction)
    return max(1e-8, exec_price), friction


# ── Helpers ───────────────────────────────────────────────────────────────────
def _last_closed_ts(candles: list[dict]) -> int:
    """Timestamp ms de la dernière bar fermée (avant-dernière de la réponse API)."""
    return candles[-2]["timestamp"] if len(candles) >= 2 else 0


def _warmup(strategy: RSIExtremeStrategy, candles: list[dict]) -> None:
    """Alimente la stratégie sans générer de trades (initialisation RSI)."""
    for c in candles:
        strategy.generate_signal(c)
    logger.info(f"Warmup terminé ({len(candles)} candles)")


# ── Runner ────────────────────────────────────────────────────────────────────
def run_paper_arena() -> None:
    """
    Boucle principale Paper Arena V1.
    Tourne jusqu'à ce que la gate statistique soit franchie,
    ou jusqu'à interruption manuelle (Ctrl-C).
    """
    metrics = PaperMetrics(
        initial_equity=INITIAL_EQUITY,
        equity=INITIAL_EQUITY,
        peak_equity=INITIAL_EQUITY,
    )
    position_mgr = PaperPositionManager()
    strategy = RSIExtremeStrategy(
        rsi_period=RSI_PERIOD,
        oversold=RSI_OVERSOLD,
        overbought=RSI_OVERBOUGHT,
        use_trend_filter=False,
    )
    last_processed_ts: Optional[int] = None
    run_number = 0

    logger.info(
        f"Paper Arena V1 démarré — {SYMBOL} {INTERVAL} "
        f"RSI {RSI_OVERSOLD}/{RSI_OVERBOUGHT}"
    )

    # ── Warmup initial ────────────────────────────────────────────────────────
    try:
        raw = fetch_mexc_candles(SYMBOL, INTERVAL, limit=WARMUP_CANDLES)
        if len(raw) >= 2:
            warmup_candles = raw[:-1]  # exclure la bar potentiellement en formation
            _warmup(strategy, warmup_candles)
            last_processed_ts = _last_closed_ts(raw)
    except Exception as e:
        logger.exception(f"Warmup échoué : {e}")

    # ── Boucle principale ─────────────────────────────────────────────────────
    while True:
        try:
            raw = fetch_mexc_candles(SYMBOL, INTERVAL, limit=50)
            if len(raw) < 2:
                time.sleep(POLL_INTERVAL_S)
                continue

            current_bar_ts = _last_closed_ts(raw)

            if current_bar_ts == last_processed_ts:
                time.sleep(POLL_INTERVAL_S)
                continue

            last_processed_ts = current_bar_ts
            bar = raw[-2]  # dernière bar fermée
            price = bar["close"]
            signal = strategy.generate_signal(bar)

            if signal:
                metrics.signal_count += 1
                direction = signal.direction  # "buy" | "sell"
                logger.debug(f"Signal {direction.upper()} | RSI | close={price:.2f}")

            # ── Gestion position ──────────────────────────────────────────────
            if position_mgr.in_position and signal:
                pos = position_mgr.position
                should_exit = (pos.side == "LONG" and signal.direction == "sell") or (
                    pos.side == "SHORT" and signal.direction == "buy"
                )
                if should_exit:
                    close_side = "sell" if pos.side == "LONG" else "buy"
                    exec_price, enl_cost = _enl_fill(price, close_side)
                    closed_pos, pnl_net, fee, hold_s = position_mgr.close(exec_price)
                    total_enl = enl_cost * (pos.size_usdt / pos.entry_price)
                    metrics.record_trade(pnl_net, total_enl, hold_s)
                    run_number += 1
                    logger.info(
                        f"EXIT {closed_pos.side} | entry={closed_pos.entry_price:.2f} "
                        f"exit={exec_price:.2f} | pnl={pnl_net:+.2f} "
                        f"| equity={metrics.equity:.2f}"
                    )
                    notify_exit(
                        SYMBOL,
                        closed_pos.entry_price,
                        exec_price,
                        pnl_net,
                        run_number,
                        metrics,
                    )

                    if run_number % SUMMARY_EVERY_N == 0:
                        notify_summary(metrics)

                    if gate_passed(metrics):
                        logger.info("GATE PASSÉE — preuves statistiques suffisantes")
                        logger.info(gate_status(metrics))
                        notify_summary(metrics)
                        return

            if not position_mgr.in_position and signal:
                if signal.direction == "buy":
                    side = "LONG"
                    exec_price, enl_cost = _enl_fill(price, "buy")
                elif signal.direction == "sell":
                    side = "SHORT"
                    exec_price, enl_cost = _enl_fill(price, "sell")
                else:
                    time.sleep(POLL_INTERVAL_S)
                    continue

                rsi_val = strategy._rsi() or 0.0
                position_mgr.open(SYMBOL, side, exec_price, POSITION_SIZE_USDT, rsi_val)
                logger.info(
                    f"ENTRY {side} | exec={exec_price:.2f} | RSI={rsi_val:.1f} | "
                    f"equity={metrics.equity:.2f}"
                )
                notify_entry(
                    SYMBOL, side, exec_price, POSITION_SIZE_USDT, rsi_val, metrics
                )

        except KeyboardInterrupt:
            logger.info("Paper Arena interrompue manuellement")
            notify_summary(metrics)
            return
        except Exception as e:
            logger.exception(f"Erreur runner : {e}")

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run_paper_arena()
