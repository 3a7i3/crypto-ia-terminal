"""Noyau source D5B-R1, sans I/O, endpoint ni dépendance runtime.

Le registre est volontairement en mémoire : aucune instance n'est une preuve de
déploiement ou un stockage durable. D5C et les actions humaines restent hors scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Mapping
from uuid import uuid4


SCHEMA_VERSION = "1.0.0"
PRIORITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"})
INITIAL_STATUSES = frozenset({"TO_VALIDATE", "TO_READ", "TO_PLAN", "BLOCKED"})
SOURCE_TYPES = frozenset({
    "PROBLEM", "PROPOSED_EVOLUTION", "BOUNTY_RESULT", "RESEARCH_CANDIDATE",
    "SECURITY_FINDING", "INCIDENT_FOLLOWUP", "ARCHITECTURE_CHANGE",
    "RUNTIME_CHANGE_REQUEST", "COST_GOVERNANCE",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class ContractError(ValueError):
    """Un candidat ou une preuve viole le contrat gouverné."""


class IntegrityError(ContractError):
    """Le journal append-only ne peut plus être projeté avec confiance."""


def _utc(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ContractError("horodatage UTC invalide") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError("horodatage UTC requis")


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{label} requis sans espaces de bord")


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    candidate_revision: int
    source_type: str
    source_id: str
    source_ref: str
    source_sha: str
    source_generated_at_utc: str
    producer: str
    producer_authority: str
    owner_registry: str
    owner_record_version: str
    decision_type: str
    title: str
    summary: str
    proposed_change: str
    decision_purpose: str
    requested_status: str
    requested_priority: str
    evidence_status: str
    evidence_refs: tuple[str, ...]
    upstream_approval_ref: str
    risk: str
    validation: str
    rollback: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AvailabilityProof:
    """Attestation injectée par un gate futur, jamais fabriquée par le registre."""
    producer_certified: bool
    deployment_evidence_ref: str
    complete_event_count: int
    observed_at_utc: str


class GovernedProducer:
    """Prototype source isolé. Les propriétaires admis sont injectés explicitement."""

    def __init__(self, owners: Mapping[str, str]):
        if not owners or any(k not in SOURCE_TYPES or not isinstance(v, str)
                             or not v.strip() for k, v in owners.items()):
            raise ContractError("politique de propriétaires explicite requise")
        self._owners = dict(owners)
        self._events: list[dict] = []
        self._admitted: dict[tuple[str, ...], tuple[str, str]] = {}

    @staticmethod
    def _payload(candidate: Candidate) -> dict:
        return {name: getattr(candidate, name) for name in
                Candidate.__dataclass_fields__ if name != "evidence_refs"} | {
                    "evidence_refs": list(candidate.evidence_refs)
                }

    def _validate(self, c: Candidate) -> None:
        if not isinstance(c, Candidate) or c.schema_version != SCHEMA_VERSION:
            raise ContractError("version ou type candidat non pris en charge")
        for field in (
            "candidate_id", "source_id", "source_ref", "producer",
            "producer_authority", "owner_registry", "owner_record_version",
            "decision_type", "title", "summary", "proposed_change", "decision_purpose",
            "evidence_status", "upstream_approval_ref", "risk",
            "validation", "rollback",
        ):
            _text(getattr(c, field), field)
        if type(c.candidate_revision) is not int or c.candidate_revision < 1:
            raise ContractError("révision de candidat invalide")
        if not isinstance(c.source_type, str) or c.source_type not in self._owners or c.owner_registry != self._owners[c.source_type]:
            raise ContractError("propriétaire source non autorisé")
        if c.source_type not in SOURCE_TYPES or c.producer_authority != "GOVERNED_SOURCE":
            raise ContractError("source non gouvernée")
        if not isinstance(c.source_sha, str) or not _SHA.fullmatch(c.source_sha):
            raise ContractError("hash source SHA-256 requis")
        _utc(c.source_generated_at_utc)
        if c.requested_status not in INITIAL_STATUSES or c.requested_priority not in PRIORITIES:
            raise ContractError("statut initial ou priorité invalide")
        if c.evidence_status != "VERIFIED" or not isinstance(c.evidence_refs, tuple) or not c.evidence_refs:
            raise ContractError("preuves vérifiées et inspectables requises")
        for ref in c.evidence_refs:
            _text(ref, "evidence_ref")
        if len(set(c.evidence_refs)) != len(c.evidence_refs):
            raise ContractError("références de preuve dupliquées")

    def admit(self, candidate: Candidate, *, occurred_at_utc: str) -> str:
        """Admettre sans action humaine. Un doublon strict ne produit aucun événement."""
        self._validate(candidate)
        _utc(occurred_at_utc)
        self.verify()
        key = (candidate.owner_registry, candidate.source_type,
               candidate.source_id, candidate.owner_record_version,
               candidate.decision_purpose)
        fingerprint = _digest(self._payload(candidate))
        if key in self._admitted:
            prior_fingerprint, decision_id = self._admitted[key]
            if prior_fingerprint != fingerprint:
                raise ContractError("collision de clé d'admission")
            return decision_id
        decision_id = str(uuid4())
        sequence = len(self._events) + 1
        event = {
            "schema_version": SCHEMA_VERSION, "event_id": str(uuid4()),
            "decision_id": decision_id, "decision_version": 1,
            "sequence": sequence, "event_type": "CANDIDATE_ADMITTED",
            "actor_type": "GOVERNANCE_SERVICE",
            "actor_ref": "governed-admission", "occurred_at_utc": occurred_at_utc,
            "previous_status": None, "new_status": candidate.requested_status,
            "expected_version": 0, "candidate_id": candidate.candidate_id,
            "source_revision_ref": candidate.owner_record_version,
            "reason": "admission gouvernée",
            "evidence_refs": list(candidate.evidence_refs),
            "idempotency_key": _digest(key),
            "previous_event_hash": self._events[-1]["event_hash"] if self._events else "GENESIS",
            "candidate": self._payload(candidate),
        }
        event["event_hash"] = _digest(event)
        self._events.append(event)
        self._admitted[key] = (fingerprint, decision_id)
        return decision_id

    def verify(self) -> None:
        previous = "GENESIS"
        seen: set[str] = set()
        for index, event in enumerate(self._events, 1):
            if (event.get("sequence") != index or
                event.get("previous_event_hash") != previous or
                event.get("event_hash") != _digest({
                    k: v for k, v in event.items() if k != "event_hash"
                }) or event.get("decision_id") in seen or
                event.get("decision_version") != 1 or
                event.get("event_type") != "CANDIDATE_ADMITTED"):
                raise IntegrityError("chaîne d'événements invalide")
            seen.add(event["decision_id"])
            previous = event["event_hash"]

    def events(self) -> tuple[dict, ...]:
        """Copie détachée : aucun appelant ne peut altérer le journal interne."""
        return tuple(json.loads(json.dumps(event)) for event in self._events)

    def project(self, proof: AvailabilityProof | None = None) -> dict:
        """Sans attestation externe : NON DÉPLOYÉ, jamais zéro synthétique."""
        try:
            self.verify()
        except (IntegrityError, TypeError, KeyError, ValueError):
            return {"schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
                    "decision_count": None, "items": None, "limitations": ["integrity_failure"]}
        if proof is None:
            return {"schema_version": SCHEMA_VERSION, "availability": "NON DÉPLOYÉ",
                    "decision_count": None, "items": None,
                    "limitations": ["aucune preuve de déploiement"]}
        if not isinstance(proof, AvailabilityProof) or proof.producer_certified is not True:
            raise ContractError("attestation de producteur requise")
        _text(proof.deployment_evidence_ref, "deployment_evidence_ref")
        _utc(proof.observed_at_utc)
        if type(proof.complete_event_count) is not int or proof.complete_event_count != len(self._events):
            return {"schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
                    "decision_count": None, "items": None,
                    "limitations": ["watermark incomplet"]}
        items = []
        for e in self._events:
            c = e["candidate"]
            items.append({
                "decision_id": e["decision_id"], "schema_version": SCHEMA_VERSION,
                "decision_type": c["decision_type"], "title": c["title"],
                "summary": c["summary"], "status": e["new_status"],
                "priority": c["requested_priority"],
                "created_at_utc": e["occurred_at_utc"],
                "updated_at_utc": e["occurred_at_utc"],
                "source": {
                    "source_type": c["source_type"], "source_id": c["source_id"],
                    "source_ref": c["source_ref"], "source_sha": c["source_sha"],
                    "source_generated_at_utc": c["source_generated_at_utc"],
                    "producer": c["producer"],
                    "producer_authority": c["producer_authority"],
                    "owner_registry": c["owner_registry"],
                    "owner_record_version": c["owner_record_version"],
                },
                "authority": "HUMAN_OPERATOR",
                "evidence": {
                    "evidence_status": c["evidence_status"],
                    "evidence_refs": list(e["evidence_refs"]),
                    "source_hashes": [c["source_sha"]],
                    "tests": None, "ci": None, "review": c["upstream_approval_ref"],
                    "limitations": ["tests/CI non fournis dans cette tranche"],
                },
                "proposed_change": c["proposed_change"],
                "risk": c["risk"], "validation": c["validation"],
                "rollback": c["rollback"], "human_decision": None,
                "version": e["decision_version"],
            })
        counts = {status: sum(i["status"] == status for i in items)
                  for status in sorted(INITIAL_STATUSES)}
        return {
            "schema_version": SCHEMA_VERSION, "product": "OPERATOR_DECISION_QUEUE",
            "domain": "GOVERNANCE", "authority": "GOVERNANCE_WORKFLOW_PRESENTATION",
            "availability": "AVAILABLE", "generated_at_utc": proof.observed_at_utc,
            "deployment_evidence_ref": proof.deployment_evidence_ref,
            "as_of_event_version": len(self._events),
            "decision_count": len(items), "counts_by_status": counts,
            "items": items, "limitations": [],
            "projection_hash": _digest(items),
        }
