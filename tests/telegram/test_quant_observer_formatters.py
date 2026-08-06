"""Formatters — Telegram-HTML safety and honest rendering of absent values."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.telegram.quant_observer import formatters as f
from visualization.api.models import (
    BurnInSnapshot,
    CriSnapshot,
    LogLine,
    LogTailSnapshot,
    RegretInvestigationSnapshot,
    TimelineEvent,
    TimelineSnapshot,
)

TS = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


# ── Primitives ────────────────────────────────────────────────────────────────


def test_esc_neutralizes_markup():
    assert f.esc("<b>x</b>&") == "&lt;b&gt;x&lt;/b&gt;&amp;"


@pytest.mark.parametrize(
    "pct,expected_filled",
    [(0, 0), (50, 5), (100, 10), (-20, 0), (250, 10)],
)
def test_bar_is_clamped(pct, expected_filled):
    assert f.bar(pct, 10).count("█") == expected_filled
    assert len(f.bar(pct, 10)) == 10


def test_clip_respects_telegram_limit():
    text = "\n".join(f"line {i}" for i in range(2000))
    out = f.clip(text)

    assert len(out) <= f.TG_MAX_CHARS
    assert "tronqué" in out


def test_clip_leaves_short_text_untouched():
    assert f.clip("short") == "short"


def test_clip_cuts_on_line_boundaries():
    text = "\n".join(["<code>row</code>"] * 1000)
    out = f.clip(text)

    # No dangling half-tag from a mid-line cut.
    assert out.count("<code>") == out.count("</code>")


# ── CRI ───────────────────────────────────────────────────────────────────────


def _cri(**kw) -> CriSnapshot:
    base = dict(
        ts=TS,
        cri=42.5,
        cri_min=90,
        gate_ready=False,
        n_clean=120,
        n_regrets_clean=30,
        clean_data_since="2026-07-17T01:30:00+00:00",
        sub_scores={"n_score": 24.0, "coverage_score": 50.0},
        weights={"n": 40, "coverage": 30},
        validity="OK",
    )
    base.update(kw)
    return CriSnapshot(**base)


def test_unmeasured_cri_is_not_rendered_as_zero():
    out = f.format_cri(_cri(cri=None, error="dataset absent: /x.jsonl"))

    assert "NON MESURABLE" in out
    assert "0.00" not in out
    assert "n'est pas un CRI de 0" in out


def test_cri_shows_gate_status_and_provenance():
    out = f.format_cri(
        _cri(
            provenance={"close_events_total": 300, "excluded_by_reason": {"vieux": 180}}
        )
    )

    assert "42.50" in out
    assert "Gate NON atteinte" in out
    assert "300" in out
    assert "vieux" in out


def test_cri_gate_reached_is_announced():
    out = f.format_cri(_cri(cri=95.0, gate_ready=True))

    assert "Gate de calibration ATTEINTE" in out


def test_cri_warnings_are_shown():
    out = f.format_cri(_cri(validity="PARTIAL", warnings=["DATASET REGRET PÉRIMÉ"]))

    assert "PARTIAL" in out
    assert "PÉRIMÉ" in out


# ── Burn-in ───────────────────────────────────────────────────────────────────


def _burnin(**kw) -> BurnInSnapshot:
    base = dict(
        ts=TS,
        generated_at=TS,
        trades_count=49,
        trades_min=500,
        wins=20,
        wins_min=150,
        losses=29,
        losses_min=150,
        missed_win_count=10,
        missed_win_min=100,
        good_refusal_count=5,
        good_refusal_min=100,
        per_regime_min=50,
        per_layer_min=30,
        win_rate_pct=40.8,
        profit_factor=0.9,
        expectancy_pct=-0.3,
        coverage_pct=55.0,
        cri=None,
        cri_min=90,
        calibration_locked=True,
        go_no_go="NO-GO",
        blockers=["N insuffisant"],
    )
    base.update(kw)
    return BurnInSnapshot(**base)


def test_burnin_reports_locked_calibration():
    out = f.format_burnin(_burnin())

    assert "VERROUILLÉE" in out
    assert "49/500" in out.replace(" ", "")
    assert "NO-GO" in out
    assert "N insuffisant" in out


def test_burnin_flags_unlocked_calibration_loudly():
    out = f.format_burnin(_burnin(calibration_locked=False))

    assert "DÉVERROUILLÉE" in out
    assert "ADR requis" in out


def test_burnin_absent_cri_says_so():
    assert "non mesuré" in f.format_burnin(_burnin())
    assert "95.0/90" in f.format_burnin(_burnin(cri=95.0))


# ── Regret ────────────────────────────────────────────────────────────────────


def test_regret_escapes_layer_names():
    snap = RegretInvestigationSnapshot(
        ts=TS,
        regret_type="MISSED_WIN",
        n_total=3,
        by_layer={"<script>alert(1)</script>": 3},
        by_regime={"bull": 3},
        by_score_bin={"60-69": 3},
        by_week={"2026-W30": 3},
        first_evaluated_at=TS,
        last_evaluated_at=TS,
    )
    out = f.format_regret(snap)

    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "ADR-0007" in out


def test_regret_empty_is_explicit():
    snap = RegretInvestigationSnapshot(
        ts=TS,
        regret_type="GOOD_REFUSAL",
        n_total=0,
        by_layer={},
        by_regime={},
        by_score_bin={},
        by_week={},
        first_evaluated_at=None,
        last_evaluated_at=None,
    )
    out = f.format_regret(snap)

    assert "aucun enregistrement" in out


# ── Timeline ──────────────────────────────────────────────────────────────────


def test_timeline_escapes_and_limits():
    events = [
        TimelineEvent(
            packet_id=f"p{i}",
            ts=TS,
            symbol="<img src=x>",
            event_category="TRADE",
            lifecycle_state="REJECTED",
            regime="bull",
            conviction="SKIP",
            reason="blocked by <layer>",
        )
        for i in range(30)
    ]
    snap = TimelineSnapshot(
        ts=TS,
        events=events,
        total_packets=30,
        n_trade=30,
        n_system=0,
        n_rejected=30,
        n_executed=0,
    )
    out = f.format_timeline(snap, limit=5)

    assert "<img" not in out
    assert out.count("🔴") == 5


# ── Logs ──────────────────────────────────────────────────────────────────────


def test_logs_escape_untrusted_line_content():
    snap = LogTailSnapshot(
        ts=TS,
        source_path="logs/advisor_loop.log",
        exists=True,
        n_returned=1,
        n_scanned=1,
        level_filter="ALL",
        lines=[LogLine(raw="<b>injected</b> & done", level="ERROR")],
    )
    out = f.format_logs(snap)

    assert "<b>injected</b>" not in out
    assert "&lt;b&gt;injected" in out


def test_logs_report_redaction_count():
    snap = LogTailSnapshot(
        ts=TS,
        source_path="logs/advisor_loop.log",
        exists=True,
        n_returned=2,
        n_scanned=10,
        level_filter="ALL",
        lines=[LogLine(raw="ok", level="INFO")],
        n_redacted=3,
    )
    out = f.format_logs(snap)

    assert "3 masquées" in out


def test_logs_error_is_surfaced():
    snap = LogTailSnapshot(
        ts=TS,
        source_path="",
        exists=False,
        n_returned=0,
        n_scanned=0,
        level_filter="ALL",
        error="log file not found",
    )
    out = f.format_logs(snap)

    assert "log file not found" in out
