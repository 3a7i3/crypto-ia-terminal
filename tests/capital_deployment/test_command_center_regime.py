"""`/regime` — la commande renvoyait `unknown 0%` sur les 135 paires.

Deux défauts distincts, mesurés le 2026-08-05 :

1. **Données.** `_get_regime_for_bot` renvoyait
   `{s: {"regime": _adaptive_regime, "score": 0} for s in symbols}` — le régime
   GLOBAL répété à l'identique sur toutes les paires, et un score codé en dur à
   zéro. Au même instant, `/signals` affichait correctement
   « sideways: 110 | bear_trend: 16 » : la donnée par symbole existait dans
   `results`, la commande lisait simplement la mauvaise source.

2. **Affichage.** 135 lignes identiques, où l'information réelle — « 110 paires
   en sideways » — était noyée.

Ces tests portent sur le formateur. La propriété centrale : **un score inconnu
ne doit jamais s'afficher comme un score nul** — confondre les deux est ce qui
rendait l'ancien affichage trompeur plutôt que simplement verbeux.
"""

from __future__ import annotations

from capital_deployment.command_center_bot import (
    _REGIME_DETAIL_MAX,
    CommandDataProvider,
    _fmt_regime,
)


def _provider(reg):
    return CommandDataProvider(get_regime=lambda: reg)


def _repartition_reelle():
    """Reproduit la répartition mesurée en production."""
    reg = {}
    for i in range(110):
        reg[f"S{i}/USDT"] = {"regime": "sideways", "score": 50 + i % 25}
    for i in range(16):
        reg[f"B{i}/USDT"] = {"regime": "bear_trend", "score": 60 + i}
    for i in range(6):
        reg[f"H{i}/USDT"] = {"regime": "high_volatility_regime", "score": 55 + i}
    for i in range(3):
        reg[f"U{i}/USDT"] = {"regime": "bull_trend", "score": 70 + i}
    return reg


class TestAgregation:
    def test_les_regimes_sont_groupes_avec_leur_compte(self):
        out = _fmt_regime(_provider(_repartition_reelle()))
        assert "sideways" in out and "110" in out
        assert "bear_trend" in out and "16" in out

    def test_le_plus_frequent_apparait_en_premier(self):
        out = _fmt_regime(_provider(_repartition_reelle()))
        assert out.index("sideways") < out.index("bear_trend") < out.index("bull_trend")

    def test_la_sortie_reste_lisible_sur_telephone(self):
        out = _fmt_regime(_provider(_repartition_reelle()))
        assert len(out.splitlines()) < 50, "135 paires ne doivent pas faire 137 lignes"

    def test_le_total_est_annonce(self):
        out = _fmt_regime(_provider(_repartition_reelle()))
        assert "135" in out.splitlines()[0]

    def test_les_paires_excedentaires_sont_comptees_pas_masquees(self):
        out = _fmt_regime(_provider(_repartition_reelle()))
        assert f"+{110 - _REGIME_DETAIL_MAX} autres" in out


class TestScoreInconnuNestPasScoreNul:
    """La propriété qui rendait l'ancien affichage trompeur."""

    def test_score_none_n_affiche_aucun_chiffre(self):
        out = _fmt_regime(_provider({"X/USDT": {"regime": "sideways", "score": None}}))
        ligne = [ln for ln in out.splitlines() if "X/USDT" in ln][0]
        assert ligne.strip() == "X/USDT", "aucun score ne doit être inventé"

    def test_score_zero_reel_est_affiche(self):
        out = _fmt_regime(_provider({"X/USDT": {"regime": "sideways", "score": 0}}))
        ligne = [ln for ln in out.splitlines() if "X/USDT" in ln][0]
        assert "0" in ligne, "un vrai zéro doit rester visible"


class TestRobustesse:
    def test_dictionnaire_vide(self):
        assert _fmt_regime(_provider({})) == "_Regime non disponible_"

    def test_provider_absent(self):
        assert _fmt_regime(CommandDataProvider()) == "_Regime non disponible_"

    def test_valeurs_non_dict_ne_cassent_pas(self):
        out = _fmt_regime(_provider({"X/USDT": "sideways"}))
        assert "sideways" in out

    def test_regime_manquant_devient_unknown(self):
        out = _fmt_regime(_provider({"X/USDT": {"score": 70}}))
        assert "unknown" in out
