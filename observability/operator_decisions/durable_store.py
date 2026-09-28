"""Prototype de stockage durable D5B-R2, isolé et hors runtime.

Ce module N'EST PAS un service, un endpoint ou un composant déployé. Il
prolonge le noyau source D5B-R1 (`producer.GovernedProducer`) avec un journal
append-only persistant (SQLite, transaction explicite) et une projection
reconstruite uniquement à partir de ce journal.

Contrat de confiance : ADR-0020 (`docs/adr/0020-contrat-de-confiance-...md`).

- Admission : exige une approbation signée (Ed25519) par un
  `ADMISSION_APPROVER` de la politique passée au CONSTRUCTEUR, liée au
  candidat exact ; statut et priorité sont lus depuis l'approbation vérifiée.
- Projection : `AVAILABLE` (y compris le zéro explicite) exige une
  attestation signée par un `AVAILABILITY_AUTHORITY`, fraîche (horloge
  injectée), liée au `journal_id`, complète (compte + hash de tête) et
  monotone (dernier checkpoint accepté persisté par le vérificateur).
  `AvailabilityProof` (preuve libre) ne produit plus jamais `AVAILABLE`.
- Limite : la politique utilisée est une FIXTURE non opérationnelle ; aucune
  autorité réelle n'est désignée (ADR-0020 §3, blocage de certification).
  La chaîne de hash reste un contrôle d'INTÉGRITÉ : une réécriture complète
  avec recalcul n'est détectée que par l'attestation fraîche ou l'ancre
  anti-retour, jamais par `verify()` seul.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
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
from observability.operator_decisions.trust import (
    ADMISSION_APPROVAL,
    ADMISSION_APPROVER,
    AVAILABILITY_ATTESTATION,
    AVAILABILITY_AUTHORITY,
    EVIDENCE_ACCESS_AUTHORITY,
    EVIDENCE_ACCESS_GRANT,
    OWNER_TRANSFER,
    PRIORITY_RANK,
    SOURCE_OWNER,
    SignedStatement,
    TrustError,
    TrustPolicy,
)

# Version du JOURNAL (corps d'événement + attestations). 3.0.0 : transfert
# signé par le propriétaire, classification des références de preuves,
# permissions par triplet exact. Un journal d'une version antérieure est
# refusé (échec fermé) : aucun journal hors tests n'existe à ce jour.
SCHEMA_VERSION = "3.0.0"
EVIDENCE_PUBLIC = "PUBLIC"
EVIDENCE_SENSITIVE = "SENSITIVE"
EVIDENCE_CLASSES = frozenset({EVIDENCE_PUBLIC, EVIDENCE_SENSITIVE})
JOURNAL_SCOPE = "OPERATOR_DECISION_QUEUE"
KNOWN_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

# Retenue bornée UNIQUEMENT pour `PRAGMA journal_mode=WAL` dans `_connect()`
# face à `sqlite3.OperationalError("database is locked")` (reproduction
# locale déterministe documentée, PR #316). Aucune autre erreur n'est
# retentée : la retenue générique de `_read_events_verified` a été retirée,
# son diagnostic ayant été réfuté (cause réelle : monkeypatch au niveau
# classe dans le test).
_WAL_RETRY_ATTEMPTS = 5
_WAL_RETRY_DELAY_SECONDS = 0.05


@dataclass(frozen=True)
class AvailabilityProof:
    """OBSOLÈTE — preuve libre non authentifiée, conservée pour la rétro-lecture.

    Depuis ADR-0020, `project()` n'accorde AUCUNE autorité à cet objet : un
    booléen `producer_certified` fourni par l'appelant n'établit jamais sa
    propre autorité. Passée à `project()`, elle produit toujours `UNKNOWN`
    (jamais `AVAILABLE`, base vide ou non). Seule une attestation signée par
    un `AVAILABILITY_AUTHORITY` de la politique du constructeur compte.
    """

    producer_certified: bool
    deployment_evidence_ref: str
    complete_event_count: int
    observed_at_utc: str
    trust_root_ref: str = "UNVERIFIED_NO_TRUST_ROOT"


class CorruptedJournalError(IntegrityError):
    """Le journal sur disque ne peut plus être vérifié : échec fermé."""


def candidate_fingerprint(payload: Mapping) -> str:
    """Empreinte canonique du candidat exact (tous champs, JSON trié)."""
    return _digest(dict(payload))


def availability_attestation_payload(
    *, policy_version: str, authority_id: str, journal_id: str,
    checkpoint: int, event_count: int, head_hash: str, issued_at_utc: str,
    expires_at_utc: str, deployment_evidence_ref: str,
    scope: str = JOURNAL_SCOPE, schema_version: str = SCHEMA_VERSION,
) -> dict:
    """Construit la charge d'une attestation de disponibilité (à signer HORS store)."""
    return {
        "statement_type": AVAILABILITY_ATTESTATION,
        "policy_version": policy_version, "authority_id": authority_id,
        "journal_id": journal_id, "scope": scope,
        "schema_version": schema_version, "checkpoint": checkpoint,
        "event_count": event_count, "head_hash": head_hash,
        "issued_at_utc": issued_at_utc, "expires_at_utc": expires_at_utc,
        "deployment_evidence_ref": deployment_evidence_ref,
    }


def evidence_ref_digest(ref: str) -> str:
    """Empreinte d'une référence de preuve (clé de classification)."""
    return _digest(ref)


def _candidate_bindings(candidate: Candidate) -> dict:
    """Champs qui lient un énoncé signé au candidat exact."""
    return {
        "candidate_fingerprint": candidate_fingerprint(
            GovernedProducer._payload(candidate)  # noqa: SLF001
        ),
        "owner_registry": candidate.owner_registry,
        "source_type": candidate.source_type,
        "source_id": candidate.source_id,
        "owner_record_version": candidate.owner_record_version,
        "source_sha": candidate.source_sha,
        "decision_purpose": candidate.decision_purpose,
    }


def owner_transfer_payload(
    candidate: Candidate, *, policy_version: str, owner_id: str,
    transfer_id: str, evidence_ref_classes: Mapping[str, str],
    issued_at_utc: str, expires_at_utc: str,
) -> dict:
    """Charge d'un transfert explicite du propriétaire source (à signer HORS store).

    Contrat D5B §2 : chaque admission exige un transfert explicite approuvé
    par le propriétaire du fait source. `evidence_ref_classes` classe CHAQUE
    référence de preuve du candidat (clé = `evidence_ref_digest`), afin que
    la projection masque les références sensibles (D5B §5).
    """
    return {
        "statement_type": OWNER_TRANSFER,
        "policy_version": policy_version,
        "transfer_id": transfer_id,
        "owner_id": owner_id,
        **_candidate_bindings(candidate),
        "evidence_ref_classes": dict(evidence_ref_classes),
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": expires_at_utc,
    }


def transfer_digest(transfer: SignedStatement) -> str:
    """Empreinte du transfert signé exact (signature comprise)."""
    return _digest(transfer.digest_material())


def admission_approval_payload(
    candidate: Candidate, *, policy_version: str, approver_id: str,
    approved_status: str, approved_priority: str, owner_transfer_digest: str,
    approval_id: str, issued_at_utc: str, expires_at_utc: str,
) -> dict:
    """Construit la charge d'une approbation d'admission (à signer HORS store).

    Simple constructeur de données : une charge non signée n'a aucune
    autorité. Seule `TrustPolicy.verify` (politique du constructeur du store)
    lui en confère une. L'approbation est liée au transfert propriétaire
    exact par son empreinte (`owner_transfer_digest`).
    """
    return {
        "statement_type": ADMISSION_APPROVAL,
        "policy_version": policy_version,
        "approval_id": approval_id,
        "approver_id": approver_id,
        **_candidate_bindings(candidate),
        "approved_status": approved_status,
        "approved_priority": approved_priority,
        "owner_transfer_digest": owner_transfer_digest,
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": expires_at_utc,
    }


def evidence_access_grant_payload(
    *, policy_version: str, authority_id: str, journal_id: str,
    decision_id: str, accessor_id: str, issued_at_utc: str,
    expires_at_utc: str,
) -> dict:
    """Charge d'un droit de lecture des références sensibles d'UNE décision."""
    return {
        "statement_type": EVIDENCE_ACCESS_GRANT,
        "policy_version": policy_version, "authority_id": authority_id,
        "journal_id": journal_id, "decision_id": decision_id,
        "accessor_id": accessor_id, "issued_at_utc": issued_at_utc,
        "expires_at_utc": expires_at_utc,
    }


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version TEXT NOT NULL,
    journal_id TEXT NOT NULL
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
    event_hash TEXT NOT NULL,
    committed_at_utc TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL
);
"""

# Ancre anti-retour (ADR-0020 §8) : dernier checkpoint ACCEPTÉ par le
# vérificateur, jamais fourni par l'appelant. Peut vivre dans un fichier
# distinct du journal (`anchor_path`).
_ANCHOR_SQL = """
CREATE TABLE IF NOT EXISTS accepted_checkpoint (
    journal_id TEXT PRIMARY KEY,
    checkpoint INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    head_hash TEXT NOT NULL,
    accepted_at_utc TEXT NOT NULL
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

    def __init__(
        self, db_path: str | Path, owners: Mapping[str, str], *,
        trust_policy: TrustPolicy, clock: Callable[[], datetime],
        anchor_path: str | Path | None = None,
        allow_colocated_anchor: bool = False,
    ):
        # Réutilise la validation du noyau R1 sans dupliquer la logique de
        # décision (gel architectural) : seule la persistance change.
        self._validator = GovernedProducer(dict(owners))
        # Politique de confiance = configuration du VÉRIFICATEUR (ADR-0020
        # §5) : fournie ici, jamais dans une requête.
        if not isinstance(trust_policy, TrustPolicy):
            raise ContractError("politique de confiance du vérificateur requise")
        if not callable(clock):
            raise ContractError("horloge injectée requise (ADR-0020 §9)")
        self._policy = trust_policy
        self._clock = clock
        self._db_path = str(db_path)
        # Ancre anti-retour (ADR-0020 §8) : hors du fichier journal par
        # défaut. Colocalisée, une restauration du fichier entier fait
        # reculer l'ancre avec lui ; ce choix doit donc être explicite.
        if anchor_path is None:
            anchor = self._db_path
        else:
            anchor = str(anchor_path)
        if (Path(anchor).resolve() == Path(self._db_path).resolve()
                and not allow_colocated_anchor):
            raise ContractError(
                "ancre anti-retour hors du fichier journal requise (anchor_path) ; "
                "colocalisation seulement avec allow_colocated_anchor=True "
                "(une restauration du fichier entier ferait reculer l'ancre)"
            )
        self._anchor_path = anchor
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self, path: str | None = None) -> sqlite3.Connection:
        """Ouvre une connexion configurée ; la ferme sur tout échec.

        `busy_timeout` explicite, puis passage en WAL seulement si
        nécessaire. Reproduction locale déterministe (5 threads créant chacun
        leur `DurableGovernedStore` sur le même fichier neuf) :
        `sqlite3.OperationalError: database is locked` précisément sur
        `PRAGMA journal_mode=WAL` malgré `busy_timeout` — le changement de
        mode exige un verrou exclusif bref que `busy_timeout` ne couvre pas
        toujours. Seule cette erreur précise est retentée (bornée) ; toute
        autre exception remonte immédiatement, connexion fermée.
        """
        conn = sqlite3.connect(path or self._db_path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            current_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if str(current_mode).lower() != "wal":
                for attempt in range(_WAL_RETRY_ATTEMPTS):
                    try:
                        conn.execute("PRAGMA journal_mode=WAL")
                        break
                    except sqlite3.OperationalError as exc:
                        if ("database is locked" not in str(exc)
                                or attempt == _WAL_RETRY_ATTEMPTS - 1):
                            raise
                        time.sleep(_WAL_RETRY_DELAY_SECONDS)
            conn.execute("PRAGMA foreign_keys=ON")
        except BaseException:
            conn.close()
            raise
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)  # DDL : idempotent, hors journal
            conn.execute("BEGIN IMMEDIATE")
            # Identifiant de journal stable : créé une seule fois à
            # l'initialisation, lié par chaque attestation de disponibilité.
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta (id, schema_version, journal_id) "
                "VALUES (1, ?, ?)",
                (SCHEMA_VERSION, str(uuid4())),
            )
            row = conn.execute(
                "SELECT schema_version, journal_id FROM schema_meta WHERE id=1"
            ).fetchone()
            conn.execute("COMMIT")
            if row[0] not in KNOWN_SCHEMA_VERSIONS:
                raise CorruptedJournalError(
                    f"version de schéma de base inconnue : {row[0]!r}"
                )
            self._journal_id = row[1]
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            conn.close()

    def _init_anchor(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_ANCHOR_SQL)

    @property
    def journal_id(self) -> str:
        return self._journal_id

    @staticmethod
    def _key(candidate: Candidate) -> tuple:
        return (
            candidate.owner_registry, candidate.source_type,
            candidate.source_id, candidate.owner_record_version,
            candidate.decision_purpose,
        )

    @staticmethod
    def _check_bindings(body: dict, candidate: Candidate, payload: dict, label: str) -> None:
        """L'énoncé signé doit viser exactement ce candidat (anti-substitution)."""
        bindings = {
            "owner_registry": candidate.owner_registry,
            "source_type": candidate.source_type,
            "source_id": candidate.source_id,
            "owner_record_version": candidate.owner_record_version,
            "source_sha": candidate.source_sha,
            "decision_purpose": candidate.decision_purpose,
            "candidate_fingerprint": candidate_fingerprint(payload),
        }
        for name, expected in bindings.items():
            if body.get(name) != expected:
                raise TrustError(
                    f"{label} non lié au candidat présenté ({name}) : "
                    "substitution, source remplacée ou obsolète"
                )

    def _authenticate(self, candidate: Candidate, payload: dict,
                      owner_transfer: object, approval: object) -> tuple[dict, dict]:
        """Authentifie transfert propriétaire + approbation, SANS fraîcheur.

        Signature, clé connue et non révoquée, rôle, version de politique,
        identité, permissions exactes (registre, type, finalité), liens au
        candidat exact, lien approbation → transfert. Aucune écriture n'a
        lieu ici. La fraîcheur est vérifiée à part (`_check_fresh`), et
        seulement quand un nouvel événement va être écrit : un rejeu d'une
        commande déjà commitée doit rester possible après expiration
        (réponse perdue), tout en restant authentifié.
        """
        t_body, t_key = self._policy.verify(
            owner_transfer, role=SOURCE_OWNER, statement_type=OWNER_TRANSFER,
        )
        self._policy.check_window(t_body)
        if t_body.get("owner_id") != t_key.identity:
            raise TrustError("le propriétaire signé ne correspond pas à l'identité de la clé")
        self._policy.authorize(
            t_key, candidate.owner_registry, candidate.source_type,
            candidate.decision_purpose,
        )
        self._check_bindings(t_body, candidate, payload, "transfert propriétaire")
        _text(t_body.get("transfer_id"), "transfer_id")
        classes = t_body.get("evidence_ref_classes")
        expected_refs = {evidence_ref_digest(r) for r in candidate.evidence_refs}
        if (not isinstance(classes, dict) or set(classes) != expected_refs
                or any(v not in EVIDENCE_CLASSES for v in classes.values())):
            raise TrustError(
                "classification des références de preuves incomplète ou "
                "invalide (chaque référence doit être PUBLIC ou SENSITIVE)"
            )

        a_body, a_key = self._policy.verify(
            approval, role=ADMISSION_APPROVER, statement_type=ADMISSION_APPROVAL,
        )
        self._policy.check_window(a_body)
        if a_body.get("approver_id") != a_key.identity:
            raise TrustError("l'approbateur signé ne correspond pas à l'identité de la clé")
        self._policy.authorize(
            a_key, candidate.owner_registry, candidate.source_type,
            candidate.decision_purpose,
        )
        self._check_bindings(a_body, candidate, payload, "approbation")
        if a_body.get("owner_transfer_digest") != transfer_digest(owner_transfer):
            raise TrustError("approbation non liée au transfert propriétaire présenté")
        status, priority = a_body.get("approved_status"), a_body.get("approved_priority")
        if status not in INITIAL_STATUSES or priority not in PRIORITIES:
            raise TrustError("statut ou priorité approuvé invalide")
        if PRIORITY_RANK[priority] > PRIORITY_RANK[candidate.requested_priority]:
            raise TrustError("priorité auto-promue au-delà de la demande du candidat")
        _text(a_body.get("approval_id"), "approval_id")
        return t_body, a_body

    def _check_fresh(self, *bodies: dict) -> None:
        now = self._clock()
        for body in bodies:
            self._policy.check_validity(body, now)

    def admit(self, candidate: Candidate, *, owner_transfer: SignedStatement,
              approval: SignedStatement, command_id: str) -> str:
        """Admission atomique et idempotente, y compris après redémarrage.

        `owner_transfer` : transfert explicite signé par un `SOURCE_OWNER`
        autorisé pour (registre, type de source, finalité) (contrat D5B §2).
        `approval` : approbation signée par un `ADMISSION_APPROVER`
        distinct, liée au candidat exact ET au transfert présenté ; statut
        et priorité approuvés sont lus depuis elle (jamais depuis des
        arguments libres). Le seuil de candidature D5B reste celui de
        `GovernedProducer._validate`. L'admission gouvernée n'est PAS la
        décision humaine D5D (non implémentée ici).

        `command_id` identifie la requête de l'appelant (pas la décision) :
        si l'appelant a perdu la réponse après un commit réussi (crash,
        coupure réseau, expiration entre-temps), rejouer `admit` avec le
        même `command_id` et les mêmes énoncés retrouve la `decision_id`
        déjà committée sans dupliquer d'événement.
        """
        self._validator._validate(candidate)  # noqa: SLF001 (réutilisation intentionnelle)
        _text(command_id, "command_id")
        payload = self._validator._payload(candidate)  # noqa: SLF001
        t_body, a_body = self._authenticate(candidate, payload, owner_transfer, approval)
        approved_status = a_body["approved_status"]
        approved_priority = a_body["approved_priority"]
        occurred_at_utc = self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
        _utc(occurred_at_utc)

        key = self._key(candidate)
        key_hash = _digest(key)
        fingerprint = _digest({
            "candidate": payload, "owner_transfer": owner_transfer.digest_material(),
            "approval": approval.digest_material(),
        })

        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Corrige la faille #2 signalée en revue indépendante (PR #316,
                # review_id 5333698547) : la chaîne DOIT être vérifiée AVANT
                # de renvoyer quoi que ce soit depuis `command_results`, sinon
                # une réponse rejouée peut masquer une corruption survenue
                # après l'admission d'origine.
                self._verify_locked(conn)

                existing_cmd = conn.execute(
                    "SELECT decision_id, request_fingerprint FROM command_results "
                    "WHERE command_id = ?",
                    (command_id,),
                ).fetchone()
                if existing_cmd is not None:
                    existing_decision_id, existing_fingerprint = existing_cmd
                    if existing_fingerprint != fingerprint:
                        conn.execute("ROLLBACK")
                        raise ContractError(
                            "rejeu de command_id avec une charge différente de "
                            "la requête d'origine : réponse refusée (pas de "
                            "réponse périmée renvoyée silencieusement)"
                        )
                    conn.execute("COMMIT")
                    return existing_decision_id

                existing_key = conn.execute(
                    "SELECT decision_id, payload_json, sequence, event_hash FROM events "
                    "WHERE idempotency_key = ?", (key_hash,),
                ).fetchone()
                if existing_key is not None:
                    decision_id, payload_json, sequence, event_hash = existing_key
                    stored = json.loads(payload_json)
                    if stored.get("fingerprint") != fingerprint:
                        conn.execute("ROLLBACK")
                        raise ContractError("collision de clé d'admission")
                else:
                    # Nouvel événement : les énoncés doivent être frais. Le
                    # refus a lieu AVANT toute écriture (ROLLBACK par le
                    # gestionnaire d'exception ci-dessous).
                    self._check_fresh(t_body, a_body)
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
                        "admission_approval_ref": a_body["approval_id"],
                        "approver_id": a_body["approver_id"],
                        "owner_id": t_body["owner_id"],
                        "policy_version": a_body["policy_version"],
                        "transfer_id": t_body["transfer_id"],
                        "owner_transfer": owner_transfer.digest_material(),
                        "approval": approval.digest_material(),
                        "evidence_ref_classes": t_body["evidence_ref_classes"],
                        "approved_priority": approved_priority,
                        "requested_priority": candidate.requested_priority,
                        "evidence_refs": list(candidate.evidence_refs),
                        "idempotency_key": key_hash,
                        "previous_event_hash": previous_hash,
                        "candidate": payload,
                        "fingerprint": fingerprint,
                        "command_id": command_id,
                    }
                    # Le hash couvre TOUT le corps (empreinte et commande
                    # d'origine comprises) : l'index est reconstructible et
                    # vérifiable depuis le journal seul.
                    event_hash = _digest(event_body)
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

                # L'accusé de commande référence séquence + event_hash du
                # journal vérifié : une altération de l'index est détectée
                # par `_verify_locked`.
                conn.execute(
                    "INSERT INTO command_results (command_id, decision_id, "
                    "sequence, event_hash, committed_at_utc, request_fingerprint) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (command_id, decision_id, sequence, event_hash,
                     occurred_at_utc, fingerprint),
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
    def _verify_events(conn: sqlite3.Connection) -> dict[int, dict]:
        """Vérifie la chaîne et la cohérence colonnes/charge ; renvoie les corps."""
        rows = conn.execute(
            "SELECT sequence, event_id, decision_id, idempotency_key, event_hash, "
            "previous_event_hash, schema_version, payload_json FROM events "
            "ORDER BY sequence ASC"
        ).fetchall()
        previous = "GENESIS"
        seen_decisions: set[str] = set()
        bodies: dict[int, dict] = {}
        for expected_seq, row in enumerate(rows, 1):
            (sequence, event_id, decision_id, idem, event_hash,
             previous_event_hash, schema_version, payload_json) = row
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
            if not isinstance(body, dict):
                raise CorruptedJournalError("charge utile invalide")
            recomputed = _digest({k: v for k, v in body.items() if k != "event_hash"})
            if (
                previous_event_hash != previous or event_hash != recomputed
                or body.get("event_hash") != event_hash
                or body.get("previous_event_hash") != previous
                or body.get("sequence") != sequence
                or body.get("event_id") != event_id
                or body.get("decision_id") != decision_id
                or body.get("idempotency_key") != idem
                or decision_id in seen_decisions
            ):
                raise CorruptedJournalError("chaîne d'événements invalide")
            seen_decisions.add(decision_id)
            bodies[sequence] = body
            previous = event_hash
        return bodies

    @staticmethod
    def _verify_index(conn: sqlite3.Connection, bodies: Mapping[int, dict]) -> None:
        """Chaque accusé de commande doit pointer vers un événement vérifié."""
        rows = conn.execute(
            "SELECT command_id, decision_id, sequence, event_hash, "
            "request_fingerprint FROM command_results"
        ).fetchall()
        for command_id, decision_id, sequence, event_hash, fingerprint in rows:
            body = bodies.get(sequence)
            if (
                body is None or body.get("event_hash") != event_hash
                or body.get("decision_id") != decision_id
                or body.get("fingerprint") != fingerprint
            ):
                raise CorruptedJournalError(
                    f"index command_results altéré ou orphelin ({command_id!r})"
                )

    def _verify_locked(self, conn: sqlite3.Connection) -> None:
        """Vérifie journal + index dans la transaction en cours (fail-closed)."""
        self._verify_index(conn, self._verify_events(conn))

    def verify(self) -> None:
        """Vérification en lecture seule, hors transaction d'écriture."""
        conn = self._connect()
        try:
            self._verify_locked(conn)
        finally:
            conn.close()

    def rebuild_command_index(self) -> int:
        """Reconstruit `command_results` depuis le journal vérifié seul.

        Une ligne par événement (commande d'origine, liée à séquence +
        event_hash). Les commandes secondaires convergentes (même charge,
        autre `command_id`) ne sont pas dans le journal : leur rejeu
        reconverge par la clé d'idempotence sur la même `decision_id`.
        Renvoie le nombre de lignes reconstruites.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                bodies = self._verify_events(conn)  # index ignoré : il est reconstruit
                conn.execute("DELETE FROM command_results")
                for sequence, body in bodies.items():
                    conn.execute(
                        "INSERT INTO command_results (command_id, decision_id, "
                        "sequence, event_hash, committed_at_utc, request_fingerprint) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (body["command_id"], body["decision_id"], sequence,
                         body["event_hash"], body["occurred_at_utc"], body["fingerprint"]),
                    )
                conn.execute("COMMIT")
                return len(bodies)
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
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

    def _read_events_verified(self) -> tuple[dict, ...]:
        """Lit les événements et vérifie journal + index sous le même instantané.

        Revue indépendante PR #316 (review_id 5333698547), faille #3 : une
        unique transaction de lecture (`BEGIN` en mode WAL) fixe l'instantané
        avant la première lecture ; lecture et vérification voient le même
        état.

        Aucune retenue ici (commentaire propriétaire 5864337478, point 4) :
        la retenue générique sur `sqlite3.DatabaseError` ajoutée pendant le
        diagnostic CI a été RETIRÉE, ce diagnostic ayant été réfuté par
        instrumentation CI directe (runs 36377422947, 36379284990,
        36379739236 : aucune exception SQLite ; cause réelle = monkeypatch
        au niveau classe dans le test, corrigé côté test). Toute erreur
        SQLite remonte et `project()` échoue fermé (`UNKNOWN`).
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            try:
                rows = conn.execute(
                    "SELECT payload_json FROM events ORDER BY sequence ASC"
                ).fetchall()
                self._verify_locked(conn)
            finally:
                conn.execute("COMMIT")
            return tuple(json.loads(r[0]) for r in rows)
        finally:
            conn.close()

    @staticmethod
    def _projected_refs(event: dict) -> list:
        """Références de preuves exposables : tout ce qui n'est pas
        explicitement `PUBLIC` (classé par le propriétaire) est masqué
        (D5B §5, échec fermé). Le journal garde les références brutes ;
        leur lecture passe par `read_sensitive_evidence`."""
        classes = event.get("evidence_ref_classes") or {}
        out: list = []
        for ref in event["evidence_refs"]:
            digest = evidence_ref_digest(ref)
            if classes.get(digest) == EVIDENCE_PUBLIC:
                out.append(ref)
            else:
                out.append({"redacted": True, "ref_digest": digest})
        return out

    def read_sensitive_evidence(self, decision_id: str, *,
                                grant: SignedStatement) -> tuple[str, ...]:
        """Références SENSIBLES d'une décision, sous contrôle d'accès distinct.

        Exige un droit signé par un `EVIDENCE_ACCESS_AUTHORITY` de la
        politique du constructeur, lié à ce journal et à CETTE décision,
        frais (horloge injectée). Le journal est vérifié avant toute
        lecture (échec fermé). Limite : le droit est une capacité au porteur ;
        `accessor_id` est consigné pour audit mais l'authentification réelle
        de l'appelant relève de la future couche d'identité opérateur
        (D5A), hors de ce prototype.
        """
        body, key = self._policy.verify(
            grant, role=EVIDENCE_ACCESS_AUTHORITY, statement_type=EVIDENCE_ACCESS_GRANT,
        )
        self._policy.check_validity(body, self._clock())
        if body.get("authority_id") != key.identity:
            raise TrustError("autorité signée différente de l'identité de la clé")
        _text(body.get("accessor_id"), "accessor_id")
        if body.get("journal_id") != self._journal_id:
            raise TrustError("droit d'accès d'un autre journal")
        if body.get("decision_id") != decision_id:
            raise TrustError("droit d'accès lié à une autre décision")
        for event in self._read_events_verified():
            if event["decision_id"] == decision_id:
                classes = event.get("evidence_ref_classes") or {}
                return tuple(
                    ref for ref in event["evidence_refs"]
                    if classes.get(evidence_ref_digest(ref)) != EVIDENCE_PUBLIC
                )
        raise ContractError("décision inconnue")

    def _unknown(self, reason: str) -> dict:
        return {
            "schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
            "decision_count": None, "items": None, "limitations": [reason],
        }

    def _load_anchor(self) -> tuple[int, int, str] | None:
        conn = self._connect(self._anchor_path)
        try:
            self._init_anchor(conn)
            row = conn.execute(
                "SELECT checkpoint, event_count, head_hash FROM accepted_checkpoint "
                "WHERE journal_id = ?", (self._journal_id,),
            ).fetchone()
        finally:
            conn.close()
        return tuple(row) if row else None

    @staticmethod
    def _anchor_violation(anchor, checkpoint: int, count: int, head: str) -> str | None:
        """Règles anti-retour (ADR-0020 §8) ; `None` si acceptable."""
        if anchor is None:
            return None
        a_cp, a_count, a_head = anchor
        if checkpoint < a_cp:
            return "checkpoint antérieur au dernier accepté (retour arrière)"
        if checkpoint == a_cp and (count, head) != (a_count, a_head):
            return "checkpoint rejoué avec un état différent"
        if checkpoint > a_cp and count < a_count:
            return "journal plus court que le dernier état accepté (troncature)"
        return None

    def _accept_checkpoint(self, checkpoint: int, count: int, head: str) -> str | None:
        """Persiste l'ancre de façon atomique et monotone (vérificateur seul)."""
        conn = self._connect(self._anchor_path)
        try:
            self._init_anchor(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT checkpoint, event_count, head_hash FROM accepted_checkpoint "
                    "WHERE journal_id = ?", (self._journal_id,),
                ).fetchone()
                violation = self._anchor_violation(
                    tuple(row) if row else None, checkpoint, count, head
                )
                if violation is None and (row is None or checkpoint > row[0]):
                    conn.execute(
                        "INSERT OR REPLACE INTO accepted_checkpoint (journal_id, "
                        "checkpoint, event_count, head_hash, accepted_at_utc) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (self._journal_id, checkpoint, count, head,
                         self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")),
                    )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return violation

    def project(self, attestation: SignedStatement | None = None) -> dict:
        """Reconstruit la projection à partir du journal seul (fail-closed).

        `AVAILABLE` exige une attestation signée par un
        `AVAILABILITY_AUTHORITY` de la politique du constructeur, fraîche
        (horloge injectée), liée à ce journal (`journal_id`, périmètre,
        schéma), complète (`event_count`, `head_hash` égaux au journal
        vérifié) et monotone (checkpoint >= dernier accepté, persisté par le
        vérificateur). Le zéro explicite n'est possible qu'à ces conditions.
        """
        try:
            events = self._read_events_verified()
        except (CorruptedJournalError, IntegrityError, sqlite3.DatabaseError,
                json.JSONDecodeError):
            return self._unknown("integrity_failure")
        count = len(events)
        head = events[-1]["event_hash"] if events else "GENESIS"

        # Anti-retour indépendant de toute attestation : le journal réel doit
        # prolonger le dernier état accepté (préfixe identique).
        anchor = self._load_anchor()
        if anchor is not None:
            _, a_count, a_head = anchor
            prefix_head = events[a_count - 1]["event_hash"] if a_count and count >= a_count else (
                "GENESIS" if a_count == 0 else None
            )
            if count < a_count or prefix_head != a_head:
                return self._unknown(
                    "retour arrière détecté : le journal ne prolonge pas le "
                    "dernier checkpoint accepté (troncature ou réécriture)"
                )

        if attestation is None:
            return {
                "schema_version": SCHEMA_VERSION, "availability": "NON DÉPLOYÉ",
                "decision_count": None, "items": None,
                "limitations": ["aucune attestation de disponibilité"],
            }
        if isinstance(attestation, AvailabilityProof) or not isinstance(attestation, SignedStatement):
            return self._unknown(
                "preuve non authentifiée refusée : seule une attestation signée "
                "par AVAILABILITY_AUTHORITY peut produire AVAILABLE (ADR-0020)"
            )
        try:
            body, key = self._policy.verify(
                attestation, role=AVAILABILITY_AUTHORITY,
                statement_type=AVAILABILITY_ATTESTATION,
            )
            self._policy.check_validity(body, self._clock())
            if body.get("authority_id") != key.identity:
                raise TrustError("autorité signée différente de l'identité de la clé")
            _text(body.get("deployment_evidence_ref"), "deployment_evidence_ref")
        except (TrustError, ContractError) as exc:
            return self._unknown(f"attestation refusée : {exc}")

        checkpoint = body.get("checkpoint")
        if body.get("journal_id") != self._journal_id:
            return self._unknown("attestation d'un autre journal (substitution)")
        if body.get("scope") != JOURNAL_SCOPE or body.get("schema_version") != SCHEMA_VERSION:
            return self._unknown("périmètre ou version de schéma non attestés")
        if type(checkpoint) is not int or checkpoint < 1:
            return self._unknown("checkpoint invalide")
        if type(body.get("event_count")) is not int or body["event_count"] != count:
            return self._unknown("attestation incomplète : nombre d'événements différent")
        if body.get("head_hash") != head:
            return self._unknown("attestation incomplète : hash de tête différent")
        violation = self._accept_checkpoint(checkpoint, count, head)
        if violation is not None:
            return self._unknown(f"anti-retour : {violation}")

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
                    "evidence_refs": self._projected_refs(e),
                    "sensitive_refs_redacted": sum(
                        1 for r in self._projected_refs(e) if isinstance(r, dict)
                    ),
                    "source_hashes": [c["source_sha"]],
                    "tests": None, "ci": None, "review": c["upstream_approval_ref"],
                    "limitations": [
                        "politique de confiance FIXTURE non opérationnelle (ADR-0020 §3)"
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
            "availability": "AVAILABLE", "generated_at_utc": body["issued_at_utc"],
            "deployment_evidence_ref": body["deployment_evidence_ref"],
            "journal_id": self._journal_id, "checkpoint": checkpoint,
            "attested_by": body["authority_id"],
            "policy_version": body["policy_version"],
            "as_of_event_version": count, "head_hash": head,
            "decision_count": len(items), "counts_by_status": counts,
            "items": items, "limitations": [
                "politique de confiance FIXTURE non opérationnelle : aucune "
                "autorité réelle désignée (ADR-0020 §3, blocage de certification)"
            ],
            "projection_hash": _digest(items),
        }


__all__ = [
    "AvailabilityProof", "CorruptedJournalError", "DurableGovernedStore",
    "EVIDENCE_PUBLIC", "EVIDENCE_SENSITIVE", "JOURNAL_SCOPE", "SCHEMA_VERSION",
    "admission_approval_payload", "availability_attestation_payload",
    "candidate_fingerprint", "evidence_access_grant_payload",
    "evidence_ref_digest", "owner_transfer_payload", "transfer_digest",
]
