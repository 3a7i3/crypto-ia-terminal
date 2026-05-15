from __future__ import annotations

# Expectancy interpretation thresholds
EXPECTANCY_LABELS = [
    (float("inf"), 1.0, "exceptionnel"),
    (1.0, 0.5, "très solide"),
    (0.5, 0.2, "correct"),
    (0.2, 0.0, "fragile"),
    (0.0, float("-inf"), "système perdant"),
]

# Signal stability thresholds
STABILITY_THRESHOLDS = {
    "stable": 0.8,
    "acceptable": 0.5,
}

# Drift detection thresholds
DRIFT_Z_SCORE_THRESHOLD = 2.0
DRIFT_PF_DROP_RATIO = 0.7  # rolling PF < baseline * 0.7 → drift
DRIFT_VOLATILITY_RATIO = 2.0  # market vol > baseline * 2 → drift

PAYOFF_RATIO_TARGET = 1.5


def label_expectancy(value: float) -> str:
    for upper, lower, label in EXPECTANCY_LABELS:
        if lower <= value < upper:
            return label
    return "inconnu"


def label_stability(value: float) -> str:
    if value >= STABILITY_THRESHOLDS["stable"]:
        return "très stable"
    if value >= STABILITY_THRESHOLDS["acceptable"]:
        return "acceptable"
    return "drift probable"
