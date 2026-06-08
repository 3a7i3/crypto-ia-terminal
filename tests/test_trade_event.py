"""
Tests de contrat pour TradeEvent.
Garantie exécutable des invariants définis dans docs/TRADE_EVENT_CONTRACT.md.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.trade_event import MarketRegime, TradeEvent

_T0 = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)


def _make(**overrides) -> TradeEvent:
    defaults = dict(
        trade_id="T001",
        run_id="run-abc",
        strategy_id="sma_3_10",
        symbol="BTC/USDT",
        side="buy",
        entry_price=60_000.0,
        exit_price=61_200.0,
        quantity=0.1,
        execution_mode="paper",
        gross_pnl_usd=120.0,
        fees_usd=12.0,
        slippage_usd=3.0,
        opened_at=_T0,
        closed_at=_T1,
    )
    return TradeEvent(**{**defaults, **overrides})


# ── Invariant PnL ──────────────────────────────────────────────────────────────


class TestInvariant:
    def test_net_pnl_equals_gross_minus_fees_minus_slippage(self):
        e = _make(gross_pnl_usd=120.0, fees_usd=12.0, slippage_usd=3.0)
        assert e.net_pnl_usd == pytest.approx(105.0)

    def test_net_pnl_negative_trade(self):
        e = _make(gross_pnl_usd=-50.0, fees_usd=10.0, slippage_usd=2.0)
        assert e.net_pnl_usd == pytest.approx(-62.0)

    def test_net_pnl_zero_costs(self):
        e = _make(gross_pnl_usd=100.0, fees_usd=0.0, slippage_usd=0.0)
        assert e.net_pnl_usd == pytest.approx(100.0)

    def test_net_pnl_breakeven(self):
        e = _make(gross_pnl_usd=15.0, fees_usd=12.0, slippage_usd=3.0)
        assert e.net_pnl_usd == pytest.approx(0.0)

    def test_total_cost_is_fees_plus_slippage(self):
        e = _make(fees_usd=12.0, slippage_usd=3.0)
        assert e.total_cost_usd == pytest.approx(15.0)

    def test_net_plus_cost_equals_gross(self):
        e = _make(gross_pnl_usd=120.0, fees_usd=12.0, slippage_usd=3.0)
        assert e.net_pnl_usd + e.total_cost_usd == pytest.approx(e.gross_pnl_usd)


# ── Immutabilité ───────────────────────────────────────────────────────────────


class TestImmutability:
    def test_frozen_cannot_set_field(self):
        e = _make()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            e.gross_pnl_usd = 999.0  # type: ignore[misc]

    def test_frozen_cannot_set_derived_property(self):
        e = _make()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            e.net_pnl_usd = 999.0  # type: ignore[misc]

    def test_two_identical_events_are_equal(self):
        assert _make() == _make()


# ── UTC obligatoire ────────────────────────────────────────────────────────────


class TestUTC:
    def test_naive_opened_at_rejected(self):
        with pytest.raises(ValueError, match="opened_at"):
            _make(opened_at=datetime(2026, 6, 4, 10, 0))  # naive — pas de tzinfo

    def test_naive_closed_at_rejected(self):
        with pytest.raises(ValueError, match="closed_at"):
            _make(closed_at=datetime(2026, 6, 4, 12, 0))  # naive

    def test_non_utc_offset_rejected(self):
        paris = timezone(timedelta(hours=2))
        with pytest.raises(ValueError, match="UTC"):
            _make(opened_at=datetime(2026, 6, 4, 10, 0, tzinfo=paris))

    def test_utc_accepted(self):
        e = _make(opened_at=_T0, closed_at=_T1)
        assert e.opened_at.utcoffset().total_seconds() == 0

    def test_hold_seconds(self):
        e = _make(opened_at=_T0, closed_at=_T1)
        assert e.hold_seconds == pytest.approx(7200.0)  # 2h


# ── Identité traçable ──────────────────────────────────────────────────────────


class TestOwnership:
    def test_trade_id_is_present(self):
        e = _make(trade_id="T-XYZ")
        assert e.trade_id == "T-XYZ"

    def test_run_id_links_to_session(self):
        e = _make(run_id="run-2026-06-04")
        assert e.run_id == "run-2026-06-04"

    def test_strategy_id_is_traceable(self):
        e = _make(strategy_id="rsi_extreme_v2")
        assert e.strategy_id == "rsi_extreme_v2"

    def test_symbol_is_present(self):
        e = _make(symbol="ETH/USDT")
        assert e.symbol == "ETH/USDT"


# ── Modes d'exécution ──────────────────────────────────────────────────────────


class TestExecutionMode:
    @pytest.mark.parametrize("mode", ["backtest", "paper", "live"])
    def test_valid_modes(self, mode):
        assert _make(execution_mode=mode).execution_mode == mode

    def test_side_sell(self):
        e = _make(side="sell", gross_pnl_usd=-30.0)
        assert e.side == "sell"
        assert e.net_pnl_usd == pytest.approx(-30.0 - 12.0 - 3.0)


# ── Regime — Enum strict ───────────────────────────────────────────────────────


class TestRegime:
    def test_default_is_unknown(self):
        assert _make().regime is MarketRegime.UNKNOWN

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_all_enum_values_accepted(self, regime):
        assert _make(regime=regime).regime is regime

    def test_string_coercion_via_enum(self):
        # MarketRegime est un str-Enum : "trending" == MarketRegime.TRENDING
        assert MarketRegime("trending") is MarketRegime.TRENDING

    def test_invalid_string_rejected(self):
        with pytest.raises(ValueError):
            MarketRegime("trend")  # typo — rejeté par l'Enum

    def test_regime_queryable_as_string(self):
        e = _make(regime=MarketRegime.TRENDING)
        assert e.regime == "trending"  # utile pour les requêtes SQL / JSON


# ── Signal score — sans borne ─────────────────────────────────────────────────


class TestSignalScore:
    def test_default_is_none(self):
        assert _make().signal_score is None

    def test_score_0_to_100(self):
        assert _make(signal_score=75.0).signal_score == pytest.approx(75.0)

    def test_score_0_to_1_probability(self):
        assert _make(signal_score=0.82).signal_score == pytest.approx(0.82)

    def test_score_negative_allowed(self):
        # ex. z-score ou signal centré sur zéro
        assert _make(signal_score=-2.3).signal_score == pytest.approx(-2.3)

    def test_score_above_100_allowed(self):
        # le producteur définit l'échelle — aucune borne imposée
        assert _make(signal_score=142.0).signal_score == pytest.approx(142.0)
