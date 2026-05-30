"""
Chaos #3 — Partial fill.

Simule une exécution partielle (fraction de l'ordre remplie par l'exchange).
Invariants vérifiés :
  - PaperTradingEngine : position et solde cohérents après partial fill
  - Pas de position négative si on vend plus que ce qu'on possède
  - PositionManager : qty partielle conservée sans corruption d'état
  - Plusieurs partial fills successifs restent cohérents
"""

from __future__ import annotations

from quant_hedge_ai.agents.execution.paper_trading_engine import PaperTradingEngine
from quant_hedge_ai.agents.execution.position_manager import (
    Position,
    PositionManager,
    PositionSide,
)

# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPartialFill:
    def test_partial_sell_leaves_correct_position(self):
        """Vendre 0.5 d'une position de 1.0 laisse exactement 0.5."""
        engine = PaperTradingEngine(initial_balance=100_000.0, persist=False)
        engine.execute(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 1.0}, mark_price=50_000.0
        )
        engine.execute(
            {"symbol": "BTC/USDT", "action": "SELL", "size": 0.5}, mark_price=51_000.0
        )

        remaining = engine.positions.get("BTC/USDT", 0.0)
        assert (
            abs(remaining - 0.5) < 1e-6
        ), f"INVARIANT BRISÉ: position restante = {remaining}, attendu 0.5"

    def test_partial_fill_balance_coherence(self):
        """Le solde après partial fill est entre le solde pré-achat et post-achat."""
        engine = PaperTradingEngine(initial_balance=100_000.0, persist=False)
        initial = engine.balance

        engine.execute(
            {"symbol": "ETH/USDT", "action": "BUY", "size": 2.0}, mark_price=3_000.0
        )
        after_buy = engine.balance

        engine.execute(
            {"symbol": "ETH/USDT", "action": "SELL", "size": 1.0}, mark_price=3_000.0
        )
        after_partial = engine.balance

        assert after_buy < after_partial <= initial, (
            f"INVARIANT BRISÉ: solde incohérent — "
            f"initial={initial}, after_buy={after_buy}, after_partial={after_partial}"
        )

    def test_oversell_no_negative_position(self):
        """Vendre plus que ce qu'on possède ne crée pas de position négative."""
        engine = PaperTradingEngine(initial_balance=100_000.0, persist=False)
        engine.execute(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.5}, mark_price=50_000.0
        )
        engine.execute(
            {"symbol": "BTC/USDT", "action": "SELL", "size": 1.0}, mark_price=50_000.0
        )

        remaining = engine.positions.get("BTC/USDT", 0.0)
        assert remaining >= 0.0, f"INVARIANT BRISÉ: position négative = {remaining}"

    def test_multiple_partial_fills_coherent(self):
        """3 ventes partielles de 0.25 sur 1.0 BTC laissent 0.25."""
        engine = PaperTradingEngine(initial_balance=100_000.0, persist=False)
        engine.execute(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 1.0}, mark_price=50_000.0
        )
        for _ in range(3):
            engine.execute(
                {"symbol": "BTC/USDT", "action": "SELL", "size": 0.25},
                mark_price=50_000.0,
            )

        remaining = engine.positions.get("BTC/USDT", 0.0)
        assert (
            abs(remaining - 0.25) < 1e-6
        ), f"INVARIANT BRISÉ: après 3 partial sells de 0.25, position = {remaining}"

    def test_position_manager_partial_qty_coherent(self):
        """PositionManager avec qty partielle conserve l'état sans corruption."""
        pm = PositionManager(exchange=None, paper_mode=True)
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            entry_price=50_000.0,
            size_usd=25_000.0,  # 0.5 BTC
            qty=0.5,
            use_atr=False,
        )
        pm.add_position(pos, silent=True)

        open_pos = pm.get_open()
        assert len(open_pos) == 1
        assert (
            abs(open_pos[0].qty - 0.5) < 1e-9
        ), f"INVARIANT BRISÉ: qty = {open_pos[0].qty}, attendu 0.5"
        assert abs(open_pos[0].size_usd - 25_000.0) < 1e-6

    def test_partial_fill_pnl_computable(self):
        """Une position avec qty partielle peut calculer son PnL sans erreur."""
        pm = PositionManager(exchange=None, paper_mode=True)
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.LONG,
            entry_price=3_000.0,
            size_usd=1_500.0,
            qty=0.5,
            use_atr=False,
        )
        pm.add_position(pos, silent=True)
        pos.update_price(3_300.0)

        assert (
            pos.pnl_pct > 0
        ), "Position LONG avec prix en hausse doit avoir PnL positif"
        assert pos.pnl_usd > 0

    def test_zero_size_buy_ignored(self):
        """Un BUY de taille 0 ne modifie pas le solde."""
        engine = PaperTradingEngine(initial_balance=100_000.0, persist=False)
        before = engine.balance
        engine.execute(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.0}, mark_price=50_000.0
        )
        assert engine.balance == before, "BUY de 0 ne doit pas modifier le solde"
