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
    PRIORITY_RANK,
    SignedStatement,
    TrustError,
    TrustPolicy,
)

SCHEMA_VERSION = "2.0.0"
JOURNAL_SCOPE = "OPERATOR_DECISION_QUEUE"
KNOWN_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

# Retenue bornée pour `_read_events_verified` face à un `sqlite3.OperationalError`
# transitoire (voir docstring de `_read_events_verified`) — pas un nouveau
# comportement fonctionnel, une résilience I/O sur un chemin déjà fail-closed.
_OPEN_RETRY_ATTEMPTS = 5
_OPEN_RETRY_DELAY_SECONDS = 0.05


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


def admission_approval_payload(
    candidate: Candidate, *, policy_version: str, approver_id: str,
    approved_status: str, approved_priority: str, transfer_ref: str,
    approval_id: str, issued_at_utc: str, expires_at_utc: str,
) -> dict:
    """Construit la charge d'une approbation d'admission (à signer HORS store).

    Simple constructeur de données : une charge non signée n'a aucune
    autorité. Seule `TrustPolicy.verify` (politique du constructeur du store)
    lui en confère une.
    """
    return {
        "statement_type": ADMISSION_APPROVAL,
        "policy_version": policy_version,
        "approval_id": approval_id,
        "approver_id": approver_id,
        "candidate_fingerprint": candidate_fingerprint(
            GovernedProducer._payload(candidate)  # noqa: SLF001
        ),
        "owner_registry": candidate.owner_registry,
        "source_type": candidate.source_type,
        "source_id": candidate.source_id,
        "owner_record_version": candidate.owner_record_version,
        "source_sha": candidate.source_sha,
        "decision_purpose": candidate.decision_purpose,
        "approved_status": approved_status,
        "approved_priority": approved_priority,
        "transfer_ref": transfer_ref,
        "issued_at_utc": issued_at_utc,
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
        self._anchor_path = str(anchor_path) if anchor_path is not None else self._db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self, path: str | None = None) -> sqlite3.Connection:
        conn = sqlite3.connect(path or self._db_path, timeout=30, isolation_level=None)
        # `busy_timeout` explicite (en plus de `timeout=` ci-dessus, qui règle
        # la même chose côté wrapper Python) : le changement de mode journal
        # ci-dessous exige un verrou exclusif bref, et sous forte contention
        # (admissions concurrentes, ou suite de tests complète avec de
        # nombreux threads SQLite actifs) l'échec observé en CI
        # (`sqlite3.OperationalError: database is locked` sur cette ligne,
        # cf. échec CI PR #316 sur TEST REGRESSION GATE) montre que la
        # retenue par défaut peut ne pas suffire tant que le PRAGMA n'a pas
        # explicitement son propre délai d'attente.
        conn.execute("PRAGMA busy_timeout=30000")
        # N'exécute le changement de mode que s'il est nécessaire : une fois
        # la base déjà en WAL (cas de toute connexion après la première),
        # réémettre `PRAGMA journal_mode=WAL` est un no-op côté résultat mais
        # peut encore solliciter un verrou bref sur certaines versions de
        # SQLite — l'éviter réduit la fenêtre de contention sans changer le
        # comportement fonctionnel du prototype.
        current_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if str(current_mode).lower() != "wal":
            # Reproduit localement (hors CI, 5 threads créant chacun leur
            # propre `DurableGovernedStore` sur le même fichier neuf) :
            # `sqlite3.OperationalError: database is locked` précisément sur
            # `PRAGMA journal_mode=WAL`, malgré `busy_timeout=30000` déjà
            # posé sur CETTE connexion. Cause réelle (pas une hypothèse) :
            # le changement de mode journal exige un verrou EXCLUSIF bref
            # pendant que la première écriture crée le fichier `-wal`/`-shm`
            # ; sous plusieurs connexions concurrentes exécutant ce PRAGMA au
            # même instant sur un fichier tout juste créé, SQLite peut
            # renvoyer `SQLITE_BUSY` sur CE PRAGMA précis avant même que le
            # compteur `busy_timeout` de l'appelant n'ait une fenêtre pour
            # s'appliquer côté verrou de création de fichier (comportement
            # documenté de SQLite sur le changement de journal_mode, distinct
            # du verrou de transaction ordinaire). La retenue bornée ici est
            # symétrique à celle de `_read_events_verified` : seule une
            # `sqlite3.OperationalError` transitoire est retentée, jamais un
            # signe de corruption.
            last_exc: sqlite3.OperationalError | None = None
            for attempt in range(_OPEN_RETRY_ATTEMPTS):
                if attempt:
                    time.sleep(_OPEN_RETRY_DELAY_SECONDS)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    last_exc = exc
                    continue
            else:
                raise last_exc
        conn.execute("PRAGMA foreign_keys=ON")
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

    def _verify_approval(self, candidate: Candidate, payload: dict,
                         approval: object) -> dict:
        """Vérifie l'approbation signée contre la politique du constructeur.

        Aucune écriture n'a lieu avant la fin de cette méthode : tout échec
        lève `TrustError`/`ContractError` sans toucher au journal.
        """
        body, key = self._policy.verify(
            approval, role=ADMISSION_APPROVER, statement_type=ADMISSION_APPROVAL,
        )
        self._policy.check_validity(body, self._clock())
        if body.get("approver_id") != key.identity:
            raise TrustError("l'approbateur signé ne correspond pas à l'identité de la clé")
        if candidate.owner_registry not in key.scopes:
            raise TrustError("approbateur non autorisé pour ce propriétaire source")
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
                    f"approbation non liée au candidat présenté ({name}) : "
                    "substitution, source remplacée ou obsolète"
                )
        status, priority = body.get("approved_status"), body.get("approved_priority")
        if status not in INITIAL_STATUSES or priority not in PRIORITIES:
            raise TrustError("statut ou priorité approuvé invalide")
        if PRIORITY_RANK[priority] > PRIORITY_RANK[candidate.requested_priority]:
            raise TrustError("priorité auto-promue au-delà de la demande du candidat")
        _text(body.get("transfer_ref"), "transfer_ref")
        _text(body.get("approval_id"), "approval_id")
        return body

    def admit(self, candidate: Candidate, *, approval: SignedStatement,
              command_id: str) -> str:
        """Admission atomique et idempotente, y compris après redémarrage.

        `approval` est une approbation signée par un `ADMISSION_APPROVER` de
        la politique du constructeur ; statut et priorité approuvés sont lus
        depuis elle (jamais depuis des arguments libres). Le seuil de
        candidature D5B reste celui de `GovernedProducer._validate`.
        L'admission gouvernée n'est PAS la décision humaine D5D (non
        implémentée ici).

        `command_id` identifie la requête de l'appelant (pas la décision) :
        si l'appelant a perdu la réponse après un commit réussi (crash,
        coupure réseau), rejouer `admit` avec le même `command_id` retrouve
        la `decision_id` déjà committée sans dupliquer d'événement.
        """
        self._validator._validate(candidate)  # noqa: SLF001 (réutilisation intentionnelle)
        _text(command_id, "command_id")
        payload = self._validator._payload(candidate)  # noqa: SLF001
        body = self._verify_approval(candidate, payload, approval)
        approved_status = body["approved_status"]
        approved_priority = body["approved_priority"]
        occurred_at_utc = self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
        _utc(occurred_at_utc)

        key = self._key(candidate)
        key_hash = _digest(key)
        fingerprint = _digest({
            "candidate": payload, "approval": approval.digest_material(),
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
                        "admission_approval_ref": body["approval_id"],
                        "approver_id": body["approver_id"],
                        "policy_version": body["policy_version"],
                        "transfer_ref": body["transfer_ref"],
                        "approval": approval.digest_material(),
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
                    "sequence, committed_at_utc, request_fingerprint) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (command_id, decision_id, sequence, occurred_at_utc, fingerprint),
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

    def _read_events_verified(self) -> tuple[dict, ...]:
        """Lit les événements et vérifie la chaîne sous le même instantané.

        Corrige la faille #3 signalée en revue indépendante (PR #316, review_id
        5333698547) : `events()` et `verify()` ouvraient chacun leur propre
        connexion/transaction, ce qui laissait une fenêtre où une admission
        concurrente pouvait s'intercaler entre la lecture des événements et
        leur vérification. Ici, une unique transaction de lecture SQLite
        (`BEGIN` en mode WAL) fixe l'instantané avant la première lecture ;
        les deux opérations voient donc strictement le même état, quoi qu'il
        se passe sur une autre connexion pendant ce temps.

        Retenue bornée sur `sqlite3.DatabaseError` (`_OPEN_RETRY_ATTEMPTS`) :
        résilience défensive raisonnable face à une contention SQLite
        transitoire réelle (verrou, ouverture de fichier) sous forte charge.

        MISE EN GARDE (PR #316, historique de diagnostic) : les deux premiers
        correctifs sur cette méthode (retenue sur `sqlite3.OperationalError`
        puis élargie à `sqlite3.DatabaseError`) partaient de l'hypothèse que
        le flaking CI de
        `test_project_lit_et_verifie_sous_un_instantane_transactionnel_unique`
        venait d'une exception SQLite transitoire non retenue avant
        `_verify_locked`. Cette hypothèse n'a JAMAIS été confirmée par une
        trace CI directe (seulement plausible par injection forcée locale) et
        s'est avérée FAUSSE : une instrumentation CI directe (runs
        36377422947, 36379284990, 36379739236) a prouvé que `_connect()` et
        le `SELECT` réussissaient toujours sans aucune exception, que
        `_verify_locked` était bien atteint et appelé, et que le callable
        réellement invoqué était l'implémentation ORIGINALE de la classe —
        jamais le remplacement posé par
        `monkeypatch.setattr(DurableGovernedStore, "_verify_locked", ...)`
        du test. La cause réelle n'était donc pas dans cette méthode : le
        monkeypatch au niveau CLASSE ne prenait pas effet de façon fiable
        dans l'environnement CI (suite complète, 6549+ tests dans le même
        processus), jamais reproduit en isolation locale. Le correctif est
        côté test (monkeypatch au niveau INSTANCE, voir
        `tests/test_web_dir_d5b_r2_durable_store.py`), pas ici. La retenue
        `sqlite3.DatabaseError` ci-dessous reste néanmoins une défense
        raisonnable contre une vraie contention transitoire, sans rapport
        avec ce flaking précis. `CorruptedJournalError`/`IntegrityError`
        (vraie corruption détectée par `_verify_locked`) restent une
        hiérarchie d'exceptions entièrement distincte (`ValueError`, définie
        dans `producer.py`), jamais une sous-classe de
        `sqlite3.DatabaseError` — elles continuent de remonter immédiatement,
        sans aucun affaiblissement du fail-closed, retenue ou pas.
        """
        last_exc: sqlite3.DatabaseError | None = None
        for attempt in range(_OPEN_RETRY_ATTEMPTS):
            if attempt:
                time.sleep(_OPEN_RETRY_DELAY_SECONDS)
            try:
                conn = self._connect()
            except sqlite3.DatabaseError as exc:
                last_exc = exc
                continue
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
            except sqlite3.DatabaseError as exc:
                last_exc = exc
                continue
            finally:
                conn.close()
        assert last_exc is not None  # noqa: S101 (garantie interne, pas un test)
        raise last_exc

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
                    "evidence_refs": list(e["evidence_refs"]),
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
    "JOURNAL_SCOPE", "SCHEMA_VERSION", "admission_approval_payload",
    "availability_attestation_payload", "candidate_fingerprint",
]
