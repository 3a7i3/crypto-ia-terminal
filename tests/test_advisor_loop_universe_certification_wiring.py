"""OPS-C — dual-domain pinned-universe runtime wiring.

The configured experimental population must be measurable by the current
MarketScanner (spot) AND eligible in the PAPER futures derivative domain
(swap/future).  Neither domain alone authorizes boot.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from core import advisor_loop
from tools.perp_universe_builder import PerpUniverseBuilder


def _mk_market(symbol: str, *, market_type: str = "swap", active: bool = True) -> dict:
    return {"symbol": symbol, "type": market_type, "active": active}


def _mk_ticker(symbol: str, last: float) -> dict:
    return {"symbol": symbol, "last": last}


def _dual_domain_markets_tickers(symbol_deriv: str, symbol_spot: str, last: float):
    markets = {
        symbol_deriv: _mk_market(symbol_deriv, market_type="swap"),
        symbol_spot: _mk_market(symbol_spot, market_type="spot"),
    }
    tickers = {
        symbol_deriv: _mk_ticker(symbol_deriv, last),
        symbol_spot: _mk_ticker(symbol_spot, last),
    }
    return markets, tickers


def _patch_evidence(
    monkeypatch,
    *,
    execution: tuple[dict, dict],
    scan: tuple[dict, dict],
) -> None:
    calls: list[str] = []

    def _fake_fetch_raw_evidence(self, *, market_type: str):
        calls.append(market_type)
        if market_type == "spot":
            return scan
        if market_type == "swap":
            return execution
        raise AssertionError(f"unexpected market_type={market_type!r}")

    monkeypatch.setattr(
        PerpUniverseBuilder, "fetch_raw_evidence", _fake_fetch_raw_evidence
    )
    monkeypatch.setattr(advisor_loop, "_OPS_C_TEST_EVIDENCE_CALLS", calls, raising=False)


def _patch_same_evidence(monkeypatch, markets: dict, tickers: dict) -> None:
    _patch_evidence(monkeypatch, execution=(markets, tickers), scan=(markets, tickers))


@pytest.fixture(autouse=True)
def _reset_certification_snapshot():
    advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT = None
    yield
    advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT = None


@pytest.fixture()
def _artifact_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "universe_certification.json"
    monkeypatch.setattr(
        advisor_loop,
        "_UNIVERSE_CERTIFICATION_ARTIFACT_PATH",
        str(path),
        raising=False,
    )
    return path


def test_both_domains_pass_boot_allowed(monkeypatch, _artifact_path):
    markets, tickers = {}, {}
    for base, price in (("BTC", 65000.0), ("ETH", 3500.0)):
        m, t = _dual_domain_markets_tickers(
            f"{base}/USDT:USDT", f"{base}/USDT", price
        )
        markets.update(m)
        tickers.update(t)
    _patch_same_evidence(monkeypatch, markets, tickers)

    symbols, snapshot = advisor_loop._resolve_pinned_universe_boot(
        ["BTC/USDT", "ETH/USDT"]
    )

    assert symbols == ["BTC/USDT", "ETH/USDT"]
    assert snapshot == {"n_symbols_configured": 2, "n_symbols_validated": 2}
    assert advisor_loop._OPS_C_TEST_EVIDENCE_CALLS == ["spot", "swap"]


def test_spot_only_is_insufficient_and_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")}
    tickers = {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)}
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert scan_cert.is_certified
    assert not execution_cert.is_certified

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_swap_only_is_insufficient_and_boot_refused(monkeypatch, _artifact_path):
    markets = {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT", market_type="swap")}
    tickers = {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)}
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert execution_cert.is_certified
    assert not scan_cert.is_certified

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_zero_price_in_spot_refuses_boot_even_if_swap_valid(monkeypatch, _artifact_path):
    execution = (
        {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT", market_type="swap")},
        {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 65000.0)},
    )
    scan = (
        {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")},
        {"BTC/USDT": _mk_ticker("BTC/USDT", 0.0)},
    )
    _patch_evidence(monkeypatch, execution=execution, scan=scan)

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_zero_price_in_swap_refuses_boot_even_if_spot_valid(monkeypatch, _artifact_path):
    execution = (
        {"BTC/USDT:USDT": _mk_market("BTC/USDT:USDT", market_type="swap")},
        {"BTC/USDT:USDT": _mk_ticker("BTC/USDT:USDT", 0.0)},
    )
    scan = (
        {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")},
        {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)},
    )
    _patch_evidence(monkeypatch, execution=execution, scan=scan)

    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_spot_evidence_exception_is_classified_unavailable(monkeypatch):
    def _fetch(self, *, market_type: str):
        if market_type == "spot":
            raise ConnectionError("spot evidence unavailable")
        return {}, {}

    monkeypatch.setattr(PerpUniverseBuilder, "fetch_raw_evidence", _fetch)

    with pytest.raises(
        advisor_loop._CertificationEvidenceUnavailable, match="scan domain"
    ):
        advisor_loop._certify_pinned_universe(["BTC/USDT"])
    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_swap_evidence_exception_is_classified_unavailable(monkeypatch):
    spot = (
        {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")},
        {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)},
    )

    def _fetch(self, *, market_type: str):
        if market_type == "spot":
            return spot
        if market_type == "swap":
            raise ConnectionError("swap evidence unavailable")
        raise AssertionError(market_type)

    monkeypatch.setattr(PerpUniverseBuilder, "fetch_raw_evidence", _fetch)

    with pytest.raises(
        advisor_loop._CertificationEvidenceUnavailable, match="execution domain"
    ):
        advisor_loop._certify_pinned_universe(["BTC/USDT"])
    with pytest.raises(SystemExit) as exc_info:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
    assert exc_info.value.code == 1


def test_certification_never_calls_discover(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    def _forbidden(self, *_args, **_kwargs):
        raise AssertionError("certification must never call discover()")

    monkeypatch.setattr(PerpUniverseBuilder, "discover", _forbidden)
    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert execution_cert.is_certified
    assert scan_cert.is_certified


def test_symbol_without_settle_suffix_matches_derivative_market(
    monkeypatch, _artifact_path
):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])
    assert execution_cert.validated_symbols == ("BTC/USDT",)
    assert scan_cert.validated_symbols == ("BTC/USDT",)


def test_single_nested_artifact_preserves_both_hashes(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    execution_cert, scan_cert = advisor_loop._certify_pinned_universe(["BTC/USDT"])

    payload = json.loads(_artifact_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "ops-c-dual-domain-v1"
    assert payload["source"] == "pinned_universe_boot"
    assert payload["is_certified"] is True
    assert payload["configured_count"] == 1
    assert payload["validated_count"] == 1
    assert payload["domains"]["scan_data"] == {
        "exchange": "mexc",
        "market_type": "spot",
    }
    assert payload["domains"]["execution_derivative"] == {
        "exchange": "mexc",
        "market_type": "swap/future",
    }
    assert payload["scan_data"]["evidence_sha256"] == scan_cert.evidence_sha256
    assert (
        payload["execution_derivative"]["evidence_sha256"]
        == execution_cert.evidence_sha256
    )
    second_path = Path(str(_artifact_path).replace(".json", "_scan_domain.json"))
    assert not second_path.exists()


def test_single_nested_artifact_records_fail(monkeypatch, _artifact_path):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    advisor_loop._certify_pinned_universe(["BTC/USDT", "NOPE/USDT"])

    payload = json.loads(_artifact_path.read_text(encoding="utf-8"))
    assert payload["is_certified"] is False
    assert payload["configured_count"] == 2
    assert payload["validated_count"] == 1
    assert payload["scan_data"]["is_certified"] is False
    assert payload["execution_derivative"]["is_certified"] is False


def test_empty_pin_keeps_historical_dynamic_path(monkeypatch):
    monkeypatch.delenv("UNIVERSE_PINNED_SYMBOLS", raising=False)
    assert advisor_loop._universe_pinned_symbols() == []
    assert advisor_loop._UNIVERSE_CERTIFICATION_SNAPSHOT is None


def test_dynamic_counter_contract_and_legacy_n_symbols_are_preserved():
    src = inspect.getsource(advisor_loop)
    assert '"n_symbols": len(results),' in src
    assert '"n_symbols_configured"' in src
    assert '"n_symbols_validated"' in src
    assert '"n_symbols_scan_successful": (' in src
    assert "len(results) if _UNIVERSE_CERTIFICATION_SNAPSHOT else None" in src


def test_fail_closed_boundary_prevents_downstream_scan(monkeypatch, _artifact_path):
    markets = {"BTC/USDT": _mk_market("BTC/USDT", market_type="spot")}
    tickers = {"BTC/USDT": _mk_ticker("BTC/USDT", 65000.0)}
    _patch_same_evidence(monkeypatch, markets, tickers)
    downstream_calls: list[str] = []

    def _boot_then_scan() -> None:
        advisor_loop._resolve_pinned_universe_boot(["BTC/USDT"])
        downstream_calls.append("scan")

    with pytest.raises(SystemExit) as exc_info:
        _boot_then_scan()
    assert exc_info.value.code == 1
    assert downstream_calls == []



def test_settle_suffixed_pin_normalizes_dual_domain_intersection(
    monkeypatch, _artifact_path
):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    symbols, snapshot = advisor_loop._resolve_pinned_universe_boot(
        ["BTC/USDT:USDT"]
    )

    assert symbols == ["BTC/USDT"]
    assert snapshot == {"n_symbols_configured": 1, "n_symbols_validated": 1}
    payload = json.loads(_artifact_path.read_text(encoding="utf-8"))
    assert payload["validated_symbols"] == ["BTC/USDT"]
