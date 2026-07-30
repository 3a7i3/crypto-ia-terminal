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
"""

from __future__ import annotations

from tools.protocol_efficacy_audit import (
    EFFORT_ORDER,
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
