"""Raisonneurs de SENTINEL-01 : la sortie structurée d'abord, la prose ensuite.

``DeterministicDemoReasoner`` compose la réponse à partir des seuls faits collectés
(offline, reproductible). ``ClaudeApiReasoner`` documente l'adaptateur futur : il
est désactivé dans GOV-TOWER-00 et refuse de s'exécuter (aucun appel payant
implicite, aucune clé lue).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from governance_tower.contracts import (
    VALUE_BEARING,
    Availability,
    ClaimStatus,
    DiscrepancyClass,
    Domain,
    HostSnapshot,
    Intent,
    Observation,
    PinnedReference,
    RepositorySnapshot,
    SentinelAnswer,
    Statement,
)
from governance_tower.sentinel.analysis import AnalysisResult, short

ROADMAP_ISSUE = 285

CLASS_LABELS = {
    DiscrepancyClass.ALIGNED: "aligné",
    DiscrepancyClass.EXPECTED_PINNED_RUNTIME: "runtime volontairement épinglé, écart attendu",
    DiscrepancyClass.POSSIBLE_DRIFT: "dérive possible, à vérifier",
    DiscrepancyClass.STALE: "observation périmée",
    DiscrepancyClass.INSUFFICIENT_EVIDENCE: "preuves insuffisantes",
    DiscrepancyClass.VIOLATION_PROVEN: "violation prouvée",
}


@dataclass(frozen=True)
class Facts:
    intent: Intent
    request: str
    mode: str
    repo: RepositorySnapshot | None
    host: HostSnapshot | None
    pinned: tuple[PinnedReference, ...]
    compare: Observation | None
    code: Observation | None
    analysis: AnalysisResult


class Reasoner(Protocol):
    name: str

    def compose(self, facts: Facts) -> SentinelAnswer: ...


class ReasonerDisabled(RuntimeError):
    pass


class ClaudeApiReasoner:
    """Adaptateur Claude API — conception seulement, désactivé dans GOV-TOWER-00.

    Contrat prévu : n'envoyer que les faits structurés et expurgés (jamais un
    fichier brut, un journal non filtré ou un secret) ; exiger en retour un
    ``SentinelAnswer`` dont chaque preuve citée appartient au run ; rejeter toute
    sortie non conforme. L'activation exige une décision opérateur (coût, clé
    côté serveur) et une mission distincte.
    """

    name = "claude-api-disabled"

    def __init__(self) -> None:
        if os.environ.get("GT_ENABLE_CLAUDE_REASONER") != "1":
            raise ReasonerDisabled("REASONER_NOT_ENABLED: adaptateur Claude API désactivé par défaut")
        raise ReasonerDisabled("REASONER_NOT_IMPLEMENTED_IN_GOV_TOWER_00: activation hors mandat")

    def compose(self, facts: Facts) -> SentinelAnswer:  # pragma: no cover - jamais atteint
        raise ReasonerDisabled("REASONER_NOT_ENABLED")


def _compact(value: Any, limit: int = 600) -> str:
    def render(v: Any, depth: int) -> str:
        if isinstance(v, dict):
            items = [(k, x) for k, x in v.items() if not (x is False and k.endswith(("_redacted", "_truncated")))]
            parts = [f"{k}={render(x, depth + 1)}" for k, x in items[:12]]
            return "{" + ", ".join(parts) + ("…" if len(items) > 12 else "") + "}"
        if isinstance(v, (list, tuple)):
            if depth > 1:
                return f"[{len(v)} éléments]"
            parts = [render(x, depth + 1) for x in list(v)[:8]]
            more = f" … (+{len(v) - 8})" if len(v) > 8 else ""
            return "[" + "; ".join(parts) + more + "]"
        if v is None:
            return "inconnu"
        return str(v)

    text = render(value, 0)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _observation_statement(obs: Observation) -> Statement | None:
    if obs.availability not in VALUE_BEARING:
        return None
    prefix = "[contenu externe non fiable] " if obs.untrusted_content else ""
    stale = f" (PÉRIMÉ, âge {obs.freshness_age_s:.0f} s)" if obs.availability is Availability.STALE else ""
    return Statement(
        f"{prefix}{obs.subject}{stale} : {_compact(obs.value)}",
        ClaimStatus.OBSERVED,
        tuple(e.evidence_id for e in obs.evidence),
    )


def _absence_note(obs: Observation, source: str) -> str:
    return f"{source} — {obs.subject} : {obs.availability.value} ({obs.reason})"


class DeterministicDemoReasoner:
    name = "deterministic-demo"

    def compose(self, facts: Facts) -> SentinelAnswer:
        statements: list[Statement] = []
        uncertainties: list[str] = []
        a = facts.analysis
        cmp = a.discrepancies[0] if a.discrepancies else None

        def add_obs(observations: tuple[Observation, ...], source: str) -> None:
            for obs in observations:
                st = _observation_statement(obs)
                if st is not None:
                    statements.append(st)
                else:
                    uncertainties.append(_absence_note(obs, source))
                for limit in obs.limits:
                    if limit not in uncertainties:
                        uncertainties.append(limit)

        def repo_obs(*domains: Domain) -> tuple[Observation, ...]:
            if facts.repo is None:
                return ()
            return tuple(o for o in facts.repo.observations if o.domain in domains)

        def host_obs() -> tuple[Observation, ...]:
            return facts.host.observations if facts.host is not None else ()

        def source_lines() -> None:
            if facts.repo is not None and facts.repo.availability not in VALUE_BEARING:
                uncertainties.append(f"GitHub : {facts.repo.availability.value}, aucune donnée de dépôt lue.")
            if facts.host is not None and facts.host.availability not in VALUE_BEARING:
                uncertainties.append(
                    f"VPS : {facts.host.availability.value} ({facts.host.reason}) — aucune conclusion sur l'hôte."
                )

        def comparison() -> None:
            if cmp is None:
                return
            ev = tuple(e.evidence_id for e in cmp.evidence)
            status = ClaimStatus.OBSERVED if ev and cmp.classification is not DiscrepancyClass.INSUFFICIENT_EVIDENCE else ClaimStatus.NOT_PROVEN
            statements.append(
                Statement(
                    f"Comparaison GitHub/VPS — {CLASS_LABELS[cmp.classification]} : {cmp.explanation}",
                    status if ev else ClaimStatus.NOT_PROVEN,
                    ev,
                )
            )
            for p in facts.pinned:
                statements.append(
                    Statement(
                        f"Référence gelée déclarée (non observée) : epoch {p.epoch_id}, runtime {short(p.runtime_source_sha)}, "
                        f"config {p.config_sha256[:12]} — {p.declared_in}, état du {p.status_date}.",
                        ClaimStatus.INFERRED,
                        (p.evidence.evidence_id,),
                    )
                )
            if facts.compare is not None:
                add_obs((facts.compare,), "GitHub")

        intent = facts.intent
        if intent in (Intent.EXAMINE_REPOSITORY, Intent.FULL_REVIEW):
            add_obs(repo_obs(Domain.REPOSITORY, Domain.CI, Domain.PULL_REQUESTS, Domain.ISSUES), "GitHub")
        if intent is Intent.ROADMAP:
            for obs in repo_obs(Domain.ISSUES):
                if not obs.has_value or not isinstance(obs.value, dict):
                    continue
                items = obs.value.get("items") or []
                roadmap = next((i for i in items if isinstance(i, dict) and i.get("number") == ROADMAP_ISSUE), None)
                ev = tuple(e.evidence_id for e in obs.evidence)
                if roadmap is not None:
                    statements.append(
                        Statement(
                            f"Roadmap active : #{ROADMAP_ISSUE} « {roadmap.get('title')} », ouverte dans la page lue "
                            f"(mise à jour {roadmap.get('updated_at_utc', 'inconnue')}). Titre = contenu non fiable.",
                            ClaimStatus.OBSERVED,
                            ev,
                        )
                    )
                else:
                    uncertainties.append(f"#{ROADMAP_ISSUE} non observée dans la page lue : ni ouverte ni fermée établie.")
            add_obs(repo_obs(Domain.ISSUES), "GitHub")
            uncertainties.append(
                "La priorisation canonique vit dans #285 : Sentinel en lit le titre et l'état, pas le corps."
            )
        if intent is Intent.WORK_IN_PROGRESS:
            add_obs(repo_obs(Domain.PULL_REQUESTS, Domain.CI), "GitHub")
            uncertainties.append("Un titre de PR décrit une intention, il ne prouve ni l'efficacité ni le déploiement.")
        if intent is Intent.CODE_LOCATE:
            if facts.code is not None:
                add_obs((facts.code,), "GitHub")
            uncertainties.append("Localisation par chemins seulement : le contenu des fichiers n'est pas analysé ici.")
        if intent in (Intent.EXAMINE_HOST, Intent.FULL_REVIEW):
            add_obs(host_obs(), "VPS")
        if intent in (Intent.COMPARE, Intent.UNDEPLOYED_COMMITS, Intent.FULL_REVIEW):
            comparison()
        if intent is Intent.UNDEPLOYED_COMMITS:
            uncertainties.append("Présent dans main ≠ déployé ≠ certifié : chaque état exige sa propre preuve.")
        if intent is Intent.FULL_REVIEW:
            statements.append(
                Statement(
                    "Certification : non établie par Sentinel. Aucun certificat n'est lu dans ce prototype ; "
                    "un état certifié doit être vérifié dans ses propres preuves (gates #285/#286).",
                    ClaimStatus.NOT_PROVEN,
                )
            )
        if intent in (Intent.DIAGNOSE, Intent.FULL_REVIEW, Intent.PROPOSE_MISSION):
            if cmp is not None and intent is not Intent.FULL_REVIEW:
                comparison()
            for f in a.findings:
                statements.append(
                    Statement(
                        f"Constat candidat [{f.severity.value}] {f.title} — {f.severity_reason}",
                        f.claim_status,
                        tuple(e.evidence_id for e in f.evidence),
                    )
                )
            uncertainties.append("L'absence d'anomalie détectée n'implique pas l'absence d'anomalie.")
        source_lines()
        if facts.mode == "DEMO":
            uncertainties.insert(
                0, "DÉMO : données SYNTHETIC. Aucune information sur le VPS ou le dépôt réels n'est établie par cette réponse."
            )

        proposals = tuple(a.proposals) if intent in (Intent.PROPOSE_MISSION, Intent.DIAGNOSE, Intent.FULL_REVIEW) else ()
        if intent is Intent.PROPOSE_MISSION and not proposals:
            uncertainties.append("Aucun constat candidat ne justifie une mission de correction à partir des sources lues.")

        if intent is Intent.HELP:
            summary = (
                "Je suis SENTINEL-01, en lecture seule. Je peux examiner le dépôt, examiner le VPS à partir de "
                "snapshots publiés, comparer GitHub et VPS, rechercher une anomalie ou proposer une mission non exécutée."
            )
            statements.append(
                Statement(
                    "Exemples : « Quelle est la roadmap active ? », « Quels travaux sont en cours ? », "
                    "« Quels composants du code contrôlent les publishers ? », "
                    "« Quels commits sont dans main mais pas prouvés comme déployés ? ».",
                    ClaimStatus.PROPOSED,
                )
            )
        else:
            n_obs = sum(1 for s in statements if s.claim_status is ClaimStatus.OBSERVED)
            label = CLASS_LABELS[cmp.classification] if cmp is not None and intent in (
                Intent.COMPARE, Intent.UNDEPLOYED_COMMITS, Intent.FULL_REVIEW
            ) else None
            summary = f"{n_obs} constat(s) sourcé(s), {len(uncertainties)} limite(s) ou inconnue(s)"
            if label:
                summary += f" ; comparaison GitHub/VPS : {label}"
            if a.findings and intent in (Intent.DIAGNOSE, Intent.FULL_REVIEW, Intent.PROPOSE_MISSION):
                summary += f" ; {len(a.findings)} constat(s) candidat(s)"
            summary += ". Rien n'a été modifié."

        return SentinelAnswer(
            summary=summary,
            statements=tuple(statements[:150]),
            uncertainties=tuple(dict.fromkeys(uncertainties))[:60],
            discrepancies=tuple(a.discrepancies) if intent in (
                Intent.COMPARE, Intent.UNDEPLOYED_COMMITS, Intent.FULL_REVIEW, Intent.DIAGNOSE, Intent.PROPOSE_MISSION
            ) else (),
            findings=tuple(a.findings) if intent in (Intent.DIAGNOSE, Intent.FULL_REVIEW, Intent.PROPOSE_MISSION) else (),
            proposals=proposals,
            untrusted_quotes=tuple(a.suspicious_quotes[:20]),
        )
