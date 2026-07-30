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
  PROV-06  attach_proof est un aller-retour vérifiable ; l'empreinte exclut la preuve
  PROV-07  un artefact sans preuve est NON PROUVÉ, jamais « invalide »
  PROV-08  l'adoption est une couverture de première classe (0 % -> AUCUNE)
  PROV-09  falsification du corps ET changement de version de l'outil détectés
  CHAIN-07 contrôle PREUVE : ok / NON_PROUVE / ROMPU, trois cas distincts
  CHAIN-08 la boucle complète est démontrée sur le PREMIER producteur adopté
  CHAIN-09 deux plafonds publiés séparément + adoption sur artefacts présents
  PROV-10  output_sha256 absent ne certifie plus le corps (défaut CRITIQUE)
  PROV-11  bloc proof forgé minimal = NON PROUVÉ (défaut MAJEUR)
  PROV-12  substitution d'artefact détectée par expected_artifact
  PROV-13  chemins d'entrée relatifs résolus contre le dépôt, pas le cwd
  PROV-14  outil introuvable != outil altéré ; tool_path prime sur le nom
  CHAIN-10 la portée d'une preuve sur un JSONL est déclarée
  PROV-15  un denominateur minuscule ne donne pas un plafond eleve ;
           proof_adoption ignore les artefacts absents
  PROV-16  VALIDITE : le mecanisme passe son auto-test, cas negatifs inclus
  PROV-17  point unique d'instrumentation ; identifiant de preuve deterministe
  PROV-18  la dependance create_proof -> chain_audit est EXPLICITE
  CHAIN-11 la decision prelive est un artefact prouve qui epingle ses entrees
"""

from __future__ import annotations

import json
from pathlib import Path

from system.provenance import (
    CEILING_FULL,
    CEILING_HIGH,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_NONE,
    MIN_COMPATIBLE_PROOF_VERSION,
    MIN_TOTAL_FOR_HIGH_CEILING,
    PROOF_KEY,
    PROVENANCE_SCHEMA_VERSION,
    REQUIRED_PROOF_FIELDS,
    VALIDITY_BROKEN,
    Coverage,
    InputRef,
    artifact_has_proof,
    attach_proof,
    build_provenance,
    proof_adoption,
    self_test,
    sha256_file,
    sha256_json,
    verify_artifact,
    verify_provenance,
    weakest_ceiling,
)
from tools.chain_audit import (
    CHAINS,
    CHECK_CONTRACT,
    CHECK_FRESHNESS,
    CHECK_POPULATION,
    CHECK_PROOF,
    CHECK_PROVENANCE,
    STATUS_ABSENT,
    STATUS_BROKEN,
    STATUS_OK,
    STATUS_UNPROVEN,
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


def _stamp_complet(tmp_path, **extra) -> dict:
    """Bloc de provenance avec tous les champs désormais OBLIGATOIRES.

    Depuis la correction du 2026-07-30, l'absence de `tool_sha256`, `inputs` ou
    `output_sha256` est elle-même un écart : ces tests doivent donc partir d'un
    bloc complet pour isoler le défaut qu'ils visent.
    """
    tool = tmp_path / "outil_ref.py"
    if not tool.exists():
        tool.write_text("x = 1\n", encoding="utf-8")
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-29T00:00:00Z",
        "tool": "outil_ref.py",
        "tool_path": "outil_ref.py",
        "tool_sha256": sha256_file(tool),
        "inputs": [],
    }
    stamp.update(extra)
    return stamp


def test_prov03_entree_modifiee_est_detectee(tmp_path):
    data = tmp_path / "entree.jsonl"
    data.write_text('{"a": 1}\n', encoding="utf-8")
    stamp = _stamp_complet(
        tmp_path, inputs=[{"path": str(data), "sha256": sha256_file(data)}]
    )
    assert verify_provenance(stamp, repo_root=tmp_path) == []
    data.write_text('{"a": 2}\n', encoding="utf-8")
    assert any(
        "modifiée depuis la production" in i
        for i in verify_provenance(stamp, repo_root=tmp_path)
    )


def test_prov03_entree_disparue_est_detectee(tmp_path):
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-29T00:00:00Z",
        "inputs": [{"path": str(tmp_path / "jamais.jsonl"), "sha256": "deadbeef"}],
    }
    assert any("disparue" in i for i in verify_provenance(stamp))


def test_prov03_corps_edite_apres_production_est_detecte(tmp_path):
    body = {"go_no_go": "NO_GO", "n": 121}
    stamp = _stamp_complet(tmp_path, output_sha256=sha256_json(body))
    assert verify_provenance(stamp, body=body, repo_root=tmp_path) == []
    falsifie = {"go_no_go": "GO", "n": 121}
    assert any(
        "modifié après production" in i
        for i in verify_provenance(stamp, body=falsifie, repo_root=tmp_path)
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


# ── PROV-06..09 : le bloc de preuve et son constructeur unique ────────────────


def test_prov06_attach_proof_est_un_aller_retour_verifiable(tmp_path):
    """Le producteur écrit, le consommateur relit : la boucle doit fermer."""
    tool = tmp_path / "producteur.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    body = {"go_no_go": "NO_GO", "n": 121}
    artefact = attach_proof(body, tool_path=tool, population={"n_canonical": 121})
    assert artifact_has_proof(artefact)
    assert verify_artifact(artefact, repo_root=tmp_path) == []


def test_prov06_l_empreinte_de_sortie_exclut_le_bloc_de_preuve(tmp_path):
    """Sinon ajouter la preuve changerait l'empreinte de ce qu'elle prouve.

    Propriété non négociable : le bloc doit pouvoir être retiré pour recalculer
    l'empreinte. Un artefact auto-référentiel serait invérifiable.
    """
    tool = tmp_path / "producteur.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    body = {"a": 1, "b": [2, 3]}
    artefact = attach_proof(body, tool_path=tool)
    corps = {k: v for k, v in artefact.items() if k != PROOF_KEY}
    assert artefact[PROOF_KEY]["output_sha256"] == sha256_json(corps)


def test_prov06_reattacher_une_preuve_est_idempotent(tmp_path):
    """Une preuve déjà présente est ignorée pour le calcul, jamais empilée."""
    tool = tmp_path / "producteur.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    once = attach_proof({"a": 1}, tool_path=tool, generated_at="2026-07-30T00:00:00Z")
    twice = attach_proof(once, tool_path=tool, generated_at="2026-07-30T00:00:00Z")
    assert once[PROOF_KEY]["output_sha256"] == twice[PROOF_KEY]["output_sha256"]
    assert verify_artifact(twice, repo_root=tmp_path) == []


def test_prov07_un_artefact_sans_preuve_est_non_prouve_pas_invalide():
    """« Je ne peux pas vérifier » n'est pas « la vérification échoue ».

    Confondre les deux ferait apparaître tout le dépôt comme rompu le jour où le
    contrôle a été ajouté, ce qui serait faux.
    """
    issues = verify_artifact({"go_no_go": "GO", "generated_at": "2026-07-30T00:00:00Z"})
    assert len(issues) == 1
    assert "NON PROUVÉ" in issues[0]
    assert "adoption" in issues[0]


def test_prov08_l_adoption_est_une_couverture_de_premiere_classe(tmp_path):
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    prouve = attach_proof({"a": 1}, tool_path=tool)
    cov = proof_adoption([prouve, {"a": 2}, {"a": 3}])
    assert cov.measured == 1 and cov.total == 3
    assert cov.confidence_ceiling == CEILING_MEDIUM
    assert "plafond de confiance" in cov.sentence()


def test_prov08_adoption_nulle_plafonne_a_aucune():
    """0 % d'adoption : un protocole parfait non utilisé équivaut à son absence."""
    assert proof_adoption([{"a": 1}, {"b": 2}]).confidence_ceiling == CEILING_NONE


def test_prov09_falsification_du_corps_detectee_par_verify_artifact(tmp_path):
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    artefact = attach_proof({"go_no_go": "NO_GO"}, tool_path=tool)
    falsifie = dict(artefact)
    falsifie["go_no_go"] = "GO"
    ecarts = verify_artifact(falsifie, repo_root=tmp_path)
    assert any("modifié après production" in e for e in ecarts)


def test_prov09_changement_de_version_de_l_outil_detecte(tmp_path):
    tool = tmp_path / "p.py"
    tool.write_text("version = 1\n", encoding="utf-8")
    artefact = attach_proof({"a": 1}, tool_path=tool)
    tool.write_text("version = 2\n", encoding="utf-8")
    ecarts = verify_artifact(artefact, repo_root=tmp_path)
    assert any("autre version du script" in e for e in ecarts)


# ── CHAIN-07..09 : contrôle PREUVE et double plafond ─────────────────────────


def test_chain07_artefact_prouve_passe_le_controle_preuve(tmp_path):
    tool = tmp_path / "producteur.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    body = {
        "verdict": "GO",
        "generated_at": "2999-01-01T00:00:00Z",
        "dataset_provenance": {"n_canonical": 1},
    }
    artefact = attach_proof(body, tool_path=tool, repo_root=tmp_path, artifact="a.json")
    (tmp_path / "a.json").write_text(json.dumps(artefact), encoding="utf-8")
    consumer = tmp_path / "consommateur.py"
    consumer.write_text("pop = d['dataset_provenance']\n", encoding="utf-8")
    report = audit_edge(_edge("a.json", consumer="consommateur.py"), tmp_path)
    assert _status(report, CHECK_PROOF) == STATUS_OK
    assert report.proven is True
    assert report.confidence_ceiling == CEILING_FULL


def test_chain07_artefact_sans_preuve_est_non_prouve_et_plafonne_a_elevee(tmp_path):
    """Tous les autres contrôles passent : seule la preuve manque.

    Le plafond doit alors valoir ELEVEE — ni COMPLETE (rien ne garantit que le
    fichier n'a pas été édité), ni FAIBLE (aucun contrôle n'échoue).
    """
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "verdict": "GO",
                "generated_at": "2999-01-01T00:00:00Z",
                "dataset_provenance": {"n_canonical": 1},
            }
        ),
        encoding="utf-8",
    )
    consumer = tmp_path / "consommateur.py"
    consumer.write_text("pop = d['dataset_provenance']\n", encoding="utf-8")
    report = audit_edge(
        _edge("a.json", consumer="consommateur.py", keys_consumed=()), tmp_path
    )
    assert _status(report, CHECK_PROOF) == STATUS_UNPROVEN
    assert report.broken == []
    assert report.confidence_ceiling == CEILING_HIGH


def test_chain07_artefact_edite_a_la_main_est_rompu(tmp_path):
    tool = tmp_path / "producteur.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    artefact = attach_proof(
        {"verdict": "NO-GO", "generated_at": "2999-01-01T00:00:00Z"}, tool_path=tool
    )
    artefact["verdict"] = "GO"  # édition manuelle après production
    (tmp_path / "a.json").write_text(json.dumps(artefact), encoding="utf-8")
    report = audit_edge(_edge("a.json", keys_consumed=()), tmp_path)
    assert _status(report, CHECK_PROOF) == STATUS_BROKEN
    assert CHECK_PROOF in report.broken


def test_chain08_la_boucle_complete_est_demontree_sur_le_premier_producteur():
    """producteur → proof → persisté → verify_provenance → chain_audit.

    Précédent complet exigé avant généralisation (directive de l'opérateur du
    2026-07-30). Si l'artefact n'a pas été régénéré sur cette machine, le test
    ne conclut pas — il ne prétend pas mesurer ce qui n'existe pas.
    """
    report = build_report()
    chain = next(c for c in report.chains if c.name == "CHAIN-BURNIN-PRELIVE")
    edge = chain.edges[0]
    if not edge.exists:
        return
    assert edge.proven is True, "burnin_v3.json ne porte plus de bloc de preuve"
    assert _status(edge, CHECK_PROOF) == STATUS_OK
    assert edge.broken == []


def test_chain09_les_deux_plafonds_et_l_adoption_sont_publies():
    report = build_report()
    assert set(report.ceilings) == {
        "coverage_ceiling",
        "adoption_ceiling",
        "weakest_link_ceiling",
        "final",
        "binding_reason",
    }
    assert report.adoption["total"] >= 0
    assert report.confidence_ceiling == report.ceilings["final"]


def test_chain09_l_adoption_ne_compte_que_les_artefacts_presents():
    """Un artefact absent n'est pas « non adopté » : il n'y a rien à prouver."""
    report = build_report()
    present = sum(1 for c in report.chains for e in c.edges if e.exists)
    assert report.adoption["total"] == present


# ── PROV-10..14 : non-régression des défauts trouvés par attaque adversariale ─
#
# Chaque test ci-dessous correspond à un défaut DÉMONTRÉ par un agent attaquant
# le 2026-07-30, puis corrigé. Ils sont écrits ici pour que la correction ne
# puisse pas être défaite en silence.


def test_prov10_output_sha256_absent_ne_certifie_plus_le_corps(tmp_path):
    """Défaut CRITIQUE : le corps n'était PAS vérifié et l'artefact passait « ok ».

    `if body is not None and stamp.get("output_sha256")` sautait silencieusement
    le contrôle quand l'empreinte manquait. chain_audit annonçait alors « corps
    inchangé » et un plafond COMPLETE. Une empreinte manquante n'est pas une
    empreinte satisfaite.
    """
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-30T00:00:00Z",
        "tool": "p.py",
        "tool_sha256": sha256_file(tool),
        "tool_path": "p.py",
        "inputs": [],
    }
    ecarts = verify_provenance(stamp, body={"go_no_go": "GO"}, repo_root=tmp_path)
    assert any("output_sha256 absent" in e for e in ecarts)
    assert any("N'EST PAS vérifié" in e for e in ecarts)


def test_prov11_bloc_proof_forge_minimal_est_non_prouve():
    """Défaut MAJEUR : {schema_version, generated_at} obtenait PREUVE=ok.

    L'axe ADOPTION se gagnait donc sans aucune empreinte — exactement l'inverse
    de ce que l'axe est censé mesurer.
    """
    forge = {
        "go_no_go": "GO",
        PROOF_KEY: {"schema_version": 1, "generated_at": "2026-07-30T00:00:00Z"},
    }
    assert artifact_has_proof(forge) is False
    ecarts = verify_artifact(forge)
    assert len(ecarts) == 1
    assert "incomplet" in ecarts[0]
    assert "tool_sha256" in ecarts[0] and "output_sha256" in ecarts[0]


def test_prov11_tous_les_champs_requis_sont_exiges():
    complet = {
        "schema_version": 1,
        "generated_at": "x",
        "tool_sha256": "abc",
        "output_sha256": "def",
    }
    assert artifact_has_proof({PROOF_KEY: complet})
    for champ in REQUIRED_PROOF_FIELDS:
        ampute = {k: v for k, v in complet.items() if k != champ}
        assert artifact_has_proof({PROOF_KEY: ampute}) is False, champ


def test_prov12_substitution_d_artefact_detectee(tmp_path):
    """Deux artefacts cohérents étaient interchangeables sans qu'on le voie."""
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    art = attach_proof(
        {"a": 1}, tool_path=tool, repo_root=tmp_path, artifact="cache/vrai.json"
    )
    assert (
        verify_artifact(art, repo_root=tmp_path, expected_artifact="cache/vrai.json")
        == []
    )
    ecarts = verify_artifact(
        art, repo_root=tmp_path, expected_artifact="cache/autre.json"
    )
    assert any("substitué ou déplacé" in e for e in ecarts)


def test_prov12_preuve_sans_identite_est_signalee(tmp_path):
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    art = attach_proof({"a": 1}, tool_path=tool, repo_root=tmp_path)  # artifact=None
    ecarts = verify_artifact(art, repo_root=tmp_path, expected_artifact="cache/x.json")
    assert any("ne nomme pas l'artefact" in e for e in ecarts)


def test_prov13_chemin_d_entree_relatif_resolu_contre_le_depot(tmp_path):
    """Le verdict ne doit PAS dépendre du répertoire d'invocation."""
    data = tmp_path / "databases"
    data.mkdir()
    entree = data / "e.jsonl"
    entree.write_text('{"a": 1}\n', encoding="utf-8")
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-30T00:00:00Z",
        "tool": "p.py",
        "tool_path": "p.py",
        "tool_sha256": sha256_file(tool),
        "inputs": [{"path": "databases/e.jsonl", "sha256": sha256_file(entree)}],
        "output_sha256": None,
    }
    assert verify_provenance(stamp, repo_root=tmp_path) == []


def test_prov14_outil_introuvable_n_est_pas_une_alteration(tmp_path):
    """Un producteur honnête vivant ailleurs était classé « rompu ».

    Le message doit distinguer « je ne peux pas recalculer » de « l'empreinte
    diffère » : la première n'accuse personne.
    """
    stamp = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": "2026-07-30T00:00:00Z",
        "tool": "vit_ailleurs.py",
        "tool_path": "recherche/vit_ailleurs.py",
        "tool_sha256": "abc123",
        "inputs": [],
        "output_sha256": "def456",
    }
    ecarts = verify_provenance(stamp, repo_root=tmp_path)
    assert any("INTROUVABLE" in e for e in ecarts)
    assert any("n'est PAS la preuve d'une altération" in e for e in ecarts)
    assert not any("autre version du script" in e for e in ecarts)


def test_prov14_tool_path_est_prioritaire_sur_la_recherche_par_nom(tmp_path):
    """Le chemin déclaré évite de hacher un homonyme dans tools/ ou scripts/."""
    ailleurs = tmp_path / "recherche"
    ailleurs.mkdir()
    vrai = ailleurs / "outil.py"
    vrai.write_text("vrai = True\n", encoding="utf-8")
    piege = tmp_path / "scripts"
    piege.mkdir()
    (piege / "outil.py").write_text("homonyme = True\n", encoding="utf-8")
    art = attach_proof({"a": 1}, tool_path=vrai, repo_root=tmp_path)
    assert art[PROOF_KEY]["tool_path"] == "recherche/outil.py"
    assert verify_artifact(art, repo_root=tmp_path) == []


def test_chain10_portee_jsonl_est_declaree(tmp_path):
    """Sur un journal en append, PREUVE ne couvre que la dernière ligne."""
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    art = attach_proof(
        {"verdict": "GO", "generated_at": "2999-01-01T00:00:00Z"},
        tool_path=tool,
        repo_root=tmp_path,
        artifact="a.jsonl",
    )
    (tmp_path / "a.jsonl").write_text(
        '{"vieux": 1}\n' + json.dumps(art) + "\n", encoding="utf-8"
    )
    report = audit_edge(_edge("a.jsonl", keys_consumed=()), tmp_path)
    assert "dernière ligne seulement" in _detail(report, CHECK_PROOF)


def test_prov15_un_denominateur_minuscule_ne_donne_pas_un_plafond_eleve():
    """Défaut MINEUR : « 1/1 = 100 % » annonçait un plafond COMPLETE.

    Un ratio calculé sur un seul élément est bruyant : aucune couverture sous
    MIN_TOTAL_FOR_HIGH_CEILING éléments ne peut valoir mieux que MOYENNE.
    """
    assert Coverage(1, 1).confidence_ceiling == CEILING_MEDIUM
    assert Coverage(4, 4).confidence_ceiling == CEILING_MEDIUM
    assert Coverage(5, 5).confidence_ceiling == CEILING_FULL
    assert MIN_TOTAL_FOR_HIGH_CEILING == 5


def test_prov15_proof_adoption_ignore_les_artefacts_absents(tmp_path):
    """Un artefact absent n'est pas « non adopté » : il n'y a rien à prouver."""
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    prouve = attach_proof({"a": 1}, tool_path=tool, repo_root=tmp_path)
    cov = proof_adoption([prouve, None, None])
    assert cov.total == 1 and cov.measured == 1


# ── PROV-16..18 : VALIDITE du mecanisme et point unique d'instrumentation ─────


def test_prov16_le_mecanisme_passe_son_propre_auto_test():
    """SIXIÈME famille : le mécanisme détecte-t-il ce qu'il prétend détecter ?

    Un mécanisme peut être adopté, exécuté et parfaitement traçable tout en
    étant incapable de rien détecter. C'est ce qui s'est produit le 2026-07-30 :
    l'axe ADOPTION annonçait 1/1 = 100 % sur un `verify_provenance` qui sautait
    silencieusement le contrôle du corps.
    """
    rapport = self_test()
    assert rapport.valid, f"cas en échec : {rapport.failures}"
    assert rapport.cases_passed == rapport.cases_total
    assert rapport.cases_total >= 8


def test_prov16_l_auto_test_contient_des_cas_NEGATIFS():
    """Un auto-test sans cas négatif validerait un mécanisme qui ne détecte rien.

    Vérifié par construction : on casse `verify_provenance` et l'auto-test doit
    tomber. Sinon il ne teste que sa propre complaisance.
    """
    import system.provenance as prov

    originale = prov.verify_provenance
    try:
        prov.verify_provenance = lambda *a, **k: []  # ne détecte plus rien
        rapport = prov.self_test()
        assert not rapport.valid
        assert rapport.failures
    finally:
        prov.verify_provenance = originale
    assert prov.self_test().valid


def test_prov17_le_point_unique_instrumente_toutes_les_preuves(tmp_path):
    """Champs ajoutés dans create_proof et NULLE PART ailleurs.

    Une évolution du format ne devra donc jamais toucher un producteur — c'est
    l'avantage que `load_clean_trades()` avait apporté aux datasets.
    """
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    art = attach_proof({"a": 1}, tool_path=tool, repo_root=tmp_path)
    proof = art[PROOF_KEY]
    for champ in ("proof_id", "min_compatible_version", "tool_path", "artifact"):
        assert champ in proof, champ
    assert proof["min_compatible_version"] == MIN_COMPATIBLE_PROOF_VERSION


def test_prov17_l_identifiant_de_preuve_est_deterministe(tmp_path):
    """Pas un UUID aléatoire : deux exécutions identiques, même identifiant.

    Sinon la reproductibilité serait invérifiable.
    """
    tool = tmp_path / "p.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    kw = dict(tool_path=tool, repo_root=tmp_path, generated_at="2026-07-30T00:00:00Z")
    a = attach_proof({"a": 1}, **kw)
    b = attach_proof({"a": 1}, **kw)
    c = attach_proof({"a": 2}, **kw)
    assert a[PROOF_KEY]["proof_id"] == b[PROOF_KEY]["proof_id"]
    assert a[PROOF_KEY]["proof_id"] != c[PROOF_KEY]["proof_id"]


def test_prov18_la_dependance_est_explicite_dans_l_audit_de_chaine():
    """create_proof -> verify_provenance -> chain_audit -> adoption.

    Si le constructeur unique échoue son auto-test, aucune garantie qui en
    dérive ne doit apparaître verte. Sans cette dépendance modélisée, quatre
    indicateurs indépendants pouvaient toutes reposer sur un mécanisme cassé.
    """
    import system.provenance as prov
    import tools.chain_audit as chain

    originale = prov.verify_provenance
    try:
        prov.verify_provenance = lambda *a, **k: []
        rapport = chain.build_report()
        assert rapport.validity["status"] == VALIDITY_BROKEN
        assert rapport.confidence_ceiling == CEILING_NONE
        statuts = {
            c.status
            for ch in rapport.chains
            for e in ch.edges
            for c in e.checks
            if c.check == CHECK_PROOF
        }
        assert chain.STATUS_MECHANISM_INVALID in statuts
    finally:
        prov.verify_provenance = originale


# ── CHAIN-11 : la DECISION est un artefact de premiere classe ─────────────────


def test_chain11_la_decision_prelive_est_un_artefact_prouve():
    """« Quelle preuve soutenait cette décision ? » devient répondable.

    La chaîne se terminait sur stdout : son verdict disparaissait. Il est
    désormais persisté, prouvé, et sa preuve ÉPINGLE l'empreinte du rapport de
    burn-in qui l'a soutenu.
    """
    report = build_report()
    chaine = next(c for c in report.chains if c.name == "CHAIN-BURNIN-PRELIVE")
    assert chaine.terminal_persisted is True
    decision = [e for e in chaine.edges if "decisions" in e.artifact]
    assert len(decision) == 1
    if not decision[0].exists:
        return
    assert decision[0].proven is True
    assert decision[0].broken == []


def test_chain11_la_preuve_de_la_decision_epingle_ses_entrees():
    """Une décision archivée reste reliée à l'état exact de ses données."""
    chemin = Path("cache/decisions/prelive_gate.json")
    if not chemin.exists():
        return
    artefact = json.loads(chemin.read_text(encoding="utf-8"))
    entrees = {i["path"] for i in artefact[PROOF_KEY]["inputs"]}
    assert any("burnin_v3.json" in e for e in entrees)
    assert artefact[PROOF_KEY]["artifact"] == "cache/decisions/prelive_gate.json"
