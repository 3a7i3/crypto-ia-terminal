"""Tests for scripts/regret_horizons_analysis.py — v2 multi-horizon regret analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.regret_horizons_analysis import (
    _horizon_verdict,
    _load_records,
    _score_bin,
    lens_blocker,
    lens_cross,
    lens_panorama,
    lens_regime,
    lens_score_bin,
    lens_symbols,
    lens_trajectory,
    summary,
)


def _make_record(
    ts: float = 1721350000.0,
    symbol: str = "BTC/USDT",
    side: str = "BUY",
    score: float = 72.0,
    first_blocker: str = "meta",
    regime: str = "sideways",
    horizon_verdicts: dict[str, str] | None = None,
) -> dict:
    if horizon_verdicts is None:
        horizon_verdicts = {"1h": "MISSED_WIN", "4h": "GOOD_REFUSAL"}

    horizons = {}
    for h, rt in horizon_verdicts.items():
        regret_score = 0.5 if rt == "MISSED_WIN" else 0.0
        return_pct = 2.5 if rt == "MISSED_WIN" else (-1.5 if rt == "GOOD_REFUSAL" else 0.3)
        horizons[h] = {
            "horizon": h,
            "ts_eval": ts + 3600,
            "price_at_signal": 65000.0,
            "price_at_eval": 65000.0 * (1 + return_pct / 100),
            "return_pct": return_pct,
            "direction_ok": rt == "MISSED_WIN",
            "mfe_pct": max(0, return_pct),
            "mae_pct": min(0, return_pct),
            "regret_score": regret_score,
            "regret_type": rt,
        }

    missed = sum(1 for h in horizons.values() if h["regret_type"] == "MISSED_WIN")
    good = sum(1 for h in horizons.values() if h["regret_type"] == "GOOD_REFUSAL")
    neutral = sum(1 for h in horizons.values() if h["regret_type"] == "NEUTRAL")

    return {
        "observation_id": f"TEST-{symbol}-{int(ts)}",
        "ts_signal": ts,
        "ts_iso_signal": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side,
        "score": score,
        "price_at_signal": 65000.0,
        "regime": regime,
        "first_blocker": first_blocker,
        "all_blockers": [first_blocker],
        "personality_name": "conservative",
        "horizons": horizons,
        "missed_win_count": missed,
        "good_refusal_count": good,
        "neutral_count": neutral,
        "max_regret_score": max((h["regret_score"] for h in horizons.values()), default=0),
        "best_horizon": max(horizons, key=lambda h: horizons[h]["return_pct"]),
        "worst_horizon": min(horizons, key=lambda h: horizons[h]["return_pct"]),
    }


class TestScoreBin:
    def test_bins(self):
        assert _score_bin(55.0) == "<60"
        assert _score_bin(60.0) == "60-64"
        assert _score_bin(64.9) == "60-64"
        assert _score_bin(65.0) == "65-69"
        assert _score_bin(90.0) == "90+"
        assert _score_bin(100.0) == "90+"


class TestHorizonVerdict:
    def test_present(self):
        r = _make_record(horizon_verdicts={"1h": "MISSED_WIN", "4h": "GOOD_REFUSAL"})
        assert _horizon_verdict(r, "1h") == "MISSED_WIN"
        assert _horizon_verdict(r, "4h") == "GOOD_REFUSAL"

    def test_absent(self):
        r = _make_record(horizon_verdicts={"1h": "MISSED_WIN"})
        assert _horizon_verdict(r, "24h") is None

    def test_no_horizons(self):
        r = {"horizons": None}
        assert _horizon_verdict(r, "1h") is None


class TestLoadRecords:
    def test_filters_by_since(self, tmp_path):
        fp = tmp_path / "regret_horizons_2026-07-20.jsonl"
        r1 = _make_record(ts=1000.0)
        r2 = _make_record(ts=2000.0)
        r3 = _make_record(ts=3000.0)
        fp.write_text(
            "\n".join(json.dumps(r) for r in [r1, r2, r3]), encoding="utf-8"
        )
        result = _load_records(tmp_path, since_ts=1500.0)
        assert len(result) == 2

    def test_empty_dir(self, tmp_path):
        result = _load_records(tmp_path, since_ts=0.0)
        assert result == []

    def test_skips_bad_json(self, tmp_path):
        fp = tmp_path / "regret_horizons_2026-07-20.jsonl"
        good = _make_record(ts=1000.0)
        fp.write_text(
            json.dumps(good) + "\n" + "not json\n" + json.dumps(good) + "\n",
            encoding="utf-8",
        )
        result = _load_records(tmp_path, since_ts=0.0)
        assert len(result) == 2


class TestLenses:
    """Smoke tests — verify lenses don't crash and produce output."""

    @pytest.fixture
    def records(self):
        return [
            _make_record(
                ts=1721350000.0 + i * 3600,
                symbol=["BTC/USDT", "ETH/USDT"][i % 2],
                score=60 + i * 3,
                first_blocker=["meta", "gate", "conviction"][i % 3],
                regime=["sideways", "TREND_BULL"][i % 2],
                horizon_verdicts={
                    "1h": ["MISSED_WIN", "GOOD_REFUSAL", "NEUTRAL"][i % 3],
                    "4h": ["GOOD_REFUSAL", "MISSED_WIN", "NEUTRAL"][i % 3],
                },
            )
            for i in range(30)
        ]

    def test_summary(self, records, capsys):
        summary(records, "1h")
        out = capsys.readouterr().out
        assert "SUMMARY" in out
        assert "MISSED_WIN" in out

    def test_panorama(self, records, capsys):
        lens_panorama(records, "1h")
        out = capsys.readouterr().out
        assert "PANORAMA" in out
        assert "1h" in out

    def test_blocker(self, records, capsys):
        lens_blocker(records, "1h")
        out = capsys.readouterr().out
        assert "BLOCKER" in out
        assert "meta" in out

    def test_regime(self, records, capsys):
        lens_regime(records, "1h")
        out = capsys.readouterr().out
        assert "REGIME" in out
        assert "sideways" in out

    def test_score_bin(self, records, capsys):
        lens_score_bin(records, "1h")
        out = capsys.readouterr().out
        assert "SCORE BIN" in out

    def test_cross(self, records, capsys):
        lens_cross(records, "1h")
        out = capsys.readouterr().out
        assert "CROSS" in out

    def test_symbols(self, records, capsys):
        lens_symbols(records, "1h", top_n=5)
        out = capsys.readouterr().out
        assert "SYMBOLES" in out
        assert "BTC/USDT" in out

    def test_trajectory(self, records, capsys):
        lens_trajectory(records, "1h")
        out = capsys.readouterr().out
        assert "TRAJECTOIRE" in out

    def test_empty_records(self, capsys):
        summary([], "1h")
        out = capsys.readouterr().out
        assert "Aucun enregistrement" in out
