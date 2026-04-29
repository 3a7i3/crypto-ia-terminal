"""Persistance JSON des incidents de la Pieuvre."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pieuvre.incidents.models import Incident

logger = logging.getLogger(__name__)


class IncidentStore:
    """Stockage JSON des incidents — mémoire à long terme de la Pieuvre."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: list[Incident] = []
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def save(self, incident: Incident) -> None:
        """Sauvegarde ou met à jour un incident."""
        for i, inc in enumerate(self._cache):
            if inc.id == incident.id:
                self._cache[i] = incident
                self._flush()
                return
        self._cache.append(incident)
        self._flush()
        logger.debug(
            "Incident %s enregistré (sévérité=%s)", incident.id, incident.severity.value
        )

    def all(self) -> list[Incident]:
        return list(self._cache)

    def resolved(self) -> list[Incident]:
        return [i for i in self._cache if i.resolved_at is not None]

    def pending(self) -> list[Incident]:
        return [i for i in self._cache if i.resolved_at is None]

    def total_strength_gained(self) -> float:
        return sum(i.strength_gained for i in self._cache if i.resolved_at)

    def all_immunity_patterns(self) -> set[str]:
        patterns: set[str] = set()
        for inc in self._cache:
            patterns.update(inc.immunity_patterns)
        return patterns

    def recurring_rules(self, min_count: int = 2) -> dict[str, int]:
        """Retourne les règles qui se répètent — cibles de nouvelles immunités."""
        counts: dict[str, int] = {}
        for inc in self._cache:
            for pat in inc.immunity_patterns:
                counts[pat] = counts.get(pat, 0) + 1
        return {r: c for r, c in counts.items() if c >= min_count}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            self._cache = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = [Incident.from_dict(d) for d in data]
            logger.debug("IncidentStore: %d incidents chargés", len(self._cache))
        except Exception as exc:
            logger.warning(
                "IncidentStore: erreur de lecture (%s) — démarrage vide", exc
            )
            self._cache = []

    def _flush(self) -> None:
        try:
            self._path.write_text(
                json.dumps(
                    [i.to_dict() for i in self._cache],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("IncidentStore: impossible d'écrire (%s)", exc)
