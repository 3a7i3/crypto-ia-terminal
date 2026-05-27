"""
forbidden_patterns_registry.py — Forbidden Patterns Registry (P8)

Mémoire collective inter-stratégies : enregistre les patterns dangereux
identifiés par n'importe quelle stratégie et les rend consultables par toutes.

Concepts :
  - Un "pattern" est une combinaison (pattern_id, regime) jugée dangereuse.
  - Chaque stratégie peut enregistrer un pattern avec un niveau de confiance.
  - Les autres stratégies consultent le registre avant de prendre un trade.
  - Les patterns anciens (> max_age_cycles) sont purgés automatiquement.

Usage :
    reg = ForbiddenPatternsRegistry()
    reg.register_pattern(
        pattern_id="LIQUIDITY_SWEEP_AFTER_LARGE_CANDLE",
        regime="HIGH_VOL",
        strategies_affected=["grid", "scalp"],
        confidence=0.85,
        registered_by="grid",
        cycle=1423,
    )
    if reg.is_forbidden("LIQUIDITY_SWEEP_AFTER_LARGE_CANDLE", "HIGH_VOL", "scalp"):
        skip_trade()

Env vars :
  P8_PATTERN_MAX_AGE  : cycles avant purge automatique (défaut 500)
  FORBIDDEN_PATTERNS_DB : chemin JSON de persistence

"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.forbidden_patterns_registry")

_MAX_AGE_CYCLES = int(os.getenv("P8_PATTERN_MAX_AGE", "500"))
_DB_PATH = Path(os.getenv("FORBIDDEN_PATTERNS_DB", "databases/forbidden_patterns.json"))
_MIN_CONFIDENCE = 0.50  # confiance minimale pour bloquer un trade


@dataclass
class ForbiddenPattern:
    pattern_id: str
    regime: str
    strategies_affected: list[str]
    confidence: float
    registered_by: str
    cycle: int
    description: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "regime": self.regime,
            "strategies_affected": self.strategies_affected,
            "confidence": round(self.confidence, 3),
            "registered_by": self.registered_by,
            "cycle": self.cycle,
            "description": self.description,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ForbiddenPattern":
        return cls(
            pattern_id=d["pattern_id"],
            regime=d["regime"],
            strategies_affected=d.get("strategies_affected", []),
            confidence=float(d.get("confidence", 0.5)),
            registered_by=d.get("registered_by", ""),
            cycle=int(d.get("cycle", 0)),
            description=d.get("description", ""),
            ts=float(d.get("ts", time.time())),
        )


class ForbiddenPatternsRegistry:
    """
    Registre partagé de patterns dangereux entre stratégies.

    Clé de dédup : (pattern_id, regime). Si un pattern existant est soumis
    à nouveau avec une confiance plus haute, il est mis à jour.
    """

    def __init__(self) -> None:
        self._db_path = Path(
            os.getenv("FORBIDDEN_PATTERNS_DB", "databases/forbidden_patterns.json")
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Clé : (pattern_id, regime) → ForbiddenPattern
        self._patterns: dict[tuple[str, str], ForbiddenPattern] = {}
        self._load()

    # ── Enregistrement ────────────────────────────────────────────────────────

    def register_pattern(
        self,
        pattern_id: str,
        regime: str,
        strategies_affected: list[str],
        confidence: float,
        registered_by: str = "",
        cycle: int = 0,
        description: str = "",
    ) -> ForbiddenPattern:
        """
        Enregistre ou met à jour un pattern dangereux.
        Si le pattern existe déjà : met à jour si la confiance est plus haute,
        ou ajoute les stratégies affectées si la confiance est identique.
        """
        key = (pattern_id, regime)
        existing = self._patterns.get(key)

        if existing is not None:
            if confidence > existing.confidence:
                existing.confidence = round(confidence, 3)
                existing.registered_by = registered_by
                existing.cycle = cycle
                existing.description = description or existing.description
                existing.ts = time.time()
            # Fusionner les stratégies affectées
            combined = list(set(existing.strategies_affected + strategies_affected))
            existing.strategies_affected = combined
            pattern = existing
        else:
            pattern = ForbiddenPattern(
                pattern_id=pattern_id,
                regime=regime,
                strategies_affected=list(strategies_affected),
                confidence=round(confidence, 3),
                registered_by=registered_by,
                cycle=cycle,
                description=description,
            )
            self._patterns[key] = pattern

        _log.info(
            "[ForbiddenPatterns] %s/%s conf=%.0f%% affecte=%s",
            pattern_id,
            regime,
            confidence * 100,
            strategies_affected,
        )
        self._save()
        return pattern

    # ── Consultation ─────────────────────────────────────────────────────────

    def is_forbidden(
        self,
        pattern_id: str,
        regime: str,
        strategy_id: str,
        min_confidence: float = _MIN_CONFIDENCE,
    ) -> bool:
        """
        True si le pattern est interdit pour cette stratégie dans ce régime,
        avec une confiance >= min_confidence.
        Aussi True si le pattern est enregistré pour ALL ("*").
        """
        for key_regime in (regime, "*"):
            pattern = self._patterns.get((pattern_id, key_regime))
            if pattern is None:
                continue
            if pattern.confidence < min_confidence:
                continue
            if (
                strategy_id in pattern.strategies_affected
                or "*" in pattern.strategies_affected
            ):
                return True
        return False

    def get_active_patterns(
        self, regime: Optional[str] = None, cycle: int = 0
    ) -> list[ForbiddenPattern]:
        """
        Retourne les patterns actifs (non expirés).
        Si regime est fourni, filtre sur ce régime (+ wildcards "*").
        """
        result = []
        for pattern in self._patterns.values():
            if cycle > 0 and (cycle - pattern.cycle) > _MAX_AGE_CYCLES:
                continue
            if regime is not None and pattern.regime not in (regime, "*"):
                continue
            result.append(pattern)
        return sorted(result, key=lambda p: -p.confidence)

    def forbidden_for_strategy(
        self,
        strategy_id: str,
        regime: str,
        cycle: int = 0,
    ) -> list[ForbiddenPattern]:
        """Retourne tous les patterns interdits pour une stratégie dans un régime."""
        return [
            p
            for p in self.get_active_patterns(cycle=cycle)
            if (p.regime in (regime, "*"))
            and (strategy_id in p.strategies_affected or "*" in p.strategies_affected)
            and p.confidence >= _MIN_CONFIDENCE
        ]

    # ── Maintenance ──────────────────────────────────────────────────────────

    def clear_old_patterns(self, current_cycle: int) -> int:
        """Purge les patterns anciens (> max_age_cycles). Retourne le nombre purgés."""
        before = len(self._patterns)
        self._patterns = {
            k: v
            for k, v in self._patterns.items()
            if (current_cycle - v.cycle) <= _MAX_AGE_CYCLES
        }
        purged = before - len(self._patterns)
        if purged > 0:
            _log.info("[ForbiddenPatterns] Purgé %d patterns anciens", purged)
            self._save()
        return purged

    def clear_pattern(self, pattern_id: str, regime: str) -> bool:
        """Supprime manuellement un pattern. Retourne True si existait."""
        key = (pattern_id, regime)
        if key in self._patterns:
            del self._patterns[key]
            self._save()
            return True
        return False

    def summary(self) -> dict:
        return {
            "total_patterns": len(self._patterns),
            "by_regime": {
                regime: sum(1 for p in self._patterns.values() if p.regime == regime)
                for regime in {p.regime for p in self._patterns.values()}
            },
            "high_confidence": sum(
                1 for p in self._patterns.values() if p.confidence >= 0.80
            ),
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for d in data.get("patterns", []):
                p = ForbiddenPattern.from_dict(d)
                self._patterns[(p.pattern_id, p.regime)] = p
            _log.info("[ForbiddenPatterns] Chargé: %d patterns", len(self._patterns))
        except Exception as exc:
            _log.warning("[ForbiddenPatterns] Erreur chargement: %s", exc)

    def _save(self) -> None:
        try:
            data = {"patterns": [p.to_dict() for p in self._patterns.values()]}
            self._db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("[ForbiddenPatterns] Erreur sauvegarde: %s", exc)
