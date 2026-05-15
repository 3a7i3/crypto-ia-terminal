"""
paper_trading/ — Moteur de paper trading avec friction réaliste (P5.1).

Composants :
  ledger.py  — PaperTrade, PaperLedger : suivi P&L avec coûts réels
  engine.py  — PaperTradingEngine : exécute les signaux advisor en paper

Usage :
    from paper_trading.engine import PaperTradingEngine
    from execution_simulator.config import binance_usdt_futures_simulator

    engine = PaperTradingEngine(
        simulator=binance_usdt_futures_simulator(),
        initial_capital=10_000.0,
    )
    engine.on_signal("BTCUSDT", "buy", price=65_000.0, size_usd=500.0)
    report = engine.report()
"""

from paper_trading.engine import PaperTradingEngine
from paper_trading.ledger import PaperLedger, PaperTrade

__all__ = ["PaperTrade", "PaperLedger", "PaperTradingEngine"]
