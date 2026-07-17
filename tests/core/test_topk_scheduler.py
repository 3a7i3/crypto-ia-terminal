"""Ordonnanceur rotation top-K (ADR-0017 paliers 2-3) — zéro I/O réseau."""

import json

from core.topk_scheduler import (
    TopKScheduler,
    hot_symbols_from_latest,
    scheduler_from_env,
)

_UNI = [f"S{i}/USDT" for i in range(9)]


def test_flag_off_returns_none(monkeypatch):
    monkeypatch.delenv("SCANNER_TOPK_ENABLED", raising=False)

    assert scheduler_from_env(_UNI) is None


def test_k_ge_universe_selects_everything():
    """Équivalence : K >= n → tout l'univers est analysé chaque cycle."""
    sched = TopKScheduler(_UNI, k=50)

    assert set(sched.select()) == set(_UNI)


def test_open_positions_always_first():
    sched = TopKScheduler(_UNI, k=3)

    chosen = sched.select(open_symbols={"S7/USDT"}, hot_symbols=["S2/USDT"])

    assert chosen[0] == "S7/USDT"
    assert chosen[1] == "S2/USDT"
    assert len(chosen) == 3


def test_round_robin_covers_universe_with_bounded_revisit():
    """k=3, n=9, sans positions ni chaudes : 3 cycles couvrent tout
    l'univers sans répétition — revisite bornée à ceil(n/k) cycles."""
    sched = TopKScheduler(_UNI, k=3)

    seen: list[str] = []
    for _ in range(3):
        cycle = sched.select()
        assert len(cycle) == 3
        seen += cycle

    assert sorted(seen) == sorted(_UNI)  # couverture complète, zéro doublon


def test_priority_symbols_do_not_stall_rotation():
    """Une position permanente ne doit pas bloquer la rotation du reste."""
    sched = TopKScheduler(_UNI, k=3)

    seen: set[str] = set()
    for _ in range(8):
        seen |= set(sched.select(open_symbols={"S0/USDT"}))

    assert seen == set(_UNI)  # tout l'univers fini par passer


def test_symbols_outside_universe_ignored():
    """Les scanners n'existent que pour l'univers du boot — jamais hors liste."""
    sched = TopKScheduler(_UNI, k=4)

    chosen = sched.select(
        open_symbols={"GHOST/USDT"}, hot_symbols=["ALIEN/USDT", "S1/USDT"]
    )

    assert "GHOST/USDT" not in chosen
    assert "ALIEN/USDT" not in chosen
    assert chosen[0] == "S1/USDT"


def test_hot_symbols_from_latest_ranks_by_abs_change(tmp_path):
    latest = tmp_path / "latest_tick.json"
    latest.write_text(
        json.dumps(
            {
                "ts": 1.0,
                "pairs": {
                    "S1/USDT": {"chg": 2.0, "mkt": "spot"},
                    "S2/USDT": {"chg": -15.0, "mkt": "spot"},
                    "S3/USDT": {"chg": 7.0, "mkt": "spot"},
                    "HORS/USDT": {"chg": 99.0, "mkt": "spot"},  # hors univers
                },
            }
        ),
        encoding="utf-8",
    )

    hot = hot_symbols_from_latest(_UNI, n=2, path=latest)

    assert hot == ["S2/USDT", "S3/USDT"]  # tri par |variation|, univers seul


def test_hot_symbols_failsafe_on_missing_file(tmp_path):
    assert hot_symbols_from_latest(_UNI, n=3, path=tmp_path / "absent.json") == []
