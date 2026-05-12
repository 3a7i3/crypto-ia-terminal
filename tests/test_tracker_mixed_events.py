"""Test mixed MVP and structured logger events in same JSONL."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.core.trade_logger import log_entry
from tracker_system.core.event_writer import record_entry_from_mvp
import tracker_system.core.trade_tracker as core_tracker


class TrackerMixedEventsTest(unittest.TestCase):
    """Verify mixed MVP and structured events can coexist safely."""

    def test_sync_mixed_mvp_and_structured_entries(self) -> None:
        """Sync handles entries from both MVP and structured loggers."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            state_file = Path(tmp_dir) / "positions.json"

            # Write MVP entry (via adapter)
            record_entry_from_mvp(
                "BTCUSDT", "long", "momentum", "bullish",
                100.0, 50.0, 95.0, 110.0,
                77.0, 0.8, 0.5, True,
                log_file=log_file,
            )

            # Write structured entry directly
            log_entry(
                "ETHUSDT", "SELL", 2000.0, 10.0,
                stop_loss=2050.0, take_profit=1950.0,
                regime="bearish", confidence=0.7,
                log_file=log_file,
                signal_type="support", score=65.0,
            )

            # Sync should read both
            positions = core_tracker.load_positions(state_file)
            self.assertEqual(len(positions), 0)

            added = core_tracker.sync_entries_from_log(log_file, state_file)
            self.assertEqual(added, 2)

            positions = core_tracker.load_positions(state_file)
            self.assertEqual(len(positions), 2)

            # Check MVP entry (should be normalized)
            mvp_pos = next(p for p in positions if p["symbol"] == "BTCUSDT")
            self.assertEqual(mvp_pos["side"], "BUY")
            self.assertEqual(mvp_pos["size"], 50.0)
            self.assertEqual(mvp_pos["stop_loss"], 95.0)
            self.assertEqual(mvp_pos["take_profit"], 110.0)
            self.assertEqual(mvp_pos["signal_type"], "momentum")

            # Check structured entry (should pass through)
            structured_pos = next(p for p in positions if p["symbol"] == "ETHUSDT")
            self.assertEqual(structured_pos["side"], "SELL")
            self.assertEqual(structured_pos["size"], 10.0)
            self.assertEqual(structured_pos["stop_loss"], 2050.0)
            self.assertEqual(structured_pos["take_profit"], 1950.0)
            self.assertEqual(structured_pos["signal_type"], "support")

    def test_sync_handles_legacy_entries_without_sl_tp(self) -> None:
        """Sync handles legacy entries that lack SL/TP (uses defaults)."""
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "trades.jsonl"
            state_file = Path(tmp_dir) / "positions.json"

            # Write legacy event manually (without SL/TP)
            legacy_event = {
                "type": "entry",
                "symbol": "BNBUSDT",
                "side": "BUY",
                "direction": "long",
                "entry_price": 500.0,
                "size": 10.0,
                "size_usd": 10.0,
                "regime": "bullish",
                "confidence": 0.7,
                "signal_type": "breakout",
                "score": 80.0,
                "atr_pct": 0.3,
                "paper": True,
                "timestamp": "2026-05-05T10:00:00+00:00",
            }
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("w") as f:
                f.write(json.dumps(legacy_event) + "\n")

            added = core_tracker.sync_entries_from_log(log_file, state_file)
            self.assertEqual(added, 1)

            positions = core_tracker.load_positions(state_file)
            self.assertEqual(len(positions), 1)

            pos = positions[0]
            self.assertEqual(pos["symbol"], "BNBUSDT")
            self.assertEqual(pos["stop_loss"], 0.0)  # Default
            self.assertEqual(pos["take_profit"], 0.0)  # Default


if __name__ == "__main__":
    unittest.main()
