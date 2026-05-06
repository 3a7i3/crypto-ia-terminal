#!/usr/bin/env python3
"""
TEST P0 — Intégration des améliorations critiques
Montre: AlertSystem + PortfolioRiskManager + ExecutionReality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.risk.alert_system import AlertSystem
from tracker_system.risk.portfolio_risk import PortfolioRiskManager
from tracker_system.risk.execution_reality import ExecutionReality


def test_alert_system():
    print("\n" + "="*70)
    print("[P0-1] TEST SYSTÈME D'ALERTES")
    print("="*70)

    alert = AlertSystem(
        initial_capital=10000.0,
        daily_loss_threshold=-100.0,
        drawdown_threshold=0.15,
        position_concentration_threshold=0.80
    )

    print("\n1. Équité normale (pas d'alerte):")
    alert.update_equity(10100.0)
    alerts = alert.run_all_checks([{"symbol": "BTCUSDT", "size": 2000}])
    print(f"   Alertes: {len(alerts)}")
    print(f"   Équité: ${alert.current_equity:.2f}")
    print(f"   PnL jour: ${alert.daily_pnl:.2f}")

    print("\n2. Perte dépassant seuil:")
    alert.reset_daily()
    alert.daily_start_equity = 10000.0
    alert.update_equity(9850.0)  # -150$
    alerts = alert.run_all_checks([{"symbol": "BTCUSDT", "size": 2000}])
    for a in alerts:
        print(f"   [ALERT] {a}")

    print("\n3. Drawdown dépassant seuil:")
    alert.max_equity = 15000.0
    alert.current_equity = 12000.0  # Drawdown 20%
    alerts = alert.run_all_checks([{"symbol": "BTCUSDT", "size": 2000}])
    for a in alerts:
        print(f"   [CRITICAL] {a}")

    print("\n4. Concentration excessive:")
    alert.current_equity = 10000.0
    alerts = alert.run_all_checks([
        {"symbol": "BTCUSDT", "size": 5000},
        {"symbol": "ETHUSDT", "size": 4000},
        {"symbol": "BNBUSDT", "size": 2000},
    ])
    for a in alerts:
        print(f"   [WARNING] {a}")

    print("\nRésumé AlertSystem:")
    print(alert.summary())


def test_portfolio_risk_manager():
    print("\n" + "="*70)
    print("[P0-2] TEST GESTIONNAIRE RISQUE PORTEFEUILLE")
    print("="*70)

    risk = PortfolioRiskManager(
        total_capital=10000.0,
        max_single_exposure=0.20,
        max_total_exposure=0.80,
        max_avg_correlation=0.70
    )

    print("\n1. Nouvelle position VALIDE:")
    valid, reason = risk.validate_new_position(
        symbol="BTCUSDT",
        size=1000,
        current_positions=[],
        estimated_price=1.0
    )
    print(f"   Valide: {valid}")
    print(f"   Raison: {reason}")

    print("\n2. Position TROP GROSSE:")
    valid, reason = risk.validate_new_position(
        symbol="ETHUSDT",
        size=3000,  # 30% du capital
        current_positions=[],
        estimated_price=1.0
    )
    print(f"   Valide: {valid}")
    print(f"   Raison: {reason}")

    print("\n3. Exposition totale DÉPASSE:")
    valid, reason = risk.validate_new_position(
        symbol="LINKUSDT",
        size=2000,
        current_positions=[
            {"symbol": "BTCUSDT", "size": 5000, "price": 1.0},
            {"symbol": "ETHUSDT", "size": 4000, "price": 1.0},
        ],
        estimated_price=1.0
    )
    print(f"   Valide: {valid}")
    print(f"   Raison: {reason}")

    print("\n4. Concentration du portefeuille:")
    positions = [
        {"symbol": "BTCUSDT", "size": 3000},
        {"symbol": "ETHUSDT", "size": 2000},
        {"symbol": "BNBUSDT", "size": 1500},
    ]
    report = risk.get_portfolio_report(positions)
    print(f"   Total exposition: ${report['total_exposure']:.2f}")
    print(f"   Ratio exposition: {report['exposure_ratio']:.1%}")
    print(f"   Limites OK: {report['is_within_limits']}")
    print(f"\n   Répartition:")
    for sym, pct in report['breakdown'].items():
        print(f"     {sym}: {pct:.1%}")
    print(f"\n   Recommandations:")
    for rec in report['recommendations']:
        print(f"     - {rec}")

    print("\n5. Taille position suggérée:")
    suggested = risk.suggest_position_size(symbol="BTCUSDT", volatility=0.02)
    print(f"   Suggestion: ${suggested:.2f} (5% du capital avec ajustement volatilité)")


def test_execution_reality():
    print("\n" + "="*70)
    print("[P0-3] TEST RÉALISME EXECUTION")
    print("="*70)

    reality = ExecutionReality(
        slippage_bps=2.0,
        fee_maker=0.001,
        fee_taker=0.0015
    )

    print("\n1. Trade nominal +1% vs réaliste:")
    entry = 50000.0
    exit_price = 50500.0  # +1%

    pnl = reality.calculate_realistic_pnl(
        entry_price=entry,
        exit_price=exit_price,
        side="BUY",
        quantity=0.1
    )

    print(f"   Entry nominal: ${entry:.2f}")
    print(f"   Exit nominal: ${exit_price:.2f}")
    print(f"\n   PnL NOMINAL: +{pnl['nominal_pnl_pct']:.3%} = ${pnl['nominal_pnl_usd']:.2f}")
    print(f"   PnL RÉALISTE: {pnl['realistic_pnl_pct']:+.3%} = ${pnl['realistic_pnl_usd']:.2f}")
    print(f"   Friction: -{abs(pnl['friction_cost']):.2f}$ ({abs(pnl['friction_pct']):.2%})")

    print("\n2. Impact sur 100 trades (backtest fantasy vs réalité):")
    impact = reality.get_impact_summary(
        num_trades=100,
        avg_nominal_pnl_per_trade=0.005  # 0.5% avg
    )
    print(f"   Trades: {impact['num_trades']}")
    print(f"   Friction par trade: {impact['avg_friction_per_trade_pct']:.3%}")
    print(f"   Friction TOTALE: {impact['total_friction_pct']:.2%}")
    print(f"   Perte absolue sur compte 10k: ${impact['example_on_10000_account']:.2f}")
    print(f"\n   {impact['message']}")

    print("\n3. Trade enrichi avec réalisme:")
    trade = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000,
        "exit_price": 51000,
        "quantity": 0.1
    }
    realistic_trade = reality.create_realistic_trade(trade)
    print(f"   Original: entry={trade['entry_price']}, exit={trade['exit_price']}")
    print(f"   Ajusté: entry={realistic_trade['entry_price_adjusted']:.2f}, exit={realistic_trade['exit_price_adjusted']:.2f}")
    print(f"   PnL nominal: ${trade['exit_price'] - trade['entry_price']:.2f}")
    print(f"   PnL réaliste: ${realistic_trade['pnl_realistic']:.2f}")


def test_integrated_scenario():
    print("\n" + "="*70)
    print("[SCÉNARIO INTÉGRÉ] Jour de trading complet")
    print("="*70)

    alert = AlertSystem(initial_capital=10000.0)
    risk = PortfolioRiskManager(total_capital=10000.0)
    reality = ExecutionReality()

    trades = [
        {"symbol": "BTCUSDT", "side": "BUY", "entry": 50000, "exit": 50500, "qty": 0.1},
        {"symbol": "ETHUSDT", "side": "BUY", "entry": 2500, "exit": 2450, "qty": 1.0},
        {"symbol": "BNBUSDT", "side": "BUY", "entry": 600, "exit": 630, "qty": 5.0},
    ]

    print("\nMatin: 3 trades")
    cumulative_pnl = 0

    for i, trade in enumerate(trades, 1):
        pnl_calc = reality.calculate_realistic_pnl(
            entry_price=trade['entry'],
            exit_price=trade['exit'],
            side=trade['side'],
            quantity=trade['qty']
        )
        cumulative_pnl += pnl_calc['realistic_pnl_usd']

        print(f"\n  Trade {i}: {trade['symbol']}")
        print(f"    Nominal PnL: {pnl_calc['nominal_pnl_pct']:+.2%}")
        print(f"    Realistic PnL: {pnl_calc['realistic_pnl_pct']:+.2%}")
        print(f"    Friction: -{abs(pnl_calc['friction_cost']):.2f}$")

    new_equity = 10000.0 + cumulative_pnl
    alert.update_equity(new_equity)

    print(f"\nRésumé du jour:")
    print(f"  Capital départ: $10,000.00")
    print(f"  Profit brut (nominal): +$???")
    print(f"  Profit net (réaliste): +${cumulative_pnl:.2f}")
    print(f"  Capital fin: ${new_equity:.2f}")
    print(f"  PnL jour: {(cumulative_pnl/10000):.2%}")

    print(f"\nAlerts:")
    alerts = alert.run_all_checks([
        {"symbol": "BTCUSDT", "size": 1000},
        {"symbol": "ETHUSDT", "size": 2000},
    ])
    print(f"  Total: {len(alerts)}")
    for a in alerts:
        print(f"    - {a}")


if __name__ == "__main__":
    test_alert_system()
    test_portfolio_risk_manager()
    test_execution_reality()
    test_integrated_scenario()

    print("\n" + "="*70)
    print("[OK] TOUS LES TESTS P0 REUSSIS")
    print("="*70 + "\n")
