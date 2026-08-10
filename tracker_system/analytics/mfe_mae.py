from __future__ import annotations


def compute_average_mfe_mae(trades: list[dict]) -> dict[str, float]:
    mfe_values = [float(trade["mfe"]) for trade in trades if "mfe" in trade]
    mae_values = [float(trade["mae"]) for trade in trades if "mae" in trade]
    if not mfe_values or not mae_values:
        return {}
    return {
        "avg_mfe": sum(mfe_values) / len(mfe_values),
        "avg_mae": sum(mae_values) / len(mae_values),
    }


def compute_efficiency(trades: list[dict]) -> float:
    profits = [float(trade["pnl_pct"]) for trade in trades if float(trade.get("pnl_pct", 0.0)) > 0]
    mfe_values = [float(trade["mfe"]) for trade in trades if float(trade.get("mfe", 0.0)) > 0]
    if not profits or not mfe_values:
        return 0.0
    avg_profit = sum(profits) / len(profits)
    avg_mfe = sum(mfe_values) / len(mfe_values)
    if avg_mfe == 0:
        return 0.0
    return avg_profit / avg_mfe
