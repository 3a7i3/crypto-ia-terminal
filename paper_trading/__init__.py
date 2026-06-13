"""
paper_trading/ — Infrastructure de simulation burn-in avec friction réaliste (P5.1).

Composants :
  ledger.py  — PaperTrade, PaperLedger : suivi P&L avec coûts réels
  engine.py  — BurninSimulationEngine : simule les signaux advisor en burn-in

Usage :
    from paper_trading.engine import BurninSimulationEngine
    from execution_simulator.config import binance_usdt_futures_simulator

    engine = BurninSimulationEngine(
        simulator=binance_usdt_futures_simulator(),
        initial_capital=10_000.0,
    )
    engine.on_signal("BTCUSDT", "buy", price=65_000.0, size_usd=500.0)
    report = engine.report()
"""

from paper_trading.engine import BurninSimulationEngine
from paper_trading.ledger import PaperLedger, PaperTrade

__all__ = ["PaperTrade", "PaperLedger", "BurninSimulationEngine"]
