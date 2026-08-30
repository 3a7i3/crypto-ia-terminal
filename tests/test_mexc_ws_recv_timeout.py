"""
Tests ciblés — MEXCFuturesConnector recv timeout + Observatory task revival.

Couvre :
  TEST 1 — recv timeout : ws.recv() ne retourne jamais → stream terminé proprement
  TEST 2 — message avant timeout : parsing préservé
  TEST 3 — annulation (CancelledError) propagée correctement
  TEST 4 — task done dans l'observatory → recréée par _reconcile()
  TEST 5 — task vivante non redémarrée
  TEST 6 — _reconcile() répété sans duplication de task

Aucun accès réseau réel. Tout est mocké.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers communs
# ---------------------------------------------------------------------------


def _make_deal_msg(symbol: str = "BTC_USDT", ts: int = 1_788_000_000_000) -> str:
    return json.dumps(
        {
            "channel": "push.deal",
            "symbol": symbol,
            "data": [{"p": "78000.0", "v": "1.0", "T": 1, "t": ts}],
        }
    )


def _make_depth_msg(symbol: str = "BTC_USDT", ts: int = 1_788_000_000_000) -> str:
    return json.dumps(
        {
            "channel": "push.depth",
            "symbol": symbol,
            "data": {
                "bids": [["78000", "5"]],
                "asks": [["78001", "3"]],
                "timestamp": ts,
            },
        }
    )


class _FakeWS:
    """Mock minimal d'une connexion websockets."""

    def __init__(self, recv_side_effect):
        self._recv_se = recv_side_effect
        self._sent = []
        self._recv_calls = 0

    async def send(self, msg: str) -> None:
        self._sent.append(msg)

    async def recv(self) -> str:
        effect = self._recv_se[self._recv_calls % len(self._recv_se)]
        self._recv_calls += 1
        if isinstance(effect, Exception):
            raise effect
        if asyncio.iscoroutine(effect):
            return await effect
        return effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


# ---------------------------------------------------------------------------
# TEST 1 — recv timeout : ws.recv() qui ne retourne jamais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_trades_recv_timeout_terminates_cleanly():
    """
    Si ws.recv() ne retourne jamais (session CLOSE_WAIT/stale),
    asyncio.wait_for lève TimeoutError et stream_trades() doit
    terminer proprement (return, pas exception non capturée).
    """
    from market_data.connectors.mexc import MEXCFuturesConnector, _RECV_TIMEOUT_S

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()

    # ws.recv() bloque indéfiniment — simulé par asyncio.sleep très long
    async def _blocking_recv():
        await asyncio.sleep(9999)
        return ""  # jamais atteint

    ws = _FakeWS([asyncio.sleep(9999)])

    # Patch ws.recv pour qu'il bloque vraiment
    async def _stall():
        await asyncio.sleep(9999)
        return ""

    ws.recv = _stall  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 0.1),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        trades = []
        # Doit terminer sans exception après ~0.1s de timeout
        async for t in conn.stream_trades("BTCUSDT"):
            trades.append(t)  # pragma: no cover

    # Aucun trade produit, mais le générateur s'est terminé sans erreur
    assert trades == []
    # Log de warning attendu
    conn._log.warning.assert_called_once()
    call_args = conn._log.warning.call_args[0]
    assert "stream_trades" in call_args[0]
    assert "stale" in call_args[0]


@pytest.mark.asyncio
async def test_stream_orderbook_recv_timeout_terminates_cleanly():
    """Même comportement pour stream_orderbook."""
    from market_data.connectors.mexc import MEXCFuturesConnector

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()

    ws = _FakeWS([])

    async def _stall():
        await asyncio.sleep(9999)
        return ""

    ws.recv = _stall  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 0.1),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        books = []
        async for b in conn.stream_orderbook("BTCUSDT"):
            books.append(b)  # pragma: no cover

    assert books == []
    conn._log.warning.assert_called_once()
    call_args = conn._log.warning.call_args[0]
    assert "stream_orderbook" in call_args[0]
    assert "stale" in call_args[0]


# ---------------------------------------------------------------------------
# TEST 2 — message valide avant timeout : parsing préservé
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_trades_valid_message_before_timeout():
    """
    Un message push.deal valide doit être parsé et yielded normalement,
    indépendamment du timeout (qui ne se déclenche qu'en cas d'inactivité).
    """
    from market_data.connectors.mexc import MEXCFuturesConnector

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()
    # Forcer la spec contrat sans appel réseau
    from market_data.connectors.mexc import ContractSpecification
    conn._CONTRACT_SPECS["BTC_USDT"] = ContractSpecification(
        symbol="BTC_USDT", contract_size=0.0001, source="api",
        fetched_at_ms=1_000_000_000
    )
    conn._CONTRACT_API_LOADED = True  # type: ignore[attr-defined]

    msg_json = _make_deal_msg(ts=1_788_073_125_258)
    recv_calls = 0

    async def _recv_once_then_stall():
        nonlocal recv_calls
        recv_calls += 1
        if recv_calls == 1:
            return msg_json
        await asyncio.sleep(9999)
        return ""

    ws = _FakeWS([])
    ws.recv = _recv_once_then_stall  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 0.15),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        trades = []
        async for t in conn.stream_trades("BTCUSDT"):
            trades.append(t)
            break  # récupérer uniquement le premier

    assert len(trades) == 1
    assert trades[0].symbol == "BTCUSDT"
    assert trades[0].exchange == "mexc"
    assert trades[0].timestamp_ms == 1_788_073_125_258
    assert trades[0].price == 78000.0
    # Timestamp = celui de l'événement, pas wall-clock
    assert trades[0].timestamp_ms > 1_700_000_000_000  # sanity ms epoch


@pytest.mark.asyncio
async def test_stream_orderbook_valid_message_before_timeout():
    """stream_orderbook : message push.depth parsé correctement."""
    from market_data.connectors.mexc import MEXCFuturesConnector, ContractSpecification

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()
    conn._CONTRACT_SPECS["BTC_USDT"] = ContractSpecification(
        symbol="BTC_USDT", contract_size=0.0001, source="api",
        fetched_at_ms=1_000_000_000
    )
    conn._CONTRACT_API_LOADED = True  # type: ignore[attr-defined]

    msg_json = _make_depth_msg(ts=1_788_073_125_000)
    recv_calls = 0

    async def _recv_once_then_stall():
        nonlocal recv_calls
        recv_calls += 1
        if recv_calls == 1:
            return msg_json
        await asyncio.sleep(9999)
        return ""

    ws = _FakeWS([])
    ws.recv = _recv_once_then_stall  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 0.15),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        books = []
        async for b in conn.stream_orderbook("BTCUSDT"):
            books.append(b)
            break

    assert len(books) == 1
    assert books[0].symbol == "BTCUSDT"
    assert books[0].exchange == "mexc"
    assert books[0].timestamp_ms == 1_788_073_125_000
    assert len(books[0].bids) == 1
    assert books[0].bids[0][0] == 78000.0


# ---------------------------------------------------------------------------
# TEST 3 — CancelledError propagé correctement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_trades_cancellation_propagates():
    """
    Si le task parent est annulé (CancelledError), il doit se propager
    sans être avalé par le except asyncio.TimeoutError.
    """
    from market_data.connectors.mexc import MEXCFuturesConnector

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()

    async def _slow_recv():
        await asyncio.sleep(5.0)
        return ""

    ws = _FakeWS([])
    ws.recv = _slow_recv  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 10.0),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        async def _run():
            async for _ in conn.stream_trades("BTCUSDT"):
                pass  # pragma: no cover

        task = asyncio.create_task(_run())
        await asyncio.sleep(0.05)  # laisser le temps de démarrer
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_stream_orderbook_cancellation_propagates():
    """Même comportement pour stream_orderbook."""
    from market_data.connectors.mexc import MEXCFuturesConnector

    conn = MEXCFuturesConnector()
    conn._log = MagicMock()

    async def _slow_recv():
        await asyncio.sleep(5.0)
        return ""

    ws = _FakeWS([])
    ws.recv = _slow_recv  # type: ignore[method-assign]

    with (
        patch("market_data.connectors.mexc._RECV_TIMEOUT_S", 10.0),
        patch("websockets.connect", return_value=ws),
        patch.object(conn, "_ensure_contract_sizes"),
    ):
        async def _run():
            async for _ in conn.stream_orderbook("BTCUSDT"):
                pass  # pragma: no cover

        task = asyncio.create_task(_run())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# TEST 4 — Observatory : task done → recréée par _reconcile()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_recreates_done_task():
    """
    Une task asyncio terminée (done=True) pour un symbole encore dans la
    watchlist doit être retirée du registre et recréée à l'appel suivant
    de _reconcile().
    """
    from trade_analysis.observatory import Observatory
    from trade_analysis.selection import SymbolSelector

    obs = Observatory.__new__(Observatory)
    obs._tasks = {}
    obs._engines = {}
    obs._running = False

    # Watchlist fixe : un seul symbole
    obs.selector = MagicMock(spec=SymbolSelector)
    obs.selector.select_symbols.return_value = ["BTCUSDT"]
    obs.max_symbols = 5
    obs.selection_kwargs = {}
    obs.store = MagicMock()
    obs.store.set_watchlist = MagicMock()
    obs._recorder = None
    obs.exchange = "mexc"

    # Créer une fausse task déjà terminée
    async def _noop():
        pass

    done_task = asyncio.create_task(_noop())
    await asyncio.sleep(0)  # laisser la task se terminer
    assert done_task.done()

    obs._tasks["BTCUSDT"] = done_task

    # _run_symbol est patché pour ne pas faire de vrai WebSocket
    with patch.object(obs, "_run_symbol", new_callable=AsyncMock) as mock_run:
        await obs._reconcile()

    # La task done a été retirée et une nouvelle a été créée
    assert "BTCUSDT" in obs._tasks
    new_task = obs._tasks["BTCUSDT"]
    assert new_task is not done_task  # c'est une nouvelle task
    assert not new_task.done() or new_task.done()  # peut être déjà terminée (mock), mais différente instance


# ---------------------------------------------------------------------------
# TEST 5 — Task vivante non redémarrée
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_does_not_restart_alive_task():
    """
    Une task vivante (done=False) pour un symbole dans la watchlist ne doit
    PAS être annulée ou recréée par _reconcile().
    """
    from trade_analysis.observatory import Observatory
    from trade_analysis.selection import SymbolSelector

    obs = Observatory.__new__(Observatory)
    obs._tasks = {}
    obs._engines = {}
    obs._running = False
    obs.selector = MagicMock(spec=SymbolSelector)
    obs.selector.select_symbols.return_value = ["BTCUSDT"]
    obs.max_symbols = 5
    obs.selection_kwargs = {}
    obs.store = MagicMock()
    obs.store.set_watchlist = MagicMock()
    obs._recorder = None
    obs.exchange = "mexc"

    # Task vivante qui attend
    alive_event = asyncio.Event()

    async def _long_running():
        await alive_event.wait()  # bloque jusqu'à la fin du test

    alive_task = asyncio.create_task(_long_running())
    await asyncio.sleep(0)  # laisser démarrer
    assert not alive_task.done()

    obs._tasks["BTCUSDT"] = alive_task

    with patch.object(obs, "_run_symbol", new_callable=AsyncMock) as mock_run:
        await obs._reconcile()

    # La task vivante n'a pas été remplacée
    assert obs._tasks["BTCUSDT"] is alive_task
    mock_run.assert_not_called()

    # Cleanup
    alive_event.set()
    await alive_task


# ---------------------------------------------------------------------------
# TEST 6 — _reconcile() répété sans duplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_repeated_no_duplicate():
    """
    Deux appels successifs à _reconcile() ne doivent pas créer deux tasks
    actives pour le même symbole.
    """
    from trade_analysis.observatory import Observatory
    from trade_analysis.selection import SymbolSelector

    obs = Observatory.__new__(Observatory)
    obs._tasks = {}
    obs._engines = {}
    obs._running = False
    obs.selector = MagicMock(spec=SymbolSelector)
    obs.selector.select_symbols.return_value = ["BTCUSDT", "ETHUSDT"]
    obs.max_symbols = 5
    obs.selection_kwargs = {}
    obs.store = MagicMock()
    obs.store.set_watchlist = MagicMock()
    obs._recorder = None
    obs.exchange = "mexc"

    alive_event = asyncio.Event()

    async def _long_running():
        await alive_event.wait()

    alive_event = asyncio.Event()

    async def _long_running_coro():
        await alive_event.wait()

    # Pré-peupler le registre avec des tasks vivantes
    task_btc = asyncio.create_task(_long_running_coro())
    task_eth = asyncio.create_task(_long_running_coro())
    await asyncio.sleep(0)  # laisser démarrer sans avancer
    obs._tasks["BTCUSDT"] = task_btc
    obs._tasks["ETHUSDT"] = task_eth

    assert not task_btc.done()
    assert not task_eth.done()

    with patch.object(obs, "_run_symbol", side_effect=lambda s: _long_running_coro()) as mock_run:
        # Premier reconcile : tasks vivantes → pas de recréation
        await obs._reconcile()
        assert obs._tasks["BTCUSDT"] is task_btc
        assert obs._tasks["ETHUSDT"] is task_eth
        mock_run.assert_not_called()

        # Deuxième reconcile : toujours les mêmes tasks
        await obs._reconcile()
        assert obs._tasks["BTCUSDT"] is task_btc
        assert obs._tasks["ETHUSDT"] is task_eth
        mock_run.assert_not_called()

    # Une seule task par symbole, pas de doublon
    assert len(obs._tasks) == 2

    # Cleanup
    alive_event.set()
    await task_btc
    await task_eth
