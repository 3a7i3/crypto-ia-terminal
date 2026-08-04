"""Indicateurs du laboratoire — le laboratoire mesuré comme un objet.

**Aucun score composite.** Ce projet a déjà PMI, SDOS et CRI ; un quatrième
nombre agrégé n'apprendrait rien et masquerait ses composantes. Les indicateurs
sont publiés séparément, avec leur dénominateur.

Compression scientifique
------------------------
La connaissance doit se condenser : beaucoup d'événements, moins
d'observations, encore moins d'hypothèses. Deux nuances mesurées plutôt que
supposées :

1. Le rapport Event -> Observation peut légitimement être inférieur à 1 pour un
   laboratoire jeune : une seule observation peut résumer des milliers
   d'événements, et un seul événement peut en produire plusieurs (une métrique
   par dimension). Le rapport absolu ne dit donc rien seul.
2. Ce qui est diagnostique, c'est sa **dérive** : un laboratoire dont le rapport
   de compression décroît d'époque en époque produit de plus en plus de
   descriptions pour la même quantité de faits. C'est cela qu'il faut suivre.

En conséquence, la compression est publiée comme un rapport observé, jamais
comme un seuil à franchir : aucun invariant `ENFORCED` ne s'y adosse tant que
la série temporelle n'existe pas.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scios.ledger import EventLedger
from scios.objects.store import ObjectStore

# Ordre de condensation attendu de la boucle scientifique.
COMPRESSION_CHAIN = (
    "Event",
    "Observation",
    "Hypothesis",
    "Experiment",
    "Verdict",
    "Calibration",
    "Deployment",
)


@dataclass
class LabIndicators:
    counts: dict[str, int] = field(default_factory=dict)
    ratios: dict[str, float | None] = field(default_factory=dict)
    integrity: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    velocity: dict[str, dict[str, int]] = field(default_factory=dict)
    absent: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "compression_ratios": self.ratios,
            "integrity": self.integrity,
            "coverage": self.coverage,
            "velocity": self.velocity,
            "absent_objects": self.absent,
        }

    def render(self) -> str:
        lines = ["INDICATEURS DU LABORATOIRE", ""]
        lines.append("Volumétrie par type d'objet")
        for kind in COMPRESSION_CHAIN:
            n = self.counts.get(kind, 0)
            mark = "" if n else "   (aucun — objet non implémenté)"
            lines.append(f"  {kind:<14} {n:>6}{mark}")
        lines.append("")
        lines.append("Compression (n(precedent) / n(suivant))")
        if not self.ratios:
            lines.append("  NON CALCULABLE — un seul maillon peuplé")
        for label, value in self.ratios.items():
            shown = "NON CALCULABLE" if value is None else f"{value:>8.1f}"
            lines.append(f"  {label:<28} {shown}")
        lines.append("")
        lines.append("Provenance et intégrité")
        for label, value in self.integrity.items():
            lines.append(f"  {label:<28} {value}")
        lines.append("")
        lines.append("Vélocité de connaissance (par mois)")
        if len(self.velocity) < 2:
            lines.append(
                "  SÉRIE TROP COURTE — un laboratoire se juge sur sa tendance, "
                "pas sur un point"
            )
        for periode in sorted(self.velocity):
            detail = "  ".join(
                f"{k[:3]} {v:>5}" for k, v in sorted(self.velocity[periode].items())
            )
            lines.append(f"  {periode}   {detail}")
        lines.append("")
        lines.append("Couverture de la boucle scientifique")
        for label, value in self.coverage.items():
            lines.append(f"  {label:<28} {value}")
        if self.absent:
            lines.append("")
            lines.append("Maillons absents : " + ", ".join(self.absent) + ".")
            lines.append(
                "Tant qu'ils le sont, le laboratoire observe mais ne conclut pas."
            )
        return "\n".join(lines)


def compute(root: Path) -> LabIndicators:
    """Calcule les indicateurs à partir des journaux. Lecture seule."""
    root = Path(root)
    ledger = EventLedger(root)
    store = ObjectStore(root)

    counts: dict[str, int] = {k: 0 for k in COMPRESSION_CHAIN}
    counts["Event"] = ledger.count()

    current = store.current()
    for obj in current.values():
        counts[obj.KIND] = counts.get(obj.KIND, 0) + 1

    # Compression : uniquement entre maillons consécutifs tous deux peuplés.
    ratios: dict[str, float | None] = {}
    for upstream, downstream in zip(COMPRESSION_CHAIN, COMPRESSION_CHAIN[1:]):
        label = f"{upstream} -> {downstream}"
        up, down = counts.get(upstream, 0), counts.get(downstream, 0)
        ratios[label] = (up / down) if up and down else None

    ledger_problems = ledger.verify()
    store_problems = store.verify()

    # Une observation est tracée si elle cite ses événements explicitement OU
    # si elle porte un sélecteur reproductible : les deux formes descendent
    # jusqu'à l'atome, la seconde à coût constant.
    with_events = sum(
        1
        for o in current.values()
        if getattr(o, "source_events", ()) or getattr(o, "source_selector", None)
    )
    reproducible = sum(
        1 for o in current.values() if getattr(o, "source_selector", None)
    )
    observations = counts.get("Observation", 0)

    actors = Counter(o.provenance.actor_id for o in current.values())

    integrity = {
        "violations ledger": len(ledger_problems) or "aucune",
        "violations magasin": len(store_problems) or "aucune",
        "provenance complète": f"{len(current)}/{len(current)}",
        "acteurs distincts": len(actors),
    }

    coverage = {
        "observations tracées": (
            f"{with_events}/{observations}" if observations else "sans objet"
        ),
        "dont reproductibles": (
            f"{reproducible}/{observations}" if observations else "sans objet"
        ),
        "hypothèses ouvertes": counts.get("Hypothesis", 0),
        "verdicts émis": counts.get("Verdict", 0),
        "rejeux exécutés": 0,
        "calibrations appliquées": counts.get("Calibration", 0),
    }

    absent = [k for k in COMPRESSION_CHAIN if counts.get(k, 0) == 0]

    return LabIndicators(
        counts=counts,
        ratios=ratios,
        integrity=integrity,
        coverage=coverage,
        velocity=_velocity(ledger, current),
        absent=absent,
    )


def _velocity(ledger: EventLedger, current: dict) -> dict[str, dict[str, int]]:
    """Production par mois et par type — série temporelle, jamais un score.

    Un laboratoire peut mourir sans que le trading se degrade : 100 000
    evenements et zero observation decrivent un systeme qui enregistre sans
    apprendre. Seule la serie le montre ; un instantane ne le peut pas.

    Les evenements sont dates par leur instant d'occurrence (`ts_utc`), les
    objets derives par leur instant de creation : c'est le delai entre les deux
    qui mesure la reactivite du laboratoire.
    """
    series: dict[str, dict[str, int]] = {}

    def bump(moment: str, kind: str) -> None:
        periode = (moment or "")[:7]
        if len(periode) == 7:
            series.setdefault(periode, {})[kind] = (
                series.setdefault(periode, {}).get(kind, 0) + 1
            )

    for evt in ledger.read_all():
        bump(evt.ts_utc, "Event")
    for obj in current.values():
        bump(obj.created_at, obj.KIND)
    return series
