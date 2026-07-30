"""
Audit de la qualité des expériences — INV-POWER-001 et registre des instruments.

Contexte : les deux incidents les plus coûteux de la campagne (AUDIT-EMP-001 et
-002) n'étaient pas des erreurs d'algorithme mais des erreurs de méthodologie de
mesure. Aucun test unitaire ne pouvait les voir : aucun code n'était faux.

Invariants verrouillés ici :
  QUAL-01  tout fichier accédant au dataset figure au registre avec un rôle
  QUAL-02  seuls les INSTRUMENT sont soumis aux quatre critères
  QUAL-03  un critère qui ne lie pas rend N/A — jamais PASS par défaut
  QUAL-04  POPULATION : lecture directe du journal = FAIL (INV-DATASET-001)
  QUAL-05  POWER : une exigence de VOLUME ne vaut pas une puissance
  QUAL-06  TRANSFORMATION : artefact sans date ni population = FAIL
  QUAL-07  INDEPENDENCE : dispersion sans unité d'échantillonnage = FAIL
  QUAL-08  l'outil s'applique à lui-même et passe les quatre critères
  QUAL-09  PROPAGATION : POPULATION=FAIL invalide l'aval, sans effacer le constat
  QUAL-10  COUVERTURE : le plafond de confiance est mécanique, pas une remarque
  QUAL-11  imprimer du JSON n'est PAS écrire un artefact (faux positif corrigé)
  QUAL-12  ADOPTION : cinquième axe, indépendant, avec constructeur unique
  QUAL-13  deux plafonds distincts (couverture vs maillon faible) + raison
  QUAL-14  non-regression du second lot d'attaques : mention != appel,
           fabrication manuelle prioritaire, propagation idempotente,
           statut d'origine lisible, plafond monotone, absent != propre
  QUAL-15  INV-LEXICAL-001 : un USAGE se prouve par AST, jamais par motif
  QUAL-16  VALIDITE : un mecanisme casse invalide l'axe ADOPTION
"""

from __future__ import annotations

from system.provenance import CEILING_LOW, CEILING_NONE, weakest_ceiling
from tools.experiment_quality_audit import (
    AXIS_OF_CRITERION,
    CRITERIA,
    REGISTRY,
    ROLE_AFFICHAGE,
    ROLE_INSTRUMENT,
    STATUS_FAIL,
    STATUS_INVALID,
    STATUS_NA,
    STATUS_PASS,
    InstrumentReport,
    _propagate,
    audit_source,
    build_report,
    calls_function,
    find_undeclared_readers,
    main,
)


def _status(report, criterion: str) -> str:
    return next(c.status for c in report.checks if c.criterion == criterion)


def _reason(report, criterion: str) -> str:
    return next(c.binds_because for c in report.checks if c.criterion == criterion)


# ── QUAL-01 ───────────────────────────────────────────────────────────────────


def test_qual01_aucun_lecteur_du_dataset_hors_registre():
    """Un accès au dataset non classé = registre silencieusement obsolète.

    Si ce test échoue, ce n'est pas lui qu'il faut corriger : c'est le nouveau
    fichier qu'il faut déclarer au registre, ne serait-ce que comme AFFICHAGE.
    """
    undeclared = find_undeclared_readers()
    assert (
        undeclared == []
    ), "fichiers lisant le dataset sans rôle déclaré : " + ", ".join(undeclared)


def test_qual01_tout_le_registre_existe_sur_le_disque():
    report = build_report()
    assert report.missing_from_disk == []


# ── QUAL-02 / QUAL-03 ─────────────────────────────────────────────────────────


def test_qual02_un_non_instrument_n_est_pas_audite():
    """Un module d'affichage ne conclut pas : le soumettre serait du bruit."""
    source = "load_clean_trades()\nprint('sharpe', 1.0)\njson.dump(x, f)\n"
    report = audit_source("faux/affichage.py", ROLE_AFFICHAGE, "", source)
    assert report.checks == []


def test_qual03_criteres_non_liants_rendent_na():
    """Aucune conclusion, aucun artefact, aucune dispersion : trois N/A."""
    source = "def helper(x):\n    return x + 1\n"
    report = audit_source("faux/instrument.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POWER") == STATUS_NA
    assert _status(report, "TRANSFORMATION") == STATUS_NA
    assert _status(report, "INDEPENDENCE") == STATUS_NA
    assert _status(report, "POPULATION") == STATUS_NA


def test_qual03_les_quatre_criteres_sont_toujours_rendus():
    source = "verdict = 'NO_GO'\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert [c.criterion for c in report.checks] == CRITERIA


# ── QUAL-04 ───────────────────────────────────────────────────────────────────


def test_qual04_lecture_directe_du_journal_echoue():
    source = 'PATH = "databases/paper_trades.jsonl"\nverdict = "NO_GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POPULATION") == STATUS_FAIL
    assert "INV-DATASET-001" in _reason(report, "POPULATION")


def test_qual04_loader_canonique_passe():
    source = (
        "from tools.cri_calculator import load_clean_trades\nt = load_clean_trades()\n"
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POPULATION") == STATUS_PASS


def test_qual04_la_preuve_est_citable():
    """Une défaillance sans numéro de ligne n'est pas opposable."""
    source = 'x = 1\nPATH = "databases/paper_trades.jsonl"\nverdict = "FAIL"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    evidence = next(c.evidence for c in report.checks if c.criterion == "POPULATION")
    assert evidence and evidence[0].startswith("2: ")


# ── QUAL-05 : le cœur de INV-POWER-001 ────────────────────────────────────────


def test_qual05_conclusion_sans_puissance_echoue():
    source = 'if pf < 1.5:\n    verdict = "NO_GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POWER") == STATUS_FAIL
    assert "INV-POWER-001" in _reason(report, "POWER")


def test_qual05_exigence_de_volume_ne_vaut_pas_puissance():
    """N >= 500 ne dit rien de la taille d'effet visible. C'est LA confusion.

    Constatée sur tools/cri_calculator.py : le CRI publie quatre exigences de
    volume (N_TARGET, MIN_CELL_OBSERVATIONS, MIN_PSI_SAMPLE, balance) et aucun
    effet minimal détectable. Un CRI de 90 ne garantit donc pas qu'un effet
    donné serait visible.
    """
    source = 'N_TARGET = 500\nif n < N_TARGET:\n    verdict = "NO_GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POWER") == STATUS_FAIL
    assert "VOLUME" in _reason(report, "POWER")
    assert "n'est pas une puissance" in _reason(report, "POWER")


def test_qual05_effet_minimal_detectable_passe():
    source = 'rho_min = min_detectable_rho(n)\nverdict = "NO_GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POWER") == STATUS_PASS


def test_qual05_sans_conclusion_la_puissance_ne_lie_pas():
    """Un outil qui ne conclut rien n'a pas à publier de puissance."""
    source = "def mean(v):\n    return sum(v) / len(v)\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POWER") == STATUS_NA


# ── QUAL-06 ───────────────────────────────────────────────────────────────────


def test_qual06_artefact_sans_date_ni_population_echoue():
    source = 'verdict = "GO"\njson.dump({"pf": 1.2}, f)\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "TRANSFORMATION") == STATUS_FAIL
    assert "gate D" in _reason(report, "TRANSFORMATION")


def test_qual06_artefact_horodate_passe():
    source = 'json.dump({"generated_at": now, "n_canonical": n}, f)\nverdict = "GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "TRANSFORMATION") == STATUS_PASS


# ── QUAL-07 ───────────────────────────────────────────────────────────────────


def test_qual07_dispersion_sans_unite_declaree_echoue():
    source = "sharpe = mean_r / stdev(returns)\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "INDEPENDENCE") == STATUS_FAIL


def test_qual07_unite_declaree_passe():
    source = "# Sharpe par trade — unité d'échantillonnage : le trade\nsharpe = m / s\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "INDEPENDENCE") == STATUS_PASS


def test_qual07_stdout_n_est_pas_une_dispersion():
    """`stdout` ne doit pas déclencher le critère — frontière de mot testée."""
    source = "sys.stdout.write('ok')\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "INDEPENDENCE") == STATUS_NA


# ── QUAL-08 ───────────────────────────────────────────────────────────────────


def test_qual08_l_outil_se_soumet_a_ses_propres_criteres():
    """Un auditeur exempté de son propre audit n'est pas un auditeur."""
    report = build_report()
    self_report = next(
        i for i in report.instruments if i.path == "tools/experiment_quality_audit.py"
    )
    assert self_report.role == ROLE_INSTRUMENT
    assert self_report.failures == []


def test_qual08_le_registre_declare_au_moins_un_moteur_et_un_producteur():
    """La frontière observation / décision (ADR-0007) reste écrite quelque part."""
    roles = {role for role, _ in REGISTRY.values()}
    assert "MOTEUR" in roles
    assert "PRODUCTEUR" in roles


def test_qual08_le_json_est_serialisable_et_le_cli_repond():
    assert main(["--json"]) == 0


# ── QUAL-09 : propagation du maillon faible ENTRE critères ────────────────────


def test_qual09_population_fail_invalide_l_aval():
    """Une puissance calculée sur une population contaminée est SANS OBJET.

    Ni réussie, ni ratée : `POPULATION: FAIL` + `POWER: ok` laisserait croire que
    le test de puissance renseigne sur quelque chose.
    """
    source = (
        'PATH = "databases/paper_trades.jsonl"\n'
        "rho_min = min_detectable_rho(n)\n"
        'verdict = "NO_GO"\n'
        "sharpe = m / stdev(r)  # unité d'échantillonnage : le trade\n"
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POPULATION") == STATUS_FAIL
    assert _status(report, "POWER") == STATUS_INVALID
    assert _status(report, "INDEPENDENCE") == STATUS_INVALID
    assert report.invalidated == ["POWER", "INDEPENDENCE"]


def test_qual09_la_propagation_est_une_arete_de_graphe_pas_un_message():
    """`invalidated_by` porte l'ID de l'axe — traçable, pas du texte libre.

    Rétracter n'est pas nier (§ 2 du protocole) : la raison d'origine survit
    dans `original_reason` et redeviendrait exploitable si l'amont était corrigé.
    """
    source = (
        'PATH = "databases/paper_trades.jsonl"\n'
        "rho_min = min_detectable_rho(n)\n"
        'verdict = "GO"\n'
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    check = next(c for c in report.checks if c.criterion == "POWER")
    assert check.status == STATUS_INVALID
    assert check.invalidated_by == "AUDIT-POPULATION-001"
    assert check.original_reason is not None
    assert "effet minimal détectable" in check.original_reason


def test_qual09_un_critere_evalue_sur_ses_merites_n_a_pas_d_arete():
    source = 'verdict = "NO_GO"\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    for check in report.checks:
        assert check.invalidated_by is None
        assert check.original_reason is None


def test_qual09_chaque_critere_porte_un_axe_de_campagne():
    """Sans identifiant d'axe, une propagation n'est pas reconstituable."""
    assert set(AXIS_OF_CRITERION) == set(CRITERIA)
    assert all(v.startswith("AUDIT-") for v in AXIS_OF_CRITERION.values())


def test_qual09_un_critere_non_liant_n_est_jamais_invalide():
    """N/A veut dire « la question ne se pose pas » — la propagation n'y change rien."""
    source = 'PATH = "databases/paper_trades.jsonl"\nx = 1\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POPULATION") == STATUS_FAIL
    assert _status(report, "POWER") == STATUS_NA
    assert report.invalidated == []


def test_qual09_le_plafond_distingue_invalidation_et_echec():
    invalide = audit_source(
        "faux/a.py",
        ROLE_INSTRUMENT,
        "",
        'PATH = "databases/paper_trades.jsonl"\n'
        'verdict = "GO"\n'
        "rho = min_detectable_rho(n)\n",
    )
    echec = audit_source("faux/b.py", ROLE_INSTRUMENT, "", 'verdict = "GO"\n')
    assert invalide.confidence_ceiling == CEILING_NONE
    assert echec.confidence_ceiling == CEILING_LOW


# ── QUAL-10 : couverture normative ────────────────────────────────────────────


def test_qual10_la_couverture_est_un_objet_pas_une_remarque():
    report = build_report()
    cov = report.coverage
    assert cov["total"] == report.n_instruments
    assert 0 <= cov["ratio"] <= 1
    assert (
        cov["measured"]
        + len(
            [
                i
                for i in report.instruments
                if i.role == ROLE_INSTRUMENT and (i.failures or i.invalidated)
            ]
        )
        == cov["total"]
    )


def test_qual10_le_plafond_du_rapport_est_le_maillon_faible():
    report = build_report()
    attendu = weakest_ceiling(
        [report.coverage["confidence_ceiling"]]
        + [
            i.confidence_ceiling
            for i in report.instruments
            if i.role == ROLE_INSTRUMENT
        ]
    )
    assert report.confidence_ceiling == attendu


# ── QUAL-11 : précision du critère TRANSFORMATION ─────────────────────────────


def test_qual11_imprimer_du_json_n_est_pas_ecrire_un_artefact():
    """FAUX POSITIF CORRIGÉ : `json.dumps` dans un print ne persiste rien.

    Trois instruments sur quatre signalés en TRANSFORMATION n'écrivaient aucun
    fichier — ils imprimaient sur la sortie standard. La famille « à traiter en
    priorité » était surévaluée de 300 %.
    """
    source = "print(json.dumps(result, indent=1))\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "TRANSFORMATION") == STATUS_NA


def test_qual11_ecrire_un_fichier_est_un_artefact():
    for source in (
        'json.dump(payload, open("cache/r.json", "w"))\n',
        'Path("cache/r.json").write_text(txt)\n',
        'with open("databases/x.jsonl", "a") as f:\n    f.write(line)\n',
    ):
        report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
        assert _status(report, "TRANSFORMATION") in {STATUS_FAIL, STATUS_PASS}


# ── QUAL-12 : ADOPTION, cinquième axe ─────────────────────────────────────────


def test_qual12_producteur_passant_par_l_api_de_preuve():
    source = 'payload = attach_proof(body, tool_path=p)\nPath("c.json").write_text(x)\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_PASS


def test_qual12_bloc_proof_fabrique_a_la_main_echoue():
    """C'est exactement la dérive constatée 2 fois : 3 loaders, 4 Sharpe.

    Un second constructeur de la même structure dérive toujours — la seule
    protection est qu'il n'en existe qu'un, et que tout contournement se voie.
    """
    source = 'body["proof"] = {"schema_version": 1}\nPath("c.json").write_text(x)\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_FAIL
    assert "SANS passer par attach_proof" in _reason(report, "ADOPTION")


def test_qual12_artefact_sans_preuve_echoue():
    source = 'json.dump({"generated_at": now}, f)\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_FAIL


def test_qual12_sans_artefact_l_adoption_ne_lie_pas():
    source = "print(json.dumps(result))\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_NA


def test_qual12_adoption_n_est_pas_invalidee_par_population():
    """Cinquième axe INDÉPENDANT : la question reste sensée population invalide.

    « Ce producteur passe-t-il par l'API de preuve ? » ne dépend pas de la
    justesse de sa population — contrairement à sa puissance ou à son
    indépendance, qui perdent leur référent.
    """
    source = (
        'PATH = "databases/paper_trades.jsonl"\n'
        'json.dump({"generated_at": now}, f)\n'
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "POPULATION") == STATUS_FAIL
    assert _status(report, "TRANSFORMATION") == STATUS_INVALID
    assert _status(report, "ADOPTION") == STATUS_FAIL  # pas INVALIDE


def test_qual12_burnin_est_le_premier_producteur_adopte():
    """Précédent complet exigé avant généralisation (directive de l'opérateur).

    Si ce test tombe, c'est que le premier producteur a cessé de passer par
    l'API — vérifier avant de neutraliser.
    """
    report = build_report()
    burnin = next(
        i for i in report.instruments if i.path == "scripts/burnin_calibration_v3.py"
    )
    adoption = next(c for c in burnin.checks if c.criterion == "ADOPTION")
    assert adoption.status == STATUS_PASS


# ── QUAL-13 : les deux plafonds ───────────────────────────────────────────────


def test_qual13_deux_plafonds_distincts_sont_rendus():
    """Couverture et maillon faible n'appellent pas la même action."""
    report = build_report()
    assert set(report.ceilings) == {
        "coverage_ceiling",
        "adoption_ceiling",
        "weakest_link_ceiling",
        "final",
        "binding_reason",
    }
    assert report.confidence_ceiling == report.ceilings["final"]


def test_qual13_le_plafond_final_est_le_plus_contraignant_des_deux():
    report = build_report()
    assert report.ceilings["final"] == weakest_ceiling(
        [
            report.ceilings["coverage_ceiling"],
            report.ceilings["adoption_ceiling"],
            report.ceilings["weakest_link_ceiling"],
        ]
    )


def test_qual13_la_raison_dit_quelle_action_mener():
    report = build_report()
    raison = report.ceilings["binding_reason"]
    assert ("MAILLON FAIBLE" in raison) or ("COUVERTURE" in raison)


def test_qual13_l_adoption_a_son_propre_denominateur():
    """Dénominateur = producteurs pour qui la question se pose, pas le registre."""
    report = build_report()
    assert report.adoption["total"] <= report.n_instruments
    assert report.adoption["measured"] <= report.adoption["total"]


# ── QUAL-14 : non-régression du second lot d'attaques adversariales ───────────


def test_qual14_une_mention_de_l_api_ne_vaut_pas_un_appel():
    """Défaut MAJEUR : une docstring — voire une NÉGATION — donnait ADOPTION=PASS.

    Troisième instance de la famille MENTION-vs-USAGE sur cet outil. La
    parenthèse ouvrante est désormais exigée.
    """
    for source in (
        '"""Ce module n\'utilise PAS attach_proof."""\nPath("c.json").write_text(x)\n',
        '# TODO: passer par attach_proof un jour\nPath("c.json").write_text(x)\n',
    ):
        report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
        assert _status(report, "ADOPTION") == STATUS_FAIL, source


def test_qual14_fabriquer_a_la_main_gagne_sur_la_mention_de_l_api():
    """Défaut MAJEUR : la branche FAIL était masquée par tout appel à l'API.

    Un fichier qui appelle l'API ET fabrique un bloc à la main fabrique quand
    même à la main — c'est exactement la dérive que le critère cherche.
    """
    source = (
        "payload = attach_proof(body, tool_path=p)\n"
        'payload["proof"] = {"schema_version": 1}\n'
        'Path("c.json").write_text(x)\n'
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_FAIL
    assert "SANS passer par" in _reason(report, "ADOPTION")


def test_qual14_le_mot_provenance_seul_n_achete_plus_le_tampon():
    """Défaut MINEUR : importer l'API de preuve validait TRANSFORMATION."""
    source = "from system.provenance import sha256_file\njson.dump(d, f)\n"
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "TRANSFORMATION") == STATUS_FAIL


def test_qual14_propagation_idempotente():
    """Défaut MINEUR : le second appel DÉTRUISAIT original_reason."""
    source = (
        'PATH = "databases/paper_trades.jsonl"\n'
        "rho = min_detectable_rho(n)\n"
        'verdict = "GO"\n'
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    check = next(c for c in report.checks if c.criterion == "POWER")
    premier = (check.status, check.original_status, check.original_reason)
    _propagate(report)
    assert (check.status, check.original_status, check.original_reason) == premier
    assert "effet minimal détectable" in check.original_reason


def test_qual14_le_statut_d_origine_reste_lisible():
    """Un vrai PASS et un vrai FAIL doivent rester distinguables après invalidation."""
    passant = audit_source(
        "faux/a.py",
        ROLE_INSTRUMENT,
        "",
        'PATH = "databases/paper_trades.jsonl"\n'
        "rho = min_detectable_rho(n)\n"
        'verdict = "GO"\n',
    )
    echouant = audit_source(
        "faux/b.py",
        ROLE_INSTRUMENT,
        "",
        'PATH = "databases/paper_trades.jsonl"\n'
        'verdict = "GO"\n'
        "sharpe = m / stdev(r)\n",
    )
    a = next(c for c in passant.checks if c.criterion == "POWER")
    b = next(c for c in echouant.checks if c.criterion == "POWER")
    assert a.status == b.status == STATUS_INVALID
    assert a.original_status == STATUS_PASS
    assert b.original_status == STATUS_FAIL


def test_qual14_plafond_monotone_sur_population_fail():
    """Défaut MINEUR : déclarer MOINS donnait un MEILLEUR plafond.

    Deux instruments, même défaut racine (POPULATION=FAIL) : celui qui ne
    déclarait aucun critère aval obtenait FAIBLE, l'autre AUCUNE.
    """
    bavard = audit_source(
        "faux/a.py",
        ROLE_INSTRUMENT,
        "",
        'PATH = "databases/paper_trades.jsonl"\n'
        'verdict = "GO"\n'
        "rho = min_detectable_rho(n)\n",
    )
    muet = audit_source(
        "faux/b.py", ROLE_INSTRUMENT, "", 'PATH = "databases/paper_trades.jsonl"\n'
    )
    assert bavard.confidence_ceiling == muet.confidence_ceiling == CEILING_NONE


def test_qual14_un_instrument_absent_ne_compte_pas_comme_propre():
    """Défaut MINEUR : supprimer un fichier améliorait le score de couverture."""
    absent = InstrumentReport(
        path="faux/disparu.py", role=ROLE_INSTRUMENT, note="", exists=False, lines=0
    )
    assert absent.failures == []
    assert absent.confidence_ceiling == CEILING_NONE


# ── QUAL-15 : INV-LEXICAL-001 — usage ≠ mention ──────────────────────────────


def test_qual15_l_usage_est_detecte_par_analyse_syntaxique():
    """Trois occurrences de la même faute ont suffi : on change d'instrument.

    `json.dump` vs `json.dumps`, nom de fichier vs ouverture réelle,
    `attach_proof` mentionné vs appelé. Un arbre syntaxique distingue un appel
    d'un mot ; une expression régulière, jamais.
    """
    assert calls_function("x = attach_proof(a, b)\n", ["attach_proof"])
    assert calls_function("m = mod.create_proof(a)\n", ["create_proof"])
    assert not calls_function('"""ne pas utiliser attach_proof"""\n', ["attach_proof"])
    assert not calls_function("# attach_proof un jour\n", ["attach_proof"])
    assert not calls_function("nom = 'attach_proof'\n", ["attach_proof"])


def test_qual15_le_repli_textuel_se_declare(tmp_path):
    """Un fichier non analysable retombe sur le texte — et le DIT."""
    trouves = calls_function("def (:\n attach_proof\n", ["attach_proof"])
    assert trouves
    assert "repli textuel" in trouves[0]


def test_qual15_adoption_utilise_l_ast_pas_le_motif():
    source = '"""Ce module n\'appelle pas attach_proof."""\njson.dump(d, f)\n'
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    assert _status(report, "ADOPTION") == STATUS_FAIL


# ── QUAL-16 : VALIDITE, sixième famille ──────────────────────────────────────


def test_qual16_le_rapport_publie_la_validite_du_mecanisme():
    report = build_report()
    assert set(report.validity) >= {"status", "cases_total", "cases_passed", "failures"}


def test_qual16_un_mecanisme_casse_invalide_l_axe_adoption():
    """Mesurer la diffusion d'un outil cassé produit une fausse assurance.

    Pire qu'une adoption nulle : c'est une adoption qui rassure à tort.
    """
    import system.provenance as prov
    import tools.experiment_quality_audit as Q

    originale = prov.verify_provenance
    try:
        prov.verify_provenance = lambda *a, **k: []
        report = Q.build_report()
        assert report.validity["status"] != "VALIDE"
        adoptions = [
            c
            for i in report.instruments
            for c in i.checks
            if c.criterion == "ADOPTION" and c.status == STATUS_INVALID
        ]
        assert adoptions
        assert all(c.invalidated_by == Q.AXIS_VALIDITY for c in adoptions)
        assert report.confidence_ceiling == CEILING_NONE
    finally:
        prov.verify_provenance = originale


def test_qual16_prelive_est_le_second_producteur_adopte():
    """Le précédent complet établi, l'extension au producteur suivant est faite."""
    report = build_report()
    prelive = next(i for i in report.instruments if i.path == "scripts/prelive_gate.py")
    adoption = next(c for c in prelive.checks if c.criterion == "ADOPTION")
    assert adoption.status == STATUS_PASS
