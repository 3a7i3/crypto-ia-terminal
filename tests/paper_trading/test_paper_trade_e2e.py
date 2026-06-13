"""
tests/paper_trading/test_paper_trade_e2e.py — Preuve circuit complet paper trading.

Prouve la chaîne : Signal → Trade virtuel → TP/SL → Fermeture avec logs.

Utilise VirtualPortfolio (pas de thread background) pour contrôle direct
du cycle TP/SL via _check_positions().
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


class TestPaperTradeCompleteLifecycle:
    """Preuve : un trade complet de l'ouverture à la fermeture."""

    @pytest.fixture
    def notifications(self):
        return []

    @pytest.fixture
    def vp(self, notifications):
        from paper_trading.virtual_portfolio import VirtualPortfolio

        mock_reader = MagicMock()
        return VirtualPortfolio(
            mexc_reader=mock_reader,
            initial_capital=100.0,
            telegram_fn=lambda msg: notifications.append(msg),
        )

    def test_signal_to_tp_closure(self, vp, notifications, caplog):
        """
        PREUVE : Signal BUY → ouverture position → TP atteint → fermeture.

        Logs complets visibles avec pytest -s --log-cli-level=INFO.
        """
        with caplog.at_level(logging.INFO, logger="paper_trading.virtual_portfolio"):

            # ─── 1. SIGNAL ────────────────────────────────────────────────────
            # Simulateur reçoit un signal tradeable : BTC/USDT BUY score=75
            symbol = "BTC/USDT"
            entry_signal_price = 100_000.0

            pos = vp.open_position(
                symbol=symbol,
                side="buy",
                price=entry_signal_price,
                tp_pct=0.04,  # TP +4%
                sl_pct=0.02,  # SL -2%
                score=75,
                personality="momentum",
            )

        # Position ouverte
        assert pos is not None, "La position doit être ouverte suite au signal"
        assert pos.symbol == symbol
        assert pos.side == "buy"
        assert pos.is_open

        # Entry avec slippage +0.05%
        expected_entry = entry_signal_price * 1.0005
        assert (
            abs(pos.entry_price - expected_entry) < 1.0
        ), f"Entry attendu ~{expected_entry:.2f}, got {pos.entry_price:.2f}"

        # TP/SL calculés sur entry (pas sur prix signal)
        assert pos.tp_price > pos.entry_price, "TP doit être au-dessus de l'entry (BUY)"
        assert (
            pos.sl_price < pos.entry_price
        ), "SL doit être en-dessous de l'entry (BUY)"

        # Capital réduit après ouverture
        assert vp._capital < 100.0, "Capital doit être réduit après ouverture"

        # Notification ouverture envoyée
        assert len(notifications) >= 1
        open_notif = notifications[0]
        assert "SIM" in open_notif
        assert "BUY" in open_notif
        assert symbol in open_notif

        capital_after_open = vp._capital
        notifications.clear()

        # ─── 2. SURVEILLANCE ──────────────────────────────────────────────────
        # Prix monte : monitoring cycle, pas encore au TP
        mid_price = pos.entry_price * 1.02  # +2%, entre entry et TP
        vp._mexc.spot.fetch_ticker.return_value = {"last": mid_price}

        with caplog.at_level(logging.INFO, logger="paper_trading.virtual_portfolio"):
            vp._check_positions()

        # Position toujours ouverte (TP non atteint)
        assert symbol in vp._positions, "Position doit rester ouverte à mi-chemin"
        assert len(vp._closed) == 0

        # ─── 3. TP ATTEINT ───────────────────────────────────────────────────
        # Prix monte au-delà du TP
        tp_price = pos.tp_price * 1.001  # +0.1% au-dessus du TP
        vp._mexc.spot.fetch_ticker.return_value = {"last": tp_price}

        with caplog.at_level(logging.INFO, logger="paper_trading.virtual_portfolio"):
            vp._check_positions()

        # ─── 4. FERMETURE ─────────────────────────────────────────────────────
        assert symbol not in vp._positions, "Position doit être fermée après TP atteint"
        assert len(vp._closed) == 1

        closed = vp._closed[0]
        assert closed.close_reason == "TP"
        assert (
            closed.pnl_usd > 0
        ), f"TP doit produire un profit, got pnl={closed.pnl_usd:.4f}"
        assert closed.pnl_pct > 0

        # Capital augmenté après TP
        assert vp._capital > capital_after_open, "Capital doit augmenter après un TP"

        # Notification fermeture envoyée
        assert len(notifications) >= 1
        close_notif = notifications[0]
        assert "FERMETURE" in close_notif
        assert "TP" in close_notif
        assert symbol in close_notif
        assert "P&L" in close_notif

        # Rapport final cohérent
        report = vp.report()
        assert "1" in report  # 1 trade fermé
        assert "W=1" in report  # 1 win

    def test_signal_to_sl_closure(self, vp, notifications, caplog):
        """
        PREUVE : Signal BUY → ouverture → SL atteint → fermeture avec perte.
        """
        symbol = "ETH/USDT"
        entry_price = 3_000.0

        with caplog.at_level(logging.INFO, logger="paper_trading.virtual_portfolio"):
            pos = vp.open_position(
                symbol=symbol,
                side="buy",
                price=entry_price,
                tp_pct=0.04,
                sl_pct=0.02,
                score=60,
                personality="range",
            )

        assert pos is not None
        capital_after_open = vp._capital
        notifications.clear()

        # Prix chute sous le SL
        sl_price = pos.sl_price * 0.999  # légèrement sous le SL
        vp._mexc.spot.fetch_ticker.return_value = {"last": sl_price}

        with caplog.at_level(logging.INFO, logger="paper_trading.virtual_portfolio"):
            vp._check_positions()

        # Fermeture SL
        assert symbol not in vp._positions
        assert len(vp._closed) == 1
        closed = vp._closed[0]
        assert closed.close_reason == "SL"
        assert (
            closed.pnl_usd < 0
        ), f"SL doit produire une perte, got {closed.pnl_usd:.4f}"

        close_notif = notifications[0]
        assert "FERMETURE" in close_notif
        assert "SL" in close_notif

    def test_no_duplicate_positions(self, vp, notifications):
        """Un seul trade par symbole — second signal ignoré."""
        symbol = "SOL/USDT"

        pos1 = vp.open_position(
            symbol=symbol,
            side="buy",
            price=150.0,
            tp_pct=0.04,
            sl_pct=0.02,
            score=70,
            personality="momentum",
        )
        pos2 = vp.open_position(
            symbol=symbol,
            side="buy",
            price=155.0,
            tp_pct=0.04,
            sl_pct=0.02,
            score=71,
            personality="momentum",
        )

        assert pos1 is not None
        assert pos2 is None, "Second signal sur même symbole doit être ignoré"
        assert len(vp._positions) == 1

    def test_capital_insufficient_blocks_trade(self):
        """Capital insuffisant (<$5) bloque toute ouverture."""
        from paper_trading.virtual_portfolio import VirtualPortfolio

        vp = VirtualPortfolio(initial_capital=5.0)
        # 15% de $5 = $0.75 < minimum $5
        pos = vp.open_position(
            symbol="BTC/USDT",
            side="buy",
            price=100_000.0,
            tp_pct=0.04,
            sl_pct=0.02,
            score=80,
            personality="momentum",
        )
        assert pos is None, "Capital insuffisant doit bloquer l'ouverture"

    def test_mexc_simulator_market_order_complete(self):
        """
        PREUVE MexcSimulator : MARKET order → position ouverte → TP → fermeture.
        """
        from paper_trading.mexc_simulator import MexcSimulator

        notifications = []
        mock_reader = MagicMock()

        sim = MexcSimulator(
            mexc_reader=mock_reader,
            telegram_fn=lambda msg: notifications.append(msg),
        )
        sim._capital = 100.0
        sim._initial_capital = 100.0
        sim._running = True

        # 1. Ordre MARKET BUY
        order = sim.place_market_order(
            symbol="BTC/USDT",
            side="BUY",
            qty_usd=15.0,
            tp_pct=0.04,
            sl_pct=0.02,
            score=80,
            personality="momentum",
            current_price=100_000.0,
        )

        from paper_trading.mexc_simulator import OrderStatus

        assert order.status == OrderStatus.FILLED
        assert "BTC/USDT" in sim._positions

        pos = sim._positions["BTC/USDT"]
        capital_after = sim._capital
        notifications.clear()

        # 2. Prix atteint TP
        tp_price = pos.tp_price * 1.001
        mock_reader.spot.fetch_ticker.return_value = {"last": tp_price}
        sim._check_positions()

        # 3. Position fermée avec profit
        assert "BTC/USDT" not in sim._positions
        assert len(sim._closed) == 1
        closed = sim._closed[0]
        assert closed.close_reason == "TP"
        assert closed.pnl_usd > 0

        close_notif = notifications[0]
        assert (
            "TP" in close_notif
        )  # "FERMEE" supprimé du format de notification (→ "TP atteint")
        assert "BTC/USDT" in close_notif

        # Rapport de performance cohérent
        report = sim.performance_report()
        assert "W=1" in report
