"""CRI API — the index must never fabricate a score it did not measure."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE
from visualization.api.cri_api import CRI_MIN, load_cri_snapshot


def _close(ts, pnl_usd: float, score: float = 70.0, price: float = 30000.0) -> dict:
    # The canonical loader reads `ts` as a POSIX epoch (tools/cri_calculator._event_ts).
    return {
        "event": "CLOSE",
        "ts": ts.timestamp(),
        "pnl_usd": pnl_usd,
        "score": score,
        "price": price,
        "duration_s": 3600,
        "regime": "bull_trend",
    }


@pytest.fixture
def trades_file(tmp_path):
    def _write(records: list[dict]):
        path = tmp_path / "paper_trades.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
        )
        return path

    return _write


@pytest.fixture
def regret_file(tmp_path):
    path = tmp_path / "regret_analysis.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def test_absent_dataset_yields_none_not_zero(tmp_path, regret_file):
    """A missing source file must read as "not measured", never as CRI 0."""
    snap = load_cri_snapshot(
        trades_path=tmp_path / "does_not_exist.jsonl", regret_path=regret_file
    )

    assert snap.cri is None
    assert snap.gate_ready is False
    assert snap.validity == "UNAVAILABLE"
    assert "absent" in (snap.error or "")
    assert snap.cri_min == CRI_MIN == 90


def test_empty_after_filters_flags_vacuous_index(trades_file, regret_file):
    """File present but everything filtered out → computed, flagged, not silent."""
    stale = CLEAN_DATA_SINCE_ACTIVE - timedelta(days=30)
    snap = load_cri_snapshot(
        trades_path=trades_file([_close(stale, 10.0)]), regret_path=regret_file
    )

    assert snap.n_clean == 0
    assert snap.validity == "PARTIAL"
    assert any("N=0" in w for w in snap.warnings)


def test_clean_trades_produce_scores_and_provenance(trades_file, regret_file):
    base = CLEAN_DATA_SINCE_ACTIVE + timedelta(hours=1)
    records = [
        _close(base + timedelta(hours=i), 12.0 if i % 2 else -8.0, score=60.0 + i)
        for i in range(10)
    ]
    snap = load_cri_snapshot(trades_path=trades_file(records), regret_path=regret_file)

    assert snap.cri is not None
    assert 0.0 <= snap.cri <= 100.0
    assert snap.n_clean == 10
    assert snap.clean_data_since == CLEAN_DATA_SINCE_ACTIVE.isoformat()
    assert set(snap.sub_scores) == {
        "n_score",
        "coverage_score",
        "drift_score",
        "balance_score",
    }
    # Provenance must make the population reconstructible (INV-DATASET-001).
    assert snap.provenance["n_canonical"] == 10
    assert snap.provenance["loader"] == "tools.cri_calculator.load_clean_trades"


def test_excluded_records_are_reported_in_provenance(trades_file, regret_file):
    base = CLEAN_DATA_SINCE_ACTIVE + timedelta(hours=1)
    stale = CLEAN_DATA_SINCE_ACTIVE - timedelta(days=1)
    snap = load_cri_snapshot(
        trades_path=trades_file([_close(base, 5.0), _close(stale, 5.0)]),
        regret_path=regret_file,
    )

    assert snap.n_clean == 1
    assert snap.provenance["excluded_by_reason"] == {"anterieur_borne_canonique": 1}


def test_gate_not_ready_below_threshold(trades_file, regret_file):
    base = CLEAN_DATA_SINCE_ACTIVE + timedelta(hours=1)
    snap = load_cri_snapshot(
        trades_path=trades_file([_close(base, 5.0)]), regret_path=regret_file
    )

    # N=1 cannot clear a 90/100 readiness gate.
    assert snap.gate_ready is False
    assert snap.cri < CRI_MIN
