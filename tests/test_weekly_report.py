"""Tests WeeklyReportAgent — rapport hebdomadaire automatisé."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from quant_hedge_ai.agents.intelligence.weekly_report import (
    WeeklyReportAgent,
    WeeklyReport,
    WeeklyStats,
)
from quant_hedge_ai.agents.execution.trade_postmortem import (
    TradePostMortem,
    TradeRecord,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trade(pnl_pct: float, regime: str = "bull_trend", strategy: str = "S1") -> TradeRecord:
    entry = 100.0
    exit_p = entry * (1 + pnl_pct / 100)
    return TradeRecord(
        symbol="BTCUSDT", action="BUY",
        entry_price=entry, exit_price=exit_p, size=1.0,
        regime=regime, strategy_name=strategy,
    )


def _pm_with_trades(trades: list[tuple]) -> TradePostMortem:
    """trades = [(pnl_pct, regime, strategy)]"""
    pm = TradePostMortem()
    for pnl, regime, strat in trades:
        pm.analyze(_trade(pnl, regime, strat))
    return pm


@pytest.fixture
def agent_empty():
    return WeeklyReportAgent()


@pytest.fixture
def agent_with_data():
    pm = _pm_with_trades([
        (5.0, "bull_trend", "RSI"),
        (3.0, "bull_trend", "RSI"),
        (-4.0, "bear_trend", "EMA"),
        (1.5, "sideways",   "RSI"),
        (-3.0, "bear_trend", "EMA"),
    ])
    return WeeklyReportAgent(postmortem=pm)


# ── Tests WeeklyStats ─────────────────────────────────────────────────────────

class TestWeeklyStats:
    def test_win_rate_zero_trades(self):
        s = WeeklyStats()
        assert s.win_rate == 0.0

    def test_win_rate_all_wins(self):
        s = WeeklyStats(wins=3, losses=0)
        assert s.win_rate == 1.0

    def test_win_rate_mixed(self):
        s = WeeklyStats(wins=2, losses=2)
        assert s.win_rate == pytest.approx(0.5)

    def test_avg_pnl_zero_trades(self):
        s = WeeklyStats()
        assert s.avg_pnl_pct == 0.0

    def test_avg_pnl_computed(self):
        s = WeeklyStats(wins=2, losses=1, neutrals=0, total_pnl_pct=9.0)
        assert s.avg_pnl_pct == pytest.approx(3.0)


# ── Tests generate sans données ───────────────────────────────────────────────

class TestGenerateEmpty:
    def test_returns_weekly_report(self, agent_empty):
        r = agent_empty.generate()
        assert isinstance(r, WeeklyReport)

    def test_zero_trades_no_crash(self, agent_empty):
        r = agent_empty.generate()
        assert r.stats.n_trades == 0

    def test_text_not_empty(self, agent_empty):
        r = agent_empty.generate()
        assert len(r.text_summary) > 20

    def test_improvements_not_empty(self, agent_empty):
        r = agent_empty.generate()
        assert len(r.improvements) >= 1

    def test_as_dict_keys(self, agent_empty):
        r = agent_empty.generate()
        d = r.as_dict()
        for k in ("n_trades", "win_rate", "total_pnl_pct", "best_regime",
                  "worst_regime", "improvements", "generated_at"):
            assert k in d


# ── Tests generate avec données ───────────────────────────────────────────────

class TestGenerateWithData:
    def test_n_trades_correct(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.n_trades == 5

    def test_wins_losses_counted(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.wins == 3
        assert r.stats.losses == 2

    def test_win_rate_correct(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.win_rate == pytest.approx(3 / 5, rel=0.01)

    def test_best_regime_bull(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.best_regime == "bull_trend"

    def test_worst_regime_bear(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.worst_regime == "bear_trend"

    def test_best_trade_positive(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.best_trade_pct > 0

    def test_worst_trade_negative(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.worst_trade_pct < 0

    def test_pnl_total_computed(self, agent_with_data):
        r = agent_with_data.generate()
        assert r.stats.total_pnl_pct != 0.0

    def test_text_contains_header(self, agent_with_data):
        r = agent_with_data.generate()
        assert "RAPPORT HEBDOMADAIRE" in r.text_summary

    def test_text_contains_win_rate(self, agent_with_data):
        r = agent_with_data.generate()
        assert "%" in r.text_summary

    def test_text_contains_improvements_section(self, agent_with_data):
        r = agent_with_data.generate()
        assert "AMÉLIORATIONS" in r.text_summary


# ── Tests suggestions d'amélioration ─────────────────────────────────────────

class TestImprovements:
    def test_low_win_rate_triggers_improvement(self):
        pm = _pm_with_trades([
            (-5.0, "bull_trend", "X"),
            (-5.0, "bull_trend", "X"),
            (-5.0, "bull_trend", "X"),
            (-5.0, "bull_trend", "X"),
            ( 1.5, "bull_trend", "X"),
        ])
        agent = WeeklyReportAgent(postmortem=pm)
        r = agent.generate()
        assert any("Win rate" in i or "win_rate" in i.lower() or "critères" in i for i in r.improvements)

    def test_high_drawdown_triggers_improvement(self):
        pm = _pm_with_trades([
            (-15.0, "bear_trend", "X"),
            (  1.0, "bull_trend", "X"),
        ])
        agent = WeeklyReportAgent(postmortem=pm)
        r = agent.generate()
        assert any("drawdown" in i.lower() or "Drawdown" in i for i in r.improvements)

    def test_good_performance_suggests_upsize(self):
        pm = _pm_with_trades([
            (5.0, "bull_trend", "X"),
            (4.0, "bull_trend", "X"),
            (3.0, "bull_trend", "X"),
        ])
        agent = WeeklyReportAgent(postmortem=pm)
        r = agent.generate()
        assert any("position" in i.lower() for i in r.improvements)

    def test_blacklisted_strategy_in_improvement(self):
        from quant_hedge_ai.agents.execution.trade_postmortem import _MIN_TRADES_FOR_BLACKLIST
        pm = TradePostMortem()
        pm._memory = MagicMock()
        for _ in range(_MIN_TRADES_FOR_BLACKLIST):
            pm.analyze(_trade(-5.0, "bear_trend", "BAD_STRAT"))
        agent = WeeklyReportAgent(postmortem=pm)
        r = agent.generate()
        assert any("blacklist" in i.lower() or "Blacklist" in i for i in r.improvements)

    def test_no_data_returns_default_improvement(self):
        agent = WeeklyReportAgent()
        r = agent.generate()
        assert len(r.improvements) >= 1


# ── Tests avec memory_store ───────────────────────────────────────────────────

class TestWithMemoryStore:
    def test_memory_store_read_error_does_not_crash(self):
        bad_memory = MagicMock()
        bad_memory._read.side_effect = RuntimeError("DB error")
        agent = WeeklyReportAgent(memory_store=bad_memory)
        r = agent.generate()
        assert isinstance(r, WeeklyReport)

    def test_active_strategies_from_memory(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        store.save_for_regime("bull_trend", [{
            "strategy": {"name": "S"}, "sharpe": 1.5, "drawdown": 0.1,
            "win_rate": 0.6, "pnl": 100.0
        }])
        agent = WeeklyReportAgent(memory_store=store)
        r = agent.generate()
        assert "bull_trend" in r.stats.active_strategies


# ── Tests EventBus ────────────────────────────────────────────────────────────

class TestEventBus:
    def test_generate_emits_event(self):
        agent = WeeklyReportAgent()
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_inst = MagicMock()
            mock_bus.return_value = mock_inst
            agent.generate()
            assert mock_inst.emit.called

    def test_eventbus_exception_does_not_crash(self):
        agent = WeeklyReportAgent()
        with patch("event_bus.bus.EventBus.get", side_effect=RuntimeError("bus error")):
            r = agent.generate()
            assert isinstance(r, WeeklyReport)
