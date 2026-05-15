from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tracker_system.config.settings import TRADES_LOG_FILE
from tracker_system.storage.loader import load_jsonl


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def extract_scores(log_file: Path = TRADES_LOG_FILE) -> list[float]:
    """Extrait les scores des events entry (ou exit si présent)."""
    events = load_jsonl(log_file)
    scores: list[float] = []
    for event in events:
        raw = event.get("score")
        if raw is not None:
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                continue
    return scores


def compute_drift(
    scores: list[float],
    window: int = 10,
    z_threshold: float = 2.0,
) -> dict[str, Any]:
    """
    Compare la moyenne des `window` derniers scores vs baseline (tous sauf window).

    Returns:
        {
            "baseline_mean": float,
            "baseline_std": float,
            "recent_mean": float,
            "z_score": float,
            "drift_detected": bool,
            "direction": "degradation" | "improvement" | "stable",
            "alert": str | None,
            "n_baseline": int,
            "n_recent": int,
        }
    """
    if len(scores) < window + 2:
        return {
            "baseline_mean": 0.0,
            "baseline_std": 0.0,
            "recent_mean": 0.0,
            "z_score": 0.0,
            "drift_detected": False,
            "direction": "stable",
            "alert": None,
            "n_baseline": 0,
            "n_recent": len(scores),
        }

    baseline = scores[:-window]
    recent = scores[-window:]

    b_mean = _mean(baseline)
    b_std = _std(baseline)
    r_mean = _mean(recent)

    z_score = (r_mean - b_mean) / b_std if b_std > 1e-9 else 0.0

    drift_detected = abs(z_score) > z_threshold

    if not drift_detected:
        direction = "stable"
        alert = None
    elif z_score < 0:
        direction = "degradation"
        alert = (
            f"ALERTE drift score : z={z_score:.2f} — "
            f"score moyen récent ({r_mean:.4f}) a chuté de plus de {z_threshold}σ "
            f"vs baseline ({b_mean:.4f} ± {b_std:.4f}). "
            "Signal potentiellement dégradé."
        )
    else:
        direction = "improvement"
        alert = (
            f"INFO drift score : z={z_score:.2f} — "
            f"score moyen récent ({r_mean:.4f}) a augmenté de plus de {z_threshold}σ "
            f"vs baseline ({b_mean:.4f}). Vérifier overfitting."
        )

    return {
        "baseline_mean": round(b_mean, 6),
        "baseline_std": round(b_std, 6),
        "recent_mean": round(r_mean, 6),
        "z_score": round(z_score, 4),
        "drift_detected": drift_detected,
        "direction": direction,
        "alert": alert,
        "n_baseline": len(baseline),
        "n_recent": len(recent),
    }


def check_score_drift(
    log_file: Path = TRADES_LOG_FILE,
    window: int = 10,
    z_threshold: float = 2.0,
) -> dict[str, Any]:
    """Point d'entrée principal : charge les scores et calcule le drift."""
    scores = extract_scores(log_file)
    return compute_drift(scores, window=window, z_threshold=z_threshold)


def check_winrate_drift(
    log_file: Path = TRADES_LOG_FILE,
    window: int = 20,
    min_winrate: float = 0.40,
) -> dict[str, Any]:
    """
    Alerte si winrate rolling `window` passe sous `min_winrate`.
    Complémentaire au drift de score.
    """
    events = load_jsonl(log_file)
    exits = [e for e in events if e.get("type") == "exit"]

    if len(exits) < window:
        return {"alert": None, "winrate_rolling": None, "n": len(exits)}

    recent = exits[-window:]
    wins = sum(1 for t in recent if float(t.get("pnl_usd", 0.0)) > 0)
    winrate = wins / len(recent)

    alert = None
    if winrate < min_winrate:
        alert = (
            f"ALERTE winrate rolling {window} : {winrate:.1%} < seuil {min_winrate:.0%}. "
            "Performance récente dégradée — réduire exposition."
        )

    return {
        "alert": alert,
        "winrate_rolling": round(winrate, 4),
        "n": len(recent),
        "min_winrate": min_winrate,
    }
