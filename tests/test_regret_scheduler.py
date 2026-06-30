"""
Tests pour observability/regret_scheduler.py

Couvre : on_observation() enregistrement, tick() évaluation, calcul direction,
         MISSED_WIN / GOOD_REFUSAL / NEUTRAL, persistance JSONL, layer_performance(),
         filtre score minimum, filtre HOLD, update_price_cache() thread-safe.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from observability.regret_scheduler import (
    _HORIZONS,
    _MIN_MOVE_PCT,
    RegretCandidate,
    RegretScheduler,
    _compute_horizon,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_obs(**kwargs) -> Any:
    defaults = dict(
        observation_id="20260629-BTC-ABC",
        symbol="BTC/USDT",
        side="BUY",
        score=75.0,
        price=67000.0,
        ts=time.time(),
        regime="bull_trend",
        first_blocker="conviction",
        all_blockers=["conviction"],
        personality_name="momentum_following",
        trade_allowed=False,
        actionable=True,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_scheduler(tmp_path: Path) -> RegretScheduler:
    s = RegretScheduler(store_dir=tmp_path, poll_interval_s=9999.0)  # poll manuel
    return s


def _make_candidate(
    symbol: str = "BTC/USDT",
    side: str = "BUY",
    price: float = 100.0,
    *,
    ts_offset: float = 0.0,
) -> RegretCandidate:
    ts = time.time() + ts_offset
    c = RegretCandidate(
        observation_id=f"OBS-{symbol}-{int(ts)}",
        symbol=symbol,
        side=side,
        score=75.0,
        price_at_signal=price,
        ts_signal=ts,
        regime="bull_trend",
        first_blocker="conviction",
        all_blockers=["conviction"],
        personality_name="test",
    )
    return c


# ── Tests _compute_horizon ────────────────────────────────────────────────────


def test_compute_buy_price_up_is_missed_win():
    c = _make_candidate(side="BUY", price=100.0)
    result = _compute_horizon(c, "1h", 105.0)
    assert result.regret_type == "MISSED_WIN"
    assert result.direction_ok is True
    assert result.return_pct > 0


def test_compute_buy_price_down_is_good_refusal():
    c = _make_candidate(side="BUY", price=100.0)
    result = _compute_horizon(c, "1h", 95.0)
    assert result.regret_type == "GOOD_REFUSAL"
    assert result.direction_ok is False


def test_compute_sell_price_down_is_missed_win():
    c = _make_candidate(side="SELL", price=100.0)
    result = _compute_horizon(c, "1h", 95.0)
    assert result.regret_type == "MISSED_WIN"
    assert result.direction_ok is True


def test_compute_sell_price_up_is_good_refusal():
    c = _make_candidate(side="SELL", price=100.0)
    result = _compute_horizon(c, "1h", 105.0)
    assert result.regret_type == "GOOD_REFUSAL"


def test_compute_small_move_is_neutral():
    c = _make_candidate(price=100.0)
    # Mouvement < _MIN_MOVE_PCT
    tiny_move = 100.0 * (1 + _MIN_MOVE_PCT * 0.5)
    result = _compute_horizon(c, "5m", tiny_move)
    assert result.regret_type == "NEUTRAL"
    assert result.regret_score == 0.0


def test_compute_regret_score_capped_at_1():
    c = _make_candidate(price=100.0)
    result = _compute_horizon(c, "24h", 200.0)  # +100%
    assert result.regret_score == 1.0


def test_compute_zero_price_is_neutral():
    c = _make_candidate(price=0.0)
    result = _compute_horizon(c, "1h", 105.0)
    assert result.regret_type == "NEUTRAL"


# ── Tests on_observation ──────────────────────────────────────────────────────


def test_on_observation_registers_candidate(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs())
    assert len(s._candidates) == 1


def test_on_observation_ignores_allowed(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs(trade_allowed=True))
    assert len(s._candidates) == 0


def test_on_observation_ignores_non_actionable(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs(actionable=False))
    assert len(s._candidates) == 0


def test_on_observation_ignores_hold(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs(side="HOLD"))
    assert len(s._candidates) == 0


def test_on_observation_ignores_low_score(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs(score=30.0))
    assert len(s._candidates) == 0


def test_on_observation_all_7_horizons_pending(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs())
    c = list(s._candidates.values())[0]
    assert set(c.pending_horizons.keys()) == set(_HORIZONS.keys())


# ── Tests _tick / évaluation ──────────────────────────────────────────────────


def test_tick_evaluates_expired_horizon(tmp_path):
    s = _make_scheduler(tmp_path)
    obs = _fake_obs(observation_id="OBS-TICK-001")
    s.on_observation(obs)

    # Forcer toutes les deadlines dans le passé
    c = s._candidates["OBS-TICK-001"]
    for h in list(c.pending_horizons.keys()):
        c.pending_horizons[h] = time.time() - 1.0

    s.update_price_cache({"BTC/USDT": 70000.0})  # +4.5% → MISSED_WIN
    s._tick()

    # Le candidat doit être marqué complet et retiré
    assert "OBS-TICK-001" not in s._candidates


def test_tick_persists_jsonl(tmp_path):
    s = _make_scheduler(tmp_path)
    obs = _fake_obs(observation_id="OBS-PERSIST-001")
    s.on_observation(obs)

    c = s._candidates["OBS-PERSIST-001"]
    for h in list(c.pending_horizons.keys()):
        c.pending_horizons[h] = time.time() - 1.0

    s.update_price_cache({"BTC/USDT": 70000.0})
    s._tick()

    files = list(tmp_path.glob("regret_horizons_*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 1
    report = json.loads(lines[0])
    assert report["symbol"] == "BTC/USDT"
    assert "horizons" in report
    assert len(report["horizons"]) == 7


def test_tick_no_price_keeps_candidate(tmp_path):
    s = _make_scheduler(tmp_path)
    obs = _fake_obs(observation_id="OBS-NOPRICE")
    s.on_observation(obs)

    c = s._candidates["OBS-NOPRICE"]
    for h in list(c.pending_horizons.keys()):
        c.pending_horizons[h] = time.time() - 1.0

    # Pas de prix dans le cache → candidat doit rester
    s._tick()
    assert "OBS-NOPRICE" in s._candidates


def test_tick_partial_horizon_evaluation(tmp_path):
    s = _make_scheduler(tmp_path)
    obs = _fake_obs(observation_id="OBS-PARTIAL")
    s.on_observation(obs)

    c = s._candidates["OBS-PARTIAL"]
    # Expirer seulement les 3 premiers horizons
    expired = list(_HORIZONS.keys())[:3]
    for h in expired:
        c.pending_horizons[h] = time.time() - 1.0

    s.update_price_cache({"BTC/USDT": 70000.0})
    s._tick()

    # Le candidat doit encore être présent (horizons restants)
    assert "OBS-PARTIAL" in s._candidates
    assert len(c.results) == 3


# ── Tests layer_performance ───────────────────────────────────────────────────


def test_layer_performance_empty(tmp_path):
    s = _make_scheduler(tmp_path)
    result = s.layer_performance()
    assert result == {}


def test_layer_performance_from_jsonl(tmp_path):
    s = _make_scheduler(tmp_path)
    # Créer un faux fichier de rapport
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = tmp_path / f"regret_horizons_{today}.jsonl"
    report = {
        "observation_id": "OBS-001",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "score": 75.0,
        "all_blockers": ["conviction", "portfolio"],
        "missed_win_count": 3,
        "good_refusal_count": 1,
    }
    path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    perf = s.layer_performance()
    assert "conviction" in perf
    assert "portfolio" in perf
    assert perf["conviction"]["missed_wins"] == 3
    assert perf["conviction"]["total_rejections"] == 1


# ── Tests stats ───────────────────────────────────────────────────────────────


def test_stats_initial(tmp_path):
    s = _make_scheduler(tmp_path)
    stats = s.stats()
    assert stats["pending_candidates"] == 0
    assert stats["horizons_evaluated"] == 0
    assert stats["running"] is False


def test_stats_after_register(tmp_path):
    s = _make_scheduler(tmp_path)
    s.on_observation(_fake_obs())
    stats = s.stats()
    assert stats["pending_candidates"] == 1


# ── Test update_price_cache thread-safe ───────────────────────────────────────


def test_update_price_cache_concurrent(tmp_path):
    import threading

    s = _make_scheduler(tmp_path)
    errors: list[Exception] = []

    def updater(sym: str, price: float) -> None:
        try:
            for _ in range(50):
                s.update_price_cache({sym: price})
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=updater, args=(f"SYM{i}/USDT", float(i)))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    with s._price_lock:
        assert len(s._price_cache) == 5
