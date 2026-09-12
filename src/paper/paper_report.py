import logging

from .paper_gate import gate_status
from .paper_metrics import PaperMetrics

logger = logging.getLogger(__name__)

# TG-PAPER-01 (2026-09) — @PaperArena_bot est réattribué au notificateur
# main-machine (src/paper/paper_trade_notifier.py). L'expérience RSI
# indépendante ci-dessous reste une recherche manuelle légale (voir
# CLAUDE.md — gel fonctionnel), mais elle ne doit plus jamais publier sous
# la même identité Telegram : deux producteurs indépendants ne peuvent pas
# posséder le même bot. Le chemin Telegram est donc volontairement rendu
# silencieux (no-op) plutôt que supprimé, pour préserver l'expérience.
def _send(text: str) -> None:
    logger.debug(
        "Telegram path silenced for the RSI paper-arena experiment "
        "(TG-PAPER-01 reassigned @PaperArena_bot to the main-machine "
        "notifier) — message not sent: %r",
        text[:80],
    )


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
