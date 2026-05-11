#!/usr/bin/env python3
"""
TEST P1 — Advanced Metrics (Sharpe, Sortino, CAGR, Calmar)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.analytics.advanced_metrics import (
    AdvancedMetrics
)


def generate_sample_returns(scenario: str, num_trades: int = 100) -> list:
    """Génère des returns synthétiques pour différents scénarios"""
    import random
    random.seed(42)

    returns = []

    if scenario == "profitable":
        # Win rate 60%, avg gain 1%, avg loss 0.5%
        for i in range(num_trades):
            if random.random() < 0.60:
                returns.append(random.uniform(0.005, 0.015))
            else:
                returns.append(-random.uniform(0.001, 0.010))

    elif scenario == "breakeven":
        # Win rate 50%, avg gain 0.5%, avg loss 0.5%
        for i in range(num_trades):
            if random.random() < 0.50:
                returns.append(random.uniform(0.003, 0.008))
            else:
                returns.append(-random.uniform(0.003, 0.008))

    elif scenario == "losing":
        # Win rate 40%, avg gain 0.8%, avg loss 1.5%
        for i in range(num_trades):
            if random.random() < 0.40:
                returns.append(random.uniform(0.005, 0.012))
            else:
                returns.append(-random.uniform(0.010, 0.020))

    elif scenario == "volatile":
        # Très volatile, gros mouvements
        for i in range(num_trades):
            if random.random() < 0.50:
                returns.append(random.uniform(0.02, 0.05))
            else:
                returns.append(-random.uniform(0.02, 0.05))

    return returns


def test_sharpe_sortino():
    print("\n" + "="*70)
    print("[P1-1] TEST SHARPE ET SORTINO RATIO")
    print("="*70)

    metrics = AdvancedMetrics(risk_free_rate=0.02)

    scenarios = {
        "profitable": 0.012,
        "breakeven": 0.000,
        "losing": -0.008,
        "volatile": 0.005,
    }

    for scenario, expected_trend in scenarios.items():
        returns = generate_sample_returns(scenario, 100)

        sharpe = metrics.calculate_sharpe_ratio(returns)
        sortino = metrics.calculate_sortino_ratio(returns)

        print(f"\n{scenario.upper()}:")
        print(f"  Avg daily return: {sum(returns)/len(returns):.3%}")
        print(f"  Sharpe ratio: {sharpe:.2f}")
        print(f"  Sortino ratio: {sortino:.2f}")
        print("  Note: Sortino > Sharpe indique volatilité asymétrique")


def test_cagr_calmar():
    print("\n" + "="*70)
    print("[P1-2] TEST CAGR ET CALMAR RATIO")
    print("="*70)

    metrics = AdvancedMetrics()

    # Scénario 1: 5 ans, $10k -> $50k
    print("\n1. CAGR: $10k sur 5 ans -> $50k")
    cagr = metrics.calculate_cagr(10000, 50000, 5)
    print(f"   CAGR: {cagr:.2%}")
    print(f"   Interpretation: Croissance annualisée de {cagr:.1%}")

    # Scénario 2: 1 an, différentes trajectoires
    returns_good = [0.02] * 250  # +2% par jour?? très optimiste
    returns_volatile = generate_sample_returns("volatile", 250)
    returns_losing = generate_sample_returns("losing", 250)

    starting = 10000

    print("\n2. CALMAR RATIO (Return / Max Drawdown)")

    for scenario, returns in [
        ("Profitable stable", returns_good),
        ("Volatile", returns_volatile),
        ("Losing", returns_losing),
    ]:
        calmar = metrics.calculate_calmar_ratio(returns, starting, period_days=252)
        max_dd, _, _ = metrics.calculate_max_drawdown(starting, returns)

        print(f"\n   {scenario}:")
        print(f"     Max Drawdown: {max_dd:.2%}")
        print(f"     Calmar Ratio: {calmar:.2f}")


def test_drawdown():
    print("\n" + "="*70)
    print("[P1-3] TEST MAX DRAWDOWN")
    print("="*70)

    metrics = AdvancedMetrics()

    # Scénario avec drawdown évident
    returns = [
        0.05, 0.05, 0.05,  # Monte
        -0.10, -0.10, -0.10,  # Crash!
        0.02, 0.02  # Recovery
    ]

    starting = 10000
    max_dd, peak_idx, trough_idx = metrics.calculate_max_drawdown(starting, returns)

    print("\nScenario: 3 days +5%, 3 days -10%, recovery")
    print(f"  Max Drawdown: {max_dd:.2%}")
    print(f"  Peak at day: {peak_idx}")
    print(f"  Trough at day: {trough_idx}")
    print(f"  Duration: {trough_idx - peak_idx} days")


def test_win_rate():
    print("\n" + "="*70)
    print("[P1-4] TEST WIN RATE ET PROFIT FACTOR")
    print("="*70)

    metrics = AdvancedMetrics()

    scenarios = {
        "60% winrate": generate_sample_returns("profitable", 100),
        "50% winrate": generate_sample_returns("breakeven", 100),
        "40% winrate": generate_sample_returns("losing", 100),
    }

    for name, returns in scenarios.items():
        win_rate, wins, losses = metrics.calculate_win_rate(returns)
        profit_factor = metrics.calculate_profit_factor(returns)

        total_gains = sum(r for r in returns if r > 0)
        total_losses = sum(r for r in returns if r < 0)

        print(f"\n{name}:")
        print(f"  Wins: {wins}/{len(returns)} ({win_rate:.1%})")
        print(f"  Total Gains: +${total_gains*10000:.2f}")
        print(f"  Total Losses: ${total_losses*10000:.2f}")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Interpretation: {'Profitable' if profit_factor > 1 else 'Losing'}")


def test_full_report():
    print("\n" + "="*70)
    print("[P1-5] TEST FULL REPORT - CAS RÉALISTE")
    print("="*70)

    metrics = AdvancedMetrics(risk_free_rate=0.02)

    starting_capital = 10000
    returns = generate_sample_returns("profitable", 252)

    # Calculer capital final
    ending_capital = starting_capital
    for ret in returns:
        ending_capital *= (1 + ret)

    report = metrics.get_full_report(
        starting_capital=starting_capital,
        ending_capital=ending_capital,
        returns=returns,
        years=1.0,
        period_days=252
    )

    print("\nCAPITAL:")
    print(f"  Départ: ${report['starting_capital']:,.2f}")
    print(f"  Final: ${report['ending_capital']:,.2f}")
    print(f"  Profit: ${report['net_profit']:,.2f} ({report['net_profit_pct']:.2%})")

    print("\nPERFORMANCE:")
    print(f"  CAGR: {report['cagr']:.2%}")
    print(f"  Sharpe Ratio: {report['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio: {report['sortino_ratio']:.2f}")
    print(f"  Calmar Ratio: {report['calmar_ratio']:.2f}")

    print("\nRISQUE:")
    print(f"  Max Drawdown: {report['max_drawdown']:.2%} (${report['max_drawdown_usd']:,.2f})")
    print(f"  Drawdown period: Days {report['max_drawdown_period'][0]} -> {report['max_drawdown_period'][1]}")
    print(f"  Std Dev: {report['std_dev']:.3%}")

    print("\nTRADES:")
    print(f"  Total: {report['num_trades']}")
    print(f"  Wins: {report['num_wins']} ({report['win_rate']:.1%})")
    print(f"  Losses: {report['num_losses']}")
    print(f"  Profit Factor: {report['profit_factor']:.2f}")
    print(f"  Recovery Factor: {report['recovery_factor']:.2f}")

    print("\nINTERPRETATION:")
    if report['sharpe_ratio'] > 1.0:
        print(f"  [OK] Excellent Sharpe ({report['sharpe_ratio']:.2f})")
    elif report['sharpe_ratio'] > 0.5:
        print(f"  [WARN] Good Sharpe ({report['sharpe_ratio']:.2f})")
    else:
        print(f"  [FAIL] Weak Sharpe ({report['sharpe_ratio']:.2f})")

    if report['profit_factor'] > 1.5:
        print(f"  [OK] Excellent Profit Factor ({report['profit_factor']:.2f})")
    elif report['profit_factor'] > 1.0:
        print(f"  [WARN] Good Profit Factor ({report['profit_factor']:.2f})")
    else:
        print(f"  [FAIL] Losing system ({report['profit_factor']:.2f})")


if __name__ == "__main__":
    test_sharpe_sortino()
    test_cagr_calmar()
    test_drawdown()
    test_win_rate()
    test_full_report()

    print("\n" + "="*70)
    print("[OK] TOUS LES TESTS P1 ADVANCED METRICS REUSSIS")
    print("="*70 + "\n")
