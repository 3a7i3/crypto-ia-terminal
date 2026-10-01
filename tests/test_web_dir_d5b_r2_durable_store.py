"""Vérifications R2 : stockage durable hors runtime, isolé (fixtures uniquement).

Aucun test ici ne touche au runtime PAPER, à un JSONL réel, à Telegram, à
l'exchange ou à un service déployé. La base SQLite est un fichier temporaire
créé et détruit par chaque test.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from observability.operator_decisions.durable_store import (
    EVIDENCE_PUBLIC, EVIDENCE_SENSITIVE, AvailabilityProof,
    CorruptedJournalError, DurableGovernedStore, admission_approval_payload,
    availability_attestation_payload, evidence_access_grant_payload,
    evidence_ref_digest, owner_transfer_payload, transfer_digest,
)
from observability.operator_decisions.producer import Candidate, ContractError
from observability.operator_decisions.trust import (
    ADMISSION_APPROVER, AVAILABILITY_AUTHORITY, EVIDENCE_ACCESS_AUTHORITY,
    SOURCE_OWNER, TrustError, TrustPolicy, sign_statement, trusted_key,
)

NOW = "2026-09-28T03:00:00Z"
NOW_DT = datetime(2026, 9, 28, 3, 0, 0, tzinfo=timezone.utc)

# --- Fixtures de confiance NON OPÉRATIONNELLES (ADR-0020 §4) -----------------
# Clés générées à la volée pour ce module de test, jamais persistées, jamais
# réutilisables hors test. Elles ne représentent AUCUNE autorité réelle.
FIXTURE_NON_OPERATIONNELLE = True
APPROVER_SK = Ed25519PrivateKey.generate()
AUTHORITY_SK = Ed25519PrivateKey.generate()
OWNER_SK = Ed25519PrivateKey.generate()
ACCESS_SK = Ed25519PrivateKey.generate()
ROGUE_SK = Ed25519PrivateKey.generate()
POLICY_VERSION = "fixture-policy-v1"
GRANT = ("problem-registry", "PROBLEM", "planifier")
APPROVER_KEY = trusted_key(
    APPROVER_SK, "fixture-approver-1", ADMISSION_APPROVER,
    "fixture:approbateur-problem", grants=(GRANT,),
)
OWNER_KEY = trusted_key(
    OWNER_SK, "fixture-owner-1", SOURCE_OWNER,
    "fixture:proprietaire-problem", grants=(GRANT,),
)
AUTHORITY_KEY = trusted_key(
    AUTHORITY_SK, "fixture-authority-1", AVAILABILITY_AUTHORITY,
    "fixture:autorite-disponibilite",
)
ACCESS_KEY = trusted_key(
    ACCESS_SK, "fixture-access-1", EVIDENCE_ACCESS_AUTHORITY,
    "fixture:autorite-acces-preuves",
)


def policy(**overrides) -> TrustPolicy:
    base = dict(
        policy_version=POLICY_VERSION,
        keys=(OWNER_KEY, APPROVER_KEY, AUTHORITY_KEY, ACCESS_KEY),
    )
    base.update(overrides)
    return TrustPolicy(**base)


class Clock:
    """Horloge injectée et pilotable (ADR-0020 §9)."""

    def __init__(self, now: datetime = NOW_DT):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate(**overrides) -> Candidate:
    base = dict(
        candidate_id="cand-1", candidate_revision=1,
        source_type="PROBLEM", source_id="problem-1",
        source_ref="governed:problem-1:v1", source_sha="a" * 64,
        source_generated_at_utc=NOW, producer="problem-registry",
        producer_authority="GOVERNED_SOURCE", owner_registry="problem-registry",
        owner_record_version="v1", decision_type="PROPOSED_EVOLUTION",
        title="Corriger une lacune", summary="Dossier relu",
        proposed_change="Planifier une correction future",
        decision_purpose="planifier", requested_status="TO_PLAN",
        requested_priority="MEDIUM", evidence_status="VERIFIED",
        evidence_refs=("artifact:sha256:abc",), upstream_approval_ref="review:1",
        risk="Risque circonscrit", validation="Revue indépendante",
        rollback="Annuler dans une phase future",
    )
    base.update(overrides)
    return Candidate(**base)


def anchor_of(path) -> Path:
    """Ancre anti-retour dans un fichier DISTINCT du journal (défaut exigé)."""
    return Path(str(path) + ".anchor")


def store(path, *, trust_policy: TrustPolicy | None = None, clock=None,
          **kwargs) -> DurableGovernedStore:
    kwargs.setdefault("anchor_path", anchor_of(path))
    return DurableGovernedStore(
        path, {"PROBLEM": "problem-registry"},
        trust_policy=trust_policy or policy(), clock=clock or Clock(), **kwargs,
    )


def default_classes(c: Candidate) -> dict:
    return {evidence_ref_digest(r): EVIDENCE_PUBLIC for r in c.evidence_refs}


def transfer(c: Candidate, *, sk=OWNER_SK, key_id="fixture-owner-1", **overrides):
    """Transfert propriétaire signé par le propriétaire FIXTURE non opérationnel."""
    fields = dict(
        policy_version=POLICY_VERSION, owner_id="fixture:proprietaire-problem",
        transfer_id="transfert-1", evidence_ref_classes=default_classes(c),
        issued_at_utc=_iso(NOW_DT - timedelta(minutes=1)),
        expires_at_utc=_iso(NOW_DT + timedelta(minutes=30)),
    )
    payload_overrides = {k: overrides.pop(k) for k in list(overrides) if k not in fields}
    fields.update(overrides)
    payload = owner_transfer_payload(c, **fields)
    payload.update(payload_overrides)
    return sign_statement(sk, key_id, payload)


def approval(c: Candidate, *, sk=APPROVER_SK, key_id="fixture-approver-1",
             owner_transfer=None, **overrides):
    fields = dict(
        policy_version=POLICY_VERSION, approver_id="fixture:approbateur-problem",
        approved_status="TO_PLAN", approved_priority="MEDIUM",
        owner_transfer_digest=transfer_digest(owner_transfer or transfer(c)),
        approval_id="approbation-1", issued_at_utc=_iso(NOW_DT - timedelta(minutes=1)),
        expires_at_utc=_iso(NOW_DT + timedelta(minutes=30)),
    )
    payload_overrides = {k: overrides.pop(k) for k in list(overrides) if k not in fields}
    fields.update(overrides)
    payload = admission_approval_payload(c, **fields)
    payload.update(payload_overrides)
    return sign_statement(sk, key_id, payload)


def journal_state(s: DurableGovernedStore) -> tuple[int, str]:
    """Compte et hash de tête lus directement sur disque (côté autorité fixture)."""
    conn = sqlite3.connect(s._db_path, timeout=30)  # noqa: SLF001
    try:
        rows = conn.execute("SELECT event_hash FROM events ORDER BY sequence").fetchall()
    finally:
        conn.close()
    return len(rows), (rows[-1][0] if rows else "GENESIS")


def attest(s: DurableGovernedStore, checkpoint: int = 1, *, sk=AUTHORITY_SK,
           key_id="fixture-authority-1", **overrides):
    """Attestation signée par l'autorité FIXTURE non opérationnelle."""
    count, head = journal_state(s)
    fields = dict(
        policy_version=POLICY_VERSION, authority_id="fixture:autorite-disponibilite",
        journal_id=s.journal_id, checkpoint=checkpoint, event_count=count,
        head_hash=head, issued_at_utc=_iso(NOW_DT - timedelta(minutes=1)),
        expires_at_utc=_iso(NOW_DT + timedelta(minutes=10)),
        deployment_evidence_ref="fixture:deploy-audit:sha256:abc",
    )
    fields.update(overrides)
    return sign_statement(sk, key_id, availability_attestation_payload(**fields))


def admit(s: DurableGovernedStore, c: Candidate, command_id: str = "cmd-1",
          appr=None, tr=None) -> str:
    tr = tr or transfer(c)
    return s.admit(
        c, owner_transfer=tr, approval=appr or approval(c, owner_transfer=tr),
        command_id=command_id,
    )


# --- Admission atomique et idempotence -------------------------------------

def test_deux_admissions_identiques_simultanees_convergent(tmp_path):
    db = tmp_path / "store.db"
    s1 = store(db)
    results: list[str] = []
    errors: list[Exception] = []

    def run(command_id):
        try:
            results.append(admit(store(db), candidate(), command_id=command_id))
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(f"cmd-{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(set(results)) == 1  # une seule decision_id malgré 5 requêtes concurrentes
    assert len(s1.events()) == 1


def test_deux_admissions_conflictuelles_simultanees_une_seule_gagne(tmp_path):
    db = tmp_path / "store.db"
    winners: list[str] = []
    losers: list[Exception] = []

    def run(title, command_id):
        try:
            winners.append(admit(store(db), candidate(title=title), command_id=command_id))
        except ContractError as exc:
            losers.append(exc)

    threads = [
        threading.Thread(target=run, args=("Titre A", "cmd-a")),
        threading.Thread(target=run, args=("Titre B", "cmd-b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1
    assert len(losers) == 1
    assert "collision" in str(losers[0])
    assert len(store(db).events()) == 1


def test_reponse_perdue_apres_commit_est_retrouvee_sans_duplication(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    first = admit(s, candidate(), command_id="cmd-lost")
    # L'appelant "perd" la réponse (timeout réseau) et rejoue la même commande.
    replay = store(db)
    second = admit(replay, candidate(), command_id="cmd-lost")
    assert first == second
    assert len(store(db).events()) == 1


# --- Crash simulé ------------------------------------------------------------

def test_crash_avant_commit_ne_laisse_aucune_trace(tmp_path):
    db = tmp_path / "store.db"
    store(db)  # initialise le schéma avant la manipulation SQL directe
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO events (sequence, event_id, decision_id, schema_version, "
        "idempotency_key, previous_event_hash, event_hash, payload_json) "
        "VALUES (1, 'ev-1', 'dec-1', '1.0.0', 'key-1', 'GENESIS', 'hash-1', '{}')"
    )
    # "Crash" : la connexion est détruite sans COMMIT explicite ; SQLite
    # annule la transaction en cours (aucune écriture n'a atteint le fichier).
    conn.close()

    recovered = store(db)
    assert recovered.events() == ()
    assert recovered.project()["availability"] == "NON DÉPLOYÉ"


def test_crash_apres_commit_avant_reponse_est_durable_et_rejouable(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    decision_id = admit(s, candidate(), command_id="cmd-crash-after")
    # Le process s'arrête juste après le COMMIT, avant de renvoyer la réponse
    # à l'appelant (aucune fermeture explicite nécessaire : les données sont
    # déjà sur disque grâce au COMMIT).
    recovered = store(db)
    assert len(recovered.events()) == 1
    replay = admit(recovered, candidate(), command_id="cmd-crash-after")
    assert replay == decision_id
    assert len(recovered.events()) == 1  # pas de doublon


# --- Reconstruction de la projection depuis le journal seul ------------------

def test_projection_reconstruite_uniquement_depuis_le_journal(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")

    fresh = store(db)  # nouvelle instance, aucun état en mémoire partagé
    view = fresh.project(attest(fresh))
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 2
    assert view == fresh.project(attest(fresh))  # déterministe


# --- Corruption, réordonnancement, troncature : échec fermé ------------------

def _raw(db):
    return sqlite3.connect(str(db), isolation_level=None)


def test_corruption_du_journal_echoue_ferme(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
    conn.close()

    corrupted = store(db)
    view = corrupted.project(attest(corrupted))
    assert view["availability"] == "UNKNOWN"
    assert view["decision_count"] is None
    with pytest.raises(CorruptedJournalError):
        corrupted.verify()


def test_reordonnancement_du_journal_echoue_ferme(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    conn = _raw(db)
    rows = conn.execute("SELECT sequence, event_hash FROM events ORDER BY sequence").fetchall()
    # Inverse les previous_event_hash pour simuler un réordonnancement.
    conn.execute("UPDATE events SET previous_event_hash = ? WHERE sequence = 2",
                 (rows[1][1],))
    conn.close()

    corrupted = store(db)
    assert corrupted.project(attest(corrupted))["availability"] == "UNKNOWN"


def test_troncature_du_journal_echoue_ferme(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    conn = _raw(db)
    conn.execute("DELETE FROM events WHERE sequence = 1")  # trou de séquence
    conn.close()

    corrupted = store(db)
    assert corrupted.project(attest(corrupted))["availability"] == "UNKNOWN"
    with pytest.raises(CorruptedJournalError):
        corrupted.verify()


def test_corruption_avant_rejeu_de_command_id_est_detectee_pas_masquee(tmp_path):
    """Revue indépendante PR #316 (review_id 5333698547), point 2.

    Après une admission réussie, si `events.payload_json` est altéré en
    base, un rejeu du même `command_id` ne doit PAS renvoyer silencieusement
    la `decision_id` connue depuis `command_results` : la chaîne doit être
    vérifiée AVANT toute réponse issue de `command_results`, donc la
    corruption doit être détectée en premier.
    """
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
    conn.close()

    replayer = store(db)
    with pytest.raises(CorruptedJournalError):
        admit(replayer, candidate(), command_id="cmd-1")


def test_rejeu_de_command_id_avec_charge_differente_est_rejete(tmp_path):
    """Revue indépendante PR #316 (review_id 5333698547), point 2.

    Le `command_id` est désormais lié à une empreinte de la requête
    d'origine : rejouer le même `command_id` avec une charge différente
    (ex: un autre `title`) doit être rejeté explicitement, jamais renvoyer
    silencieusement une réponse périmée qui ne correspond pas à la nouvelle
    requête.
    """
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(title="Titre initial"), command_id="cmd-shared")

    with pytest.raises(ContractError, match="rejeu de command_id"):
        admit(s, candidate(title="Titre modifié"), command_id="cmd-shared")


def test_version_de_schema_inconnue_est_rejetee(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET schema_version = '9.9.9' WHERE sequence = 1")
    conn.close()

    corrupted = store(db)
    assert corrupted.project(attest(corrupted))["availability"] == "UNKNOWN"


# --- Source non gouvernée / obsolète -----------------------------------------

def test_source_non_gouvernee_est_rejetee_sans_ecriture(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    with pytest.raises(ContractError):
        admit(s, candidate(owner_registry="untrusted"), command_id="cmd-x")
    assert s.events() == ()


def test_owner_record_version_obsolete_provoque_collision_pas_mise_a_jour_silencieuse(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    with pytest.raises(ContractError, match="collision"):
        admit(s, replace(candidate(), title="Version obsolète rejouée"), command_id="cmd-2")
    assert len(s.events()) == 1


# --- AvailabilityProof non authentifiée --------------------------------------

def test_availability_proof_non_authentifiee_ne_produit_jamais_available_sans_watermark(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    assert s.project()["availability"] == "NON DÉPLOYÉ"
    for libre in (AvailabilityProof(False, "ref", 1, NOW), AvailabilityProof(True, "ref", 1, NOW)):
        assert s.project(libre)["availability"] == "UNKNOWN"


def test_project_lit_et_verifie_sous_un_instantane_transactionnel_unique(tmp_path, monkeypatch):
    """Revue indépendante PR #316 (review_id 5333698547), point 3.

    Avant la correction, `project()` lisait `events()` puis appelait
    `verify()` sur deux connexions/transactions distinctes : une écriture
    corruptrice concurrente pouvait s'intercaler entre les deux. On simule
    précisément cette fenêtre (une écriture corruptrice commitée par une
    connexion séparée juste après le début de la lecture, avant la
    vérification) et on démontre qu'elle reste invisible : l'instantané de
    transaction fixé au début de `_read_events_verified` ne voit pas les
    écritures commitées après son démarrage, donc les données lues et
    vérifiées restent cohérentes entre elles.

    Déterminisme de l'injection (pas un thread, pas de `sleep`/`Event.wait`) :
    `corrupting_verify` remplace `_verify_locked` UNIQUEMENT sur l'instance
    `s` (`monkeypatch.setattr(s, "_verify_locked", ...)`, PAS sur la classe),
    donc l'appel `self._verify_locked(conn)` dans `_read_events_verified`
    exécute la corruption de façon synchrone, dans le même thread, au point
    exact voulu — il n'y a aucune fenêtre de timing à gagner.

    Historique du diagnostic (PR #316) — cause réelle confirmée par
    instrumentation CI directe, pas par hypothèse : ce test a été rouge 3
    fois de suite en CI (runs 36377422947, 36379284990, 36379739236) alors
    qu'il passait systématiquement en isolation locale (60+ exécutions). Les
    deux premiers correctifs tentés (retenue sur `sqlite3.OperationalError`
    puis élargie à `sqlite3.DatabaseError` dans
    `DurableGovernedStore._read_events_verified`) reposaient sur l'hypothèse
    qu'une exception SQLite transitoire non retenue empêchait d'atteindre
    `_verify_locked`. Une instrumentation CI directe (capture, dans le
    store, du nombre de tentatives, de l'étape atteinte, du type/message de
    toute exception, ET de l'identité qualifiée exacte du callable résolu
    par `self._verify_locked` juste avant son appel) a prouvé que cette
    hypothèse était FAUSSE : sur les 3 runs, `_connect()` et le `SELECT`
    réussissaient sans aucune exception, `_verify_locked` était bien
    atteint et appelé, ET le callable réellement invoqué était
    `DurableGovernedStore._verify_locked` — l'implémentation ORIGINALE de
    la CLASSE, jamais `corrupting_verify`. Le monkeypatch au niveau CLASSE
    (`monkeypatch.setattr(DurableGovernedStore, "_verify_locked",
    staticmethod(corrupting_verify))`) ne prenait donc simplement pas effet
    de façon fiable dans l'environnement CI (suite complète, 6549+ tests
    dans le même processus) — jamais reproduit en isolation locale, cause
    exacte non élucidée au niveau CPython/pytest, mais le SYMPTÔME
    (dispatch classe non fiable à cette échelle) est, lui, directement
    prouvé par cette instrumentation. Correctif : monkeypatcher l'attribut
    sur l'INSTANCE `s` plutôt que sur la classe — un attribut d'instance est
    trouvé par une simple recherche dans `s.__dict__`, prioritaire sur
    l'attribut de classe et non soumis aux mêmes caches d'attribut de type
    que `setattr()` sur une classe. Aucune modification de
    `DurableGovernedStore` n'était donc nécessaire pour CE flaking précis ;
    la retenue générique ajoutée pendant le diagnostic réfuté a depuis été
    retirée de `_read_events_verified` (commentaire propriétaire
    5864337478, point 4).
    """
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")

    original_verify_locked = s._verify_locked  # méthode liée, capturée avant le patch
    injected = {"done": False}

    def corrupting_verify(conn):
        if not injected["done"]:
            injected["done"] = True
            raw = sqlite3.connect(str(db), isolation_level=None, timeout=30)
            raw.execute("PRAGMA busy_timeout=30000")
            raw.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
            raw.close()
        return original_verify_locked(conn)

    # Monkeypatch au niveau INSTANCE (pas la classe) : voir docstring.
    monkeypatch.setattr(s, "_verify_locked", corrupting_verify, raising=False)

    signed = attest(s)  # attestation de l'état AVANT la corruption injectée
    view = s.project(signed)
    assert injected["done"], (
        "_verify_locked jamais atteint avec la corruption injectée — "
        f"project() a renvoyé availability={view.get('availability')!r}, "
        f"limitations={view.get('limitations')!r}"
    )
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 1


def test_admission_concurrente_pendant_une_projection_ne_produit_aucune_incoherence(tmp_path):
    """Revue indépendante PR #316 (review_id 5333698547), point 3 (stress).

    Un thread admet de nouveaux candidats pendant qu'un autre projette en
    boucle : quel que soit l'entrelacement réel, chaque projection doit
    rester interne cohérente (jamais de crash, et `decision_count` toujours
    égal à `len(items)` et à `as_of_event_version` quand `AVAILABLE`).

    Ce test s'appuie sur de vrais threads (`threading.Thread`), mais ne
    dépend d'aucune fenêtre de timing précise pour être valide : l'invariant
    vérifié (cohérence interne d'une projection) doit tenir quel que soit
    l'entrelacement réel, par construction — ce n'est pas un test qui essaie
    de "gagner" une course. `project()` échoue fermé (`UNKNOWN`) sur toute
    erreur SQLite, sans retenue côté production ; une retenue bornée reste
    uniquement côté test, sur `sqlite3.OperationalError` seulement, pour ne
    pas confondre une contention de verrou réelle avec une incohérence —
    jamais après une `AssertionError` (une vraie violation d'invariant reste
    fatale immédiatement). Chaque projection reçoit une attestation fixture
    à checkpoint croissant (anti-retour respecté).
    """
    db = tmp_path / "store.db"
    s0 = store(db)
    errors: list[Exception] = []
    checkpoints = iter(range(1, 1000))

    def _retrying(fn):
        last_exc: sqlite3.OperationalError | None = None
        for _attempt in range(5):
            try:
                return fn()
            except sqlite3.OperationalError as exc:  # contention transitoire seulement
                last_exc = exc
                continue
        raise last_exc

    def admit_many():
        try:
            for i in range(10):
                c = candidate(source_id=f"problem-{i}", candidate_id=f"cand-{i}")
                _retrying(lambda c=c, i=i: admit(store(db), c, f"cmd-{i}"))
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    def project_many():
        try:
            for _ in range(30):
                reader = store(db)
                signed = _retrying(lambda r=reader: attest(r, next(checkpoints)))
                view = _retrying(lambda r=reader, a=signed: r.project(a))
                if view["availability"] == "AVAILABLE":
                    assert view["decision_count"] == len(view["items"])
                    assert view["decision_count"] == view["as_of_event_version"]
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=admit_many), threading.Thread(target=project_many)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(s0.events()) == 10


def test_watermark_partiel_echoue_ferme(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    view = s.project(attest(s, event_count=1))  # watermark incomplet (2 réels)
    assert view["availability"] == "UNKNOWN"
    assert view["decision_count"] is None


def test_zero_ne_peut_jamais_etre_certifie_par_une_preuve_non_authentifiee(tmp_path):
    """Revue indépendante PR #316 (review_id 5333698547), point 1.

    Une base vide et une `AvailabilityProof` librement construite par
    l'appelant (`producer_certified=True`, aucune signature, aucun ancrage)
    ne doivent JAMAIS pouvoir produire `AVAILABLE` avec `decision_count=0` :
    il n'existe aucun gate de confiance réel dans ce prototype pour
    authentifier une telle preuve, donc le zéro doit rester refusé
    (fail-closed), pas silencieusement accepté.
    """
    db = tmp_path / "store.db"
    s = store(db)
    assert s.project()["decision_count"] is None  # NON DÉPLOYÉ, jamais 0 par défaut

    invented = AvailabilityProof(True, "invented", 0, NOW)
    view = s.project(invented)
    assert view["availability"] != "AVAILABLE"
    assert view["availability"] == "UNKNOWN"
    assert view["decision_count"] is None
    assert "preuve non authentifiée" in " ".join(view["limitations"])


# --- Approbation signée liée au contenu (ADR-0020, étape 2) ------------------

def _refus_sans_ecriture(s, c, appr, match=None, tr=None):
    with pytest.raises((TrustError, ContractError), match=match):
        s.admit(c, owner_transfer=tr or transfer(c), approval=appr,
                command_id="cmd-refus")
    assert s.events() == ()
    assert _command_rows(s) == 0


def _command_rows(s) -> int:
    conn = sqlite3.connect(s._db_path, timeout=30)  # noqa: SLF001
    try:
        return conn.execute("SELECT COUNT(*) FROM command_results").fetchone()[0]
    finally:
        conn.close()


def test_approbation_avec_fausse_signature_refusee_sans_ecriture(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    forged = replace(approval(c), signature_hex="0" * 128)
    _refus_sans_ecriture(s, c, forged, match="signature invalide")


def test_approbation_signee_par_cle_inconnue_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c, sk=ROGUE_SK, key_id="cle-inconnue"),
                         match="clé inconnue")


def test_cle_hors_politique_avec_key_id_connu_ne_etablit_jamais_son_autorite(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c, sk=ROGUE_SK), match="signature invalide")


def test_approbation_par_cle_revoquee_refusee(tmp_path):
    s = store(tmp_path / "store.db",
              trust_policy=policy(revoked_key_ids=frozenset({"fixture-approver-1"})))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="révoquée")


def test_approbation_signee_par_le_mauvais_role_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    appr = approval(c, sk=AUTHORITY_SK, key_id="fixture-authority-1",
                    approver_id="fixture:autorite-disponibilite")
    _refus_sans_ecriture(s, c, appr, match="rôle incorrect")


def test_approbation_par_approbateur_d_un_autre_proprietaire_refusee(tmp_path):
    other = trusted_key(APPROVER_SK, "fixture-approver-1", ADMISSION_APPROVER,
                        "fixture:approbateur-problem",
                        grants=(("bounty-registry", "PROBLEM", "planifier"),))
    s = store(tmp_path / "store.db",
              trust_policy=policy(keys=(OWNER_KEY, other, AUTHORITY_KEY, ACCESS_KEY)))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="ADMISSION_APPROVER non autorisé")


def test_approbation_liee_a_un_mauvais_proprietaire_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c, owner_registry="bounty-registry"),
                         match="owner_registry")


def test_candidat_substitue_apres_approbation_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    appr = approval(candidate())
    _refus_sans_ecriture(s, candidate(title="Titre substitué"), appr,
                         match="candidate_fingerprint")


def test_source_remplacee_revision_differente_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    appr = approval(candidate())  # approuvée pour owner_record_version=v1
    _refus_sans_ecriture(s, candidate(owner_record_version="v2"), appr,
                         match="owner_record_version")


def test_source_obsolete_empreinte_de_contenu_differente_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    appr = approval(candidate())
    _refus_sans_ecriture(s, candidate(source_sha="b" * 64), appr, match="source_sha")


def test_priorite_auto_promue_par_l_approbation_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate(requested_priority="MEDIUM")
    _refus_sans_ecriture(s, c, approval(c, approved_priority="CRITICAL"),
                         match="auto-promue")


def test_priorite_auto_promue_par_le_demandeur_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    appr = approval(candidate(requested_priority="MEDIUM"))
    _refus_sans_ecriture(s, candidate(requested_priority="CRITICAL"), appr,
                         match="candidate_fingerprint")


def test_version_de_politique_inconnue_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c, policy_version="politique-v0"),
                         match="version de politique")


def test_approbation_expiree_refusee(tmp_path):
    s = store(tmp_path / "store.db", clock=Clock(NOW_DT + timedelta(hours=2)))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="expiré")


def test_approbateur_signe_different_de_l_identite_de_la_cle_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c, approver_id="usurpateur"), match="identité")


def test_preuve_libre_non_signee_refusee_comme_approbation(tmp_path):
    s = store(tmp_path / "store.db")
    _refus_sans_ecriture(s, candidate(), {"approved": True}, match="énoncé signé requis")


def test_statut_et_priorite_lus_depuis_l_approbation_verifiee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate(requested_priority="HIGH", requested_status="TO_VALIDATE")
    admit(s, c, appr=approval(c, approved_status="TO_READ", approved_priority="LOW"))
    (event,) = s.events()
    assert event["new_status"] == "TO_READ"
    assert event["approved_priority"] == "LOW"
    assert event["approver_id"] == "fixture:approbateur-problem"
    assert event["policy_version"] == POLICY_VERSION


def test_politique_operationnelle_refusee_sans_autorite_reelle():
    with pytest.raises(ContractError, match="aucune autorité"):
        policy(operational=True)


def test_une_identite_ne_peut_detenir_les_deux_roles():
    dual = trusted_key(AUTHORITY_SK, "k2", AVAILABILITY_AUTHORITY,
                       "fixture:approbateur-problem")
    with pytest.raises(ContractError, match="deux rôles"):
        policy(keys=(APPROVER_KEY, dual))


# --- Attestation d'origine, complétude, fraîcheur (ADR-0020, étape 3) --------

def _deux_admissions(s):
    admit(s, candidate(), command_id="cmd-1")
    c2 = candidate(source_id="problem-2", candidate_id="cand-2")
    admit(s, c2, command_id="cmd-2")


def _refusee(view, fragment):
    assert view["availability"] == "UNKNOWN", view
    assert view["decision_count"] is None
    assert fragment in " ".join(view["limitations"]), view["limitations"]


def test_zero_authentifie_complet_et_frais_est_accepte(tmp_path):
    s = store(tmp_path / "store.db")
    view = s.project(attest(s))
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 0
    assert view["items"] == []
    assert view["head_hash"] == "GENESIS"
    assert view["journal_id"] == s.journal_id


def test_identifiant_de_journal_stable_apres_reouverture(tmp_path):
    db = tmp_path / "store.db"
    assert store(db).journal_id == store(db).journal_id
    assert store(tmp_path / "autre.db").journal_id != store(db).journal_id


def test_attestation_avec_fausse_signature_jamais_available(tmp_path):
    s = store(tmp_path / "store.db")
    forged = replace(attest(s), signature_hex="0" * 128)
    _refusee(s.project(forged), "signature invalide")


def test_attestation_cle_inconnue_jamais_available(tmp_path):
    s = store(tmp_path / "store.db")
    _refusee(s.project(attest(s, sk=ROGUE_SK, key_id="inconnue")), "clé inconnue")


def test_attestation_cle_revoquee_jamais_available(tmp_path):
    s = store(tmp_path / "store.db",
              trust_policy=policy(revoked_key_ids=frozenset({"fixture-authority-1"})))
    _refusee(s.project(attest(s)), "révoquée")


def test_preuve_sensible_non_autorisee_signee_par_le_mauvais_role(tmp_path):
    """Un approbateur d'admission ne peut pas attester la disponibilité."""
    s = store(tmp_path / "store.db")
    appr_signed = attest(s, sk=APPROVER_SK, key_id="fixture-approver-1",
                         authority_id="fixture:approbateur-problem")
    _refusee(s.project(appr_signed), "rôle incorrect")


def test_attestation_expiree_jamais_available(tmp_path):
    s = store(tmp_path / "store.db", clock=Clock(NOW_DT + timedelta(minutes=11)))
    _refusee(s.project(attest(s)), "expiré")


def test_attestation_future_hors_tolerance_jamais_available(tmp_path):
    s = store(tmp_path / "store.db")
    future = attest(s, issued_at_utc=_iso(NOW_DT + timedelta(minutes=5)),
                    expires_at_utc=_iso(NOW_DT + timedelta(minutes=20)))
    _refusee(s.project(future), "futur")


def test_attestation_future_dans_la_tolerance_de_derive_acceptee(tmp_path):
    s = store(tmp_path / "store.db")
    near = attest(s, issued_at_utc=_iso(NOW_DT + timedelta(seconds=30)))
    assert s.project(near)["availability"] == "AVAILABLE"


def test_attestation_de_validite_excessive_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    _refusee(s.project(attest(s, expires_at_utc=_iso(NOW_DT + timedelta(days=2)))),
             "validité")


def test_attestation_incomplete_nombre_d_evenements(tmp_path):
    s = store(tmp_path / "store.db")
    _deux_admissions(s)
    _refusee(s.project(attest(s, event_count=1)), "nombre d'événements")


def test_attestation_incomplete_zero_sur_base_non_vide(tmp_path):
    s = store(tmp_path / "store.db")
    admit(s, candidate())
    _refusee(s.project(attest(s, event_count=0, head_hash="GENESIS")), "nombre")


def test_attestation_hash_de_tete_different(tmp_path):
    s = store(tmp_path / "store.db")
    admit(s, candidate())
    _refusee(s.project(attest(s, head_hash="f" * 64)), "hash de tête")


def test_substitution_de_journal_refusee(tmp_path):
    a = store(tmp_path / "a.db")
    b = store(tmp_path / "b.db")
    # Attestation authentique du journal A présentée au journal B (même état vide).
    _refusee(b.project(attest(a)), "autre journal")


def test_perimetre_ou_schema_non_attestes_refuses(tmp_path):
    s = store(tmp_path / "store.db")
    _refusee(s.project(attest(s, scope="AUTRE_PERIMETRE")), "périmètre")
    _refusee(s.project(attest(s, schema_version="0.0.1")), "schéma")


def test_attestation_version_de_politique_inconnue(tmp_path):
    s = store(tmp_path / "store.db")
    _refusee(s.project(attest(s, policy_version="autre")), "version de politique")


def test_rejeu_d_un_ancien_checkpoint_correctement_signe_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    admit(s, candidate())
    ancien = attest(s, checkpoint=1)
    assert s.project(ancien)["availability"] == "AVAILABLE"
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    assert s.project(attest(s, checkpoint=2))["availability"] == "AVAILABLE"
    # L'ancienne attestation (checkpoint 1) reste signée et non expirée.
    _refusee(s.project(ancien), "")
    _refusee(s.project(attest(s, checkpoint=1)), "antérieur")


def test_meme_checkpoint_avec_etat_different_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    assert s.project(attest(s, checkpoint=5))["availability"] == "AVAILABLE"
    admit(s, candidate())
    _refusee(s.project(attest(s, checkpoint=5)), "état différent")


def test_troncature_de_suffixe_apres_checkpoint_accepte_detectee(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    _deux_admissions(s)
    assert s.project(attest(s, checkpoint=1))["availability"] == "AVAILABLE"
    conn = _raw(db)
    conn.execute("DELETE FROM command_results WHERE sequence = 2")
    conn.execute("DELETE FROM events WHERE sequence = 2")  # chaîne restante cohérente
    conn.close()
    s.verify()  # l'intégrité interne seule ne voit rien : préfixe valide
    _refusee(s.project(), "retour arrière")
    # Même une attestation authentique de l'état tronqué avec un checkpoint
    # supérieur est refusée : moins d'événements que le dernier accepté.
    _refusee(s.project(attest(s, checkpoint=2)), "retour arrière")


def test_reecriture_avec_recalcul_des_hash_detectee_par_attestation(tmp_path):
    """Réécriture complète + chaîne recalculée : cohérente pour verify(),
    refusée par l'attestation (hash de tête) et par l'ancre anti-retour."""
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate())
    assert s.project(attest(s, checkpoint=1))["availability"] == "AVAILABLE"
    count, head_initial = journal_state(s)

    # L'attaquant construit un journal alternatif valide dans un autre fichier
    # (même politique fixture : il ne détient PAS la clé d'autorité) puis
    # remplace le contenu du journal réel en recopiant les lignes.
    alt_db = tmp_path / "alt.db"
    alt = store(alt_db)
    admit(alt, candidate(title="Titre réécrit"))
    src = _raw(alt_db)
    rows = src.execute("SELECT * FROM events").fetchall()
    cmds = src.execute("SELECT * FROM command_results").fetchall()
    src.close()
    conn = _raw(db)
    conn.execute("DELETE FROM command_results")
    conn.execute("DELETE FROM events")
    conn.executemany(f"INSERT INTO events VALUES ({','.join('?' * len(rows[0]))})", rows)
    conn.executemany(f"INSERT INTO command_results VALUES ({','.join('?' * len(cmds[0]))})", cmds)
    conn.close()

    s.verify()  # LIMITE documentée : l'intégrité interne ne détecte pas la réécriture
    assert journal_state(s)[1] != head_initial
    _refusee(s.project(), "retour arrière")  # ancre : préfixe différent
    # Sans l'ancre (vérificateur neuf, ancre dans un fichier vierge), seule une
    # attestation fraîche du VRAI hash de tête détecte la réécriture :
    fresh = DurableGovernedStore(db, {"PROBLEM": "problem-registry"},
                                 trust_policy=policy(), clock=Clock(),
                                 anchor_path=tmp_path / "ancre-neuve.db")
    authentic_old = attest(s, checkpoint=2, event_count=count, head_hash=head_initial)
    _refusee(fresh.project(authentic_old), "hash de tête")


def test_restauration_complete_du_fichier_detectee_avec_ancre_externe(tmp_path):
    db = tmp_path / "store.db"
    anchor = tmp_path / "ancre.db"

    def s_():
        return DurableGovernedStore(db, {"PROBLEM": "problem-registry"},
                                    trust_policy=policy(), clock=Clock(),
                                    anchor_path=anchor)

    s = s_()
    admit(s, candidate())
    ancien = attest(s, checkpoint=1)
    snapshot = sqlite3.connect(str(tmp_path / "ancien.db"))
    live = sqlite3.connect(str(db))
    live.backup(snapshot)
    live.close()
    snapshot.close()
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    assert s.project(attest(s, checkpoint=2))["availability"] == "AVAILABLE"

    # Restauration du fichier journal entier à l'état ancien (l'ancre externe
    # n'est pas touchée) + rejeu de l'ancienne attestation authentique.
    restored = sqlite3.connect(str(tmp_path / "ancien.db"))
    target = sqlite3.connect(str(db))
    restored.backup(target)
    restored.close()
    target.close()
    _refusee(s_().project(ancien), "retour arrière")


# --- Intégrité du stockage et reprise (étape 4) ------------------------------

def test_alteration_de_l_index_command_results_detectee(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    conn = _raw(db)
    # Redirige la commande 1 vers la décision de l'événement 2.
    d2 = conn.execute("SELECT decision_id FROM events WHERE sequence = 2").fetchone()[0]
    conn.execute("UPDATE command_results SET decision_id = ? WHERE command_id = 'cmd-1'", (d2,))
    conn.close()
    with pytest.raises(CorruptedJournalError, match="index"):
        s.verify()
    with pytest.raises(CorruptedJournalError, match="index"):
        admit(s, candidate(), command_id="cmd-1")  # jamais de réponse issue d'un index altéré
    assert s.project(attest(s))["availability"] == "UNKNOWN"


def test_index_orphelin_ou_event_hash_altere_detecte(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE command_results SET event_hash = ? WHERE command_id = 'cmd-1'",
                 ("e" * 64,))
    conn.close()
    with pytest.raises(CorruptedJournalError, match="index"):
        s.verify()
    conn = _raw(db)
    conn.execute("UPDATE command_results SET sequence = 99 WHERE command_id = 'cmd-1'")
    conn.close()
    with pytest.raises(CorruptedJournalError, match="orphelin"):
        s.verify()


def test_alteration_des_colonnes_d_index_du_journal_detectee(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET idempotency_key = 'cle-forgee' WHERE sequence = 1")
    conn.close()
    with pytest.raises(CorruptedJournalError):
        s.verify()


def test_reconstruction_de_l_index_depuis_le_journal(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    d1 = admit(s, candidate(), command_id="cmd-1")
    d2 = admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    conn = _raw(db)
    conn.execute("UPDATE command_results SET decision_id = 'forge' WHERE command_id = 'cmd-1'")
    conn.execute("DELETE FROM command_results WHERE command_id = 'cmd-2'")
    conn.close()
    with pytest.raises(CorruptedJournalError):
        s.verify()
    assert s.rebuild_command_index() == 2
    s.verify()
    # Rejeu idempotent après reconstruction : mêmes décisions, aucun doublon.
    assert admit(s, candidate(), command_id="cmd-1") == d1
    c2 = candidate(source_id="problem-2", candidate_id="cand-2")
    assert admit(s, c2, command_id="cmd-2") == d2
    assert len(s.events()) == 2


def test_reconstruction_refusee_si_le_journal_est_corrompu(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
    conn.close()
    with pytest.raises(CorruptedJournalError):
        s.rebuild_command_index()
    conn = _raw(db)
    assert conn.execute("SELECT COUNT(*) FROM command_results").fetchone()[0] == 1  # rollback
    conn.close()


def test_sauvegarde_restauration_puis_rejeu_idempotent(tmp_path):
    """Procédure du runbook §2-§3, exécutée : backup(), verify(), rejeu."""
    db = tmp_path / "operator_decisions.db"
    s = store(db)
    decision_id = admit(s, candidate(), command_id="cmd-sauvegarde")

    source = sqlite3.connect(str(db))
    source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    backup_path = tmp_path / "operator_decisions.backup.db"
    backup = sqlite3.connect(str(backup_path))
    with backup:
        source.backup(backup)
    backup.close()
    source.close()

    restored_path = tmp_path / "restaure.db"
    restored_path.write_bytes(backup_path.read_bytes())
    restored = store(restored_path)
    restored.verify()
    assert restored.journal_id == s.journal_id  # même journal, identité conservée
    assert admit(restored, candidate(), command_id="cmd-sauvegarde") == decision_id
    assert len(restored.events()) == 1
    view = restored.project(attest(restored))
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 1


class _TrackedConnection:
    """Proxy de connexion : trace la fermeture et injecte des échecs ciblés."""

    registry: list = []

    def __init__(self, real, fail):
        self._real = real
        self._fail = fail
        self.closed = False
        _TrackedConnection.registry.append(self)

    def execute(self, sql, *args):
        exc = self._fail(sql)
        if exc is not None:
            raise exc
        return self._real.execute(sql, *args)

    def executescript(self, sql):
        return self._real.executescript(sql)

    def close(self):
        self.closed = True
        self._real.close()


def _instrument(monkeypatch, fail):
    _TrackedConnection.registry = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect",
                        lambda *a, **k: _TrackedConnection(real_connect(*a, **k), fail))
    return _TrackedConnection.registry


def test_connexion_fermee_si_le_passage_wal_echoue_sans_retenue_hors_verrou(tmp_path, monkeypatch):
    calls = []

    def fail(sql):
        if sql == "PRAGMA journal_mode=WAL":
            calls.append(sql)
            return sqlite3.OperationalError("disk I/O error")
        return None

    opened = _instrument(monkeypatch, fail)
    with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
        store(tmp_path / "store.db")
    assert len(calls) == 1  # aucune retenue pour une erreur autre que le verrou
    assert opened and all(c.closed for c in opened)


def test_retenue_wal_limitee_a_database_is_locked(tmp_path, monkeypatch):
    calls = []

    def fail(sql):
        if sql == "PRAGMA journal_mode=WAL":
            calls.append(sql)
            if len(calls) <= 2:
                return sqlite3.OperationalError("database is locked")
        return None

    opened = _instrument(monkeypatch, fail)
    store(tmp_path / "store.db")
    assert len(calls) == 3
    assert all(c.closed for c in opened)


def test_retenue_wal_bornee_puis_connexion_fermee(tmp_path, monkeypatch):
    def fail(sql):
        if sql == "PRAGMA journal_mode=WAL":
            return sqlite3.OperationalError("database is locked")
        return None

    opened = _instrument(monkeypatch, fail)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        store(tmp_path / "store.db")
    assert opened and all(c.closed for c in opened)


def test_connexion_fermee_si_init_schema_echoue(tmp_path, monkeypatch):
    db = tmp_path / "store.db"
    store(db)
    conn = _raw(db)
    conn.execute("UPDATE schema_meta SET schema_version = '9.9.9'")
    conn.close()
    opened = _instrument(monkeypatch, lambda sql: None)
    with pytest.raises(CorruptedJournalError, match="version antérieure ou inconnue"):
        store(db)
    assert opened and all(c.closed for c in opened)


def test_lecture_verifiee_sans_retenue_generique_echoue_ferme(tmp_path, monkeypatch):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate())
    selects = []

    def fail(sql):
        if sql.startswith("SELECT payload_json FROM events"):
            selects.append(sql)
            return sqlite3.DatabaseError("erreur injectée")
        return None

    opened = _instrument(monkeypatch, fail)
    view = s.project(attest(s))
    assert view["availability"] == "UNKNOWN"
    assert len(selects) == 1  # plus de retenue générique sur DatabaseError
    assert all(c.closed for c in opened)


# --- Preuves négatives complémentaires (étape 5) ------------------------------

def test_approbation_emise_dans_le_futur_hors_tolerance_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    appr = approval(c, issued_at_utc=_iso(NOW_DT + timedelta(minutes=5)),
                    expires_at_utc=_iso(NOW_DT + timedelta(minutes=30)))
    _refus_sans_ecriture(s, c, appr, match="futur")


def test_attestation_checkpoint_invalide_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    for bad in (0, -1, "1", 1.0):
        _refusee(s.project(attest(s, checkpoint=bad)), "checkpoint")


def test_attestation_autorite_differente_de_l_identite_de_la_cle(tmp_path):
    s = store(tmp_path / "store.db")
    _refusee(s.project(attest(s, authority_id="usurpateur")), "identité")


def test_approbation_ancienne_revision_rejouee_apres_remplacement_de_source(tmp_path):
    """v1 puis v2 admises ; l'approbation v1 ne peut pas servir pour v2 ni
    être détournée vers une autre finalité."""
    s = store(tmp_path / "store.db")
    v1 = candidate()
    appr_v1 = approval(v1)
    admit(s, v1, command_id="cmd-v1", appr=appr_v1)
    v2 = candidate(owner_record_version="v2", source_sha="c" * 64,
                   candidate_id="cand-1b", candidate_revision=2)
    admit(s, v2, command_id="cmd-v2")
    with pytest.raises(TrustError, match="owner_record_version"):
        s.admit(v2, owner_transfer=transfer(v2), approval=appr_v1,
                command_id="cmd-v2-bis")
    # Détournement vers une autre finalité : les clés sont autorisées pour les
    # DEUX finalités, seule la liaison de l'approbation doit donc l'interdire.
    g2 = (GRANT[0], GRANT[1], "autre-finalite")
    owner2 = trusted_key(OWNER_SK, "fixture-owner-1", SOURCE_OWNER,
                         "fixture:proprietaire-problem", grants=(GRANT, g2))
    approver2 = trusted_key(APPROVER_SK, "fixture-approver-1", ADMISSION_APPROVER,
                            "fixture:approbateur-problem", grants=(GRANT, g2))
    s2 = store(tmp_path / "store2.db", trust_policy=policy(
        keys=(owner2, approver2, AUTHORITY_KEY, ACCESS_KEY)))
    detourne = replace(v1, decision_purpose="autre-finalite")
    with pytest.raises(TrustError, match="decision_purpose"):
        s2.admit(detourne, owner_transfer=transfer(detourne), approval=appr_v1,
                 command_id="cmd-v1-detourne")
    assert s2.events() == ()
    assert len(s.events()) == 2


def test_evenement_journalise_conserve_l_approbation_signee_verifiable(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    appr = approval(c)
    admit(s, c, appr=appr)
    (event,) = s.events()
    assert event["approval"] == appr.digest_material()
    stored = event["approval"]
    replayed = type(appr)(stored["payload"], stored["key_id"], stored["signature_hex"])
    body, _ = policy().verify(replayed, role=ADMISSION_APPROVER,
                              statement_type="ADMISSION_APPROVAL")
    assert body["approval_id"] == "approbation-1"


# --- Transfert propriétaire signé et permissions exactes (D5B §2) -----------

def test_transfert_avec_fausse_signature_refuse_sans_ecriture(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    forged = replace(transfer(c), signature_hex="0" * 128)
    _refus_sans_ecriture(s, c, approval(c), match="signature invalide", tr=forged)


def test_transfert_signe_par_une_cle_inconnue_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    tr = transfer(c, sk=ROGUE_SK, key_id="cle-inconnue")
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="clé inconnue", tr=tr)


def test_transfert_signe_par_le_mauvais_role_refuse(tmp_path):
    """L'approbateur d'admission ne peut pas se faire passer pour le propriétaire."""
    s = store(tmp_path / "store.db")
    c = candidate()
    tr = transfer(c, sk=APPROVER_SK, key_id="fixture-approver-1")
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="rôle incorrect", tr=tr)


def test_transfert_par_une_cle_proprietaire_revoquee_refuse(tmp_path):
    s = store(tmp_path / "store.db", trust_policy=policy(
        revoked_key_ids=frozenset({"fixture-owner-1"})))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="révoquée")


def test_transfert_avec_identite_proprietaire_differente_de_la_cle_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    tr = transfer(c, owner_id="usurpateur")
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="propriétaire signé", tr=tr)


@pytest.mark.parametrize("grant", [
    ("problem-registry", "PROBLEM", "autre-finalite"),
    ("problem-registry", "PROPOSED_EVOLUTION", "planifier"),
    ("autre-registre", "PROBLEM", "planifier"),
])
def test_proprietaire_non_autorise_pour_le_triplet_exact_refuse(tmp_path, grant):
    """Registre, type de source ET finalité sont tous exigés (pas de joker)."""
    limited = trusted_key(OWNER_SK, "fixture-owner-1", SOURCE_OWNER,
                          "fixture:proprietaire-problem", grants=(grant,))
    s = store(tmp_path / "store.db", trust_policy=policy(
        keys=(limited, APPROVER_KEY, AUTHORITY_KEY, ACCESS_KEY)))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="SOURCE_OWNER non autorisé")


@pytest.mark.parametrize("grant", [
    ("problem-registry", "PROBLEM", "autre-finalite"),
    ("problem-registry", "PROPOSED_EVOLUTION", "planifier"),
    ("autre-registre", "PROBLEM", "planifier"),
])
def test_approbateur_non_autorise_pour_le_triplet_exact_refuse(tmp_path, grant):
    limited = trusted_key(APPROVER_SK, "fixture-approver-1", ADMISSION_APPROVER,
                          "fixture:approbateur-problem", grants=(grant,))
    s = store(tmp_path / "store.db", trust_policy=policy(
        keys=(OWNER_KEY, limited, AUTHORITY_KEY, ACCESS_KEY)))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="ADMISSION_APPROVER non autorisé")


def test_transfert_lie_a_un_autre_candidat_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    c1, c2 = candidate(), candidate(title="Titre substitué")
    tr = transfer(c1)
    _refus_sans_ecriture(s, c2, approval(c2, owner_transfer=tr),
                         match="transfert propriétaire non lié", tr=tr)


def test_transfert_pour_une_autre_revision_source_refuse(tmp_path):
    s = store(tmp_path / "store.db")
    v1, v2 = candidate(), candidate(owner_record_version="v2")
    tr = transfer(v1)
    _refus_sans_ecriture(s, v2, approval(v2, owner_transfer=tr),
                         match="owner_record_version", tr=tr)


def test_approbation_liee_a_un_autre_transfert_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    autre = transfer(c, transfer_id="transfert-autre")
    appr = approval(c, owner_transfer=autre)
    _refus_sans_ecriture(s, c, appr, match="non liée au transfert propriétaire",
                         tr=transfer(c))


@pytest.mark.parametrize("libre", [None, {"owner": "x", "certified": True}, "transfert:1"])
def test_transfert_absent_ou_libre_refuse(tmp_path, libre):
    s = store(tmp_path / "store.db")
    c = candidate()
    with pytest.raises((TrustError, ContractError), match="énoncé signé requis"):
        s.admit(c, owner_transfer=libre, approval=approval(c), command_id="cmd-libre")
    assert s.events() == ()


def test_transfert_expire_refuse_pour_une_nouvelle_ecriture(tmp_path):
    clock = Clock()
    s = store(tmp_path / "store.db", clock=clock)
    c = candidate()
    tr = transfer(c, expires_at_utc=_iso(NOW_DT + timedelta(minutes=1)))
    appr = approval(c, owner_transfer=tr)
    clock.now = NOW_DT + timedelta(minutes=5)
    _refus_sans_ecriture(s, c, appr, match="expiré", tr=tr)


def test_une_identite_ne_peut_pas_etre_proprietaire_et_approbateur():
    meme_identite = trusted_key(OWNER_SK, "fixture-owner-2", SOURCE_OWNER,
                                "fixture:approbateur-problem", grants=(GRANT,))
    with pytest.raises(ContractError, match="deux rôles"):
        policy(keys=(meme_identite, APPROVER_KEY, AUTHORITY_KEY, ACCESS_KEY))


def test_permissions_invalides_refusees_a_la_construction():
    def cle(role, grants):
        return trusted_key(ROGUE_SK, "k", role, "fixture:x", grants=grants)

    with pytest.raises(ContractError, match="exige au moins une permission"):
        policy(keys=(cle(SOURCE_OWNER, ()),))
    with pytest.raises(ContractError, match="sans joker"):
        policy(keys=(cle(SOURCE_OWNER, (("problem-registry", "*", "planifier"),)),))
    with pytest.raises(ContractError, match="sans joker"):
        policy(keys=(cle(ADMISSION_APPROVER, (("problem-registry", "PROBLEM"),)),))
    with pytest.raises(ContractError, match="aucune permission"):
        policy(keys=(cle(AVAILABILITY_AUTHORITY, (GRANT,)),))
    with pytest.raises(ContractError, match="aucune permission"):
        policy(keys=(cle(EVIDENCE_ACCESS_AUTHORITY, (GRANT,)),))


def test_evenement_journalise_conserve_le_transfert_signe_verifiable(tmp_path):
    s = store(tmp_path / "store.db")
    c = candidate()
    tr = transfer(c)
    admit(s, c, tr=tr)
    (event,) = s.events()
    assert event["owner_transfer"] == tr.digest_material()
    assert event["owner_id"] == "fixture:proprietaire-problem"
    assert event["transfer_id"] == "transfert-1"
    stored = event["owner_transfer"]
    replayed = type(tr)(stored["payload"], stored["key_id"], stored["signature_hex"])
    body, _ = policy().verify(replayed, role=SOURCE_OWNER, statement_type="OWNER_TRANSFER")
    assert body["candidate_fingerprint"] == event["approval"]["payload"]["candidate_fingerprint"]
    assert event["approval"]["payload"]["owner_transfer_digest"] == transfer_digest(tr)


# --- Rejeu idempotent après expiration (réponse perdue) ----------------------

def _admis_puis_expire(tmp_path):
    clock = Clock()
    db = tmp_path / "store.db"
    s = store(db, clock=clock)
    c = candidate()
    tr = transfer(c)
    appr = approval(c, owner_transfer=tr)
    decision = s.admit(c, owner_transfer=tr, approval=appr, command_id="cmd-1")
    clock.now = NOW_DT + timedelta(hours=3)  # bien au-delà de la validité
    return db, clock, s, c, tr, appr, decision


def test_rejeu_apres_expiration_des_enonces_retrouve_la_decision(tmp_path):
    _, _, s, c, tr, appr, decision = _admis_puis_expire(tmp_path)
    assert s.admit(c, owner_transfer=tr, approval=appr, command_id="cmd-1") == decision
    assert len(s.events()) == 1


def test_rejeu_apres_expiration_avec_un_nouveau_command_id_converge(tmp_path):
    _, _, s, c, tr, appr, decision = _admis_puis_expire(tmp_path)
    assert s.admit(c, owner_transfer=tr, approval=appr, command_id="cmd-2") == decision
    assert len(s.events()) == 1


def test_nouvelle_admission_avec_enonces_expires_refusee_sans_ecriture(tmp_path):
    _, _, s, _, _, _, _ = _admis_puis_expire(tmp_path)
    autre = candidate(source_id="problem-2", candidate_id="cand-2")
    tr, appr = transfer(autre), approval(autre)
    with pytest.raises(TrustError, match="expiré"):
        s.admit(autre, owner_transfer=tr, approval=appr, command_id="cmd-2")
    assert len(s.events()) == 1
    assert _command_rows(s) == 1


def test_rejeu_apres_expiration_avec_cle_revoquee_refuse(tmp_path):
    db, clock, _, c, tr, appr, _ = _admis_puis_expire(tmp_path)
    revoque = store(db, clock=clock, trust_policy=policy(
        revoked_key_ids=frozenset({"fixture-approver-1"})))
    with pytest.raises(TrustError, match="révoquée"):
        revoque.admit(c, owner_transfer=tr, approval=appr, command_id="cmd-1")


def test_rejeu_apres_expiration_avec_enonce_falsifie_refuse(tmp_path):
    _, _, s, c, tr, appr, _ = _admis_puis_expire(tmp_path)
    with pytest.raises(TrustError, match="signature invalide"):
        s.admit(c, owner_transfer=tr, approval=replace(appr, signature_hex="0" * 128),
                command_id="cmd-1")


def test_rejeu_apres_expiration_avec_autre_approbation_signee_refuse(tmp_path):
    _, _, s, c, tr, _, _ = _admis_puis_expire(tmp_path)
    autre = approval(c, owner_transfer=tr, approval_id="approbation-2")
    with pytest.raises(ContractError, match="charge différente"):
        s.admit(c, owner_transfer=tr, approval=autre, command_id="cmd-1")
    assert len(s.events()) == 1


# --- Références de preuves sensibles (D5B §5) --------------------------------

PUBLIQUE, SENSIBLE = "artifact:sha256:abc", "vault:incident-7:acces-restreint"


def _candidat_sensible(**kw):
    return candidate(evidence_refs=(PUBLIQUE, SENSIBLE), **kw)


def _classes(**kw):
    base = {evidence_ref_digest(PUBLIQUE): EVIDENCE_PUBLIC,
            evidence_ref_digest(SENSIBLE): EVIDENCE_SENSITIVE}
    base.update(kw)
    return base


def _admis_sensible(tmp_path):
    s = store(tmp_path / "store.db")
    c = _candidat_sensible()
    decision = admit(s, c, tr=transfer(c, evidence_ref_classes=_classes()),
                     appr=approval(c, owner_transfer=transfer(c, evidence_ref_classes=_classes())))
    return s, c, decision


def access_grant(s, decision_id, *, sk=ACCESS_SK, key_id="fixture-access-1", **overrides):
    fields = dict(
        policy_version=POLICY_VERSION, authority_id="fixture:autorite-acces-preuves",
        journal_id=s.journal_id, decision_id=decision_id, accessor_id="fixture:lecteur-1",
        issued_at_utc=_iso(NOW_DT - timedelta(minutes=1)),
        expires_at_utc=_iso(NOW_DT + timedelta(minutes=5)),
    )
    fields.update(overrides)
    return sign_statement(sk, key_id, evidence_access_grant_payload(**fields))


def test_classification_incomplete_des_references_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = _candidat_sensible()
    tr = transfer(c, evidence_ref_classes={evidence_ref_digest(PUBLIQUE): EVIDENCE_PUBLIC})
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="classification", tr=tr)


def test_classification_avec_reference_inconnue_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = _candidat_sensible()
    tr = transfer(c, evidence_ref_classes=_classes(**{evidence_ref_digest("autre"): EVIDENCE_PUBLIC}))
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="classification", tr=tr)


def test_classification_avec_valeur_invalide_refusee(tmp_path):
    s = store(tmp_path / "store.db")
    c = _candidat_sensible()
    tr = transfer(c, evidence_ref_classes=_classes(**{evidence_ref_digest(SENSIBLE): "SECRET"}))
    _refus_sans_ecriture(s, c, approval(c, owner_transfer=tr), match="classification", tr=tr)


def test_projection_masque_les_references_sensibles(tmp_path):
    import json
    s, _, _ = _admis_sensible(tmp_path)
    view = s.project(attest(s))
    assert view["availability"] == "AVAILABLE"
    evidence = view["items"][0]["evidence"]
    assert evidence["evidence_refs"] == [
        PUBLIQUE, {"redacted": True, "ref_digest": evidence_ref_digest(SENSIBLE)},
    ]
    assert evidence["sensitive_refs_redacted"] == 1
    assert SENSIBLE not in json.dumps(view)


def test_reference_non_explicitement_publique_est_masquee_par_defaut():
    """Échec fermé : classe absente ou inconnue => masquée."""
    for classes in ({}, None, {evidence_ref_digest("x"): "INCONNU"}):
        out = DurableGovernedStore._projected_refs(  # noqa: SLF001
            {"evidence_refs": ["x"], "evidence_ref_classes": classes})
        assert out == [{"redacted": True, "ref_digest": evidence_ref_digest("x")}]


def test_lecture_des_references_sensibles_avec_droit_valide(tmp_path):
    s, _, decision = _admis_sensible(tmp_path)
    assert s.read_sensitive_evidence(decision, grant=access_grant(s, decision)) == (SENSIBLE,)


@pytest.mark.parametrize("libre", [None, {"acces": True}, "ok"])
def test_lecture_sensible_sans_droit_signe_refusee(tmp_path, libre):
    s, _, decision = _admis_sensible(tmp_path)
    with pytest.raises(TrustError, match="énoncé signé requis"):
        s.read_sensitive_evidence(decision, grant=libre)


@pytest.mark.parametrize("sk,key_id", [
    (AUTHORITY_SK, "fixture-authority-1"),
    (APPROVER_SK, "fixture-approver-1"),
    (OWNER_SK, "fixture-owner-1"),
])
def test_lecture_sensible_avec_droit_signe_par_un_autre_role_refusee(tmp_path, sk, key_id):
    s, _, decision = _admis_sensible(tmp_path)
    with pytest.raises(TrustError, match="rôle incorrect"):
        s.read_sensitive_evidence(decision, grant=access_grant(s, decision, sk=sk, key_id=key_id))


def test_lecture_sensible_avec_fausse_signature_ou_cle_inconnue_refusee(tmp_path):
    s, _, decision = _admis_sensible(tmp_path)
    with pytest.raises(TrustError, match="signature invalide"):
        s.read_sensitive_evidence(
            decision, grant=replace(access_grant(s, decision), signature_hex="0" * 128))
    with pytest.raises(TrustError, match="clé inconnue"):
        s.read_sensitive_evidence(
            decision, grant=access_grant(s, decision, sk=ROGUE_SK, key_id="inconnue"))


def test_lecture_sensible_avec_droit_d_une_autre_decision_refusee(tmp_path):
    s, _, decision = _admis_sensible(tmp_path)
    with pytest.raises(TrustError, match="autre décision"):
        s.read_sensitive_evidence(decision, grant=access_grant(s, "autre-decision"))


def test_lecture_sensible_avec_droit_d_un_autre_journal_refusee(tmp_path):
    s, _, decision = _admis_sensible(tmp_path)
    with pytest.raises(TrustError, match="autre journal"):
        s.read_sensitive_evidence(decision, grant=access_grant(s, decision, journal_id="autre"))


def test_lecture_sensible_avec_droit_expire_ou_revoque_refusee(tmp_path):
    clock = Clock()
    db = tmp_path / "store.db"
    s = store(db, clock=clock)
    c = _candidat_sensible()
    tr = transfer(c, evidence_ref_classes=_classes())
    decision = s.admit(c, owner_transfer=tr, approval=approval(c, owner_transfer=tr),
                       command_id="cmd-1")
    grant = access_grant(s, decision)
    clock.now = NOW_DT + timedelta(minutes=30)
    with pytest.raises(TrustError, match="expiré"):
        s.read_sensitive_evidence(decision, grant=grant)
    clock.now = NOW_DT
    revoque = store(db, clock=clock, trust_policy=policy(
        revoked_key_ids=frozenset({"fixture-access-1"})))
    with pytest.raises(TrustError, match="révoquée"):
        revoque.read_sensitive_evidence(decision, grant=grant)


def test_lecture_sensible_sur_journal_corrompu_echoue_ferme(tmp_path):
    s, _, decision = _admis_sensible(tmp_path)
    grant = access_grant(s, decision)
    conn = _raw(tmp_path / "store.db")
    conn.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
    conn.close()
    with pytest.raises(CorruptedJournalError):
        s.read_sensitive_evidence(decision, grant=grant)


def test_lecture_sensible_d_une_decision_inconnue_refusee(tmp_path):
    s, _, _ = _admis_sensible(tmp_path)
    with pytest.raises(ContractError, match="décision inconnue"):
        s.read_sensitive_evidence("inconnue", grant=access_grant(s, "inconnue"))


# --- Ancre anti-retour hors du fichier journal -------------------------------

def test_ancre_colocalisee_refusee_par_defaut(tmp_path):
    db = tmp_path / "store.db"
    owners = {"PROBLEM": "problem-registry"}
    with pytest.raises(ContractError, match="ancre anti-retour hors du fichier"):
        DurableGovernedStore(db, owners, trust_policy=policy(), clock=Clock())
    with pytest.raises(ContractError, match="ancre anti-retour hors du fichier"):
        DurableGovernedStore(db, owners, trust_policy=policy(), clock=Clock(),
                             anchor_path=db)


def test_ancre_colocalisee_explicite_laisse_passer_une_restauration_complete(tmp_path):
    """LIMITE DOCUMENTÉE (ADR-0020 §8) : colocalisée, l'ancre recule avec le
    fichier restauré ; seule la fenêtre de validité de l'attestation borne
    alors le rejeu. C'est pourquoi la colocalisation doit être explicite."""
    db = tmp_path / "store.db"
    s = DurableGovernedStore(db, {"PROBLEM": "problem-registry"}, trust_policy=policy(),
                             clock=Clock(), allow_colocated_anchor=True)
    admit(s, candidate())
    ancien = attest(s, checkpoint=1)
    snapshot = sqlite3.connect(str(tmp_path / "ancien.db"))
    live = sqlite3.connect(str(db))
    live.backup(snapshot)
    live.close()
    snapshot.close()
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    assert s.project(attest(s, checkpoint=2))["availability"] == "AVAILABLE"

    restored = sqlite3.connect(str(tmp_path / "ancien.db"))
    target = sqlite3.connect(str(db))
    restored.backup(target)
    restored.close()
    target.close()
    rouvert = DurableGovernedStore(db, {"PROBLEM": "problem-registry"}, trust_policy=policy(),
                                   clock=Clock(), allow_colocated_anchor=True)
    # L'ancien état signé est encore accepté : le retour arrière n'est PAS détecté.
    assert rouvert.project(ancien)["availability"] == "AVAILABLE"


# --- Unicité du matériau de clé publique (revue complémentaire, a74ce54) -----

_GRANTS = (("problem-registry", "PROBLEM", "planifier"),)


def _cle(sk, key_id, role, identity):
    grants = _GRANTS if role in (SOURCE_OWNER, ADMISSION_APPROVER) else ()
    return trusted_key(sk, key_id, role, identity, grants=grants)


def test_meme_cle_privee_sous_deux_roles_et_deux_identites_refusee():
    """Reproduction de la revue : UNE clé Ed25519, deux `key_id`, deux
    identités, deux rôles, même triplet autorisé."""
    sk = Ed25519PrivateKey.generate()
    proprietaire = _cle(sk, "owner", SOURCE_OWNER, "person-owner")
    approbateur = _cle(sk, "approver", ADMISSION_APPROVER, "person-approver")
    with pytest.raises(ContractError, match="matériau de clé public réutilisé"):
        TrustPolicy(policy_version=POLICY_VERSION, keys=(proprietaire, approbateur))


@pytest.mark.parametrize("role_a,role_b", [
    (SOURCE_OWNER, ADMISSION_APPROVER),
    (SOURCE_OWNER, AVAILABILITY_AUTHORITY),
    (SOURCE_OWNER, EVIDENCE_ACCESS_AUTHORITY),
    (ADMISSION_APPROVER, AVAILABILITY_AUTHORITY),
    (ADMISSION_APPROVER, EVIDENCE_ACCESS_AUTHORITY),
    (AVAILABILITY_AUTHORITY, EVIDENCE_ACCESS_AUTHORITY),
])
def test_aucun_cumul_de_roles_par_materiau_cryptographique(role_a, role_b):
    sk = Ed25519PrivateKey.generate()
    with pytest.raises(ContractError, match="matériau de clé public réutilisé"):
        TrustPolicy(policy_version=POLICY_VERSION, keys=(
            _cle(sk, "cle-a", role_a, "personne-a"),
            _cle(sk, "cle-b", role_b, "personne-b"),
        ))


def test_alias_de_cle_du_meme_role_refuse_donc_pas_de_contournement_de_revocation():
    """Sans ce refus, révoquer `k1` laisserait le MÊME matériau signer via `k2`."""
    sk = Ed25519PrivateKey.generate()
    k1 = _cle(sk, "k1", SOURCE_OWNER, "fixture:proprietaire-problem")
    k2 = _cle(sk, "k2", SOURCE_OWNER, "fixture:proprietaire-problem")
    with pytest.raises(ContractError, match="matériau de clé public réutilisé"):
        TrustPolicy(policy_version=POLICY_VERSION, keys=(k1, k2),
                    revoked_key_ids=frozenset({"k1"}))


def test_rotation_par_nouvelle_cle_reste_valide(tmp_path):
    """Rotation : ancienne clé révoquée + NOUVEAU matériau, même identité, même rôle."""
    nouvelle_sk = Ed25519PrivateKey.generate()
    nouvelle = trusted_key(nouvelle_sk, "fixture-owner-2", SOURCE_OWNER,
                           "fixture:proprietaire-problem", grants=(GRANT,))
    pol = policy(keys=(OWNER_KEY, nouvelle, APPROVER_KEY, AUTHORITY_KEY, ACCESS_KEY),
                 revoked_key_ids=frozenset({"fixture-owner-1"}))
    s = store(tmp_path / "store.db", trust_policy=pol)
    c = candidate()
    tr_nouveau = transfer(c, sk=nouvelle_sk, key_id="fixture-owner-2")
    assert admit(s, c, tr=tr_nouveau)
    autre = candidate(source_id="problem-2", candidate_id="cand-2")
    with pytest.raises(TrustError, match="révoquée"):  # l'ancienne clé ne signe plus
        s.admit(autre, owner_transfer=transfer(autre),
                approval=approval(autre), command_id="cmd-2")


# --- Refus explicite des anciennes versions de schéma (3.0.0) ----------------

@pytest.mark.parametrize("ancienne", ["1.0.0", "2.0.0"])
def test_evenements_d_une_version_anterieure_refuses_sans_ajout(tmp_path, ancienne):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE events SET schema_version = ? WHERE sequence = 1", (ancienne,))
    conn.close()
    with pytest.raises(CorruptedJournalError, match="version de schéma inconnue"):
        s.verify()
    assert s.project(attest(s))["availability"] == "UNKNOWN"
    with pytest.raises(CorruptedJournalError):  # jamais d'ajout sur un journal ancien
        admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    assert len(s.events()) == 1


@pytest.mark.parametrize("ancienne", ["1.0.0", "2.0.0"])
def test_base_d_une_version_anterieure_refusee_a_l_ouverture(tmp_path, ancienne):
    db = tmp_path / "store.db"
    admit(store(db), candidate(), command_id="cmd-1")
    conn = _raw(db)
    conn.execute("UPDATE schema_meta SET schema_version = ? WHERE id = 1", (ancienne,))
    conn.close()
    with pytest.raises(CorruptedJournalError, match="version antérieure ou inconnue"):
        store(db)


def test_journal_v1_sans_journal_id_refuse_explicitement_et_reste_intact(tmp_path):
    """Un vrai journal 1.0.0 (sans `journal_id`) : refus intelligible, aucune
    altération de schéma, aucun événement réécrit (append-only)."""
    db = tmp_path / "ancien.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE schema_meta (id INTEGER PRIMARY KEY CHECK (id = 1),
                                  schema_version TEXT NOT NULL);
        INSERT INTO schema_meta VALUES (1, '1.0.0');
        CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_id TEXT, decision_id TEXT,
            schema_version TEXT, idempotency_key TEXT, previous_event_hash TEXT,
            event_hash TEXT, payload_json TEXT);
        INSERT INTO events VALUES (1, 'e1', 'd1', '1.0.0', 'k1', 'GENESIS', 'h1', '{}');
    """)
    conn.commit()
    conn.close()
    with pytest.raises(CorruptedJournalError, match="version antérieure ou inconnue"):
        store(db)
    conn = sqlite3.connect(str(db))
    try:
        colonnes = [r[1] for r in conn.execute("PRAGMA table_info(schema_meta)")]
        assert colonnes == ["id", "schema_version"]  # aucune ALTER
        assert conn.execute("SELECT payload_json FROM events").fetchall() == [("{}",)]
    finally:
        conn.close()


def test_base_partiellement_initialisee_sans_evenement_reste_ouvrable(tmp_path):
    """Le refus des anciennes versions ne doit pas bloquer une initialisation
    interrompue avant l'écriture de la version (aucun événement, aucune ligne)."""
    db = tmp_path / "store.db"
    store(db)
    conn = _raw(db)
    conn.execute("DELETE FROM schema_meta")
    conn.close()
    rouvert = store(db)
    assert rouvert.events() == ()
    assert rouvert.project(None)["availability"] == "NON DÉPLOYÉ"
