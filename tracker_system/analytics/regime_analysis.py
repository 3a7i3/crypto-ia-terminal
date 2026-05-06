from __future__ import annotations

from collections import defaultdict


def group_trades_by_regime(trades: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("regime", "unknown"))].append(trade)
    return dict(grouped)


def summarize_regimes(trades: list[dict]) -> list[dict[str, float | int | str]]:
    summary: list[dict[str, float | int | str]] = []
    for regime, bucket in sorted(group_trades_by_regime(trades).items()):
        total = len(bucket)
        wins = [trade for trade in bucket if float(trade.get("pnl_usd", 0.0)) > 0]
        summary.append(
            {
                "regime": regime,
                "trades": total,
                "winrate": len(wins) / total if total else 0.0,
                "avg_pnl_pct": sum(float(trade.get("pnl_pct", 0.0)) for trade in bucket) / total if total else 0.0,
            }
        )
    return summary