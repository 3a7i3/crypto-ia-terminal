"""
backtest_profiler.py — Profilage des backtests de stratégies.

Usage:
    python backtest_profiler.py --n 1000 --n_strat 5
"""

from __future__ import annotations

import argparse
import random
import time


def run_backtest(strategy_id: int, n: int) -> dict:
    returns = [random.gauss(0.001, 0.02) for _ in range(n)]
    equity = 1.0
    for r in returns:
        equity *= 1 + r
    sharpe = (
        sum(returns)
        / (max(1e-9, (sum(r**2 for r in returns) / n - (sum(returns) / n) ** 2) ** 0.5))
        / (n**0.5)
    )
    return {
        "strategy_id": strategy_id,
        "final_equity": round(equity, 4),
        "sharpe": round(sharpe, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest profiler")
    parser.add_argument(
        "--n", type=int, default=500, help="Nombre de barres par backtest"
    )
    parser.add_argument(
        "--n_strat", type=int, default=3, help="Nombre de stratégies à profiler"
    )
    args = parser.parse_args()

    print(f"Démarrage du profiling : {args.n_strat} stratégies × {args.n} barres")
    t0 = time.perf_counter()
    results = []
    for i in range(args.n_strat):
        res = run_backtest(i, args.n)
        results.append(res)
        print(
            f"  Stratégie {i}: equity={res['final_equity']:.4f} "
            f"sharpe={res['sharpe']:.4f}"
        )

    elapsed = time.perf_counter() - t0
    print("\n--- Profiling summary ---")
    print(f"Stratégies profilées : {args.n_strat}")
    print(f"Barres par backtest  : {args.n}")
    print(f"Durée totale         : {elapsed:.3f}s")
    best = max(results, key=lambda x: x["sharpe"])
    print(
        f"Meilleure stratégie  : id={best['strategy_id']} sharpe={best['sharpe']:.4f}"
    )


if __name__ == "__main__":
    main()
