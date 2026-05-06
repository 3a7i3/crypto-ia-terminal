"""Tests unitaires et d'intégration pour meta_memory + meta_learner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tracker_system.meta_memory  import MetaMemory
from tracker_system.meta_learner import MetaLearner, _volatility_bucket, _similarity


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mem(tmp_path: Path) -> MetaMemory:
    return MetaMemory(path=tmp_path / "meta_memory.json")

def _learner(tmp_path: Path) -> MetaLearner:
    return MetaLearner(memory_path=tmp_path / "meta_memory.json")


# ── _volatility_bucket ────────────────────────────────────────────────────────

def test_vol_bucket_low():
    assert _volatility_bucket(0.005) == "low"

def test_vol_bucket_medium():
    assert _volatility_bucket(0.015) == "medium"

def test_vol_bucket_high():
    assert _volatility_bucket(0.03) == "high"

def test_vol_bucket_boundary_low_medium():
    assert _volatility_bucket(0.01) == "medium"

def test_vol_bucket_boundary_medium_high():
    assert _volatility_bucket(0.025) == "high"


# ── _similarity ───────────────────────────────────────────────────────────────

def test_similarity_exact():
    a = {"regime": "bull_trend", "volatility_bucket": "medium"}
    assert _similarity(a, a) == 2

def test_similarity_regime_only():
    a = {"regime": "bull_trend", "volatility_bucket": "low"}
    b = {"regime": "bull_trend", "volatility_bucket": "high"}
    assert _similarity(a, b) == 1

def test_similarity_none():
    a = {"regime": "bull_trend", "volatility_bucket": "low"}
    b = {"regime": "bearish",    "volatility_bucket": "high"}
    assert _similarity(a, b) == 0

def test_similarity_vol_only():
    a = {"regime": "bull_trend", "volatility_bucket": "medium"}
    b = {"regime": "bearish",    "volatility_bucket": "medium"}
    assert _similarity(a, b) == 1


# ── MetaMemory ────────────────────────────────────────────────────────────────

def test_memory_starts_empty(tmp_path):
    m = _mem(tmp_path)
    assert len(m) == 0

def test_memory_add_and_persist(tmp_path):
    m = _mem(tmp_path)
    m.add({"regime": "bull_trend", "volatility_bucket": "medium"},
          {"exit_type": "tp_sl", "tp": 0.02, "sl": 0.01},
          {"sharpe": 1.5, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 30})
    assert len(m) == 1
    # Re-load from disk
    m2 = _mem(tmp_path)
    assert len(m2) == 1
    assert m2.memory[0]["context"]["regime"] == "bull_trend"

def test_memory_update_existing(tmp_path):
    ctx = {"regime": "bull_trend", "volatility_bucket": "medium"}
    m = _mem(tmp_path)
    m.add(ctx, {"exit_type": "tp_sl"}, {"sharpe": 1.0, "win_rate": 0.5, "avg_pnl": 0.005, "n_trades": 10})
    m.add(ctx, {"exit_type": "trailing"}, {"sharpe": 2.0, "win_rate": 0.7, "avg_pnl": 0.015, "n_trades": 20})
    assert len(m) == 1
    assert m.memory[0]["decision"]["exit_type"] == "trailing"
    assert m.memory[0]["performance"]["sharpe"] == 2.0

def test_memory_multiple_regimes(tmp_path):
    m = _mem(tmp_path)
    for regime in ["bull_trend", "bearish", "range"]:
        m.add({"regime": regime, "volatility_bucket": "medium"},
              {"exit_type": "tp_sl"},
              {"sharpe": 1.0, "win_rate": 0.5, "avg_pnl": 0.01, "n_trades": 5})
    assert len(m) == 3

def test_memory_all_returns_copy(tmp_path):
    m = _mem(tmp_path)
    m.add({"regime": "bull_trend", "volatility_bucket": "low"},
          {"exit_type": "tp_sl"},
          {"sharpe": 1.0, "win_rate": 0.5, "avg_pnl": 0.01, "n_trades": 5})
    result = m.all()
    result.clear()
    assert len(m) == 1  # mutation de la liste externe n'affecte pas la mémoire


# ── MetaLearner.find_best ─────────────────────────────────────────────────────

def test_find_best_returns_none_empty_memory(tmp_path):
    learner = _learner(tmp_path)
    assert learner.find_best({"regime": "bull_trend", "volatility": 0.015}) is None

def test_find_best_exact_match(tmp_path):
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "bull_trend", "volatility_bucket": "medium"},
        {"exit_type": "tp_sl", "tp": 0.02, "sl": 0.01},
        {"sharpe": 1.8, "win_rate": 0.65, "avg_pnl": 0.012, "n_trades": 40},
    )
    dec = learner.find_best({"regime": "bull_trend", "volatility": 0.015})
    assert dec is not None
    assert dec["exit_type"] == "tp_sl"
    assert dec["tp"] == 0.02

def test_find_best_picks_highest_sharpe(tmp_path):
    """Plusieurs entrées de même similarité → on choisit le meilleur Sharpe."""
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "bull_trend", "volatility_bucket": "low"},
        {"exit_type": "tp_sl"},
        {"sharpe": 1.2, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 20},
    )
    learner.learn(
        {"regime": "bull_trend", "volatility_bucket": "high"},
        {"exit_type": "trailing"},
        {"sharpe": 2.5, "win_rate": 0.7, "avg_pnl": 0.015, "n_trades": 30},
    )

    # Contexte medium → similarité 1 avec "low" et "high" → trailing gagne (Sharpe 2.5)
    dec = learner.find_best({"regime": "bull_trend", "volatility": 0.015},
                            min_similarity=1)
    assert dec["exit_type"] == "trailing"

def test_find_best_no_match_below_threshold(tmp_path):
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "bearish", "volatility_bucket": "high"},
        {"exit_type": "tp_sl"},
        {"sharpe": 1.0, "win_rate": 0.5, "avg_pnl": 0.01, "n_trades": 5},
    )
    # Régime différent → similarité 0 → None avec min_similarity=1
    assert learner.find_best({"regime": "bull_trend", "volatility": 0.015},
                              min_similarity=1) is None

def test_find_best_volatility_bucket_normalisation(tmp_path):
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "range", "volatility_bucket": "low"},
        {"exit_type": "hybrid", "tp": 0.015, "sl": 0.008, "trail_pct": 0.005},
        {"sharpe": 2.1, "win_rate": 0.7, "avg_pnl": 0.014, "n_trades": 25},
    )
    # Passe volatility float → doit être bucketisé puis matché
    dec = learner.find_best({"regime": "range", "volatility": 0.007})
    assert dec is not None
    assert dec["exit_type"] == "hybrid"

def test_find_best_returns_copy(tmp_path):
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "bull_trend", "volatility_bucket": "medium"},
        {"exit_type": "tp_sl", "tp": 0.02},
        {"sharpe": 1.5, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 10},
    )
    dec = learner.find_best({"regime": "bull_trend", "volatility_bucket": "medium"})
    dec["exit_type"] = "MUTATED"
    dec2 = learner.find_best({"regime": "bull_trend", "volatility_bucket": "medium"})
    assert dec2["exit_type"] == "tp_sl"


# ── MetaLearner.ingest_backtest ───────────────────────────────────────────────

FAKE_BACKTEST = {
    "_meta": {"total_trades": 15, "regimes": ["bullish", "bearish"]},
    "bullish": {
        "best": {"type": "tp_sl", "tp": 0.02, "sl": 0.01,
                 "score": 0.0048, "win_rate": 0.6, "avg": 0.008, "n": 5},
        "tp_sl": {},
        "trailing": {},
        "hybrid": {},
        "n_trades": 5,
    },
    "bearish": {
        "best": {"type": "trailing", "trail_pct": 0.005, "activation_pct": 0.01,
                 "score": 0.0035, "win_rate": 0.55, "avg": 0.006, "n": 10},
        "tp_sl": {},
        "trailing": {},
        "hybrid": {},
        "n_trades": 10,
    },
}

def test_ingest_backtest_count(tmp_path):
    learner = _learner(tmp_path)
    n = learner.ingest_backtest(FAKE_BACKTEST)
    assert n == 2

def test_ingest_backtest_decision_bullish(tmp_path):
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)
    dec = learner.find_best({"regime": "bullish", "volatility_bucket": "unknown"})
    assert dec is not None
    assert dec["exit_type"] == "tp_sl"
    assert dec["tp"] == 0.02

def test_ingest_backtest_decision_bearish(tmp_path):
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)
    dec = learner.find_best({"regime": "bearish", "volatility_bucket": "unknown"})
    assert dec is not None
    assert dec["exit_type"] == "trailing"
    assert dec["trail_pct"] == 0.005

def test_ingest_backtest_skips_meta(tmp_path):
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)
    assert len(learner.memory) == 2

def test_ingest_backtest_idempotent(tmp_path):
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)
    learner.ingest_backtest(FAKE_BACKTEST)
    assert len(learner.memory) == 2  # upsert, pas doublon


# ── MetaLearner.summary ───────────────────────────────────────────────────────

def test_summary_empty(tmp_path):
    learner = _learner(tmp_path)
    assert "0 entrées" in learner.summary()

def test_summary_contains_regime(tmp_path):
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)
    s = learner.summary()
    assert "bullish" in s
    assert "bearish" in s
    assert "tp_sl" in s
    assert "trailing" in s


# ── Intégration end-to-end ────────────────────────────────────────────────────

def test_learn_then_find_cycle(tmp_path):
    """Apprentissage → sauvegarde → rechargement → find."""
    learner = _learner(tmp_path)
    learner.learn(
        {"regime": "range", "volatility": 0.018},
        {"exit_type": "hybrid", "tp": 0.015, "sl": 0.008, "trail_pct": 0.005},
        {"sharpe": 1.7, "win_rate": 0.62, "avg_pnl": 0.011, "n_trades": 20},
    )

    learner2 = _learner(tmp_path)
    dec = learner2.find_best({"regime": "range", "volatility": 0.02})
    assert dec is not None
    assert dec["exit_type"] == "hybrid"
    assert dec["trail_pct"] == 0.005

def test_full_pipeline(tmp_path):
    """Backtester → ingest → find_best → learn amélioration → find_best."""
    learner = _learner(tmp_path)
    learner.ingest_backtest(FAKE_BACKTEST)

    # Simulation : après 50 trades live, on observe mieux
    learner.learn(
        {"regime": "bullish", "volatility_bucket": "unknown"},
        {"exit_type": "hybrid", "tp": 0.025, "sl": 0.012, "trail_pct": 0.005},
        {"sharpe": 3.1, "win_rate": 0.72, "avg_pnl": 0.018, "n_trades": 50},
    )

    dec = learner.find_best({"regime": "bullish", "volatility_bucket": "unknown"})
    assert dec["exit_type"] == "hybrid"
    assert dec["tp"] == 0.025
