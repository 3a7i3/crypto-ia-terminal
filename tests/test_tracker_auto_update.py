from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.main import run_cycle
from tracker_system.scheduler.auto_update import run_auto_update
from tracker_system.storage.saver import append_jsonl, save_json


class TrackerAutoUpdateTest(unittest.TestCase):
    def test_run_auto_update_repeats_cycle_and_sleeps_between_iterations(self) -> None:
        calls: list[bool] = []
        sleeps: list[float] = []

        def _cycle_runner(*, run_optimizer: bool = False):
            calls.append(run_optimizer)
            return {"run_optimizer": run_optimizer, "iteration": len(calls)}

        results = run_auto_update(
            interval_seconds=12.5,
            run_optimizer=True,
            max_iterations=2,
            cycle_runner=_cycle_runner,
            sleep_fn=sleeps.append,
        )

        self.assertEqual(calls, [True, True])
        self.assertEqual(sleeps, [12.5])
        self.assertEqual(results[-1]["iteration"], 2)

    def test_run_auto_update_end_to_end_refreshes_optimizer_dashboard_and_log(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            trades_file = root / "trades.jsonl"
            state_file = root / "open_positions.json"
            optimizer_file = root / "optimizer.json"
            dashboard_file = root / "dashboard.md"
            auto_update_log = root / "auto_update.log"

            save_json(state_file, [])
            for pnl_usd, path in ((4.0, [100.0, 103.0, 104.0]), (-1.0, [100.0, 99.0, 99.5])):
                append_jsonl(
                    trades_file,
                    {
                        "type": "exit",
                        "id": f"trade-{pnl_usd}",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "entry_price": 100.0,
                        "exit_price": path[-1],
                        "pnl_usd": pnl_usd,
                        "pnl_pct": pnl_usd / 100.0,
                        "mfe": 0.03,
                        "mae": -0.01,
                        "regime": "bullish",
                        "price_path": path,
                    },
                )

            results = run_auto_update(
                interval_seconds=0.0,
                run_optimizer=True,
                max_iterations=1,
                cycle_runner=run_cycle,
                cycle_kwargs={
                    "log_file": trades_file,
                    "state_file": state_file,
                    "optimizer_file": optimizer_file,
                    "dashboard_file": dashboard_file,
                    "optimizer_min_trades": 1,
                },
                log_file=auto_update_log,
            )

            self.assertEqual(len(results), 1)
            self.assertTrue(optimizer_file.exists())
            self.assertTrue(dashboard_file.exists())
            self.assertTrue(auto_update_log.exists())

            optimizer_payload = json.loads(optimizer_file.read_text(encoding="utf-8"))
            self.assertIn("bullish", optimizer_payload)
            self.assertIn("tp", optimizer_payload["bullish"])

            dashboard_content = dashboard_file.read_text(encoding="utf-8")
            self.assertIn("## Optimizer State", dashboard_content)
            self.assertIn("bullish", dashboard_content)

            auto_update_content = auto_update_log.read_text(encoding="utf-8")
            self.assertIn("auto-update started", auto_update_content)
            self.assertIn("cycle_complete iteration=1", auto_update_content)
            self.assertIn(str(dashboard_file), auto_update_content)
            self.assertIn("trades=2", auto_update_content)
            self.assertIn("pnl_total=3.000000", auto_update_content)
            self.assertIn("max_drawdown=1.000000", auto_update_content)
            self.assertIn("max_drawdown_pct=0.250000", auto_update_content)


if __name__ == "__main__":
    unittest.main()