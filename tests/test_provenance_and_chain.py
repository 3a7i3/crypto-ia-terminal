"""
Preuve de transformation et audit de chaîne — § 20 / § 20.1 du protocole.

Deux limites constatées le 2026-07-29 :
  1. une transformation DÉCLARÉE n'est pas une transformation PROUVÉE ;
  2. une couverture citée en remarque n'engage personne.

`system/provenance.py` y répond par des empreintes vérifiables et un plafond de
confiance mécanique ; `tools/chain_audit.py` vérifie que la garantie survit à
chaque arête artefact — le défaut de la gate D (rapport de 559.8 h, population
étrangère, clé jamais écrite) est le précédent de chacun des quatre contrôles.

Invariants verrouillés ici :
  PROV-01  l'empreinte d'une structure ne dépend pas de l'ordre des clés
  PROV-02  la provenance hache l'OUTIL : deux versions = deux empreintes
  PROV-03  verify_provenance détecte schéma inconnu, date absente, entrée
           modifiée, corps édité — et ne lève jamais
  PROV-04  Coverage porte un plafond MÉCANIQUE (3/234 -> FAIBLE)
  PROV-05  weakest_ceiling implémente le maillon faible
  CHAIN-01 un artefact absent rend les quatre contrôles ABSENT, plafond AUCUNE
  CHAIN-02 artefact sans date -> PROVENANCE rompue
  CHAIN-03 population déclarée mais jamais lue par le consommateur -> rompue
  CHAIN-04 artefact périmé -> FRAICHEUR rompue
  CHAIN-05 clé consommée absente de l'artefact -> CONTRAT rompu (défaut gate D)
  CHAIN-06 la chaîne vaut son maillon faible, et les chaînes réelles sont valides
"""

from __future__ import annotations

import json

from system.provenance import (
    CEILING_FULL,
    CEILING_HIGH,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_NONE,
    PROVENANCE_SCHEMA_VERSION,
    Coverage,
    InputRef,
    build_provenance,
    sha256_file,
    sha256_json,
    verify_provenance,
    weakest_ceiling,
)
from tools.chain_audit import (
    CHAINS,
    CHECK_CONTRACT,
    CHECK_FRESHNESS,
    CHECK_POPULATION,
    CHECK_PROVENANCE,
    STATUS_ABSENT,
    STATUS_BROKEN,
    STATUS_OK,
    Edge,
    audit_edge,
    build_report,
)


def _status(report, check: str) -> str:
    return next(c.status for c in report.checks if c.check == check)


def _detail(report, check: str) -> str:
    return next(c.detail for c in report.checks if c.check == check)


# ── PROV-01 / PROV-02 ─────────────────────────────────────────────────────────


def test_prov01_empreinte_independante_de_l_ordre_des_cles():
    """Sinon un changement de version de bibliothèque simulerait une édition."""
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})
    assert sha256_json({"a": 1}) != sha256_json({"a": 2})


def test_prov01_fichier_absent_donne_none_et_non_une_exception():
    assert sha256_file(__import__("pathlib").Path("nexiste_pas_du_tout.json")) is None


def test_prov02_la_provenance_hache_l_outil(tmp_path):
    tool = tmp_path / "outil.py"
    tool.write_text("print('v1')\n", encoding="utf-8")
    p1 = build_provenance(tool_path=tool, generated_at="2026-07-29T00:00:00Z")
    tool.write_text("print('v2')\n", encoding="utf-8")
    p2 = build_provenance(tool_path=tool, generated_at="2026-07-29T00:00:00Z")
    assert p1.tool_sha256 != p2.tool_sha256
    assert p1.schema_version == PROVENANCE_SCHEMA_VERSION


def test_prov02_les_entrees_portent_leur_empreinte(tmp_path):
    data = tmp_path / "entree.jsonl"
    data.write_text('{"a": 1}\n', encoding="utf-8")
    tool = tmp_path / "outil.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    prov = build_provenance(
        tool_path=tool,
        inputs=[InputRef(str(data), sha256_file(data), n_records=1)],
        population={"n": 1, "loader": "test"},
    )
    assert prov.inputs[0].sha256 == sha256_file(data)
    assert prov.to_dict()["population"]["n"] == 1


# ── PROV-03 ───────────────────────────────────────────────────────────────────


def test_prov03_schema_inconnu_est_signale():
    issues = verify_provenance({"schema_version": 999, "generated_at": "x"})
    assert any("schema_version 999" in i for i in issues)


def test_prov03_date_absente_est_signalee():
    issues = verify_provenance({"schema_version": PROVENANCE_SCHEMA_VERSION})
    assert any("generated_at absent" in i for i in issues)


def test_prov03_entree_modifiee_est_detectee(tmp_path):
    data = tmp_path / "entree.jsonl"
    data.write_text('{"a": 1}\n', encoding="utf-8")
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-29T00:00:00Z",
        "inputs": [{"path": str(data), "sha256": sha256_file(data)}],
    }
    assert verify_provenance(stamp) == []
    data.write_text('{"a": 2}\n', encoding="utf-8")
    assert any("modifiée depuis la production" in i for i in verify_provenance(stamp))


def test_prov03_entree_disparue_est_detectee(tmp_path):
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-29T00:00:00Z",
        "inputs": [{"path": str(tmp_path / "jamais.jsonl"), "sha256": "deadbeef"}],
    }
    assert any("disparue" in i for i in verify_provenance(stamp))


def test_prov03_corps_edite_apres_production_est_detecte():
    body = {"go_no_go": "NO_GO", "n": 121}
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-29T00:00:00Z",
        "output_sha256": sha256_json(body),
    }
    assert verify_provenance(stamp, body=body) == []
    falsifie = {"go_no_go": "GO", "n": 121}
    assert any(
        "modifié après production" in i for i in verify_provenance(stamp, body=falsifie)
    )


def test_prov03_ne_leve_jamais_sur_une_provenance_malformee():
    """Un vérificateur qui meurt laisse le consommateur sans information."""
    assert verify_provenance(None) == ["provenance absente ou de type inattendu"]
    assert verify_provenance("pas un dict")  # non vide, mais pas d'exception
    assert verify_provenance({"schema_version": 1, "generated_at": "x", "inputs": [42]})


# ── PROV-04 / PROV-05 ─────────────────────────────────────────────────────────


def test_prov04_le_plafond_est_mecanique():
    assert Coverage(3, 234).confidence_ceiling == CEILING_LOW
    assert Coverage(30, 234).confidence_ceiling == CEILING_MEDIUM
    assert Coverage(150, 234).confidence_ceiling == CEILING_HIGH
    assert Coverage(234, 234).confidence_ceiling == CEILING_FULL


def test_prov04_zero_mesure_ou_zero_total_donne_aucune():
    assert Coverage(0, 234).confidence_ceiling == CEILING_NONE
    assert Coverage(0, 0).confidence_ceiling == CEILING_NONE
    assert Coverage(0, 0).ratio == 0.0


def test_prov04_le_cas_reel_init_order_plafonne_a_faible():
    """3 constantes mesurées sur 234 : le rapport ne peut pas écrire « vérifié »."""
    cov = Coverage(3, 234, subject="constantes INIT-ORDER mesurées")
    assert cov.ratio < 0.02
    assert cov.confidence_ceiling == CEILING_LOW
    assert "plafond de confiance FAIBLE" in cov.sentence()
    assert cov.unmeasured == 231


def test_prov05_maillon_faible():
    assert weakest_ceiling([CEILING_FULL, CEILING_LOW, CEILING_HIGH]) == CEILING_LOW
    assert weakest_ceiling([CEILING_FULL, CEILING_FULL]) == CEILING_FULL
    assert weakest_ceiling([]) == CEILING_FULL
    assert weakest_ceiling([CEILING_FULL, "PAS_UN_PLAFOND"]) == CEILING_NONE


# ── CHAIN-01..05 ──────────────────────────────────────────────────────────────


def _edge(artifact: str, **kw) -> Edge:
    defaults = dict(
        producer="faux/producteur.py",
        consumer="faux/consommateur.py",
        keys_consumed=("verdict",),
        max_age_hours=24.0,
    )
    defaults.update(kw)
    return Edge(artifact=artifact, **defaults)


def test_chain01_artefact_absent_interrompt_la_chaine(tmp_path):
    report = audit_edge(_edge("nexiste_pas.json"), tmp_path)
    assert report.exists is False
    assert all(c.status == STATUS_ABSENT for c in report.checks)
    assert report.confidence_ceiling == CEILING_NONE


def test_chain02_artefact_sans_date(tmp_path):
    (tmp_path / "a.json").write_text('{"verdict": "GO"}', encoding="utf-8")
    report = audit_edge(_edge("a.json"), tmp_path)
    assert _status(report, CHECK_PROVENANCE) == STATUS_BROKEN
    assert "aucune date" in _detail(report, CHECK_PROVENANCE)


def test_chain03_population_declaree_mais_jamais_lue(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "verdict": "GO",
                "generated_at": "2999-01-01T00:00:00Z",
                "dataset_provenance": {"n_canonical": 121},
            }
        ),
        encoding="utf-8",
    )
    consumer = tmp_path / "consommateur.py"
    consumer.write_text("data = json.load(f)\nv = data['verdict']\n", encoding="utf-8")
    report = audit_edge(_edge("a.json", consumer="consommateur.py"), tmp_path)
    assert _status(report, CHECK_POPULATION) == STATUS_BROKEN
    assert "sans être vérifiée" in _detail(report, CHECK_POPULATION)


def test_chain03_population_lue_par_le_consommateur_passe(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "verdict": "GO",
                "generated_at": "2999-01-01T00:00:00Z",
                "dataset_provenance": {"n_canonical": 121},
            }
        ),
        encoding="utf-8",
    )
    consumer = tmp_path / "consommateur.py"
    consumer.write_text("pop = data['dataset_provenance']\n", encoding="utf-8")
    report = audit_edge(_edge("a.json", consumer="consommateur.py"), tmp_path)
    assert _status(report, CHECK_POPULATION) == STATUS_OK


def test_chain04_artefact_perime(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps({"verdict": "GO", "generated_at": "2026-07-05T00:00:00Z"}),
        encoding="utf-8",
    )
    report = audit_edge(_edge("a.json", max_age_hours=24.0), tmp_path)
    assert _status(report, CHECK_FRESHNESS) == STATUS_BROKEN
    assert "système qui a changé" in _detail(report, CHECK_FRESHNESS)


def test_chain05_cle_consommee_absente_est_le_defaut_gate_d(tmp_path):
    """`burnin_passed` était lue par la gate D et écrite par personne."""
    (tmp_path / "a.json").write_text(
        json.dumps({"go_no_go": "NO_GO", "generated_at": "2999-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    report = audit_edge(_edge("a.json", keys_consumed=("burnin_passed",)), tmp_path)
    assert _status(report, CHECK_CONTRACT) == STATUS_BROKEN
    assert "burnin_passed" in _detail(report, CHECK_CONTRACT)
    assert "gate D" in _detail(report, CHECK_CONTRACT)


def test_chain05_jsonl_lit_la_derniere_ligne(tmp_path):
    (tmp_path / "a.jsonl").write_text(
        '{"verdict": "vieux"}\n'
        '{"verdict": "GO", "generated_at": "2999-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    report = audit_edge(_edge("a.jsonl"), tmp_path)
    assert _status(report, CHECK_CONTRACT) == STATUS_OK


# ── CHAIN-06 ──────────────────────────────────────────────────────────────────


def test_chain06_les_chaines_declarees_sont_coherentes():
    """Chaque chaîne déclare une source, des étapes et une décision nommée."""
    assert len(CHAINS) >= 3
    for chain in CHAINS:
        assert chain.source and chain.steps and chain.decision
        for edge in chain.edges:
            assert edge.artifact in chain.steps or edge.artifact.endswith(".jsonl")


def test_chain06_la_chaine_de_l_incident_est_desormais_intacte():
    """CHAIN-BURNIN-PRELIVE portait les 3 défauts du 2026-07-28.

    Vérification de bout en bout, sur l'artefact réellement présent : provenance,
    population, fraîcheur et contrat. Si ce test tombe, relancer
    burnin_calibration_v3 puis vérifier la cause AVANT de le neutraliser.
    """
    report = build_report()
    chain = next(c for c in report.chains if c.name == "CHAIN-BURNIN-PRELIVE")
    edge = chain.edges[0]
    if not edge.exists:  # artefact non produit sur cette machine
        return
    assert edge.broken == []


def test_chain06_le_plafond_global_est_le_maillon_faible():
    report = build_report()
    assert report.confidence_ceiling == weakest_ceiling(
        [report.coverage["confidence_ceiling"]]
        + [c.confidence_ceiling for c in report.chains]
    )


def test_chain06_terminaison_non_persistee_est_signalee():
    """Une décision sans trace n'est pas re-auditable : remarque, pas échec."""
    report = build_report()
    cri = next(c for c in report.chains if c.name == "CHAIN-CRI")
    assert any("TERMINAISON NON PERSISTÉE" in r for r in cri.remarks)
    assert cri.confidence_ceiling != CEILING_FULL
