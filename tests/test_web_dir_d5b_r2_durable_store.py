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

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from observability.operator_decisions.durable_store import (
    AvailabilityProof, CorruptedJournalError, DurableGovernedStore,
    admission_approval_payload,
)
from observability.operator_decisions.producer import Candidate, ContractError
from observability.operator_decisions.trust import (
    ADMISSION_APPROVER, AVAILABILITY_AUTHORITY, TrustError, TrustPolicy,
    sign_statement, trusted_key,
)

NOW = "2026-09-28T03:00:00Z"
NOW_DT = datetime(2026, 9, 28, 3, 0, 0, tzinfo=timezone.utc)

# --- Fixtures de confiance NON OPÉRATIONNELLES (ADR-0020 §4) -----------------
# Clés générées à la volée pour ce module de test, jamais persistées, jamais
# réutilisables hors test. Elles ne représentent AUCUNE autorité réelle.
FIXTURE_NON_OPERATIONNELLE = True
APPROVER_SK = Ed25519PrivateKey.generate()
AUTHORITY_SK = Ed25519PrivateKey.generate()
ROGUE_SK = Ed25519PrivateKey.generate()
POLICY_VERSION = "fixture-policy-v1"
APPROVER_KEY = trusted_key(
    APPROVER_SK, "fixture-approver-1", ADMISSION_APPROVER,
    "fixture:approbateur-problem", scopes=("problem-registry",),
)
AUTHORITY_KEY = trusted_key(
    AUTHORITY_SK, "fixture-authority-1", AVAILABILITY_AUTHORITY,
    "fixture:autorite-disponibilite",
)


def policy(**overrides) -> TrustPolicy:
    base = dict(policy_version=POLICY_VERSION, keys=(APPROVER_KEY, AUTHORITY_KEY))
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


def store(path, *, trust_policy: TrustPolicy | None = None, clock=None) -> DurableGovernedStore:
    return DurableGovernedStore(
        path, {"PROBLEM": "problem-registry"},
        trust_policy=trust_policy or policy(), clock=clock or Clock(),
    )


def approval(c: Candidate, *, sk=APPROVER_SK, key_id="fixture-approver-1", **overrides):
    fields = dict(
        policy_version=POLICY_VERSION, approver_id="fixture:approbateur-problem",
        approved_status="TO_PLAN", approved_priority="MEDIUM",
        transfer_ref="transfert:problem-registry->operator-decision:1",
        approval_id="approbation-1", issued_at_utc=_iso(NOW_DT - timedelta(minutes=1)),
        expires_at_utc=_iso(NOW_DT + timedelta(minutes=30)),
    )
    payload_overrides = {k: overrides.pop(k) for k in list(overrides) if k not in fields}
    fields.update(overrides)
    payload = admission_approval_payload(c, **fields)
    payload.update(payload_overrides)
    return sign_statement(sk, key_id, payload)


def proof(count: int) -> AvailabilityProof:
    return AvailabilityProof(True, "deploy-audit:sha256:abc", count, NOW)


def admit(s: DurableGovernedStore, c: Candidate, command_id: str = "cmd-1",
          appr=None) -> str:
    return s.admit(c, approval=appr or approval(c), command_id=command_id)


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
    view = fresh.project(proof(2))
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 2
    assert view == fresh.project(proof(2))  # déterministe


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
    view = corrupted.project(proof(1))
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
    assert corrupted.project(proof(2))["availability"] == "UNKNOWN"


def test_troncature_du_journal_echoue_ferme(tmp_path):
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")
    admit(s, candidate(source_id="problem-2", candidate_id="cand-2"), command_id="cmd-2")
    conn = _raw(db)
    conn.execute("DELETE FROM events WHERE sequence = 1")  # trou de séquence
    conn.close()

    corrupted = store(db)
    assert corrupted.project(proof(1))["availability"] == "UNKNOWN"
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
    assert corrupted.project(proof(1))["availability"] == "UNKNOWN"


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
    with pytest.raises(ContractError):
        s.project(AvailabilityProof(False, "ref", 1, NOW))


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
    `DurableGovernedStore` n'était donc nécessaire pour CE flaking précis
    (la retenue SQLite ajoutée reste une résilience défensive raisonnable,
    sans rapport avec ce symptôme).
    """
    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")

    original_verify_locked = type(s)._verify_locked
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

    view = s.project(proof(1))
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
    de "gagner" une course. Le seul risque de flaking résiduel est le même
    que celui diagnostiqué sur
    `test_project_lit_et_verifie_sous_un_instantane_transactionnel_unique` :
    un `sqlite3.OperationalError` transitoire (connexion/verrou) sous forte
    contention réelle (10 admissions + 30 projections concurrentes, dans un
    processus qui peut déjà tourner 6549+ tests). `_read_events_verified`
    absorbe désormais ce cas par une retenue bornée côté production ; on
    ajoute ici, uniquement côté test, une retenue bornée symétrique autour de
    chaque opération pour ne jamais confondre cette contention transitoire
    avec une vraie incohérence — sans jamais retenter après une `AssertionError`
    (une vraie violation d'invariant doit rester fatale immédiatement).
    """
    db = tmp_path / "store.db"
    s0 = store(db)
    errors: list[Exception] = []

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
                n = _retrying(lambda: len(store(db).events()))
                view = _retrying(lambda n=n: store(db).project(proof(n)))
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
    view = s.project(proof(1))  # watermark incomplet (2 événements réels)
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
    assert "zéro non authentifié" in " ".join(view["limitations"])


# --- Approbation signée liée au contenu (ADR-0020, étape 2) ------------------

def _refus_sans_ecriture(s, c, appr, match=None):
    with pytest.raises((TrustError, ContractError), match=match):
        s.admit(c, approval=appr, command_id="cmd-refus")
    assert s.events() == ()


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
                        "fixture:approbateur-problem", scopes=("bounty-registry",))
    s = store(tmp_path / "store.db", trust_policy=policy(keys=(other, AUTHORITY_KEY)))
    c = candidate()
    _refus_sans_ecriture(s, c, approval(c), match="propriétaire")


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
