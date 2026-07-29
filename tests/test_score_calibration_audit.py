"""
Audit de calibration du score — pouvoir de classement, pas de linéarité.

Contexte : la première lecture du lien score↔PnL était un Pearson r≈0.003 sur
N=109, lu comme « le score n'informe pas ». Or le score est une fonction de
CLASSEMENT : Pearson n'est pas le bon test, et surtout — sur les trades
exécutés — 45 % des observations partagent la valeur 72 et le domaine observé
couvre 13 % de l'échelle. Un r nul y est attendu même si le score classe
parfaitement.

Invariants verrouillés ici :
  SCORE-01  les ex æquo sont moyennés en rang (jamais ordonnés arbitrairement)
  SCORE-02  Spearman détecte une relation monotone non linéaire
  SCORE-03  l'AUC vaut 1 / 0 / 0.5 sur séparation parfaite / inversée / nulle
  SCORE-04  la résolution de l'instrument décroît avec N et est rapportée
  SCORE-05  trichotomie du verdict : SIGNAL / ABSENCE / INSTRUMENT_INSUFFISANT
  SCORE-06  une tranche ne coupe JAMAIS un groupe d'ex æquo
  SCORE-07  l'angle mort de domaine est déclaré même quand un signal est trouvé
  SCORE-08  la population de regret est bornée par la MÊME borne d'époque
  SCORE-09  à graine fixée, les p par permutation sont reproductibles
"""

from __future__ import annotations

import json
import math
import random

import pytest

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE
from tools.score_calibration_audit import (
    VERDICT_ABSENCE,
    VERDICT_INSTRUMENT,
    VERDICT_SIGNAL,
    analyse_population,
    auc_mann_whitney,
    build_tranches,
    describe_support,
    load_observed,
    min_detectable_rho,
    p_value_permutation,
    pearson,
    ranks,
    spearman,
)

_KW = dict(seed=7, permutation_iterations=400, bootstrap_iterations=200, target_bins=4)


# ── SCORE-01 ──────────────────────────────────────────────────────────────────


def test_score01_les_ex_aequo_sont_moyennes():
    assert ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_score01_rangs_insensibles_a_l_ordre_de_lecture():
    """Un rang qui dépend de l'ordre du fichier fabriquerait une corrélation."""
    values = [72, 72, 66, 72, 77]
    outcomes = [1.0, -1.0, 0.5, 2.0, -3.0]
    paired = list(zip(values, outcomes))
    rho_direct = spearman(values, outcomes)
    melange = list(reversed(paired))
    rho_inverse = spearman([p[0] for p in melange], [p[1] for p in melange])
    assert rho_direct == pytest.approx(rho_inverse)


# ── SCORE-02 ──────────────────────────────────────────────────────────────────


def test_score02_spearman_voit_une_monotonie_non_lineaire():
    """Pearson s'effondre sur une exponentielle, Spearman vaut 1 exactement."""
    x = [1, 2, 3, 4, 5, 6, 7, 8]
    y = [math.exp(v) for v in x]
    assert spearman(x, y) == pytest.approx(1.0)
    assert pearson(x, y) < 0.95


def test_score02_spearman_nul_sur_relation_symetrique():
    x = [-3, -2, -1, 1, 2, 3]
    y = [v * v for v in x]
    assert spearman(x, y) == pytest.approx(0.0, abs=1e-12)


# ── SCORE-03 ──────────────────────────────────────────────────────────────────


def test_score03_auc_separation_parfaite():
    scores = [10, 20, 30, 40]
    labels = [False, False, True, True]
    assert auc_mann_whitney(scores, labels) == pytest.approx(1.0)


def test_score03_auc_separation_inversee():
    scores = [10, 20, 30, 40]
    labels = [True, True, False, False]
    assert auc_mann_whitney(scores, labels) == pytest.approx(0.0)


def test_score03_auc_ex_aequo_total_vaut_un_demi():
    """Tout le monde au même score : aucun pouvoir discriminant, par définition."""
    assert auc_mann_whitney([72] * 6, [True, False] * 3) == pytest.approx(0.5)


def test_score03_auc_une_seule_classe_est_indefinie_et_rendue_neutre():
    assert auc_mann_whitney([1, 2, 3], [True, True, True]) == 0.5


# ── SCORE-04 ──────────────────────────────────────────────────────────────────


def test_score04_resolution_decroit_avec_n():
    assert min_detectable_rho(50) > min_detectable_rho(121) > min_detectable_rho(18000)


def test_score04_resolution_a_n121_interdit_les_petits_effets():
    """À N=121 tout |ρ| < ~0.25 est invisible : une absence n'informe pas."""
    assert 0.24 < min_detectable_rho(121) < 0.27


def test_score04_resolution_a_n18000_voit_les_effets_faibles():
    assert min_detectable_rho(18716) < 0.03


# ── SCORE-05 ──────────────────────────────────────────────────────────────────


def test_score05_instrument_insuffisant_sur_domaine_ecrase():
    """N=121, 45 % d'ex æquo, 13 % de l'échelle → aucune conclusion possible."""
    rng = random.Random(1)
    scores = [72.0] * 55 + [float(rng.randint(64, 77)) for _ in range(66)]
    outcomes = [rng.gauss(-0.05, 0.5) for _ in scores]
    res = analyse_population("exécutés", "pnl_usd", scores, outcomes, **_KW)
    assert res.verdict == VERDICT_INSTRUMENT
    assert any("résolution" in r for r in res.verdict_reasons)
    assert any("ex æquo" in r for r in res.verdict_reasons)


def test_score05_absence_de_signal_quand_le_test_a_de_la_puissance():
    """Domaine large, N élevé, aucun lien : là, l'absence est une information."""
    rng = random.Random(2)
    scores = [float(rng.randint(40, 95)) for _ in range(1500)]
    outcomes = [rng.gauss(0.0, 1.0) for _ in scores]
    res = analyse_population("observés", "return_pct", scores, outcomes, **_KW)
    assert res.verdict == VERDICT_ABSENCE
    assert res.min_detectable_rho < 0.2


def test_score05_signal_detecte_quand_le_score_ordonne():
    rng = random.Random(3)
    scores = [float(rng.randint(40, 95)) for _ in range(600)]
    outcomes = [(s - 65) / 30.0 + rng.gauss(0, 0.5) for s in scores]
    res = analyse_population("observés", "return_pct", scores, outcomes, **_KW)
    assert res.verdict == VERDICT_SIGNAL
    assert res.spearman_rho > 0.3
    assert res.auc > 0.6
    assert res.auc_ci_low > 0.5


def test_score05_puissance_testee_avant_significativite():
    """Un p>0.05 sans puissance ne devient JAMAIS une absence de signal.

    C'est l'ordre des tests dans `_verdict` qui est verrouillé ici : inverser
    les deux ferait lire « pas d'effet » là où le test ne pouvait rien voir.
    """
    rng = random.Random(4)
    scores = [float(rng.randint(64, 77)) for _ in range(60)]
    outcomes = [rng.gauss(0, 1) for _ in scores]
    res = analyse_population("exécutés", "pnl_usd", scores, outcomes, **_KW)
    assert res.p_value > 0.05
    assert res.verdict != VERDICT_ABSENCE


# ── SCORE-06 ──────────────────────────────────────────────────────────────────


def test_score06_une_tranche_ne_coupe_jamais_un_groupe_d_ex_aequo():
    """54 trades au score 72 ne peuvent pas être répartis sur deux tranches.

    Les couper fabriquerait un écart inter-tranches à partir du seul ordre de
    lecture — exactement l'artefact que des déciles stricts produiraient ici.
    """
    scores = [66.0] * 10 + [72.0] * 54 + [77.0] * 10
    outcomes = [float(i) for i in range(len(scores))]
    tranches = build_tranches(
        scores, outcomes, target_bins=5, seed=1, bootstrap_iterations=100
    )
    porteuses = [t for t in tranches if t.score_min <= 72.0 <= t.score_max]
    assert len(porteuses) == 1
    assert sum(t.n for t in tranches) == len(scores)


def test_score06_les_tranches_couvrent_toute_la_population():
    rng = random.Random(5)
    scores = [float(rng.randint(60, 90)) for _ in range(400)]
    outcomes = [rng.gauss(0, 1) for _ in scores]
    tranches = build_tranches(
        scores, outcomes, target_bins=5, seed=1, bootstrap_iterations=100
    )
    assert sum(t.n for t in tranches) == len(scores)
    assert tranches == sorted(tranches, key=lambda t: t.score_min)


# ── SCORE-07 ──────────────────────────────────────────────────────────────────


def test_score07_domaine_restreint_est_declare_meme_avec_un_signal():
    """Un signal trouvé ne dispense pas de dire sur quelle bande il a été trouvé."""
    rng = random.Random(6)
    scores = [float(rng.randint(70, 78)) for _ in range(800)]
    outcomes = [(s - 74) / 4.0 + rng.gauss(0, 0.5) for s in scores]
    res = analyse_population("observés", "return_pct", scores, outcomes, **_KW)
    assert res.verdict == VERDICT_SIGNAL
    assert res.support.restricted
    assert "aucune observation sous score 70" in res.support.note


def test_score07_support_mesure_le_mode_et_la_masse_d_ex_aequo():
    support = describe_support([72.0] * 45 + [66.0] * 30 + [77.0] * 25)
    assert support.modal_value == 72.0
    assert support.tie_mass == pytest.approx(0.45)
    assert support.distinct_values == 3
    assert support.support_ratio == pytest.approx(0.11)
    assert support.restricted


# ── SCORE-08 ──────────────────────────────────────────────────────────────────


def _regret_record(ts: float, score: float, ret: float) -> str:
    return json.dumps(
        {
            "observation_id": f"obs-{ts}",
            "ts_signal": ts,
            "symbol": "TEST/USDT",
            "side": "BUY",
            "score": score,
            "regime": "bear_trend",
            "horizons": {"1h": {"horizon": "1h", "return_pct": ret}},
        }
    )


def test_score08_borne_d_epoque_appliquee_a_la_population_de_regret(tmp_path):
    """Même borne que le loader de trades — sinon on recrée AUDIT-EMP-001."""
    apres = CLEAN_DATA_SINCE_ACTIVE.timestamp() + 3600
    avant = CLEAN_DATA_SINCE_ACTIVE.timestamp() - 3600
    f = tmp_path / "regret_horizons_2026-07-20.jsonl"
    f.write_text(
        "\n".join(
            [
                _regret_record(avant, 70.0, 0.01),
                _regret_record(apres, 71.0, 0.02),
                _regret_record(apres, 72.0, -0.01),
            ]
        ),
        encoding="utf-8",
    )
    scores, outcomes, stats = load_observed(tmp_path, "1h")
    assert stats["records_total"] == 3
    assert stats["excluded_hors_epoque"] == 1
    assert stats["kept"] == 2
    assert scores == [71.0, 72.0]
    assert outcomes == [0.02, -0.01]


def test_score08_horizon_absent_est_compte_et_exclu(tmp_path):
    apres = CLEAN_DATA_SINCE_ACTIVE.timestamp() + 3600
    f = tmp_path / "regret_horizons_2026-07-20.jsonl"
    f.write_text(_regret_record(apres, 70.0, 0.01), encoding="utf-8")
    scores, _, stats = load_observed(tmp_path, "24h")
    assert scores == []
    assert stats["excluded_horizon_absent"] == 1


def test_score08_repertoire_absent_ne_leve_pas(tmp_path):
    scores, outcomes, stats = load_observed(tmp_path / "nexiste_pas", "1h")
    assert scores == [] and outcomes == [] and stats["kept"] == 0


# ── SCORE-09 ──────────────────────────────────────────────────────────────────


def test_score09_permutation_reproductible_a_graine_fixee():
    rng = random.Random(8)
    x = [float(rng.randint(64, 77)) for _ in range(80)]
    y = [rng.gauss(0, 1) for _ in x]
    p1 = p_value_permutation(x, y, iterations=500, seed=42)
    p2 = p_value_permutation(x, y, iterations=500, seed=42)
    assert p1 == p2


def test_score09_p_par_permutation_n_est_jamais_nul():
    """Un p de 0 exact n'existe pas avec un nombre fini de tirages."""
    x = list(range(40))
    y = [float(v) for v in x]
    assert p_value_permutation(x, y, iterations=200, seed=1) > 0.0
