"""Test MVP→Tracker logger refactoring produces compatible events."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.core.event_writer import record_entry_from_mvp, record_exit_from_mvp
import tracker_system.core.trade_tracker as core_tracker
import tracker_system.tracker as legacy_dashboard


class TrackerMVPRefactorTest(unittest.TestCase):
    """Verify MVP adapter produces events compatible with all readers."""

    def test_mvp_adapter_entry_roundtrip(self) -> None:
        """MVP adapter entry → core tracker sync → legacy readers."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            state_file = Path(tmp_dir) / "positions.json"

            # MVP adapter call (simulating mvp_orchestrator)
            event = record_entry_from_mvp(
                symbol="BTCUSDT",
                direction="long",          # MVP uses direction
                signal_type="momentum",
                regime="bullish",
                entry_price=100.0,
                size_usd=50.0,             # MVP uses size_usd
                stop_loss=95.0,
                take_profit=110.0,
                score=77.0,
                confidence=0.8,
                atr_pct=0.5,
                paper=True,
                log_file=log_file,
            )

            # Verify canonical schema
            self.assertEqual(event["type"], "entry")
            self.assertEqual(event["side"], "BUY")  # Normalized from "long"
            self.assertEqual(event["direction"], "long")  # Legacy alias
            self.assertEqual(event["size"], 50.0)
            self.assertEqual(event["size_usd"], 50.0)
            self.assertEqual(event["stop_loss"], 95.0)
            self.assertEqual(event["take_profit"], 110.0)

            # Core tracker reads it
            added = core_tracker.sync_entries_from_log(log_file, state_file)
            self.assertEqual(added, 1)

            positions = core_tracker.load_positions(state_file)
            pos = positions[0]
            self.assertEqual(pos["symbol"], "BTCUSDT")
            self.assertEqual(pos["side"], "BUY")
            self.assertEqual(pos["size"], 50.0)
            self.assertEqual(pos["stop_loss"], 95.0)
            self.assertEqual(pos["take_profit"], 110.0)

    def test_mvp_adapter_exit_roundtrip(self) -> None:
        """MVP adapter exit → legacy dashboard readers."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            vault = Path(tmp_dir) / "vault"

            # MVP adapter exit call (simulating mvp_orchestrator)
            event = record_exit_from_mvp(
                symbol="BTCUSDT",
                direction="long",
                signal_type="momentum",
                regime="bullish",
                entry_price=100.0,
                exit_price=102.0,
                size_usd=50.0,
                pnl_usd=1.0,
                pnl_pct=0.02,
                exit_reason="TP",
                duration_minutes=45.0,
                attribution="validated",
                fee_usd=0.02,
                price_path=[100.0, 101.0, 102.0],
                log_file=log_file,
            )

            # Verify canonical schema
            self.assertEqual(event["type"], "exit")
            self.assertEqual(event["symbol"], "BTCUSDT")
            self.assertEqual(event["pnl_usd"], 1.0)
            self.assertTrue(event["win"])
            self.assertIn("mfe", event)
            self.assertIn("mae", event)

            # Legacy dashboard reads it
            exits = legacy_dashboard.load_exits(log_file)
            self.assertEqual(len(exits), 1)

            trade = exits[0]
            self.assertEqual(trade["symbol"], "BTCUSDT")
            self.assertEqual(trade["pnl_usd"], 1.0)
            self.assertTrue(trade["win"])

            # Dashboard creates note
            legacy_dashboard.create_trade_note(trade, vault)
            notes = list((vault / "03_Trades").glob("*.md"))
            self.assertEqual(len(notes), 1)

    def test_mvp_adapter_direction_normalization(self) -> None:
        """MVP adapter normalizes direction values."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"

            for mvp_direction, expected_side in [
                ("long", "BUY"),
                ("short", "SELL"),
                ("LONG", "BUY"),
                ("SHORT", "SELL"),
            ]:
                log_file.unlink(missing_ok=True)

                event = record_entry_from_mvp(
                    symbol="TEST",
                    direction=mvp_direction,
                    signal_type="test",
                    regime="test",
                    entry_price=100.0,
                    size_usd=10.0,
                    stop_loss=95.0,
                    take_profit=105.0,
                    score=50.0,
                    confidence=0.5,
                    atr_pct=0.1,
                    paper=True,
                    log_file=log_file,
                )

                self.assertEqual(event["side"], expected_side)

    def test_mvp_adapter_exit_mfe_mae_calculation(self) -> None:
        """MVP adapter computes MFE/MAE correctly from price_path."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"

            # LONG position: mfe = max-entry, mae = min-entry
            event_long = record_exit_from_mvp(
                symbol="TEST",
                direction="long",
                signal_type="test",
                regime="test",
                entry_price=100.0,
                exit_price=101.0,
                size_usd=10.0,
                pnl_usd=0.1,
                pnl_pct=0.01,
                exit_reason="TP",
                duration_minutes=30.0,
                attribution="test",
                fee_usd=0.0,
                price_path=[100.0, 102.0, 101.0, 101.5],
                log_file=log_file,
            )

            self.assertEqual(event_long["mfe"], 0.02)  # (102-100)/100
            self.assertEqual(event_long["mae"], 0.0)  # (100-100)/100

            log_file.unlink()

            # SHORT position: mfe = entry-min, mae = entry-max
            event_short = record_exit_from_mvp(
                symbol="TEST",
                direction="short",
                signal_type="test",
                regime="test",
                entry_price=100.0,
                exit_price=99.0,
                size_usd=10.0,
                pnl_usd=0.1,
                pnl_pct=0.01,
                exit_reason="TP",
                duration_minutes=30.0,
                attribution="test",
                fee_usd=0.0,
                price_path=[100.0, 98.0, 99.0, 99.5],
                log_file=log_file,
            )

            self.assertEqual(event_short["mfe"], 0.02)  # (100-98)/100
            self.assertEqual(event_short["mae"], 0.0)  # (100-100)/100


if __name__ == "__main__":
    unittest.main()
