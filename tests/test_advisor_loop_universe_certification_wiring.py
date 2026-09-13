"""OPS-C / MARKET-UNIVERSE-01 — runtime wiring: pinned universe boot must be
fail-closed and use raw derivative + scan evidence, never the ranked/filtered
discover() path. See core/universe_certification.py for the pure contract.

R1 (MASTER review): certification must cover BOTH exchange domains —
execution (swap/perp, what PAPER futures actually trades) AND scan/données
(spot, what MarketScanner actually queries — defaultType="spot" is hardcoded
there). A symbol certified on only one domain could still be absent from the
other, reintroducing exactly the denominator contamination OPS-C exists to
eliminate. Boot must fail closed if either domain is not fully certified.
"""

from __future__ import annotations

import json

import pytest

from core import advisor_loop
from tools.perp_universe_builder import PerpUniverseBuilder


def _mk_market(symbol: str, *, market_type: str = "swap", active: bool = True) -> dict:
    return {"symbol": symbol, "type": market_type, "active": active}


def _mk_ticker(symbol: str, last: float) -> dict:
    return {"symbol": symbol, "last": last}


def _patch_evidence(monkeypatch, *, execution: tuple[dict, dict], scan: tuple[dict, dict]):
    """Return distinct evidence depending on the requested domain, mirroring
    fetch_raw_evidence(use_swap=...)'s real contract."""

    def _fake_fetch_raw_evidence(self, *, use_swap: bool = True):
        return execution if use_swap else scan

    monkeypatch.setattr(
        PerpUniverseBuilder, "fetch_raw_evidence", _fake_fetch_raw_evidence
    )


def _patch_same_evidence(monkeypatch, markets: dict, tickers: dict) -> None:
    """Same catalogue on both domains — market `type` decides which domain
    call actually certifies it (swap for execution, spot for scan)."""
    _patch_evidence(monkeypatch, execution=(markets, tickers), scan=(markets, tickers))


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


def _dual_domain_markets_tickers(symbol_deriv: str, symbol_spot: str, last: float):
    """A minimal fixture where the SAME pinned symbol has both a swap market
    (execution domain) and a spot market (scan domain) available."""
    markets = {
        symbol_deriv: _mk_market(symbol_deriv, market_type="swap"),
        symbol_spot: _mk_market(symbol_spot, market_type="spot"),
    }
    tickers = {
        symbol_deriv: _mk_ticker(symbol_deriv, last),
        symbol_spot: _mk_ticker(symbol_spot, last),
    }
    return markets, tickers


# A. valid pinned universe: configured 2, validated 2, boot allowed (both
# domains certified).
def test_valid_pinned_universe_boot_allowed(monkeypatch, _artifact_path):
    markets, tickers = {}, {}
    for base, price in (("BTC", 65000.0), ("ETH", 3500.0)):
        m, t = _dual_domain_markets_tickers(
            f"{base}/USDT:USDT", f"{base}/USDT", price
        )
        markets.update(m)
        tickers.update(t)
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(
        ["BTC/USDT", "ETH/USDT"]
    )

    assert execution_cert.is_certified
    assert scan_cert.is_certified
    assert execution_cert.configured_count == 2
    assert execution_cert.validated_count == 2
    assert scan_cert.validated_count == 2


# B. one nonexistent pinned symbol: configured 2, validated 1, boot refused.
def test_one_nonexistent_symbol_boot_refused(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(
        ["BTC/USDT", "NOPE/USDT"]
    )

    assert not execution_cert.is_certified
    assert execution_cert.configured_count == 2
    assert execution_cert.validated_count == 1
    assert execution_cert.rejected_count == 1
    assert not scan_cert.is_certified


# C. zero-price ticker: boot refused.
def test_zero_price_ticker_boot_refused(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers("BTC/USDT:USDT", "BTC/USDT", 0.0)
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert not execution_cert.is_certified
    assert execution_cert.validated_count == 0
    assert not scan_cert.is_certified


# D. spot-only market (no swap market at all): execution domain refused, boot
# refused — even though the scan/spot domain alone would certify.
def test_spot_only_market_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")}
    tickers = {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)}
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert not execution_cert.is_certified
    assert execution_cert.validated_count == 0
    assert scan_cert.is_certified  # spot domain alone is not sufficient


# D2. swap-only market (no spot market at all): scan/données domain refused,
# boot refused — the new R1 case: execution certifies but the scanner's own
# domain does not.
def test_swap_only_market_scan_domain_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT", market_type="swap")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert execution_cert.is_certified
    assert not scan_cert.is_certified
    assert scan_cert.validated_count == 0

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


# E. exchange evidence exception: boot refused, classified as evidence
# unavailable — never as a symbol-level rejection.
def test_exchange_evidence_exception_classified_as_unavailable(monkeypatch):
    def _boom(self, *, use_swap: bool = True):
        raise ConnectionError("mexc unreachable")

    monkeypatch.setattr(PerpUniverseBuilder, "fetch_raw_evidence", _boom)

    with pytest.raises(advisor_loop._CertificationEvidenceUnavailable):
        advisor_loop._certify_pinned_universe(["BTC/USDT"])


# F. empty pin: historical dynamic behavior unchanged (module still importable,
# _universe_pinned_symbols() returns [] and certification is never invoked).
def test_empty_pin_returns_empty_list(monkeypatch):
    monkeypatch.delenv("UNIVERSE_PINNED_SYMBOLS", raising=False)
    assert advisor_loop._universe_pinned_symbols() == []


# F2. dynamic path: the pinned-only snapshot counters stay None (contract),
# so the snapshot/pipeline-display code must show the historical format.
def test_dynamic_path_leaves_certification_snapshot_none():
    assert advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT is None


# G. certification does NOT call ranking/spread filter/volume filter/discover().
def test_certification_never_calls_discover(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )

    def _fake_fetch_raw_evidence(self, *, use_swap: bool = True):
        return markets, tickers

    def _discover_forbidden(self, *_a, **_kw):
        raise AssertionError("certification must never call discover()")

    monkeypatch.setattr(
        PerpUniverseBuilder, "fetch_raw_evidence", _fake_fetch_raw_evidence
    )
    monkeypatch.setattr(PerpUniverseBuilder, "discover", _discover_forbidden)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert execution_cert.is_certified
    assert scan_cert.is_certified


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


# H2. use_swap toggles the requested domain when no exchange is injected —
# proven via _build_exchange's config, without a real network call.
def test_fetch_raw_evidence_use_swap_selects_domain(monkeypatch):
    seen: list[bool] = []

    class _Fake:
        def load_markets(self):
            return {}

        def fetch_tickers(self):
            return {}

    def _fake_build_exchange(self, *, use_swap: bool):
        seen.append(use_swap)
        return _Fake()

    monkeypatch.setattr(PerpUniverseBuilder, "_build_exchange", _fake_build_exchange)
    builder = PerpUniverseBuilder(exchange_id="mexc")

    builder.fetch_raw_evidence(use_swap=True)
    builder.fetch_raw_evidence(use_swap=False)

    assert seen == [True, False]


# I. configured/validated/scan-successful counters have distinct semantics.
def test_counters_have_distinct_semantics(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, _scan_cert = advisor_loop._certify_pinned_universe(
        ["BTC/USDT", "MISSING/USDT"]
    )
    assert execution_cert.configured_count == 2
    assert execution_cert.validated_count == 1
    # scan_successful is a downstream runtime concept (len(results)),
    # deliberately not produced by certification itself.
    assert not hasattr(execution_cert, "scan_successful")


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
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    assert execution_cert.is_certified
    assert execution_cert.validated_symbols == ("BTC/USDT",)
    assert scan_cert.is_certified
    assert scan_cert.validated_symbols == ("BTC/USDT",)


def test_certification_artifact_persisted_on_pass(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    advisor_loop._certify_pinned_universe(["BTC/USDT"])

    with open(_artifact_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["is_certified"] is True
    assert payload["source"] == "pinned_universe_boot_execution"
    assert "evidence_sha256" in payload

    scan_path = _artifact_path.replace(".json", "_scan_domain.json")
    with open(scan_path, encoding="utf-8") as fh:
        scan_payload = json.load(fh)
    assert scan_payload["is_certified"] is True
    assert scan_payload["source"] == "pinned_universe_boot_scan"


def test_certification_artifact_persisted_on_fail(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    advisor_loop._certify_pinned_universe(["BTC/USDT", "NOPE/USDT"])

    with open(_artifact_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["is_certified"] is False
    assert payload["rejected_count"] == 1


# ── Direct fail-closed boot-boundary regression (R1) ────────────────────────


def test_resolve_pinned_universe_boot_allowed_returns_symbols_and_snapshot(
    monkeypatch, _artifact_path
):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    symbols, snapshot = advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])

    assert symbols == ["BTC/USDT"]
    assert snapshot == {"n_symbols_configured": 1, "n_symbols_validated": 1}


def test_resolve_pinned_universe_boot_raises_systemexit_on_symbol_rejection(
    monkeypatch, _artifact_path
):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT", "NOPE/USDT"])
    assert exc_info.value.code == 1


def test_resolve_pinned_universe_boot_raises_systemexit_on_evidence_unavailable(
    monkeypatch,
):
    def _boom(self, *, use_swap: bool = True):
        raise ConnectionError("mexc unreachable")

    monkeypatch.setattr(PerpUniverseBuilder, "fetch_raw_evidence", _boom)

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1
