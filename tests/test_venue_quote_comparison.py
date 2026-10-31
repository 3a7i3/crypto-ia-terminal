from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from observability.venue_quote_comparison import InstrumentKey, Quote, compare_quotes, quote_metrics

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
BTC_USDT = InstrumentKey("bitcoin:native", "tether:USDT", "SPOT", "tether:USDT", "SPOT")


def quote(venue="mexc", **changes):
    doc = Quote(
        venue=venue, venue_symbol="BTC/USDT", instrument=BTC_USDT,
        bid="99", ask="101", observed_at=NOW - timedelta(milliseconds=100),
        received_at=NOW - timedelta(milliseconds=50),
        observer_clock_id="fixture-clock", timestamp_kind="BOOK_PUBLICATION", book_state="SNAPSHOT",
        bid_size_base="2", ask_size_base="3",
    )
    return replace(doc, **changes)


def compare(a, b, **policy):
    return compare_quotes(a, b, as_of=NOW, max_age_ms=policy.get("max_age_ms", 1000),
                          max_skew_ms=policy.get("max_skew_ms", 250))


def test_internal_spread_is_distinct_from_cross_venue_price_basis_and_gross_gap():
    a = quote()
    b = quote("bybit", bid="102", ask="104", bid_size_base="1")
    result = compare(a, b)
    assert result["status"] == "AVAILABLE"
    assert result["reference"]["mid"] == "100"
    assert result["reference"]["spread_bps"] == "200.00000000"
    assert result["mid_basis_bps"] == "300.00000000"
    assert result["buy_reference_sell_other_gross_bps"] == "99.00990099"
    assert result["buy_other_sell_reference_gross_bps"] == "-480.76923077"
    assert result["buy_reference_sell_other_top_size_base"] == "1"
    assert result["costs_funding_fx_included"] is False
    assert result["execution_authority"] is False
    assert "trade_allowed" not in result


@pytest.mark.parametrize("instrument", [
    replace(BTC_USDT, quote_asset_id="fiat:USD", settlement_asset_id="fiat:USD"),
    replace(BTC_USDT, quote_asset_id="circle:USDC", settlement_asset_id="circle:USDC"),
    replace(BTC_USDT, base_asset_id="hypercore:UBTC"),
    replace(BTC_USDT, market_kind="PERPETUAL_LINEAR", contract_identity="linear-perpetual"),
    replace(BTC_USDT, market_kind="PERPETUAL_INVERSE", contract_identity="inverse-perpetual"),
    replace(BTC_USDT, market_kind="FUTURE_LINEAR", contract_identity="expiry:2026-12-25"),
])
def test_similar_display_ticker_cannot_make_different_products_comparable(instrument):
    result = compare(quote(), quote("okx", instrument=instrument))
    assert result["status"] == "NOT_AVAILABLE"
    assert result["reason"] == "DIFFERENT_INSTRUMENT"
    assert result["mid_basis_bps"] is None


@pytest.mark.parametrize("changes,reason", [
    ({"bid": None}, "MISSING_OR_INVALID_SIDE"),
    ({"venue": "UNKNOWN"}, "MISSING_VENUE"),
    ({"venue": "MEXC"}, "NONCANONICAL_VENUE"),
    ({"venue_symbol": ""}, "MISSING_VENUE_SYMBOL"),
    ({"timestamp_kind": "LAST_TRADE"}, "UNRESOLVED_TIMESTAMP_KIND"),
    ({"ask": "0"}, "MISSING_OR_INVALID_SIDE"),
    ({"bid": True}, "MISSING_OR_INVALID_SIDE"),
    ({"bid": 99.5}, "MISSING_OR_INVALID_SIDE"),
    ({"ask": "NaN"}, "MISSING_OR_INVALID_SIDE"),
    ({"ask": "Infinity"}, "MISSING_OR_INVALID_SIDE"),
    ({"bid": "105", "ask": "101"}, "CROSSED_BOOK"),
    ({"observed_at": None}, "MISSING_EXCHANGE_TIMESTAMP"),
    ({"observed_at": NOW.replace(tzinfo=None)}, "MISSING_EXCHANGE_TIMESTAMP"),
    ({"received_at": NOW.replace(tzinfo=None)}, "MISSING_RECEIPT_TIMESTAMP"),
    ({"observer_clock_id": ""}, "UNRESOLVED_OBSERVER_CLOCK"),
    ({"observed_at": NOW + timedelta(seconds=1)}, "FUTURE_OR_INCONSISTENT_CLOCK"),
    ({"received_at": NOW + timedelta(seconds=1)}, "FUTURE_OR_INCONSISTENT_CLOCK"),
    ({"observed_at": NOW - timedelta(seconds=2)}, "STALE"),
    ({"book_state": "DELTA_WITH_GAP"}, "BOOK_NOT_SYNCHRONIZED"),
    ({"bid_size_base": "0"}, "INVALID_BASE_SIZE"),
    ({"ask_size_base": "-1"}, "INVALID_BASE_SIZE"),
    ({"instrument": replace(BTC_USDT, base_asset_id="UNKNOWN")}, "UNRESOLVED_INSTRUMENT"),
])
def test_invalid_or_missing_evidence_remains_unavailable(changes, reason):
    result = compare(quote(), replace(quote("kraken"), **changes))
    assert result["status"] == "NOT_AVAILABLE"
    assert result["reason"] == "QUOTE_UNAVAILABLE"
    assert result["other"]["reason"] == reason
    assert result["mid_basis_bps"] is None
    assert result["buy_reference_sell_other_gross_bps"] is None


def test_receive_time_cannot_stand_in_for_exchange_event_time():
    result = quote_metrics(quote(observed_at=None, received_at=NOW), as_of=NOW, max_age_ms=1000)
    assert result["reason"] == "MISSING_EXCHANGE_TIMESTAMP"
    assert result["spread_bps"] is None


def test_pair_requires_synced_events_and_same_observer_clock():
    b = quote("kucoin", observed_at=NOW - timedelta(milliseconds=900))
    assert compare(quote(), b)["reason"] == "EVENTS_NOT_SYNCHRONIZED"
    b = quote("kucoin", observer_clock_id="other-unsynchronised-host")
    assert compare(quote(), b)["reason"] == "OBSERVER_CLOCKS_NOT_ALIGNED"
    assert compare(quote(), quote())["reason"] == "SAME_VENUE"
    assert compare(quote(), quote("bybit", timestamp_kind="MATCHING_ENGINE"))["reason"] == "TIMESTAMP_KINDS_DIFFER"


def test_locked_book_zero_spread_is_real_but_missing_size_stays_unknown():
    a = quote(bid="100", ask="100", bid_size_base=None)
    result = compare(a, quote("coinbase", ask_size_base=None))
    assert result["reference"]["spread_bps"] == "0.00000000"
    assert result["buy_other_sell_reference_top_size_base"] is None
    assert result["status"] == "AVAILABLE"


def test_decimal_small_prices_and_offsets_keep_units_and_time_meaning():
    a = quote(bid=Decimal("0.00000001"), ask=Decimal("0.00000002"))
    b = quote("bitfinex", bid="0.00000002", ask="0.00000003",
              observed_at=a.observed_at.astimezone(timezone(timedelta(hours=2))))
    result = compare(a, b)
    assert result["event_skew_ms"] == "0"
    assert result["mid_basis_bps"] == "6666.66666667"


@pytest.mark.parametrize("policy", [{"max_age_ms": -1}, {"max_age_ms": True}, {"max_skew_ms": -1}, {"max_skew_ms": None}])
def test_quality_policy_is_explicit_and_not_a_trading_threshold(policy):
    with pytest.raises(ValueError):
        compare(quote(), quote("bybit"), **policy)
