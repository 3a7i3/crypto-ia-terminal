from __future__ import annotations

import math

import pytest

from core.universe_certification import (
    UniverseIssue,
    certify_universe,
)


def _swap_market(
    symbol: str,
    *,
    active: bool | None = True,
    market_type: str | None = "swap",
) -> dict:
    market = {
        "symbol": symbol,
        "base": symbol.split("/", 1)[0],
        "quote": symbol.split("/", 1)[1].split(":", 1)[0],
    }
    if active is not None:
        market["active"] = active
    if market_type is not None:
        market["type"] = market_type
        market[market_type] = True
    return market


def _ticker(symbol: str, last: object = 100.0, **extra: object) -> dict:
    return {"symbol": symbol, "last": last, **extra}


def test_all_valid_pinned_symbols_certify_fail_closed_contract() -> None:
    markets = {
        "BTC/USDT:USDT": _swap_market("BTC/USDT:USDT"),
        "ETH/USDT:USDT": _swap_market("ETH/USDT:USDT"),
    }
    tickers = {
        "BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0),
        "ETH/USDT:USDT": _ticker("ETH/USDT:USDT", 3200.0),
    }

    cert = certify_universe(
        ["BTC/USDT", "ETH/USDT"],
        markets=markets,
        tickers=tickers,
        exchange="mexc",
    )

    assert cert.is_certified is True
    assert cert.configured_count == 2
    assert cert.validated_count == 2
    assert cert.rejected_count == 0
    assert cert.validated_symbols == ("BTC/USDT", "ETH/USDT")
    assert cert.symbol_results[0].market_symbol == "BTC/USDT:USDT"
    assert cert.symbol_results[0].last_price == 64000.0


def test_one_invalid_symbol_makes_whole_universe_uncertified() -> None:
    markets = {
        "BTC/USDT:USDT": _swap_market("BTC/USDT:USDT"),
    }
    tickers = {
        "BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0),
    }

    cert = certify_universe(
        ["BTC/USDT", "MISSING/USDT"],
        markets=markets,
        tickers=tickers,
        exchange="mexc",
    )

    assert cert.is_certified is False
    assert cert.configured_count == 2
    assert cert.validated_count == 1
    assert cert.rejected_count == 1
    assert cert.validated_symbols == ("BTC/USDT",)
    assert cert.symbol_results[1].issues == (UniverseIssue.MARKET_MISSING,)


def test_spot_only_symbol_is_market_type_mismatch() -> None:
    markets = {
        "BTC/USDT": {
            "symbol": "BTC/USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        }
    }
    tickers = {"BTC/USDT": _ticker("BTC/USDT", 64000.0)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.MARKET_TYPE_MISMATCH,)
    assert cert.symbol_results[0].market_type == "spot"


def test_explicitly_inactive_derivative_is_rejected() -> None:
    markets = {
        "BTC/USDT:USDT": _swap_market("BTC/USDT:USDT", active=False),
    }
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.MARKET_INACTIVE,)


def test_missing_active_flag_is_not_treated_as_inactive() -> None:
    markets = {
        "BTC/USDT:USDT": _swap_market("BTC/USDT:USDT", active=None),
    }
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is True


@pytest.mark.parametrize("last", [0, -1, None, float("nan"), float("inf"), True])
def test_non_positive_or_non_finite_last_price_is_rejected(last: object) -> None:
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", last)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.LAST_PRICE_INVALID,)


def test_missing_ticker_is_rejected() -> None:
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers={}, exchange="mexc"
    )

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.TICKER_MISSING,)


def test_duplicate_configured_symbol_is_rejected_not_silently_deduplicated() -> None:
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0)}

    cert = certify_universe(
        ["btc/usdt", "BTC/USDT:USDT"],
        markets=markets,
        tickers=tickers,
        exchange="mexc",
    )

    assert cert.is_certified is False
    assert cert.configured_count == 2
    assert cert.validated_count == 1
    assert cert.symbol_results[0].normalized_symbol == "BTC/USDT"
    assert cert.symbol_results[1].issues == (UniverseIssue.DUPLICATE_SYMBOL,)


def test_unsupported_quote_is_rejected_before_market_evidence() -> None:
    cert = certify_universe(
        ["BTC/EUR"], markets={}, tickers={}, exchange="mexc"
    )

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.QUOTE_NOT_ALLOWED,)


@pytest.mark.parametrize("symbol", ["", "BTCUSDT", "BTC/", "/USDT", "BTC/USDT/USDC"])
def test_invalid_symbol_syntax_is_rejected(symbol: str) -> None:
    cert = certify_universe([symbol], markets={}, tickers={}, exchange="mexc")

    assert cert.is_certified is False
    assert cert.symbol_results[0].issues == (UniverseIssue.INVALID_SYMBOL,)


def test_empty_configured_universe_is_never_certified() -> None:
    cert = certify_universe([], markets={}, tickers={}, exchange="mexc")

    assert cert.is_certified is False
    assert cert.configured_count == 0
    assert cert.issues == (UniverseIssue.EMPTY_UNIVERSE,)


def test_swap_boolean_is_accepted_when_market_type_field_is_absent() -> None:
    market = _swap_market("BTC/USDT:USDT", market_type=None)
    market["swap"] = True
    markets = {"BTC/USDT:USDT": market}
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is True
    assert cert.symbol_results[0].market_type == "swap"


def test_liquidity_spread_and_volume_are_not_certification_gates() -> None:
    """OPS-C certifies measurability, not ranker/strategy quality."""
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}
    tickers = {
        "BTC/USDT:USDT": _ticker(
            "BTC/USDT:USDT",
            64000.0,
            bid=0,
            ask=0,
            quoteVolume=0,
            baseVolume=0,
        )
    }

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is True


def test_selected_derivative_ticker_is_not_replaced_by_spot_ticker() -> None:
    markets = {
        "BTC/USDT": {
            "symbol": "BTC/USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        "BTC/USDT:USDT": _swap_market("BTC/USDT:USDT"),
    }
    tickers = {
        "BTC/USDT": _ticker("BTC/USDT", 64000.0),
        "BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 63950.0),
    }

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is True
    assert cert.symbol_results[0].market_symbol == "BTC/USDT:USDT"
    assert cert.symbol_results[0].last_price == 63950.0


def test_ticker_can_be_found_by_embedded_market_symbol() -> None:
    markets = {"MEXC_INTERNAL_ID": _swap_market("BTC/USDT:USDT")}
    tickers = {
        "OTHER_INTERNAL_ID": _ticker("BTC/USDT:USDT", 64000.0),
    }

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert cert.is_certified is True


def test_evidence_hash_is_deterministic_and_payload_is_serializable() -> None:
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", 64000.0)}

    first = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )
    second = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    assert first.evidence_sha256 == second.evidence_sha256
    assert len(first.evidence_sha256) == 64
    payload = first.to_dict()
    assert payload["is_certified"] is True
    assert payload["configured_count"] == 1
    assert payload["validated_count"] == 1
    assert payload["evidence_sha256"] == first.evidence_sha256


def test_nan_is_never_leaked_into_serializable_evidence() -> None:
    markets = {"BTC/USDT:USDT": _swap_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _ticker("BTC/USDT:USDT", math.nan)}

    cert = certify_universe(
        ["BTC/USDT"], markets=markets, tickers=tickers, exchange="mexc"
    )

    payload = cert.to_dict()
    assert payload["symbols"][0]["last_price"] is None
    assert payload["symbols"][0]["issues"] == ["last_price_invalid"]
