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


class TestHistoricalLevelAWiring:
    """Canari Phase 4.6 V1..V4 — verdict Level A appliqué via la vraie frontière.

    Le test simule la 4ᵉ tentative d'ouverture sur l'état {SPX, MET, VIRTUAL}
    en pilotant HARD_MAX via ``PB_MAX_POSITIONS`` et en produisant le verdict
    via ``evaluate_hard_portfolio_ceiling``. Prouve que la chaîne complète
    (vue canonique → Level A → simulateur → ledger) protège l'invariant.
    """

    def _new_verdict(self, sim):
        from paper_trading.admission_policy import evaluate_hard_portfolio_ceiling

        pb_max = int(__import__("os").environ.get("PB_MAX_POSITIONS", "5"))
        view = paper_portfolio_view(sim)
        return evaluate_hard_portfolio_ceiling(len(view), pb_max)

    def test_v1_hard_max_5_default_admits(
        self, mexc_positions_historical, monkeypatch, tmp_path
    ):
        """V1 — comportement historique préservé (HARD_MAX=5 par défaut)."""
        from paper_trading.admission_ledger import (
            AdmissionLedger,
            reset_admission_ledger_singleton,
        )

        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "v1.jsonl"))
        monkeypatch.setenv("PB_MAX_POSITIONS", "5")
        reset_admission_ledger_singleton()
        try:
            monkeypatch.setattr(
                mexc_positions_historical, "_fetch_price", lambda _sym: 100.0
            )
            mexc_positions_historical._capital = 100.0
            verdict = self._new_verdict(mexc_positions_historical)

            n_before = len(mexc_positions_historical._positions)
            assert n_before == 3
            result = mexc_positions_historical.place_market_order(
                symbol="BNB/USDT",
                side="buy",
                qty_usd=10.0,
                current_price=100.0,
                admission=verdict,
                cycle_id="v1",
            )
            assert result is not None
            assert result.status.value == "FILLED"
            assert len(mexc_positions_historical._positions) == 4
            pairs = AdmissionLedger().pairs()
            assert len(pairs) == 1
            _, out = pairs[0]
            assert out["write_result"] == "FILLED"
        finally:
            reset_admission_ledger_singleton()

    def test_v3_hard_max_2_rejects_fourth_admission(
        self, mexc_positions_historical, monkeypatch, tmp_path
    ):
        """V3 — HARD_MAX=2 avec 3 positions déjà ouvertes (état OVER_LIMIT).
        La 4ᵉ tentative doit être bloquée par PORTFOLIO_HARD_CEILING.
        C'est le canari de régression Phase 1 : ce test doit rester rouge si
        quelqu'un retire INV-001 du chemin PAPER."""
        from paper_trading.admission_ledger import (
            AdmissionLedger,
            reset_admission_ledger_singleton,
        )

        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "v3.jsonl"))
        monkeypatch.setenv("PB_MAX_POSITIONS", "2")
        reset_admission_ledger_singleton()
        try:
            monkeypatch.setattr(
                mexc_positions_historical, "_fetch_price", lambda _sym: 100.0
            )
            mexc_positions_historical._capital = 100.0
            verdict = self._new_verdict(mexc_positions_historical)
            assert verdict.decision.value == "REJECTED"
            assert verdict.blocker.value == "PORTFOLIO_HARD_CEILING"

            n_before = len(mexc_positions_historical._positions)
            result = mexc_positions_historical.place_market_order(
                symbol="BNB/USDT",
                side="buy",
                qty_usd=10.0,
                current_price=100.0,
                admission=verdict,
                cycle_id="v3",
            )
            assert result is not None
            assert result.status.value == "REJECTED"
            # Aucune fermeture forcée — les 3 positions historiques restent (ADR-0007)
            assert len(mexc_positions_historical._positions) == n_before == 3

            pairs = AdmissionLedger().pairs()
            assert len(pairs) == 1
            att, out = pairs[0]
            assert att["decision"] == "REJECTED"
            assert att["blocker"] == "PORTFOLIO_HARD_CEILING"
            assert out["write_result"] == "REJECTED_ADMISSION"
            assert out["anomaly"] == "PORTFOLIO_HARD_CEILING"
            assert out["n_after"] == 3
        finally:
            reset_admission_ledger_singleton()

    def test_v4_over_limit_restored_blocks_new_entries_no_forced_close(
        self, mexc_positions_historical, monkeypatch, tmp_path
    ):
        """V4 — INV-003 opérationnel : après restore avec HARD_MAX=2, les 3
        positions restaurées restent (aucune fermeture forcée, ADR-0007) et
        toute nouvelle entrée est bloquée."""
        from paper_trading.admission_ledger import (
            AdmissionLedger,
            reset_admission_ledger_singleton,
        )

        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "v4.jsonl"))
        monkeypatch.setenv("PB_MAX_POSITIONS", "2")
        reset_admission_ledger_singleton()
        try:
            monkeypatch.setattr(
                mexc_positions_historical, "_fetch_price", lambda _sym: 100.0
            )
            mexc_positions_historical._capital = 100.0
            # Les 3 positions historiques sont déjà chargées par la fixture
            # (analogue à un restore au boot). Aucune n'est fermée.
            assert len(mexc_positions_historical._positions) == 3

            # Deux tentatives successives — les deux doivent être rejetées
            for i, sym in enumerate(("BNB/USDT", "XRP/USDT")):
                verdict = self._new_verdict(mexc_positions_historical)
                result = mexc_positions_historical.place_market_order(
                    symbol=sym,
                    side="buy",
                    qty_usd=10.0,
                    current_price=100.0,
                    admission=verdict,
                    cycle_id=f"v4-{i}",
                )
                assert result.status.value == "REJECTED"

            # Toujours 3 positions — aucune n'a été forcée à fermer
            assert len(mexc_positions_historical._positions) == 3
            pairs = AdmissionLedger().pairs()
            assert len(pairs) == 2
            assert all(o["write_result"] == "REJECTED_ADMISSION" for _, o in pairs)
        finally:
            reset_admission_ledger_singleton()
