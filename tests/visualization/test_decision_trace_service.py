"""
tests/visualization/test_decision_trace_service.py — DecisionTraceService.

Couvre la logique métier partagée entre tools/decision_trace.py (CLI) et
visualization/api/decision_api.py (SDOS Data API) : parsing/dédoublonnage du
RejectionStore, reconstruction de la chaîne causale et agrégats statistiques.
Aucun accès aux données réelles — fixtures synthétiques en tmp_path.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from visualization.decision_trace_service import DecisionTraceService, label_for


def _entry(**overrides) -> dict:
    base = {
        "packet_id": "pid-0001",
        "observation_id": "obs-0001",
        "cycle": 1,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "score": 82.0,
        "regime": "bull_trend",
        "ts_iso": "2026-06-30T07:13:10+00:00",
        "ts": 1782803590.0,
        "gate_failed": [],
        "meta_reason": "OK",
        "personality_name": "momentum",
        "conviction_level": None,
        "conviction_score": None,
        "portfolio_reason": None,
        "override_level": None,
        "override_reason": None,
        "mistake_reason": None,
        "radar_level": None,
        "radar_threat_count": 0,
        "arbitration_decision": None,
        "first_blocker": None,
        "all_blockers": [],
        "trade_allowed": True,
        "human_verdict": "AUTORISÉ",
        "base_size_usd": 25.0,
    }
    base.update(overrides)
    return base


def _write_day(rejections_dir: Path, day: date, entries: list[dict]) -> None:
    path = rejections_dir / f"rejections_{day}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def service(tmp_path: Path) -> DecisionTraceService:
    return DecisionTraceService(rejections_dir=tmp_path)


# ── load_entries ───────────────────────────────────────────────────────────────


def test_load_entries_filters_by_symbol_and_cycle(
    service: DecisionTraceService, tmp_path: Path
):
    day = date(2026, 6, 30)
    _write_day(
        tmp_path,
        day,
        [
            _entry(packet_id="p1", symbol="BTC/USDT", cycle=1),
            _entry(packet_id="p2", symbol="ETH/USDT", cycle=1),
            _entry(packet_id="p3", symbol="BTC/USDT", cycle=2),
        ],
    )

    all_entries = service.load_entries(day=day)
    assert len(all_entries) == 3

    by_symbol = service.load_entries(day=day, symbol="BTC")
    assert {e["packet_id"] for e in by_symbol} == {"p1", "p3"}

    by_cycle = service.load_entries(day=day, cycle=2)
    assert {e["packet_id"] for e in by_cycle} == {"p3"}


def test_load_entries_dedups_by_packet_id(
    service: DecisionTraceService, tmp_path: Path
):
    day = date(2026, 6, 30)
    _write_day(
        tmp_path,
        day,
        [
            _entry(packet_id="dup"),
            _entry(packet_id="dup"),
            _entry(packet_id="unique"),
        ],
    )

    entries = service.load_entries(day=day)
    assert len(entries) == 2
    assert {e["packet_id"] for e in entries} == {"dup", "unique"}


def test_load_entries_missing_file_returns_empty(service: DecisionTraceService):
    assert service.load_entries(day=date(2099, 1, 1)) == []


def test_load_entries_skips_malformed_lines(
    service: DecisionTraceService, tmp_path: Path
):
    day = date(2026, 6, 30)
    path = tmp_path / f"rejections_{day}.jsonl"
    path.write_text(
        json.dumps(_entry(packet_id="ok")) + "\nnot json\n",
        encoding="utf-8",
    )
    entries = service.load_entries(day=day)
    assert len(entries) == 1
    assert entries[0]["packet_id"] == "ok"


# ── load_recent_entries ────────────────────────────────────────────────────────


def test_load_recent_entries_spans_multiple_days(
    service: DecisionTraceService, tmp_path: Path
):
    end = date(2026, 6, 30)
    _write_day(tmp_path, end, [_entry(packet_id="today")])
    _write_day(tmp_path, end - timedelta(days=1), [_entry(packet_id="yesterday")])
    _write_day(tmp_path, end - timedelta(days=5), [_entry(packet_id="too_old")])

    entries = service.load_recent_entries(days=2, end_day=end)
    assert {e["packet_id"] for e in entries} == {"today", "yesterday"}


# ── build_trace ────────────────────────────────────────────────────────────────


def test_build_trace_all_pass_when_allowed(service: DecisionTraceService):
    entry = _entry(trade_allowed=True, all_blockers=[])
    trace = service.build_trace(entry)

    assert trace.trade_allowed is True
    assert trace.first_blocker is None
    step2_gate = trace.steps[1]
    assert step2_gate.status is True


def test_build_trace_marks_blocked_layer_as_false(service: DecisionTraceService):
    entry = _entry(
        trade_allowed=False,
        first_blocker="meta_strategy(score<66)",
        all_blockers=["meta_strategy(score<66)"],
        meta_reason="score<66",
        human_verdict="REFUSÉ",
    )
    trace = service.build_trace(entry)

    assert trace.trade_allowed is False
    assert trace.first_blocker == "meta_strategy(score<66)"
    meta_step = next(s for s in trace.steps if s.name.startswith("MetaStrategy"))
    assert meta_step.status is False
    assert trace.first_blocker_label == label_for("meta_strategy(score<66)")


def test_trace_and_find_by_packet_id_across_days(
    service: DecisionTraceService, tmp_path: Path
):
    end = date(2026, 6, 30)
    _write_day(
        tmp_path,
        end - timedelta(days=3),
        [_entry(packet_id="deep-pid", symbol="SOL/USDT")],
    )

    found = service.find_by_packet_id("deep-pid", days=7, end_day=end)
    assert found is not None
    assert found["symbol"] == "SOL/USDT"

    trace = service.trace("deep-pid", days=7, end_day=end)
    assert trace is not None
    assert trace.symbol == "SOL/USDT"

    assert service.find_by_packet_id("does-not-exist", days=7, end_day=end) is None
    assert service.trace("does-not-exist", days=7, end_day=end) is None


# ── statistics / rejections / timeline ─────────────────────────────────────────


def test_statistics_aggregates_by_layer_regime_personality(
    service: DecisionTraceService,
):
    entries = [
        _entry(
            packet_id="p1",
            all_blockers=["meta_strategy(score<66)"],
            regime="bull_trend",
            personality_name="momentum",
        ),
        _entry(
            packet_id="p2",
            all_blockers=["meta_strategy(score<66)"],
            regime="sideways",
            personality_name="scalp",
        ),
        _entry(
            packet_id="p3",
            all_blockers=["portfolio(size=0)"],
            regime="bull_trend",
            personality_name="momentum",
        ),
    ]
    stats = service.statistics(entries)

    assert stats["n_entries"] == 3
    assert stats["n_unique"] == 3
    assert stats["by_layer"] == {"meta_strategy": 2, "portfolio": 1}
    assert stats["by_layer_pct"]["meta_strategy"] == pytest.approx(66.7, abs=0.1)
    assert stats["by_regime"] == {"bull_trend": 2, "sideways": 1}
    assert stats["by_personality"] == {"momentum": 2, "scalp": 1}


def test_rejections_snapshot_combines_stats_and_recent(
    service: DecisionTraceService, tmp_path: Path
):
    day = date(2026, 6, 30)
    _write_day(
        tmp_path,
        day,
        [
            _entry(packet_id="p1", ts=100.0, all_blockers=["meta_strategy(score<66)"]),
            _entry(packet_id="p2", ts=200.0, all_blockers=["portfolio(size=0)"]),
        ],
    )

    snapshot = service.rejections(days=1, limit=10, end_day=day)

    assert snapshot.n_entries == 2
    assert snapshot.n_unique == 2
    assert set(snapshot.by_layer) == {"meta_strategy", "portfolio"}
    assert snapshot.days_covered[0] == str(day)
    assert [e.packet_id for e in snapshot.recent] == ["p2", "p1"]


def test_timeline_sorts_most_recent_first(
    service: DecisionTraceService, tmp_path: Path
):
    day = date(2026, 6, 30)
    _write_day(
        tmp_path,
        day,
        [
            _entry(packet_id="old", ts=100.0),
            _entry(packet_id="new", ts=999.0),
        ],
    )

    events = service.timeline(days=2, limit=10, end_day=day)
    ids = [e.packet_id for e in events if e.packet_id in ("old", "new")]
    assert ids == ["new", "old"]


def test_timeline_respects_limit(service: DecisionTraceService, tmp_path: Path):
    day = date(2026, 6, 30)
    _write_day(
        tmp_path, day, [_entry(packet_id=f"p{i}", ts=float(i)) for i in range(10)]
    )

    events = service.timeline(days=2, limit=3, end_day=day)
    assert len(events) == 3


# ── label_for ──────────────────────────────────────────────────────────────────


def test_label_for_known_and_unknown_layer():
    assert label_for("meta_strategy(score<66)").startswith("MetaStrategy")
    assert label_for("totally_unknown_layer") == "totally_unknown_layer"
