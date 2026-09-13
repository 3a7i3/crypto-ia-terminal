"""OPS-C — fetch_raw_evidence() : évidence brute, aucun filtrage/ranking."""

from __future__ import annotations

import pytest

from tools.perp_universe_builder import PerpUniverseBuilder


class _FakeExchange:
    """CCXT-like minimal — enregistre les appels pour prouver l'absence de
    filtrage : load_markets()/fetch_tickers() sont les SEULES méthodes
    appelées par fetch_raw_evidence()."""

    def __init__(self, markets: dict, tickers: dict) -> None:
        self._markets = markets
        self._tickers = tickers
        self.calls: list[str] = []

    def load_markets(self) -> dict:
        self.calls.append("load_markets")
        return self._markets

    def fetch_tickers(self) -> dict:
        self.calls.append("fetch_tickers")
        return self._tickers

    def discover(self, *_a, **_kw):  # pragma: no cover - doit rester inutilisé
        raise AssertionError("fetch_raw_evidence() ne doit jamais appeler discover()")


def _markets() -> dict:
    return {
        "BTC/USDT:USDT": {
            "symbol": "BTC/USDT:USDT",
            "type": "swap",
            "active": True,
        },
        "ETH/USDT": {
            "symbol": "ETH/USDT",
            "type": "spot",
            "active": True,
        },
    }


def _tickers() -> dict:
    return {
        "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "last": 65000.0},
        "ETH/USDT": {"symbol": "ETH/USDT", "last": 3500.0},
    }


def test_fetch_raw_evidence_returns_unfiltered_markets_and_tickers() -> None:
    fake = _FakeExchange(_markets(), _tickers())
    builder = PerpUniverseBuilder(exchange_id="mexc", exchange=fake)

    markets, tickers = builder.fetch_raw_evidence(market_type="swap")

    assert markets == _markets()
    assert tickers == _tickers()
    assert fake.calls == ["load_markets", "fetch_tickers"]


def test_fetch_raw_evidence_calls_only_load_markets_and_fetch_tickers() -> None:
    fake = _FakeExchange(_markets(), _tickers())
    builder = PerpUniverseBuilder(exchange_id="mexc", exchange=fake)

    builder.fetch_raw_evidence(market_type="spot")

    assert set(fake.calls) == {"load_markets", "fetch_tickers"}


def test_fetch_raw_evidence_does_not_rank_or_filter_low_volume_low_price() -> None:
    """Contrairement à discover(), aucun seuil vol/spread ne doit exclure un
    marché même illiquide ou sans profondeur, tant que l'évidence brute
    contient l'entrée — la certification décide seule de la validité."""
    markets = {
        "ILLIQUID/USDT:USDT": {
            "symbol": "ILLIQUID/USDT:USDT",
            "type": "swap",
            "active": True,
        }
    }
    tickers = {
        "ILLIQUID/USDT:USDT": {
            "symbol": "ILLIQUID/USDT:USDT",
            "last": 0.0001,
            "quoteVolume": 1.0,
            "bid": 0.00009,
            "ask": 0.00012,
        }
    }
    fake = _FakeExchange(markets, tickers)
    builder = PerpUniverseBuilder(exchange_id="mexc", exchange=fake)

    out_markets, out_tickers = builder.fetch_raw_evidence(market_type="swap")

    assert "ILLIQUID/USDT:USDT" in out_markets
    assert "ILLIQUID/USDT:USDT" in out_tickers


def test_fetch_raw_evidence_builds_explicit_spot_domain(monkeypatch) -> None:
    seen: list[str] = []

    class _EmptyExchange:
        def load_markets(self):
            return {}

        def fetch_tickers(self):
            return {}

    def _fake_build(self, *, market_type: str):
        seen.append(market_type)
        return _EmptyExchange()

    monkeypatch.setattr(PerpUniverseBuilder, "_build_evidence_exchange", _fake_build)
    PerpUniverseBuilder(exchange_id="mexc").fetch_raw_evidence(market_type="spot")

    assert seen == ["spot"]


def test_fetch_raw_evidence_builds_explicit_swap_domain(monkeypatch) -> None:
    seen: list[str] = []

    class _EmptyExchange:
        def load_markets(self):
            return {}

        def fetch_tickers(self):
            return {}

    def _fake_build(self, *, market_type: str):
        seen.append(market_type)
        return _EmptyExchange()

    monkeypatch.setattr(PerpUniverseBuilder, "_build_evidence_exchange", _fake_build)
    PerpUniverseBuilder(exchange_id="mexc").fetch_raw_evidence(market_type="swap")

    assert seen == ["swap"]


def test_fetch_raw_evidence_rejects_unknown_market_type() -> None:
    builder = PerpUniverseBuilder(exchange_id="mexc", exchange=_FakeExchange({}, {}))

    with pytest.raises(ValueError, match="market_type invalide"):
        builder.fetch_raw_evidence(market_type="future")  # type: ignore[arg-type]
