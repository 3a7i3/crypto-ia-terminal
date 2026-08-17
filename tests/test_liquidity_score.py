"""
tests/test_liquidity_score.py — Suite deterministe pour l'indicateur unique
de liquidite (market_data/metrics/liquidity.py).

Ces tests garantissent :
  1. Bornes strictes du score dans [0, 100]
  2. Monotonie (book plus liquide => score plus haut)
  3. Symetrie buy/sell sur book equilibre
  4. Gestion propre du book vide / degenere
  5. Coherence des tiers ("excellent" | ... | "toxic" | "empty")
  6. Le poids total doit valoir 1.0 (garde-fou config)
"""

from __future__ import annotations

import math

import pytest

from market_data.metrics.liquidity import (
    DEFAULT_CONFIG,
    LiquidityConfig,
    liquidity_score,
)
from market_data.models import NormalizedOrderBook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _book(bids, asks, *, symbol: str = "BTCUSDT", ts: int = 1000) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="binance",
        symbol=symbol,
        timestamp_ms=ts,
        bids=bids,
        asks=asks,
    )


@pytest.fixture
def book_deep():
    """Book profond, spread serre, equilibre : score attendu tres eleve."""
    bids = [(100.0 - i * 0.01, 5000.0) for i in range(20)]
    asks = [(100.01 + i * 0.01, 5000.0) for i in range(20)]
    return _book(bids, asks)


@pytest.fixture
def book_thin():
    """Spread large et depth mince : score bas."""
    bids = [(100.0, 1.0), (99.0, 1.0)]
    asks = [(101.5, 1.0), (103.0, 1.0)]
    return _book(bids, asks)


@pytest.fixture
def book_empty():
    return _book([], [])


@pytest.fixture
def book_one_sided():
    """Que des bids, aucun ask : imbalance = +1, degenere."""
    return _book([(100.0, 100.0)], [])


@pytest.fixture
def book_medium():
    bids = [(100.0 - i * 0.05, 500.0) for i in range(10)]
    asks = [(100.10 + i * 0.05, 500.0) for i in range(10)]
    return _book(bids, asks)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        LiquidityConfig(w_tightness=0.5, w_depth=0.5, w_resilience=0.5, w_balance=0.5)


def test_default_config_weights_valid():
    total = (
        DEFAULT_CONFIG.w_tightness
        + DEFAULT_CONFIG.w_depth
        + DEFAULT_CONFIG.w_resilience
        + DEFAULT_CONFIG.w_balance
    )
    assert math.isclose(total, 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Bornes et tiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    ["book_deep", "book_thin", "book_medium", "book_one_sided", "book_empty"],
)
def test_score_within_bounds(fixture_name, request):
    book = request.getfixturevalue(fixture_name)
    snap = liquidity_score(book)
    assert 0.0 <= snap.score <= 100.0
    assert 0.0 <= snap.tightness <= 1.0
    assert 0.0 <= snap.depth <= 1.0
    assert 0.0 <= snap.resilience <= 1.0
    assert 0.0 <= snap.balance <= 1.0


def test_empty_book_returns_empty_tier(book_empty):
    snap = liquidity_score(book_empty)
    assert snap.tier == "empty"
    assert snap.score == 0.0
    assert not snap.filled_buy
    assert not snap.filled_sell


def test_one_sided_book_is_toxic(book_one_sided):
    snap = liquidity_score(book_one_sided)
    # pas de best_ask -> spread_bps None -> traite comme empty
    assert snap.tier == "empty"


# ---------------------------------------------------------------------------
# Monotonie
# ---------------------------------------------------------------------------


def test_deep_book_scores_higher_than_thin(book_deep, book_thin):
    deep = liquidity_score(book_deep)
    thin = liquidity_score(book_thin)
    assert deep.score > thin.score
    assert deep.tier in ("excellent", "healthy")
    assert thin.tier in ("thin", "fragile", "toxic")


def test_deep_book_dominates_medium(book_deep, book_medium):
    deep = liquidity_score(book_deep)
    med = liquidity_score(book_medium)
    assert deep.score >= med.score


# ---------------------------------------------------------------------------
# Symetrie et slippage
# ---------------------------------------------------------------------------


def test_symmetric_book_has_symmetric_slippage(book_deep):
    snap = liquidity_score(book_deep)
    assert math.isclose(snap.slippage_buy_bps, snap.slippage_sell_bps, rel_tol=1e-3)
    # book quasi-symetrique : imbalance tolere le 1er niveau desaligne (spread)
    assert abs(snap.imbalance) < 1e-3


def test_deep_book_absorbs_notional(book_deep):
    snap = liquidity_score(book_deep)
    assert snap.filled_buy is True
    assert snap.filled_sell is True


def test_thin_book_may_fail_to_fill():
    """Book insuffisant pour un test 10k USD -> resilience plafonnee."""
    book = _book([(100.0, 0.5)], [(100.5, 0.5)])
    snap = liquidity_score(book)
    assert not (snap.filled_buy and snap.filled_sell)
    assert snap.resilience <= 0.15


# ---------------------------------------------------------------------------
# Imbalance -> balance
# ---------------------------------------------------------------------------


def test_bid_heavy_book_penalises_balance():
    bids = [(100.0, 100.0), (99.9, 100.0)]
    asks = [(100.1, 5.0), (100.2, 5.0)]
    snap = liquidity_score(_book(bids, asks))
    assert snap.imbalance > 0.5
    assert snap.balance < 0.5


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_snapshot_as_dict_is_json_serialisable(book_deep):
    import json

    snap = liquidity_score(book_deep)
    d = snap.as_dict()
    # inf -> non-JSON-safe : on remplace avant serialisation
    text = json.dumps(d, default=lambda o: None, allow_nan=False)
    assert "score" in text
    assert "tier" in text


# ---------------------------------------------------------------------------
# Configuration personnalisee
# ---------------------------------------------------------------------------


def test_custom_config_changes_score(book_medium):
    cfg = LiquidityConfig(
        w_tightness=0.10,
        w_depth=0.10,
        w_resilience=0.10,
        w_balance=0.70,
        depth_ref_usd=10_000.0,
    )
    default = liquidity_score(book_medium)
    custom = liquidity_score(book_medium, cfg)
    assert default.score != custom.score
