from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tracker_system.sessions.session_analyzer import SessionAnalyzer
from tracker_system.sessions.session_manager import SESSIONS_ROOT, load_session_trades


def compare_sessions(session_id_a: str, session_id_b: str) -> dict[str, Any]:
    """Compare deux sessions et retourne les deltas KPI + régime."""
    dir_a = SESSIONS_ROOT / session_id_a
    dir_b = SESSIONS_ROOT / session_id_b

    for sid, d in [(session_id_a, dir_a), (session_id_b, dir_b)]:
        if not d.exists():
            raise FileNotFoundError(f"Session introuvable : {sid} → {d}")

    trades_a = load_session_trades(dir_a)
    trades_b = load_session_trades(dir_b)

    analyzer = SessionAnalyzer()
    analysis_a = analyzer.analyze(trades_a)
    analysis_b = analyzer.analyze(trades_b)

    kpi_delta = _compute_kpi_delta(analysis_a, analysis_b)
    regime_delta = _compute_regime_delta(
        analysis_a.get("regime_matrix", {}),
        analysis_b.get("regime_matrix", {}),
    )

    kpis_a = _extract_kpis(analysis_a)
    kpis_b = _extract_kpis(analysis_b)
    return {
        "session_a": session_id_a,
        "session_b": session_id_b,
        "winner": _determine_winner(kpis_a, kpis_b),
        "kpi_delta": kpi_delta,
        "regime_delta": regime_delta,
        "raw": {
            session_id_a: kpis_a,
            session_id_b: kpis_b,
        },
    }


def _extract_kpis(analysis: dict) -> dict[str, Any]:
    return {
        "trades": analysis.get("summary", {}).get("trades", 0),
        "winrate": analysis.get("summary", {}).get("winrate", 0.0),
        "profit_factor": analysis.get("profit_factor", 0.0),
        "expectancy": analysis.get("expectancy", {}).get("value", 0.0),
        "trade_quality_score": analysis.get("trade_quality_score", 0.0),
        "recovery_factor": analysis.get("recovery_factor", 0.0),
        "stability_index": analysis.get("signal_stability", {}).get("index", 0.0),
        "pnl_total_usd": analysis.get("summary", {}).get("pnl_total_usd", 0.0),
    }


def _compute_kpi_delta(a: dict, b: dict) -> dict[str, str]:
    kpis_a = _extract_kpis(a)
    kpis_b = _extract_kpis(b)
    delta: dict[str, str] = {}
    for key in kpis_a:
        val_a = kpis_a[key]
        val_b = kpis_b[key]
        if (
            isinstance(val_a, (int, float))
            and isinstance(val_b, (int, float))
            and val_a != float("inf")
            and val_b != float("inf")
        ):
            diff = val_b - val_a
            sign = "+" if diff >= 0 else ""
            delta[key] = f"{sign}{diff:.4f}"
        else:
            delta[key] = f"{val_a} → {val_b}"
    return delta


def _compute_regime_delta(matrix_a: dict, matrix_b: dict) -> dict[str, Any]:
    all_regimes = set(matrix_a) | set(matrix_b)
    delta: dict[str, Any] = {}
    for regime in all_regimes:
        a = matrix_a.get(regime, {})
        b = matrix_b.get(regime, {})
        exp_a = a.get("expectancy", 0.0)
        exp_b = b.get("expectancy", 0.0)
        if isinstance(exp_a, (int, float)) and isinstance(exp_b, (int, float)):
            diff = exp_b - exp_a
            sign = "+" if diff >= 0 else ""
            delta[regime] = {
                "expectancy_delta": f"{sign}{diff:.4f}",
                "trades_a": a.get("trades", 0),
                "trades_b": b.get("trades", 0),
            }
    return delta


def _determine_winner(kpis_a: dict, kpis_b: dict) -> str:
    exp_a = kpis_a.get("expectancy", 0.0)
    exp_b = kpis_b.get("expectancy", 0.0)
    if not isinstance(exp_a, (int, float)) or not isinstance(exp_b, (int, float)):
        return "indéterminé"
    if exp_b > exp_a:
        return "B"
    if exp_a > exp_b:
        return "A"
    # tie-break: quality_score
    qs_a = kpis_a.get("trade_quality_score", 0.0)
    qs_b = kpis_b.get("trade_quality_score", 0.0)
    return "B" if qs_b >= qs_a else "A"


def list_comparison_candidates() -> list[str]:
    """Retourne les sessions disponibles pour comparaison."""
    from tracker_system.sessions.session_manager import list_sessions

    return list_sessions()
