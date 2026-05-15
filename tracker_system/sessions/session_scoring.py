from __future__ import annotations

from typing import Any

from tracker_system.sessions.session_labels import (
    DRIFT_THRESHOLD,
    KNOWN_REGIMES,
    SIDEWAYS_OVEREXPOSURE_THRESHOLD,
    analyze_failures,
    build_session_dna,
    label_confidence,
    label_regime_coverage,
    label_session,
)

# Poids du score composite
_WEIGHTS = {
    "expectancy": 0.25,
    "profit_factor": 0.25,
    "stability_index": 0.20,
    "recovery_factor": 0.15,
    "winrate": 0.10,
    "drawdown_penalty": 0.25,  # soustrait
}

# Nombre de trades pour confidence = 1.0
CONFIDENCE_TRADES_TARGET = 100
# Nombre minimum de régimes distincts pour coverage = 1.0
TOTAL_REGIMES_POSSIBLE = len(KNOWN_REGIMES)


class SessionScoring:
    """Calcule le score global de qualité d'une session."""

    def score(self, analysis: dict, trades: list[dict] | None = None) -> dict[str, Any]:
        summary = analysis.get("summary", {})
        n_trades = summary.get("trades", 0)
        winrate = summary.get("winrate", 0.0)

        exp_val = analysis.get("expectancy", {}).get("value", 0.0)
        pf = analysis.get("profit_factor", 0.0)
        pf_val = min(float(pf) if isinstance(pf, (int, float)) else 0.0, 5.0)
        stab = analysis.get("signal_stability", {}).get("index", 0.0)
        rec = analysis.get("recovery_factor", 0.0)
        rec_val = min(float(rec) if isinstance(rec, (int, float)) else 0.0, 5.0)
        drift_events = analysis.get("drift_events", [])
        regime_matrix = analysis.get("regime_matrix", {})

        # Drawdown proxy (inverted recovery)
        dd_proxy = 1.0 / (rec_val + 1.0)

        raw = (
            exp_val * _WEIGHTS["expectancy"]
            + pf_val * _WEIGHTS["profit_factor"]
            + stab * _WEIGHTS["stability_index"]
            + rec_val * _WEIGHTS["recovery_factor"]
            + winrate * _WEIGHTS["winrate"]
            - dd_proxy * _WEIGHTS["drawdown_penalty"]
        )
        quality_score = max(0.0, min(100.0, raw * 20.0))

        confidence = self._confidence(n_trades, drift_events, regime_matrix)
        regime_coverage = self._regime_coverage(regime_matrix)
        market_fingerprint = self._market_fingerprint(analysis, trades or [])
        failure_causes = analyze_failures(analysis)
        dna = build_session_dna(analysis)

        return {
            "quality_score": round(quality_score, 2),
            "label": label_session(quality_score),
            "confidence": {
                "value": round(confidence, 4),
                "label": label_confidence(confidence),
            },
            "regime_coverage": {
                "value": round(regime_coverage, 4),
                "label": label_regime_coverage(regime_coverage),
                "unique_regimes": len(regime_matrix),
                "total_possible": TOTAL_REGIMES_POSSIBLE,
            },
            "market_fingerprint": market_fingerprint,
            "failure_analysis": {
                "has_failures": len(failure_causes) > 0,
                "root_causes": failure_causes,
            },
            "session_dna": dna,
        }

    def _confidence(
        self, n_trades: int, drift_events: list[dict], regime_matrix: dict
    ) -> float:
        base = min(1.0, n_trades / CONFIDENCE_TRADES_TARGET)

        if len(drift_events) >= DRIFT_THRESHOLD:
            base *= 0.7

        unique_regimes = len(regime_matrix)
        if unique_regimes < 2:
            base *= 0.8

        return base

    def _regime_coverage(self, regime_matrix: dict) -> float:
        return len(regime_matrix) / TOTAL_REGIMES_POSSIBLE

    def _market_fingerprint(
        self, analysis: dict, trades: list[dict]
    ) -> dict[str, float]:
        regime_matrix = analysis.get("regime_matrix", {})
        total = analysis.get("summary", {}).get("trades", 1) or 1

        trend_trades = regime_matrix.get("trend", {}).get("trades", 0)
        momentum_trades = regime_matrix.get("momentum", {}).get("trades", 0)
        sideways_trades = (
            regime_matrix.get("sideways", {}).get("trades", 0)
            + regime_matrix.get("range", {}).get("trades", 0)
            + regime_matrix.get("range_faible", {}).get("trades", 0)
        )
        volatile_trades = regime_matrix.get("volatile", {}).get("trades", 0)

        trend_strength = (trend_trades + momentum_trades) / total
        sideways_ratio = sideways_trades / total
        anomaly_ratio = volatile_trades / total

        # Volatility proxy: std of pnl_pct
        if trades:
            pnl_pcts = [float(t.get("pnl_pct", 0.0)) for t in trades]
            try:
                import statistics

                vol_mean = statistics.stdev(pnl_pcts) if len(pnl_pcts) > 1 else 0.0
            except Exception:
                vol_mean = 0.0
        else:
            vol_mean = 0.0

        return {
            "volatility_mean": round(vol_mean, 4),
            "trend_strength": round(trend_strength, 4),
            "sideways_ratio": round(sideways_ratio, 4),
            "anomaly_ratio": round(anomaly_ratio, 4),
        }


def score_session(analysis: dict, trades: list[dict] | None = None) -> dict[str, Any]:
    """Raccourci : score une analyse déjà calculée."""
    return SessionScoring().score(analysis, trades)
