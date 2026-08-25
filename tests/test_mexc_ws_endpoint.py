"""Regression test: MEXC Futures WebSocket endpoint.

L'ancien endpoint /ws redirige vers une page 404 (scheme https) et casse
la lib websockets. Ce test verrouille l'endpoint /edge et la presence du
keepalive applicatif (sans lequel MEXC ferme la connexion inactive).
"""

import inspect

from market_data.connectors import mexc


def test_ws_endpoint_is_edge():
    assert mexc._WS == "wss://contract.mexc.com/edge"
    assert "/ws" not in mexc._WS.rsplit("/", 1)[0]


def test_keepalive_is_coroutine():
    conn = mexc.MEXCFuturesConnector()
    assert inspect.iscoroutinefunction(conn._keepalive)


def test_ping_interval_positive():
    assert mexc._PING_INTERVAL_S > 0


def test_stream_methods_are_async_generators():
    conn = mexc.MEXCFuturesConnector()
    assert inspect.isasyncgenfunction(conn.stream_trades)
    assert inspect.isasyncgenfunction(conn.stream_orderbook)
