"""
Tentacule Guérison — gestionnaire de la récupération post-attaque.

La Pieuvre, comme toute créature vivante, doit se reposer après un choc sévère.
Ce tentacule:
  - Surveille le compte à rebours de récupération
  - Calcule le temps réduit grâce à l'expérience accumulée
  - Génère les leçons post-incident
  - Signe la fin de la guérison pour déclencher le REGROWTH
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from pieuvre.incidents.models import (
    Finding,
    Incident,
    Severity,
)
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)

# Réduction du temps de récupération par point de force au-delà de 1.0
_EXPERIENCE_REDUCTION = 0.08  # 8% par point de force
_MAX_REDUCTION = 0.60  # jamais en dessous de 40% du temps original


@dataclass
class RecoveryState:
    active: bool = False
    incident_id: str = ""
    end_time: float = 0.0
    original_seconds: float = 0.0
    actual_seconds: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.end_time - time.time())

    @property
    def is_done(self) -> bool:
        return self.active and time.time() >= self.end_time

    @property
    def progress(self) -> float:
        elapsed = self.actual_seconds - self.remaining
        return min(1.0, elapsed / max(1.0, self.actual_seconds))


class GuerisonTentacle(BaseTentacle):
    """Gestionnaire de la guérison — surveille et signale la fin de récupération."""

    name = "guerison"
    emoji = "💊"

    def __init__(self, repo_path: Path) -> None:
        super().__init__(repo_path)
        self.recovery = RecoveryState()
        self._healed_count: int = 0

    # ── API publique (appelée par le cerveau) ──────────────────────────────────

    def start_recovery(self, incident: Incident, current_force: float) -> float:
        """Démarre la phase de guérison. Retourne le temps de récupération en secondes."""
        original = incident.required_recovery()
        reduction = min(_MAX_REDUCTION, (current_force - 1.0) * _EXPERIENCE_REDUCTION)
        actual = original * (1.0 - reduction)

        self.recovery = RecoveryState(
            active=True,
            incident_id=incident.id,
            end_time=time.time() + actual,
            original_seconds=original,
            actual_seconds=actual,
        )

        logger.warning(
            "[GUERISON] Récupération démarrée: %.0fs (base %.0fs, -%.0f%% expérience)",
            actual,
            original,
            reduction * 100,
        )
        return actual

    def is_healed(self) -> bool:
        """Le cerveau appelle cette méthode pour savoir si la guérison est terminée."""
        return self.recovery.is_done

    def complete_recovery(self) -> None:
        self._healed_count += 1
        self.recovery = RecoveryState()
        logger.info(
            "[GUERISON] Guérison terminée. Total guérisons: %d", self._healed_count
        )

    # ── Scan passif (monitoring) ───────────────────────────────────────────────

    def scan(self) -> list[Finding]:
        """Rapporte l'état de guérison si actif."""
        self._scan_count += 1
        findings: list[Finding] = []

        if self.recovery.active and not self.recovery.is_done:
            remaining = self.recovery.remaining
            mins = int(remaining) // 60
            secs = int(remaining) % 60
            progress_pct = self.recovery.progress * 100

            findings.append(
                Finding(
                    file="guerison:recovery",
                    line=0,
                    rule="recovery_in_progress",
                    message=(
                        f"Guérison en cours — {mins:02d}:{secs:02d} restant "
                        f"({progress_pct:.0f}% completé)"
                    ),
                    severity=Severity.LOW,
                    snippet=f"incident={self.recovery.incident_id}",
                    tentacle=self.name,
                )
            )

        self.last_findings = findings
        return findings

    def render_recovery_bar(self, width: int = 30) -> str:
        """Barre de progression ASCII pour le dashboard."""
        if not self.recovery.active:
            return "✅ Pieuvre en pleine santé"

        pct = self.recovery.progress
        filled = int(pct * width)
        bar = "█" * filled + "░" * (width - filled)
        remaining = self.recovery.remaining
        mins, secs = divmod(int(remaining), 60)
        return f"💊 [{bar}] {pct*100:.0f}% — {mins:02d}:{secs:02d} restant"

    @property
    def healed_count(self) -> int:
        return self._healed_count
