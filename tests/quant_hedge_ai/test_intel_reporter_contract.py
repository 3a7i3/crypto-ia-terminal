"""Briefing @rapport_automatique_bot — contrat § 2.

« Est-ce que la machine fonctionne correctement, et où en est la preuve
scientifique ? » — jamais « que fait le marché ».

Le briefing contenait une narration de marché (régimes groupés + noms de paires)
et l'entonnoir de décision (« 41/135 signaux autorisés, 94 bloqués »). Ces deux
blocs appartiennent au canal marché (§ 5) et y étaient déjà émis : c'était l'une
des sept duplications mesurées entre les six canaux.

Deux propriétés verrouillées ici :

1. **Le briefing ne parle pas du marché.** Ni régimes, ni paires, ni comptage de
   signaux.
2. **La gouvernance annonce la contrainte BLOQUANTE**, pas le compteur le plus
   flatteur. La règle du statisticien exige 500 trades, 150 gagnants ET 150
   perdants : c'est le plus en retard des trois qui commande la date, et
   afficher seulement le plus avancé laisserait croire le gate proche.
"""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.intelligence.system_intel_reporter import (
    _GATE_LOSSES,
    _GATE_N,
    _GATE_WINS,
    SystemIntelReporter,
)


def _ctx(**over):
    base = {
        "elapsed_h": 6.0,
        "n_since": 12,
        "kpis": {
            "n": 190,
            "n_wins": 72,
            "n_losses": 115,
            "win_rate": 37.9,
            "pf": 0.75,
            "sharpe": -5.7,
            "max_dd": 0.015,
            "total_pnl": -7.0,
            "by_symbol": {},
        },
        "pnl_since": -1.2,
        "trade_stall_h": 0.5,
        "regimes_now": {"BTC/USDT": "bear_trend", "ETH/USDT": "sideways"},
        "regime_changes": ["BTC/USDT: sideways → bear_trend"],
        "decision_funnel": {"total_evaluated": 135, "allowed": 41, "blocked": 94},
        "dataset": {"violations": 0},
        "stability": {"state": "stable"},
        "awareness": {"level": "OK"},
        "override": {"level": "CLEAR"},
        "pos_manager_stats": {},
        "activity": {},
        "regret": {},
        "mistakes": {},
    }
    base.update(over)
    return base


def _render(**over):
    return SystemIntelReporter()._render(_ctx(**over), 861)


class TestLeBriefingNeParlePasDuMarche:
    def test_pas_de_narration_de_marche(self):
        out = _render()
        assert "MARCHÉ" not in out

    def test_pas_de_regimes_ni_de_paires(self):
        out = _render()
        assert "bear_trend" not in out and "sideways" not in out
        assert "BTC" not in out

    def test_pas_de_comptage_de_signaux(self):
        out = _render()
        assert "bloqués" not in out and "41" not in out


class TestLeBriefingNeParlePasDePerformance:
    def test_pas_de_pnl_en_dollars(self):
        assert "$" not in _render()

    def test_pas_de_win_rate_ni_sharpe(self):
        out = _render()
        assert "Win Rate" not in out and "Sharpe" not in out


class TestGouvernance:
    def test_les_trois_bornes_du_gate_sont_annoncees(self):
        out = _render()
        assert f"190/{_GATE_N}" in out
        assert f"72/{_GATE_WINS}" in out
        assert f"115/{_GATE_LOSSES}" in out

    def test_la_contrainte_bloquante_est_la_plus_eloignee(self):
        """310 trades manquants > 78 gagnants > 35 perdants."""
        out = _render()
        assert "310 trades manquants" in out

    def test_le_blocage_suit_le_compteur_le_plus_en_retard(self):
        """N presque atteint mais gagnants loin : c'est eux qui commandent."""
        out = _render(
            kpis={
                "n": 495,
                "n_wins": 60,
                "n_losses": 300,
                "win_rate": 12.0,
                "pf": 0.5,
                "sharpe": -1.0,
                "max_dd": 0.02,
                "total_pnl": -1.0,
                "by_symbol": {},
            }
        )
        assert "90 gagnants manquants" in out

    def test_aucune_contrainte_quand_les_trois_sont_franchies(self):
        out = _render(
            kpis={
                "n": 600,
                "n_wins": 200,
                "n_losses": 200,
                "win_rate": 50.0,
                "pf": 1.2,
                "sharpe": 1.1,
                "max_dd": 0.01,
                "total_pnl": 5.0,
                "by_symbol": {},
            }
        )
        assert "contrainte bloquante" not in out


class TestSanteResteAnomalieSeulement:
    def test_silencieux_quand_tout_va_bien(self):
        assert "SANTÉ : OK" in _render()

    def test_parle_quand_le_dataset_est_viole(self):
        out = _render(dataset={"violations": 3})
        assert "ALERTE" in out and "3 violation" in out

    @pytest.mark.parametrize("etat", ["oscillating", "degraded"])
    def test_parle_quand_le_comportement_derive(self, etat):
        out = _render(stability={"state": etat})
        assert "ALERTE" in out and etat in out
