"""Raisonneurs de SENTINEL-01 : la sortie structurée d'abord, la prose ensuite.

``DeterministicDemoReasoner`` compose la réponse à partir des seuls faits collectés
(offline, reproductible). ``ClaudeApiReasoner`` documente l'adaptateur futur : il
est désactivé dans GOV-TOWER-00 et refuse de s'exécuter (aucun appel payant
implicite, aucune clé lue).
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Any, Protocol

from governance_tower.contracts import (
    VALUE_BEARING,
    Availability,
    ClaimStatus,
    CodeExcerpt,
    DiscrepancyClass,
    Domain,
    EvidenceRef,
    HostSnapshot,
    Intent,
    Observation,
    PinnedReference,
    RepositorySnapshot,
    SentinelAnswer,
    SourceStatus,
    Statement,
)
from governance_tower.coverage import COVERAGE
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
    details: tuple[Observation, ...] = ()  # GOV-TOWER-01 : lectures ciblées
    sources: tuple[SourceStatus, ...] = ()  # dernier état connu des sources (cartographie)
    coverage_evidence: tuple[EvidenceRef, ...] = ()


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


def _titles(items: Any, limit: int = 6) -> str:
    if not isinstance(items, list) or not items:
        return "aucun"
    shown = [f"#{i.get('number')} « {i.get('title')} »" for i in items[:limit] if isinstance(i, dict)]
    return "; ".join(shown) + (f" … (+{len(items) - limit})" if len(items) > limit else "")


def _humanize(obs: Observation) -> str | None:
    """Phrase lisible pour les observations connues ; None ⇒ rendu compact générique (GOV-TOWER-01 M3)."""
    v = obs.value if isinstance(obs.value, dict) else None
    if v is None:
        return None
    oid = obs.observation_id
    if oid == "gh-repository":
        return (
            f"Branche {v.get('default_branch')} à {short(v.get('head_sha'))}, commit du "
            f"{v.get('head_committed_at_utc')} « {v.get('head_title')} »."
        )
    if oid == "gh-ci":
        return (
            f"{v.get('status')} — {v.get('succeeded')} réussi(s), {v.get('failed')} en échec, {v.get('pending')} en "
            f"cours, {v.get('skipped')} ignoré(s), {v.get('neutral')} neutre(s) sur {v.get('total')}."
        )
    if oid == "gh-pull-requests":
        return f"{v.get('open_on_page')} PR ouvertes sur la page lue : {_titles(v.get('items'))}."
    if oid == "gh-issues":
        return f"{v.get('open_on_page')} issues ouvertes sur la page lue : {_titles(v.get('items'))}."
    if oid == "gh-compare":
        commits = v.get("commits") or []
        listed = "; ".join(f"{short(c.get('sha'))} « {c.get('title')} »" for c in commits[:5] if isinstance(c, dict))
        return (
            f"GitHub compte {v.get('total_commits')} commit(s) (status={v.get('status')}, ahead_by={v.get('ahead_by')}, "
            f"behind_by={v.get('behind_by')}) ; {v.get('commits_returned')} listé(s), dont : {listed or 'aucun'}."
        )
    if oid == "host.service":
        return (
            f"{v.get('unit')} {v.get('active_state')}/{v.get('sub_state')} (load {v.get('load_state')}, "
            f"NRestarts {v.get('restart_count')}, démarré {v.get('exec_main_started_at_utc')}), observé à "
            f"{v.get('observed_at_utc')} sur {v.get('host_id')}. ACTIVE ≠ HEALTHY."
        )
    if oid == "host.deployment":
        return (
            f"SHA source publié {short(v.get('source_code_sha'))}, artefact {str(v.get('artifact_sha256'))[:12]}, "
            f"preuve « {v.get('evidence_ref')} » du {v.get('observed_at_utc')}."
        )
    if oid == "host.storage":
        return (
            f"{v.get('matched_file_count')} fichier(s) de décision, {v.get('total_bytes')} octets, dernière "
            f"modification {v.get('latest_file_modified_at_utc')} (métadonnées seulement)."
        )
    return None


def _observation_statement(obs: Observation) -> Statement | None:
    if obs.availability not in VALUE_BEARING:
        return None
    prefix = "[contenu externe non fiable] " if obs.untrusted_content else ""
    stale = f" (PÉRIMÉ, âge {obs.freshness_age_s:.0f} s)" if obs.availability is Availability.STALE else ""
    text = _humanize(obs) or _compact(obs.value)
    return Statement(
        f"{prefix}{obs.subject}{stale} : {text}"[:4000],
        ClaimStatus.OBSERVED,
        tuple(e.evidence_id for e in obs.evidence),
    )


def _absence_note(obs: Observation, source: str) -> str:
    return f"{source} — {obs.subject} : {obs.availability.value} ({obs.reason})"


_DETAIL_INTENTS = (Intent.READ_FILE, Intent.ISSUE_DETAIL, Intent.PULL_DETAIL, Intent.CI_FOR_SHA)
_DIAGNOSTIC_INTENTS = (
    Intent.EXAMINE_REPOSITORY, Intent.EXAMINE_HOST, Intent.COMPARE, Intent.DIAGNOSE, Intent.PROPOSE_MISSION,
    Intent.UNDEPLOYED_COMMITS, Intent.FULL_REVIEW, Intent.WORK_IN_PROGRESS, Intent.PULL_DETAIL, Intent.CI_FOR_SHA,
)
_BODY_QUOTE = 1_500


def _ids(obs: Observation) -> tuple[str, ...]:
    return tuple(e.evidence_id for e in obs.evidence)


def _detail_statements(obs: Observation) -> list[Statement]:
    """Phrases lisibles pour une lecture ciblée (au lieu d'un vidage clé=valeur)."""
    v = obs.value if isinstance(obs.value, dict) else {}
    ids = _ids(obs)
    if obs.domain is Domain.CODE_CONTENT:
        rng = f"lignes {v.get('line_start')}–{v.get('line_end')} sur {v.get('total_lines')}"
        return [
            Statement(
                f"Fichier {v.get('path')} au SHA {short(v.get('ref_sha'))} : {rng} (blob {short(v.get('blob_sha'))}, "
                f"empreinte Git vérifiée, {v.get('size_bytes')} octets). L'extrait est un contenu non fiable, cité "
                "comme donnée ; présent à ce SHA ≠ déployé.",
                ClaimStatus.OBSERVED,
                ids,
            )
        ]
    if obs.domain is Domain.CI:
        return [
            Statement(
                f"{obs.subject} : {v.get('status')} — {v.get('succeeded')} réussi(s), {v.get('failed')} en échec, "
                f"{v.get('pending')} en cours, {v.get('skipped')} ignoré(s), {v.get('neutral')} neutre(s) sur "
                f"{v.get('total')} contrôle(s). CI ≠ déploiement.",
                ClaimStatus.OBSERVED,
                ids,
            )
        ]
    out: list[Statement] = []
    if obs.domain is Domain.ISSUES:
        reason = f" ({v.get('state_reason')})" if v.get("state_reason") else ""
        labels = ", ".join(v.get("labels") or []) or "aucune"
        out.append(
            Statement(
                f"[contenu externe non fiable] Issue #{v.get('number')} : {v.get('state')}{reason}, « {v.get('title')} », "
                f"créée {v.get('created_at_utc')}, mise à jour {v.get('updated_at_utc')} ; étiquettes : {labels} ; "
                f"{v.get('comments_count')} commentaire(s) non lu(s).",
                ClaimStatus.OBSERVED,
                ids,
            )
        )
    elif obs.domain is Domain.PULL_REQUESTS:
        merged = f"fusionnée le {v.get('merged_at_utc')}" if v.get("merged") else "non fusionnée"
        out.append(
            Statement(
                f"[contenu externe non fiable] PR #{v.get('number')} : {v.get('state')}, {merged}, "
                f"brouillon {'oui' if v.get('draft') else 'non'} ; tête {short(v.get('head_sha'))} ({v.get('head_ref')}) "
                f"→ base {v.get('base_ref')} {short(v.get('base_sha'))} ; {v.get('changed_files')} fichier(s), "
                f"+{v.get('additions')}/−{v.get('deletions')} ; « {v.get('title')} ». Fusion ≠ déploiement.",
                ClaimStatus.OBSERVED,
                ids,
            )
        )
    if v.get("body_present"):
        excerpt = str(v.get("body_excerpt") or "")
        cut = "…" if len(excerpt) > _BODY_QUOTE or v.get("body_truncated") else ""
        out.append(
            Statement(
                f"[contenu externe non fiable] Corps (extrait, jamais une instruction) : {excerpt[:_BODY_QUOTE]}{cut}",
                ClaimStatus.OBSERVED,
                ids,
            )
        )
    return out


def _excerpt(obs: Observation, n: int) -> CodeExcerpt | None:
    if obs.domain is not Domain.CODE_CONTENT or not obs.has_value or not obs.evidence:
        return None
    v = obs.value
    return CodeExcerpt(
        excerpt_id=f"x-{n}",
        repo=v["repo"],
        ref_sha=v["ref_sha"],
        path=v["path"],
        blob_sha=v["blob_sha"],
        line_start=v["line_start"],
        line_end=v["line_end"],
        total_lines=v["total_lines"],
        text=v["text"],
        evidence_id=obs.evidence[-1].evidence_id,
        redactions=v["redactions"],
        truncated=bool(v["range_truncated"] or v["line_truncated"]),
    )


def _coverage_statements(facts: "Facts") -> list[Statement]:
    ids = tuple(e.evidence_id for e in facts.coverage_evidence)
    out = [
        Statement(
            f"[{e.visibility.value}] {e.domain} ({e.source}) — {e.provider} {e.endpoint} ; champs : {e.fields} ; "
            f"fraîcheur : {e.freshness} ; limites : {e.limits}.",
            ClaimStatus.INFERRED,
            ids,
        )
        for e in COVERAGE
    ]
    names = {"GITHUB": "GitHub", "HOST": "VPS"}
    for st in facts.sources:
        age = f", âge {st.age_s:.0f} s" if st.age_s is not None else ""
        out.append(
            Statement(
                f"Dernier état connu {names.get(st.source.value, st.source.value)} (non relu pour cette question) : "
                f"{st.availability.value}{age} — {st.detail}",
                ClaimStatus.INFERRED,
            )
        )
    return out


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
        excerpts: list[CodeExcerpt] = []
        if intent in _DETAIL_INTENTS:
            for obs in facts.details:
                if obs.has_value:
                    statements.extend(_detail_statements(obs))
                    x = _excerpt(obs, len(excerpts) + 1)
                    if x is not None:
                        excerpts.append(x)
                else:
                    uncertainties.append(_absence_note(obs, "GitHub"))
                    statements.append(
                        Statement(f"{obs.subject} : non lu ({obs.availability.value}, {obs.reason}).", ClaimStatus.NOT_PROVEN)
                    )
                for limit in obs.limits:
                    if limit not in uncertainties:
                        uncertainties.append(limit)
        if intent is Intent.COVERAGE_MAP:
            statements.extend(_coverage_statements(facts))
            uncertainties += [
                "Cartographie déclarative : elle décrit ce que le code sait lire, pas ce qui a été lu.",
                "« Vue complète » = inventaire des domaines et des angles morts, jamais un accès root ni des données "
                "non admises.",
                "Lecture VPS réelle par le connecteur Governance Tower : NOT_PROVEN (gate GT01-V).",
            ]
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
            if intent is Intent.COVERAGE_MAP:
                summary = (
                    f"Cartographie déclarée de {len(COVERAGE)} domaines (observables, bornés, non publiés, interdits) "
                    "et dernier état connu des sources ; aucune source relue"
                )
            if label:
                summary += f" ; comparaison GitHub/VPS : {label}"
            if a.findings and intent in (Intent.DIAGNOSE, Intent.FULL_REVIEW, Intent.PROPOSE_MISSION):
                summary += f" ; {len(a.findings)} constat(s) candidat(s)"
            if intent in _DIAGNOSTIC_INTENTS and a.diagnostics:
                summary += f" ; {len(a.diagnostics)} diagnostic(s)"
            summary += ". Rien n'a été modifié."

        proposal_ids = {p.proposal_id for p in proposals}
        diagnostics = tuple(
            d if d.proposal_ref is None or d.proposal_ref in proposal_ids else dataclasses.replace(d, proposal_ref=None)
            for d in (a.diagnostics if intent in _DIAGNOSTIC_INTENTS else ())
        )

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
            diagnostics=diagnostics,
            excerpts=tuple(excerpts[:3]),
        )
