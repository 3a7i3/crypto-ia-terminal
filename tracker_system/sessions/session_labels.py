from __future__ import annotations

from typing import Any

# ── Labels ────────────────────────────────────────────────────────────────


def label_session(score: float) -> str:
    if score >= 85:
        return "institutional_grade"
    if score >= 70:
        return "stable_profitable"
    if score >= 50:
        return "experimental"
    return "unstable"


def label_regime_coverage(coverage: float) -> str:
    if coverage >= 0.75:
        return "diversifié"
    if coverage >= 0.40:
        return "partiel"
    return "non représentatif"


def label_confidence(confidence: float) -> str:
    if confidence >= 0.80:
        return "haute"
    if confidence >= 0.50:
        return "modérée"
    return "faible"


# ── Failure Analysis ─────────────────────────────────────────────────────

FAILURE_RULES: list[tuple[str, Any, str]] = [
    # (kpi_path_dot, threshold, message)
    ("expectancy.value", 0.0, "expectancy négative — edge inexistant"),
    ("profit_factor", 1.0, "profit factor < 1.0 — système perdant sur la période"),
    ("signal_stability.index", 0.5, "instabilité signal élevée — scores IA divergents"),
    ("recovery_factor", 1.0, "recovery factor faible — drawdown mal récupéré"),
]

SIDEWAYS_OVEREXPOSURE_THRESHOLD = 0.40  # >40% des trades en sideways → alerte
DRIFT_THRESHOLD = 1  # >= 1 drift event → pénalité confiance


def analyze_failures(analysis: dict) -> list[str]:
    """Retourne les causes racines d'une session sous-performante."""
    causes: list[str] = []

    exp = analysis.get("expectancy", {}).get("value", 0.0)
    if exp < 0:
        causes.append("expectancy négative — edge inexistant")

    pf = analysis.get("profit_factor", 0.0)
    if isinstance(pf, (int, float)) and pf < 1.0:
        causes.append("profit factor < 1.0 — système perdant sur la période")

    stab = analysis.get("signal_stability", {}).get("index", 1.0)
    if stab < 0.5:
        causes.append("instabilité signal élevée — scores IA divergents")

    drift_events = analysis.get("drift_events", [])
    if drift_events:
        types = {e.get("type", "inconnu") for e in drift_events}
        causes.append(f"dérive détectée : {', '.join(types)}")

    regime_matrix = analysis.get("regime_matrix", {})
    total_trades = analysis.get("summary", {}).get("trades", 0)
    if total_trades > 0 and regime_matrix:
        sideways_trades = regime_matrix.get("sideways", {}).get("trades", 0)
        range_trades = regime_matrix.get("range", {}).get("trades", 0)
        rf_trades = regime_matrix.get("range_faible", {}).get("trades", 0)
        blocked_ratio = (sideways_trades + range_trades + rf_trades) / total_trades
        if blocked_ratio > SIDEWAYS_OVEREXPOSURE_THRESHOLD:
            causes.append(
                f"sur-exposition aux régimes bloqués ({blocked_ratio:.0%} des trades)"
            )

    rec = analysis.get("recovery_factor", 0.0)
    if isinstance(rec, (int, float)) and rec < 1.0:
        causes.append(
            "recovery factor < 1.0 — le système ne récupère pas les drawdowns"
        )

    return causes


# ── Session DNA Vector ────────────────────────────────────────────────────

KNOWN_REGIMES = [
    "trend",
    "momentum",
    "sideways",
    "range",
    "range_faible",
    "volatile",
    "unknown",
]


def build_session_dna(analysis: dict) -> dict[str, Any]:
    """Vecteur numérique d'une session — base pour clustering et meta-learning."""
    summary = analysis.get("summary", {})
    total = summary.get("trades", 1) or 1
    regime_matrix = analysis.get("regime_matrix", {})

    regime_ratios = {
        r: regime_matrix.get(r, {}).get("trades", 0) / total for r in KNOWN_REGIMES
    }

    exp_val = analysis.get("expectancy", {}).get("value", 0.0)
    pf = analysis.get("profit_factor", 0.0)
    pf_capped = min(float(pf) if isinstance(pf, (int, float)) else 0.0, 10.0)
    stab = analysis.get("signal_stability", {}).get("index", 0.0)
    rec = analysis.get("recovery_factor", 0.0)
    rec_capped = min(float(rec) if isinstance(rec, (int, float)) else 0.0, 10.0)
    drift_count = len(analysis.get("drift_events", []))

    vector = {
        "expectancy": round(exp_val, 4),
        "profit_factor": round(pf_capped, 4),
        "stability": round(stab, 4),
        "recovery_factor": round(rec_capped, 4),
        "drift_score": round(1.0 / (1.0 + drift_count), 4),
        "winrate": round(summary.get("winrate", 0.0), 4),
        **{f"regime_{r}": round(ratio, 4) for r, ratio in regime_ratios.items()},
    }
    return vector
