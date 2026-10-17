"""SENTINEL-01 : orchestration à invocation manuelle, bornée et READ-ONLY.

Une question → politique (refus éventuel, avant tout outil) → plan fixe dérivé de
l'intention → outils read-only de la table fixe → analyse pure → réponse
structurée → ``AgentRun`` validé par contrat. Aucun démon, aucun ordonnanceur,
aucune boucle autonome : sans question, Sentinel ne fait rien.

Chaque question ouvre le budget de lecture GitHub du fournisseur
(``begin_investigation``) ; l'état des sources porte son âge et passe à
``STALE`` au-delà de ``SOURCE_STALE_AFTER_S`` ; un échec du journal d'audit
est ajouté aux incertitudes du run, jamais ignoré.
"""

from __future__ import annotations

import dataclasses
import re
import secrets
import threading
from datetime import datetime
from typing import Any

from governance_tower.contracts import (
    VALUE_BEARING,
    AgentRun,
    Availability,
    ClaimStatus,
    EvidenceRef,
    HostSnapshot,
    Intent,
    Observation,
    PinnedReference,
    Provenance,
    Refusal,
    RepositorySnapshot,
    SentinelAnswer,
    SourceKind,
    SourceStatus,
    Statement,
    ToolCall,
    format_utc,
    parse_utc,
)
from governance_tower.providers.base import Clock, GithubReadProvider, HostObservationProvider
from governance_tower.references import load_pinned_references
from governance_tower.sentinel.analysis import analyse
from governance_tower.sentinel.audit import AuditLog, AuditUnavailable
from governance_tower.sentinel.policy import REFUSAL_REASONS, decide
from governance_tower.sentinel.reasoner import DeterministicDemoReasoner, Facts, Reasoner
from governance_tower.sentinel.tools import ToolDenied, ToolRegistry

_REPO_INTENTS = {
    Intent.EXAMINE_REPOSITORY,
    Intent.ROADMAP,
    Intent.WORK_IN_PROGRESS,
    Intent.CODE_LOCATE,
    Intent.COMPARE,
    Intent.DIAGNOSE,
    Intent.PROPOSE_MISSION,
    Intent.UNDEPLOYED_COMMITS,
    Intent.FULL_REVIEW,
}
_HOST_INTENTS = {
    Intent.EXAMINE_HOST,
    Intent.COMPARE,
    Intent.DIAGNOSE,
    Intent.PROPOSE_MISSION,
    Intent.UNDEPLOYED_COMMITS,
    Intent.FULL_REVIEW,
}
_STOPWORDS = {
    "quels", "quelles", "quel", "quelle", "sont", "dans", "code", "composants", "composant", "contrôlent",
    "controlent", "contrôle", "module", "modules", "fichier", "fichiers", "trouve", "est-ce", "pour", "avec",
    "les", "des", "une", "qui", "que", "where", "which", "what",
}
_SYNONYMS = {"publishers": "publish", "publisher": "publish", "publications": "publish"}


SOURCE_STALE_AFTER_S = 300.0
_STALE_SUFFIX = " — dernier état connu, périmé"
AUDIT_FAILURES = {
    "AUDIT_CAP_REACHED": "Journal d'audit plein (plafond atteint) : ce run n'a pas été journalisé.",
    "AUDIT_WRITE_ERROR": "Écriture du journal d'audit en échec : ce run n'a pas été journalisé.",
}


def _aged(status: SourceStatus, now: datetime) -> SourceStatus:
    """Âge mesuré du dernier état connu ; AVAILABLE trop ancien devient STALE, jamais l'inverse."""
    if status.collected_at_utc is None:
        return status
    age = max(0.0, round((now - parse_utc(status.collected_at_utc)).total_seconds(), 3))
    if status.availability is Availability.AVAILABLE and age > SOURCE_STALE_AFTER_S:
        detail = status.detail[: 300 - len(_STALE_SUFFIX)] + _STALE_SUFFIX
        return dataclasses.replace(status, availability=Availability.STALE, detail=detail, age_s=age)
    return dataclasses.replace(status, age_s=age)


class ProviderMixError(ValueError):
    """Fixtures SYNTHETIC et lectures réelles ne peuvent pas être combinées."""


def _terms(request: str) -> tuple[str, ...]:
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_-]{3,40}", request.lower())
    out: list[str] = []
    for w in words:
        w = _SYNONYMS.get(w, w)
        if w not in _STOPWORDS and w not in out:
            out.append(w)
    return tuple(out[:5])


class Sentinel:
    def __init__(
        self,
        github: GithubReadProvider,
        host: HostObservationProvider,
        clock: Clock,
        *,
        reasoner: Reasoner | None = None,
        pinned: tuple[PinnedReference, ...] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        provs = {github.info.provenance, host.info.provenance}
        lives = {github.info.live, host.info.live}
        if Provenance.SYNTHETIC in provs and True in lives:
            raise ProviderMixError("fixtures SYNTHETIC et lecture réelle refusées dans une même instance")
        self.mode = "DEMO" if Provenance.SYNTHETIC in provs or True not in lives else "LIVE_READ"
        self._github = github
        self._host = host
        self._clock = clock
        self._tools = ToolRegistry(github, host, clock)
        self._reasoner = reasoner or DeterministicDemoReasoner()
        self._pinned = (
            pinned if pinned is not None else load_pinned_references(collected_at_utc=format_utc(clock()))
        )
        self._audit = audit
        self._lock = threading.Lock()
        self._last_sources: dict[SourceKind, SourceStatus] = {}
        self.audit_state: str = "DISABLED" if audit is None else "NOT_WRITTEN"

    # ── État des sources (dernier connu, jamais inventé) ─────────────────────
    def source_status(self) -> tuple[SourceStatus, ...]:
        now = self._clock()
        out = []
        for kind, info in ((SourceKind.GITHUB, self._github.info), (SourceKind.HOST, self._host.info)):
            last = self._last_sources.get(kind)
            if last is None:
                out.append(SourceStatus(kind, Availability.UNKNOWN, None, None, f"Pas encore consulté ({info.name})."))
            else:
                out.append(_aged(last, now))
        return tuple(out)

    def prime(self) -> None:
        """Consultation initiale des sources (fixtures uniquement : aucun coût réel)."""
        if self.mode == "DEMO":
            self.ask("", shortcut="compare")

    # ── Question ─────────────────────────────────────────────────────────────
    def ask(self, question: object, shortcut: str | None = None) -> AgentRun:
        with self._lock:
            return self._ask(question, shortcut)

    def _ask(self, question: object, shortcut: str | None) -> AgentRun:
        started = format_utc(self._clock())
        decision = decide(question, shortcut)
        run_id = "run-" + secrets.token_hex(8)
        if decision.refused:
            run = self._refusal_run(run_id, decision.request, decision.refusal_code or "REFUSED", started)
            return self._record(run)

        intent = decision.intent
        begin = getattr(self._github, "begin_investigation", None)
        if callable(begin):  # budget GitHub propre à cette question (quotas distants conservés)
            begin()
        session = self._tools.session()
        failed_calls: list[ToolCall] = []
        repo: RepositorySnapshot | None = None
        host: HostSnapshot | None = None
        compare_obs: Observation | None = None
        code_obs: Observation | None = None

        def call(name: str, *args: Any) -> Any:
            t0 = format_utc(self._clock())
            try:
                return session.invoke(name, *args)
            except ToolDenied:
                raise
            except Exception as exc:  # panne de fournisseur : jamais convertie en succès
                failed_calls.append(
                    ToolCall(name, Availability.ERROR, t0, format_utc(self._clock()), type(exc).__name__[:60])
                )
                return None

        if intent in _REPO_INTENTS:
            repo = call("github.repository_snapshot")
        if intent in _HOST_INTENTS:
            host = call("host.host_snapshot")
        if intent is Intent.CODE_LOCATE:
            terms = _terms(decision.request) or ("publish",)
            code_obs = call("github.locate_code", terms)
        head = repo.head_sha if repo is not None and repo.availability in VALUE_BEARING else None
        if intent in (Intent.UNDEPLOYED_COMMITS, Intent.FULL_REVIEW, Intent.COMPARE) and head:
            base = host.deployed_source_sha if host is not None and host.deployed_source_sha else None
            if base is None and self._pinned:
                base = self._pinned[0].runtime_source_sha
            if base and base != head:
                compare_obs = call("github.compare_commits", base, head)

        analysis = analyse(repo, host, self._pinned, tuple(o for o in (compare_obs, code_obs) if o is not None))
        facts = Facts(intent, decision.request, self.mode, repo, host, self._pinned, compare_obs, code_obs, analysis)
        answer = self._reasoner.compose(facts)

        evidence: dict[str, EvidenceRef] = {}

        def collect(evs: tuple[EvidenceRef, ...]) -> None:
            for ev in evs:
                evidence.setdefault(ev.evidence_id, ev)

        for snap in (repo, host):
            if snap is not None:
                for obs in snap.observations:
                    collect(obs.evidence)
        for obs in (compare_obs, code_obs):
            if obs is not None:
                collect(obs.evidence)
        for p in self._pinned:
            collect((p.evidence,))
        for d in answer.discrepancies:
            collect(d.evidence)
        for f in answer.findings:
            collect(f.evidence)

        sources = self._sources(repo, host, intent)
        run = AgentRun(
            run_id=run_id,
            request=decision.request,
            intent=intent,
            started_at_utc=started,
            finished_at_utc=format_utc(self._clock()),
            tool_calls=tuple(session.calls) + tuple(failed_calls),
            evidence=tuple(evidence.values()),
            sources=sources,
            answer=answer,
            reasoner=self._reasoner.name,
            mode=self.mode,
        )
        return self._record(run)

    def _sources(self, repo: RepositorySnapshot | None, host: HostSnapshot | None, intent: Intent) -> tuple[SourceStatus, ...]:
        if repo is not None:
            self._last_sources[SourceKind.GITHUB] = SourceStatus(
                SourceKind.GITHUB,
                repo.availability,
                self._github.info.provenance,
                repo.collected_at_utc,
                f"{repo.repo} — HEAD {repo.head_sha[:12] if repo.head_sha else 'inconnu'}",
            )
        elif intent in _REPO_INTENTS:
            self._last_sources[SourceKind.GITHUB] = SourceStatus(
                SourceKind.GITHUB, Availability.ERROR, None, None, "Lecture GitHub en erreur."
            )
        if host is not None:
            self._last_sources[SourceKind.HOST] = SourceStatus(
                SourceKind.HOST,
                host.availability,
                self._host.info.provenance if host.availability in VALUE_BEARING else None,
                host.collected_at_utc,
                f"{host.host_label} — " + (
                    f"runtime {host.deployed_source_sha[:12]}" if host.deployed_source_sha else (host.reason or "SHA déployé inconnu")
                ),
            )
        elif intent in _HOST_INTENTS:
            self._last_sources[SourceKind.HOST] = SourceStatus(
                SourceKind.HOST, Availability.ERROR, None, None, "Lecture hôte en erreur."
            )
        return self.source_status()

    def _refusal_run(self, run_id: str, request: str, code: str, started: str) -> AgentRun:
        reason = REFUSAL_REASONS.get(code, "Demande hors du périmètre READ-ONLY de Sentinel.")
        answer = SentinelAnswer(
            summary=f"Demande refusée ({code}). Aucun outil n'a été appelé, rien n'a été modifié.",
            statements=(
                Statement(
                    "Je peux en revanche observer, comparer et proposer une mission documentée, "
                    "qui restera non exécutée et soumise à ta décision (#286, #315).",
                    ClaimStatus.PROPOSED,
                ),
            ),
            uncertainties=(),
            refusals=(Refusal(code, reason, request[:300]),),
        )
        return AgentRun(
            run_id=run_id,
            request=request,
            intent=Intent.REFUSED,
            started_at_utc=started,
            finished_at_utc=format_utc(self._clock()),
            tool_calls=(),
            evidence=(),
            sources=self.source_status(),
            answer=answer,
            reasoner=self._reasoner.name,
            mode=self.mode,
        )

    def _record(self, run: AgentRun) -> AgentRun:
        """Journalise le run ; un échec d'audit devient une incertitude visible, jamais un succès."""
        if self._audit is None:
            return run
        try:
            code = "OK" if self._audit.append(run) else "AUDIT_CAP_REACHED"
        except (OSError, AuditUnavailable):
            code = "AUDIT_WRITE_ERROR"
        self.audit_state = code
        if code == "OK":
            return run
        answer = dataclasses.replace(run.answer, uncertainties=run.answer.uncertainties + (AUDIT_FAILURES[code],))
        return dataclasses.replace(run, answer=answer)


__all__ = ["ProviderMixError", "Sentinel"]
