"""Tests du module symbol_stability — scoring OHLCV + classement de tradabilité."""

from __future__ import annotations

from datetime import datetime, timezone

from quant_hedge_ai.agents.market.symbol_stability import (
    SYMBOL_TIERS,
    compute_stability,
    sort_by_tradability,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _candle(close: float, pct_body: float = 0.6, vol: float = 100_000.0) -> dict:
    """Construit une bougie synthétique avec une structure contrôlée."""
    rng = close * 0.01
    body = rng * pct_body
    open_ = close - body / 2
    high = close + rng * (1 - pct_body) / 2
    low = open_ - rng * (1 - pct_body) / 2
    return {
        "symbol": "TEST/USDT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open": round(open_, 6),
        "close": round(close, 6),
        "high": round(high, 6),
        "low": round(low, 6),
        "volume": vol,
        "source": "synthetic",
    }


def _trending_series(
    n: int = 50, start: float = 100.0, step: float = 0.5
) -> list[dict]:
    """Série avec tendance haussière claire et bougies propres."""
    return [_candle(start + i * step, pct_body=0.70) for i in range(n)]


def _ranging_series(n: int = 50, center: float = 100.0) -> list[dict]:
    """Série oscillant autour d'un centre — pas de tendance."""
    import random

    random.seed(42)
    series = []
    price = center
    for _ in range(n):
        price = center + random.uniform(-2, 2)
        series.append(_candle(price, pct_body=0.30))
    return series


def _noisy_series(n: int = 50, start: float = 100.0) -> list[dict]:
    """Série avec forte volatilité et bougies pleines de mèches."""
    import random

    random.seed(7)
    series = []
    price = start
    for _ in range(n):
        price *= 1 + random.gauss(0, 0.05)  # 5% std par bougie = très volatile
        price = max(price, 1.0)
        series.append(_candle(price, pct_body=0.15))
    return series


# ── Tests compute_stability ───────────────────────────────────────────────────


def test_stability_returns_all_keys():
    series = _trending_series()
    result = compute_stability(series, "BTC/USDT")
    expected_keys = {
        "score",
        "tier",
        "regime",
        "body_ratio",
        "vol_cv",
        "atr_pct",
        "trend_r2",
        "n_candles",
    }
    assert expected_keys == set(result.keys())


def test_trending_series_has_high_score_and_trending_regime():
    series = _trending_series(50)
    st = compute_stability(series, "BTC/USDT")
    assert st["score"] >= 55, f"score={st['score']} trop faible pour série tendancielle"
    assert st["regime"] in ("trending", "directional")
    assert st["trend_r2"] > 0.70


def test_ranging_series_has_ranging_regime():
    series = _ranging_series(50)
    st = compute_stability(series)
    assert st["regime"] in ("ranging", "flat")


def test_noisy_series_has_low_score():
    series = _noisy_series(50)
    st = compute_stability(series)
    # Série très volatile avec mèches → score bas et régime noisy ou ranging
    assert st["score"] < 60
    assert st["regime"] in ("noisy", "ranging", "directional")


def test_empty_series_returns_zero_score():
    st = compute_stability([], "ETH/USDT")
    assert st["score"] == 0.0
    assert st["regime"] == "flat"


def test_short_series_does_not_crash():
    series = _trending_series(3)
    st = compute_stability(series)
    assert 0.0 <= st["score"] <= 100.0


def test_tier_lookup_known_symbol():
    st = compute_stability(_trending_series(), "BTC/USDT")
    assert st["tier"] == 1

    st_defi = compute_stability(_trending_series(), "LINK/USDT")
    assert st_defi["tier"] == 3


def test_tier_unknown_symbol_defaults_to_6():
    st = compute_stability(_trending_series(), "UNKNOWN/USDT")
    assert st["tier"] == 6


def test_body_ratio_is_clamped_0_1():
    series = _trending_series(30)
    st = compute_stability(series)
    assert 0.0 <= st["body_ratio"] <= 1.0


def test_atr_pct_is_positive_for_real_data():
    series = _trending_series(30)
    st = compute_stability(series)
    assert st["atr_pct"] >= 0.0


def test_n_candles_capped_at_50():
    series = _trending_series(100)
    st = compute_stability(series)
    assert st["n_candles"] == 50  # fenêtre interne = 50 dernières bougies


def test_score_between_0_and_100():
    for gen in [_trending_series, _ranging_series, _noisy_series]:
        st = compute_stability(gen())
        assert (
            0.0 <= st["score"] <= 100.0
        ), f"score={st['score']} hors [0,100] pour {gen.__name__}"


def test_consistent_volume_gives_better_score_than_erratic():
    """Même série de prix, volume stable vs erratique → score plus haut."""
    base = _trending_series(50)

    # Volume stable
    stable = [{**c, "volume": 100_000.0} for c in base]
    st_stable = compute_stability(stable)

    # Volume erratique (très fort CV)
    import random

    random.seed(99)
    erratic = [{**c, "volume": random.uniform(100, 10_000_000)} for c in base]
    st_erratic = compute_stability(erratic)

    assert st_stable["score"] > st_erratic["score"]
    assert st_stable["vol_cv"] < st_erratic["vol_cv"]


# ── Tests sort_by_tradability ─────────────────────────────────────────────────


def test_sort_orders_by_score_descending():
    stab_map = {
        "BTC/USDT": {
            "score": 80.0,
            "tier": 1,
            "regime": "trending",
            "body_ratio": 0.7,
            "vol_cv": 0.5,
            "atr_pct": 1.2,
            "trend_r2": 0.85,
            "n_candles": 50,
        },
        "PEPE/USDT": {
            "score": 30.0,
            "tier": 5,
            "regime": "noisy",
            "body_ratio": 0.2,
            "vol_cv": 1.8,
            "atr_pct": 6.0,
            "trend_r2": 0.10,
            "n_candles": 50,
        },
        "ETH/USDT": {
            "score": 70.0,
            "tier": 1,
            "regime": "directional",
            "body_ratio": 0.6,
            "vol_cv": 0.6,
            "atr_pct": 1.5,
            "trend_r2": 0.60,
            "n_candles": 50,
        },
    }
    result = sort_by_tradability(["BTC/USDT", "ETH/USDT", "PEPE/USDT"], stab_map)
    assert result == ["BTC/USDT", "ETH/USDT", "PEPE/USDT"]


def test_sort_uses_tier_as_tiebreaker():
    stab_map = {
        "LINK/USDT": {
            "score": 65.0,
            "tier": 3,
            "regime": "trending",
            "body_ratio": 0.6,
            "vol_cv": 0.5,
            "atr_pct": 1.0,
            "trend_r2": 0.7,
            "n_candles": 50,
        },
        "BTC/USDT": {
            "score": 65.0,
            "tier": 1,
            "regime": "trending",
            "body_ratio": 0.6,
            "vol_cv": 0.5,
            "atr_pct": 1.0,
            "trend_r2": 0.7,
            "n_candles": 50,
        },
    }
    result = sort_by_tradability(["LINK/USDT", "BTC/USDT"], stab_map)
    # Même score → tier bas (Tier 1) en premier
    assert result[0] == "BTC/USDT"


def test_sort_unknown_symbols_placed_last():
    stab_map = {
        "BTC/USDT": {
            "score": 75.0,
            "tier": 1,
            "regime": "trending",
            "body_ratio": 0.7,
            "vol_cv": 0.4,
            "atr_pct": 1.0,
            "trend_r2": 0.8,
            "n_candles": 50,
        },
    }
    result = sort_by_tradability(
        ["UNKNOWN/USDT", "BTC/USDT", "ALSO_UNKNOWN/USDT"], stab_map
    )
    assert result[0] == "BTC/USDT"


def test_sort_empty_list():
    assert sort_by_tradability([], {}) == []


def test_sort_preserves_all_symbols():
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    result = sort_by_tradability(symbols, {})
    assert set(result) == set(symbols)


# ── Tests SYMBOL_TIERS ────────────────────────────────────────────────────────


def test_symbol_tiers_covers_all_50_default_symbols():
    from core.advisor_loop import SYMBOLS_DEFAULT

    missing = [s for s in SYMBOLS_DEFAULT if s not in SYMBOL_TIERS]
    assert not missing, f"Symboles sans tier: {missing}"
