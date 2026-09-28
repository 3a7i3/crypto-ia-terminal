"""Vérifications R2 : stockage durable hors runtime, isolé (fixtures uniquement).

Aucun test ici ne touche au runtime PAPER, à un JSONL réel, à Telegram, à
l'exchange ou à un service déployé. La base SQLite est un fichier temporaire
créé et détruit par chaque test.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace

import pytest

from observability.operator_decisions.durable_store import (
    AvailabilityProof, CorruptedJournalError, DurableGovernedStore,
)
from observability.operator_decisions.producer import Candidate, ContractError

NOW = "2026-09-28T03:00:00Z"


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


def store(path) -> DurableGovernedStore:
    return DurableGovernedStore(path, {"PROBLEM": "problem-registry"})


def proof(count: int) -> AvailabilityProof:
    return AvailabilityProof(True, "deploy-audit:sha256:abc", count, NOW)


def admit(s: DurableGovernedStore, c: Candidate, command_id: str = "cmd-1") -> str:
    return s.admit(
        c, occurred_at_utc=NOW, approved_status="TO_PLAN",
        approved_priority="HIGH", admission_approval_ref="gate:review-1",
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
    """
    from observability.operator_decisions.durable_store import DurableGovernedStore

    db = tmp_path / "store.db"
    s = store(db)
    admit(s, candidate(), command_id="cmd-1")

    original_verify_locked = DurableGovernedStore._verify_locked
    injected = {"done": False}

    def corrupting_verify(conn):
        if not injected["done"]:
            injected["done"] = True
            raw = sqlite3.connect(str(db), isolation_level=None)
            raw.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 1")
            raw.close()
        return original_verify_locked(conn)

    monkeypatch.setattr(DurableGovernedStore, "_verify_locked", staticmethod(corrupting_verify))

    view = s.project(proof(1))
    assert injected["done"]
    assert view["availability"] == "AVAILABLE"
    assert view["decision_count"] == 1


def test_admission_concurrente_pendant_une_projection_ne_produit_aucune_incoherence(tmp_path):
    """Revue indépendante PR #316 (review_id 5333698547), point 3 (stress).

    Un thread admet de nouveaux candidats pendant qu'un autre projette en
    boucle : quel que soit l'entrelacement réel, chaque projection doit
    rester interne cohérente (jamais de crash, et `decision_count` toujours
    égal à `len(items)` et à `as_of_event_version` quand `AVAILABLE`).
    """
    db = tmp_path / "store.db"
    s0 = store(db)
    errors: list[Exception] = []

    def admit_many():
        try:
            for i in range(10):
                admit(store(db), candidate(source_id=f"problem-{i}", candidate_id=f"cand-{i}"),
                      command_id=f"cmd-{i}")
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    def project_many():
        try:
            for _ in range(30):
                n = len(store(db).events())
                view = store(db).project(proof(n))
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
