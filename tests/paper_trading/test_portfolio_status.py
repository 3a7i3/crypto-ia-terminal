"""Tests — PortfolioStatus : source de données honnête pour le reporting.

Corrige le mensonge du label ``META-STRATEGY: <personality>`` (Phase 2 §5,
critère P2) : le label présentait la personality du DERNIER signal comme
si c'était une politique globale de portefeuille.

``build_portfolio_status`` produit une structure honnête au niveau
portefeuille : compteur réel, plafond, état d'admission, ventilation par
personality et par régime — construite depuis la vue canonique
(MexcSimulator._positions via paper_portfolio_view), jamais depuis
``meta_engine.current_personality()``.

Fonction pure, passive. Ne décide rien.
"""

from __future__ import annotations

import pytest

from paper_trading.paper_portfolio_view import (
    PortfolioSide,
    PositionView,
    paper_portfolio_view,
)
from paper_trading.portfolio_status import (
    AdmissionState,
    build_portfolio_status,
    render_portfolio_block,
)


def _view(symbol, personality, regime, size=10.0):
    return PositionView(
        symbol=symbol,
        size_usd=size,
        regime=regime,
        pnl_usd=0.0,
        side=PortfolioSide.LONG,
        personality=personality,
    )


class TestAdmissionState:
    def test_open_when_below_limit(self):
        st = build_portfolio_status([_view("A/USDT", "momentum_following", "bull_trend")], hard_max=5)
        assert st.current_positions == 1
        assert st.hard_position_limit == 5
        assert st.admission_state == AdmissionState.OPEN

    def test_saturated_when_at_limit(self):
        views = [
            _view("A/USDT", "mean_reversion", "sideways"),
            _view("B/USDT", "mean_reversion", "sideways"),
        ]
        st = build_portfolio_status(views, hard_max=2)
        assert st.admission_state == AdmissionState.SATURATED

    def test_over_limit_when_above(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
            _view("VIRTUAL/USDT", "momentum_following", "bull_trend"),
        ]
        st = build_portfolio_status(views, hard_max=2)
        assert st.current_positions == 3
        assert st.admission_state == AdmissionState.OVER_LIMIT

    def test_empty_portfolio_is_open(self):
        st = build_portfolio_status([], hard_max=5)
        assert st.current_positions == 0
        assert st.admission_state == AdmissionState.OPEN


class TestVentilation:
    def test_positions_by_personality(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
            _view("VIRTUAL/USDT", "momentum_following", "bull_trend"),
        ]
        st = build_portfolio_status(views, hard_max=5)
        assert st.positions_by_personality == {
            "momentum_following": 2,
            "mean_reversion": 1,
        }

    def test_positions_by_regime(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
            _view("VIRTUAL/USDT", "momentum_following", "bull_trend"),
        ]
        st = build_portfolio_status(views, hard_max=5)
        assert st.positions_by_regime == {"bull_trend": 2, "sideways": 1}

    def test_unknown_personality_bucketed(self):
        st = build_portfolio_status([_view("A/USDT", "", "bull_trend")], hard_max=5)
        assert st.positions_by_personality == {"unknown": 1}


class TestContract:
    def test_to_dict_shape(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
            _view("VIRTUAL/USDT", "momentum_following", "bull_trend"),
        ]
        d = build_portfolio_status(views, hard_max=2).to_dict()
        assert d["current_positions"] == 3
        assert d["hard_position_limit"] == 2
        assert d["admission_state"] == "OVER_LIMIT"
        assert d["positions_by_personality"] == {
            "momentum_following": 2,
            "mean_reversion": 1,
        }
        assert d["positions_by_regime"] == {"bull_trend": 2, "sideways": 1}

    def test_status_is_immutable(self):
        st = build_portfolio_status([], hard_max=5)
        with pytest.raises(Exception):
            st.current_positions = 99  # type: ignore[misc]

    def test_negative_hard_max_raises(self):
        with pytest.raises(ValueError):
            build_portfolio_status([], hard_max=-1)


class TestRenderHonest:
    """Le rendu ne doit jamais présenter une personality de signal comme policy globale."""

    def test_over_limit_marked_visibly(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
            _view("VIRTUAL/USDT", "momentum_following", "bull_trend"),
        ]
        block = render_portfolio_block(build_portfolio_status(views, hard_max=2))
        assert "3 / 2" in block
        assert "LIMIT" in block.upper() or "OVER" in block.upper()

    def test_saturated_shown(self):
        views = [_view("A/USDT", "mean_reversion", "sideways")]
        block = render_portfolio_block(build_portfolio_status(views, hard_max=1))
        assert "1 / 1" in block

    def test_block_lists_personalities(self):
        views = [
            _view("SPX/USDT", "momentum_following", "bull_trend"),
            _view("MET/USDT", "mean_reversion", "sideways"),
        ]
        block = render_portfolio_block(build_portfolio_status(views, hard_max=5))
        assert "momentum_following" in block
        assert "mean_reversion" in block


class TestCanonicalIntegration:
    """Le statut se construit depuis la vue canonique (personality incluse)."""

    def test_view_carries_personality(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        personalities = {pv.symbol: pv.personality for pv in view}
        assert personalities["SPX/USDT"] == "momentum_following"
        assert personalities["MET/USDT"] == "mean_reversion"
        assert personalities["VIRTUAL/USDT"] == "momentum_following"

    def test_historical_status_over_limit_at_two(self, mexc_positions_historical):
        view = paper_portfolio_view(mexc_positions_historical)
        st = build_portfolio_status(view, hard_max=2)
        assert st.current_positions == 3
        assert st.admission_state == AdmissionState.OVER_LIMIT
        assert st.positions_by_personality == {
            "momentum_following": 2,
            "mean_reversion": 1,
        }
