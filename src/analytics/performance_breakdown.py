"""
Agrège les rapports de runs par régime de marché.
Entrée : liste de rapports BacktestEngine (chacun contenant un champ "regime").
Sortie : stats par régime {trend, range, volatile}.
"""


def breakdown(reports: list[dict]) -> dict:
    """
    reports : liste de dicts avec au minimum :
      run_id, regime, total_trades, total_pnl, win_rate, max_drawdown

    Retourne :
      {
        "trending":  {n_runs, total_trades, avg_pnl, avg_win_rate, avg_drawdown, profit_factor},
        "sideways":  {...},
        "volatile":  {...},
        "all":      {...},
      }
    """
    buckets: dict[str, list[dict]] = {"trending": [], "sideways": [], "volatile": []}

    for r in reports:
        regime = r.get("regime", "sideways")
        if regime in buckets:
            buckets[regime].append(r)

    result = {}
    all_reports = reports

    for label, group in [*buckets.items(), ("all", all_reports)]:
        result[label] = _stats(group)

    return result


def _stats(group: list[dict]) -> dict:
    if not group:
        return {
            "n_runs": 0,
            "total_trades": 0,
            "avg_pnl": 0.0,
            "avg_win_rate": 0.0,
            "avg_drawdown": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
        }

    n = len(group)
    total_trades = sum(r.get("total_trades", 0) for r in group)
    avg_pnl = sum(r.get("total_pnl", 0.0) for r in group) / n
    avg_wr = sum(r.get("win_rate", 0.0) for r in group) / n
    avg_dd = sum(r.get("max_drawdown", 0.0) for r in group) / n

    gains = sum(r["total_pnl"] for r in group if r.get("total_pnl", 0) > 0)
    losses = abs(sum(r["total_pnl"] for r in group if r.get("total_pnl", 0) < 0))
    pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)

    # Expectancy = gain moyen par trade (PnL total / nombre total de trades)
    expectancy = avg_pnl / (total_trades / n) if total_trades > 0 else 0.0

    return {
        "n_runs": n,
        "total_trades": total_trades,
        "avg_pnl": round(avg_pnl, 2),
        "avg_win_rate": round(avg_wr, 3),
        "avg_drawdown": round(avg_dd, 4),
        "profit_factor": round(pf, 2),
        "expectancy": round(expectancy, 3),
    }
