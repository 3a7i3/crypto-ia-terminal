"""Analyse croisée GitHub ↔ hôte ↔ références déclarées, pure et déterministe.

Règles :
- un runtime égal à la référence gelée déclarée (#286) alors que main a avancé est
  ``EXPECTED_PINNED_RUNTIME`` : ce n'est pas un écart à corriger ;
- un hôte indisponible ou un HEAD inconnu donne ``INSUFFICIENT_EVIDENCE`` ;
- un snapshot hôte périmé donne ``STALE`` ;
- un SHA déployé inattendu reste ``POSSIBLE_DRIFT`` : Sentinel n'a pas les preuves
  d'origine nécessaires pour affirmer ``VIOLATION_PROVEN``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from governance_tower.contracts import (
    Availability,
    ClaimStatus,
    Discrepancy,
    DiscrepancyClass,
    Domain,
    EvidenceRef,
    Finding,
    HostSnapshot,
    MissionProposal,
    Observation,
    PinnedReference,
    RepositorySnapshot,
    Severity,
)
from governance_tower.sentinel.injection import looks_like_instruction


@dataclass
class AnalysisResult:
    discrepancies: list[Discrepancy] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    proposals: list[MissionProposal] = field(default_factory=list)
    suspicious_quotes: list[str] = field(default_factory=list)


def short(sha: str | None) -> str:
    return sha[:12] if sha else "inconnu"


def _value(obs: Observation) -> dict[str, Any]:
    return obs.value if obs.has_value and isinstance(obs.value, dict) else {}


def _evidence(*groups: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    seen: dict[str, EvidenceRef] = {}
    for group in groups:
        for ev in group:
            seen.setdefault(ev.evidence_id, ev)
    return tuple(seen.values())


def _obs_evidence(snapshot: RepositorySnapshot | HostSnapshot | None, domain: Domain) -> tuple[EvidenceRef, ...]:
    if snapshot is None:
        return ()
    return _evidence(*(o.evidence for o in snapshot.get(domain)))


def compare_runtime(
    repo: RepositorySnapshot | None,
    host: HostSnapshot | None,
    pinned: tuple[PinnedReference, ...],
) -> Discrepancy:
    pinned_shas = {p.runtime_source_sha: p for p in pinned}
    ref_evidence = tuple(p.evidence for p in pinned)
    head = repo.head_sha if repo is not None and repo.availability.value in ("AVAILABLE", "STALE") else None
    deployed = host.deployed_source_sha if host is not None else None
    expectation = (
        "Runtime PAPER gelé sous #286 sur "
        + ", ".join(f"{short(p.runtime_source_sha)} ({p.epoch_id})" for p in pinned)
        + " ; main peut avancer sans que le runtime doive suivre."
        if pinned
        else "Aucune référence gelée déclarée disponible."
    )
    evidence = _evidence(
        _obs_evidence(repo, Domain.REPOSITORY), _obs_evidence(host, Domain.HOST_DEPLOYMENT), ref_evidence
    )
    if host is None or host.availability not in (Availability.AVAILABLE, Availability.STALE):
        reason = host.reason if host is not None else "non consulté"
        return Discrepancy(
            "cmp-runtime",
            "Source GitHub (main) vs runtime observé",
            DiscrepancyClass.INSUFFICIENT_EVIDENCE,
            expectation,
            f"VPS non disponible ({reason}) : aucune conclusion sur le runtime, ni conforme ni en écart.",
            _evidence(_obs_evidence(repo, Domain.REPOSITORY), ref_evidence),
            github_value=head,
        )
    if deployed is None:
        return Discrepancy(
            "cmp-runtime",
            "Source GitHub (main) vs runtime observé",
            DiscrepancyClass.INSUFFICIENT_EVIDENCE,
            expectation,
            "Le snapshot hôte ne publie pas de SHA de déploiement : provenance du runtime non établie.",
            evidence,
            github_value=head,
        )
    if host.availability is Availability.STALE:
        return Discrepancy(
            "cmp-runtime",
            "Source GitHub (main) vs runtime observé",
            DiscrepancyClass.STALE,
            expectation,
            f"Le dernier snapshot hôte (SHA {short(deployed)}) est périmé : il ne décrit pas l'état actuel.",
            evidence,
            github_value=head,
            host_value=deployed,
        )
    if head is None:
        if deployed in pinned_shas:
            text = (
                f"Le runtime observé ({short(deployed)}) correspond à la référence gelée déclarée ; "
                "HEAD GitHub non disponible, comparaison avec main impossible."
            )
        else:
            text = "HEAD GitHub non disponible : comparaison avec main impossible."
        return Discrepancy(
            "cmp-runtime",
            "Source GitHub (main) vs runtime observé",
            DiscrepancyClass.INSUFFICIENT_EVIDENCE,
            expectation,
            text,
            evidence,
            host_value=deployed,
        )
    if deployed == head:
        cls, text = DiscrepancyClass.ALIGNED, "Le runtime observé exécute le même SHA que main."
        if pinned_shas and deployed not in pinned_shas:
            cls = DiscrepancyClass.POSSIBLE_DRIFT
            text = (
                f"Le runtime observé exécute main ({short(head)}) mais pas la référence gelée déclarée sous #286 : "
                "à vérifier, le runtime aurait dû rester épinglé."
            )
    elif deployed in pinned_shas:
        cls = DiscrepancyClass.EXPECTED_PINNED_RUNTIME
        text = (
            f"Le runtime observé ({short(deployed)}) est la référence gelée déclarée ; main ({short(head)}) a avancé. "
            "Écart attendu : ne pas « installer main », le burn-in doit rester intact."
        )
    else:
        cls = DiscrepancyClass.POSSIBLE_DRIFT
        text = (
            f"Le runtime observé ({deployed}) n'est ni main ({head}) ni la référence gelée déclarée. "
            "Dérive possible ; Sentinel ne dispose pas de preuve d'origine suffisante pour conclure à une violation."
        )
    return Discrepancy(
        "cmp-runtime",
        "Source GitHub (main) vs runtime observé",
        cls,
        expectation,
        text,
        evidence,
        github_value=head,
        host_value=deployed,
    )


def _drift_proposal(finding_id: str) -> MissionProposal:
    return MissionProposal(
        proposal_id=f"prop-{finding_id}",
        title="Vérifier en lecture seule l'origine du SHA déployé",
        problem_ref=finding_id,
        description=(
            "Rapprocher le SHA publié par le snapshot runtime-service de la release installée et des preuves "
            "de déploiement datées, sans rien modifier. Conclure seulement avec des preuves d'origine."
        ),
        allowed_scope=(
            "Lecture des snapshots publiés et des preuves GitHub datées",
            "Checkpoint VPS READ-ONLY dans une mission séparée autorisée",
        ),
        required_evidence=(
            "SHA et empreinte d'artefact du snapshot runtime-service",
            "Preuve de release ou d'exception #286 correspondante",
        ),
        tests=("Comparaison reproductible SHA publié / release / référence #286",),
    )


def _verification_proposal(finding_id: str, title: str, subject: str) -> MissionProposal:
    return MissionProposal(
        proposal_id=f"prop-{finding_id}",
        title=title,
        problem_ref=finding_id,
        description=f"Documenter et vérifier en lecture seule : {subject}. Aucune correction runtime dans cette mission.",
        allowed_scope=("Lecture des preuves publiées", "Rapport daté sur GitHub après décision opérateur"),
        required_evidence=("Observation datée et sa provenance",),
        tests=("Relecture indépendante de la preuve",),
    )


def analyse(
    repo: RepositorySnapshot | None,
    host: HostSnapshot | None,
    pinned: tuple[PinnedReference, ...],
    extra_observations: tuple[Observation, ...] = (),
) -> AnalysisResult:
    result = AnalysisResult()
    cmp = compare_runtime(repo, host, pinned)
    result.discrepancies.append(cmp)

    if cmp.classification is DiscrepancyClass.POSSIBLE_DRIFT:
        f = Finding(
            "f-runtime-drift",
            "SHA runtime inattendu par rapport à la référence gelée",
            Severity.WARNING,
            "Le runtime observé ne correspond pas à la référence déclarée sous #286 ; impact potentiel sur "
            "l'intégrité du burn-in, non prouvé.",
            ClaimStatus.OBSERVED,
            cmp.evidence,
            "Si confirmé, l'epoch active pourrait ne plus tourner sur le code gelé.",
            hypothesis="Déploiement non consigné, snapshot erroné ou référence documentaire obsolète.",
            suggestion="Vérification READ-ONLY de l'origine du SHA avant toute conclusion.",
        )
        result.findings.append(f)
        result.proposals.append(_drift_proposal(f.finding_id))

    if repo is not None:
        for obs in repo.get(Domain.CI):
            status = str(_value(obs).get("status", "")).upper()
            if status == "FAILURE":
                f = Finding(
                    "f-ci-failure",
                    "CI en échec sur le HEAD de main",
                    Severity.WARNING,
                    "Au moins un check du HEAD est en échec : la source n'est pas dans un état vérifié.",
                    ClaimStatus.OBSERVED,
                    obs.evidence,
                    "Une fusion ou une release préparée depuis ce HEAD ne serait pas prouvée.",
                    suggestion="Ouvrir une mission source de correction de CI (hors runtime).",
                )
                result.findings.append(f)
                result.proposals.append(
                    _verification_proposal(f.finding_id, "Diagnostiquer l'échec de CI sur main", "les checks en échec du HEAD")
                )
        for obs in repo.get(Domain.ISSUES):
            missing = _value(obs).get("tracked_missing") or []
            if missing:
                result.findings.append(
                    Finding(
                        "f-tracked-issues",
                        "Issues de gouvernance non observées dans la page lue",
                        Severity.INFO,
                        "Absence de la page lue ≠ issue fermée : simple limite de lecture.",
                        ClaimStatus.OBSERVED,
                        obs.evidence,
                        f"Issues non observées : {', '.join('#' + str(n) for n in missing[:10])}.",
                    )
                )

    if host is not None:
        for obs in host.get(Domain.HOST_SERVICE):
            v = _value(obs)
            if not v or obs.subject == "journal_excerpt":
                continue
            active, sub = v.get("active_state"), v.get("sub_state")
            if active is not None and (active, sub) != ("active", "running"):
                f = Finding(
                    "f-service-state",
                    f"Service {v.get('unit', 'observé')} hors état active/running",
                    Severity.CRITICAL if active == "failed" else Severity.WARNING,
                    f"État publié {active}/{sub} : le runtime observé n'est pas en fonctionnement nominal.",
                    ClaimStatus.OBSERVED,
                    obs.evidence,
                    "L'expérience PAPER pourrait ne pas produire de données pendant cette période.",
                    suggestion="Signalement à l'opérateur ; aucune action sur le service depuis Governance Tower.",
                )
                result.findings.append(f)
                result.proposals.append(
                    _verification_proposal(f.finding_id, "Établir l'état réel du service par checkpoint READ-ONLY", "l'état du service Advisor")
                )
            restarts = v.get("restart_count")
            if isinstance(restarts, int) and not isinstance(restarts, bool) and restarts > 0:
                result.findings.append(
                    Finding(
                        "f-service-restarts",
                        "Redémarrages comptés par systemd",
                        Severity.NOTICE,
                        f"NRestarts={restarts} publié : à rapprocher des opérations consignées.",
                        ClaimStatus.OBSERVED,
                        obs.evidence,
                        "Un redémarrage non consigné toucherait la continuité du burn-in.",
                    )
                )
        for obs in host.get(Domain.HOST_STORAGE):
            status = _value(obs).get("source_status")
            if status is not None and status != "PRESENT":
                result.findings.append(
                    Finding(
                        "f-storage-status",
                        "Source de stockage publiée hors état PRESENT",
                        Severity.NOTICE,
                        f"source_status={status} : l'inventaire des fichiers de décision n'est pas complet.",
                        ClaimStatus.OBSERVED,
                        obs.evidence,
                        "Les métriques de stockage restent inconnues, pas nulles.",
                    )
                )

    # Contenus externes ressemblant à des instructions : signalés, cités, jamais suivis.
    sources: list[Observation] = list(extra_observations)
    if repo is not None:
        sources.extend(repo.observations)
    if host is not None:
        sources.extend(host.observations)
    flagged: list[EvidenceRef] = []
    for obs in sources:
        if not obs.untrusted_content or not obs.has_value:
            continue
        for text in _texts(obs.value):
            if looks_like_instruction(text) and text not in result.suspicious_quotes:
                result.suspicious_quotes.append(text[:600])
                flagged.extend(obs.evidence)
    if result.suspicious_quotes:
        result.findings.append(
            Finding(
                "f-untrusted-instructions",
                "Contenu externe formulé comme une instruction",
                Severity.NOTICE,
                "Texte provenant de GitHub ou d'un journal qui demande une action ; il est cité comme donnée, jamais exécuté.",
                ClaimStatus.OBSERVED,
                _evidence(tuple(flagged)),
                "Tentative possible d'injection d'instructions ; aucune conséquence sur les outils de Sentinel.",
                suggestion="Relire la source concernée ; signaler si elle est malveillante.",
            )
        )
    return result


def _texts(value: Any, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for v in value.values():
            out.extend(_texts(v, depth + 1))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_texts(v, depth + 1))
        return out
    return []
