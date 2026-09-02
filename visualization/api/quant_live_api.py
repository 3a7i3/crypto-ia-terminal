"""Quant Live API — READ-ONLY SDOS projection for @QuantCrypto_bot (Q1).

Single read path, no business logic, no database writes:

    databases/live_snapshot.json
        -> visualization.api.system_snapshot_source (canonical adapter)
        -> load_quant_live_snapshot() -> QuantLiveSnapshot

The loader maps only semantically-honest, in-domain engine microstructure
fields. It never reads portfolio/capital, never fabricates aggregate health
percentages, and never touches the Telegram/main_channel health flag. See
``QuantLiveSnapshot`` for the exclusion rationale. ADR-0007 passivity: this is
observability, it observes and never decides.
"""
from __future__ import annotations

from datetime import datetime, timezone

from visualization.api.models import QuantLiveSnapshot
from visualization.api.system_snapshot_source import (
    load_system_snapshot_dict,
    load_system_snapshot_meta,
    parse_iso_dt,
)


def load_quant_live_snapshot() -> QuantLiveSnapshot:
    snap = load_system_snapshot_dict()
    meta = load_system_snapshot_meta()

    ts = parse_iso_dt(meta.get("timestamp_utc")) or datetime.now(timezone.utc)
    snapshot_age_s = max((datetime.now(timezone.utc) - ts).total_seconds(), 0.0)

    health = snap.get("health", {})
    market = snap.get("market", {})
    decision = snap.get("ai_decision", {})
    block_stats = snap.get("block_stats", {})

    # Attrition: current cycle ONLY (mission Q1). block_stats.current_cycle is a
    # list of [layer_name, count] pairs — never session/lifetime here.
    refusal_breakdown = {
        str(k): int(v)
        for k, v in dict(block_stats.get("current_cycle", [])).items()
    }

    pipeline_stages = [
        {
            "name": str(s.get("name", "")),
            "status": str(s.get("status", "")),
            "message": str(s.get("message", "")),
        }
        for s in snap.get("pipeline", [])
        if isinstance(s, dict)
    ]

    decision_trace = [
        {
            "node": str(n.get("node", "")),
            "decision": str(n.get("decision", "")),
            "score": float(n.get("score", 0.0) or 0.0),
            "reason_code": str(n.get("reason_code", "")),
        }
        for n in snap.get("decision_trace", [])
        if isinstance(n, dict)
    ]

    return QuantLiveSnapshot(
        ts=ts,
        cycle=int(meta.get("cycle", 0) or 0),
        engine_version=str(meta.get("engine_version", "") or ""),
        snapshot_age_s=snapshot_age_s,
        health_market=bool(health.get("market", False)),
        health_api=bool(health.get("api", False)),
        health_database=bool(health.get("database", False)),
        regime=str(market.get("regime", "unknown") or "unknown"),
        exchange_latency_ms=float(market.get("exchange_latency_ms", 0.0) or 0.0),
        exchange_uptime_pct=float(market.get("exchange_uptime_pct", 0.0) or 0.0),
        state=str(decision.get("state", "") or ""),
        top_candidate_symbol=str(decision.get("highest_candidate_symbol", "") or ""),
        top_candidate_score=float(decision.get("highest_candidate_score", 0.0) or 0.0),
        required_score=float(decision.get("required_score", 0.0) or 0.0),
        confidence_pct=int(decision.get("confidence_pct", 0) or 0),
        reason_text=str(decision.get("reason_text", "") or ""),
        gate_reason=str(decision.get("gate_reason", "") or ""),
        next_evaluation_sec=int(decision.get("next_evaluation_sec", 0) or 0),
        refusal_breakdown=refusal_breakdown,
        pipeline_stages=pipeline_stages,
        decision_trace=decision_trace,
    )
