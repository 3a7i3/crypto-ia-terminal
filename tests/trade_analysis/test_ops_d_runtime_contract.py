"""Régressions OPS-D — contrat runtime LMI.

Ces tests sont purement source : aucun accès réseau réel. Ils verrouillent les
invariants démontrés par la capture VPS OPS-D du 2026-09-13 :

- aucun état historique hors watchlist dans le sidecar courant ;
- distinction requested/streamable/observed/fresh/unavailable ;
- validation MEXC via le catalogue Futures public avant souscription WS ;
- indisponibilité du catalogue traitée fail-closed pour l'itération.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_data.connectors.mexc import MEXCFuturesConnector
from trade_analysis.observatory import LiveStateStore, Observatory


class _DummyPF:
    def __init__(self, symbol: str, *, age_ms: int = 0) -> None:
        self.symbol = symbol
        self._timestamp_ms = int(time.time() * 1000) - age_ms

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp_ms": self._timestamp_ms,
            "price": 1.0,
            "state": "quiet",
        }


def test_store_prunes_states_removed_from_watchlist(tmp_path):
    store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
    store.set_watchlist(["BTCUSDT", "ETHUSDT"])
    store.update(_DummyPF("BTCUSDT"))
    store.update(_DummyPF("ETHUSDT"))

    store.set_watchlist(["ETHUSDT"])
    snap = store.snapshot()

    assert set(snap["symbols"]) == {"ETHUSDT"}
    assert snap["stats"]["symbols_active"] == 1
    assert snap["stats"]["symbols_watched"] == 1


def test_removed_symbol_cannot_be_reintroduced_by_late_update(tmp_path):
    store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
    store.set_watchlist(["BTCUSDT"])
    store.update(_DummyPF("BTCUSDT"))

    store.set_watchlist(["ETHUSDT"])
    store.update(_DummyPF("BTCUSDT"))

    snap = store.snapshot()
    assert "BTCUSDT" not in snap["symbols"]
    assert snap["coverage"]["ETHUSDT"]["status"] == "UNAVAILABLE"
    assert snap["coverage"]["ETHUSDT"]["reason"] == "no_pressure_field"


def test_snapshot_separates_requested_streamable_and_unavailable(tmp_path):
    store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
    store.set_watchlist(
        ["BTCUSDT", "USD1USDT"],
        stream_symbols=["BTCUSDT"],
        unavailable={"USD1USDT": "not_in_mexc_futures_catalog"},
    )
    store.update(_DummyPF("BTCUSDT"))

    snap = store.snapshot()

    assert snap["watchlist"] == ["BTCUSDT", "USD1USDT"]
    assert snap["stream_watchlist"] == ["BTCUSDT"]
    assert snap["coverage"]["BTCUSDT"]["status"] == "LIVE"
    assert snap["coverage"]["USD1USDT"] == {
        "status": "UNAVAILABLE",
        "age_ms": None,
        "stream_requested": False,
        "reason": "not_in_mexc_futures_catalog",
    }
    assert snap["stats"]["symbols_watched"] == 2
    assert snap["stats"]["symbols_streamable"] == 1
    assert snap["stats"]["symbols_active"] == 1
    assert snap["stats"]["symbols_fresh"] == 1
    assert snap["stats"]["symbols_stale"] == 0
    assert snap["stats"]["symbols_unavailable"] == 1


def test_snapshot_marks_old_market_timestamp_stale(tmp_path):
    store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
    store.set_watchlist(["BTCUSDT"])
    store.update(_DummyPF("BTCUSDT", age_ms=30_000))

    snap = store.snapshot()

    assert snap["coverage"]["BTCUSDT"]["status"] == "STALE"
    assert snap["stats"]["symbols_fresh"] == 0
    assert snap["stats"]["symbols_stale"] == 1


def test_mexc_public_catalog_normalizes_symbols(monkeypatch):
    conn = MEXCFuturesConnector()
    monkeypatch.setattr(
        conn,
        "_get_json",
        lambda *args, **kwargs: {
            "data": [
                {"symbol": "BTC_USDT", "contractSize": 0.0001},
                {"symbol": "ETH_USDT", "contractSize": 0.01},
            ]
        },
    )

    assert conn.fetch_supported_symbols() == {"BTCUSDT", "ETHUSDT"}


def test_mexc_public_catalog_empty_is_not_valid_evidence(monkeypatch):
    conn = MEXCFuturesConnector()
    monkeypatch.setattr(conn, "_get_json", lambda *args, **kwargs: {"data": []})

    with pytest.raises(RuntimeError, match="no symbols"):
        conn.fetch_supported_symbols()


@pytest.mark.asyncio
async def test_validate_watchlist_filters_unsupported_mexc_symbols():
    obs = Observatory.__new__(Observatory)
    obs.exchange = "mexc"

    connector = MagicMock()
    connector.fetch_supported_symbols.return_value = {"BTCUSDT", "ETHUSDT"}

    with patch.object(obs, "_make_connector", return_value=connector):
        streamable, unavailable = await obs._validate_watchlist(
            ["BTCUSDT", "USD1USDT"]
        )

    assert streamable == ["BTCUSDT"]
    assert unavailable == {"USD1USDT": "not_in_mexc_futures_catalog"}


@pytest.mark.asyncio
async def test_validate_watchlist_catalog_failure_is_fail_closed():
    obs = Observatory.__new__(Observatory)
    obs.exchange = "mexc"

    connector = MagicMock()
    connector.fetch_supported_symbols.side_effect = RuntimeError("network down")

    with patch.object(obs, "_make_connector", return_value=connector):
        streamable, unavailable = await obs._validate_watchlist(
            ["BTCUSDT", "ETHUSDT"]
        )

    assert streamable == []
    assert unavailable == {
        "BTCUSDT": "market_catalog_unavailable:RuntimeError",
        "ETHUSDT": "market_catalog_unavailable:RuntimeError",
    }


@pytest.mark.asyncio
async def test_reconcile_starts_only_streamable_symbols():
    obs = Observatory.__new__(Observatory)
    obs.exchange = "mexc"
    obs._tasks = {}
    obs._engines = {}
    obs.store = MagicMock()
    obs.compute_watchlist = MagicMock(return_value=["BTCUSDT", "USD1USDT"])
    obs._validate_watchlist = AsyncMock(
        return_value=(
            ["BTCUSDT"],
            {"USD1USDT": "not_in_mexc_futures_catalog"},
        )
    )

    blocker = __import__("asyncio").Event()

    async def _run_symbol(_symbol: str) -> None:
        await blocker.wait()

    with patch.object(obs, "_run_symbol", side_effect=_run_symbol):
        await obs._reconcile()
        await __import__("asyncio").sleep(0)

    try:
        assert set(obs._tasks) == {"BTCUSDT"}
        obs.store.set_watchlist.assert_called_once_with(
            ["BTCUSDT", "USD1USDT"],
            stream_symbols=["BTCUSDT"],
            unavailable={"USD1USDT": "not_in_mexc_futures_catalog"},
        )
    finally:
        blocker.set()
        await obs._tasks["BTCUSDT"]
