from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.core.trade_logger import log_entry, log_exit
import tracker_system.trade_tracker as legacy_trade_tracker
import tracker_system.tracker as legacy_dashboard


class TrackerSchemaCompatibilityTest(unittest.TestCase):
    def test_structured_events_remain_legacy_compatible(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            state_file = root / "open_positions.json"
            vault = root / "vault"

            original_log_file = legacy_trade_tracker.LOG_FILE
            original_state_file = legacy_trade_tracker.STATE_FILE
            try:
                legacy_trade_tracker.LOG_FILE = log_file
                legacy_trade_tracker.STATE_FILE = state_file

                log_entry(
                    "BTCUSDT",
                    "BUY",
                    100.0,
                    50.0,
                    regime="bullish",
                    confidence=0.8,
                    log_file=log_file,
                    id="pos-1",
                    stop_loss=95.0,
                    take_profit=110.0,
                    score=77,
                    signal_type="momentum",
                    paper=True,
                )

                added = legacy_trade_tracker.sync_from_log()
                self.assertEqual(added, 1)

                positions = legacy_trade_tracker.load_positions()
                self.assertEqual(len(positions), 1)
                self.assertEqual(positions[0]["direction"], "long")
                self.assertEqual(positions[0]["size_usd"], 50.0)
                self.assertEqual(positions[0]["signal_type"], "momentum")

                log_exit(
                    {
                        "id": "pos-1",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "signal_type": "momentum",
                        "regime": "bullish",
                        "entry_price": 100.0,
                        "size": 50.0,
                        "confidence": 0.8,
                        "paper": True,
                        "price_path": [100.0, 104.0, 102.0],
                    },
                    102.0,
                    0.02,
                    1.0,
                    0.04,
                    -0.01,
                    "TP",
                    15.0,
                    log_file=log_file,
                )

                exits = legacy_dashboard.load_exits(log_file)
                self.assertEqual(len(exits), 1)
                self.assertTrue(exits[0]["win"])
                self.assertEqual(exits[0]["duration_minutes"], 15.0)
                self.assertEqual(exits[0]["signal_type"], "momentum")

                legacy_dashboard.create_trade_note(exits[0], vault)
                notes = list((vault / "03_Trades").glob("*.md"))
                self.assertEqual(len(notes), 1)
            finally:
                legacy_trade_tracker.LOG_FILE = original_log_file
                legacy_trade_tracker.STATE_FILE = original_state_file


if __name__ == "__main__":
    unittest.main()
