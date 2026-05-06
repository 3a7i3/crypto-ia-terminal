"""
Test d'intégration complet: entry → tracking → exit → logs
C'est LE test qui valide que le système marche en prod.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
import time

from tracker_system.core.trade_tracker import (
    open_position,
    close_position,
    update_positions,
)
from tracker_system.engine.composite_exit_engine import CompositeExitEngine
from tracker_system.engine.exit_rules import (
    StopLossRule,
    TakeProfitRule,
    TimeExitRule,
)
from tracker_system.core.position_manager import load_positions


class TestFullTradeLifecycle(unittest.TestCase):
    """Test d'intégration: signal → entry → tracking → exit → PnL → logs."""

    def setUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.log_file = self.root / "trades.jsonl"
        self.state_file = self.root / "positions.json"
        self.decision_log = self.root / "exit_decisions.jsonl"

        # Moteur d'exit avec règles simples
        self.exit_engine = CompositeExitEngine(
            rules=[
                StopLossRule(),
                TakeProfitRule(),
                TimeExitRule(max_duration_min=1.0),  # Court pour test
            ],
            decision_log_file=self.decision_log,
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_lifecycle_1_long_tp_hit(self) -> None:
        """Lifecycle: LONG → TP touché → PnL positif."""
        # === ÉTAPE 1: SIGNAL → ENTRY ===
        position = open_position(
            symbol="BTC/USDT",
            side="BUY",
            price=50000.0,
            size=1.0,
            regime="bullish",
            confidence=0.85,
            log_file=self.log_file,
            state_file=self.state_file,
            stop_loss=49000.0,
            take_profit=52000.0,
        )

        # Vérifie que la position est ouverte
        positions = load_positions(self.state_file)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "BTC/USDT")
        self.assertEqual(positions[0]["entry_price"], 50000.0)

        # === ÉTAPE 2: TRACKING → PRIX MONTE ===
        # Simule path de prix: 50k → 51k → 52k (TP touché)
        current_prices = {"BTC/USDT": 50500.0}
        closed = update_positions(
            current_prices,
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )
        self.assertEqual(len(closed), 0, "Position ne devrait pas fermer à 50.5k")

        current_prices = {"BTC/USDT": 52000.0}
        closed = update_positions(
            current_prices,
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )

        # === ÉTAPE 3: EXIT → PnL ===
        self.assertEqual(len(closed), 1, "Position devrait fermer à 52k (TP)")
        closed_pos = closed[0]

        self.assertEqual(closed_pos["symbol"], "BTC/USDT")
        self.assertEqual(closed_pos["exit_price"], 52000.0)
        self.assertTrue(closed_pos["win"], "Trade doit être gagnant")
        self.assertAlmostEqual(closed_pos["pnl_pct"], 0.04, places=3)  # +4%

        # === ÉTAPE 4: LOGS ===
        # Vérifie que le trade est enregistré
        trades = self._load_trades_log()
        exits = [t for t in trades if t.get("type") == "exit"]
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0]["pnl_pct"], closed_pos["pnl_pct"])

        # Vérifie que les décisions d'exit sont loggées
        decisions = self._load_decision_log()
        self.assertGreater(len(decisions), 0, "Devrait avoir au moins 1 décision loggée")
        self.assertIn("TP", decisions[0]["chosen"]["action"])

    def test_lifecycle_2_short_sl_hit(self) -> None:
        """Lifecycle: SHORT → SL touché → PnL négatif."""
        position = open_position(
            symbol="ETH/USDT",
            side="SELL",
            price=3000.0,
            size=5.0,
            regime="bearish",
            stop_loss=3100.0,
            take_profit=2800.0,
            log_file=self.log_file,
            state_file=self.state_file,
        )

        # Simule path: 3000 → 3050 → 3100 (SL touché)
        current_prices = {"ETH/USDT": 3050.0}
        closed = update_positions(
            current_prices,
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )
        self.assertEqual(len(closed), 0)

        current_prices = {"ETH/USDT": 3100.0}
        closed = update_positions(
            current_prices,
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )

        self.assertEqual(len(closed), 1)
        closed_pos = closed[0]

        self.assertFalse(closed_pos["win"], "Trade SHORT doit être perdant")
        self.assertAlmostEqual(closed_pos["pnl_pct"], -0.0333, places=3)  # -3.33%
        self.assertLess(closed_pos["pnl_usd"], 0, "PnL doit être négatif")

    def test_lifecycle_3_multiple_positions(self) -> None:
        """Lifecycle: Plusieurs positions en parallèle."""
        pos1 = open_position(
            symbol="BTC/USDT",
            side="BUY",
            price=50000.0,
            size=1.0,
            stop_loss=49000.0,
            take_profit=51000.0,
            log_file=self.log_file,
            state_file=self.state_file,
        )

        pos2 = open_position(
            symbol="ETH/USDT",
            side="BUY",
            price=3000.0,
            size=5.0,
            stop_loss=2900.0,
            take_profit=3100.0,
            log_file=self.log_file,
            state_file=self.state_file,
        )

        # Vérifier 2 positions ouvertes
        positions = load_positions(self.state_file)
        self.assertEqual(len(positions), 2)

        # BTC touche TP, ETH reste ouvert
        current_prices = {"BTC/USDT": 51000.0, "ETH/USDT": 3050.0}
        closed = update_positions(
            current_prices,
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )

        self.assertEqual(len(closed), 1, "Seul BTC doit fermer")
        positions = load_positions(self.state_file)
        self.assertEqual(len(positions), 1, "Une position doit rester ouverte")
        self.assertEqual(positions[0]["symbol"], "ETH/USDT")

    def test_lifecycle_4_audit_trail(self) -> None:
        """Vérifie l'audit trail complet."""
        # Ouvre position
        open_position(
            symbol="SOL/USDT",
            side="BUY",
            price=200.0,
            size=10.0,
            stop_loss=190.0,
            take_profit=210.0,
            log_file=self.log_file,
            state_file=self.state_file,
        )

        # Simule prix → TP
        update_positions(
            {"SOL/USDT": 210.0},
            exit_engine=self.exit_engine,
            state_file=self.state_file,
            log_file=self.log_file,
        )

        # === AUDIT: Tous les logs sont-ils présents? ===
        trades = self._load_trades_log()
        entries = [t for t in trades if t.get("type") == "entry"]
        exits = [t for t in trades if t.get("type") == "exit"]

        self.assertEqual(len(entries), 1)
        self.assertEqual(len(exits), 1)

        decisions = self._load_decision_log()
        self.assertGreater(len(decisions), 0)
        decision = decisions[0]
        self.assertEqual(decision["symbol"], "SOL/USDT")
        self.assertIn("TP", decision["chosen"]["action"])

    def _load_trades_log(self) -> list[dict]:
        """Charge logs/trades.jsonl."""
        if not self.log_file.exists():
            return []
        trades = []
        with self.log_file.open("r") as f:
            for line in f:
                try:
                    trades.append(json.loads(line))
                except Exception:
                    pass
        return trades

    def _load_decision_log(self) -> list[dict]:
        """Charge logs/exit_decisions.jsonl."""
        if not self.decision_log.exists():
            return []
        decisions = []
        with self.decision_log.open("r") as f:
            for line in f:
                try:
                    decisions.append(json.loads(line))
                except Exception:
                    pass
        return decisions


if __name__ == "__main__":
    unittest.main()
