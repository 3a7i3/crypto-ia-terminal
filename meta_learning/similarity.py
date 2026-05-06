"""
Similarity Calculation — Trouve context similaires
Match: regime + volatility + trend
"""

from typing import Any


class SimilarityEngine:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "regime": 1.0,
            "volatility": 0.5,
            "momentum": 0.3,
        }

    def regime_match(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        if a.get("regime") == b.get("regime"):
            return self.weights.get("regime", 1.0)
        return 0.0

    def volatility_match(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        vol_a = float(a.get("volatility", 0.0))
        vol_b = float(b.get("volatility", 0.0))
        diff = abs(vol_a - vol_b)
        if diff < 0.01:
            return self.weights.get("volatility", 0.5)
        if diff < 0.02:
            return self.weights.get("volatility", 0.5) * 0.5
        return 0.0

    def momentum_match(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        mom_a = float(a.get("momentum", 0.0))
        mom_b = float(b.get("momentum", 0.0))
        if abs(mom_a - mom_b) < 0.05:
            return self.weights.get("momentum", 0.3)
        return 0.0

    def compute(self, context_a: dict[str, Any], context_b: dict[str, Any]) -> float:
        score = 0.0
        score += self.regime_match(context_a, context_b)
        score += self.volatility_match(context_a, context_b)
        score += self.momentum_match(context_a, context_b)
        return score

    def find_best_match(self, context: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
        best = None
        best_score = -1.0
        for candidate in candidates:
            score = self.compute(context, candidate)
            if score > best_score:
                best_score = score
                best = candidate
        return best, best_score
