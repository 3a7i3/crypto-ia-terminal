from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.config.settings import bootstrap_tracker_layout


class TrackerMainEntrypointTest(unittest.TestCase):
    def test_bootstrap_status_contains_clean_sections(self) -> None:
        status = bootstrap_tracker_layout()

        self.assertIn("core", status["sections"])
        self.assertIn("engine", status["sections"])
        self.assertIn("runtime", status["sections"])
        self.assertTrue(
            any(item["path"] == "logs/trades.jsonl" and item["exists"] for item in status["sections"]["runtime"]["files"])
        )

    def test_main_status_mode_runs_as_script(self) -> None:
        script = Path("tracker_system/main.py")
        completed = subprocess.run(
            [sys.executable, str(script), "--status"],
            capture_output=True,
            check=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["sections"]["core"]["role"], "trade lifecycle, open positions, pnl")
        self.assertTrue(payload["sections"]["dashboard"]["files"][0]["exists"])

    def test_main_scheduler_mode_runs_as_script(self) -> None:
        script = Path("tracker_system/main.py")
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "scheduler.log"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--scheduler",
                    "--max-iterations",
                    "0",
                    "--no-optimizer",
                    "--scheduler-log-file",
                    str(log_file),
                ],
                capture_output=True,
                check=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload, {})
            self.assertTrue(log_file.exists())


if __name__ == "__main__":
    unittest.main()