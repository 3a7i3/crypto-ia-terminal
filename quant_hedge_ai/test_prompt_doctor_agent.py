from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant_hedge_ai.agents.monitoring.prompt_doctor_agent import \
    CreatePromptAgent


class TestCreatePromptAgent(unittest.TestCase):
    def test_generate_prompt_returns_valid_json(self):
        agent = CreatePromptAgent()
        prompt_json = agent.generate_prompt()
        parsed = json.loads(prompt_json)
        self.assertEqual(parsed["action"], "enhance_bot_platform_with_doctor")
        self.assertIn("parameters", parsed)
        self.assertIn("doctor_ai", parsed["parameters"])

    def test_apply_doctor_corrections_does_not_mutate_original(self):
        agent = CreatePromptAgent()
        strategy = {"trade_signal": None, "allocation": "error", "risk_level": "medium"}
        _ = agent.apply_doctor_corrections(strategy)
        self.assertIsNone(strategy["trade_signal"])
        self.assertEqual(strategy["allocation"], "error")

    def test_simulate_telegram_alerts_sends_only_current_cycle_issues(self):
        agent = CreatePromptAgent()
        sent_messages = []

        def _collector(_user_id, message):
            sent_messages.append(message)

        strategy_one = {
            "trade_signal": None,
            "allocation": "error",
            "risk_level": "medium",
        }
        strategy_two = {"trade_signal": "BUY", "allocation": 0.2, "risk_level": "high"}
        corrected_one = agent.simulate_telegram_alerts(
            12345, strategy_one, send_func=_collector
        )
        corrected_two = agent.simulate_telegram_alerts(
            12345, strategy_two, send_func=_collector
        )
        self.assertEqual(corrected_one["trade_signal"], "HOLD")
        self.assertEqual(corrected_one["allocation"], 0.0)
        self.assertEqual(corrected_two, strategy_two)
        self.assertEqual(len(sent_messages), 2)
        self.assertTrue(all("Bot Doctor ALERT" in message for message in sent_messages))

    def test_run_realtime_demo_returns_corrected_snapshots_without_sleep(self):
        agent = CreatePromptAgent()
        sent_messages = []

        def _collector(_user_id, message):
            sent_messages.append(message)

        strategies = [
            {"trade_signal": None, "allocation": "error", "risk_level": "medium"},
            {"trade_signal": "BUY", "allocation": None, "risk_level": "high"},
        ]
        corrected = agent.run_realtime_demo(
            12345, strategies, delay_seconds=0, send_func=_collector
        )
        self.assertEqual(corrected[0]["trade_signal"], "HOLD")
        self.assertEqual(corrected[0]["allocation"], 0.0)
        self.assertEqual(corrected[1]["allocation"], 0.0)
        self.assertEqual(len(sent_messages), 3)

    def test_apply_doctor_corrections_fixes_unknown_signal_and_string_allocation(self):
        agent = CreatePromptAgent()
        strategy = {
            "trade_signal": "long",
            "allocation": "0,42",
            "risk_level": "medium",
        }
        corrected = agent.apply_doctor_corrections(strategy)
        self.assertEqual(corrected["trade_signal"], "HOLD")
        self.assertEqual(corrected["allocation"], 0.42)

    def test_build_evolution_snapshot_returns_expected_counters(self):
        agent = CreatePromptAgent()
        strategy = {"trade_signal": "???", "allocation": -0.5, "risk_level": "extreme"}
        _corrected, cycle_issues = agent.apply_doctor_corrections_with_issues(strategy)
        snapshot = agent.build_evolution_snapshot(cycle_issues)
        self.assertEqual(snapshot["cycle_corrections"], len(cycle_issues))
        self.assertGreaterEqual(snapshot["total_corrections"], len(cycle_issues))
        self.assertGreaterEqual(snapshot["risk_related_corrections"], 1)
        self.assertGreaterEqual(snapshot["signal_related_corrections"], 1)
        self.assertIsInstance(snapshot["recent_corrections"], list)

    def test_director_panel_accumulates_entries(self):
        agent = CreatePromptAgent()
        _ = agent.apply_doctor_corrections(
            {"trade_signal": None, "allocation": "error", "risk_level": "medium"}
        )
        panel = agent.director_panel()
        self.assertTrue(panel["bot_status"])
        self.assertEqual(
            panel["performance_metrics"]["errors_corrected"],
            len(agent.get_doctor_log()),
        )
        self.assertEqual(len(agent.director_logs), 1)

    def test_developer_dashboard_reports_recent_corrections(self):
        agent = CreatePromptAgent()
        _ = agent.apply_doctor_corrections(
            {"trade_signal": None, "allocation": "error", "risk_level": "medium"}
        )
        dashboard = agent.developer_dashboard()
        self.assertIn("active_agents", dashboard)
        self.assertEqual(dashboard["pending_alerts"], len(agent.get_doctor_log()))
        self.assertIsInstance(dashboard["recent_corrections"], list)

    def test_interactive_doctor_panel_filters_by_strategy(self):
        agent = CreatePromptAgent()
        agent.doctor_log.extend(
            [
                "Correction applied on strategy_name: 'x' -> 'y'",
                "Correction applied on allocation: 2.0 -> 1.0",
            ]
        )
        panel = agent.interactive_doctor_panel(filter_by="strategy")
        self.assertEqual(panel["filter"], "strategy")
        self.assertEqual(panel["filtered_logs_count"], 1)
        self.assertIn("strategy", panel["logs"][0].lower())

    def test_createprompagent_alias_works(self):
        alias_agent = CreatePromptAgent()
        self.assertIsInstance(alias_agent, CreatePromptAgent)


if __name__ == "__main__":
    unittest.main()


def test_interactive_doctor_panel_filters_by_strategy() -> None:
    agent = CreatePromptAgent()
    agent.doctor_log.extend(
        [
            "Correction applied on strategy_name: 'x' -> 'y'",
            "Correction applied on allocation: 2.0 -> 1.0",
        ]
    )

    panel = agent.interactive_doctor_panel(filter_by="strategy")

    assert panel["filter"] == "strategy"
    assert panel["filtered_logs_count"] == 1
    assert "strategy" in panel["logs"][0].lower()


def test_createprompagent_alias_works() -> None:
    alias_agent = CreatePromptAgent()
    assert isinstance(alias_agent, CreatePromptAgent)
