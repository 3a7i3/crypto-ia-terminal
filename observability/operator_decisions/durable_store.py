"""Prototype de stockage durable D5B-R2, isolé et hors runtime.

Ce module N'EST PAS un service, un endpoint ou un composant déployé. Il
prolonge le noyau source D5B-R1 (`producer.GovernedProducer`) avec un journal
append-only persistant (SQLite, transaction explicite) et une projection
reconstruite uniquement à partir de ce journal.

Limites documentées (voir aussi `docs/adr/0019-...md`) :

- L'`AvailabilityProof` reste une attestation *injectée par l'appelant*. Ce
  module ne l'authentifie jamais : aucune signature, aucune racine de
  confiance externe n'est vérifiée ici. Une preuve non authentifiée ne peut
  donc JAMAIS, à elle seule, produire `AVAILABLE` avec certitude — elle ne
  fait que refléter ce que l'appelant prétend. Le champ
  `AvailabilityProof.trust_root_ref` documente l'absence de vérification et
  DOIT être traité comme non fiable tant qu'aucun mécanisme de signature ou
  d'ancrage n'est branché (gate distinct, non couvert par ce prototype).
- Le hash de chaîne (`event_hash`/`previous_event_hash`) est un contrôle
  d'INTÉGRITÉ interne (détecte réécriture, troncature, réordonnancement) ; ce
  n'est PAS une preuve d'AUTHENTICITÉ externe (rien n'empêche quiconque a un
  accès disque de recalculer une chaîne cohérente après une réécriture totale
  du fichier). Une racine de confiance externe (clé de signature détenue hors
  de ce processus, ancrage dans un registre faisant autorité) resterait
  nécessaire pour ce niveau de garantie et n'est pas implémentée ici.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping
from uuid import uuid4

from observability.operator_decisions.producer import (
    INITIAL_STATUSES,
    PRIORITIES,
    Candidate,
    ContractError,
    GovernedProducer,
    IntegrityError,
    _digest,
    _text,
    _utc,
)

SCHEMA_VERSION = "1.0.0"
KNOWN_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})


@dataclass(frozen=True)
class AvailabilityProof:
    """Attestation injectée par un gate futur — jamais fabriquée ici.

    `trust_root_ref` documente explicitement qu'aucune vérification de
    signature ou d'ancrage n'est effectuée par ce prototype : la valeur est
    acceptée telle quelle et n'ajoute aucune garantie cryptographique. Un
    gate distinct devra brancher une racine de confiance réelle avant que
    cette attestation puisse justifier une décision opérationnelle.
    """

    producer_certified: bool
    deployment_evidence_ref: str
    complete_event_count: int
    observed_at_utc: str
    trust_root_ref: str = "UNVERIFIED_NO_TRUST_ROOT"


class CorruptedJournalError(IntegrityError):
    """Le journal sur disque ne peut plus être vérifié : échec fermé."""


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    decision_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    previous_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS command_results (
    command_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    committed_at_utc TEXT NOT NULL
);
"""


class DurableGovernedStore:
    """Journal append-only SQLite + projection gouvernée, hors runtime.

    Chaque admission est une transaction SQLite explicite
    (`BEGIN IMMEDIATE` ... `COMMIT`/`ROLLBACK`) : soit l'événement, son index
    d'idempotence et l'enregistrement de la commande sont tous durables
    ensemble, soit rien ne l'est. `BEGIN IMMEDIATE` prend le verrou
    d'écriture dès le début de la transaction, ce qui sérialise les
    admissions concurrentes au niveau du fichier — deux admissions
    simultanées identiques convergent sur la même `decision_id` ; deux
    admissions conflictuelles sur la même clé sont rejetées.
    """

    def __init__(self, db_path: str | Path, owners: Mapping[str, str]):
        # Réutilise la validation du noyau R1 sans dupliquer la logique de
        # décision (gel architectural) : seule la persistance change.
        self._validator = GovernedProducer(dict(owners))
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)  # DDL : idempotent, hors journal
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta (id, schema_version) VALUES (1, ?)",
                (SCHEMA_VERSION,),
            )
            row = conn.execute("SELECT schema_version FROM schema_meta WHERE id=1").fetchone()
            conn.execute("COMMIT")
            if row[0] not in KNOWN_SCHEMA_VERSIONS:
                raise CorruptedJournalError(
                    f"version de schéma de base inconnue : {row[0]!r}"
                )
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            conn.close()

    @staticmethod
    def _key(candidate: Candidate) -> tuple:
        return (
            candidate.owner_registry, candidate.source_type,
            candidate.source_id, candidate.owner_record_version,
            candidate.decision_purpose,
        )

    def admit(
        self, candidate: Candidate, *, occurred_at_utc: str,
        approved_status: str, approved_priority: str,
        admission_approval_ref: str, command_id: str,
    ) -> str:
        """Admission atomique et idempotente, y compris après redémarrage.

        `command_id` identifie la requête de l'appelant (pas la décision) :
        si l'appelant a perdu la réponse après un commit réussi (crash,
        coupure réseau), rejouer `admit` avec le même `command_id` retrouve
        la `decision_id` déjà committée sans dupliquer d'événement.
        """
        self._validator._validate(candidate)  # noqa: SLF001 (réutilisation intentionnelle)
        _utc(occurred_at_utc)
        _text(admission_approval_ref, "admission_approval_ref")
        _text(command_id, "command_id")
        if approved_status not in INITIAL_STATUSES or approved_priority not in PRIORITIES:
            raise ContractError("statut ou priorité approuvé invalide")

        payload = self._validator._payload(candidate)  # noqa: SLF001
        key = self._key(candidate)
        key_hash = _digest(key)
        fingerprint = _digest({
            "candidate": payload, "approved_status": approved_status,
            "approved_priority": approved_priority,
            "admission_approval_ref": admission_approval_ref,
        })

        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing_cmd = conn.execute(
                    "SELECT decision_id FROM command_results WHERE command_id = ?",
                    (command_id,),
                ).fetchone()
                if existing_cmd is not None:
                    conn.execute("COMMIT")
                    return existing_cmd[0]

                self._verify_locked(conn)

                existing_key = conn.execute(
                    "SELECT decision_id, payload_json, sequence FROM events "
                    "WHERE idempotency_key = ?", (key_hash,),
                ).fetchone()
                if existing_key is not None:
                    decision_id, payload_json, sequence = existing_key
                    stored = json.loads(payload_json)
                    if stored.get("fingerprint") != fingerprint:
                        conn.execute("ROLLBACK")
                        raise ContractError("collision de clé d'admission")
                else:
                    last = conn.execute(
                        "SELECT sequence, event_hash FROM events "
                        "ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    sequence = (last[0] + 1) if last else 1
                    previous_hash = last[1] if last else "GENESIS"
                    decision_id = str(uuid4())
                    event_body = {
                        "schema_version": SCHEMA_VERSION,
                        "event_id": str(uuid4()), "decision_id": decision_id,
                        "decision_version": 1, "sequence": sequence,
                        "event_type": "CANDIDATE_ADMITTED",
                        "actor_type": "GOVERNANCE_SERVICE",
                        "actor_ref": "governed-admission",
                        "occurred_at_utc": occurred_at_utc,
                        "new_status": approved_status,
                        "candidate_id": candidate.candidate_id,
                        "source_revision_ref": candidate.owner_record_version,
                        "admission_approval_ref": admission_approval_ref,
                        "approved_priority": approved_priority,
                        "requested_priority": candidate.requested_priority,
                        "evidence_refs": list(candidate.evidence_refs),
                        "idempotency_key": key_hash,
                        "previous_event_hash": previous_hash,
                        "candidate": payload,
                        "fingerprint": fingerprint,
                    }
                    event_hash = _digest(
                        {k: v for k, v in event_body.items() if k != "fingerprint"}
                    )
                    event_body["event_hash"] = event_hash
                    conn.execute(
                        "INSERT INTO events (sequence, event_id, decision_id, "
                        "schema_version, idempotency_key, previous_event_hash, "
                        "event_hash, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            sequence, event_body["event_id"], decision_id,
                            SCHEMA_VERSION, key_hash, previous_hash, event_hash,
                            json.dumps(event_body, sort_keys=True),
                        ),
                    )

                conn.execute(
                    "INSERT INTO command_results (command_id, decision_id, "
                    "sequence, committed_at_utc) VALUES (?, ?, ?, ?)",
                    (command_id, decision_id, sequence, occurred_at_utc),
                )
                conn.execute("COMMIT")
                return decision_id
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
            finally:
                conn.close()

    @staticmethod
    def _verify_locked(conn: sqlite3.Connection) -> None:
        """Vérifie la chaîne dans la transaction en cours (fail-closed)."""
        rows = conn.execute(
            "SELECT sequence, event_hash, previous_event_hash, schema_version, "
            "payload_json FROM events ORDER BY sequence ASC"
        ).fetchall()
        previous = "GENESIS"
        seen_decisions: set[str] = set()
        expected_seq = 1
        for sequence, event_hash, previous_event_hash, schema_version, payload_json in rows:
            if sequence != expected_seq:
                raise CorruptedJournalError("trou ou réordonnancement de séquence")
            if schema_version not in KNOWN_SCHEMA_VERSIONS:
                raise CorruptedJournalError(
                    f"version de schéma inconnue : {schema_version!r}"
                )
            try:
                body = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                raise CorruptedJournalError("charge utile illisible") from exc
            recomputed = _digest(
                {k: v for k, v in body.items() if k not in ("event_hash", "fingerprint")}
            )
            if (
                previous_event_hash != previous or event_hash != recomputed
                or body.get("event_hash") != event_hash
                or body.get("decision_id") in seen_decisions
            ):
                raise CorruptedJournalError("chaîne d'événements invalide")
            seen_decisions.add(body["decision_id"])
            previous = event_hash
            expected_seq += 1

    def verify(self) -> None:
        """Vérification en lecture seule, hors transaction d'écriture."""
        conn = self._connect()
        try:
            self._verify_locked(conn)
        finally:
            conn.close()

    def events(self) -> tuple[dict, ...]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT payload_json FROM events ORDER BY sequence ASC"
            ).fetchall()
        finally:
            conn.close()
        return tuple(json.loads(r[0]) for r in rows)

    def project(self, proof: AvailabilityProof | None = None) -> dict:
        """Reconstruit la projection à partir du journal seul (fail-closed)."""
        try:
            events = self.events()
            self.verify()
        except (CorruptedJournalError, IntegrityError, sqlite3.DatabaseError,
                json.JSONDecodeError):
            return {
                "schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
                "decision_count": None, "items": None,
                "limitations": ["integrity_failure"],
            }

        if proof is None:
            return {
                "schema_version": SCHEMA_VERSION, "availability": "NON DÉPLOYÉ",
                "decision_count": None, "items": None,
                "limitations": ["aucune preuve de déploiement"],
            }
        if not isinstance(proof, AvailabilityProof) or proof.producer_certified is not True:
            raise ContractError("attestation de producteur requise")
        _text(proof.deployment_evidence_ref, "deployment_evidence_ref")
        _utc(proof.observed_at_utc)
        if type(proof.complete_event_count) is not int or proof.complete_event_count != len(events):
            return {
                "schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
                "decision_count": None, "items": None,
                "limitations": ["watermark incomplet"],
            }

        items = []
        for e in events:
            c = e["candidate"]
            items.append({
                "decision_id": e["decision_id"], "schema_version": SCHEMA_VERSION,
                "decision_type": c["decision_type"], "title": c["title"],
                "summary": c["summary"], "status": e["new_status"],
                "priority": e["approved_priority"],
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
                    "limitations": [
                        "AvailabilityProof non authentifiée (pas de racine de confiance)"
                    ],
                },
                "proposed_change": c["proposed_change"],
                "risk": c["risk"], "validation": c["validation"],
                "rollback": c["rollback"], "human_decision": None,
                "version": e["decision_version"],
            })
        counts = {
            status: sum(i["status"] == status for i in items)
            for status in sorted(INITIAL_STATUSES)
        }
        return {
            "schema_version": SCHEMA_VERSION, "product": "OPERATOR_DECISION_QUEUE",
            "domain": "GOVERNANCE", "authority": "GOVERNANCE_WORKFLOW_PRESENTATION",
            "availability": "AVAILABLE", "generated_at_utc": proof.observed_at_utc,
            "deployment_evidence_ref": proof.deployment_evidence_ref,
            "trust_root_ref": proof.trust_root_ref,
            "as_of_event_version": len(events),
            "decision_count": len(items), "counts_by_status": counts,
            "items": items, "limitations": [
                "AvailabilityProof non authentifiée : voir docs/adr — "
                "aucune racine de confiance externe branchée dans ce prototype"
            ],
            "projection_hash": _digest(items),
        }


__all__ = [
    "AvailabilityProof", "CorruptedJournalError", "DurableGovernedStore",
    "SCHEMA_VERSION",
]
