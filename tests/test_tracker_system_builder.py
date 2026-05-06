from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.dashboard.builder import build_dashboard
from tracker_system.storage.saver import append_jsonl, save_json


class TrackerSystemBuilderTest(unittest.TestCase):
    def test_build_dashboard_writes_into_configured_vault_path(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            trades_file = root / "trades.jsonl"
            optimizer_file = root / "optimizer.json"
            vault_dir = root / "obsidian_vault"

            append_jsonl(
                trades_file,
                {
                    "type": "exit",
                    "symbol": "BTCUSDT",
                    "pnl_usd": 42.5,
                    "pnl_pct": 0.021,
                    "mfe": 0.031,
                    "mae": -0.009,
                    "regime": "bullish",
                },
            )
            save_json(
                optimizer_file,
                {
                    "bullish": {
                        "tp": 0.03,
                        "sl": 0.015,
                        "trailing": 0.007,
                        "score": 0.0123,
                        "winrate": 0.61,
                    }
                },
            )

            dashboard_path = build_dashboard(
                log_file=trades_file,
                optimizer_file=optimizer_file,
                vault_dir=vault_dir,
            )

            self.assertEqual(dashboard_path, vault_dir / "06_Dashboard" / "dashboard.md")
            self.assertTrue(dashboard_path.exists())

            content = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("# Dashboard Intelligence", content)
            self.assertIn("## Performance", content)
            self.assertIn("## Equity Curve", content)
            self.assertIn("Max drawdown", content)
            self.assertIn("```mermaid", content)
            self.assertIn("## Optimizer State", content)
            self.assertIn("bullish", content)


if __name__ == "__main__":
    unittest.main()