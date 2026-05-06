from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tracker_system.backtesting.auto_backtester import run_backtest
from tracker_system.config import exit_config
from tracker_system.storage.saver import append_jsonl, save_json


class TrackerOptimizerConfigTest(unittest.TestCase):
    def test_get_exit_config_ignores_under_sampled_optimizer_payload(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            optimizer_file = root / "optimizer.json"
            original_optimizer_file = exit_config.OPTIMIZER_FILE
            try:
                exit_config.OPTIMIZER_FILE = optimizer_file
                save_json(
                    optimizer_file,
                    {
                        "bullish": {
                            "tp": 0.05,
                            "sl": 0.02,
                            "trailing": 0.01,
                            "samples": exit_config.MIN_OPTIMIZER_SAMPLES - 1,
                        }
                    },
                )

                config = exit_config.get_exit_config("bullish")
                self.assertEqual(config["tp"], exit_config.EXIT_CONFIG["bullish"]["tp"])
                self.assertEqual(config["sl"], exit_config.EXIT_CONFIG["bullish"]["sl"])
                self.assertEqual(config["trailing"], exit_config.EXIT_CONFIG["bullish"]["trailing"])
            finally:
                exit_config.OPTIMIZER_FILE = original_optimizer_file

    def test_get_exit_config_applies_optimizer_payload_after_min_samples(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            optimizer_file = root / "optimizer.json"
            original_optimizer_file = exit_config.OPTIMIZER_FILE
            try:
                exit_config.OPTIMIZER_FILE = optimizer_file
                save_json(
                    optimizer_file,
                    {
                        "bullish": {
                            "tp": 0.05,
                            "sl": 0.02,
                            "trailing": 0.01,
                            "samples": exit_config.MIN_OPTIMIZER_SAMPLES,
                        }
                    },
                )

                config = exit_config.get_exit_config("bullish")
                self.assertEqual(config["tp"], 0.05)
                self.assertEqual(config["sl"], 0.02)
                self.assertEqual(config["trailing"], 0.01)
            finally:
                exit_config.OPTIMIZER_FILE = original_optimizer_file

    def test_run_backtest_tracks_skipped_regimes_in_meta(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            log_file = root / "trades.jsonl"
            out_file = root / "optimizer.json"

            for pnl in (1.0, -0.5):
                append_jsonl(
                    log_file,
                    {
                        "type": "exit",
                        "symbol": "BTCUSDT",
                        "regime": "bullish",
                        "pnl_usd": pnl,
                        "pnl_pct": pnl / 100,
                        "price_path": [100.0, 101.0, 102.0],
                        "entry_price": 100.0,
                        "side": "BUY",
                    },
                )

            result = run_backtest(min_trades=3, log_file=log_file, out_file=out_file)
            self.assertEqual(result["_meta"]["skipped_regimes"], {"bullish": 2})
            self.assertNotIn("bullish", result)


if __name__ == "__main__":
    unittest.main()