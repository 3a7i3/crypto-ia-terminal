"""Test backward compatibility: legacy readers handle new events."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.core.trade_logger import log_exit
import tracker_system.tracker as legacy_dashboard


class TrackerBackwardCompatTest(unittest.TestCase):
    """Verify legacy readers work with new canonical events."""

    def test_dashboard_reads_exit_with_mfe_mae(self) -> None:
        """Dashboard should gracefully handle MFE/MAE fields."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            vault = Path(tmp_dir) / "vault"

            position = {
                "id": "test-exit-1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 100.0,
                "size": 50.0,
                "regime": "bullish",
                "confidence": 0.8,
                "signal_type": "momentum",
                "score": 77.0,
                "price_path": [100.0, 101.0, 102.0, 101.5, 102.0],
            }

            log_exit(
                position,
                exit_price=102.0,
                pnl_pct=0.02,
                pnl_usd=1.0,
                mfe=0.02,
                mae=-0.01,
                exit_reason="TP",
                duration_min=45.0,
                log_file=log_file,
            )

            # Legacy reader
            exits = legacy_dashboard.load_exits(log_file)
            self.assertEqual(len(exits), 1)

            trade = exits[0]
            self.assertEqual(trade["symbol"], "BTCUSDT")
            self.assertEqual(trade["pnl_usd"], 1.0)
            self.assertEqual(trade["pnl_pct"], 0.02)
            self.assertTrue(trade["win"])
            self.assertEqual(trade["mfe"], 0.02)
            self.assertEqual(trade["mae"], -0.01)
            self.assertEqual(trade["duration_minutes"], 45.0)

            # Dashboard should create note without crashing
            legacy_dashboard.create_trade_note(trade, vault)
            notes = list((vault / "03_Trades").glob("*.md"))
            self.assertEqual(len(notes), 1)

    def test_dashboard_reads_missing_optional_fields(self) -> None:
        """Dashboard handles missing optional fields with defaults."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            vault = Path(tmp_dir) / "vault"

            position = {
                "id": "minimal-exit",
                "symbol": "DOGEUSDT",
                "side": "SELL",
                "entry_price": 0.50,
                "size": 100.0,
                "price_path": [0.50, 0.49, 0.48],
            }

            log_exit(
                position,
                exit_price=0.48,
                pnl_pct=-0.04,
                pnl_usd=-2.0,
                mfe=0.0,
                mae=-0.04,
                exit_reason="SL",
                duration_min=10.0,
                log_file=log_file,
            )

            exits = legacy_dashboard.load_exits(log_file)
            self.assertEqual(len(exits), 1)

            trade = exits[0]
            # Fields with defaults should work
            self.assertEqual(trade.get("regime", "unknown"), "unknown")
            self.assertEqual(trade.get("confidence", 0), 0)
            self.assertEqual(trade.get("signal_type", "unknown"), "unknown")

            # Dashboard should still function
            legacy_dashboard.create_trade_note(trade, vault)
            notes = list((vault / "03_Trades").glob("*.md"))
            self.assertEqual(len(notes), 1)

    def test_dashboard_builds_metrics_from_mixed_events(self) -> None:
        """Dashboard metrics aggregation works with mixed event formats."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            vault = Path(tmp_dir) / "vault"

            # Create diverse exit events
            for i, (direction, side) in enumerate([("long", "BUY"), ("short", "SELL")]):
                position = {
                    "id": f"pos-{i}",
                    "symbol": f"TEST{i}USDT",
                    "side": side,
                    "entry_price": 100.0,
                    "size": 10.0,
                    "regime": "bullish" if direction == "long" else "bearish",
                    "price_path": [100.0, 102.0] if direction == "long" else [100.0, 98.0],
                }

                pnl_pct = 0.02 if direction == "long" else -0.02
                pnl_usd = 0.2 if direction == "long" else -0.2

                log_exit(
                    position,
                    exit_price=102.0 if direction == "long" else 98.0,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    mfe=0.02,
                    mae=-0.01,
                    exit_reason="TP",
                    duration_min=60.0,
                    log_file=log_file,
                )

            # Dashboard aggregation
            exits = legacy_dashboard.load_exits(log_file)
            self.assertEqual(len(exits), 2)

            legacy_dashboard.update_dashboard(exits, vault)
            dashboard_file = vault / "06_Dashboard" / "dashboard.md"
            self.assertTrue(dashboard_file.exists())

            content = dashboard_file.read_text(encoding="utf-8")
            self.assertIn("Performance", content)
            self.assertIn("Winrate", content)


if __name__ == "__main__":
    unittest.main()
