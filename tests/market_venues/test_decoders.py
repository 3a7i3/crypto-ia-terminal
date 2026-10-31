from decimal import Decimal
import json
import socket
import subprocess
from unittest.mock import patch
import pytest
from observability.market_venues.decoders import decode_snapshot, strict_json
from observability.market_venues.publication import build_publication
from observability.venue_quote_comparison import InstrumentKey, quote_metrics
from tests.market_venues.support import NOW, binding, decode, native, pilot, raw


@pytest.mark.parametrize(
    "venue",
    [
        "mexc",
        "bybit",
        "okx",
        "kraken",
        "bitfinex",
        "kucoin",
        "coinbase_exchange",
        "hyperliquid",
    ],
)
def test_eight_native_snapshots(venue):
    d = decode(binding(venue))
    assert (
        isinstance(d.quote.bid, Decimal)
        and d.quote.bid > 0
        and d.quote.ask > d.quote.bid
    )
    assert len(d.payload_sha256) == 64
    assert d.binding.native_symbol == d.quote.venue_symbol


def test_bitfinex_json_numbers_are_decoded_exactly():
    d = decode(
        binding("bitfinex"), b"[[100.123456789012345678901,2,1.25],[101.1,1,-2.5]]"
    )
    assert str(d.quote.bid) == "100.123456789012345678901"
    assert d.quote.bid_size_base == Decimal(
        "1.25"
    ) and d.quote.ask_size_base == Decimal("2.5")


@pytest.mark.parametrize("venue", ["mexc", "kraken", "bitfinex"])
def test_no_book_timestamp_is_invented(venue):
    d = decode(binding(venue))
    assert d.quote.observed_at is None
    assert (
        quote_metrics(d.quote, as_of=NOW, max_age_ms=5000)["status"] == "NOT_AVAILABLE"
    )


@pytest.mark.parametrize("venue", ["kucoin", "coinbase_exchange", "hyperliquid"])
def test_unspecified_native_time_is_preserved_but_not_qualified(venue):
    d = decode(binding(venue))
    assert d.quote.observed_at is not None and d.quote.timestamp_kind == "UNRESOLVED"
    assert (
        quote_metrics(d.quote, as_of=NOW, max_age_ms=5000)["reason"]
        == "UNRESOLVED_TIMESTAMP_KIND"
    )


def test_trade_price_is_never_substituted_for_kucoin_book():
    assert decode(binding("kucoin")).quote.bid == Decimal("100")


def test_explicit_request_identity_is_required():
    b = binding("bybit")
    with pytest.raises(ValueError, match="REQUEST_BINDING"):
        decode_snapshot(
            b,
            raw("bybit"),
            requested_symbol="ETHUSDT",
            requested_market_kind="SPOT",
            received_at=NOW,
            clock_id="clock",
            requested_category="spot",
        )


@pytest.mark.parametrize("venue", ["bybit", "hyperliquid"])
def test_native_symbol_echo_mismatch_is_refused(venue):
    with pytest.raises(ValueError, match="SYMBOL"):
        decode(binding(venue), raw(venue, symbol="WRONG"))


def test_kraken_result_key_is_not_a_ticker_alias_guess():
    with pytest.raises(ValueError, match="SYMBOL"):
        decode(binding("kraken"), raw("kraken", symbol="BTCUSD"))


def test_bybit_category_and_product_identity_are_both_required():
    b = binding("bybit")
    with pytest.raises(ValueError, match="CATEGORY"):
        decode_snapshot(
            b,
            raw("bybit"),
            requested_symbol=b.native_symbol,
            requested_market_kind="SPOT",
            received_at=NOW,
            clock_id="clock",
            requested_category="linear",
        )


def test_inverse_funding_and_raw_bitfinex_books_are_not_spot_snapshots():
    with pytest.raises(ValueError, match="FUNDING"):
        decode(binding("bitfinex", "fUSD"))
    with pytest.raises(ValueError, match="NON_SNAPSHOT"):
        decode(binding("bitfinex"), b"[[123456789,0,2]]")


def test_derivative_sizes_are_not_relabelled_as_base():
    ins = InstrumentKey("BTC", "USDT", "PERPETUAL_LINEAR", "USDT", "PERP")
    d = decode(binding("okx", "BTC-USDT-SWAP", ins))
    assert d.quote.bid_size_base is None and d.quote.ask_size_base is None


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"{"])
def test_malformed_duplicate_or_nonfinite_native_json_refused(payload):
    with pytest.raises(ValueError):
        strict_json(payload)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "1e1000"])
def test_invalid_price_is_not_zero_or_a_missing_side(value):
    doc = native("mexc")
    doc["bids"][0][0] = value
    with pytest.raises(ValueError):
        decode(binding("mexc"), json.dumps(doc).encode())


def test_boolean_error_code_not_admitted_as_zero():
    doc = native("bybit")
    doc["retCode"] = False
    with pytest.raises(ValueError):
        decode(binding("bybit"), json.dumps(doc).encode())


def test_duplicate_snapshot_price_level_is_not_silently_chosen():
    doc = native("mexc")
    doc["bids"].append(["100.1", "4"])
    with pytest.raises(ValueError, match="DUPLICATE"):
        decode(binding("mexc"), json.dumps(doc).encode())


def test_empty_book_preserves_missing_not_zero():
    doc = native("mexc")
    doc["bids"] = []
    assert decode(binding("mexc"), json.dumps(doc).encode()).quote.bid is None


def test_pure_pipeline_has_no_file_network_or_subprocess_effects():
    bindings, observations = pilot()
    with (
        patch.object(socket, "socket", side_effect=AssertionError("network")),
        patch.object(subprocess, "Popen", side_effect=AssertionError("process")),
        patch("builtins.open", side_effect=AssertionError("file")),
    ):
        doc = build_publication(
            bindings,
            observations,
            as_of=NOW,
            max_age_ms=5000,
            max_skew_ms=100,
            evidence_kind="SYNTHETIC",
        )
    assert doc["execution_authority"] is False
