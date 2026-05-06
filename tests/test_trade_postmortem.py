"""Tests TradePostMortem + StrategyMemoryStore.blacklist_regime."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from quant_hedge_ai.agents.execution.trade_postmortem import (
    TradePostMortem,
    TradeRecord,
    PostmortemReport,
    _MIN_TRADES_FOR_BLACKLIST,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trade(
    pnl_pct_target: float = 5.0,
    regime: str = "bull_trend",
    strategy_name: str = "RSI_v1",
    entry_score: int = 75,
    confirmed: bool = True,
    strength: float = 0.7,
) -> TradeRecord:
    """Crée un trade simple avec entrée à 100 et sortie calculée."""
    entry = 100.0
    if pnl_pct_target >= 0:
        exit_price = entry * (1 + pnl_pct_target / 100)
    else:
        exit_price = entry * (1 + pnl_pct_target / 100)
    return TradeRecord(
        symbol="BTCUSDT",
        action="BUY",
        entry_price=entry,
        exit_price=exit_price,
        size=1.0,
        regime=regime,
        strategy_name=strategy_name,
        entry_score=entry_score,
        entry_signal_confirmed=confirmed,
        entry_strength=strength,
    )


@pytest.fixture
def pm():
    return TradePostMortem()


# ── Tests TradeRecord ────────────────────────────────────────────────────────

class TestTradeRecord:
    def test_pnl_buy_positive(self):
        t = _trade(pnl_pct_target=10.0)
        assert t.pnl > 0

    def test_pnl_buy_negative(self):
        t = _trade(pnl_pct_target=-5.0)
        assert t.pnl < 0

    def test_pnl_pct_buy_up(self):
        t = _trade(pnl_pct_target=10.0)
        assert abs(t.pnl_pct - 10.0) < 0.01

    def test_pnl_pct_sell_direction(self):
        t = TradeRecord(
            symbol="ETH", action="SELL",
            entry_price=100.0, exit_price=90.0, size=1.0,
            regime="bear_trend", strategy_name="s",
        )
        assert t.pnl > 0

    def test_is_loss_above_threshold(self):
        t = _trade(pnl_pct_target=-3.0)
        assert t.is_loss is True

    def test_is_loss_false_small_loss(self):
        t = _trade(pnl_pct_target=-1.0)
        assert t.is_loss is False

    def test_as_dict_keys(self):
        t = _trade()
        d = t.as_dict()
        for k in ("symbol", "action", "pnl", "pnl_pct", "regime", "entry_score", "is_loss"):
            assert k in d

    def test_pnl_zero_price(self):
        t = TradeRecord(
            symbol="X", action="BUY",
            entry_price=0.0, exit_price=0.0, size=1.0,
            regime="unknown", strategy_name="s",
        )
        assert t.pnl_pct == 0.0


# ── Tests analyze / verdict ───────────────────────────────────────────────────

class TestAnalyzeVerdict:
    def test_win_verdict(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=5.0))
        assert r.verdict == "win"

    def test_loss_verdict(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-3.0))
        assert r.verdict == "loss"

    def test_neutral_verdict_small_positive(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=0.5))
        assert r.verdict == "neutral"

    def test_neutral_verdict_tiny_loss(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-0.5))
        assert r.verdict == "neutral"

    def test_returns_postmortem_report(self, pm):
        r = pm.analyze(_trade())
        assert isinstance(r, PostmortemReport)

    def test_report_has_trade(self, pm):
        t = _trade()
        r = pm.analyze(t)
        assert r.trade is t


# ── Tests root_cause ─────────────────────────────────────────────────────────

class TestRootCause:
    def test_no_causes_on_win(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=5.0))
        assert r.root_cause == []

    def test_unconfirmed_signal_cause(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, confirmed=False))
        assert "signal_non_confirme" in r.root_cause

    def test_low_score_cause(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, entry_score=40))
        assert any("score_entree_faible" in c for c in r.root_cause)

    def test_bad_regime_cause_flash_crash(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, regime="flash_crash"))
        assert any("regime_defavorable" in c for c in r.root_cause)

    def test_weak_signal_strength_cause(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, strength=0.3))
        assert any("force_signal_faible" in c for c in r.root_cause)

    def test_unknown_cause_fallback(self, pm):
        # Tous les critères corrects mais perte quand même
        r = pm.analyze(_trade(
            pnl_pct_target=-3.0, confirmed=True, entry_score=80,
            regime="bull_trend", strength=0.8
        ))
        assert "cause_inconnue" in r.root_cause


# ── Tests recommendations ─────────────────────────────────────────────────────

class TestRecommendations:
    def test_recs_for_unconfirmed_signal(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, confirmed=False))
        assert any("signal_confirmed" in rec for rec in r.recommendations)

    def test_recs_for_low_score(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, entry_score=40))
        assert any("SIGNAL_MIN_SCORE" in rec for rec in r.recommendations)

    def test_recs_for_bad_regime(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-5.0, regime="flash_crash"))
        assert any("flash_crash" in rec for rec in r.recommendations)

    def test_win_high_score_upsize_rec(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=5.0, entry_score=85))
        assert any("taille de position" in rec for rec in r.recommendations)


# ── Tests blacklist ───────────────────────────────────────────────────────────

class TestBlacklist:
    def test_no_blacklist_on_win(self, pm):
        for _ in range(5):
            r = pm.analyze(_trade(pnl_pct_target=5.0))
        assert r.blacklisted is False

    def test_blacklist_triggered_after_n_losses(self, pm):
        mock_memory = MagicMock()
        pm._memory = mock_memory
        for i in range(_MIN_TRADES_FOR_BLACKLIST):
            r = pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="BAD", regime="bear_trend"))
        assert r.blacklisted is True
        mock_memory.blacklist_regime.assert_called_once_with("BAD", "bear_trend")

    def test_loss_streak_resets_after_blacklist(self, pm):
        pm._memory = MagicMock()
        for _ in range(_MIN_TRADES_FOR_BLACKLIST):
            pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="X", regime="sideways"))
        # Vérifier que le compteur est remis à zéro
        key = "X::sideways"
        assert pm._loss_streaks.get(key, 0) == 0

    def test_win_resets_streak(self, pm):
        for _ in range(2):
            pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="S", regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=5.0, strategy_name="S", regime="bull_trend"))
        assert pm._loss_streaks.get("S::bull_trend", 0) == 0

    def test_blacklist_calls_signal_engine(self, pm):
        mock_engine = MagicMock()
        pm._signal_engine = mock_engine
        pm._memory = MagicMock()
        for _ in range(_MIN_TRADES_FOR_BLACKLIST):
            pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="Z", regime="sideways"))
        mock_engine.blacklist_regime.assert_called_with("sideways")

    def test_blacklist_key_format(self, pm):
        r = pm.analyze(_trade(pnl_pct_target=-3.0, strategy_name="RSI", regime="bull_trend"))
        assert r.blacklist_key == "RSI::bull_trend"


# ── Tests statistiques ────────────────────────────────────────────────────────

class TestStats:
    def test_regime_stats_empty(self, pm):
        s = pm.regime_stats("bull_trend")
        assert s["n_trades"] == 0

    def test_regime_stats_win_rate(self, pm):
        pm.analyze(_trade(pnl_pct_target=5.0, regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=5.0, regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=-5.0, regime="bull_trend"))
        s = pm.regime_stats("bull_trend")
        assert s["n_trades"] == 3
        assert s["win_rate"] == pytest.approx(2 / 3, rel=0.01)

    def test_strategy_stats_empty(self, pm):
        s = pm.strategy_stats("RSI_v1")
        assert s["n_trades"] == 0

    def test_strategy_stats_best_regime(self, pm):
        pm.analyze(_trade(pnl_pct_target=5.0, strategy_name="S1", regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=5.0, strategy_name="S1", regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=5.0, strategy_name="S1", regime="bear_trend"))
        s = pm.strategy_stats("S1")
        assert s["best_regime"] == "bull_trend"

    def test_summary_empty(self, pm):
        assert pm.summary()["n_trades"] == 0

    def test_summary_counts(self, pm):
        pm.analyze(_trade(pnl_pct_target=5.0))
        pm.analyze(_trade(pnl_pct_target=-5.0))
        s = pm.summary()
        assert s["n_trades"] == 2
        assert s["wins"] == 1
        assert s["losses"] == 1


# ── Tests StrategyMemoryStore.blacklist_regime ────────────────────────────────

class TestStrategyMemoryBlacklist:
    def test_blacklist_regime_persists(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        store.blacklist_regime("RSI_v1", "flash_crash")
        assert store.is_blacklisted("RSI_v1", "flash_crash")

    def test_is_blacklisted_false_for_other_regime(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        store.blacklist_regime("RSI_v1", "flash_crash")
        assert not store.is_blacklisted("RSI_v1", "bull_trend")

    def test_blacklist_does_not_duplicate(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        store.blacklist_regime("RSI_v1", "flash_crash")
        store.blacklist_regime("RSI_v1", "flash_crash")
        payload = store._read()
        count = sum(
            1 for b in payload.get("blacklist", [])
            if b == {"strategy": "RSI_v1", "regime": "flash_crash"}
        )
        assert count == 1

    def test_blacklisted_strategy_excluded_from_load(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        # Sauvegarder une stratégie
        store.save_for_regime("bull_trend", [{
            "strategy": {"name": "BAD_STRAT", "entry_indicator": "RSI"},
            "sharpe": 1.5, "drawdown": 0.1, "win_rate": 0.6, "pnl": 500.0,
        }])
        store.blacklist_regime("BAD_STRAT", "bull_trend")
        results = store.load_by_regime("bull_trend")
        names = [r.get("strategy", {}).get("name", "") for r in results]
        assert "BAD_STRAT" not in names

    def test_is_blacklisted_false_initially(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        assert not store.is_blacklisted("any_strat", "any_regime")

    def test_save_for_regime_ages_strategies(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        strat = {"strategy": {"name": "S"}, "sharpe": 1.0, "drawdown": 0.1,
                 "win_rate": 0.5, "pnl": 100.0}
        store.save_for_regime("bull_trend", [strat])
        store.save_for_regime("bull_trend", [strat])  # 2e cycle → age=1
        rows = store.load_by_regime("bull_trend")
        assert any(r.get("age_cycles", 0) >= 1 for r in rows)

    def test_regime_stability_empty_history(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        assert store.get_regime_stability("bull_trend") == 0.0

    def test_regime_stability_all_matching(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        strat = {"strategy": {"name": "S"}, "sharpe": 1.0, "drawdown": 0.1,
                 "win_rate": 0.5, "pnl": 100.0}
        for _ in range(10):
            store.save_for_regime("bull_trend", [strat])
        stability = store.get_regime_stability("bull_trend")
        assert stability > 0.8

    def test_load_by_regime_empty_store(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        assert store.load_by_regime("unknown_regime") == []

    def test_load_by_regime_limit(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        strats = [
            {"strategy": {"name": f"S{i}"}, "sharpe": float(i), "drawdown": 0.1,
             "win_rate": 0.5, "pnl": float(i * 100)}
            for i in range(10)
        ]
        store.save_for_regime("bull_trend", strats)
        results = store.load_by_regime("bull_trend", limit=3)
        assert len(results) <= 3

    def test_dedupe_keeps_best_sharpe(self, tmp_path):
        from quant_hedge_ai.ai_evolution.strategy_memory import (
            StrategyMemoryStore, MemoryConfig
        )
        cfg = MemoryConfig(file_path=tmp_path / "mem.json")
        store = StrategyMemoryStore(cfg)
        # Même stratégie soumise 2x avec Sharpe différents
        strat_low  = {"strategy": {"name": "DUP"}, "sharpe": 0.5, "drawdown": 0.2,
                      "win_rate": 0.4, "pnl": 50.0}
        strat_high = {"strategy": {"name": "DUP"}, "sharpe": 2.0, "drawdown": 0.1,
                      "win_rate": 0.6, "pnl": 200.0}
        store.save_for_regime("bull_trend", [strat_low, strat_high])
        rows = store.load_by_regime("bull_trend")
        sharpes = [r["sharpe"] for r in rows]
        assert 2.0 in sharpes


# ── Tests supplémentaires PostMortem ─────────────────────────────────────────

class TestPostMortemExtra:
    def test_worst_regime_for_no_losses(self):
        pm = TradePostMortem()
        pm.analyze(_trade(pnl_pct_target=5.0, strategy_name="S", regime="bull_trend"))
        s = pm.strategy_stats("S")
        assert s["worst_regime"] == "none"

    def test_best_regime_for_no_wins(self):
        pm = TradePostMortem()
        pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="S", regime="bear_trend"))
        s = pm.strategy_stats("S")
        assert s["best_regime"] == "none"

    def test_report_as_dict(self):
        pm = TradePostMortem()
        r = pm.analyze(_trade(pnl_pct_target=5.0))
        d = r.as_dict()
        assert "trade" in d
        assert "verdict" in d
        assert "blacklisted" in d

    def test_blacklist_memory_exception_returns_false(self):
        pm = TradePostMortem()
        bad_memory = MagicMock()
        bad_memory.blacklist_regime.side_effect = RuntimeError("DB error")
        pm._memory = bad_memory
        for _ in range(_MIN_TRADES_FOR_BLACKLIST):
            r = pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="X", regime="sideways"))
        assert r.blacklisted is False

    def test_summary_active_loss_streaks(self):
        pm = TradePostMortem()
        pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="X", regime="bull_trend"))
        pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="X", regime="bull_trend"))
        s = pm.summary()
        assert "X::bull_trend" in s["active_loss_streaks"]

    def test_multiple_strategies_independent_streaks(self):
        pm = TradePostMortem()
        for _ in range(2):
            pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="A", regime="bull_trend"))
        for _ in range(1):
            pm.analyze(_trade(pnl_pct_target=-5.0, strategy_name="B", regime="bull_trend"))
        assert pm._loss_streaks.get("A::bull_trend", 0) == 2
        assert pm._loss_streaks.get("B::bull_trend", 0) == 1
