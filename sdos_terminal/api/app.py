"""SDOS Terminal — FastAPI backend.

Read-only REST API over the SDOS Data API (visualization/api/).
No database writes. No engine modification. Passive observer (ADR-0007).

Endpoints:
    GET /api/health       → HealthSnapshot (JSON)
    GET /api/pipeline     → PipelineSnapshot (JSON)
    GET /api/portfolio    → PortfolioSnapshot (JSON)
    GET /api/rejections   → RejectionsSnapshot — breakdown/couche + derniers rejets (JSON)
    GET /api/burnin       → BurnInSnapshot — progrès vs seuils statisticien (JSON)
    GET /api/regret       → RegretInvestigationSnapshot — breakdown MISSED_WIN/GOOD_REFUSAL (JSON)
    GET /api/decision/{packet_id} → DecisionTrace — chaîne causale complète (JSON)
    GET /api/system       → Combined system state (JSON)
    GET /api/snapshot.png → 4-panel snapshot PNG (image)
    GET /api/health.png   → Radar chart PNG
    GET /api/pipeline.png → Pipeline chart PNG
    GET /api/portfolio.png → Equity chart PNG
    WS  /ws/live          → Live system updates (JSON, every 10s)
"""
from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from visualization.api import (
    load_health_snapshot,
    load_pipeline_snapshot,
    load_portfolio_snapshot,
    load_scientific_snapshot,
    load_timeline_snapshot,
    load_datasets_snapshot,
    load_rejections_snapshot,
    load_decision_packet,
    load_burnin_snapshot,
    load_regret_investigation,
)
from visualization.renderers.snapshot import SnapshotBundle, SnapshotRenderer
from visualization.ves import VisualizationEngine

app = FastAPI(
    title="SDOS Terminal API",
    description="Read-only Scientific Decision Operating System data API",
    version="1.0",
    docs_url="/api/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_ves = VisualizationEngine()


# ── Serialization helpers ─────────────────────────────────────────────────────

def _dt(v) -> str | None:
    return v.isoformat() if v else None


def _health_dict(h) -> dict:
    return {
        "ts": _dt(h.ts),
        "observer_pct": h.observer_pct,
        "dataset_pct": h.dataset_pct,
        "knowledge_pct": h.knowledge_pct,
        "evidence_pct": h.evidence_pct,
        "capital_pct": h.capital_pct,
        "drift_pct": h.drift_pct,
        "system_state": h.system_state,
        "trading_enabled": h.trading_enabled,
        "capital_usd": h.capital_usd,
        "n_trades": h.n_trades,
        "win_rate_pct": h.win_rate_pct,
        "profit_factor": h.profit_factor,
        "heartbeat_age_seconds": h.heartbeat_age_seconds,
        "top_root_cause": h.top_root_cause,
        "top_root_cause_pct": h.top_root_cause_pct,
    }


def _pipeline_dict(p) -> dict:
    return {
        "ts": _dt(p.ts),
        "n_signals": p.n_signals,
        "n_traded": p.n_traded,
        "n_refused": p.n_refused,
        "pass_rate_pct": p.pass_rate_pct,
        "refusal_breakdown": p.refusal_breakdown,
        "regime_distribution": p.regime_distribution,
        "capital_usd": p.capital_usd,
        "cycle": p.cycle,
        "top_layer": p.top_layer,
    }


def _portfolio_dict(pf) -> dict:
    return {
        "ts": _dt(pf.ts),
        "n_trades": pf.n_trades,
        "n_wins": pf.n_wins,
        "n_losses": pf.n_losses,
        "win_rate_pct": pf.win_rate_pct,
        "profit_factor": pf.profit_factor,
        "expectancy_pct": pf.expectancy_pct,
        "max_drawdown_pct": pf.max_drawdown_pct,
        "sharpe": pf.sharpe,
        "total_pnl_usd": pf.total_pnl_usd,
        "avg_pnl_usd": pf.avg_pnl_usd,
        "avg_duration_h": pf.avg_duration_h,
        "capital_usd": pf.capital_usd,
    }


def _scientific_dict(s) -> dict:
    return {
        "ts": _dt(s.ts),
        "certification_level": s.certification_level,
        "certification_name": s.certification_name,
        "iii": s.iii,
        "ocs": s.ocs,
        "n_decisions_production": s.n_decisions_production,
        "n_knowledge_entries": s.n_knowledge_entries,
        "n_alerts_active": s.n_alerts_active,
        "n_counterfactuals": s.n_counterfactuals,
        "last_cert_at": _dt(s.last_cert_at),
        "cert_decision": s.cert_decision,
        "checks": s.checks,
    }


def _timeline_dict(t) -> dict:
    return {
        "ts": _dt(t.ts),
        "total_packets": t.total_packets,
        "n_trade": t.n_trade,
        "n_system": t.n_system,
        "n_rejected": t.n_rejected,
        "n_executed": t.n_executed,
        "events": [
            {
                "packet_id": e.packet_id,
                "ts": _dt(e.ts),
                "symbol": e.symbol,
                "event_category": e.event_category,
                "lifecycle_state": e.lifecycle_state,
                "regime": e.regime,
                "conviction": e.conviction,
                "reason": e.reason,
            }
            for e in t.events
        ],
    }


def _rejections_dict(r) -> dict:
    return {
        "ts": _dt(r.ts),
        "days_covered": r.days_covered,
        "n_entries": r.n_entries,
        "n_unique": r.n_unique,
        "by_layer": r.by_layer,
        "by_layer_pct": r.by_layer_pct,
        "by_regime": r.by_regime,
        "by_personality": r.by_personality,
        "recent": [
            {
                "packet_id": e.packet_id,
                "ts": e.ts_iso,
                "cycle": e.cycle,
                "symbol": e.symbol,
                "side": e.side,
                "regime": e.regime,
                "trade_allowed": e.trade_allowed,
                "first_blocker": e.first_blocker,
                "first_blocker_label": e.first_blocker_label,
            }
            for e in r.recent
        ],
    }


def _trace_dict(t) -> dict:
    return {
        "packet_id": t.packet_id,
        "observation_id": t.observation_id,
        "cycle": t.cycle,
        "symbol": t.symbol,
        "side": t.side,
        "score": t.score,
        "regime": t.regime,
        "personality": t.personality,
        "ts": t.ts_iso,
        "steps": [
            {"step": s.step, "name": s.name, "status": s.status, "detail": s.detail}
            for s in t.steps
        ],
        "first_blocker": t.first_blocker,
        "first_blocker_label": t.first_blocker_label,
        "all_blockers": t.all_blockers,
        "trade_allowed": t.trade_allowed,
        "verdict": t.verdict,
        "base_size_usd": t.base_size_usd,
    }


def _burnin_dict(b) -> dict:
    return {
        "ts": _dt(b.ts),
        "generated_at": _dt(b.generated_at),
        "trades_count": b.trades_count,
        "trades_min": b.trades_min,
        "wins": b.wins,
        "wins_min": b.wins_min,
        "losses": b.losses,
        "losses_min": b.losses_min,
        "missed_win_count": b.missed_win_count,
        "missed_win_min": b.missed_win_min,
        "good_refusal_count": b.good_refusal_count,
        "good_refusal_min": b.good_refusal_min,
        "per_regime_min": b.per_regime_min,
        "per_layer_min": b.per_layer_min,
        "win_rate_pct": b.win_rate_pct,
        "profit_factor": b.profit_factor,
        "expectancy_pct": b.expectancy_pct,
        "coverage_pct": b.coverage_pct,
        "cri": b.cri,
        "cri_min": b.cri_min,
        "calibration_locked": b.calibration_locked,
        "go_no_go": b.go_no_go,
        "blockers": b.blockers,
        "warnings": b.warnings,
    }


def _regret_investigation_dict(r) -> dict:
    return {
        "ts": _dt(r.ts),
        "regret_type": r.regret_type,
        "n_total": r.n_total,
        "by_layer": r.by_layer,
        "by_regime": r.by_regime,
        "by_score_bin": r.by_score_bin,
        "by_week": r.by_week,
        "first_evaluated_at": _dt(r.first_evaluated_at),
        "last_evaluated_at": _dt(r.last_evaluated_at),
    }


def _datasets_dict(d) -> dict:
    return {
        "ts": _dt(d.ts),
        "latest_level": d.latest_level,
        "latest_iii": d.latest_iii,
        "latest_ocs": d.latest_ocs,
        "certifications": [
            {
                "certification_id": c.certification_id,
                "generated_at": _dt(c.generated_at),
                "level": c.level,
                "level_name": c.level_name,
                "iii": c.iii,
                "ocs": c.ocs,
                "n_live_passed": c.n_live_passed,
                "n_live_failed": c.n_live_failed,
                "n_decisions_production": c.n_decisions_production,
                "decision": c.decision,
                "checks": c.checks,
            }
            for c in d.certifications
        ],
    }


# ── JSON endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health", summary="System health snapshot")
def get_health():
    return _health_dict(load_health_snapshot())


@app.get("/api/pipeline", summary="Decision pipeline snapshot")
def get_pipeline():
    return _pipeline_dict(load_pipeline_snapshot())


@app.get("/api/portfolio", summary="Portfolio performance snapshot")
def get_portfolio():
    return _portfolio_dict(load_portfolio_snapshot())


@app.get("/api/scientific", summary="Observer certification + DIP knowledge state")
def get_scientific():
    return _scientific_dict(load_scientific_snapshot())


@app.get("/api/timeline", summary="Decision packet stream (last 100 events)")
def get_timeline():
    return _timeline_dict(load_timeline_snapshot())


@app.get("/api/datasets", summary="Observer certification history")
def get_datasets():
    return _datasets_dict(load_datasets_snapshot())


@app.get("/api/rejections", summary="RejectionStore breakdown + recent events (Reject Analyzer)")
def get_rejections(days: int = 1, limit: int = 20):
    return _rejections_dict(load_rejections_snapshot(days=days, limit=limit))


@app.get("/api/burnin", summary="Burn-in progress vs statistician thresholds (CLAUDE.md)")
def get_burnin():
    return _burnin_dict(load_burnin_snapshot())


@app.get("/api/regret", summary="Regret breakdown by layer/regime/score/week (read-only investigation)")
def get_regret(regret_type: str = "MISSED_WIN"):
    return _regret_investigation_dict(load_regret_investigation(regret_type=regret_type))


@app.get("/api/decision/{packet_id}", summary="Full causal-chain trace for one decision packet")
def get_decision_packet(packet_id: str, days: int = 7):
    trace = load_decision_packet(packet_id, days=days)
    if trace is None:
        raise HTTPException(status_code=404, detail="Packet introuvable dans le RejectionStore")
    return _trace_dict(trace)


@app.get("/api/system", summary="Combined system state (all snapshots)")
def get_system():
    h = load_health_snapshot()
    p = load_pipeline_snapshot()
    pf = load_portfolio_snapshot()
    return {
        "health": _health_dict(h),
        "pipeline": _pipeline_dict(p),
        "portfolio": _portfolio_dict(pf),
        "sdos_version": "1.0",
        "svl_version": "1.0",
        "sva_version": "1.0",
    }


# ── PNG image endpoints ────────────────────────────────────────────────────────

@app.get("/api/snapshot.png", summary="4-panel SDOS snapshot (PNG)")
def get_snapshot_png():
    h = load_health_snapshot()
    p = load_pipeline_snapshot()
    pf = load_portfolio_snapshot()
    bundle = SnapshotBundle(health=h, pipeline=p, portfolio=pf)
    png = SnapshotRenderer(viewer_level=3).render(bundle)
    return Response(content=png, media_type="image/png")


@app.get("/api/health.png", summary="Health radar chart (PNG)")
def get_health_png():
    png = _ves.render(load_health_snapshot(), viewer_level=3)
    return Response(content=png, media_type="image/png")


@app.get("/api/pipeline.png", summary="Decision pipeline chart (PNG)")
def get_pipeline_png():
    png = _ves.render(load_pipeline_snapshot(), viewer_level=3)
    return Response(content=png, media_type="image/png")


@app.get("/api/portfolio.png", summary="Portfolio equity chart (PNG)")
def get_portfolio_png():
    png = _ves.render(load_portfolio_snapshot(), viewer_level=3)
    return Response(content=png, media_type="image/png")


# ── WebSocket — live updates ──────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """Push system snapshots every 10 seconds to connected clients."""
    await ws.accept()
    try:
        while True:
            data = {
                "health": _health_dict(load_health_snapshot()),
                "pipeline": _pipeline_dict(load_pipeline_snapshot()),
                "portfolio": _portfolio_dict(load_portfolio_snapshot()),
            }
            await ws.send_text(json.dumps(data, default=str))
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
    except Exception:
        await ws.close()


# ── Static files (frontend) ───────────────────────────────────────────────────

_STATIC = Path(__file__).parent.parent / "frontend" / "dist"
if _STATIC.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="frontend")
