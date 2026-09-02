"""Q1 — @QuantCrypto_bot LIVE panel semantic-cleanup tests.

Proves the pinned SDOS LIVE panel is fed by the READ-ONLY QuantLiveSnapshot
projection and shows only semantically-honest, in-domain engine microstructure
data. Covers the 15 mandatory checks of MISSION Q1:

  1. Capital absent from the LIVE panel.
  2. Win Rate absent.
  3. Observer/Dataset/Knowledge/Evidence/Drift absent.
  4. Cycle correctly displayed.
  5. Engine version correctly displayed.
  6. Regime correctly displayed.
  7. Top candidate correctly displayed.
  8. Score / required score correctly displayed.
  9. refusal_breakdown correctly computed.
 10. Dominant attrition correctly computed.
 11. Real pipeline displayed.
 12. Real decision_trace displayed.
 13. Telegram/main_channel not used as Quant health.
 14. No database writes.
 15. No engine-logic modification (projection reads only the snapshot source).

All fixtures use fixed values — no test depends on the wall clock.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.telegram.quant_observer.bot import render_quant_live_panel
from visualization.api import system_snapshot_source
from visualization.api.models import QuantLiveSnapshot
from visualization.api.quant_live_api import load_quant_live_snapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────

# The example snapshot from MISSION Q1 (§ PANEL Q1 CIBLE).
_EXAMPLE_SNAPSHOT = {
    "system_snapshot": {
        "meta": {
            "snapshot_id": "597-deadbeef",
            "timestamp_utc": "2026-09-02T10:00:00Z",
            "cycle": 597,
            "engine_version": "v9.1",
        },
        "health": {
            "api": True,
            "database": True,
            "telegram": False,  # generic channel — must NOT surface as Quant health
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
            "confidence_pct": 54,
            "highest_candidate_symbol": "MORPHO/USDT",
            "highest_candidate_score": 85,
            "required_score": 70,
            "next_evaluation_sec": 300,
            "brain_score_pct": 61,
            "gate_reason": "",
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


def _write_live(tmp_path: Path, payload: dict) -> Path:
    live = tmp_path / "live_snapshot.json"
    live.write_text(json.dumps(payload), encoding="utf-8")
    return live


def _load(tmp_path, monkeypatch, payload=_EXAMPLE_SNAPSHOT) -> QuantLiveSnapshot:
    live = _write_live(tmp_path, payload)
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", live)
    return load_quant_live_snapshot()


def _panel(tmp_path, monkeypatch, payload=_EXAMPLE_SNAPSHOT) -> str:
    return render_quant_live_panel(_load(tmp_path, monkeypatch, payload))


# ── 1. Capital absent ─────────────────────────────────────────────────────────

def test_capital_absent_from_live(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    lowered = panel.lower()
    assert "capital" not in lowered
    assert "equity" not in lowered
    assert "cash" not in lowered
    assert "$" not in panel
    assert "12345" not in panel  # paper_equity value never leaks


# ── 2. Win rate absent ────────────────────────────────────────────────────────

def test_win_rate_absent_from_live(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    lowered = panel.lower()
    assert "win rate" not in lowered
    assert "win_rate" not in lowered
    assert "wr" not in lowered
    assert "profit factor" not in lowered
    assert "pnl" not in lowered


# ── 3. Observer/Dataset/Knowledge/Evidence/Drift absent ───────────────────────

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


# ── 4. Cycle displayed ────────────────────────────────────────────────────────

def test_cycle_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.cycle == 597
    assert "Cycle 597" in render_quant_live_panel(snap)


# ── 5. Engine version displayed ───────────────────────────────────────────────

def test_engine_version_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.engine_version == "v9.1"
    assert "v9.1" in render_quant_live_panel(snap)


# ── 6. Regime displayed ───────────────────────────────────────────────────────

def test_regime_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.regime == "bull_trend"
    assert "BULL TREND" in render_quant_live_panel(snap)


# ── 7. Top candidate displayed ────────────────────────────────────────────────

def test_top_candidate_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.top_candidate_symbol == "MORPHO/USDT"
    assert "MORPHO/USDT" in render_quant_live_panel(snap)


# ── 8. Score / required score displayed ───────────────────────────────────────

def test_score_and_required_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.top_candidate_score == 85
    assert snap.required_score == 70
    assert "85 / 70" in render_quant_live_panel(snap)


# ── 9. refusal_breakdown correctly computed ───────────────────────────────────

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
    # session gate=900, lifetime gate=90000 must be ignored
    assert snap.total_refusals == 52
    panel = render_quant_live_panel(snap)
    assert "900" not in panel
    assert "90000" not in panel


# ── 10. Dominant attrition correctly computed ─────────────────────────────────

def test_dominant_filter_computed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert snap.dominant_filter == "gate"
    # 45 / 52 * 100 = 86.538... → 86.5
    assert snap.dominant_filter_pct == 86.5
    panel = render_quant_live_panel(snap)
    assert "DOMINANT FILTER" in panel
    assert "86.5%" in panel


# ── 11. Real pipeline displayed ───────────────────────────────────────────────

def test_pipeline_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    names = [s["name"] for s in snap.pipeline_stages]
    assert names[:2] == ["Scanner", "Feature Engine"]
    panel = render_quant_live_panel(snap)
    assert "PIPELINE" in panel
    assert "Scanner" in panel
    assert "135/135" in panel
    assert "Risk Manager" in panel


# ── 12. Real decision_trace displayed ─────────────────────────────────────────

def test_decision_trace_displayed(tmp_path, monkeypatch):
    snap = _load(tmp_path, monkeypatch)
    assert [n["node"] for n in snap.decision_trace] == ["Signal Generator", "Execution"]
    panel = render_quant_live_panel(snap)
    assert "DECISION TRACE" in panel
    assert "Signal Generator" in panel
    assert "SCORED" in panel


# ── 13. Telegram/main_channel not used as Quant health ────────────────────────

def test_telegram_health_not_surfaced(tmp_path, monkeypatch):
    """health.telegram is the generic historical channel — never the DATA row."""
    snap = _load(tmp_path, monkeypatch)
    assert not hasattr(snap, "health_telegram")
    panel = _panel(tmp_path, monkeypatch)
    assert "Telegram" not in panel
    assert "main_channel" not in panel


def test_bot_pinned_does_not_read_telegram_health():
    """Static check: the pinned panel path never reads the telegram health flag.

    (``api.telegram.org`` legitimately appears in the bot, so we check for the
    specific health-flag access patterns, not the bare word 'telegram'.)
    """
    src = Path("src/telegram/quant_observer/bot.py").read_text(encoding="utf-8")
    assert 'health.get("telegram"' not in src
    assert "health.get('telegram'" not in src
    assert "h.telegram" not in src
    assert "health_telegram" not in src

    loader = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    assert "telegram" not in loader  # projection never reads any telegram field


# ── 14. No database writes ────────────────────────────────────────────────────

def test_loader_performs_no_database_writes(tmp_path, monkeypatch):
    live = _write_live(tmp_path, _EXAMPLE_SNAPSHOT)
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", live)

    before = live.read_text(encoding="utf-8")
    before_mtime = live.stat().st_mtime_ns
    before_dir = sorted(p.name for p in tmp_path.iterdir())

    for _ in range(3):
        load_quant_live_snapshot()

    assert live.read_text(encoding="utf-8") == before  # content untouched
    assert live.stat().st_mtime_ns == before_mtime  # not rewritten
    assert sorted(p.name for p in tmp_path.iterdir()) == before_dir  # no new files


def test_loader_source_has_no_write_calls():
    src = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    for banned in ("write_text", "open(", ".write(", "json.dump", "mkdir"):
        assert banned not in src, f"loader must not call {banned!r}"


# ── 15. No engine-logic modification (projection reads only the snapshot) ──────

def test_loader_reads_only_snapshot_source():
    """The projection imports only the canonical read adapter + models —
    never the decision engine, risk manager, execution, or sizing."""
    src = Path("visualization/api/quant_live_api.py").read_text(encoding="utf-8")
    for banned in (
        "advisor_loop",
        "risk_manager",
        "GlobalRiskGate",
        "execution_engine",
        "ExecutionEngine",
        "meta_strategy",
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


# ── Sanity: DATA section shows only api/database/market booleans ───────────────

def test_data_section_shows_core_health_booleans(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    assert "DATA" in panel
    assert "Market" in panel
    assert "API" in panel
    assert "Database" in panel
    assert "Snapshot age" in panel
