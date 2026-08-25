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


def test_parse_book_side_contract_format():
    """Format /edge : niveaux [price, vol_contrats, nb_ordres]."""
    conn = mexc.MEXCFuturesConnector()
    levels = [["78835.4", "883", "1"], ["78835.3", "2", "5"]]
    parsed = conn._parse_book_side("BTC_USDT", levels)
    assert parsed == [(78835.4, 883.0), (78835.3, 2.0)]


def test_parse_book_side_skips_malformed():
    conn = mexc.MEXCFuturesConnector()
    levels = [["78835.4", "883"], [], ["bad"], ["100.0", "5", "1"]]
    parsed = conn._parse_book_side("BTC_USDT", levels)
    # les niveaux valides passent, les malformes sont ignores
    assert (78835.4, 883.0) in parsed
    assert (100.0, 5.0) in parsed
    assert len(parsed) == 2


def test_contract_to_base_uses_contract_size_cache():
    conn = mexc.MEXCFuturesConnector()
    saved = dict(mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE)
    try:
        mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE = {"BTC_USDT": 0.0001}
        # 883 contrats * 0.0001 BTC = 0.0883 BTC (pas 883 !)
        assert abs(conn._contract_to_base("BTC_USDT", 883, 78896) - 0.0883) < 1e-9
    finally:
        mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE = saved


def test_contract_to_base_fallback_when_unknown():
    conn = mexc.MEXCFuturesConnector()
    saved = dict(mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE)
    try:
        mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE = {}
        # symbole absent du cache et de la table -> facteur 1.0
        assert conn._contract_to_base("FOO_USDT", 10, 1.0) == 10.0
    finally:
        mexc.MEXCFuturesConnector._CONTRACT_SIZE_CACHE = saved
