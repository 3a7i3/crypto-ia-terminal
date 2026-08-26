"""
market_data/connectors/mexc.py — Connecteur MEXC Futures (USDT-M).

REST  : https://contract.mexc.com/api/v1/contract/
WS    : wss://contract.mexc.com/ws

Particularites MEXC :
  - API Futures differente du Spot (contract.mexc.com vs api.mexc.com)
  - Timestamp en secondes (pas ms) pour certains endpoints -> normaliser * 1000
  - Symboles format "BTC_USDT" -> normaliser vers "BTCUSDT"
  - Volume en contrats (pas en base asset) -> convertir selon contract_value
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from market_data.connectors.base import BaseConnector
from market_data.models import NormalizedCandle, NormalizedOrderBook, NormalizedTrade

_BASE = "https://contract.mexc.com/api/v1/contract"
# Endpoint WS Futures MEXC : l'ancien /ws redirige desormais vers une page
# 404 (scheme https), ce qui casse la lib websockets. Le point d'entree
# courant est /edge. Keepalive applicatif obligatoire (ping toutes les ~15s)
# sinon le serveur ferme la connexion inactive.
_WS = "wss://contract.mexc.com/edge"
_PING_INTERVAL_S = 15.0

_TF_MAP = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "1d": "Day1",
}

# Taille d'un contrat (base asset par contrat) — FALLBACK UNIQUEMENT.
#
# Ce n'est PAS la source d'autorite : la source primaire est l'API MEXC
# contract/detail (voir _ensure_contract_sizes). Cette table ne sert que de
# defense de continuite si l'API est injoignable. Toute conversion basee sur
# elle est marquee source="fallback" et loggee en ERROR (donnee degradee).
#
# Valeurs verifiees le 2026-08-26 contre contract/detail. A ne pas prendre
# pour une verite permanente — MEXC peut changer un contractSize.
_CONTRACT_VALUE: dict[str, float] = {
    "BTC_USDT": 0.0001,
    "ETH_USDT": 0.01,
    "SOL_USDT": 0.1,
    "BNB_USDT": 0.01,
    "AVAX_USDT": 0.1,
    "XRP_USDT": 1.0,
    "DOGE_USDT": 100.0,
}


@dataclass
class ContractSpecification:
    """
    Identite scientifique d'un contrat : sa taille et sa provenance.

    source = "api"      : contractSize lu depuis MEXC contract/detail (autorite)
    source = "fallback" : table statique de continuite (donnee DEGRADEE)
    """

    symbol: str
    contract_size: float
    source: str  # "api" | "fallback"
    fetched_at_ms: int

    @property
    def is_degraded(self) -> bool:
        return self.source != "api"

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "contract_size": self.contract_size,
            "source": self.source,
            "fetched_at_ms": self.fetched_at_ms,
        }


class MEXCFuturesConnector(BaseConnector):

    exchange_name = "mexc"
    base_url = _BASE
    ws_url = _WS

    def _mexc_symbol(self, symbol: str) -> str:
        """Convertit "BTCUSDT" -> "BTC_USDT" pour MEXC Futures."""
        s = symbol.upper()
        # Insere le _ avant USDT/USDC si absent
        for quote in ("USDT", "USDC", "BTC", "ETH"):
            if s.endswith(quote) and "_" not in s:
                return s[: -len(quote)] + "_" + quote
        return s

    def _normalize_symbol(self, mexc_sym: str) -> str:
        """Inverse : "BTC_USDT" -> "BTCUSDT"."""
        return mexc_sym.replace("_", "").upper()

    # Registre partage (classe) des specifications de contrat, avec provenance.
    _CONTRACT_SPECS: dict[str, ContractSpecification] = {}
    _CONTRACT_API_LOADED: bool = False
    _FALLBACK_LOGGED: set[str] = set()

    def _ensure_contract_sizes(self) -> None:
        """
        Charge contractSize par symbole depuis l'API MEXC (source d'autorite).

        Rempli une seule fois par process (cache classe). Chaque entree est
        marquee source="api". Si l'API echoue, on logge en ERROR : les
        conversions retomberont sur le fallback (donnee degradee, tracee).

        Idempotent et sur-appelable : REST et WS l'invoquent tous les deux.
        """
        if MEXCFuturesConnector._CONTRACT_API_LOADED:
            return
        try:
            resp = self._get_json(f"{_BASE}/detail")
            data = resp.get("data", []) if isinstance(resp, dict) else []
            now = int(time.time() * 1000)
            specs: dict[str, ContractSpecification] = {}
            for c in data:
                sym = c.get("symbol")
                size = c.get("contractSize")
                if sym and size:
                    specs[str(sym)] = ContractSpecification(
                        symbol=str(sym),
                        contract_size=float(size),
                        source="api",
                        fetched_at_ms=now,
                    )
            if specs:
                MEXCFuturesConnector._CONTRACT_SPECS = specs
                MEXCFuturesConnector._CONTRACT_API_LOADED = True
            else:
                self._log.error(
                    "MEXC contract/detail returned no usable contractSize — "
                    "conversions will use DEGRADED fallback values"
                )
        except Exception as exc:
            self._log.error(
                "MEXC contract/detail fetch FAILED (%s) — conversions will use "
                "DEGRADED fallback values",
                exc,
            )

    def _spec_for(self, symbol_mexc: str) -> ContractSpecification:
        """
        Retourne la ContractSpecification d'un symbole.

        Priorite : registre API. Sinon fallback statique (source="fallback",
        loggue une fois en ERROR par symbole) — la donnee est alors degradee
        mais scientifiquement identifiable comme telle.
        """
        spec = MEXCFuturesConnector._CONTRACT_SPECS.get(symbol_mexc)
        if spec is not None and spec.source == "api":
            return spec
        size = _CONTRACT_VALUE.get(symbol_mexc, 1.0)
        spec = ContractSpecification(
            symbol=symbol_mexc,
            contract_size=size,
            source="fallback",
            fetched_at_ms=int(time.time() * 1000),
        )
        MEXCFuturesConnector._CONTRACT_SPECS[symbol_mexc] = spec
        if symbol_mexc not in MEXCFuturesConnector._FALLBACK_LOGGED:
            MEXCFuturesConnector._FALLBACK_LOGGED.add(symbol_mexc)
            self._log.error(
                "contract size FALLBACK for %s = %s (no API metadata) — "
                "downstream USD metrics for this symbol are DEGRADED",
                symbol_mexc,
                size,
            )
        return spec

    def _contract_to_base(
        self, symbol_mexc: str, contracts: float, price: float
    ) -> float:
        """
        Convertit un volume en contrats -> quantite BASE ASSET.

        INVARIANT : la valeur retournee est toujours en actif de base
        (BTC, ETH, SOL...), jamais un nombre brut de contrats.
        base = contracts * contract_size.
        """
        return contracts * self._spec_for(symbol_mexc).contract_size

    @classmethod
    def contract_provenance(cls) -> dict:
        """
        Resume de provenance des contractSize utilises (pour le sidecar/audit).

        source globale : "api" (tout API), "fallback" (tout fallback),
        "mixed" (les deux), "unknown" (rien encore charge).
        """
        specs = cls._CONTRACT_SPECS
        n_api = sum(1 for s in specs.values() if s.source == "api")
        n_fb = sum(1 for s in specs.values() if s.source == "fallback")
        if not specs:
            source = "unknown"
        elif n_fb == 0:
            source = "api"
        elif n_api == 0:
            source = "fallback"
        else:
            source = "mixed"
        return {
            "source": source,
            "api_loaded": cls._CONTRACT_API_LOADED,
            "n_api": n_api,
            "n_fallback": n_fb,
            "degraded_symbols": sorted(
                s.symbol for s in specs.values() if s.is_degraded
            ),
        }

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    def fetch_trades(self, symbol: str, limit: int = 100) -> list[NormalizedTrade]:
        self._ensure_contract_sizes()  # charge la spec contrat (REST aussi)
        sym = self._mexc_symbol(symbol)
        data = self._get_json(f"{_BASE}/deals/{sym}", {"limit": min(limit, 100)})
        trades = []
        result_data = data.get("data", {})
        deals = (
            result_data.get("resultList", result_data)
            if isinstance(result_data, dict)
            else result_data
        )
        for t in deals[:limit]:
            # MEXC: {"p": price, "v": volume, "T": side (1=buy,2=sell), "O": timestamp_s}
            side_raw = int(t.get("T", t.get("takerSide", 1)))
            side = "buy" if side_raw == 1 else "sell"
            ts = int(t.get("t", t.get("O", time.time())))
            ts_ms = ts if ts > 1e12 else ts * 1000  # normaliser vers ms
            price = float(t.get("p", 0))
            size_raw = float(t.get("v", 0))
            trades.append(
                NormalizedTrade(
                    exchange=self.exchange_name,
                    symbol=self._normalize_symbol(sym),
                    timestamp_ms=ts_ms,
                    price=price,
                    size=self._contract_to_base(sym, size_raw, price),
                    side=side,
                    trade_id=str(t.get("id", "")),
                    raw=t,
                )
            )
        return trades

    def fetch_orderbook(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        self._ensure_contract_sizes()  # charge la spec contrat (REST aussi)
        sym = self._mexc_symbol(symbol)
        data = self._get_json(f"{_BASE}/depth/{sym}", {"limit": min(depth, 150)})
        book_data = data.get("data", data)
        # Volumes en contrats -> base asset (coherent avec le chemin WS)
        bids = [
            (float(p), self._contract_to_base(sym, float(s), float(p)))
            for p, s in zip(book_data.get("bids", []), book_data.get("bidVols", []))
        ]
        asks = [
            (float(p), self._contract_to_base(sym, float(s), float(p)))
            for p, s in zip(book_data.get("asks", []), book_data.get("askVols", []))
        ]
        # Assurer le tri correct
        bids = sorted(bids, key=lambda x: x[0], reverse=True)
        asks = sorted(asks, key=lambda x: x[0])
        ts = int(book_data.get("timestamp", time.time() * 1000))
        return NormalizedOrderBook(
            exchange=self.exchange_name,
            symbol=self._normalize_symbol(sym),
            timestamp_ms=ts if ts > 1e12 else ts * 1000,
            bids=bids,
            asks=asks,
            is_snapshot=True,
        )

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> list[NormalizedCandle]:
        sym = self._mexc_symbol(symbol)
        tf = _TF_MAP.get(timeframe, "Min1")
        params: dict = {"interval": tf}
        if start_ms:
            params["start"] = start_ms // 1000  # MEXC attend des secondes
        if end_ms:
            params["end"] = end_ms // 1000

        data = self._get_json(f"{_BASE}/kline/{sym}", params)
        klines = data.get("data", {})
        opens = klines.get("open", [])
        highs = klines.get("high", [])
        lows = klines.get("low", [])
        closes = klines.get("close", [])
        vols = klines.get("vol", [])
        times = klines.get("time", [])
        buy_vols = klines.get("buyVol", [0] * len(opens))

        candles = []
        for i in range(min(len(opens), limit)):
            ts = int(times[i]) if i < len(times) else 0
            ts_ms = ts if ts > 1e12 else ts * 1000
            volume = float(vols[i]) if i < len(vols) else 0.0
            buy_vol = float(buy_vols[i]) if i < len(buy_vols) else 0.0
            candles.append(
                NormalizedCandle(
                    exchange=self.exchange_name,
                    symbol=self._normalize_symbol(sym),
                    timestamp_ms=ts_ms,
                    timeframe=timeframe,
                    open=float(opens[i]),
                    high=float(highs[i]) if i < len(highs) else 0.0,
                    low=float(lows[i]) if i < len(lows) else 0.0,
                    close=float(closes[i]) if i < len(closes) else 0.0,
                    volume=volume,
                    buy_volume=buy_vol,
                    sell_volume=volume - buy_vol,
                    is_closed=True,
                )
            )
        return candles

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def _keepalive(self, ws) -> None:
        """Ping applicatif MEXC toutes les ~15s (sinon le serveur ferme)."""
        try:
            while True:
                await asyncio.sleep(_PING_INTERVAL_S)
                await ws.send(json.dumps({"method": "ping"}))
        except asyncio.CancelledError:
            raise
        except Exception:  # connexion fermee : le stream s'arrete de lui-meme
            return

    def _parse_book_side(self, sym: str, levels: list) -> list[tuple[float, float]]:
        """
        Parse un cote du book MEXC Futures (/edge).

        Format contrat : chaque niveau = [price, volume_contrats, nb_ordres].
        Le volume est converti en base asset. Tolerant aux niveaux malformes.
        """
        out: list[tuple[float, float]] = []
        for lvl in levels:
            try:
                price = float(lvl[0])
                vol_contracts = float(lvl[1])
            except (TypeError, ValueError, IndexError):
                continue
            out.append((price, self._contract_to_base(sym, vol_contracts, price)))
        return out

    async def stream_trades(self, symbol: str) -> AsyncGenerator[NormalizedTrade, None]:
        """Stream trades MEXC Futures. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        await asyncio.get_event_loop().run_in_executor(
            None, self._ensure_contract_sizes
        )
        sym = self._mexc_symbol(symbol)
        sub = json.dumps({"method": "sub.deal", "param": {"symbol": sym}})

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            ping_task = asyncio.create_task(self._keepalive(ws))
            try:
                async for msg in ws:
                    payload = json.loads(msg)
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("channel") != "push.deal":
                        continue
                    # /edge : data est une LISTE de deals (pas {"deals": [...]})
                    deals = payload.get("data", [])
                    if isinstance(deals, dict):  # tolerance ancien format
                        deals = deals.get("deals", [])
                    for t in deals:
                        side_raw = int(t.get("T", 1))
                        ts = int(t.get("t", time.time() * 1000))
                        price = float(t.get("p", 0))
                        size_raw = float(t.get("v", 0))
                        yield NormalizedTrade(
                            exchange=self.exchange_name,
                            symbol=self._normalize_symbol(sym),
                            timestamp_ms=ts if ts > 1e12 else ts * 1000,
                            price=price,
                            size=self._contract_to_base(sym, size_raw, price),
                            side="buy" if side_raw == 1 else "sell",
                            raw=t,
                        )
            finally:
                ping_task.cancel()

    async def stream_orderbook(
        self, symbol: str, depth: int = 20
    ) -> AsyncGenerator[NormalizedOrderBook, None]:
        """Stream depth MEXC Futures. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        await asyncio.get_event_loop().run_in_executor(
            None, self._ensure_contract_sizes
        )
        sym = self._mexc_symbol(symbol)
        sub = json.dumps({"method": "sub.depth", "param": {"symbol": sym}})

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            ping_task = asyncio.create_task(self._keepalive(ws))
            try:
                async for msg in ws:
                    payload = json.loads(msg)
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("channel") != "push.depth":
                        continue
                    d = payload.get("data", {})
                    bids = sorted(
                        self._parse_book_side(sym, d.get("bids", [])),
                        reverse=True,
                    )[:depth]
                    asks = sorted(
                        self._parse_book_side(sym, d.get("asks", []))
                    )[:depth]
                    ts = int(d.get("timestamp", time.time() * 1000))
                    yield NormalizedOrderBook(
                        exchange=self.exchange_name,
                        symbol=self._normalize_symbol(sym),
                        timestamp_ms=ts if ts > 1e12 else ts * 1000,
                        bids=bids,
                        asks=asks,
                        is_snapshot=False,
                    )
            finally:
                ping_task.cancel()
