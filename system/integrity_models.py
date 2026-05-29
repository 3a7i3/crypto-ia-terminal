"""
system/integrity_models.py — Data models for State Integrity Audit.

IntegritySeverity : OK < WARNING < DEGRADED < UNSAFE
IntegrityDomain   : signal | position | capital | temporal | order
IntegrityLevel    : NORMAL > DEGRADED > RESTRICTED > UNSAFE > HALTED
IntegrityIssue    : une règle violée, immutable
                    (enrichie avec trace_id/cycle_id/snapshot_hash)
IntegrityReport   : résultat d'un audit complet, avec score 0-100, level, domain_health
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class IntegritySeverity(Enum):
    OK = 0
    WARNING = 1
    DEGRADED = 2
    UNSAFE = 3

    @staticmethod
    def aggregate(issues: list[IntegrityIssue]) -> IntegritySeverity:
        if not issues:
            return IntegritySeverity.OK
        return max((i.severity for i in issues), key=lambda s: s.value)

    @property
    def label(self) -> str:
        return self.name


class IntegrityDomain(str, Enum):
    """Domaine fonctionnel d'une règle d'intégrité."""

    SIGNAL = "signal"
    POSITION = "position"
    CAPITAL = "capital"
    TEMPORAL = "temporal"
    ORDER = "order"


class IntegrityLevel(str, Enum):
    """
    Échelle de dégradation 5 états.

    Remplace le binaire is_safe — permet une dégradation progressive :
      NORMAL     → score >= 80  : état sain, trading normal
      DEGRADED   → score >= 65  : anomalies mineures, trading prudent
      RESTRICTED → score >= 50  : anomalies significatives, taille réduite
      UNSAFE     → score >= 25  : corruption détectée, bloquer nouveaux ordres
      HALTED     → score <  25  : dégradation critique, arrêt complet
    """

    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    RESTRICTED = "RESTRICTED"
    UNSAFE = "UNSAFE"
    HALTED = "HALTED"

    @staticmethod
    def from_score(score: int) -> IntegrityLevel:
        if score >= 80:
            return IntegrityLevel.NORMAL
        if score >= 65:
            return IntegrityLevel.DEGRADED
        if score >= 50:
            return IntegrityLevel.RESTRICTED
        if score >= 25:
            return IntegrityLevel.UNSAFE
        return IntegrityLevel.HALTED


@dataclass(frozen=True)
class IntegrityIssue:
    """Une violation d'invariant — immutable, comparable."""

    rule: str  # "signal.stale_lock", "capital.ghost_exposure", ...
    severity: IntegritySeverity
    description: str
    invariant: str  # ce qui devrait être vrai
    observed: str  # ce qui est réellement observé
    category: str  # signal | position | capital | temporal | order

    # Enrichi par StateIntegrityAudit.run() après calcul du snapshot hash
    trace_id: str = ""  # trace_id global du cycle (Task 3 correlation)
    cycle_id: int = 0  # cycle courant
    snapshot_hash: str = ""  # hash de l'état au moment de la détection

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.name,
            "description": self.description,
            "invariant": self.invariant,
            "observed": self.observed,
            "category": self.category,
            "trace_id": self.trace_id,
            "cycle_id": self.cycle_id,
            "snapshot_hash": self.snapshot_hash,
        }


# Pénalités de score par sévérité (cumulatives)
_SCORE_PENALTIES: dict[IntegritySeverity, int] = {
    IntegritySeverity.WARNING: 5,
    IntegritySeverity.DEGRADED: 15,
    IntegritySeverity.UNSAFE: 30,
}


@dataclass
class IntegrityReport:
    """Résultat d'un audit complet. Produit un score 0-100 et un level 5 états."""

    timestamp: float = field(default_factory=time.time)
    cycle: int = 0
    issues: list[IntegrityIssue] = field(default_factory=list)
    state_hash: str = ""
    trace_id: str = ""  # propagé depuis le cycle courant

    @property
    def severity(self) -> IntegritySeverity:
        return IntegritySeverity.aggregate(self.issues)

    @property
    def score(self) -> int:
        """0-100. 100 = entièrement cohérent. Pénalités cumulatives par issue."""
        penalty = sum(_SCORE_PENALTIES.get(i.severity, 0) for i in self.issues)
        return max(0, 100 - penalty)

    @property
    def level(self) -> IntegrityLevel:
        """Niveau de dégradation 5 états dérivé du score."""
        return IntegrityLevel.from_score(self.score)

    @property
    def primary_failure(self) -> Optional[IntegrityIssue]:
        """Issue la plus sévère — raison principale quand le système est unsafe."""
        if not self.issues:
            return None
        return max(self.issues, key=lambda i: i.severity.value)

    @property
    def domain_health(self) -> dict[str, int]:
        """Score 0-100 par domaine fonctionnel. Permet dégradation partielle."""
        domains = {d.value: 100 for d in IntegrityDomain}
        for issue in self.issues:
            penalty = _SCORE_PENALTIES.get(issue.severity, 0)
            if issue.category in domains:
                domains[issue.category] = max(0, domains[issue.category] - penalty)
        return domains

    @property
    def is_safe(self) -> bool:
        """Compat v1.0 — False seulement si niveau UNSAFE ou HALTED."""
        return self.level not in (IntegrityLevel.UNSAFE, IntegrityLevel.HALTED)

    @property
    def is_clean(self) -> bool:
        return not self.issues

    @property
    def by_category(self) -> dict[str, list[IntegrityIssue]]:
        result: dict[str, list[IntegrityIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.category, []).append(issue)
        return result

    def summary_line(self) -> str:
        if not self.issues:
            return (
                f"[INTEGRITY] CLEAN score=100 level=NORMAL hash={self.state_hash[:8]}"
            )
        cats = ", ".join(f"{cat}({len(iss)})" for cat, iss in self.by_category.items())
        return (
            f"[INTEGRITY] score={self.score} level={self.level.value} "
            f"severity={self.severity.name} issues={len(self.issues)} "
            f"[{cats}] hash={self.state_hash[:8]}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cycle": self.cycle,
            "score": self.score,
            "severity": self.severity.name,
            "level": self.level.value,
            "state_hash": self.state_hash,
            "trace_id": self.trace_id,
            "primary_failure": (
                self.primary_failure.rule if self.primary_failure else None
            ),
            "domain_health": self.domain_health,
            "issues": [i.as_dict() for i in self.issues],
        }
