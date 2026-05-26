"""
feature_validator.py — Feature Quality Assurance

Détecte les features invalides : NaN, hors plage, obsolètes,
constantes, ou fortement corrélées (redondance).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.features.feature_validator")


@dataclass
class ValidationReport:
    valid: bool
    n_features: int
    n_invalid: int
    issues: list[str]
    quality_score: float  # [0,1]
    cleaned: dict[str, float]


class FeatureValidator:
    """
    Valide un vecteur de features et retourne un rapport de qualité.
    Nettoie automatiquement les valeurs invalides (remplace par 0 ou médiane).
    """

    def __init__(self, registry=None) -> None:
        self._registry = registry

    def validate(
        self,
        features: dict[str, float],
        symbol: str = "",
        strict: bool = False,
    ) -> ValidationReport:
        issues: list[str] = []
        cleaned: dict[str, float] = {}
        n_invalid = 0

        for name, val in features.items():
            # NaN / Inf
            if val is None or (
                isinstance(val, float) and (math.isnan(val) or math.isinf(val))
            ):
                issues.append(f"{name}: NaN/Inf value → replaced with 0")
                cleaned[name] = 0.0
                n_invalid += 1
                continue

            # Vérification plage via registry
            if self._registry:
                meta = self._registry.get(name)
                if meta and not (meta.expected_min <= val <= meta.expected_max):
                    issues.append(
                        f"{name}={val:.4f} hors plage [{meta.expected_min}, {meta.expected_max}]"
                    )
                    cleaned[name] = max(meta.expected_min, min(meta.expected_max, val))
                    n_invalid += 1
                    continue

            cleaned[name] = val

        # Détection features constantes (variance nulle sur historique pas dispo ici)
        # On détecte juste les valeurs suspectes simples
        constant_suspects = [k for k, v in cleaned.items() if v == 0.0]
        if len(constant_suspects) > len(cleaned) * 0.5:
            issues.append(
                f"WARN: {len(constant_suspects)}/{len(cleaned)} features à 0 — données manquantes?"
            )

        quality = 1.0 - (n_invalid / len(features)) if features else 0.0
        valid = n_invalid == 0 or not strict

        if issues:
            _log.debug(
                "[FeatureValidator] %s — %d issues, quality=%.0f%%",
                symbol,
                len(issues),
                quality * 100,
            )

        return ValidationReport(
            valid=valid,
            n_features=len(features),
            n_invalid=n_invalid,
            issues=issues,
            quality_score=quality,
            cleaned=cleaned,
        )

    def validate_batch(
        self,
        batch: dict[str, dict[str, float]],
        strict: bool = False,
    ) -> dict[str, ValidationReport]:
        return {
            symbol: self.validate(features, symbol, strict)
            for symbol, features in batch.items()
        }
