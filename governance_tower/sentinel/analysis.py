"""Analyse croisée GitHub ↔ hôte ↔ références déclarées, pure et déterministe.

Règles :
- un runtime égal à la référence gelée déclarée (#286) alors que main a avancé est
  ``EXPECTED_PINNED_RUNTIME`` : ce n'est pas un écart à corriger ;
- un hôte indisponible ou un HEAD inconnu donne ``INSUFFICIENT_EVIDENCE`` ;
- un snapshot hôte périmé donne ``STALE`` ;
- un SHA déployé inattendu reste ``POSSIBLE_DRIFT`` : Sentinel n'a pas les preuves
  d'origine nécessaires pour affirmer ``VIOLATION_PROVEN``.

GOV-TOWER-01 M3 ajoute des **diagnostics** pédagogiques (``Diagnostic``) :
observation → interprétation limitée → ce qui reste à vérifier → proposition
non exécutée. Ils ne remplacent pas la comparaison ``Discrepancy`` : ils la
détaillent sans jamais conclure à une santé, une certification ou une violation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from governance_tower.contracts import (
    VALUE_BEARING,
    Availability,
    ClaimStatus,
    Diagnostic,
    DiagnosticCode,
    DiagnosticLevel,
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
    diagnostics: list[Diagnostic] = field(default_factory=list)


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
        texts = _texts(obs.value)
        if obs.domain is Domain.CODE_CONTENT:  # un extrait de code est cité ligne à ligne
            texts = [line for t in texts for line in t.splitlines()]
        for text in texts:
            if looks_like_instruction(text) and text[:600] not in result.suspicious_quotes:
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
    result.diagnostics = diagnose(repo, host, pinned, cmp, extra_observations, result.proposals)
    return result


# ── Diagnostics croisés (GOV-TOWER-01 M3) ────────────────────────────────────

_ABSENCE_CODES = {
    Availability.DENIED: DiagnosticCode.SOURCE_DENIED,
    Availability.RATE_LIMITED: DiagnosticCode.SOURCE_RATE_LIMITED,
}


def _first(snapshot: HostSnapshot | None, domain: Domain) -> Observation | None:
    if snapshot is None:
        return None
    for obs in snapshot.get(domain):
        if obs.subject not in ("journal_excerpt", "journaux"):
            return obs
    return None


def _age(obs: Observation | None) -> str:
    if obs is None or obs.freshness_age_s is None:
        return "âge non mesuré"
    return f"âge {obs.freshness_age_s:.0f} s"


def _runtime_diagnostic(
    repo: RepositorySnapshot | None,
    host: HostSnapshot,
    pinned: tuple[PinnedReference, ...],
    cmp: Discrepancy,
    compare: Observation | None,
    proposal_ids: set[str],
) -> Diagnostic:
    pins = {p.runtime_source_sha: p for p in pinned}
    head = repo.head_sha if repo is not None and repo.availability in VALUE_BEARING else None
    deployed = host.deployed_source_sha
    service, deployment = _first(host, Domain.HOST_SERVICE), _first(host, Domain.HOST_DEPLOYMENT)
    host_ev = _evidence(*(o.evidence for o in (service, deployment) if o is not None))
    ref_ev = tuple(p.evidence for p in pinned)
    if host.availability not in VALUE_BEARING:
        return Diagnostic(
            "diag-runtime",
            _ABSENCE_CODES.get(host.availability, DiagnosticCode.SOURCE_UNAVAILABLE),
            DiagnosticLevel.UNKNOWN,
            "VPS non observé",
            f"Les snapshots publiés n'ont pas pu être lus : {host.availability.value} ({host.reason}).",
            "Aucune conclusion sur le runtime, ni conforme ni en écart : une panne de lecture n'est pas un état vide.",
            (
                "Rétablir la lecture des snapshots publiés ; le connecteur distant relève de la gate GT01-V",
                "Ne jamais déduire l'état du runtime depuis main ni depuis la CI",
            ),
            host_ev,
        )
    if deployed is None:
        reason = deployment.reason if deployment is not None and deployment.reason else "non publiée"
        return Diagnostic(
            "diag-runtime",
            DiagnosticCode.NO_DEPLOYED_BUILD_ID,
            DiagnosticLevel.UNKNOWN,
            "Identité du build déployé absente",
            f"Le snapshot runtime-service ne publie pas d'identité de build (deployment : {reason}).",
            "Le code exécuté n'est pas identifiable : impossible de dire s'il s'agit de la référence #286 ou d'autre "
            "chose. Le service peut tourner sans que sa provenance soit prouvée.",
            (
                "Preuve de déploiement datée publiée par le publicateur gouverné (hors Sentinel)",
                "Référence #286 déclarée : " + (", ".join(short(s) for s in pins) or "aucune") + " (non observée)",
            ),
            host_ev,
        )
    if host.availability is Availability.STALE:
        return Diagnostic(
            "diag-runtime",
            DiagnosticCode.STALE,
            DiagnosticLevel.UNKNOWN,
            "Observation du runtime périmée",
            f"Dernier snapshot : SHA {short(deployed)}, {_age(service)}.",
            "Il décrit un état passé : ni l'état actuel, ni une dérive ne peuvent être affirmés.",
            ("Relire un snapshot frais avant toute conclusion", "Vérifier que le publicateur du snapshot fonctionne"),
            host_ev,
        )
    verification: list[str] = []
    if deployment is not None and deployment.has_value and isinstance(deployment.value, dict):
        art = deployment.value.get("artifact_sha256")
        if isinstance(art, str):
            verification.append(f"Empreinte d'artefact {art[:12]} à rapprocher d'une preuve de release datée")
    for p in pins.values():
        verification.append(
            f"Hash de configuration #286 ({p.config_sha256[:12]}) non publié par les snapshots : NON VÉRIFIÉ"
        )
    verification.append(f"Observation ponctuelle ({_age(service)}) ; aucune surveillance continue")
    if compare is not None and compare.has_value and isinstance(compare.value, dict):
        c = compare.value
        verification.append(
            f"GitHub compte {c.get('total_commits')} commit(s) de main absents du runtime "
            f"({c.get('commits_returned')} listé(s)) : présent dans main ≠ déployé"
        )
    elif compare is not None:
        verification.append(f"Comparaison runtime/main non lue ({compare.availability.value}) : nombre de commits inconnu")
    main_txt = f" ; main est à {short(head)}" if head else " ; main n'a pas été lu pour cette question"
    if deployed in pins:
        return Diagnostic(
            "diag-runtime",
            DiagnosticCode.EXPECTED_PINNED_RUNTIME,
            DiagnosticLevel.INFO,
            "Runtime épinglé sur la référence #286",
            f"Le snapshot runtime-service publie le SHA {short(deployed)}, référence déclarée sous #286{main_txt}.",
            "Écart attendu pendant le burn-in : main peut avancer sans que le runtime suive. Cela ne prouve ni la "
            "santé du trading, ni la certification : le SHA est déclaré par le publicateur du snapshot.",
            tuple(verification),
            _evidence(host_ev, ref_ev),
        )
    if not pins and head is not None and deployed == head:
        return Diagnostic(
            "diag-runtime",
            DiagnosticCode.ALIGNED_WITH_MAIN,
            DiagnosticLevel.INFO,
            "Runtime au même SHA que main",
            f"Le snapshot runtime-service publie le SHA de main ({short(head)}).",
            "Même source ≠ même configuration ni même santé.",
            tuple(verification),
            _evidence(host_ev, cmp.evidence),
        )
    drift_prop = "prop-f-runtime-drift"
    return Diagnostic(
        "diag-runtime",
        DiagnosticCode.POSSIBLE_DRIFT,
        DiagnosticLevel.ATTENTION,
        "SHA runtime inattendu",
        f"Le snapshot runtime-service publie {short(deployed)}, qui n'est pas la référence déclarée sous #286"
        f"{main_txt}.",
        "Dérive possible, non prouvée : déploiement non consigné, snapshot erroné ou référence documentaire "
        "obsolète. Sentinel ne conclut pas à une violation sans preuve d'origine.",
        tuple(["Rapprocher le SHA publié d'une preuve de release ou d'une exception #286 datée"] + verification),
        _evidence(host_ev, ref_ev, cmp.evidence),
        drift_prop if drift_prop in proposal_ids else None,
    )


def _ci_diagnostic(obs: Observation, proposal_ids: set[str]) -> Diagnostic | None:
    did = "diag-" + obs.observation_id
    if not obs.has_value:
        return Diagnostic(
            did,
            DiagnosticCode.CI_INCONCLUSIVE,
            DiagnosticLevel.UNKNOWN,
            f"{obs.subject} : non établie",
            f"Les contrôles n'ont pas pu être lus entièrement : {obs.availability.value} ({obs.reason}).",
            "Statut inconnu : ni vert, ni rouge. Une liste incomplète n'est jamais un succès.",
            ("Relire les contrôles du SHA exact", "Distinguer contrôles requis, ignorés et en attente"),
            obs.evidence,
        )
    v = _value(obs)
    status = v.get("status")
    if status == "FAILURE":
        return Diagnostic(
            did,
            DiagnosticCode.CI_FAILURE,
            DiagnosticLevel.ATTENTION,
            f"{obs.subject} : en échec",
            f"{v.get('failed')} contrôle(s) en échec sur {v.get('total')} : "
            + ", ".join(str(n) for n in (v.get("failing_names") or [])[:5]),
            "La source n'est pas dans un état vérifié ; cela ne dit rien du runtime épinglé.",
            ("Lire le journal du contrôle en échec sur GitHub", "Reproduire localement sur le SHA exact"),
            obs.evidence,
            "prop-f-ci-failure" if obs.observation_id == "gh-ci" and "prop-f-ci-failure" in proposal_ids else None,
        )
    if status in ("PENDING", "NONE"):
        detail = (
            f"{v.get('pending')} contrôle(s) en cours sur {v.get('total')}"
            if status == "PENDING"
            else "aucun contrôle réussi observé (ignorés ou neutres seulement, ou aucun contrôle)"
        )
        return Diagnostic(
            did,
            DiagnosticCode.CI_INCONCLUSIVE,
            DiagnosticLevel.UNKNOWN,
            f"{obs.subject} : non conclusive",
            detail[:300] + ".",
            "CI non terminée ⇒ HOLD : aucun verdict de qualité ne peut être tiré.",
            ("Relire après la fin des contrôles",),
            obs.evidence,
        )
    return None


def diagnose(
    repo: RepositorySnapshot | None,
    host: HostSnapshot | None,
    pinned: tuple[PinnedReference, ...],
    cmp: Discrepancy,
    extra_observations: tuple[Observation, ...] = (),
    proposals: list[MissionProposal] | tuple[MissionProposal, ...] = (),
) -> list[Diagnostic]:
    """Diagnostics déterministes, chacun borné à ses preuves ; aucun ne vaut autorisation."""
    proposal_ids = {p.proposal_id for p in proposals}
    compare = next((o for o in extra_observations if o.observation_id == "gh-compare"), None)
    out: list[Diagnostic] = []
    if host is not None:
        out.append(_runtime_diagnostic(repo, host, pinned, cmp, compare, proposal_ids))
    if repo is not None and repo.availability not in VALUE_BEARING:
        first = repo.observations[0] if repo.observations else None
        reason = first.reason if first is not None else "inconnue"
        rate = repo.availability is Availability.RATE_LIMITED
        out.append(
            Diagnostic(
                "diag-github",
                _ABSENCE_CODES.get(repo.availability, DiagnosticCode.SOURCE_UNAVAILABLE),
                DiagnosticLevel.UNKNOWN,
                "GitHub non lu",
                f"Le dépôt n'a pas pu être lu : {repo.availability.value} ({reason}).",
                "Quota ≠ panne : GitHub limite les lectures, aucune requête n'est renvoyée avant la réinitialisation."
                if rate
                else "Refus ou indisponibilité : aucun contournement, aucune valeur déduite.",
                (
                    "Réessayer après la réinitialisation du quota" if rate else "Vérifier l'accès en lecture au dépôt",
                    "main inconnu : aucune comparaison avec le runtime n'est possible",
                ),
                _evidence(*(o.evidence for o in repo.observations)),
            )
        )
    if compare is not None and not compare.has_value:
        out.append(
            Diagnostic(
                "diag-compare",
                DiagnosticCode.NOT_COMPARABLE,
                DiagnosticLevel.UNKNOWN,
                "Commits runtime → main non comparés",
                f"{compare.subject} : {compare.availability.value} ({compare.reason}).",
                "Le nombre de commits entre le runtime et main n'est pas établi ; aucun chiffre approximatif n'est donné.",
                ("Relire la comparaison dans une question ultérieure ou sur GitHub",),
                compare.evidence,
            )
        )
    elif compare is not None and _value(compare).get("status") == "diverged":
        c = _value(compare)
        out.append(
            Diagnostic(
                "diag-compare",
                DiagnosticCode.DIVERGED_HISTORY,
                DiagnosticLevel.ATTENTION,
                "Historique divergé entre runtime et main",
                f"GitHub : ahead_by {c.get('ahead_by')}, behind_by {c.get('behind_by')} — le SHA runtime n'est pas "
                "un ancêtre de main.",
                "Le runtime peut contenir des commits absents de main : hypothèse à vérifier, pas une violation.",
                ("Identifier la branche d'origine du SHA runtime", "Rapprocher d'une exception #286 datée"),
                compare.evidence,
            )
        )
    ci_obs = [o for o in (repo.get(Domain.CI) if repo is not None and repo.availability in VALUE_BEARING else ())]
    ci_obs += [o for o in extra_observations if o.domain is Domain.CI]
    for obs in ci_obs:
        d = _ci_diagnostic(obs, proposal_ids)
        if d is not None:
            out.append(d)
    if host is not None and host.availability in VALUE_BEARING:
        service, storage = _first(host, Domain.HOST_SERVICE), _first(host, Domain.HOST_STORAGE)
        v = _value(service) if service is not None else {}
        if v.get("active_state") is not None:
            running = (v.get("active_state"), v.get("sub_state")) == ("active", "running")
            st = _value(storage) if storage is not None else {}
            corroboration = (
                f"Dernière modification d'un fichier de décision publiée : {st.get('latest_file_modified_at_utc')} "
                "(métadonnée, pas une preuve d'activité correcte)"
                if st.get("latest_file_modified_at_utc")
                else "Métadonnées de stockage indisponibles : activité non corroborée"
            )
            if running:
                out.append(
                    Diagnostic(
                        "diag-service",
                        DiagnosticCode.ACTIVE_NOT_HEALTH,
                        DiagnosticLevel.INFO,
                        "Service actif ≠ système sain",
                        f"systemd publie {v.get('unit')} active/running (NRestarts {v.get('restart_count')}), "
                        f"observé à {v.get('observed_at_utc', 'heure non publiée')}.",
                        "Le processus tourne. Cela ne prouve ni la production de décisions, ni la santé PAPER, ni "
                        "l'intégrité du burn-in.",
                        (corroboration, "Aucun journal, CPU/RAM ni métrique métier n'est publié : angle mort"),
                        _evidence(service.evidence, storage.evidence if storage is not None else ()),
                    )
                )
            else:
                out.append(
                    Diagnostic(
                        "diag-service",
                        DiagnosticCode.SERVICE_NOT_RUNNING,
                        DiagnosticLevel.ATTENTION,
                        "Service hors état active/running",
                        f"systemd publie {v.get('unit')} {v.get('active_state')}/{v.get('sub_state')}.",
                        "Le runtime observé n'est pas en fonctionnement nominal ; cause inconnue de Sentinel.",
                        (corroboration, "Checkpoint READ-ONLY de l'opérateur dans une mission autorisée"),
                        service.evidence,
                        "prop-f-service-state" if "prop-f-service-state" in proposal_ids else None,
                    )
                )
        fresh = [o for o in (service, storage) if o is not None and o.availability is Availability.AVAILABLE]
        if service is not None and storage is not None and len(fresh) == 1:
            other = storage if fresh[0] is service else service
            out.append(
                Diagnostic(
                    "diag-host-partial",
                    DiagnosticCode.PARTIAL_HOST_EVIDENCE,
                    DiagnosticLevel.UNKNOWN,
                    "Un seul snapshot frais",
                    f"{fresh[0].subject} : AVAILABLE ; {other.subject} : {other.availability.value} "
                    f"({other.reason or _age(other)}).",
                    "Les deux snapshots ne décrivent pas le même instant : pas de vue cohérente de l'hôte.",
                    (
                        "Relire les deux snapshots",
                        "Le snapshot storage ne publie pas host_id : rattachement à l'hôte non vérifiable",
                    ),
                    fresh[0].evidence,
                )
            )
    return out


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
