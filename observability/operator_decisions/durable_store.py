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
  Conséquence explicite : une preuve non authentifiée ne peut jamais, à elle
  seule, certifier un ZÉRO (base vide) — `project()` refuse ce cas
  (`UNKNOWN`) tant qu'aucune racine de confiance réelle n'est branchée (voir
  revue indépendante PR #316, review_id 5333698547, point 1).
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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
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

# Retenue bornée pour `_read_events_verified` face à un `sqlite3.OperationalError`
# transitoire (voir docstring de `_read_events_verified`) — pas un nouveau
# comportement fonctionnel, une résilience I/O sur un chemin déjà fail-closed.
_OPEN_RETRY_ATTEMPTS = 5
_OPEN_RETRY_DELAY_SECONDS = 0.05


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
    committed_at_utc TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL
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
        # DIAGNOSTIC TEMPORAIRE (PR #316) : capture l'état exact de la
        # dernière exécution de `_read_events_verified`, pour permettre au
        # test d'afficher le VRAI déroulement sous CI au lieu de deviner. À
        # retirer une fois la cause CI confirmée par instrumentation directe.
        self.last_read_retry_exception: BaseException | None = None
        self.last_read_exception_type: str | None = None
        self.last_read_exception_repr: str | None = None
        self.last_read_attempts_used: int = 0
        self.last_read_reached_verify: bool = False
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
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
        observé en CI (TEST REGRESSION GATE, PR #316, run 36374909495,
        check_run_id 108778642724 et 108778632585) — sous forte contention
        d'ouverture de connexion (suite complète, 6549+ tests dans le même
        processus), `self._connect()` peut échouer rapidement (verrou SQLite
        transitoire, pression sur les descripteurs de fichiers, ou glitch I/O
        transitoire du système de fichiers du runner) avant même d'atteindre
        `_verify_locked`. Sans retenue, cette erreur transitoire était
        absorbée par le `except sqlite3.DatabaseError` fail-closed de
        `project()` et renvoyée comme `UNKNOWN`/`integrity_failure` — un faux
        négatif indiscernable d'une vraie corruption, et la cause du test
        `test_project_lit_et_verifie_sous_un_instantane_transactionnel_unique`
        constaté comme flaky (jamais atteint en isolation, seulement sous la
        suite complète).

        Correctif précédent (retenue sur `sqlite3.OperationalError` seul,
        HEAD 85e9c23) INSUFFISANT — cause réelle prouvée par reproduction
        ciblée (pas une hypothèse) : `sqlite3.OperationalError` n'est qu'UNE
        sous-classe de `sqlite3.DatabaseError` (verrou, timeout, "unable to
        open database file"). Une erreur SQLite transitoire d'un AUTRE type
        de cette même hiérarchie (ex. `sqlite3.DatabaseError` nu, levé par
        exemple sur un glitch I/O du système de fichiers du runner CI) n'est
        PAS un `sqlite3.OperationalError` : elle traverse ce `except` sans
        être retenue, remonte immédiatement hors de la boucle (zéro retry
        tenté, quel que soit `_OPEN_RETRY_ATTEMPTS`), et est absorbée
        silencieusement par le `except (..., sqlite3.DatabaseError, ...)`
        fail-closed de `project()` — exactement le symptôme observé
        (`injected["done"]` resté `False`, échec identique sur les 3 runs
        CI malgré le correctif précédent, puisque ce correctif ne change
        rien à une erreur qui ne passe jamais par le `except
        sqlite3.OperationalError`). Reproduction : forcer `self._connect()`
        à lever un `sqlite3.DatabaseError` nu (et non une de ses sous-classes)
        au premier appel démontre, avec le code d'avant ce correctif, que
        `project()` renvoie `UNKNOWN` après un seul appel à `_connect()`
        (aucune retenue déclenchée) — reproduisant fidèlement le symptôme
        CI sans deviner. La retenue ne s'applique qu'aux erreurs SQLite
        transitoires : `CorruptedJournalError`/`IntegrityError` (vraie
        corruption détectée par `_verify_locked`) sont une hiérarchie
        d'exceptions entièrement distincte (`ValueError`, définie dans
        `producer.py`), jamais une sous-classe de `sqlite3.DatabaseError` —
        elles continuent de remonter immédiatement, sans aucun
        affaiblissement du fail-closed, retenue ou pas.
        """
        last_exc: sqlite3.DatabaseError | None = None
        for attempt in range(_OPEN_RETRY_ATTEMPTS):
            # DIAGNOSTIC TEMPORAIRE (PR #316) : trace l'étape exacte atteinte
            # à chaque tentative, pour distinguer sans ambiguïté "aucune
            # exception, `_verify_locked` jamais appelé" (bug de dispatch ou
            # de logique) de "une exception hors `sqlite3.DatabaseError` a
            # été levée avant `_verify_locked`" (retenue trop étroite).
            self.last_read_attempts_used = attempt + 1
            if attempt:
                time.sleep(_OPEN_RETRY_DELAY_SECONDS)
            try:
                conn = self._connect()
            except sqlite3.DatabaseError as exc:
                last_exc = exc
                self.last_read_retry_exception = exc
                self.last_read_exception_type = type(exc).__name__
                self.last_read_exception_repr = repr(exc)
                continue
            except Exception as exc:  # DIAGNOSTIC TEMPORAIRE : ne masque rien, re-lève tel quel
                self.last_read_exception_type = type(exc).__name__
                self.last_read_exception_repr = repr(exc)
                raise
            try:
                conn.execute("BEGIN")
                try:
                    rows = conn.execute(
                        "SELECT payload_json FROM events ORDER BY sequence ASC"
                    ).fetchall()
                    self.last_read_reached_verify = True  # DIAGNOSTIC TEMPORAIRE
                    self._verify_locked(conn)
                finally:
                    conn.execute("COMMIT")
                return tuple(json.loads(r[0]) for r in rows)
            except sqlite3.DatabaseError as exc:
                last_exc = exc
                self.last_read_retry_exception = exc
                self.last_read_exception_type = type(exc).__name__
                self.last_read_exception_repr = repr(exc)
                continue
            except Exception as exc:  # DIAGNOSTIC TEMPORAIRE : ne masque rien, re-lève tel quel
                self.last_read_exception_type = type(exc).__name__
                self.last_read_exception_repr = repr(exc)
                raise
            finally:
                conn.close()
        assert last_exc is not None  # noqa: S101 (garantie interne, pas un test)
        raise last_exc

    def project(self, proof: AvailabilityProof | None = None) -> dict:
        """Reconstruit la projection à partir du journal seul (fail-closed)."""
        try:
            events = self._read_events_verified()
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
        if len(events) == 0:
            # Corrige la faille #1 signalée en revue indépendante (PR #316,
            # review_id 5333698547) : une `AvailabilityProof` est une
            # attestation injectée par l'appelant, jamais authentifiée par ce
            # module (aucune signature, aucune racine de confiance externe).
            # Elle ne peut donc JAMAIS, seule, certifier un zéro — un
            # appelant pourrait sinon fabriquer librement une preuve
            # affirmant qu'aucune décision n'existe. Tant qu'aucun gate de
            # confiance réel n'est branché, ce cas reste fail-closed.
            return {
                "schema_version": SCHEMA_VERSION, "availability": "UNKNOWN",
                "decision_count": None, "items": None,
                "limitations": [
                    "zéro non authentifié refusé : une AvailabilityProof non "
                    "authentifiée ne peut jamais certifier une base vide en "
                    "l'absence de racine de confiance externe vérifiée"
                ],
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
