"""
INIT-ORDER — la configuration précède-t-elle les imports ?

Catégorie de défaut distincte du dataset (INV-DATASET-001) et des KPI
(INV-METRIC-001) : une constante écrite à la racine d'un module est évaluée à
l'import. Si l'import précède `load_dotenv()`, elle garde son défaut codé en dur
pour toute la vie du process, sans erreur ni trace.

Instance constatée le 2026-07-29 : `infra/wallet_sync.py:48`,
`_PAPER_CAPITAL = float(os.getenv("WALLET_PAPER_CAPITAL", "100"))` alors que
`.env` porte 1000 — drawdown 0.95 % ou 9.42 % selon l'ordre, face à un seuil de
gate à 10 %.

Invariants verrouillés ici :
  INIT-01  seules les lectures au NIVEAU MODULE sont inventoriées
  INIT-02  la criticité est classée, pas devinée au cas par cas
  INIT-03  l'instance historique reste détectée (test d'ancrage au réel)
  INIT-04  le différentiel PROUVE la dépendance à l'ordre, il ne la suppose pas
  INIT-05  égalité sans variable définie = NON_CONTRAINT, jamais STABLE
  INIT-06  l'outil observe et ne corrige rien (ADR-0007) ; --strict seul échoue
"""

from __future__ import annotations

from tools.init_order_audit import (
    RUNTIME_REGISTRY,
    VERDICT_ORDER_DEPENDENT,
    VERDICT_STABLE,
    VERDICT_UNCONSTRAINED,
    build_report,
    check_runtime,
    main,
    scan_module_level_env,
)


def _write(tmp_path, name: str, content: str):
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


# ── INIT-01 ───────────────────────────────────────────────────────────────────


def test_init01_lecture_dans_une_fonction_n_est_pas_concernee(tmp_path):
    """Lue à l'appel, pas à l'import : ce motif est justement le correctif."""
    _write(
        tmp_path,
        "paresseux.py",
        "import os\n\n\ndef capital():\n    return float(os.getenv('CAP', '100'))\n",
    )
    assert scan_module_level_env(tmp_path) == []


def test_init01_constante_de_module_est_detectee(tmp_path):
    _write(tmp_path, "figee.py", "import os\nCAP = float(os.getenv('CAP', '100'))\n")
    found = scan_module_level_env(tmp_path)
    assert len(found) == 1
    assert found[0].line == 2
    assert "CAP" in found[0].source


def test_init01_les_tests_et_archives_sont_exclus(tmp_path):
    _write(tmp_path, "tests/test_x.py", "import os\nA = os.getenv('A', '1')\n")
    _write(tmp_path, "_ARCHIVE_2026/vieux.py", "import os\nB = os.getenv('B', '1')\n")
    assert scan_module_level_env(tmp_path) == []


def test_init01_un_fichier_illisible_ne_fait_pas_tomber_l_inventaire(tmp_path):
    _write(tmp_path, "casse.py", "def (:\n")
    _write(tmp_path, "ok.py", "import os\nA = os.getenv('A', '1')\n")
    found = scan_module_level_env(tmp_path)
    assert [f.path for f in found] == ["ok.py"]


# ── INIT-02 ───────────────────────────────────────────────────────────────────


def test_init02_criticite_classee_par_categorie(tmp_path):
    _write(
        tmp_path,
        "m.py",
        "import os\n"
        "_PAPER_CAPITAL = float(os.getenv('WALLET_PAPER_CAPITAL', '100'))\n"
        "_MAX_EXPOSURE = float(os.getenv('EM_MAX_NORMAL', '0.2'))\n"
        "_MAX_ORDER = float(os.getenv('MAX_ORDER_USD', '50'))\n"
        "_VERBOSE = os.getenv('VERBOSE', 'false')\n",
    )
    labels = {c.criticality for c in scan_module_level_env(tmp_path)}
    assert {"CAPITAL", "RISQUE", "EXECUTION", "AUTRE"} <= labels


# ── INIT-03 : ancrage au réel ─────────────────────────────────────────────────


def test_init03_l_instance_historique_reste_detectee():
    """Si ce test tombe, wallet_sync a changé : le vérifier, pas le supprimer."""
    found = scan_module_level_env()
    capital = [
        c
        for c in found
        if c.path == "infra/wallet_sync.py" and "WALLET_PAPER_CAPITAL" in c.source
    ]
    assert len(capital) == 1
    assert capital[0].criticality == "CAPITAL"


def test_init03_l_inventaire_reel_est_massif_pas_anecdotique():
    """La règle de formation du protocole exige une PROPRIÉTÉ, pas un accident.

    Une occurrence est un accident, deux sont une propriété du processus. Ici
    l'inventaire en compte plus de cent : l'invariant n'est pas de la
    superstition écrite après un incident unique.
    """
    report = build_report(with_runtime=False)
    assert report.total_module_level_env_reads > 100
    assert report.files_concerned > 20
    assert len(report.critical_constants) >= 10


# ── INIT-04 / INIT-05 ─────────────────────────────────────────────────────────


def test_init04_le_differentiel_prouve_la_dependance_sur_wallet_sync():
    """Deux sous-processus, deux ordres, deux valeurs : c'est une mesure."""
    checks = check_runtime(
        [("infra.wallet_sync", "_PAPER_CAPITAL", "WALLET_PAPER_CAPITAL")]
    )
    assert len(checks) == 1
    check = checks[0]
    assert check.verdict == VERDICT_ORDER_DEPENDENT
    assert check.value_without_dotenv != check.value_with_dotenv


def test_init05_variable_absente_donne_non_contraint():
    """Égalité par absence de configuration : ne prouve RIEN sur le motif."""
    checks = check_runtime(
        [("runtime.system_state_bus", "_MAX_QUEUE_SIZE", "P10_BUS_MAX_QUEUE_ABSENTE")]
    )
    assert checks[0].verdict == VERDICT_UNCONSTRAINED
    assert checks[0].defined_in_env is False


def test_init05_stable_exige_une_variable_reellement_definie():
    verdicts = {c.env_var: c for c in check_runtime(RUNTIME_REGISTRY)}
    for check in verdicts.values():
        if check.verdict == VERDICT_STABLE:
            assert check.defined_in_env is True


def test_init04_module_inexistant_est_non_mesurable():
    checks = check_runtime([("module.qui.nexiste.pas", "_X", "X_VAR")])
    assert checks[0].verdict == "NON_MESURABLE"


# ── INIT-06 ───────────────────────────────────────────────────────────────────


def test_init06_par_defaut_l_outil_observe_sans_echouer():
    """Observer n'est pas décider (ADR-0007) : le défaut ne bloque personne."""
    assert main(["--no-runtime", "--json"]) == 0


def test_init06_strict_echoue_quand_une_constante_est_prouvee_dependante():
    assert main(["--strict"]) == 1
