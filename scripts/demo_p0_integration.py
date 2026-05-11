#!/usr/bin/env python3
"""
INTÉGRATION P0 — Démo complète avec AlertSystem + PortfolioRisk + ExecutionReality
Montre comment utiliser P0Manager dans un workflow trading réaliste
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.p0_integration import create_default_p0_manager


def demo_trading_day():
    """Simulation d'une journée de trading avec P0"""

    print("\n" + "="*70)
    print("DEMO INTEGRATION P0 — JOURNEE DE TRADING REALISTE")
    print("="*70)

    # Initialiser P0
    p0 = create_default_p0_manager(initial_capital=10000.0)
    print("\n[INIT] P0Manager créé")
    print("  Capital initial: $10,000.00")
    print("  Max perte jour: -$100")
    print("  Max drawdown: 15%")
    print("  Max exposure: 80%")

    # ========================================================================
    # MATIN: OUVERTURE POSITIONS
    # ========================================================================
    print("\n" + "-"*70)
    print("[MATIN] VALIDATION ET OUVERTURE POSITIONS")
    print("-"*70)

    open_positions = []

    # Position 1: BTCUSDT
    print("\n1. BTCUSDT 0.1 BTC @ $50,000")
    valide, raison, suggested = p0.validate_position_before_open(
        symbol="BTCUSDT",
        size=5000,
        current_positions=[],
        estimated_price=1.0
    )
    print(f"   Validation: {valide}")
    print(f"   Raison: {raison}")
    if suggested:
        print(f"   Taille suggeree: ${suggested:.2f}")

    open_positions.append({"symbol": "BTCUSDT", "size": 5000})

    # Position 2: ETHUSDT
    print("\n2. ETHUSDT 2.0 ETH @ $2,500")
    valide, raison, suggested = p0.validate_position_before_open(
        symbol="ETHUSDT",
        size=5000,
        current_positions=open_positions,
        estimated_price=1.0
    )
    print(f"   Validation: {valide}")
    print(f"   Raison: {raison}")

    open_positions.append({"symbol": "ETHUSDT", "size": 5000})

    # Position 3: BNBUSDT (devrait être rejetée pour concentration)
    print("\n3. BNBUSDT 10 BNB @ $600 (tentative position 3)")
    valide, raison, suggested = p0.validate_position_before_open(
        symbol="BNBUSDT",
        size=6000,
        current_positions=open_positions,
        estimated_price=1.0
    )
    print(f"   Validation: {valide}")
    print(f"   Raison: {raison}")

    if not valide:
        print("   => Position REJETEE — exposition totale trop haute")
    else:
        open_positions.append({"symbol": "BNBUSDT", "size": 6000})

    print(f"\nPositions ouvertes: {len(open_positions)}")
    for pos in open_positions:
        print(f"  - {pos['symbol']}: ${pos['size']:.0f}")

    # ========================================================================
    # MID-DAY: EXECUTION PREMIER TRADE
    # ========================================================================
    print("\n" + "-"*70)
    print("[MID-DAY] EXECUTION PREMIER TRADE")
    print("-"*70)

    print("\nTrade 1: BTCUSDT BUY @ 50000 -> EXIT @ 50500 (0.1 BTC)")
    trade1 = p0.record_trade_with_reality(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=50000.0,
        exit_price=50500.0,
        quantity=0.1
    )

    print(f"\n  PnL NOMINAL: +{trade1['pnl_nominal_pct']:.3%} = ${trade1['pnl_nominal']:.2f}")
    print(f"  PnL RÉALISTE: {trade1['pnl_realistic_pct']:+.3%} = ${trade1['pnl_realistic']:.2f}")
    print(f"  Friction: -${abs(trade1['friction_cost']):.2f} ({abs(trade1['friction_pct']):.2%})")

    # Update equity et check alerts
    new_equity = 10000.0 + trade1['pnl_realistic']
    alerts = p0.update_equity_and_check_alerts(new_equity, open_positions)

    if alerts:
        print(f"\n  ALERTES: {len(alerts)}")
        for alert in alerts:
            print(f"    - {alert}")
    else:
        print(f"\n  Pas d'alertes. Equity: ${new_equity:.2f}")

    # ========================================================================
    # APRES-MIDI: AUTRE TRADE
    # ========================================================================
    print("\n" + "-"*70)
    print("[APRES-MIDI] DEUXIEME TRADE")
    print("-"*70)

    print("\nTrade 2: ETHUSDT BUY @ 2500 ->  EXIT @ 2450 (2.0 ETH)")
    trade2 = p0.record_trade_with_reality(
        symbol="ETHUSDT",
        side="BUY",
        entry_price=2500.0,
        exit_price=2450.0,
        quantity=2.0
    )

    print(f"\n  PnL NOMINAL: {trade2['pnl_nominal_pct']:.3%} = ${trade2['pnl_nominal']:.2f}")
    print(f"  PnL RÉALISTE: {trade2['pnl_realistic_pct']:.3%} = ${trade2['pnl_realistic']:.2f}")
    print(f"  Friction: -${abs(trade2['friction_cost']):.2f}")

    new_equity += trade2['pnl_realistic']
    alerts = p0.update_equity_and_check_alerts(new_equity, open_positions)

    print(f"\n  Equity: ${new_equity:.2f}")
    if alerts:
        print(f"  Alertes: {len(alerts)}")

    # ========================================================================
    # CLÔTURE: RESUME JOURNEE
    # ========================================================================
    print("\n" + "="*70)
    print("[RESUME JOURNEE]")
    print("="*70)

    summary = p0.get_trades_summary()
    portfolio = p0.get_portfolio_summary(open_positions)

    print("\nTRADES EXÉCUTÉS:")
    print(f"  Total trades: {summary['total_trades']}")
    print(f"  PnL nominal: +${summary['total_pnl_nominal']:.2f}")
    print(f"  PnL réaliste: +${summary['total_pnl_realistic']:.2f}")
    print(f"  Friction totale: -${abs(summary['total_friction']):.2f}")
    print(f"  Impact friction: {abs(summary['friction_impact_pct']):.2%}")

    print("\nPORTEFEUILLE:")
    print(f"  Positions ouvertes: {portfolio['total_positions']}")
    print(f"  Exposition totale: ${portfolio['total_exposure']:.0f}")
    print(f"  Ratio exposition: {portfolio['exposure_ratio']:.1%}")
    print(f"  Limites respectées: {portfolio['within_limits']}")

    print("\nRISQUES:")
    alert_summary = portfolio['alert_summary']
    print(f"  Equity courante: ${alert_summary['current_equity']:.2f}")
    print(f"  Drawdown actuel: {alert_summary['drawdown']:.1%}")
    print(f"  Total alertes: {alert_summary['total_alerts']}")
    print(f"  Alertes critiques: {alert_summary['critical_alerts']}")

    print("\nRECOMMENDATIONS:")
    for rec in portfolio.get('recommendations', []):
        print(f"  - {rec}")

    # ========================================================================
    # ESTIMATION IMPACT
    # ========================================================================
    print("\n" + "="*70)
    print("[IMPACT FRICTION SUR 100 TRADES]")
    print("="*70)

    impact = p0.get_friction_impact(num_trades=100, avg_pnl=0.005)
    print(f"\n{impact['message']}")
    print(f"  ->  Perte sur compte 10k: ${impact['example_on_10000_account']:.2f}")

    print("\n" + "="*70)
    print("[OK] DEMO INTEGRATION P0 COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    demo_trading_day()
