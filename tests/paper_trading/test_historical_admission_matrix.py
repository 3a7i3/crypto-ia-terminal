"""Canari historique SPX / MET / VIRTUAL (Phase 4.6).

Test PERMANENT : reproduit l'état runtime observé le 2026-08-26 (Phase 1)
et vérifie que le chemin de données PAPER expose correctement 3 positions à
PortfolioBrain. Ce test doit :

  * fail si l'adaptateur paper_portfolio_view cesse d'exposer les positions
    du simulateur ;
  * fail si PortfolioBrain cesse d'appliquer sa borne MAX_POSITIONS ;
  * fail si quelqu'un retire la condition ``n_positions >= MAX_POSITIONS``
    de PortfolioBrain.check_new_trade.

Les variantes V1..V4 avec verdict final combiné (INV-001 + INV-002)
arriveront au commit suivant, une fois AdmissionVerdict et Level A wiring
livrés.
"""

from __future__ import annotations

import pytest

from paper_trading.paper_portfolio_view import paper_portfolio_view
from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain


class TestHistoricalDataPath:
    """Phase 4.6 — data path : PortfolioBrain voit-il ce que MexcSimulator détient ?"""

    def test_historical_state_reconstructs_three_positions(
        self, mexc_positions_historical
    ):
        assert len(mexc_positions_historical._positions) == 3
        view = paper_portfolio_view(mexc_positions_historical)
        assert {pv.symbol for pv in view} == {
            "SPX/USDT",
            "MET/USDT",
            "VIRTUAL/USDT",
        }

    def test_historical_regimes_ventilation(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        pb = PortfolioBrain(total_capital=1000.0)
        snap = pb._snapshot(view)
        # 2 × bull_trend (SPX, VIRTUAL) + 1 × sideways (MET) × 10 USD
        assert snap.by_regime["bull_trend"] == pytest.approx(20.0)
        assert snap.by_regime["sideways"] == pytest.approx(10.0)
        assert snap.n_positions == 3


class TestHistoricalPortfolioBrainDecision:
    """Preuve directe : PortfolioBrain applique la borne INV-001 (canari)."""

    def test_hard_max_2_rejects_fourth_admission_attempt(
        self, mexc_positions_historical
    ):
        """Avec HARD_MAX=2 et 3 positions déjà ouvertes, toute 4ᵉ admission
        doit être rejetée par PortfolioBrain (condition #6 de check_new_trade).

        C'est le canari du bug de Phase 1 : si un jour ce test devient vert
        alors qu'on tente une 4ᵉ admission avec n=3 et max=2, la borne aura
        disparu du portefeuille et le bug pourra revenir.
        """
        view = paper_portfolio_view(mexc_positions_historical)
        pb = PortfolioBrain(total_capital=1000.0)
        pb.MAX_POSITIONS = 2  # override test — INV-001 stricte
        verdict = pb.check_new_trade(
            symbol="BNB/USDT",
            action="BUY",
            size_usd=10.0,
            regime="bull_trend",
            open_positions=view,
        )
        assert verdict.allowed is False
        assert "Max positions" in verdict.reason
        assert verdict.metrics["n_positions"] == 3

    def test_hard_max_5_would_accept_admission(self, mexc_positions_historical):
        """Contrepreuve : avec HARD_MAX=5 (défaut PortfolioBrain), la même
        admission est autorisée par la condition INV-001. Cela prouve que
        le rejet du test précédent vient bien de la borne, pas d'un autre
        filtre (exposition, corrélation, hedge).
        """
        view = paper_portfolio_view(mexc_positions_historical)
        pb = PortfolioBrain(total_capital=1000.0)
        # PB_MAX_POSITIONS par défaut = 5
        verdict = pb.check_new_trade(
            symbol="BNB/USDT",
            action="BUY",
            size_usd=10.0,
            regime="bull_trend",
            open_positions=view,
        )
        # Peut être allowed ou réduit par exposure (30 USD + 10 USD = 40 USD
        # sur capital 1000 = 4% < 40% seuil) — mais surtout PAS rejeté sur
        # n_positions.
        assert verdict.allowed is True, (
            f"attendu allowed=True pour HARD_MAX=5, reçu {verdict.reason}"
        )
