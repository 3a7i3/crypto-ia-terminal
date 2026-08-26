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
    mexc.MEXCFuturesConnector._CONTRACT_SPECS = {
        "TEST_USDT": mexc.ContractSpecification("TEST_USDT", 1.0, "api", 1)
    }
    mexc.MEXCFuturesConnector._CONTRACT_API_LOADED = True
    try:
        conn = mexc.MEXCFuturesConnector()
        levels = [["78835.4", "883", "1"], ["78835.3", "2", "5"]]
        parsed = conn._parse_book_side("TEST_USDT", levels)  # size 1.0 = identite
        assert parsed == [(78835.4, 883.0), (78835.3, 2.0)]
    finally:
        mexc.MEXCFuturesConnector._CONTRACT_SPECS = {}
        mexc.MEXCFuturesConnector._CONTRACT_API_LOADED = False


def test_parse_book_side_skips_malformed():
    mexc.MEXCFuturesConnector._CONTRACT_SPECS = {
        "TEST_USDT": mexc.ContractSpecification("TEST_USDT", 1.0, "api", 1)
    }
    mexc.MEXCFuturesConnector._CONTRACT_API_LOADED = True
    try:
        conn = mexc.MEXCFuturesConnector()
        levels = [["78835.4", "883"], [], ["bad"], ["100.0", "5", "1"]]
        parsed = conn._parse_book_side("TEST_USDT", levels)
        # les niveaux valides passent, les malformes sont ignores
        assert (78835.4, 883.0) in parsed
        assert (100.0, 5.0) in parsed
        assert len(parsed) == 2
    finally:
        mexc.MEXCFuturesConnector._CONTRACT_SPECS = {}
        mexc.MEXCFuturesConnector._CONTRACT_API_LOADED = False


# ---------------------------------------------------------------------------
# Conversion contrats -> base asset -> USD notional (integrite scientifique)
# ---------------------------------------------------------------------------

C = mexc.MEXCFuturesConnector

# contractSize officiels MEXC verifies le 2026-08-26 (curl contract/detail)
OFFICIAL = {
    "BTC_USDT": 0.0001,
    "ETH_USDT": 0.01,
    "SOL_USDT": 0.1,
    "BNB_USDT": 0.01,
    "AVAX_USDT": 0.1,
    "XRP_USDT": 1.0,
    "DOGE_USDT": 100.0,
}


def _reset_specs():
    C._CONTRACT_SPECS = {}
    C._CONTRACT_API_LOADED = False
    C._FALLBACK_LOGGED = set()


def _inject_api_specs(mapping):
    """Simule un chargement API reussi."""
    C._CONTRACT_SPECS = {
        s: mexc.ContractSpecification(s, sz, "api", 1) for s, sz in mapping.items()
    }
    C._CONTRACT_API_LOADED = True


def test_fallback_table_matches_official_values():
    # Le fallback DOIT porter les vraies valeurs (defense de continuite).
    assert mexc._CONTRACT_VALUE == OFFICIAL


def test_per_symbol_conversion_from_api_specs():
    _reset_specs()
    try:
        _inject_api_specs(OFFICIAL)
        conn = C()
        # 100 contrats de chaque symbole -> base asset attendu
        for sym, size in OFFICIAL.items():
            assert abs(conn._contract_to_base(sym, 100, 1.0) - 100 * size) < 1e-12
    finally:
        _reset_specs()


def test_end_to_end_notional_eth():
    """ETH: 100 contrats, size 0.01, prix 2500 -> 1 ETH -> 2500 USD."""
    _reset_specs()
    try:
        _inject_api_specs({"ETH_USDT": 0.01})
        conn = C()
        base = conn._contract_to_base("ETH_USDT", 100, 2500)
        assert abs(base - 1.0) < 1e-12          # 1 ETH
        assert abs(base * 2500 - 2500.0) < 1e-9  # 2500 USD notional
    finally:
        _reset_specs()


def test_end_to_end_notional_btc():
    """BTC: 883 contrats, size 0.0001, prix 78896 -> 0.0883 BTC -> ~6966 USD."""
    _reset_specs()
    try:
        _inject_api_specs({"BTC_USDT": 0.0001})
        conn = C()
        base = conn._contract_to_base("BTC_USDT", 883, 78896)
        assert abs(base - 0.0883) < 1e-9
        assert abs(base * 78896 - 6966.5168) < 1e-2  # notional realiste (pas 69M)
    finally:
        _reset_specs()


def test_invariant_size_is_base_asset_not_contracts():
    """INVARIANT : la size retournee != nombre brut de contrats (sauf size==1)."""
    _reset_specs()
    try:
        _inject_api_specs({"BTC_USDT": 0.0001})
        conn = C()
        raw_contracts = 883
        base = conn._contract_to_base("BTC_USDT", raw_contracts, 78896)
        assert base != raw_contracts
        assert base == raw_contracts * 0.0001
    finally:
        _reset_specs()


def test_spec_source_is_api_when_loaded():
    _reset_specs()
    try:
        _inject_api_specs({"BTC_USDT": 0.0001})
        conn = C()
        assert conn._spec_for("BTC_USDT").source == "api"
    finally:
        _reset_specs()


def test_spec_falls_back_and_is_marked_degraded():
    """Sans API, la conversion utilise le fallback et est marquee degradee."""
    _reset_specs()
    try:
        conn = C()
        spec = conn._spec_for("SOL_USDT")
        assert spec.source == "fallback"
        assert spec.is_degraded is True
        assert spec.contract_size == 0.1  # vraie valeur, pas 1.0
    finally:
        _reset_specs()


def test_provenance_summary():
    _reset_specs()
    try:
        assert C.contract_provenance()["source"] == "unknown"
        _inject_api_specs({"BTC_USDT": 0.0001})
        assert C.contract_provenance()["source"] == "api"
        # une conversion sur un symbole absent de l'API -> mixed
        C()._spec_for("ZZZ_USDT")
        prov = C.contract_provenance()
        assert prov["source"] == "mixed"
        assert "ZZZ_USDT" in prov["degraded_symbols"]
    finally:
        _reset_specs()


def test_ensure_contract_sizes_from_api(monkeypatch):
    """_ensure_contract_sizes parse contract/detail et marque source=api."""
    _reset_specs()
    try:
        fake = {"data": [
            {"symbol": "BTC_USDT", "contractSize": 0.0001},
            {"symbol": "ETH_USDT", "contractSize": 0.01},
        ]}
        conn = C()
        monkeypatch.setattr(conn, "_get_json", lambda *a, **k: fake)
        conn._ensure_contract_sizes()
        assert C._CONTRACT_API_LOADED is True
        assert conn._spec_for("BTC_USDT").source == "api"
        assert conn._spec_for("BTC_USDT").contract_size == 0.0001
    finally:
        _reset_specs()


def test_ensure_contract_sizes_api_failure_stays_degraded(monkeypatch):
    """Si l'API echoue, api_loaded reste False et la conversion degrade."""
    _reset_specs()
    try:
        def boom(*a, **k):
            raise RuntimeError("network down")

        conn = C()
        monkeypatch.setattr(conn, "_get_json", boom)
        conn._ensure_contract_sizes()
        assert C._CONTRACT_API_LOADED is False
        # conversion tombe sur le fallback, marquee degradee
        assert conn._spec_for("ETH_USDT").source == "fallback"
        assert C.contract_provenance()["source"] == "fallback"
    finally:
        _reset_specs()
