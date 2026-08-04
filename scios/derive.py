"""Event -> Observation : le premier lien exécutable de la boucle.

Un lien est *exécutable* quand quatre conditions sont réunies :

  1. une **dérivation** nommée et versionnée transforme un ensemble
     d'événements en un énoncé descriptif ;
  2. elle est **reproductible** — mêmes événements + même version = même
     énoncé, aux identifiants et horodatages près ;
  3. l'observation **enregistre** de quoi elle vient (sélecteur, décompte,
     empreinte du jeu d'événements) et par quoi (nom et version de la
     dérivation, via la provenance) ;
  4. elle est **vérifiable** : `reproduce()` re-sélectionne, recalcule et
     compare. Une observation qui ne se reproduit plus est signalée.

Le point 4 est la graine du moteur de rejeu, appliquée au maillon le plus
simple. Si le lien le plus court n'est pas reproductible, aucun des suivants
ne le sera.

Pourquoi une empreinte plutôt que la liste des identifiants
-----------------------------------------------------------
Une dérivation sur 709 clôtures inscrirait 709 identifiants dans l'objet. À
l'échelle d'un ledger de plusieurs millions d'événements, la provenance
coûterait plus cher que le fait. L'observation enregistre donc le **sélecteur**
(comment re-choisir exactement le même ensemble), le **décompte** et
l'**empreinte** du jeu d'identifiants triés. La vérification reste totale :
un événement ajouté, retiré ou substitué change l'empreinte.

`source_events` reste réservé aux observations à sources peu nombreuses et
citées explicitement.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scios.ledger import Event, EventLedger
from scios.objects.base import canonical_dumps, utc_now
from scios.objects.observation import Observation
from scios.objects.provenance import ActorType, ConfidenceBasis, Provenance
from scios.objects.store import ObjectStore


class DerivationError(RuntimeError):
    """La dérivation ne peut pas s'appliquer."""


@dataclass(frozen=True)
class DerivedFact:
    statement: str
    metrics: dict[str, Any]
    n: int | None = None


@dataclass(frozen=True)
class Derivation:
    name: str
    version: str
    description: str
    limitations: str
    event_kinds: tuple[str, ...]
    compute: Callable[[list[Event]], DerivedFact]

    @property
    def actor_id(self) -> str:
        return f"derivation:{self.name}"

    def selector(self, epoch_id: str | None) -> dict[str, Any]:
        """Description reproductible de l'ensemble d'entrée."""
        return {
            "derivation": self.name,
            "derivation_version": self.version,
            "event_kinds": list(self.event_kinds),
            "epoch_id": epoch_id,
        }


def event_set_digest(ids: list[str]) -> str:
    return hashlib.sha256(
        canonical_dumps({"ids": sorted(ids)}).encode("utf-8")
    ).hexdigest()


def select(
    ledger: EventLedger, derivation: Derivation, epoch_id: str | None
) -> list[Event]:
    return [
        e
        for e in ledger.read_all()
        if e.event_kind in derivation.event_kinds
        and (epoch_id is None or e.epoch_id == epoch_id)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Dérivations. Chaque énoncé est DESCRIPTIF : aucune cause, aucun jugement.
# ─────────────────────────────────────────────────────────────────────────────


def _census(events: list[Event]) -> DerivedFact:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.event_kind] = counts.get(e.event_kind, 0) + 1
    detail = ", ".join(f"{k} : {v}" for k, v in sorted(counts.items()))
    return DerivedFact(
        statement=f"Le ledger contient {len(events)} evenements de trade ({detail}).",
        metrics=counts,
        n=len(events),
    )


def _pnl(events: list[Event]) -> DerivedFact:
    pnls = [
        float(e.payload_data["pnl_usd"])
        for e in events
        if e.payload_data.get("pnl_usd") is not None
    ]
    if not pnls:
        raise DerivationError("aucune cloture ne porte de pnl_usd")
    gains = [p for p in pnls if p > 0]
    pertes = [p for p in pnls if p < 0]
    somme_gains = sum(gains)
    somme_pertes = abs(sum(pertes))
    pf = (somme_gains / somme_pertes) if somme_pertes else None
    wr = len(gains) / len(pnls)
    return DerivedFact(
        statement=(
            f"Sur {len(pnls)} clotures portant un pnl_usd : {len(gains)} positives, "
            f"{len(pertes)} negatives, taux de positives {wr:.3f}, "
            f"profit factor {'non calculable' if pf is None else f'{pf:.3f}'}, "
            f"somme {sum(pnls):+.2f} USD."
        ),
        metrics={
            "n_closes": len(pnls),
            "n_positives": len(gains),
            "n_negatives": len(pertes),
            "win_rate": round(wr, 6),
            "profit_factor": None if pf is None else round(pf, 6),
            "somme_pnl_usd": round(sum(pnls), 6),
        },
        n=len(pnls),
    )


def _duration(events: list[Event]) -> DerivedFact:
    durees = [
        float(e.payload_data["duration_s"])
        for e in events
        if e.payload_data.get("duration_s") is not None
    ]
    if not durees:
        raise DerivationError("aucune cloture ne porte de duration_s")
    mediane_h = statistics.median(durees) / 3600.0
    return DerivedFact(
        statement=(
            f"Sur {len(durees)} clotures portant une duree, la detention mediane "
            f"vaut {mediane_h:.2f} h (min {min(durees)/3600:.2f} h, "
            f"max {max(durees)/3600:.2f} h)."
        ),
        metrics={
            "n": len(durees),
            "mediane_h": round(mediane_h, 6),
            "min_h": round(min(durees) / 3600, 6),
            "max_h": round(max(durees) / 3600, 6),
        },
        n=len(durees),
    )


def _exit_reasons(events: list[Event]) -> DerivedFact:
    counts: dict[str, int] = {}
    for e in events:
        raison = str(e.payload_data.get("reason") or "(vide)")
        counts[raison] = counts.get(raison, 0) + 1
    total = sum(counts.values())
    detail = ", ".join(
        f"{k} : {v} ({v/total:.1%})"
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    )
    return DerivedFact(
        statement=f"Repartition des motifs de sortie sur {total} clotures — {detail}.",
        metrics=counts,
        n=total,
    )


DERIVATIONS: dict[str, Derivation] = {
    d.name: d
    for d in (
        Derivation(
            name="trade_event_census",
            version="1.0.0",
            description="comptage des evenements de trade par type",
            limitations=(
                "compte des evenements journalises, pas des trades : une "
                "ouverture sans cloture correspondante est comptee"
            ),
            event_kinds=("TRADE_OPEN", "TRADE_CLOSE"),
            compute=_census,
        ),
        Derivation(
            name="close_pnl_distribution",
            version="1.0.0",
            description="distribution des pnl_usd sur les clotures",
            limitations=(
                "les clotures sans pnl_usd sont exclues du calcul et non "
                "imputees ; les frais reels ne sont pas modelises ; la fidelite "
                "du simulateur d'execution est NON MESUREE"
            ),
            event_kinds=("TRADE_CLOSE",),
            compute=_pnl,
        ),
        Derivation(
            name="holding_duration",
            version="1.0.0",
            description="mediane de duration_s sur les clotures",
            limitations=(
                "duration_s est produit par le moteur ; les clotures sans duree "
                "sont exclues"
            ),
            event_kinds=("TRADE_CLOSE",),
            compute=_duration,
        ),
        Derivation(
            name="exit_reason_mix",
            version="1.0.0",
            description="repartition des motifs de sortie",
            limitations="le vocabulaire des motifs est celui du moteur, non normalise",
            event_kinds=("TRADE_CLOSE",),
            compute=_exit_reasons,
        ),
    )
}


# ─────────────────────────────────────────────────────────────────────────────
# Exécution du lien et vérification
# ─────────────────────────────────────────────────────────────────────────────


def _provenance(
    derivation: Derivation, epoch_id: str | None, n_events: int
) -> Provenance:
    return Provenance(
        actor_type=ActorType.TOOL,
        actor_id=derivation.actor_id,
        actor_version=derivation.version,
        method=(
            f"{derivation.description} ; selection {derivation.event_kinds} "
            f"sur epoque {epoch_id or 'toutes'} ; {n_events} evenements"
        ),
        limitations=derivation.limitations,
        confidence=1.0,
        confidence_basis=ConfidenceBasis.MEASUREMENT,
    )


def derive(
    root: Path, name: str, epoch_id: str | None = None, year: int = 2026
) -> Observation:
    """Applique une dérivation au ledger et journalise l'observation produite."""
    if name not in DERIVATIONS:
        raise DerivationError(f"derivation inconnue: {name!r}")
    derivation = DERIVATIONS[name]
    ledger, store = EventLedger(root), ObjectStore(root)

    events = select(ledger, derivation, epoch_id)
    if not events:
        raise DerivationError(
            f"{name}: aucun evenement selectionne "
            f"(kinds={derivation.event_kinds}, epoch={epoch_id})"
        )
    fact = derivation.compute(events)
    ids = [e.id for e in events]

    return store.create(
        Observation,
        year,
        created_at=utc_now(),
        provenance=_provenance(derivation, epoch_id, len(events)),
        epoch_id=epoch_id,
        statement=fact.statement,
        metrics=fact.metrics,
        n=fact.n,
        source_selector=derivation.selector(epoch_id),
        source_event_count=len(events),
        source_event_digest=event_set_digest(ids),
    )


def reproduce(root: Path, observation: Observation) -> list[str]:
    """Re-exécute la dérivation d'une observation et compare. [] = reproduite."""
    selector = observation.source_selector
    if not selector:
        return []  # observation non dérivée : rien à reproduire

    name = selector.get("derivation")
    if name not in DERIVATIONS:
        return [
            f"{observation.id}: derivation {name!r} absente du registre — "
            "l'observation n'est plus reproductible avec ce code"
        ]
    derivation = DERIVATIONS[name]
    problems: list[str] = []

    if selector.get("derivation_version") != derivation.version:
        problems.append(
            f"{observation.id}: produite par {name} v"
            f"{selector.get('derivation_version')}, registre en v{derivation.version} "
            "— comparaison faite sous la version courante"
        )

    events = select(EventLedger(root), derivation, selector.get("epoch_id"))
    if len(events) != observation.source_event_count:
        problems.append(
            f"{observation.id}: {len(events)} evenements selectionnes contre "
            f"{observation.source_event_count} a l'origine"
        )
    digest = event_set_digest([e.id for e in events])
    if digest != observation.source_event_digest:
        problems.append(
            f"{observation.id}: le jeu d'evenements a change "
            f"({digest[:12]} != {observation.source_event_digest[:12]})"
        )
        return problems

    fact = derivation.compute(events)
    if fact.statement != observation.statement:
        problems.append(f"{observation.id}: enonce different apres recalcul")
    if fact.metrics != observation.metrics:
        problems.append(f"{observation.id}: metriques differentes apres recalcul")
    return problems


def reproduce_all(root: Path) -> list[str]:
    store = ObjectStore(root)
    problems: list[str] = []
    for obj in store.current().values():
        if isinstance(obj, Observation):
            problems.extend(reproduce(root, obj))
    return problems
