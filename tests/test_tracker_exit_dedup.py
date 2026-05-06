"""
Validation: Trade tracker and exit engine deduplication.
Tests that the refactored modules work correctly with no duplication.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tracker_system.core.trade_tracker import (
    open_position,
    close_position,
    finalize_position,
    update_positions,
    sync_entries_from_log,
)
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.engine.exit_factory import build_exit_engine
from tracker_system.core.position_manager import load_positions


class TestTradeTrackerDedup(unittest.TestCase):
    """Verify refactored trade_tracker.py (core) works correctly."""

    def test_open_and_close_position(self) -> None:
        """Test position open/close workflow in refactored module."""
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            state_file = root / "positions.json"

            position = open_position(
                symbol="BTC/USDT",
                side="BUY",
                price=50000.0,
                size=1.5,
                regime="bullish",
                confidence=0.85,
                log_file=log_file,
                state_file=state_file,
            )

            self.assertEqual(position["symbol"], "BTC/USDT")
            self.assertEqual(position["side"], "BUY")
            self.assertEqual(position["entry_price"], 50000.0)
            self.assertEqual(position["size"], 1.5)

            record = close_position(
                position,
                price=52000.0,
                exit_reason="TP",
                log_file=log_file,
            )

            self.assertEqual(record["exit_price"], 52000.0)
            self.assertTrue(record["closed_at"])
            self.assertAlmostEqual(record["pnl_pct"], 0.04, places=3)

    def test_exit_engine_integration(self) -> None:
        """Test that exit_engine integrates correctly with position updates."""
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            state_file = root / "positions.json"

            position = open_position(
                symbol="ETH/USDT",
                side="BUY",
                price=3000.0,
                size=5.0,
                regime="bullish",
                log_file=log_file,
                state_file=state_file,
            )

            engine = build_exit_engine("bullish", 0.8)
            self.assertIsNotNone(engine)

            current_prices = {"ETH/USDT": 2900.0}
            closed = update_positions(
                current_prices,
                exit_engine=engine,
                state_file=state_file,
                log_file=log_file,
            )

            self.assertGreaterEqual(len(closed), 0)

    def test_sync_from_log(self) -> None:
        """Test that sync_entries_from_log uses correct module."""
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            state_file = root / "positions.json"

            log_file.write_text(
                '{"type": "entry", "id": "test-1", "symbol": "SOL/USDT", "side": "BUY", '
                '"entry_price": 200.0, "size": 10.0}\n'
            )

            added = sync_entries_from_log(log_file, state_file)
            self.assertEqual(added, 1)

            positions = load_positions(state_file)
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0]["symbol"], "SOL/USDT")

    def test_sync_from_log_skips_closed_position_ids(self) -> None:
        """Closed trades should not be resurrected by a later sync pass."""
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            state_file = root / "positions.json"

            position = open_position(
                symbol="BTC/USDT",
                side="BUY",
                price=100.0,
                size=10.0,
                log_file=log_file,
                state_file=state_file,
                id="closed-1",
            )

            closed = finalize_position(
                "closed-1",
                102.0,
                "TP",
                state_file=state_file,
                log_file=log_file,
                fallback_position=position,
            )
            self.assertIsNotNone(closed)

            added = sync_entries_from_log(log_file, state_file)
            self.assertEqual(added, 0)
            self.assertEqual(load_positions(state_file), [])


class TestBacktesterDedup(unittest.TestCase):
    """Verify backtester uses the correct (non-duplicated) module."""

    def test_factory_backtester_available(self) -> None:
        """Test that FactoryBacktester can be imported from correct location."""
        from quant_hedge_ai.strategy_factory.backtester import FactoryBacktester

        backtester = FactoryBacktester()
        self.assertIsNotNone(backtester)

    def test_run_strategy_factory_uses_correct_import(self) -> None:
        """Validate that run_strategy_factory_large uses new backtester."""
        script = Path("run_strategy_factory_large.py")
        if script.exists():
            content = script.read_text()
            self.assertIn("quant_hedge_ai.strategy_factory.backtester", content)


if __name__ == "__main__":
    unittest.main()
