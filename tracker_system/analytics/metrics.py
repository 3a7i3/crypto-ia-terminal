from __future__ import annotations

from pathlib import Path

from tracker_system.analytics.mfe_mae import compute_average_mfe_mae, compute_efficiency
from tracker_system.analytics.regime_analysis import summarize_regimes
from tracker_system.config.settings import REFERENCE_CAPITAL, TRADES_LOG_FILE
from tracker_system.storage.loader import load_jsonl


def load_trades(log_file: Path = TRADES_LOG_FILE) -> list[dict]:
    return [event for event in load_jsonl(log_file) if event.get("type") == "exit"]


def compute_basic_metrics(trades: list[dict]) -> dict[str, float | int]:
    if not trades:
        return {}

    total = len(trades)
    wins = [t for t in trades if float(t.get("pnl_usd", 0.0)) > 0]
    losses = [t for t in trades if float(t.get("pnl_usd", 0.0)) <= 0]
    winrate = len(wins) / total if total else 0.0
    avg_win = (
        sum(float(t.get("pnl_pct", 0.0)) for t in wins) / len(wins) if wins else 0.0
    )
    avg_loss = (
        sum(float(t.get("pnl_pct", 0.0)) for t in losses) / len(losses)
        if losses
        else 0.0
    )
    pnl_total = sum(float(t.get("pnl_usd", 0.0)) for t in trades)
    return {
        "trades": total,
        "winrate": winrate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "pnl_total": pnl_total,
    }


def compute_robustness_metrics(
    trades: list[dict], reference_capital: float = REFERENCE_CAPITAL
) -> dict:
    """P0 KPIs : profit_factor, avg_win_loss_ratio, worst_trade, drawdown_normalized, rolling_20."""
    if not trades:
        return {}

    pnl_pct = [float(t.get("pnl_pct", 0.0)) for t in trades]
    pnl_usd = [float(t.get("pnl_usd", 0.0)) for t in trades]

    gross_win = sum(p for p in pnl_pct if p > 0)
    gross_loss = abs(sum(p for p in pnl_pct if p < 0))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

    wins_pct = [p for p in pnl_pct if p > 0]
    losses_pct = [p for p in pnl_pct if p < 0]
    avg_win = sum(wins_pct) / len(wins_pct) if wins_pct else 0.0
    avg_loss = sum(losses_pct) / len(losses_pct) if losses_pct else 0.0
    avg_win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    worst_trade_pct = min(pnl_pct) if pnl_pct else 0.0
    worst_trade_usd = min(pnl_usd) if pnl_usd else 0.0

    # Drawdown normalisé sur capital de référence
    equity = reference_capital
    peak = reference_capital
    max_dd_usd = 0.0
    for usd in pnl_usd:
        equity += usd
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_usd:
            max_dd_usd = dd
    drawdown_normalized_pct = (
        max_dd_usd / reference_capital if reference_capital > 0 else 0.0
    )

    # Rolling derniers 20 trades
    last20 = trades[-20:]
    wins20 = [t for t in last20 if float(t.get("pnl_usd", 0.0)) > 0]
    losses20 = [t for t in last20 if float(t.get("pnl_usd", 0.0)) <= 0]
    wr20 = len(wins20) / len(last20) if last20 else 0.0
    avg_win20 = (
        sum(float(t.get("pnl_pct", 0.0)) for t in wins20) / len(wins20)
        if wins20
        else 0.0
    )
    avg_loss20 = (
        sum(float(t.get("pnl_pct", 0.0)) for t in losses20) / len(losses20)
        if losses20
        else 0.0
    )
    expectancy20 = (wr20 * avg_win20) + ((1 - wr20) * avg_loss20)

    return {
        "profit_factor": round(profit_factor, 4),
        "avg_win_loss_ratio": round(avg_win_loss_ratio, 4),
        "worst_trade_pct": round(worst_trade_pct, 6),
        "worst_trade_usd": round(worst_trade_usd, 4),
        "drawdown_normalized_pct": round(drawdown_normalized_pct, 6),
        "drawdown_reference_capital": reference_capital,
        "rolling_20": {
            "trades": len(last20),
            "winrate": round(wr20, 4),
            "expectancy": round(expectancy20, 6),
        },
    }


def check_asymmetric_risk(winrate: float, pnl_total: float) -> str | None:
    """Alerte si winrate élevé mais PnL négatif — signe de pertes asymétriques."""
    if winrate >= 0.85 and pnl_total < 0:
        return (
            f"ALERTE asymétrie : winrate={winrate:.1%} mais PnL={pnl_total:.2f}$ — "
            "les pertes coûtent trop cher par rapport aux gains. Vérifier avg_loss vs avg_win."
        )
    return None


def compute_expectancy(winrate: float, avg_win: float, avg_loss: float) -> float:
    lossrate = 1.0 - winrate
    return (winrate * avg_win) + (lossrate * avg_loss)


def compute_all_metrics(
    log_file: Path = TRADES_LOG_FILE, reference_capital: float = REFERENCE_CAPITAL
) -> dict:
    trades = load_trades(log_file)
    basic = compute_basic_metrics(trades)
    if not basic:
        return {}

    mfe_mae = compute_average_mfe_mae(trades)
    expectancy = compute_expectancy(
        float(basic.get("winrate", 0.0)),
        float(basic.get("avg_win", 0.0)),
        float(basic.get("avg_loss", 0.0)),
    )
    robustness = compute_robustness_metrics(trades, reference_capital)
    asymmetry_alert = check_asymmetric_risk(
        float(basic.get("winrate", 0.0)), float(basic.get("pnl_total", 0.0))
    )

    return {
        **basic,
        "expectancy": expectancy,
        **mfe_mae,
        "efficiency": compute_efficiency(trades),
        "regimes": summarize_regimes(trades),
        **robustness,
        "asymmetry_alert": asymmetry_alert,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(compute_all_metrics(), indent=2, default=str))
