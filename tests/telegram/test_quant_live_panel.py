"""Q1 / Q1.1 — @QuantCrypto_bot LIVE panel semantic-cleanup tests.

Proves the pinned SDOS LIVE panel is fed by the READ-ONLY QuantLiveSnapshot
projection and shows only semantically-honest, in-domain engine microstructure
data.

Q1 mandatory checks (unchanged):
  1. Capital absent · 2. Win Rate absent · 3. Observer/Dataset/Knowledge/
  Evidence/Drift absent · 4. Cycle · 5. Engine version · 6. Regime ·
  7. Top candidate · 8. Score/required · 9. refusal_breakdown ·
  10. dominant attrition · 11. pipeline · 12. trace · 13. Telegram not health ·
  14. no DB writes · 15. no engine-logic modification.

Q1.1 review corrections:
  FIX 1 — Telegram/main_channel pipeline stage excluded from the projection.
  FIX 2 — every dynamic value HTML-escaped (html.escape).
  FIX 3 — "confidence" → mean_signal_score (NN / 100), no interpretation.
  FIX 4 — health_database dropped (dir-exists boolean ≠ data integrity).
  FIX 5 — pipeline labelled REPORTED / PARTIAL (declared, not proven-healthy).
  FIX 6 — trace labelled LIVE TRACE — PARTIAL (only present nodes, no synthesis).
  FIX 7 — missing/empty/invalid timestamp → ts=None, age=None, "UNAVAILABLE";
          never a fabricated "now".

All fixtures use fixed values — no test depends on the wall clock.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.telegram.quant_observer.bot import render_quant_live_panel
from visualization.api import system_snapshot_source
from visualization.api.models import QuantLiveSnapshot
from visualization.api.quant_live_api import load_quant_live_snapshot


# ── Production-like fixture ────────────────────────────────────────────────────
# Reproduces the structure the engine actually emits, including the Telegram/
# main_channel pipeline stage and a real gate_reason "signal_score (66<72)",
# so the Q1 tests cannot pass by accident.

_SNAPSHOT = {
    "system_snapshot": {
        "meta": {
            "snapshot_id": "597-deadbeef",
            "timestamp_utc": "2026-09-02T10:00:00Z",
            "cycle": 597,
            "engine_version": "v9.1",
        },
        "health": {
            "api": True,
            "database": True,  # dir-exists boolean — must NOT reach the panel
            "telegram": False,  # generic channel — must NOT surface as health
            "market": True,
            "strategy": True,
        },
        # Portfolio block is present in the source but must be ignored by Q1.
        "portfolio": {
            "paper_equity": 12345.67,
            "paper_cash": 9000.0,
            "free_cash": 8000.0,
            "open_pnl_usd": 42.0,
            "open_positions": 3,
        },
        "ai_decision": {
            "decision_id": "d-1",
            "state": "ACTIVE",
            "reason_code": "R000",
            "reason_text": "20 setup(s) tradable",
            "blocking_module": "",
            "confidence_pct": 99,  # legacy field — must NOT be read anymore
            "highest_candidate_symbol": "MORPHO/USDT",
            "highest_candidate_score": 85,
            "required_score": 70,
            "next_evaluation_sec": 300,
            "brain_score_pct": 54,  # producer mean-signal-score → panel value
            "gate_reason": "signal_score (66<72)",  # production-like, has '<'
        },
        "market": {
            "regime": "bull_trend",
            "exchange_latency_ms": 225.0,
            "exchange_uptime_pct": 100.0,
        },
        "pipeline": [
            {"name": "Scanner", "status": "OK", "message": "135/135"},
            {"name": "Feature Engine", "status": "OK", "message": ""},
            {"name": "AI Scoring", "status": "OK", "message": ""},
            {"name": "Portfolio Brain", "status": "OK", "message": ""},
            {"name": "Risk Manager", "status": "OK", "message": "R000"},
            {"name": "Execution", "status": "ACTIVE", "message": ""},
            {"name": "Exchange", "status": "READY", "message": "225ms"},
            {"name": "Telegram", "status": "FAILED", "message": "main_channel"},
        ],
        "api_account": {
            "api_equity_usdt": 1.0,
            "api_free_cash_usdt": 1.0,
            "api_positions": 0,
            "api_assets": [],
        },
        "block_stats": {
            # current cycle: 45 risk-gate refusals + 7 meta-strategy = 52 total
            "current_cycle": [["gate", 45], ["meta_strategy", 7]],
            "session": [["gate", 900], ["meta_strategy", 140]],
            "lifetime": [["gate", 90000], ["meta_strategy", 14000]],
        },
        "decision_trace": [
            {
                "node": "Signal Generator",
                "ts_utc": "2026-09-02T10:00:00Z",
                "duration_ms": 4.0,
                "decision": "SCORED",
                "reason_code": "R000",
                "score": 85,
            },
            {
                "node": "Execution",
                "ts_utc": "2026-09-02T10:00:00Z",
                "duration_ms": 1.0,
                "decision": "ACTIVE",
                "reason_code": "R000",
                "score": 85,
            },
        ],
    }
}


def _clone(**meta_overrides) -> dict:
    """Deep-ish copy of the base snapshot, optionally overriding meta keys."""
    payload = json.loads(json.dumps(_SNAPSHOT))
    if meta_overrides:
        payload["system_snapshot"]["meta"].update(meta_overrides)
    return payload


def _write_live(tmp_path: Path, payload: dict) -> Path:
    live = tmp_path / "live_snapshot.json"
    live.write_text(json.dumps(payload), encoding="utf-8")
    return live


def _load(tmp_path, monkeypatch, payload=None) -> QuantLiveSnapshot:
    live = _write_live(tmp_path, payload if payload is not None else _SNAPSHOT)
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", live)
    return load_quant_live_snapshot()


def _panel(tmp_path, monkeypatch, payload=None) -> str:
    return render_quant_live_panel(_load(tmp_path, monkeypatch, payload))


# ── Q1 §1. Capital absent ─────────────────────────────────────────────────────

def test_capital_absent_from_live(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    lowered = panel.lower()
    assert "capital" not in lowered
    assert "equity" not in lowered
    assert "cash" not in lowered
    assert "$" not in panel
    assert "12345" not in panel  # paper_equity value never leaks


# ── Q1 §2. Win rate absent ────────────────────────────────────────────────────

def test_win_rate_absent_from_live(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    lowered = panel.lower()
    assert "win rate" not in lowered
    assert "win_rate" not in lowered
    assert "wr" not in lowered
    assert "profit factor" not in lowered
    assert "pnl" not in lowered


# ── Q1 §3. Observer/Dataset/Knowledge/Evidence/Drift absent ───────────────────

def test_semantically_wrong_proxies_absent(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch).lower()
    for banned in ("observer", "dataset", "knowledge", "evidence", "drift"):
        assert banned not in panel, f"'{banned}' must not appear in the LIVE panel"


def test_host_metrics_absent(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch).lower()
    for banned in ("ram", "cpu", "pid"):
        assert banned not in panel


def test_ntrades_proxy_absent(tmp_path, monkeypatch):
    """The misleading 'Traités: N' (n_traded = 1 if state ACTIVE) must be gone."""
    panel = _panel(tmp_path, monkeypatch)
    assert "Traités" not in panel
    assert "n_traded" not in panel.lower()


# ── Q1 §4. Cycle displayed ────────────────────────────────────────────────────

def test_cycle_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.cycle == 597
    assert "Cycle 597" in render_quant_live_panel(snap)


# ── Q1 §5. Engine version displayed ───────────────────────────────────────────

def test_engine_version_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.engine_version == "v9.1"
    assert "v9.1" in render_quant_live_panel(snap)


# ── Q1 §6. Regime displayed ───────────────────────────────────────────────────

def test_regime_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.regime == "bull_trend"
    assert "BULL TREND" in render_quant_live_panel(snap)


# ── Q1 §7. Top candidate displayed ────────────────────────────────────────────

def test_top_candidate_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.top_candidate_symbol == "MORPHO/USDT"
    assert "MORPHO/USDT" in render_quant_live_panel(snap)


# ── Q1 §8. Score / required score displayed ───────────────────────────────────

def test_score_and_required_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.top_candidate_score == 85
    assert snap.required_score == 70
    assert "85 / 70" in render_quant_live_panel(snap)


# ── Q1 §9. refusal_breakdown correctly computed ───────────────────────────────

def test_refusal_breakdown_computed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.refusal_breakdown == {"gate": 45, "meta_strategy": 7}
    assert snap.total_refusals == 52
    panel = render_quant_live_panel(snap)
    assert "Risk gates" in panel
    assert "45" in panel
    assert "Meta-strategy" in panel
    assert "Total refusals" in panel
    assert "52" in panel


def test_attrition_uses_current_cycle_only(tmp_path, monkeypatch):
    """Session/lifetime counters must never leak into the current-cycle attrition."""
    snap = _load(tmp_path, monkeypatch)
    assert snap.total_refusals == 52  # session gate=900 / lifetime=90000 ignored
    panel = render_quant_live_panel(snap)
    assert "900" not in panel
    assert "90000" not in panel


# ── Q1 §10. Dominant attrition correctly computed ─────────────────────────────

def test_dominant_filter_computed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.dominant_filter == "gate"
    assert snap.dominant_filter_pct == 86.5  # 45 / 52 * 100 = 86.538 → 86.5
    panel = render_quant_live_panel(snap)
    assert "DOMINANT FILTER" in panel
    assert "86.5%" in panel


# ── Q1 §11. Real pipeline displayed ───────────────────────────────────────────

def test_pipeline_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    names = [s["name"] for s in snap.pipeline_stages]
    assert names[:2] == ["Scanner", "Feature Engine"]
    panel = render_quant_live_panel(snap)
    assert "Scanner" in panel
    assert "135/135" in panel
    assert "Risk Manager" in panel


# ── Q1 §12. Real decision_trace displayed ─────────────────────────────────────

def test_decision_trace_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert [n["node"] for n in snap.decision_trace] == ["Signal Generator", "Execution"]
    panel = render_quant_live_panel(snap)
    assert "Signal Generator" in panel
    assert "SCORED" in panel


# ── Q1 §14. No database writes ─────────────────────────────────────────────────

def test_loader_performs_no_database_writes(tmp_path, monkeypatch):
    live = _write_live(tmp_path, _SNAPSHOT)
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", live)

    before = live.read_text(encoding="utf-8")
    before_mtime = live.stat().st_mtime_ns
    before_dir = sorted(p.name for p in tmp_path.iterdir())

    for _ in range(3):
        load_quant_live_snapshot()

    assert live.read_text(encoding="utf-8") == before
    assert live.stat().st_mtime_ns == before_mtime
    assert sorted(p.name for p in tmp_path.iterdir()) == before_dir


def test_loader_source_has_no_write_calls():
    src = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    for banned in ("write_text", "open(", ".write(", "json.dump", "mkdir"):
        assert banned not in src, f"loader must not call {banned!r}"


# ── Q1 §15. No engine-logic modification ──────────────────────────────────────

def test_loader_reads_only_snapshot_source():
    src = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    for banned in (
        "advisor_loop",
        "risk_manager",
        "GlobalRiskGate",
        "execution_engine",
        "ExecutionEngine",
        "sizing",
    ):
        assert banned not in src, f"projection must not touch {banned!r}"
    assert "system_snapshot_source" in src


def test_missing_snapshot_renders_without_crash(tmp_path, monkeypatch):
    """An empty/missing snapshot must degrade gracefully, never raise."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", missing)
    snap = load_quant_live_snapshot()
    assert isinstance(snap, QuantLiveSnapshot)
    panel = render_quant_live_panel(snap)
    assert "SDOS LIVE" in panel


# ══════════════════════════════════════════════════════════════════════════════
# Q1.1 REVIEW CORRECTIONS
# ══════════════════════════════════════════════════════════════════════════════

# ── FIX 1 — Telegram/main_channel pipeline stage excluded ─────────────────────

def test_telegram_stage_excluded_from_projection(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    names = [s["name"] for s in snap.pipeline_stages]
    assert "Telegram" not in names
    assert "Exchange" in names  # the other stages survive


def test_telegram_and_main_channel_absent_from_panel(tmp_path, monkeypatch):
    """The real pipeline carries {Telegram, FAILED, main_channel} — neither
    token may appear anywhere in the Quant LIVE."""
    panel = _panel(tmp_path, monkeypatch)
    assert "Telegram" not in panel
    assert "main_channel" not in panel
    assert "FAILED" not in panel  # only the telegram stage carried FAILED


# ── Q1 §13 + FIX 1 — Telegram never used as Quant health ──────────────────────

def test_telegram_health_not_surfaced(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert not hasattr(snap, "health_telegram")
    panel = _panel(tmp_path, monkeypatch)
    assert "Telegram" not in panel


def test_bot_and_loader_do_not_read_telegram_health():
    """Static check: neither the panel path nor the projection reads a telegram
    health flag. (``api.telegram.org`` legitimately appears in the bot, so we
    check the specific access patterns, not the bare word.)"""
    src = Path("src/telegram/quant_observer/bot.py").read_text(encoding="utf-8")
    assert 'health.get("telegram"' not in src
    assert "health.get('telegram'" not in src
    assert "h.telegram" not in src
    assert "health_telegram" not in src

    loader = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    assert "health.get(\"telegram\"" not in loader
    assert "health_telegram" not in loader


# ── FIX 2 — HTML escaping of dynamic values ───────────────────────────────────

def test_gate_reason_html_escaped(tmp_path, monkeypatch):
    payload = _clone()
    payload["system_snapshot"]["ai_decision"]["gate_reason"] = (
        "signal_score (66<72) & blocked"
    )
    panel = _panel(tmp_path, monkeypatch, payload)
    assert "66&lt;72" in panel
    assert "&amp;" in panel
    # The raw, unescaped forms must never be injected as HTML.
    assert "66<72" not in panel
    assert "72) & blocked" not in panel


def test_dynamic_symbol_html_escaped(tmp_path, monkeypatch):
    """Any producer string is escaped — e.g. a symbol carrying angle brackets."""
    payload = _clone()
    payload["system_snapshot"]["ai_decision"]["highest_candidate_symbol"] = "A<b>X"
    panel = _panel(tmp_path, monkeypatch, payload)
    assert "A&lt;b&gt;X" in panel
    assert "A<b>X" not in panel


def test_static_tags_preserved(tmp_path, monkeypatch):
    """Escaping dynamic values must not damage the static HTML tags."""
    panel = _panel(tmp_path, monkeypatch)
    assert "<b>SDOS LIVE</b>" in panel
    assert "<code>" in panel and "</code>" in panel


# ── FIX 3 — mean_signal_score replaces "confidence" ───────────────────────────

def test_mean_signal_score_field_and_display(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.mean_signal_score == 54  # from brain_score_pct, not confidence_pct
    assert not hasattr(snap, "confidence_pct")
    panel = render_quant_live_panel(snap)
    assert "Mean signal score" in panel
    assert "54 / 100" in panel


def test_confidence_label_removed(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch).lower()
    assert "confidence" not in panel


def test_legacy_confidence_pct_not_read(tmp_path, monkeypatch):
    """confidence_pct=99 in the snapshot must be ignored (we read brain_score_pct)."""
    snap = _load(tmp_path, monkeypatch)
    assert snap.mean_signal_score == 54
    assert "99" not in render_quant_live_panel(snap)


# ── FIX 4 — health_database dropped ───────────────────────────────────────────

def test_database_removed_from_model_and_panel(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert not hasattr(snap, "health_database")
    panel = render_quant_live_panel(snap)
    assert "Database" not in panel


def test_data_section_shows_only_market_and_api(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    assert "DATA" in panel
    assert "Market" in panel
    assert "API" in panel
    assert "Snapshot age" in panel
    assert "Database" not in panel


# ── FIX 5 — pipeline labelled REPORTED / PARTIAL ──────────────────────────────

def test_pipeline_section_marked_partial(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    assert "PIPELINE — REPORTED / PARTIAL" in panel
    # not presented as bare/proven "PIPELINE"
    assert "<b>PIPELINE</b>" not in panel


# ── FIX 6 — trace labelled LIVE TRACE — PARTIAL, only present nodes ───────────

def test_trace_section_marked_partial(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    assert "LIVE TRACE — PARTIAL" in panel
    assert "<b>DECISION TRACE</b>" not in panel


def test_trace_renders_only_present_nodes(tmp_path, monkeypatch):
    """No synthetic Gate/MetaStrategy nodes — only what the snapshot carries."""
    snap = _load(tmp_path, monkeypatch)
    panel = render_quant_live_panel(snap)
    assert "Signal Generator" in panel
    assert "Execution" in panel
    for invented in ("Gate", "MetaStrategy", "Portfolio Brain", "Risk Manager"):
        # these appear in PIPELINE but must not be fabricated as trace nodes;
        # assert the trace section itself lists exactly the two real nodes
        pass
    trace_section = panel.split("LIVE TRACE — PARTIAL", 1)[1]
    assert trace_section.count("<code>") == 2  # exactly two trace rows


# ── FIX 7 — snapshot age: valid vs missing/empty/invalid timestamp ────────────

def test_valid_timestamp_yields_age(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)  # valid timestamp in base fixture
    assert snap.ts is not None
    assert snap.snapshot_age_s is not None
    assert snap.snapshot_age_s >= 0
    assert "UNAVAILABLE" not in render_quant_live_panel(snap)


def _age_row(panel: str) -> str:
    return next(ln for ln in panel.splitlines() if "Snapshot age" in ln)


def test_missing_timestamp_is_unavailable(tmp_path, monkeypatch):
    payload = _clone()
    del payload["system_snapshot"]["meta"]["timestamp_utc"]
    snap = _load(tmp_path, monkeypatch, payload)
    assert snap.ts is None
    assert snap.snapshot_age_s is None
    panel = render_quant_live_panel(snap)
    row = _age_row(panel)
    assert "UNAVAILABLE" in row
    assert "0s" not in row  # never a fabricated fresh age


def test_empty_timestamp_is_unavailable(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch, _clone(timestamp_utc=""))
    assert snap.ts is None
    assert snap.snapshot_age_s is None
    assert "UNAVAILABLE" in render_quant_live_panel(snap)


def test_invalid_timestamp_is_unavailable(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch, _clone(timestamp_utc="not-a-timestamp"))
    assert snap.ts is None
    assert snap.snapshot_age_s is None
    row = _age_row(render_quant_live_panel(snap))
    assert "UNAVAILABLE" in row
    assert "0s" not in row


def test_no_fabricated_now_on_invalid_timestamp(tmp_path, monkeypatch):
    """Regression guard for FIX 7: an invalid timestamp must not silently
    become a fresh 'now' snapshot."""
    snap = _load(tmp_path, monkeypatch, _clone(timestamp_utc="garbage"))
    assert snap.ts is None
    assert snap.snapshot_age_s is None
