import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tracker_system.tracker import load_dashboard_thresholds, update_dashboard


class TrackerDashboardTest(unittest.TestCase):
    @staticmethod
    def _baseline_trades() -> list[dict]:
        return [
            {
                "symbol": "BTCUSDT",
                "pnl_usd": 120.0,
                "pnl_pct": 0.015,
                "win": True,
                "mfe": 0.030,
                "mae": -0.010,
                "regime": "bullish",
                "duration_minutes": 18.0,
            },
            {
                "symbol": "ETHUSDT",
                "pnl_usd": -80.0,
                "pnl_pct": -0.012,
                "win": False,
                "mfe": 0.010,
                "mae": -0.018,
                "regime": "range",
                "duration_minutes": 32.0,
            },
            {
                "symbol": "SOLUSDT",
                "pnl_usd": 30.0,
                "pnl_pct": 0.004,
                "win": True,
                "mfe": 0.020,
                "mae": -0.006,
                "regime": "range",
                "duration_minutes": 24.0,
            },
        ]

    def test_update_dashboard_writes_semi_pro_markdown(self) -> None:
        trades = self._baseline_trades()

        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            update_dashboard(trades, vault)

            dash = vault / "06_Dashboard" / "dashboard.md"
            self.assertTrue(dash.exists())

            content = dash.read_text(encoding="utf-8")
            for expected in (
                "# 📊 Trading Dashboard",
                "## 📈 Performance Globale",
                "## 🎯 Qualité du Système",
                "## 🧠 Edge",
                "Efficiency:",
                "## 📊 Par Régime",
                "- edge mal monétisé: sorties trop tôt pour un standard prop firm",
                "- éviter range faible",
                "- drawdown trop élevé pour un cadre prop strict",
                "## 🧩 Architecture",
                "tracker_system = analyse, dashboard, optimisation",
            ):
                self.assertIn(expected, content)

    def test_update_dashboard_prioritizes_strong_regime_when_metrics_are_clean(self) -> None:
        trades = [
            {
                "symbol": "BTCUSDT",
                "pnl_usd": 150.0,
                "pnl_pct": 0.012,
                "win": True,
                "mfe": 0.015,
                "mae": -0.004,
                "regime": "bullish",
                "duration_minutes": 35.0,
            },
            {
                "symbol": "ETHUSDT",
                "pnl_usd": 130.0,
                "pnl_pct": 0.010,
                "win": True,
                "mfe": 0.014,
                "mae": -0.003,
                "regime": "bullish",
                "duration_minutes": 28.0,
            },
            {
                "symbol": "SOLUSDT",
                "pnl_usd": 40.0,
                "pnl_pct": 0.003,
                "win": True,
                "mfe": 0.004,
                "mae": -0.002,
                "regime": "range",
                "duration_minutes": 16.0,
            },
        ]

        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            update_dashboard(trades, vault)

            content = (vault / "06_Dashboard" / "dashboard.md").read_text(encoding="utf-8")
            self.assertIn("- capture de l'edge propre", content)
            self.assertIn("- concentrer le risque sur bull trend", content)
            self.assertIn("- prioriser bull trend quand le marché est lisible", content)

    def test_update_dashboard_uses_external_threshold_override(self) -> None:
        trades = self._baseline_trades()

        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            config_path = vault / "dashboard_thresholds.json"
            config_path.write_text(
                json.dumps(
                    {
                        "edge": {
                            "poor_efficiency_pct": 20.0,
                            "review_efficiency_pct": 30.0,
                            "max_drawdown_hard_pct": 80.0,
                            "max_drawdown_review_pct": 70.0,
                        },
                        "regime": {
                            "range_avoid_avg_pnl_pct": -1.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            thresholds = load_dashboard_thresholds(config_path)

            update_dashboard(trades, vault, thresholds=thresholds)

            content = (vault / "06_Dashboard" / "dashboard.md").read_text(encoding="utf-8")
            self.assertIn("- capture de l'edge propre", content)
            self.assertIn("- réduire l'exposition en range", content)
            self.assertNotIn("- éviter range faible", content)
            self.assertNotIn("- edge mal monétisé: sorties trop tôt pour un standard prop firm", content)
            self.assertNotIn("- drawdown trop élevé pour un cadre prop strict", content)


if __name__ == "__main__":
    unittest.main()
