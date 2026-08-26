"""Tests P5-04 — wiring MexcSimulator ↔ AdmissionVerdict + ledger causal.

Vérifie l'invariant central :

    aucune mutation de ``_positions`` sans AdmissionAttempt persisté,
    ni sans AdmissionOutcome ultérieur reliant l'attempt au résultat.

Couvre :
  * compat historique (``admission=None`` → comportement inchangé) ;
  * fail-fast REJECTED_ADMISSION (verdict rejeté → attempt persisté +
    outcome REJECTED_ADMISSION, aucune écriture, retour REJECTED) ;
  * défense TOCTOU (verdict APPROVED mais le portefeuille a bougé →
    outcome REJECTED_STALE, aucune écriture) ;
  * chemin nominal FILLED (attempt + outcome liés par ``attempt_id``,
    ``position_identity`` renseigné) ;
  * classification des rejets internes du simulateur (duplicate,
    capital insuffisant) ;
  * P4 admission causality : chaque tentative produit exactement 1
    attempt + 1 outcome, jamais un attempt orphelin quand la fonction
    retourne normalement.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from paper_trading.admission_ledger import (
    AdmissionLedger,
    reset_admission_ledger_singleton,
)
from paper_trading.admission_types import (
    AdmissionBlocker,
    AdmissionDecision,
    AdmissionLevel,
    AdmissionVerdict,
)
from paper_trading.mexc_simulator import (
    MexcSimulator,
    OrderSide,
    OrderStatus,
)
from tests.paper_trading.conftest import _make_position


@pytest.fixture(autouse=True)
def isolate_admission_ledger(tmp_path, monkeypatch):
    p = tmp_path / "admission_ledger_int.jsonl"
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(p))
    reset_admission_ledger_singleton()
    yield p
    reset_admission_ledger_singleton()


@pytest.fixture
def sim() -> MexcSimulator:
    """Simulateur avec capital de test, sans thread background."""
    s = MexcSimulator(mexc_reader=MagicMock(), telegram_fn=lambda _m: None)
    s._capital = 100.0
    s._initial_capital = 100.0
    s._positions.clear()
    return s


def _make_verdict(
    decision=AdmissionDecision.APPROVED,
    n=0,
    max_=5,
    blocker=AdmissionBlocker.NONE,
    reason="",
) -> AdmissionVerdict:
    return AdmissionVerdict(
        decision=decision,
        level=AdmissionLevel.A,
        n_at_check=n,
        hard_max_at_check=max_,
        blocker=blocker,
        reason=reason,
        checked_by="test",
    )


class TestLegacyCompat:
    """Sans verdict fourni, comportement historique — aucune écriture au ledger."""

    def test_admission_none_does_not_touch_ledger(
        self, sim, isolate_admission_ledger, monkeypatch
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        result = sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=None,
        )
        assert result is not None
        assert result.status == OrderStatus.FILLED
        assert not isolate_admission_ledger.exists() or isolate_admission_ledger.stat().st_size == 0

    def test_admission_none_writes_position_normally(self, sim, monkeypatch):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        assert len(sim._positions) == 0
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
        )
        assert len(sim._positions) == 1


class TestRejectedAdmission:
    """Verdict REJECTED → attempt persisté + outcome REJECTED_ADMISSION, aucune mutation."""

    def test_rejected_verdict_produces_no_position(self, sim, monkeypatch):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        verdict = _make_verdict(
            decision=AdmissionDecision.REJECTED,
            n=5,
            max_=5,
            blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
            reason="Max positions atteint: 5/5",
        )
        result = sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
            cycle_id="42",
        )
        assert result is not None
        assert result.status == OrderStatus.REJECTED
        assert len(sim._positions) == 0

    def test_rejected_verdict_persists_attempt_and_outcome(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        verdict = _make_verdict(
            decision=AdmissionDecision.REJECTED,
            n=5,
            max_=5,
            blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
            reason="Max positions atteint",
        )
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
            cycle_id="42",
        )
        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 1
        att, out = pairs[0]
        assert att["symbol"] == "BTC/USDT"
        assert att["decision"] == "REJECTED"
        assert att["blocker"] == "PORTFOLIO_HARD_CEILING"
        assert att["cycle_id"] == "42"
        assert out is not None
        assert out["write_result"] == "REJECTED_ADMISSION"
        assert out["n_after"] == 0
        assert out["anomaly"] == "PORTFOLIO_HARD_CEILING"
        assert out["attempt_id"] == att["attempt_id"]


class TestToctouStale:
    """Verdict APPROVED mais l'état a changé entre check et write → REJECTED_STALE."""

    def test_stale_verdict_when_positions_now_at_ceiling(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        # Verdict pris quand n=1, max=2 (allowed).
        # Entre-temps une seconde position est apparue → n=2, ce qui met le simulator
        # à l'égalité avec hard_max_at_check=2.
        sim._positions["ETH/USDT"] = _make_position(
            "ETH/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            regime="bull_trend",
            personality="momentum",
        )
        sim._positions["SOL/USDT"] = _make_position(
            "SOL/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            regime="bull_trend",
            personality="momentum",
        )
        verdict = _make_verdict(
            decision=AdmissionDecision.APPROVED,
            n=1,
            max_=2,  # au moment du check n=1 < 2 → approved. Mais maintenant n=2.
        )
        result = sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
            cycle_id="99",
        )
        assert result is not None
        assert result.status == OrderStatus.REJECTED
        assert "BTC/USDT" not in sim._positions
        assert len(sim._positions) == 2  # inchangé

        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 1
        att, out = pairs[0]
        assert att["decision"] == "APPROVED"  # verdict initial
        assert out["write_result"] == "REJECTED_STALE"
        assert out["anomaly"] == "STALE_TOCTOU"


class TestApprovedNominalPath:
    """Verdict APPROVED + write ok → FILLED, ledger causal complet, position ouverte."""

    def test_approved_writes_position_and_journals_filled(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        verdict = _make_verdict(n=0, max_=5)
        result = sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
            cycle_id="7",
        )
        assert result is not None
        assert result.status == OrderStatus.FILLED
        assert len(sim._positions) == 1

        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 1
        att, out = pairs[0]
        assert att["decision"] == "APPROVED"
        assert att["cycle_id"] == "7"
        assert out["write_result"] == "FILLED"
        assert out["n_after"] == 1
        assert out["position_identity"].startswith("BTC/USDT#")
        assert out["attempt_id"] == att["attempt_id"]

    def test_multiple_approvals_produce_multiple_paired_events(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        for sym in ("BTC/USDT", "ETH/USDT", "SOL/USDT"):
            v = _make_verdict(n=len(sim._positions), max_=5)
            sim.place_market_order(
                symbol=sym,
                side="buy",
                qty_usd=10.0,
                current_price=100.0,
                admission=v,
                cycle_id="1",
            )
        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 3
        for att, out in pairs:
            assert out is not None
            assert out["write_result"] == "FILLED"
            assert out["attempt_id"] == att["attempt_id"]


class TestWriteResultClassification:
    """Le write_result reflète fidèlement le résultat interne du simulateur."""

    def test_duplicate_symbol_maps_to_rejected_duplicate(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        # Pré-remplit BTC → prochaine admission APPROVED sur BTC = duplicate
        sim._positions["BTC/USDT"] = _make_position(
            "BTC/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            regime="bull_trend",
            personality="momentum",
        )
        verdict = _make_verdict(n=1, max_=5)
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
        )
        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 1
        _, out = pairs[0]
        assert out["write_result"] == "REJECTED_DUPLICATE"

    def test_insufficient_capital_maps_to_rejected_capital(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        sim._capital = 0.5  # trop bas pour une position même minimale
        verdict = _make_verdict(n=0, max_=5)
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=50.0,  # > capital
            current_price=100.0,
            admission=verdict,
        )
        pairs = AdmissionLedger().pairs()
        assert len(pairs) == 1
        _, out = pairs[0]
        assert out["write_result"] == "REJECTED_INSUFFICIENT_CAPITAL"


class TestInvariantP4CausalCompleteness:
    """P4 : chaque tentative produit exactement 1 attempt + 1 outcome liés."""

    def test_every_call_with_admission_produces_paired_events(
        self, sim, monkeypatch, isolate_admission_ledger
    ):
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)
        # Un mix : approved+ok, approved+duplicate, rejected, stale
        sim._positions["ETH/USDT"] = _make_position(
            "ETH/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            regime="bull_trend",
            personality="momentum",
        )
        # 1) approved+ok
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=_make_verdict(n=1, max_=5),
        )
        # 2) approved sur symbol déjà présent
        sim.place_market_order(
            symbol="ETH/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=_make_verdict(n=2, max_=5),
        )
        # 3) rejected
        sim.place_market_order(
            symbol="SOL/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=_make_verdict(
                decision=AdmissionDecision.REJECTED,
                n=2,
                max_=2,
                blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
            ),
        )

        pairs = AdmissionLedger().pairs()
        # 3 attempts, chacun a son outcome (aucun orphelin)
        assert len(pairs) == 3
        assert all(out is not None for _, out in pairs)
        # attempt_id unique par paire, cohérent entre att et out
        for att, out in pairs:
            assert att["attempt_id"] == out["attempt_id"]


class TestArchitecturalBoundary:
    """La frontière d'écriture ne doit journaliser qu'à l'admission_ledger,
    jamais au paper_trades.jsonl du recorder (chaînes distinctes)."""

    def test_admission_ledger_isolated_from_paper_trades_recorder(
        self, sim, monkeypatch, isolate_admission_ledger, tmp_path
    ):
        # Redirige PAPER_TRADE_LOG vers un chemin de test dédié
        pt = tmp_path / "paper_trades_iso.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(pt))
        monkeypatch.setattr(sim, "_fetch_price", lambda _sym: 100.0)

        # Verdict REJECTED → ne doit RIEN écrire dans paper_trades.jsonl
        verdict = _make_verdict(
            decision=AdmissionDecision.REJECTED,
            n=5,
            max_=5,
            blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
        )
        sim.place_market_order(
            symbol="BTC/USDT",
            side="buy",
            qty_usd=10.0,
            current_price=100.0,
            admission=verdict,
        )
        assert not pt.exists() or pt.stat().st_size == 0
        # Mais l'admission_ledger doit contenir attempt + outcome
        assert isolate_admission_ledger.exists()
        assert isolate_admission_ledger.stat().st_size > 0
