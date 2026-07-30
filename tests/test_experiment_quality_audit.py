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
"""

from __future__ import annotations

from system.provenance import CEILING_LOW, CEILING_NONE, weakest_ceiling
from tools.experiment_quality_audit import (
    CRITERIA,
    REGISTRY,
    ROLE_AFFICHAGE,
    ROLE_INSTRUMENT,
    STATUS_FAIL,
    STATUS_INVALID,
    STATUS_NA,
    STATUS_PASS,
    audit_source,
    build_report,
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


def test_qual09_la_propagation_conserve_le_constat_initial():
    """Rétracter n'est pas nier (§ 2 du protocole) : la raison d'origine reste."""
    source = (
        'PATH = "databases/paper_trades.jsonl"\n'
        "rho_min = min_detectable_rho(n)\n"
        'verdict = "GO"\n'
    )
    report = audit_source("faux/i.py", ROLE_INSTRUMENT, "", source)
    raison = _reason(report, "POWER")
    assert raison.startswith("INVALIDE par propagation depuis POPULATION=FAIL")
    assert "constat initial conservé" in raison
    assert "effet minimal détectable" in raison


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
