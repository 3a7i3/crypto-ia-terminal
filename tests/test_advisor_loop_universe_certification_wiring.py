"""OPS-C / MARKET-UNIVERSE-01 — runtime wiring: pinned universe boot must be
fail-closed and use raw derivative evidence, never the ranked/filtered
discover() path. See core/universe_certification.py for the pure contract."""

from __future__ import annotations

import json

import pytest

from core import advisor_loop
from tools.perp_universe_builder import PerpUniverseBuilder


def _mk_market(symbol: str, *, market_type: str = "swap", active: bool = True) -> dict:
    return {"symbol": symbol, "type": market_type, "active": active}


def _mk_ticker(symbol: str, last: float) -> dict:
    return {"symbol": symbol, "last": last}


def _patch_evidence(monkeypatch, markets: dict, tickers: dict) -> None:
    def _fake_fetch_raw_evidence(self):
        return markets, tickers

    monkeypatch.setattr(
        PerpUniverseBuilder, "fetch_raw_evidence", _fake_fetch_raw_evidence
    )


@pytest.fixture(autouse=True)
def _reset_certification_snapshot():
    advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT = None
    yield
    advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT = None


@pytest.fixture()
def _artifact_path(tmp_path, monkeypatch):
    path = str(tmp_path / "universe_certification.json")
    monkeypatch.setattr(
        advisor_loop, "_UNIVERSE_CERTIFICATION_ARTIFACT_PATH", path, raising=False
    )
    return path


# A. valid pinned universe: configured 2, validated 2, boot allowed.
def test_valid_pinned_universe_boot_allowed(monkeypatch, _artifact_path):
    markets = {
        "BTC/USDT:USDT": _mk_market("BTC/USDT:USDT"),
        "ETH/USDT:USDT": _mk_market("ETH/USDT:USDT"),
    }
    tickers = {
        "BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0),
        "ETH/USDT:USDT": _mk_ticker("ETH/USDT:USDT", 3500.0),
    }
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT", "ETH/USDT"])

    assert cert.is_certified
    assert cert.configured_count == 2
    assert cert.validated_count == 2


# B. one nonexistent pinned symbol: configured 2, validated 1, boot refused.
def test_one_nonexistent_symbol_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT", "NOPE/USDT"])

    assert not cert.is_certified
    assert cert.configured_count == 2
    assert cert.validated_count == 1
    assert cert.rejected_count == 1


# C. zero-price ticker: boot refused.
def test_zero_price_ticker_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 0.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert not cert.is_certified
    assert cert.validated_count == 0


# D. spot-only market: boot refused.
def test_spot_only_market_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")}
    tickers = {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert not cert.is_certified
    assert cert.validated_count == 0


# E. exchange evidence exception: boot refused, classified as evidence
# unavailable — never as a symbol-level rejection.
def test_exchange_evidence_exception_classified_as_unavailable(monkeypatch):
    def _boom(self):
        raise ConnectionError("mexc unreachable")

    monkeypatch.setattr(PerpUniverseBuilder, "fetch_raw_evidence", _boom)

    with pytest.raises(advisor_loop._CertificationEvidenceUnavailable):
        advisor_loop._certify_pinned_universe(["BTC/USDT"])


# F. empty pin: historical dynamic behavior unchanged (module still importable,
# _universe_pinned_symbols() returns [] and certification is never invoked).
def test_empty_pin_returns_empty_list(monkeypatch):
    monkeypatch.delenv("UNIVERSE_PINNED_SYMBOLS", raising=False)
    assert advisor_loop._universe_pinned_symbols() == []


# G. certification does NOT call ranking/spread filter/volume filter/discover().
def test_certification_never_calls_discover(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}

    def _fake_fetch_raw_evidence(self):
        return markets, tickers

    def _discover_forbidden(self, *_a, **_kw):
        raise AssertionError("certification must never call discover()")

    monkeypatch.setattr(
        PerpUniverseBuilder, "fetch_raw_evidence", _fake_fetch_raw_evidence
    )
    monkeypatch.setattr(PerpUniverseBuilder, "discover", _discover_forbidden)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert cert.is_certified


# H. raw evidence method: load_markets + fetch_tickers only.
def test_raw_evidence_method_uses_only_load_markets_and_fetch_tickers():
    calls = []

    class _Fake:
        def load_markets(self):
            calls.append("load_markets")
            return {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}

        def fetch_tickers(self):
            calls.append("fetch_tickers")
            return {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}

    builder = PerpUniverseBuilder(exchange_id="mexc", exchange=_Fake())
    builder.fetch_raw_evidence()
    assert calls == ["load_markets", "fetch_tickers"]


# I. configured/validated/scan-successful counters have distinct semantics.
def test_counters_have_distinct_semantics(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT", "MISSING/USDT"])
    assert cert.configured_count == 2
    assert cert.validated_count == 1
    # scan_successful is a downstream runtime concept (len(results)),
    # deliberately not produced by certification itself.
    assert not hasattr(cert, "scan_successful")


# J. existing n_symbols remains backward compatible (still present alongside
# the new explicit fields in the quantitative snapshot payload built in main()).
def test_n_symbols_field_still_referenced_in_source():
    import inspect

    src = inspect.getsource(advisor_loop)
    assert '"n_symbols": len(results),' in src
    assert '"n_symbols_configured"' in src
    assert '"n_symbols_validated"' in src
    assert '"n_symbols_scan_successful"' in src


# Symbol-format boundary: MEXC/CCXT derivative "BTC/USDT:USDT" market vs the
# operator pin "BTC/USDT" — normalization from the MASTER core must resolve.
def test_pinned_symbol_without_settle_suffix_matches_derivative_market(
    monkeypatch, _artifact_path
):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert cert.is_certified
    assert cert.validated_symbols == ("BTC/USDT",)


def test_certification_artifact_persisted_on_pass(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    advisor_loop._certify_pinned_universe(["BTC/USDT"])

    with open(_artifact_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["is_certified"] is True
    assert payload["source"] == "pinned_universe_boot"
    assert "evidence_sha256" in payload


def test_certification_artifact_persisted_on_fail(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_evidence(monkeypatch, markets, tickers)

    advisor_loop._certify_pinned_universe(["BTC/USDT", "NOPE/USDT"])

    with open(_artifact_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["is_certified"] is False
    assert payload["rejected_count"] == 1
