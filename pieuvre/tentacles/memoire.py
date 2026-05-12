"""
Tentacule Mémoire — gardienne de la mémoire immunitaire de la Pieuvre.

Rôle:
  - Analyse les incidents passés pour extraire des patterns récurrents
  - Construit l'immunité active (règles que les autres tentacules ignorent)
  - Détecte si un incident actuel ressemble à un passé (déjà vu = plus rapide)
  - Rapporte la santé mémorielle: force accumulée, taux de récidive
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.incidents.store import IncidentStore
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)


class MemoireTentacle(BaseTentacle):
    """Surveillance de la mémoire immunitaire et des patterns récurrents."""

    name = "memoire"
    emoji = "🧠"

    def __init__(self, repo_path: Path, store: IncidentStore) -> None:
        super().__init__(repo_path)
        self._store = store

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        findings: list[Finding] = []

        all_incidents = self._store.all()
        if not all_incidents:
            return []

        findings.extend(self._check_recurring_patterns(all_incidents))
        findings.extend(self._check_unresolved_backlog(all_incidents))
        findings.extend(self._report_strength_milestone())

        self.last_findings = findings
        return findings

    # ── Analyses ──────────────────────────────────────────────────────────────

    def _check_recurring_patterns(self, incidents) -> list[Finding]:
        """Détecte les règles qui reviennent — cibles de nouveaux tentacules."""
        findings = []
        rule_counter: Counter = Counter()

        for inc in incidents:
            for pat in inc.immunity_patterns:
                rule_counter[pat] += 1

        for rule, count in rule_counter.most_common():
            if count >= 3 and not self.is_immune(f"recurrence_{rule}"):
                findings.append(
                    Finding(
                        file="memoire:patterns",
                        line=0,
                        rule=f"recurrence_{rule}",
                        message=(
                            f"Pattern '{rule}' récurrent ({count}x) — "
                            f"candidat pour nouveau tentacule spécialisé"
                        ),
                        severity=Severity.LOW,
                        snippet=f"occurrences={count}",
                        tentacle=self.name,
                    )
                )

        return findings

    def _check_unresolved_backlog(self, incidents) -> list[Finding]:
        """Incidents non résolus depuis trop longtemps."""
        from datetime import datetime

        findings = []
        now = datetime.now()
        unresolved = [i for i in incidents if i.resolved_at is None]

        for inc in unresolved:
            age = (now - inc.timestamp).total_seconds()
            if age > 3600:  # >1h non résolu
                findings.append(
                    Finding(
                        file=f"memoire:incident:{inc.id}",
                        line=0,
                        rule="stale_incident",
                        message=(
                            f"Incident {inc.id} non résolu depuis {age/3600:.1f}h "
                            f"({inc.severity.value}): {inc.message[:60]}"
                        ),
                        severity=Severity.MEDIUM if age > 7200 else Severity.LOW,
                        snippet=inc.message[:120],
                        tentacle=self.name,
                    )
                )

        return findings

    def _report_strength_milestone(self) -> list[Finding]:
        """Célèbre les jalons de force (informationnel, sévérité LOW)."""
        total_strength = self._store.total_strength_gained()
        milestones = [1.0, 2.0, 3.0, 5.0, 10.0]

        for milestone in milestones:
            rule = f"milestone_{int(milestone * 10)}"
            if total_strength >= milestone and not self.is_immune(rule):
                self.add_immunity(rule)  # ne rapporter qu'une fois
                return [
                    Finding(
                        file="memoire:force",
                        line=0,
                        rule=rule,
                        message=f"🐙 Force cumulée ≥ {milestone:.1f}x — nouvelle génération plus résistante",
                        severity=Severity.LOW,
                        snippet=f"force_totale={total_strength:.3f}",
                        tentacle=self.name,
                    )
                ]

        return []

    def extract_lessons(self, findings: list[Finding]) -> list[str]:
        """Méthode publique — appelée par le cerveau pour générer les leçons."""
        seen: set[str] = set()
        lessons: list[str] = []
        for f in findings:
            key = f"{f.rule}@{Path(f.file).name}"
            if key not in seen:
                seen.add(key)
                lessons.append(
                    f"Vulnérabilité '{f.rule}' dans {Path(f.file).name}:{f.line} — {f.message[:60]}"
                )
        return lessons[:15]

    def extract_immunity_patterns(self, findings: list[Finding]) -> list[str]:
        """Extrait les noms de règles uniques à injecter comme immunités."""
        return list({f.rule for f in findings})
