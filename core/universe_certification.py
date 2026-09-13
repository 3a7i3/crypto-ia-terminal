"""Pure certification core for a pinned PAPER/F-00 market universe.

OPS-C / MARKET-UNIVERSE-01.

This module deliberately performs no network, filesystem, environment, trading,
or persistence work.  It certifies an operator-configured universe against
already-fetched CCXT-like ``markets`` and ``tickers`` mappings.  Runtime wiring
is intentionally a separate step.

Scientific contract:

* configured universe != validated universe != scan results;
* one invalid configured symbol makes the whole certification fail closed;
* existence/type/activity/positive-price are measurement prerequisites;
* liquidity, spread, ranking and strategy quality are NOT certification gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "ops-c-universe-certification-v1"
_DEFAULT_QUOTES = ("USDT", "USDC")
_DEFAULT_MARKET_TYPES = ("swap", "future")


class UniverseIssue(str, Enum):
    """Stable fail-closed reason codes for universe certification."""

    EMPTY_UNIVERSE = "empty_universe"
    INVALID_SYMBOL = "invalid_symbol"
    QUOTE_NOT_ALLOWED = "quote_not_allowed"
    DUPLICATE_SYMBOL = "duplicate_symbol"
    MARKET_MISSING = "market_missing"
    MARKET_TYPE_MISMATCH = "market_type_mismatch"
    MARKET_INACTIVE = "market_inactive"
    TICKER_MISSING = "ticker_missing"
    LAST_PRICE_INVALID = "last_price_invalid"


@dataclass(frozen=True)
class SymbolCertification:
    """Certification evidence for one configured symbol."""

    configured_symbol: str
    normalized_symbol: str | None
    valid: bool
    issues: tuple[UniverseIssue, ...]
    market_symbol: str | None = None
    market_type: str | None = None
    last_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured_symbol": self.configured_symbol,
            "normalized_symbol": self.normalized_symbol,
            "valid": self.valid,
            "issues": [issue.value for issue in self.issues],
            "market_symbol": self.market_symbol,
            "market_type": self.market_type,
            "last_price": self.last_price,
        }


@dataclass(frozen=True)
class UniverseCertification:
    """Deterministic certification result for one configured universe."""

    exchange: str
    configured_symbols: tuple[str, ...]
    validated_symbols: tuple[str, ...]
    symbol_results: tuple[SymbolCertification, ...]
    issues: tuple[UniverseIssue, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def configured_count(self) -> int:
        return len(self.configured_symbols)

    @property
    def validated_count(self) -> int:
        return len(self.validated_symbols)

    @property
    def rejected_count(self) -> int:
        return sum(1 for result in self.symbol_results if not result.valid)

    @property
    def is_certified(self) -> bool:
        """Fail closed: every configured symbol must be independently valid."""
        return (
            self.configured_count > 0
            and not self.issues
            and self.rejected_count == 0
            and self.validated_count == self.configured_count
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "exchange": self.exchange,
            "is_certified": self.is_certified,
            "configured_count": self.configured_count,
            "validated_count": self.validated_count,
            "rejected_count": self.rejected_count,
            "configured_symbols": list(self.configured_symbols),
            "validated_symbols": list(self.validated_symbols),
            "issues": [issue.value for issue in self.issues],
            "symbols": [result.to_dict() for result in self.symbol_results],
        }

    @property
    def evidence_sha256(self) -> str:
        """Stable content hash suitable for a later certification artifact."""
        raw = json.dumps(
            self._payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["evidence_sha256"] = self.evidence_sha256
        return payload


def _normalize_symbol(symbol: str) -> tuple[str, str] | None:
    """Return ``(BASE/QUOTE, QUOTE)`` for a CCXT-like symbol."""
    if not isinstance(symbol, str):
        return None
    value = symbol.strip().upper()
    if not value or value.count("/") != 1 or any(ch.isspace() for ch in value):
        return None

    base, quote_and_settle = value.split("/", 1)
    if not base or not quote_and_settle or ":" in base:
        return None

    if ":" in quote_and_settle:
        quote, settle = quote_and_settle.split(":", 1)
        if not quote or not settle or ":" in settle:
            return None
    else:
        quote = quote_and_settle

    if not quote:
        return None
    return f"{base}/{quote}", quote


def _market_symbol(key: str, market: Mapping[str, Any]) -> str:
    value = market.get("symbol")
    return str(value) if value else str(key)


def _market_type(market: Mapping[str, Any]) -> str | None:
    value = str(market.get("type") or "").strip().lower()
    if value:
        return value
    if market.get("swap") is True:
        return "swap"
    if market.get("future") is True:
        return "future"
    if market.get("spot") is True:
        return "spot"
    return None


def _market_type_allowed(
    market: Mapping[str, Any], allowed_market_types: frozenset[str]
) -> bool:
    kind = _market_type(market)
    if kind in allowed_market_types:
        return True
    if market.get("swap") is True and "swap" in allowed_market_types:
        return True
    return market.get("future") is True and "future" in allowed_market_types


def _positive_finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _find_ticker(
    tickers: Mapping[str, Mapping[str, Any]],
    *,
    market_key: str,
    market_symbol: str,
) -> Mapping[str, Any] | None:
    """Find only the ticker belonging to the selected certified market."""
    for key in (market_key, market_symbol):
        ticker = tickers.get(key)
        if isinstance(ticker, Mapping):
            return ticker

    # Some adapters key the mapping differently but preserve CCXT ``symbol``.
    for ticker in tickers.values():
        if not isinstance(ticker, Mapping):
            continue
        if str(ticker.get("symbol") or "") == market_symbol:
            return ticker
    return None


def certify_universe(
    configured_symbols: Sequence[str],
    *,
    markets: Mapping[str, Mapping[str, Any]],
    tickers: Mapping[str, Mapping[str, Any]],
    exchange: str,
    allowed_quotes: Sequence[str] = _DEFAULT_QUOTES,
    allowed_market_types: Sequence[str] = _DEFAULT_MARKET_TYPES,
) -> UniverseCertification:
    """Certify a pinned universe against already-fetched exchange evidence.

    The function is intentionally pure.  The caller owns exchange I/O and any
    later artifact persistence.  A symbol is valid only when an eligible
    allowed market exists, is not explicitly inactive, and has a finite
    strictly-positive ``last`` price.
    """
    configured = tuple(str(symbol) for symbol in configured_symbols)
    quote_set = frozenset(str(q).upper() for q in allowed_quotes)
    market_type_set = frozenset(str(t).lower() for t in allowed_market_types)

    if not configured:
        return UniverseCertification(
            exchange=exchange,
            configured_symbols=(),
            validated_symbols=(),
            symbol_results=(),
            issues=(UniverseIssue.EMPTY_UNIVERSE,),
        )

    market_index: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for key, market in markets.items():
        if not isinstance(market, Mapping):
            continue
        normalized = _normalize_symbol(_market_symbol(str(key), market))
        if normalized is None:
            continue
        canonical, _ = normalized
        market_index.setdefault(canonical, []).append((str(key), market))

    results: list[SymbolCertification] = []
    validated: list[str] = []
    seen: set[str] = set()

    for configured_symbol in configured:
        normalized = _normalize_symbol(configured_symbol)
        if normalized is None:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=None,
                    valid=False,
                    issues=(UniverseIssue.INVALID_SYMBOL,),
                )
            )
            continue

        canonical, quote = normalized
        if quote not in quote_set:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.QUOTE_NOT_ALLOWED,),
                )
            )
            continue

        if canonical in seen:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.DUPLICATE_SYMBOL,),
                )
            )
            continue
        seen.add(canonical)

        candidates = market_index.get(canonical, [])
        if not candidates:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.MARKET_MISSING,),
                )
            )
            continue

        derivative_candidates = [
            candidate
            for candidate in candidates
            if _market_type_allowed(candidate[1], market_type_set)
        ]
        if not derivative_candidates:
            market_key, market = candidates[0]
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.MARKET_TYPE_MISMATCH,),
                    market_symbol=_market_symbol(market_key, market),
                    market_type=_market_type(market),
                )
            )
            continue

        active_candidates = [
            candidate
            for candidate in derivative_candidates
            if candidate[1].get("active") is not False
        ]
        if not active_candidates:
            market_key, market = derivative_candidates[0]
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.MARKET_INACTIVE,),
                    market_symbol=_market_symbol(market_key, market),
                    market_type=_market_type(market),
                )
            )
            continue

        market_key, market = active_candidates[0]
        selected_market_symbol = _market_symbol(market_key, market)
        selected_market_type = _market_type(market)
        ticker = _find_ticker(
            tickers,
            market_key=market_key,
            market_symbol=selected_market_symbol,
        )
        if ticker is None:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.TICKER_MISSING,),
                    market_symbol=selected_market_symbol,
                    market_type=selected_market_type,
                )
            )
            continue

        last_price = _positive_finite_number(ticker.get("last"))
        if last_price is None:
            results.append(
                SymbolCertification(
                    configured_symbol=configured_symbol,
                    normalized_symbol=canonical,
                    valid=False,
                    issues=(UniverseIssue.LAST_PRICE_INVALID,),
                    market_symbol=selected_market_symbol,
                    market_type=selected_market_type,
                )
            )
            continue

        validated.append(canonical)
        results.append(
            SymbolCertification(
                configured_symbol=configured_symbol,
                normalized_symbol=canonical,
                valid=True,
                issues=(),
                market_symbol=selected_market_symbol,
                market_type=selected_market_type,
                last_price=last_price,
            )
        )

    return UniverseCertification(
        exchange=exchange,
        configured_symbols=configured,
        validated_symbols=tuple(validated),
        symbol_results=tuple(results),
    )
