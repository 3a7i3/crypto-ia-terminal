"""Contrats fermés de Governance Tower (GOV-TOWER-00, lot B).

Noyau typé, déterministe et sans effet de bord. Règles :

- vocabulaires fermés (``Enum``) ; aucun booléen ne remplace un état qualifié ;
- ``UNKNOWN``/``NOT_AVAILABLE``/``DENIED``/``RATE_LIMITED``/``ERROR`` ne portent
  jamais de valeur : une absence n'est jamais convertie en zéro ou en liste vide ;
- dates UTC explicites ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z`` ; une observation
  datée dans le futur est refusée ;
- chaînes et listes bornées ; champs inconnus refusés au chargement ;
- une affirmation ``OBSERVED`` cite au moins une preuve présente dans le run ;
- un run ne mélange jamais des preuves ``SYNTHETIC`` et ``LIVE_READ``.

Le vocabulaire d'absence reprend celui de ``observability/operator/contracts.py``
(UNKNOWN ≠ 0, STALE ≠ CURRENT) sans l'importer : Governance Tower ne dépend
pas du cycle de vie de l'Operator App.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import MISSING, dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = "gt-contracts/1"

MAX_SHORT = 300
MAX_TEXT = 4_000
MAX_ITEMS = 200
MAX_VALUE_BYTES = 64 * 1024
#: Tolérance d'horloge entre la collecte et l'horodatage observé.
CLOCK_SKEW_S = 120.0

_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ContractError(ValueError):
    """Une valeur viole un contrat : refus explicite, jamais de correction silencieuse."""


# ── Vocabulaires fermés ──────────────────────────────────────────────────────


class Availability(str, Enum):
    """État d'une source ou d'une observation. Seuls AVAILABLE et STALE portent une valeur."""

    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    DENIED = "DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


VALUE_BEARING = frozenset({Availability.AVAILABLE, Availability.STALE})


class Provenance(str, Enum):
    SYNTHETIC = "SYNTHETIC"  # fixture de démonstration, jamais une preuve VPS/GitHub
    LIVE_READ = "LIVE_READ"  # lecture réelle opt-in
    DECLARED_REFERENCE = "DECLARED_REFERENCE"  # référence documentaire (ex. #286)


class SourceKind(str, Enum):
    GITHUB = "GITHUB"
    HOST = "HOST"
    DECLARED_REFERENCE = "DECLARED_REFERENCE"


class ClaimStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    PROPOSED = "PROPOSED"
    NOT_PROVEN = "NOT_PROVEN"


class DiscrepancyClass(str, Enum):
    ALIGNED = "ALIGNED"
    EXPECTED_PINNED_RUNTIME = "EXPECTED_PINNED_RUNTIME"
    POSSIBLE_DRIFT = "POSSIBLE_DRIFT"
    STALE = "STALE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    VIOLATION_PROVEN = "VIOLATION_PROVEN"


class Severity(str, Enum):
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Domain(str, Enum):
    REPOSITORY = "repository"
    CI = "ci"
    PULL_REQUESTS = "pull_requests"
    ISSUES = "issues"
    CODE = "code"
    HOST_SERVICE = "host_service"
    HOST_STORAGE = "host_storage"
    HOST_DEPLOYMENT = "host_deployment"
    REFERENCE = "reference"


class Intent(str, Enum):
    EXAMINE_REPOSITORY = "EXAMINE_REPOSITORY"
    EXAMINE_HOST = "EXAMINE_HOST"
    COMPARE = "COMPARE"
    DIAGNOSE = "DIAGNOSE"
    PROPOSE_MISSION = "PROPOSE_MISSION"
    ROADMAP = "ROADMAP"
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    CODE_LOCATE = "CODE_LOCATE"
    UNDEPLOYED_COMMITS = "UNDEPLOYED_COMMITS"
    FULL_REVIEW = "FULL_REVIEW"
    HELP = "HELP"
    REFUSED = "REFUSED"


# ── Utilitaires purs ─────────────────────────────────────────────────────────


def parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not _UTC_RE.match(value):
        raise ContractError(f"horodatage UTC invalide: {value!r}"[:MAX_SHORT])
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ContractError("horodatage UTC invalide") from exc


def format_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ContractError("datetime naïf refusé : UTC explicite requis")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_sha1(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA1_RE.match(value))


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


def check_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ContractError(f"{name}: identifiant invalide")
    return value


def check_text(value: Any, name: str, limit: int = MAX_TEXT, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name}: texte attendu")
    if not allow_empty and not value.strip():
        raise ContractError(f"{name}: texte vide")
    if len(value) > limit:
        raise ContractError(f"{name}: texte trop long ({len(value)} > {limit})")
    if _CONTROL_RE.search(value):
        raise ContractError(f"{name}: caractère de contrôle refusé")
    return value


def check_items(values: Any, name: str, limit: int = MAX_ITEMS) -> tuple:
    if not isinstance(values, tuple):
        raise ContractError(f"{name}: tuple attendu")
    if len(values) > limit:
        raise ContractError(f"{name}: trop d'éléments ({len(values)} > {limit})")
    return values


def check_json_value(value: Any, name: str) -> Any:
    """Valeur JSON finie et bornée ; aucun NaN/Infinity, aucun objet arbitraire."""

    def walk(v: Any, depth: int) -> None:
        if depth > 8:
            raise ContractError(f"{name}: valeur trop profonde")
        if v is None or isinstance(v, (bool, str)):
            return
        if isinstance(v, int):
            return
        if isinstance(v, float):
            if not math.isfinite(v):
                raise ContractError(f"{name}: nombre non fini refusé")
            return
        if isinstance(v, (list, tuple)):
            for item in v:
                walk(item, depth + 1)
            return
        if isinstance(v, dict):
            for k, item in v.items():
                if not isinstance(k, str):
                    raise ContractError(f"{name}: clé non textuelle")
                walk(item, depth + 1)
            return
        raise ContractError(f"{name}: type non sérialisable {type(v).__name__}")

    walk(value, 0)
    if len(json.dumps(value, sort_keys=True, default=list)) > MAX_VALUE_BYTES:
        raise ContractError(f"{name}: valeur trop volumineuse")
    return value


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in sorted(value.items())}
    return value


def _strict_keys(raw: Any, cls: type, name: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractError(f"{name}: objet attendu")
    expected = {f.name for f in fields(cls)}
    unknown = set(raw) - expected
    if unknown:
        raise ContractError(f"{name}: champs inconnus refusés {sorted(unknown)}")
    missing = {
        f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING
    } - set(raw)
    if missing:
        raise ContractError(f"{name}: champs manquants {sorted(missing)}")
    return raw


# ── Preuves et observations ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceRef:
    """Référence de preuve non sensible : où, quand, d'après quelle source."""

    evidence_id: str
    source: SourceKind
    locator: str  # URL GitHub publique, ``snapshot:<nom>`` ou ``reference:<nom>``
    provenance: Provenance
    collected_at_utc: str
    observed_at_utc: str | None = None
    source_sha: str | None = None
    content_sha256: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        check_id(self.evidence_id, "evidence_id")
        if not isinstance(self.source, SourceKind) or not isinstance(self.provenance, Provenance):
            raise ContractError("EvidenceRef: source/provenance hors vocabulaire")
        check_text(self.locator, "locator", MAX_SHORT)
        if not (
            self.locator.startswith("https://github.com/")
            or self.locator.startswith("https://api.github.com/")
            or self.locator.startswith("snapshot:")
            or self.locator.startswith("reference:")
            or self.locator.startswith("fixture:")
        ):
            raise ContractError("locator: schéma non admis")
        collected = parse_utc(self.collected_at_utc)
        if self.observed_at_utc is not None:
            observed = parse_utc(self.observed_at_utc)
            if (observed - collected).total_seconds() > CLOCK_SKEW_S:
                raise ContractError("observed_at_utc postérieur à la collecte (horodatage futur)")
        if self.source_sha is not None and not is_sha1(self.source_sha):
            raise ContractError("source_sha: SHA-1 hexadécimal de 40 caractères attendu")
        if self.content_sha256 is not None and not is_sha256(self.content_sha256):
            raise ContractError("content_sha256: SHA-256 hexadécimal attendu")
        if self.note is not None:
            check_text(self.note, "note", MAX_SHORT)
        if self.provenance is Provenance.SYNTHETIC and not self.locator.startswith("fixture:"):
            raise ContractError("une preuve SYNTHETIC doit avoir un locator fixture:")
        if self.provenance is not Provenance.SYNTHETIC and self.locator.startswith("fixture:"):
            raise ContractError("un locator fixture: ne peut pas être une preuve réelle")

    @classmethod
    def from_dict(cls, raw: Any) -> "EvidenceRef":
        data = dict(_strict_keys(raw, cls, "EvidenceRef"))
        data["source"] = SourceKind(data["source"])
        data["provenance"] = Provenance(data["provenance"])
        return cls(**data)


@dataclass(frozen=True)
class Observation:
    """Une mesure qualifiée : valeur seulement si la source a réellement répondu."""

    observation_id: str
    domain: Domain
    subject: str
    availability: Availability
    value: Any
    reason: str | None
    evidence: tuple[EvidenceRef, ...]
    limits: tuple[str, ...] = ()
    untrusted_content: bool = False
    freshness_age_s: float | None = None

    def __post_init__(self) -> None:
        check_id(self.observation_id, "observation_id")
        if not isinstance(self.domain, Domain) or not isinstance(self.availability, Availability):
            raise ContractError("Observation: domaine/disponibilité hors vocabulaire")
        check_text(self.subject, "subject", MAX_SHORT)
        check_items(self.evidence, "evidence")
        for ev in self.evidence:
            if not isinstance(ev, EvidenceRef):
                raise ContractError("Observation.evidence: EvidenceRef attendu")
        for limit in check_items(self.limits, "limits"):
            check_text(limit, "limit", MAX_SHORT)
        if self.availability in VALUE_BEARING:
            check_json_value(self.value, "value")
            if not self.evidence:
                raise ContractError("une observation disponible doit citer une preuve")
        else:
            if self.value is not None:
                raise ContractError(
                    f"{self.availability.value}: aucune valeur autorisée (UNKNOWN ≠ 0)"
                )
            if not self.reason:
                raise ContractError("une absence doit porter une raison explicite")
        if self.reason is not None:
            check_text(self.reason, "reason", MAX_SHORT)
        if self.availability is Availability.STALE and self.freshness_age_s is None:
            raise ContractError("STALE exige l'âge mesuré de la donnée")
        if self.freshness_age_s is not None:
            if isinstance(self.freshness_age_s, bool) or not isinstance(self.freshness_age_s, (int, float)):
                raise ContractError("freshness_age_s: nombre attendu")
            if not math.isfinite(self.freshness_age_s) or self.freshness_age_s < 0:
                raise ContractError("freshness_age_s: nombre fini positif attendu")
        if not isinstance(self.untrusted_content, bool):
            raise ContractError("untrusted_content: booléen attendu")

    @property
    def has_value(self) -> bool:
        return self.availability in VALUE_BEARING

    @classmethod
    def absent(
        cls,
        observation_id: str,
        domain: Domain,
        subject: str,
        availability: Availability,
        reason: str,
        evidence: tuple[EvidenceRef, ...] = (),
        limits: tuple[str, ...] = (),
    ) -> "Observation":
        if availability in VALUE_BEARING:
            raise ContractError("absent() exige une disponibilité sans valeur")
        return cls(observation_id, domain, subject, availability, None, reason, evidence, limits)

    @classmethod
    def from_dict(cls, raw: Any) -> "Observation":
        data = dict(_strict_keys(raw, cls, "Observation"))
        data["domain"] = Domain(data["domain"])
        data["availability"] = Availability(data["availability"])
        data["evidence"] = tuple(EvidenceRef.from_dict(e) for e in data.get("evidence", ()))
        data["limits"] = tuple(data.get("limits", ()))
        return cls(**data)


def _provenances(observations: tuple[Observation, ...]) -> set[Provenance]:
    return {ev.provenance for obs in observations for ev in obs.evidence}


def check_no_mixed_provenance(provenances: set[Provenance], name: str) -> None:
    if Provenance.SYNTHETIC in provenances and Provenance.LIVE_READ in provenances:
        raise ContractError(f"{name}: données SYNTHETIC mélangées à des lectures réelles")


@dataclass(frozen=True)
class RepositorySnapshot:
    repo: str
    collected_at_utc: str
    availability: Availability
    observations: tuple[Observation, ...]
    default_branch: str | None = None
    head_sha: str | None = None

    def __post_init__(self) -> None:
        check_text(self.repo, "repo", 100)
        parse_utc(self.collected_at_utc)
        check_items(self.observations, "observations")
        if self.head_sha is not None and not is_sha1(self.head_sha):
            raise ContractError("head_sha: SHA-1 attendu")
        if self.availability not in VALUE_BEARING and self.head_sha is not None:
            raise ContractError("dépôt indisponible : head_sha doit rester inconnu")
        check_no_mixed_provenance(_provenances(self.observations), "RepositorySnapshot")

    def get(self, domain: Domain) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.domain is domain)


@dataclass(frozen=True)
class HostSnapshot:
    host_label: str  # anonymisable ; jamais une adresse IP ni un secret
    collected_at_utc: str
    availability: Availability
    observations: tuple[Observation, ...]
    deployed_source_sha: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        check_text(self.host_label, "host_label", 100)
        parse_utc(self.collected_at_utc)
        check_items(self.observations, "observations")
        if self.deployed_source_sha is not None and not is_sha1(self.deployed_source_sha):
            raise ContractError("deployed_source_sha: SHA-1 attendu")
        if self.availability not in VALUE_BEARING:
            if self.deployed_source_sha is not None:
                raise ContractError("hôte indisponible : aucun SHA déployé ne peut être affirmé")
            if not self.reason:
                raise ContractError("hôte indisponible : raison explicite requise")
        check_no_mixed_provenance(_provenances(self.observations), "HostSnapshot")

    def get(self, domain: Domain) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.domain is domain)


@dataclass(frozen=True)
class PinnedReference:
    """Référence gelée déclarée sous #286 : documentaire, jamais observée par Sentinel."""

    reference_id: str
    epoch_id: str
    runtime_source_sha: str
    config_sha256: str
    declared_in: str
    status_date: str
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        check_id(self.reference_id, "reference_id")
        check_id(self.epoch_id, "epoch_id")
        if not is_sha1(self.runtime_source_sha) or not is_sha256(self.config_sha256):
            raise ContractError("référence gelée : empreintes invalides")
        check_text(self.declared_in, "declared_in", MAX_SHORT)
        check_text(self.status_date, "status_date", 40)
        if self.evidence.provenance is not Provenance.DECLARED_REFERENCE:
            raise ContractError("une référence gelée est une preuve DECLARED_REFERENCE")


@dataclass(frozen=True)
class Discrepancy:
    discrepancy_id: str
    subject: str
    classification: DiscrepancyClass
    expectation: str
    explanation: str
    evidence: tuple[EvidenceRef, ...]
    github_value: str | None = None
    host_value: str | None = None

    def __post_init__(self) -> None:
        check_id(self.discrepancy_id, "discrepancy_id")
        check_text(self.subject, "subject", MAX_SHORT)
        check_text(self.expectation, "expectation", MAX_SHORT * 2)
        check_text(self.explanation, "explanation")
        check_items(self.evidence, "evidence")
        if not isinstance(self.classification, DiscrepancyClass):
            raise ContractError("classification hors vocabulaire")
        proving = {
            DiscrepancyClass.ALIGNED,
            DiscrepancyClass.EXPECTED_PINNED_RUNTIME,
            DiscrepancyClass.POSSIBLE_DRIFT,
            DiscrepancyClass.VIOLATION_PROVEN,
        }
        if self.classification in proving and (self.github_value is None or self.host_value is None):
            raise ContractError(
                f"{self.classification.value} exige les deux faits comparés ; sinon INSUFFICIENT_EVIDENCE"
            )
        if self.classification in proving and not self.evidence:
            raise ContractError("une comparaison conclusive doit citer ses preuves")


@dataclass(frozen=True)
class Finding:
    finding_id: str
    title: str
    severity: Severity
    severity_reason: str
    claim_status: ClaimStatus
    evidence: tuple[EvidenceRef, ...]
    impact: str
    hypothesis: str | None = None
    suggestion: str | None = None
    status: str = "CANDIDATE_ONLY"

    def __post_init__(self) -> None:
        check_id(self.finding_id, "finding_id")
        check_text(self.title, "title", MAX_SHORT)
        check_text(self.severity_reason, "severity_reason", MAX_SHORT * 2)
        check_text(self.impact, "impact", MAX_SHORT * 2)
        check_items(self.evidence, "evidence")
        if self.status != "CANDIDATE_ONLY":
            raise ContractError("un Finding reste CANDIDATE_ONLY : aucune autorité")
        if not isinstance(self.severity, Severity) or not isinstance(self.claim_status, ClaimStatus):
            raise ContractError("Finding: vocabulaire")
        if self.claim_status is ClaimStatus.OBSERVED and not self.evidence:
            raise ContractError("un constat OBSERVED doit citer une preuve")


DEFAULT_FORBIDDEN_SCOPE = (
    "Aucun restart/deploy Advisor, API ou web",
    "Aucune modification du checkout runtime gelé, de l'epoch, de la config ou du capital",
    "Aucune mutation PPL/FIN, stratégie, signal, risk ou sizing",
    "Aucun accès secret, .env, clé exchange ; aucun TESTNET/LIVE",
    "Aucun merge, aucune PR ou écriture GitHub autonome",
    "Aucune levée de #286 ni décision Gate O #315",
)


@dataclass(frozen=True)
class MissionProposal:
    """Proposition documentée ; jamais approuvée ni exécutée par Sentinel."""

    proposal_id: str
    title: str
    problem_ref: str
    description: str
    allowed_scope: tuple[str, ...]
    required_evidence: tuple[str, ...]
    tests: tuple[str, ...]
    forbidden_scope: tuple[str, ...] = DEFAULT_FORBIDDEN_SCOPE
    authority: str = "NONE"
    execution: str = "NOT_EXECUTED"
    approval_path: str = "Décision opérateur explicite ; gate #286/#315 selon le périmètre"

    def __post_init__(self) -> None:
        check_id(self.proposal_id, "proposal_id")
        check_text(self.title, "title", MAX_SHORT)
        check_id(self.problem_ref, "problem_ref")
        check_text(self.description, "description")
        for name in ("allowed_scope", "required_evidence", "tests", "forbidden_scope"):
            for item in check_items(getattr(self, name), name, 30):
                check_text(item, name, MAX_SHORT)
        if self.authority != "NONE" or self.execution != "NOT_EXECUTED":
            raise ContractError("une proposition n'a ni autorité ni exécution")
        missing = set(DEFAULT_FORBIDDEN_SCOPE) - set(self.forbidden_scope)
        if missing:
            raise ContractError("le périmètre interdit par défaut ne peut pas être retiré")


@dataclass(frozen=True)
class Statement:
    text: str
    claim_status: ClaimStatus
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        check_text(self.text, "statement", MAX_TEXT)
        if not isinstance(self.claim_status, ClaimStatus):
            raise ContractError("Statement: vocabulaire")
        for ev in check_items(self.evidence_ids, "evidence_ids", 50):
            check_id(ev, "evidence_id")
        if self.claim_status is ClaimStatus.OBSERVED and not self.evidence_ids:
            raise ContractError("constat OBSERVED sans preuve refusé")


@dataclass(frozen=True)
class Refusal:
    code: str
    reason: str
    quoted_request: str | None = None

    def __post_init__(self) -> None:
        check_id(self.code, "refusal.code")
        check_text(self.reason, "refusal.reason", MAX_SHORT * 2)
        if self.quoted_request is not None:
            check_text(self.quoted_request, "quoted_request", MAX_SHORT * 2, allow_empty=True)


@dataclass(frozen=True)
class SourceStatus:
    source: SourceKind
    availability: Availability
    provenance: Provenance | None
    collected_at_utc: str | None
    detail: str
    age_s: float | None = None  # âge de la dernière consultation au moment du statut

    def __post_init__(self) -> None:
        check_text(self.detail, "detail", MAX_SHORT)
        if self.collected_at_utc is not None:
            parse_utc(self.collected_at_utc)
        if self.age_s is not None:
            if isinstance(self.age_s, bool) or not isinstance(self.age_s, (int, float)):
                raise ContractError("age_s : nombre attendu")
            if not math.isfinite(self.age_s) or self.age_s < 0:
                raise ContractError("age_s : nombre fini positif attendu")
            if self.collected_at_utc is None:
                raise ContractError("age_s sans collected_at_utc : âge non mesurable")


@dataclass(frozen=True)
class SentinelAnswer:
    """Sortie structurée ; la prose de l'interface est dérivée, jamais l'inverse."""

    summary: str
    statements: tuple[Statement, ...]
    uncertainties: tuple[str, ...]
    discrepancies: tuple[Discrepancy, ...] = ()
    findings: tuple[Finding, ...] = ()
    proposals: tuple[MissionProposal, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    untrusted_quotes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        check_text(self.summary, "summary", MAX_SHORT * 2)
        for name in (
            "statements",
            "uncertainties",
            "discrepancies",
            "findings",
            "proposals",
            "refusals",
            "untrusted_quotes",
        ):
            check_items(getattr(self, name), name)
        for u in self.uncertainties:
            check_text(u, "uncertainty", MAX_SHORT * 2)
        for q in self.untrusted_quotes:
            check_text(q, "untrusted_quote", MAX_SHORT * 2, allow_empty=True)


@dataclass(frozen=True)
class ToolCall:
    tool: str
    availability: Availability
    started_at_utc: str
    finished_at_utc: str
    detail: str = ""

    def __post_init__(self) -> None:
        check_id(self.tool, "tool")
        if parse_utc(self.finished_at_utc) < parse_utc(self.started_at_utc):
            raise ContractError("ToolCall: fin avant début")
        check_text(self.detail, "detail", MAX_SHORT, allow_empty=True)


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    request: str
    intent: Intent
    started_at_utc: str
    finished_at_utc: str
    tool_calls: tuple[ToolCall, ...]
    evidence: tuple[EvidenceRef, ...]
    sources: tuple[SourceStatus, ...]
    answer: SentinelAnswer
    reasoner: str
    mode: str  # DEMO | LIVE_READ
    agent_id: str = "SENTINEL-01"
    capability: str = "OBSERVE_ONLY"
    operational_authority: str = "DENIED"
    cost: str | None = None  # jamais inventé ; None = non mesuré
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        check_id(self.run_id, "run_id")
        check_text(self.request, "request", 2_000, allow_empty=True)
        if (self.agent_id, self.capability, self.operational_authority) != (
            "SENTINEL-01",
            "OBSERVE_ONLY",
            "DENIED",
        ):
            raise ContractError("identité ou capacité de Sentinel altérée")
        if self.mode not in {"DEMO", "LIVE_READ"}:
            raise ContractError("mode inconnu")
        if parse_utc(self.finished_at_utc) < parse_utc(self.started_at_utc):
            raise ContractError("AgentRun: fin avant début")
        check_items(self.tool_calls, "tool_calls")
        check_items(self.evidence, "evidence", 500)
        provs = {e.provenance for e in self.evidence}
        check_no_mixed_provenance(provs, "AgentRun")
        if self.mode == "DEMO" and Provenance.LIVE_READ in provs:
            raise ContractError("un run DEMO ne peut pas citer de lecture réelle")
        if self.mode == "LIVE_READ" and Provenance.SYNTHETIC in provs:
            raise ContractError("un run LIVE_READ ne peut pas citer de fixture")
        known = {e.evidence_id for e in self.evidence}
        cited: set[str] = set()
        for st in self.answer.statements:
            cited.update(st.evidence_ids)
        for group in (self.answer.discrepancies, self.answer.findings):
            for item in group:
                cited.update(e.evidence_id for e in item.evidence)
        unknown = cited - known
        if unknown:
            raise ContractError(f"preuves citées absentes du run: {sorted(unknown)[:5]}")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


