from __future__ import annotations

from tracker_system.config.settings import (
    MIN_PROFIT_FACTOR,
    NO_TRADE_REGIMES,
    OPTIMIZER_FILE,
)
from tracker_system.storage.loader import load_json

# Régimes pour lesquels on réduit le sizing quand profit factor < seuil
_SOFT_REGIME_FACTOR: dict[str, float] = {
    "sideways": 0.3,
    "range": 0.3,
    "range_faible": 0.3,
}

EXIT_CONFIG = {
    "bull_trend": {
        "tp": 0.030,
        "sl": 0.015,
        "trailing": 0.007,
    },
    "bullish": {
        "tp": 0.030,
        "sl": 0.015,
        "trailing": 0.007,
    },
    "range": {
        "tp": 0.012,
        "sl": 0.008,
        "trailing": 0.004,
    },
    "bear_trend": {
        "tp": 0.020,
        "sl": 0.012,
        "trailing": 0.006,
    },
    "bearish": {
        "tp": 0.020,
        "sl": 0.012,
        "trailing": 0.006,
    },
    "default": {
        "tp": 0.015,
        "sl": 0.010,
        "trailing": 0.005,
    },
}

MIN_OPTIMIZER_SAMPLES = 20


def _optimizer_override(regime: str) -> dict[str, float]:
    optimizer = load_json(OPTIMIZER_FILE, {})
    payload = optimizer.get(regime, {}) if isinstance(optimizer, dict) else {}
    if not isinstance(payload, dict):
        return {}

    try:
        samples = int(payload.get("samples", 0))
    except (TypeError, ValueError):
        return {}

    if samples < MIN_OPTIMIZER_SAMPLES:
        return {}

    override: dict[str, float] = {}
    for key in ("tp", "sl", "trailing"):
        if key not in payload:
            continue
        try:
            override[key] = float(payload[key])
        except (TypeError, ValueError):
            continue
    return override


def get_size_factor(regime: str | None, profit_factor: float | None = None) -> float:
    """
    Retourne un multiplicateur de taille (0.0–1.0) selon le régime et le profit factor.

    Si le régime est dégradé (sideways/range) ET profit_factor < MIN_PROFIT_FACTOR,
    retourne 0.3 pour forcer une taille réduite.
    Dans tous les autres cas, retourne 1.0 (taille normale).
    """
    key = str(regime or "").strip().lower()
    factor = _SOFT_REGIME_FACTOR.get(key)
    if factor is None:
        return 1.0

    pf = float(profit_factor) if profit_factor is not None else 0.0
    if pf < MIN_PROFIT_FACTOR:
        return factor

    return 1.0


def is_regime_tradable(regime: str | None) -> tuple[bool, str]:
    """Retourne (tradable, raison). Bloque les régimes en no-trade gate."""
    key = str(regime or "").strip().lower()
    if key in NO_TRADE_REGIMES:
        return (
            False,
            f"Régime '{key}' bloqué par no-trade gate (profit factor historique insuffisant).",
        )
    return True, ""


def get_exit_config(
    regime: str | None, confidence: float | None = None
) -> dict[str, float]:
    key = str(regime or "default").strip().lower()
    config = dict(EXIT_CONFIG.get(key, EXIT_CONFIG["default"]))
    config.update(_optimizer_override(key))

    if confidence is None:
        return config

    try:
        scaled_confidence = max(0.0, min(float(confidence), 100.0))
    except (TypeError, ValueError):
        return config

    config["tp"] = round(config["tp"] * (1.0 + scaled_confidence / 100.0), 6)
    return config
