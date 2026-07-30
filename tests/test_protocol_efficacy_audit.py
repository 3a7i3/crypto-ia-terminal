"""
Efficacité mesurée du protocole — § 25 du protocole (v4.5, gel).

Le facteur limitant n'est plus la conception du protocole mais son épreuve. Cet
outil additionne, règle par règle, ce qu'elle a réellement détecté et ce qu'elle
a coûté. Une règle élégante qui n'a jamais rien trouvé est un candidat au
retrait, pas une réussite.

Invariants verrouillés ici :
  EFF-01  une règle jamais liée n'est pas classée « non détectrice »
  EFF-02  autant de faux positifs que de détections = COUTEUSE
  EFF-03  une règle déclarée mais absente du registre est SIGNALÉE
  EFF-04  un axe qui ne rend jamais FAIL est marqué NON discriminant
  EFF-05  le registre réel couvre toutes les règles déclarées du manifeste
  EFF-06  le caveat et la limite « faux négatifs » sont publiés, pas implicites
  EFF-07  dimension économique : décisions changées, effort ordinal, gravité
  EFF-08  faux négatifs NON ESTIMÉS — l'espace des méthodes reste ouvert
  EFF-09  cycle de vie : INACTIVE / EPROUVEE / ASSURANCE, justification exigée
  EFF-10  retrait : les TROIS conditions, jamais l'absence de déclenchement seule
  EFF-11  garde-fou anti-optimisation : l'élagage sans détection est signalé
  EFF-12  source de légitimité : observation / analyse de risque / aucune
  EFF-13  élagage : une diminution JUSTIFIÉE n'est pas une alerte
  EFF-14  hiérarchie d'autorité documentaire déclarée, ordonnée, limitée
"""

from __future__ import annotations

from tools.protocol_efficacy_audit import (
    EFFORT_ORDER,
    LEGITIMACY_OBSERVED,
    LEGITIMACY_OF_LIFECYCLE,
    LEGITIMACY_RISK,
    LIFECYCLE_INACTIVE,
    LIFECYCLE_INSURANCE,
    LIFECYCLES,
    REMOVAL_KINDS,
    SEVERITY_ORDER,
    VERDICT_COSTLY,
    VERDICT_NEVER_BOUND,
    VERDICT_NON_DETECTING,
    VERDICT_PRODUCTIVE,
    _verdict,
    build_report,
    main,
    render_text,
)

# ── EFF-01 / EFF-02 ───────────────────────────────────────────────────────────


def test_eff01_jamais_liee_prime_sur_non_detectrice():
    """L'occasion de mordre passe avant le score.

    Classer « non détectrice » une règle qui n'a jamais eu l'occasion de se
    déclencher lui reprocherait un silence dont elle n'est pas responsable.
    """
    assert _verdict(0, 0, True) == VERDICT_NEVER_BOUND
    assert _verdict(0, 0, False) == VERDICT_NON_DETECTING


def test_eff02_autant_de_faux_positifs_que_de_detections_est_couteux():
    assert _verdict(1, 1, False) == VERDICT_COSTLY
    assert _verdict(2, 3, False) == VERDICT_COSTLY
    assert _verdict(3, 1, False) == VERDICT_PRODUCTIVE


def test_eff02_une_detection_sans_faux_positif_est_productive():
    assert _verdict(1, 0, False) == VERDICT_PRODUCTIVE


# ── EFF-03 / EFF-05 ───────────────────────────────────────────────────────────


def test_eff03_une_regle_hors_registre_est_signalee(tmp_path):
    """Sans ce contrôle, un protocole grossit sans qu'on sache ce qui sert."""
    manifeste = tmp_path / "m.yaml"
    manifeste.write_text(
        "invariants:\n"
        "  - id: INV-A\n"
        "  - id: INV-B\n"
        "protocol_efficacy:\n"
        "  measured_at: '2026-07-30'\n"
        "  rules:\n"
        "    - id: INV-A\n"
        "      title: A\n"
        "      detected: 1\n",
        encoding="utf-8",
    )
    report = build_report(manifeste)
    assert report.unregistered_rules == ["INV-B"]
    assert report.confidence_ceiling == "AUCUNE"


def test_eff05_le_registre_reel_couvre_toutes_les_regles_declarees():
    """Si ce test tombe : inscrire la nouvelle règle au registre, pas l'inverse."""
    report = build_report()
    assert (
        report.unregistered_rules == []
    ), "règles sans mesure d'efficacité : " + ", ".join(report.unregistered_rules)


def test_eff05_le_releve_reel_est_inconfortable_et_le_reste():
    """Ancrage au réel : la majorité des règles n'a jamais rien détecté.

    Ce test n'exige pas un bon score — il exige que le mauvais score reste
    VISIBLE. S'il tombe parce que tout est devenu productif, tant mieux :
    vérifier avant de le mettre à jour.
    """
    report = build_report()
    t = report.totals
    assert t["rules"] >= 14
    assert t["detections"] >= 10
    assert t[VERDICT_NEVER_BOUND] >= 1
    assert t[VERDICT_PRODUCTIVE] < t["rules"]


# ── EFF-04 ────────────────────────────────────────────────────────────────────


def test_eff04_un_axe_sans_aucun_fail_n_est_pas_discriminant():
    """Il ne distingue pas un dépôt sain d'un critère qui ne mord pas."""
    report = build_report()
    for axis in report.axes:
        assert axis.discriminant == (axis.failed > 0), axis.id
    assert any(not a.discriminant for a in report.axes)


# ── EFF-06 ────────────────────────────────────────────────────────────────────


def test_eff06_le_caveat_est_publie():
    report = build_report()
    assert "un seul auditeur" in report.caveat
    assert "activite" in report.caveat.lower()


def test_eff06_la_limite_des_faux_negatifs_est_dans_le_rapport():
    """Le trou principal doit être écrit DANS la sortie, pas seulement su."""
    texte = render_text(build_report())
    assert "faux NÉGATIFS" in texte
    assert "ne laisse aucune trace" in texte


def test_eff06_le_cli_repond_et_n_echoue_pas_par_defaut():
    """Observer n'est pas décider : un mauvais score ne bloque personne."""
    assert main(["--json"]) == 0


# ── EFF-07 : dimension économique (INV-ROI-001) ──────────────────────────────


def test_eff07_le_registre_porte_une_dimension_economique():
    """Compter les détections ne suffit pas : deux règles à deux détections ne
    se valent pas si l'une a évité une erreur mineure et l'autre une décision
    contaminant une campagne."""
    report = build_report()
    for rule in report.rules:
        assert rule.effort in EFFORT_ORDER, rule.id
        assert rule.severity_avoided in SEVERITY_ORDER, rule.id
    assert report.totals["decisions_changed"] >= 1
    assert report.totals["rules_changing_a_decision"] >= 1


def test_eff07_aucun_ratio_n_est_calcule():
    """Diviser deux ordinaux ne produit pas un nombre, seulement l'apparence.

    La lecture économique est une PHRASE dont chaque terme renvoie à une
    observation consignée — jamais un score.
    """
    from tools.protocol_efficacy_audit import RuleEfficacy

    for cas, attendu in (
        ((1, "NUL", "MAJEURE", 0), "RENDEMENT ELEVE"),
        ((1, "ELEVE", "MAJEURE", 2), "JUSTIFIEE"),
        ((0, "MOYEN", "CRITIQUE", 2), "COUTEUSE MAIS COUVRANTE"),
        ((0, "MOYEN", "NULLE", 0), "A INSTRUIRE"),
        ((0, "MOYEN", "MINEURE", 2), "TROUVE SANS EFFET"),
        ((0, "FAIBLE", "MINEURE", 0), "COUT FAIBLE"),
    ):
        dec, effort, gravite, detect = cas
        regle = RuleEfficacy(
            id="X",
            title="",
            detected=detect,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
            decisions_changed=dec,
            effort=effort,
            severity_avoided=gravite,
        )
        assert regle.yield_reading.startswith(attendu), (cas, regle.yield_reading)


def test_eff07_une_regle_chere_qui_trouve_sans_effet_est_distinguee():
    """Elle n'est pas « à laisser courir » : elle attend son premier effet."""
    report = build_report()
    lectures = {r.id: r.yield_reading for r in report.rules}
    assert lectures["INV-INIT-001"].startswith("TROUVE SANS EFFET")
    assert lectures["INV-PROOF-001"].startswith("A INSTRUIRE")


def test_eff07_l_effort_est_declare_ordinal_et_sa_base_mesurable():
    """Publier des heures non chronométrées serait inventer un chiffre."""
    report = build_report()
    assert "ORDINALE" in report.effort_caveat
    assert "chronometre" in report.effort_caveat
    assert "MESURABLE" in report.effort_caveat


# ── EFF-08 : faux négatifs — non estimés, pas inobservables ──────────────────


def test_eff08_les_faux_negatifs_sont_dits_NON_ESTIMES():
    """Écrire « inobservables » fermerait l'espace des méthodes.

    Correction du 2026-07-30 : quatre pistes existent, aucune n'est exclue.
    """
    texte = render_text(build_report())
    assert "NON ESTIMÉS" in texte
    assert "pas inobservables" in texte or "non estimés" in texte.lower()
    for methode in ("injections contrôlées", "synthétiques", "indépendants"):
        assert methode in texte, methode


def test_eff08_l_espace_des_methodes_est_declare_ouvert():
    texte = render_text(build_report())
    assert "reste ouvert" in texte


# ── EFF-09 : cycle de vie — valeur historique != valeur optionnelle ──────────


def test_eff09_trois_situations_et_non_deux():
    """Une règle inactive n'est pas forcément inutile : elle peut être un
    garde-fou dont la conséquence d'absence serait grave."""
    report = build_report()
    cycles = {r.lifecycle for r in report.rules}
    assert cycles <= set(LIFECYCLES)
    assert LIFECYCLE_INSURANCE in cycles
    assert report.totals[LIFECYCLE_INSURANCE] >= 1


def test_eff09_une_assurance_sans_justification_n_en_est_pas_une():
    """Sans cette exigence, toute règle inactive se déclarerait « assurance »
    et le registre cesserait de trier quoi que ce soit.

    Depuis EFF-12, la validité exige AUSSI que la source de légitimité
    corresponde au statut — les deux conditions sont cumulatives.
    """
    from tools.protocol_efficacy_audit import RuleEfficacy

    def _regle(cycle, justif="", source=None, base=""):
        return RuleEfficacy(
            id="X",
            title="",
            detected=0,
            false_positives=0,
            prevented=0,
            never_bound=True,
            verdict="",
            lifecycle=cycle,
            assurance_justification=justif,
            legitimacy_source=(
                source if source is not None else LEGITIMACY_OF_LIFECYCLE[cycle]
            ),
            legitimacy_basis=base,
        )

    assert _regle(
        LIFECYCLE_INSURANCE, "conséquence irréversible", base="ADR-0007"
    ).lifecycle_valid
    assert not _regle(LIFECYCLE_INSURANCE, base="ADR-0007").lifecycle_valid
    assert _regle(LIFECYCLE_INACTIVE).lifecycle_valid


def test_eff09_les_assurances_reelles_sont_toutes_justifiees():
    report = build_report()
    for rule in report.rules:
        assert rule.lifecycle_valid, rule.id
    assert report.totals["lifecycle_invalid"] == 0


# ── EFF-10 : retrait — les trois conditions, jamais une seule ────────────────


def test_eff10_aucune_regle_n_est_eligible_au_retrait_aujourd_hui():
    """Les conditions (2) et (3) n'ont pas été éprouvées : aucune injection
    contrôlée n'a été tentée, aucune analyse de risque écrite.

    Le résultat correct est donc ZÉRO éligible — et non « toutes les règles
    jamais liées ». Naître d'une extrapolation n'est pas un argument contre une
    règle : c'est un argument pour l'éprouver.
    """
    report = build_report()
    assert report.totals["retirement_eligible"] == 0
    assert all(not r.retirement_eligible for r in report.rules)


def test_eff10_la_regle_de_retrait_est_publiee():
    report = build_report()
    assert "TROIS conditions" in report.retirement_rule
    assert "extrapolation" in report.retirement_rule
    texte = render_text(report)
    assert "les TROIS conditions, jamais une seule" in texte


# ── EFF-11 : garde-fou anti-optimisation ─────────────────────────────────────


def test_eff11_le_registre_se_declare_descriptif_et_non_cible():
    report = build_report()
    assert "DESCRIPTIF" in report.anti_optimisation
    assert "pas une cible" in report.anti_optimisation or "n'est pas un objectif" in (
        report.anti_optimisation
    )
    assert "GARDE-FOU ANTI-OPTIMISATION" in render_text(report)


def test_eff11_un_elagage_sans_justification_est_signale():
    """Supprimer des règles ferait monter le taux de « productives » sans
    améliorer la qualité des audits — c'est la dérive de Goodhart.

    Depuis EFF-13, le détecteur compare des IDENTITÉS de règles et non des
    comptes : c'est ce qui permet de distinguer un retrait justifié d'un
    élagage. Un comptage seul ne pouvait pas faire cette différence.
    """
    from tools.protocol_efficacy_audit import RuleEfficacy, _pruning_alert

    regles = [
        RuleEfficacy(
            id=f"R{i}",
            title="",
            detected=1,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
        )
        for i in range(3)
    ]
    ledger = {"previous_measurement": {"rule_ids": [f"R{i}" for i in range(10)]}}
    alerte = _pruning_alert(ledger, regles)
    assert "ÉLAGAGE SUSPECT" in alerte
    assert "R9" in alerte


def test_eff11_pas_d_alerte_quand_le_registre_grandit_ou_detecte_plus():
    from tools.protocol_efficacy_audit import RuleEfficacy, _pruning_alert

    regles = [
        RuleEfficacy(
            id=f"R{i}",
            title="",
            detected=3,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
        )
        for i in range(9)
    ]
    assert (
        _pruning_alert({"previous_measurement": {"rules": 10, "detections": 5}}, regles)
        == ""
    )
    assert _pruning_alert({}, regles) == ""


def test_eff11_aucune_alerte_sur_le_releve_reel():
    """Le relevé courant n'a retiré aucune règle."""
    assert build_report().pruning_alert == ""


# ── EFF-12 : source de légitimité — statut de gouvernance, pas statistique ───


def test_eff12_chaque_statut_a_sa_source_de_legitimite():
    """ÉPROUVÉE ← observation ; ASSURANCE ← analyse de risque ; INACTIVE ← rien.

    Confondre les deux formes de justification permettrait à une règle sans
    fondement de se déclarer garde-fou.
    """
    report = build_report()
    for rule in report.rules:
        attendu = LEGITIMACY_OF_LIFECYCLE[rule.lifecycle]
        assert rule.legitimacy_source == attendu, rule.id


def test_eff12_une_assurance_exige_une_base_citable():
    from tools.protocol_efficacy_audit import RuleEfficacy

    def _regle(**kw):
        base = dict(
            id="X",
            title="",
            detected=0,
            false_positives=0,
            prevented=0,
            never_bound=True,
            verdict="",
            lifecycle=LIFECYCLE_INSURANCE,
            legitimacy_source=LEGITIMACY_RISK,
            assurance_justification="conséquence irréversible",
            legitimacy_basis="ADR-0007",
        )
        base.update(kw)
        return RuleEfficacy(**base)

    assert _regle().lifecycle_valid
    assert not _regle(legitimacy_basis="").lifecycle_valid
    assert not _regle(assurance_justification="").lifecycle_valid
    # une « assurance » adossée à une observation est en fait une ÉPROUVÉE
    assert not _regle(legitimacy_source=LEGITIMACY_OBSERVED).lifecycle_valid


def test_eff12_la_limite_qualitative_des_analyses_est_declaree():
    """Les trois analyses nomment une conséquence, elles n'estiment aucune
    probabilité. Suffisant à coût nul, insuffisant pour arbitrer."""
    import yaml

    from tools.protocol_efficacy_audit import MANIFEST

    ledger = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["protocol_efficacy"]
    assert "QUALITATIVES" in ledger["legitimacy_limit"]
    assert "probabilite" in ledger["legitimacy_limit"]


# ── EFF-13 : élagage — diminution SANS justification observée ────────────────


def test_eff13_un_retrait_justifie_n_est_pas_une_alerte():
    """Une diminution est le résultat ATTENDU d'une campagne mature.

    Signaler « diminution = suspect » contredirait le critère de sortie du gel.
    """
    from tools.protocol_efficacy_audit import RuleEfficacy, _pruning_alert

    restantes = [
        RuleEfficacy(
            id="INV-A",
            title="",
            detected=1,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
        )
    ]
    ledger = {
        "previous_measurement": {"rule_ids": ["INV-A", "INV-B"]},
        "removals": [
            {
                "id": "INV-B",
                "kind": "FUSION",
                "evidence": "démonstration d'équivalence avec INV-A, AUDIT-EMP-00X",
            }
        ],
    }
    assert _pruning_alert(ledger, restantes) == ""


def test_eff13_un_retrait_sans_motif_est_signale():
    from tools.protocol_efficacy_audit import RuleEfficacy, _pruning_alert

    restantes = [
        RuleEfficacy(
            id="INV-A",
            title="",
            detected=1,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
        )
    ]
    ledger = {"previous_measurement": {"rule_ids": ["INV-A", "INV-B"]}}
    alerte = _pruning_alert(ledger, restantes)
    assert "ÉLAGAGE SUSPECT" in alerte
    assert "INV-B" in alerte


def test_eff13_un_motif_hors_taxonomie_ou_sans_preuve_est_signale():
    from tools.protocol_efficacy_audit import RuleEfficacy, _pruning_alert

    restantes = [
        RuleEfficacy(
            id="INV-A",
            title="",
            detected=1,
            false_positives=0,
            prevented=0,
            never_bound=False,
            verdict="",
        )
    ]
    base = {"previous_measurement": {"rule_ids": ["INV-A", "INV-B"]}}

    hors_taxo = dict(
        base, removals=[{"id": "INV-B", "kind": "PARCE_QUE", "evidence": "x"}]
    )
    assert "non recevable" in _pruning_alert(hors_taxo, restantes)

    sans_preuve = dict(
        base, removals=[{"id": "INV-B", "kind": "FUSION", "evidence": ""}]
    )
    assert "AUCUNE preuve" in _pruning_alert(sans_preuve, restantes)


def test_eff13_les_quatre_motifs_recevables_sont_declares():
    assert set(REMOVAL_KINDS) == {
        "FUSION",
        "GENERALISATION",
        "INVALIDATION_EXPERIMENTALE",
        "RISQUE_DISPARU",
    }


# ── EFF-14 : hiérarchie d'autorité documentaire ─────────────────────────────


def test_eff14_la_hierarchie_est_declaree_et_ordonnee():
    """L'ordre exact importe moins que le fait qu'il soit explicite."""
    import yaml

    from tools.protocol_efficacy_audit import MANIFEST

    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    hierarchie = data["authority_hierarchy"]
    rangs = [e["rank"] for e in hierarchie["order"]]
    assert rangs == sorted(rangs)
    assert len(set(rangs)) == len(rangs), "deux sources au même rang"
    for entree in hierarchie["order"]:
        assert entree.get("scope") and entree.get("why"), entree["source"]


def test_eff14_le_departage_et_la_limite_sont_ecrits():
    import yaml

    from tools.protocol_efficacy_audit import MANIFEST

    h = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["authority_hierarchy"]
    assert "plus RECENT" in h["tie_break"]
    assert "dette" in h["tie_break"]
    assert "DECLARATIVE" in h["limite"]
    assert "n'est pas instrumentee" in h["limite"]
