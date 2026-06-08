"""
tests/test_dataset_validator.py — Invariants du DatasetValidator.

Vérifie que chaque règle d'intégrité est bien appliquée :
  - schema_version
  - complétude v2
  - NaN
  - plages de valeurs (RSI, ATR, bb_pct, range_pos)
  - conviction_level enum
  - cohérence DecisionContext ↔ champs legacy
"""

from __future__ import annotations

import math
import time

import pytest

from paper_trading.dataset_validator import (
    DatasetValidator,
    ValidationResult,
    validate_log,
)
from paper_trading.recorder import DecisionContext, MarketContext, TradeEvent

# ── Factories ─────────────────────────────────────────────────────────────────


def _event(
    event: str = "OPEN",
    trade_id: str = "t1",
    schema_version: int = 2,
    regime: str = "bull_trend",
    score: int = 75,
    market_context: MarketContext | None = None,
    decision_context: DecisionContext | None = None,
) -> TradeEvent:
    mc = market_context if market_context is not None else _valid_mc()
    dc = decision_context if decision_context is not None else _valid_dc()
    return TradeEvent(
        event=event,
        trade_id=trade_id,
        ts=time.time(),
        ts_iso="2026-06-06T12:00:00Z",
        symbol="BTC/USDT",
        side="buy",
        price=65000.0,
        size_usd=55.0,
        mode="futures_demo",
        schema_version=schema_version,
        regime=regime,
        score=score,
        market_context=mc if event == "OPEN" else None,
        decision_context=dc if event == "OPEN" else None,
    )


def _valid_mc(**overrides) -> MarketContext:
    base = dict(
        momentum=0.012,
        realized_volatility=0.003,
        trend_strength=0.7,
        avg_volume=1500.0,
        volume_ratio=1.4,
        atr=250.0,
        atr_ratio=0.004,
        rsi=42.1,
        rsi_oversold=False,
        rsi_overbought=False,
        ema20=62000.0,
        ema50=61000.0,
        ema_cross=0.016,
        ema_bullish=True,
        macd_line=120.0,
        macd_signal=100.0,
        macd_hist=20.0,
        macd_bullish=True,
        bb_pct=0.62,
        bb_squeeze=False,
        vwap_dist=0.008,
        range_pos=0.55,
    )
    base.update(overrides)
    return MarketContext(**base)


def _valid_dc(**overrides) -> DecisionContext:
    base = dict(
        score=75.0,
        conviction_level="HIGH",
        conviction_value=0.84,
        personality="momentum",
        regime="bull_trend",
    )
    base.update(overrides)
    return DecisionContext(**base)


_validator = DatasetValidator()


# ── 1. Schema version ─────────────────────────────────────────────────────────


def test_valid_schema_v1():
    evt = _event(schema_version=1, market_context=None, decision_context=None)
    # v1 n'exige pas market_context ni decision_context
    r = _validator.validate_event(evt)
    assert r.valid


def test_valid_schema_v2():
    r = _validator.validate_event(_event(schema_version=2))
    assert r.valid
    assert not r.violations


def test_invalid_schema_version():
    evt = _event(schema_version=99)
    r = _validator.validate_event(evt)
    assert not r.valid
    assert any("schema_version=99" in v for v in r.violations)


# ── 2. Complétude v2 ──────────────────────────────────────────────────────────


def test_v2_missing_market_context_is_violation():
    evt = _event(schema_version=2, market_context=None, decision_context=_valid_dc())
    # market_context=None injecté manuellement
    evt.market_context = None
    r = _validator.validate_event(evt)
    assert not r.valid
    assert any("market_context absent" in v for v in r.violations)


def test_v2_missing_decision_context_is_violation():
    evt = _event(schema_version=2, market_context=_valid_mc(), decision_context=None)
    evt.decision_context = None
    r = _validator.validate_event(evt)
    assert not r.valid
    assert any("decision_context absent" in v for v in r.violations)


def test_v2_close_event_no_context_required():
    evt = _event(
        event="CLOSE", schema_version=2, market_context=None, decision_context=None
    )
    r = _validator.validate_event(evt)
    assert r.valid, r.violations


# ── 3. NaN ────────────────────────────────────────────────────────────────────


def test_nan_in_price_is_violation():
    evt = _event()
    evt.price = float("nan")
    r = _validator.validate_event(evt)
    assert not r.valid
    assert any("price=NaN" in v for v in r.violations)


def test_nan_in_market_context_rsi():
    mc = _valid_mc(rsi=float("nan"))
    r = _validator.validate_event(_event(market_context=mc))
    assert not r.valid
    assert any("rsi=NaN" in v for v in r.violations)


def test_nan_in_decision_score():
    dc = _valid_dc(score=float("nan"))
    r = _validator.validate_event(_event(decision_context=dc))
    assert not r.valid
    assert any("decision_context.score=NaN" in v for v in r.violations)


def test_nan_in_conviction_value():
    dc = _valid_dc(conviction_value=float("nan"))
    r = _validator.validate_event(_event(decision_context=dc))
    assert not r.valid
    assert any("conviction_value=NaN" in v for v in r.violations)


# ── 4. Plages de valeurs — violations ────────────────────────────────────────


@pytest.mark.parametrize("rsi_val", [-1.0, 101.0, 150.0])
def test_rsi_out_of_range_is_violation(rsi_val):
    mc = _valid_mc(rsi=rsi_val)
    r = _validator.validate_event(_event(market_context=mc))
    assert not r.valid
    assert any("rsi=" in v and "hors" in v for v in r.violations)


def test_rsi_at_bounds_is_valid():
    for rsi in (0.0, 50.0, 100.0):
        mc = _valid_mc(rsi=rsi)
        r = _validator.validate_event(_event(market_context=mc))
        assert r.valid, f"RSI={rsi} devrait être valide"


def test_negative_atr_is_violation():
    mc = _valid_mc(atr=-1.0)
    r = _validator.validate_event(_event(market_context=mc))
    assert not r.valid
    assert any("atr=" in v and "négatif" in v for v in r.violations)


def test_negative_atr_ratio_is_violation():
    mc = _valid_mc(atr_ratio=-0.01)
    r = _validator.validate_event(_event(market_context=mc))
    assert not r.valid
    assert any("atr_ratio=" in v for v in r.violations)


def test_range_pos_out_of_bounds_is_violation():
    for bad in (-0.1, 1.01):
        mc = _valid_mc(range_pos=bad)
        r = _validator.validate_event(_event(market_context=mc))
        assert not r.valid, f"range_pos={bad} devrait être une violation"


def test_bb_pct_slightly_outside_is_warning_not_violation():
    # bb_pct peut légèrement dépasser [0,1] en marché extrême → warning seulement
    mc = _valid_mc(bb_pct=1.2)
    r = _validator.validate_event(_event(market_context=mc))
    assert r.valid  # pas une violation
    # pas de warning non plus (1.2 ∈ [-0.5, 1.5])


def test_bb_pct_very_extreme_is_violation():
    mc = _valid_mc(bb_pct=2.5)
    r = _validator.validate_event(_event(market_context=mc))
    assert not r.valid
    assert any("bb_pct=" in v for v in r.violations)


def test_volume_ratio_extremely_high_is_warning():
    mc = _valid_mc(volume_ratio=75.0)
    r = _validator.validate_event(_event(market_context=mc))
    assert r.valid  # pas une violation
    assert any("volume_ratio" in w for w in r.warnings)


# ── 5. DecisionContext — conviction_level ─────────────────────────────────────


@pytest.mark.parametrize("level", ["NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"])
def test_valid_conviction_levels(level):
    dc = _valid_dc(conviction_level=level)
    r = _validator.validate_event(_event(decision_context=dc))
    assert r.valid, f"conviction_level={level} devrait être valide"


def test_invalid_conviction_level_is_violation():
    dc = _valid_dc(conviction_level="ULTRA")
    r = _validator.validate_event(_event(decision_context=dc))
    assert not r.valid
    assert any("conviction_level" in v and "ULTRA" in v for v in r.violations)


def test_none_conviction_level_is_valid():
    dc = _valid_dc(conviction_level=None)
    r = _validator.validate_event(_event(decision_context=dc))
    assert r.valid


# ── 6. Cohérence DecisionContext ↔ champs legacy ─────────────────────────────


def test_regime_mismatch_is_warning():
    evt = _event(regime="sideways")
    evt.decision_context = _valid_dc(regime="bull_trend")
    r = _validator.validate_event(evt)
    assert r.valid  # warning, pas violation
    assert any("regime" in w and "incohérence" in w for w in r.warnings)


def test_regime_match_no_warning():
    evt = _event(regime="bull_trend")
    evt.decision_context = _valid_dc(regime="bull_trend")
    r = _validator.validate_event(evt)
    assert not any("régime" in w or "regime" in w for w in r.warnings)


def test_score_large_delta_is_warning():
    # event.score=75, dc.score=90 → delta=15 > 1 → warning
    evt = _event(score=75)
    evt.decision_context = _valid_dc(score=90.0)
    r = _validator.validate_event(evt)
    assert any("score" in w and "delta" in w for w in r.warnings)


def test_score_small_delta_no_warning():
    evt = _event(score=75)
    evt.decision_context = _valid_dc(score=75.5)
    r = _validator.validate_event(evt)
    assert not any("delta" in w for w in r.warnings)


# ── 7. ValidationResult helpers ───────────────────────────────────────────────


def test_validation_result_valid_report_contains_ok():
    r = ValidationResult(valid=True)
    assert "OK" in r.report()


def test_validation_result_invalid_report_contains_violation():
    r = ValidationResult(valid=False, violations=["rsi=NaN"])
    report = r.report()
    assert "VIOLATIONS" in report
    assert "rsi=NaN" in report


def test_validation_result_addition():
    r1 = ValidationResult(valid=True, violations=[], warnings=["w1"])
    r2 = ValidationResult(valid=False, violations=["v1"], warnings=[])
    merged = r1 + r2
    assert not merged.valid
    assert "v1" in merged.violations
    assert "w1" in merged.warnings


# ── 8. Batch et validate_log ─────────────────────────────────────────────────


def test_validate_batch_prefixes_trade_id():
    evt = _event(trade_id="abc123", schema_version=99)
    r = DatasetValidator().validate_batch([evt])
    assert not r.valid
    assert any("[abc123/OPEN]" in v for v in r.violations)


def test_validate_log_empty_file(tmp_path):
    log = str(tmp_path / "empty.jsonl")
    r = validate_log(log)
    assert r.valid
    assert any("Aucun événement" in w for w in r.warnings)


def test_validate_log_valid_file(tmp_path):
    from paper_trading.recorder import (
        DecisionContext,
        MarketContext,
        PaperTradeRecorder,
    )

    log = str(tmp_path / "trades.jsonl")
    rec = PaperTradeRecorder(log_path=log)
    mc = MarketContext.from_features(
        {
            "rsi": 45.0,
            "atr": 200.0,
            "atr_ratio": 0.003,
            "momentum": 0.01,
            "realized_volatility": 0.002,
            "trend_strength": 0.6,
            "avg_volume": 1000.0,
            "volume_ratio": 1.2,
            "ema20": 60000.0,
            "ema50": 59000.0,
            "ema_cross": 0.01,
            "ema_bullish": True,
            "macd_line": 50.0,
            "macd_signal": 40.0,
            "macd_hist": 10.0,
            "macd_bullish": True,
            "bb_pct": 0.5,
            "bb_squeeze": False,
            "vwap_dist": 0.005,
            "range_pos": 0.5,
        }
    )
    dc = DecisionContext(score=70.0, conviction_level="MEDIUM", regime="bull_trend")
    rec.record_open(
        "t1",
        "BTC/USDT",
        "buy",
        65000.0,
        55.0,
        regime="bull_trend",
        score=70,
        market_context=mc,
        decision_context=dc,
    )
    rec.record_close(
        "t1",
        exit_price=66000.0,
        pnl_usd=0.85,
        pnl_pct=0.015,
        reason="take_profit",
        opened_at=time.time() - 300,
    )
    r = validate_log(log)
    assert r.valid, r.report()
