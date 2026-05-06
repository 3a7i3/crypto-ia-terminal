"""Test schema validation: SL/TP mandatory, comprehensive round-trip."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.core.trade_logger import log_entry, log_exit


class TrackerSchemaValidationTest(unittest.TestCase):
    """Validate canonical schema at write time."""

    def test_log_entry_requires_stop_loss(self) -> None:
        """Entry without stop_loss should raise ValueError."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            with self.assertRaises(ValueError) as ctx:
                log_entry(
                    "BTCUSDT", "BUY", 100.0, 50.0,
                    stop_loss=None, take_profit=110.0,
                    regime="bullish", confidence=0.8,
                    log_file=log_file,
                )
            self.assertIn("stop_loss", str(ctx.exception))

    def test_log_entry_requires_take_profit(self) -> None:
        """Entry without take_profit should raise ValueError."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            with self.assertRaises(ValueError) as ctx:
                log_entry(
                    "BTCUSDT", "BUY", 100.0, 50.0,
                    stop_loss=95.0, take_profit=None,
                    regime="bullish", confidence=0.8,
                    log_file=log_file,
                )
            self.assertIn("take_profit", str(ctx.exception))

    def test_log_entry_produces_canonical_schema(self) -> None:
        """Verify log_entry produces all canonical fields."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"

            event = log_entry(
                "BTCUSDT", "BUY", 100.0, 50.0,
                stop_loss=95.0, take_profit=110.0,
                regime="bullish", confidence=0.8,
                log_file=log_file,
                signal_type="momentum", score=77.0,
                atr_pct=0.5, paper=True, id="test-id",
            )

            # Verify canonical fields
            self.assertEqual(event["type"], "entry")
            self.assertEqual(event["symbol"], "BTCUSDT")
            self.assertEqual(event["side"], "BUY")
            self.assertEqual(event["direction"], "long")
            self.assertEqual(event["entry_price"], 100.0)
            self.assertEqual(event["size"], 50.0)
            self.assertEqual(event["size_usd"], 50.0)
            self.assertEqual(event["stop_loss"], 95.0)
            self.assertEqual(event["take_profit"], 110.0)
            self.assertEqual(event["regime"], "bullish")
            self.assertEqual(event["confidence"], 0.8)
            self.assertEqual(event["signal_type"], "momentum")
            self.assertEqual(event["score"], 77.0)
            self.assertEqual(event["atr_pct"], 0.5)
            self.assertEqual(event["paper"], True)
            self.assertIn("timestamp", event)
            self.assertIn("logged_at", event)

            # Verify file written
            self.assertTrue(log_file.exists())
            lines = log_file.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            written = json.loads(lines[0])
            self.assertEqual(written["type"], "entry")

    def test_log_exit_produces_canonical_schema(self) -> None:
        """Verify log_exit produces all canonical fields including MFE/MAE."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"

            position = {
                "id": "test-pos-1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 100.0,
                "size": 50.0,
                "regime": "bullish",
                "confidence": 0.8,
                "signal_type": "momentum",
                "price_path": [100.0, 101.0, 102.0, 101.5, 102.0],
            }

            event = log_exit(
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

            # Verify canonical fields
            self.assertEqual(event["type"], "exit")
            self.assertEqual(event["symbol"], "BTCUSDT")
            self.assertEqual(event["side"], "BUY")
            self.assertEqual(event["direction"], "long")
            self.assertEqual(event["entry_price"], 100.0)
            self.assertEqual(event["exit_price"], 102.0)
            self.assertEqual(event["size"], 50.0)
            self.assertEqual(event["size_usd"], 50.0)
            self.assertEqual(event["pnl_pct"], 0.02)
            self.assertEqual(event["pnl_usd"], 1.0)
            self.assertTrue(event["win"])
            self.assertEqual(event["mfe"], 0.02)
            self.assertEqual(event["mae"], -0.01)
            self.assertEqual(event["exit_reason"], "TP")
            self.assertEqual(event["duration_min"], 45.0)
            self.assertEqual(event["duration_minutes"], 45.0)
            self.assertEqual(event["regime"], "bullish")
            self.assertEqual(event["signal_type"], "momentum")
            self.assertIn("timestamp", event)
            self.assertIn("logged_at", event)


if __name__ == "__main__":
    unittest.main()
