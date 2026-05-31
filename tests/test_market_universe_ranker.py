"""
Tests MarketUniverseRanker — scoring heuristique sans exchange réel.
"""

from __future__ import annotations

from tools.market_universe_ranker import MarketUniverseRanker, RankEntry


def _ranker() -> MarketUniverseRanker:
    return MarketUniverseRanker(reader=None)


# ── rank() ────────────────────────────────────────────────────────────────────


def test_rank_returns_entries_for_all_symbols():
    r = _ranker()
    results = r.rank(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    assert len(results) == 3
    symbols = {e.symbol for e in results}
    assert symbols == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}


def test_rank_sorted_descending():
    r = _ranker()
    results = r.rank(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    scores = [e.score for e in results]
    assert scores == sorted(scores, reverse=True)


def test_rank_scores_between_0_and_100():
    r = _ranker()
    for entry in r.rank(["BTC/USDT", "XRP/USDT"]):
        assert 0 <= entry.score <= 100


def test_rank_top_n():
    r = _ranker()
    results = r.rank(["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"], top_n=2)
    assert len(results) == 2


def test_rank_details_have_all_keys():
    r = _ranker()
    entry = r.rank(["BTC/USDT"])[0]
    for key in (
        "volume",
        "liquidity",
        "spread",
        "volatility",
        "correlation",
        "reliability",
    ):
        assert key in entry.details


# ── Scoring corrélation ───────────────────────────────────────────────────────


def test_correlation_no_positions_gives_100():
    r = _ranker()
    score = r._score_correlation("BTC/USDT", [])
    assert score == 100.0


def test_correlation_same_symbol_penalized():
    r = _ranker()
    score_with = r._score_correlation("ETH/USDT", ["BTC/USDT"])
    assert score_with < 100.0


def test_correlation_uncorrelated_less_penalized():
    r = _ranker()
    score_btc_eth = r._score_correlation("ETH/USDT", ["BTC/USDT"])
    score_btc_xrp = r._score_correlation("XRP/USDT", ["BTC/USDT"])
    assert score_btc_xrp >= score_btc_eth


# ── Scoring volume ────────────────────────────────────────────────────────────


def test_volume_none_ticker_returns_fallback():
    r = _ranker()
    assert r._score_volume(None) == 50.0


def test_volume_zero_returns_zero():
    from infra.live_exchange_reader import Ticker

    r = _ranker()
    t = Ticker("X/USDT", 0, 0, 0, volume_24h=0, spread_pct=0)
    assert r._score_volume(t) == 0.0


def test_volume_large_gives_near_100():
    from infra.live_exchange_reader import Ticker

    r = _ranker()
    t = Ticker(
        "BTC/USDT", 50000, 50001, 50000, volume_24h=1_000_000_000, spread_pct=0.002
    )
    score = r._score_volume(t)
    assert score > 90.0


# ── Scoring spread ────────────────────────────────────────────────────────────


def test_spread_tight_gives_high_score():
    from infra.live_exchange_reader import OrderBook

    r = _ranker()
    ob = OrderBook("BTC/USDT", bids=[[50000.0, 1.0]], asks=[[50000.5, 1.0]])
    score = r._score_spread(None, ob)
    assert score > 80.0


def test_spread_wide_gives_low_score():
    from infra.live_exchange_reader import OrderBook

    r = _ranker()
    ob = OrderBook("X/USDT", bids=[[100.0, 1.0]], asks=[[100.5, 1.0]])
    score = r._score_spread(None, ob)
    assert score < 50.0


# ── Scoring volatilité ────────────────────────────────────────────────────────


def test_volatility_none_returns_fallback():
    r = _ranker()
    assert r._score_volatility(None) == 50.0


def test_volatility_stable_asset_low_score():
    r = _ranker()
    candles = [{"high": 100.1, "low": 99.9, "close": 100.0} for _ in range(10)]
    score = r._score_volatility(candles)
    assert score < 20.0


def test_volatility_volatile_asset_higher_score():
    r = _ranker()
    candles = [{"high": 110.0, "low": 90.0, "close": 100.0} for _ in range(10)]
    score = r._score_volatility(candles)
    assert score > 50.0


# ── RankEntry ─────────────────────────────────────────────────────────────────


def test_rank_entry_repr():
    e = RankEntry("BTC/USDT", 82.5)
    assert "BTC/USDT" in repr(e)
    assert "82.5" in repr(e)
