import logging
import os

import requests

from .paper_gate import gate_status
from .paper_metrics import PaperMetrics

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("PAPER_ARENA_TG_TOKEN", "")
_CHAT = os.getenv("PAPER_ARENA_TG_CHAT_ID", "")


def _send(text: str) -> None:
    if not _TOKEN or not _CHAT:
        logger.debug(
            "Telegram not configured (PAPER_ARENA_TG_TOKEN / PAPER_ARENA_TG_CHAT_ID)"
        )
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            json={"chat_id": _CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")


def notify_entry(
    symbol: str,
    side: str,
    price: float,
    size_usdt: float,
    rsi: float,
    metrics: PaperMetrics,
) -> None:
    emoji = "🟢" if side == "LONG" else "🔴"
    _send(
        f"{emoji} *PAPER ENTRY*\n\n"
        f"*{symbol}*\n"
        f"{side}\n\n"
        f"Price: {price:,.2f}\n"
        f"Size: {size_usdt:.2f} USDT\n\n"
        f"RSI: {rsi:.1f}\n"
        f"Timeframe: 4h\n\n"
        f"Paper Equity:\n"
        f"{metrics.equity:,.2f} USDT"
    )


def notify_exit(
    symbol: str,
    entry_price: float,
    exit_price: float,
    pnl_net: float,
    run: int,
    metrics: PaperMetrics,
) -> None:
    emoji = "🟢" if pnl_net >= 0 else "🔴"
    sign = "+" if pnl_net >= 0 else ""
    _send(
        f"{emoji} *PAPER EXIT*\n\n"
        f"*{symbol}*\n\n"
        f"Entry: {entry_price:,.2f}\n"
        f"Exit : {exit_price:,.2f}\n\n"
        f"PnL : {sign}{pnl_net:,.2f} USDT\n\n"
        f"Equity : {metrics.equity:,.2f} USDT\n\n"
        f"Run : {run}"
    )


def notify_summary(metrics: PaperMetrics) -> None:
    s = metrics.summary()
    _send(
        f"📊 *PAPER ARENA — Rapport*\n\n"
        f"Equity: {s['equity']:,.2f} USDT\n"
        f"Signals: {s['signal_count']} | Trades: {s['trade_count']}\n"
        f"Win Rate: {s['win_rate_pct']}%\n"
        f"PF: {s['profit_factor']}\n"
        f"Expectancy: {s['expectancy']:+.2f} USDT\n"
        f"Avg: {s['avg_trade']:+.2f} | Median: {s['median_trade']:+.2f}\n"
        f"MaxDD: {s['max_drawdown_pct']}%\n"
        f"Avg Hold: {s['avg_hold_hours']}h\n"
        f"ENL Cost: {s['avg_enl_cost']:.4f}\n\n"
        f"*Gate*\n"
        f"{gate_status(metrics)}"
    )
