"""Tests du socle d'objets scientifiques (Phase B1).

Chaque test vise un invariant nommé du modèle gelé V5-FOUNDATION-1.0.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from scios.objects import (
    ActorType,
    ConfidenceBasis,
    IdentityError,
    IdRegistry,
    ObjectError,
    ObjectStore,
    Observation,
    Provenance,
    ProvenanceError,
    StoreError,
    measurement,
)


@pytest.fixture()
def store(tmp_path) -> ObjectStore:
    return ObjectStore(tmp_path / "knowledge")


@pytest.fixture()
def prov() -> Provenance:
    return measurement(
        tool="tools/runtime_cartographer.py",
        method="analyse AST du graphe d'import, puis mesure .pyc sur l'hôte",
        limitations=(
            "borne inférieure : les branches non prises au boot ne sont pas couvertes"
        ),
    )


# ── M2 : provenance obligatoire ──────────────────────────────────────────────


def test_provenance_refuse_limitations_vides(prov):
    with pytest.raises(ProvenanceError, match="limitations"):
        dataclasses.replace(prov, limitations="")


@pytest.mark.parametrize("sentinelle", ["-", "N/A", "aucune", "TODO", "  none  "])
def test_provenance_refuse_les_sentinelles(prov, sentinelle):
    with pytest.raises(ProvenanceError, match="limitations"):
        dataclasses.replace(prov, limitations=sentinelle)


def test_provenance_refuse_confidence_sans_base(prov):
    with pytest.raises(ProvenanceError, match="confidence_basis"):
        Provenance(
            actor_type=ActorType.HUMAN,
            actor_id="operator",
            method="lecture",
            limitations="jugement humain non reproductible",
            confidence=0.9,
        )


def test_provenance_agent_exige_une_implementation():
    with pytest.raises(ProvenanceError, match="actor_impl"):
        Provenance(
            actor_type=ActorType.AGENT,
            actor_id="council.statistician",
            method="analyse",
            limitations="aucune expérience menée",
        )


def test_role_permanent_et_implementation_remplacable():
    """Le rôle survit au modèle : deux implémentations, un seul actor_id."""
    commun = {
        "actor_type": ActorType.AGENT,
        "actor_id": "council.statistician",
        "method": "test de Student sur les rendements",
        "limitations": "N insuffisant pour la puissance visée",
        "confidence": 0.6,
        "confidence_basis": ConfidenceBasis.REASONING,
    }
    hier = Provenance(**commun, actor_impl="modele-a", actor_version="1")
    demain = Provenance(**commun, actor_impl="modele-b", actor_version="9")
    assert hier.actor_id == demain.actor_id
    assert hier.actor_impl != demain.actor_impl


# ── Identité : jamais réattribuée ────────────────────────────────────────────


def test_identifiants_monotones(tmp_path):
    reg = IdRegistry(tmp_path / "identity.jsonl")
    assert reg.allocate("Observation", 2026) == "OBS-2026-001"
    assert reg.allocate("Observation", 2026) == "OBS-2026-002"
    assert reg.allocate("Hypothesis", 2026) == "HYP-2026-001"


def test_identifiant_jamais_reattribue_apres_rechargement(tmp_path):
    path = tmp_path / "identity.jsonl"
    IdRegistry(path).allocate("Observation", 2026)
    # Nouveau registre : le journal est la source de vérité, pas la mémoire.
    assert IdRegistry(path).allocate("Observation", 2026) == "OBS-2026-002"


def test_reserve_refuse_une_reattribution(tmp_path):
    reg = IdRegistry(tmp_path / "identity.jsonl")
    reg.reserve("OBS-2026-042")
    with pytest.raises(IdentityError, match="réattribution interdite"):
        reg.reserve("OBS-2026-042")


def test_type_hors_modele_gele_refuse(tmp_path):
    reg = IdRegistry(tmp_path / "identity.jsonl")
    with pytest.raises(IdentityError, match="ADR"):
        reg.allocate("Serendipity", 2026)


# ── SCIENTIFIC_PROTOCOL §2 : une observation ne dit jamais pourquoi ──────────


def test_observation_refuse_un_enonce_causal(store, prov):
    with pytest.raises(ObjectError, match="marqueur causal"):
        store.create(
            Observation,
            2026,
            provenance=prov,
            statement="Le PF est bas parce que le score ne classe pas les trades.",
        )


def test_observation_accepte_un_enonce_descriptif(store, prov):
    obs = store.create(
        Observation,
        2026,
        provenance=prov,
        statement="rho = 0.16 entre score et rendement a 12-24 h ; N = 139.",
        metrics={"rho": 0.16, "auc": 0.60},
        n=139,
        epoch_id="EPO-004",
    )
    assert obs.id == "OBS-2026-001"
    assert obs.n == 139


def test_contournement_causal_possible_mais_explicite(store, prov):
    obs = store.create(
        Observation,
        2026,
        provenance=prov,
        statement="Le module A cause le chargement du module B a l'import.",
        allow_causal_terms=True,
    )
    assert obs.to_dict()["allow_causal_terms"] is True


# ── M1 : immuabilité, succession jamais mutation ─────────────────────────────


def test_objet_immuable(store, prov):
    obs = store.create(
        Observation, 2026, provenance=prov, statement="210 modules executes sur 1115."
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.statement = "autre chose"


def test_succession_cree_un_nouvel_objet_sans_toucher_l_ancien(store, prov):
    v1 = store.create(
        Observation, 2026, provenance=prov, statement="170 modules atteignables.", n=170
    )
    v2 = store.supersede(v1, 2026, statement="210 modules reellement executes.", n=210)

    assert v2.version == 2
    assert v2.supersedes == v1.id
    assert v1.n == 170, "l'objet original ne doit jamais être muté en mémoire"

    courant = store.current()
    assert courant[v1.id].superseded_by == v2.id
    assert courant[v2.id].n == 210


def test_un_objet_ne_peut_pas_se_succeder_a_lui_meme(store, prov):
    obs = store.create(Observation, 2026, provenance=prov, statement="fait mesure.")
    with pytest.raises(ObjectError, match="lui-même"):
        dataclasses.replace(obs, supersedes=obs.id)


# ── Magasin : append-only, intégrité ─────────────────────────────────────────


def test_journal_append_only(store, prov):
    store.create(Observation, 2026, provenance=prov, statement="premier fait.")
    store.create(Observation, 2026, provenance=prov, statement="second fait.")
    lignes = store.journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 2


def test_append_refuse_un_id_non_alloue(store, prov):
    orphelin = Observation(
        id="OBS-2026-999",
        created_at="2026-08-02T00:00:00+00:00",
        provenance=prov,
        statement="objet fabrique hors du registre.",
    )
    with pytest.raises(StoreError, match="registre d'identité"):
        store.append(orphelin)


def test_aller_retour_json_preserve_l_empreinte(store, prov):
    obs = store.create(
        Observation,
        2026,
        provenance=prov,
        statement="PF = 0.617, WR = 34.9 %, t = -1.571 ; N = 139.",
        metrics={"pf": 0.617, "wr": 0.349, "t": -1.571},
        n=139,
    )
    relu = store.get(obs.id)
    assert relu.fingerprint() == obs.fingerprint()
    assert relu.to_dict() == obs.to_dict()


def test_verify_detecte_une_alteration_posterieure(store, prov):
    store.create(Observation, 2026, provenance=prov, statement="fait initial.")
    assert store.verify() == []

    rec = json.loads(store.journal.read_text(encoding="utf-8").strip())
    rec["statement"] = "fait reecrit apres coup."
    store.journal.write_text(
        json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    problemes = store.verify()
    assert len(problemes) == 1
    assert "empreinte incohérente" in problemes[0]


def test_historique_complet_rejouable(store, prov):
    v1 = store.create(Observation, 2026, provenance=prov, statement="version un.")
    store.supersede(v1, 2026, statement="version deux.")
    assert len(store.history(v1.id)) == 2


def test_index_reconstructible_depuis_le_journal(store, prov, tmp_path):
    """PM-1 : perdre l'index ne perd aucune connaissance."""
    obs = store.create(Observation, 2026, provenance=prov, statement="fait durable.")
    rouvert = ObjectStore(tmp_path / "knowledge")
    assert rouvert.get(obs.id).fingerprint() == obs.fingerprint()


# ── M3 : auto-descriptif, lisible sans le producteur ─────────────────────────


def test_serialisation_est_du_json_lisible(store, prov):
    obs = store.create(Observation, 2026, provenance=prov, statement="fait mesure.")
    brut = json.loads(store.journal.read_text(encoding="utf-8").strip())
    assert brut["kind"] == "Observation"
    assert brut["provenance"]["actor_id"] == "tools/runtime_cartographer.py"
    assert brut["provenance"]["limitations"]
    assert isinstance(brut["statement"], str)
    assert obs.canonical_json() == json.dumps(
        obs.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def test_scios_n_importe_rien_du_runtime():
    """Le laboratoire ne peut pas casser le moteur."""
    import pathlib

    racine = pathlib.Path(__file__).resolve().parents[2] / "scios"
    interdits = (
        "core.",
        "quant_hedge_ai",
        "paper_trading",
        "supervision",
        "tracker_system",
    )
    for module in racine.rglob("*.py"):
        texte = module.read_text(encoding="utf-8")
        for ligne in texte.splitlines():
            nu = ligne.strip()
            if nu.startswith(("import ", "from ")):
                assert not any(i in nu for i in interdits), f"{module.name}: {nu}"
