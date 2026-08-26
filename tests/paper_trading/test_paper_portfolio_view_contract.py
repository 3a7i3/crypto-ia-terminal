"""Contract tests (Phase 4.1) — paper_portfolio_view.

STOP-GATE : ces tests DOIVENT être verts avant tout branchement de
l'adaptateur dans advisor_loop. Toute cassure ici indique un contrat non
honoré entre MexcSimulator et PortfolioBrain.

CT-01..10 couvrent shape, renaming (qty_usd → size_usd), mapping de side
(BUY→long, SELL→short), défaut leverage, robustesse aux régimes inconnus,
et compatibilité binaire avec PortfolioBrain._snapshot.
"""

from __future__ import annotations

import pytest

from paper_trading.mexc_simulator import OrderSide
from paper_trading.paper_portfolio_view import (
    PortfolioSide,
    paper_portfolio_view,
)
from tests.paper_trading.conftest import _make_position


class TestContractShape:
    """CT-01..05 : shape et renaming du contrat."""

    def test_ct01_view_maps_qty_usd_to_size_usd(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        assert len(view) == 3, "fixture historique doit fournir 3 positions"
        for pv in view:
            assert isinstance(pv.size_usd, float)
            assert pv.size_usd == 10.0

    def test_ct02_view_maps_buy_to_long(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        for pv in view:
            assert pv.side == PortfolioSide.LONG
            assert pv.side.value == "long"

    def test_ct03_view_maps_sell_to_short(self, mexc_positions_empty):
        pos = _make_position(
            "ETH/USDT",
            OrderSide.SELL,
            qty_usd=10.0,
            entry_price=3000.0,
            regime="bear_trend",
            personality="defensive_short",
        )
        mexc_positions_empty._positions[pos.symbol] = pos
        view = paper_portfolio_view(mexc_positions_empty)
        assert len(view) == 1
        assert view[0].side == PortfolioSide.SHORT
        assert view[0].side.value == "short"

    def test_ct04_view_defaults_leverage_1(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        for pv in view:
            assert pv.leverage == 1

    def test_ct05_view_preserves_regime(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        regimes = {pv.symbol: pv.regime for pv in view}
        assert regimes["SPX/USDT"] == "bull_trend"
        assert regimes["MET/USDT"] == "sideways"
        assert regimes["VIRTUAL/USDT"] == "bull_trend"


class TestContractBehavior:
    """CT-06..10 : filtres, ordre, robustesse."""

    def test_ct06_view_excludes_closed(self, mexc_positions_historical):
        # Marque MET fermée (closed_ts != 0 ⇒ is_open == False).
        mexc_positions_historical._positions["MET/USDT"].closed_ts = 1_000_000.0
        view = paper_portfolio_view(mexc_positions_historical)
        symbols = {pv.symbol for pv in view}
        assert symbols == {"SPX/USDT", "VIRTUAL/USDT"}

    def test_ct07_view_stable_ordering(self, mexc_positions_historical):
        v1 = [pv.symbol for pv in paper_portfolio_view(mexc_positions_historical)]
        v2 = [pv.symbol for pv in paper_portfolio_view(mexc_positions_historical)]
        assert v1 == v2, "ordre non déterministe entre deux appels"
        assert v1 == sorted(v1), "ordre attendu = tri alphabétique des symboles"

    def test_ct08_view_contract_matches_portfolio_brain_snapshot(
        self, mexc_positions_historical
    ):
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain

        view = paper_portfolio_view(mexc_positions_historical)
        pb = PortfolioBrain(total_capital=1000.0)
        snap = pb._snapshot(view)
        assert snap.n_positions == 3
        assert snap.total_exposure_usd == pytest.approx(30.0)
        assert snap.by_regime["bull_trend"] == pytest.approx(20.0)
        assert snap.by_regime["sideways"] == pytest.approx(10.0)
        assert snap.by_symbol["SPX/USDT"] == pytest.approx(10.0)
        assert snap.by_symbol["MET/USDT"] == pytest.approx(10.0)
        assert snap.by_symbol["VIRTUAL/USDT"] == pytest.approx(10.0)

    def test_ct09_view_zero_positions_yields_empty_snapshot(
        self, mexc_positions_empty
    ):
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain

        view = paper_portfolio_view(mexc_positions_empty)
        assert view == []
        snap = PortfolioBrain(total_capital=1000.0)._snapshot(view)
        assert snap.n_positions == 0
        assert snap.total_exposure_usd == 0.0

    def test_ct10_view_survives_unknown_regime(self, mexc_positions_empty):
        pos = _make_position(
            "SOL/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            regime="",
            personality="unknown",
        )
        # regime None ne doit pas casser l'adaptateur — coalesce vers "unknown"
        pos.regime = None  # type: ignore[assignment]
        mexc_positions_empty._positions[pos.symbol] = pos
        view = paper_portfolio_view(mexc_positions_empty)
        assert len(view) == 1
        assert view[0].regime == "unknown"


class TestNullInput:
    """Robustesse aux entrées dégénérées."""

    def test_view_of_none_yields_empty_list(self):
        assert paper_portfolio_view(None) == []
