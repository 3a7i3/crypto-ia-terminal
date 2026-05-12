"""
blockchain_ingester.py — On-Chain Data Ingestion

Agrège les données on-chain depuis plusieurs sources avec fallback gracieux.
Sources supportées :
  - CryptoQuant (exchange flows)
  - Glassnode (supply metrics)
  - Coinglass (liquidations, OI)
  - Fallback synthétique si APIs indisponibles
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OnChainData:
    symbol: str
    timestamp: float = field(default_factory=time.time)

    # Exchange flows
    exchange_inflow_usd: float = 0.0
    exchange_outflow_usd: float = 0.0
    net_flow_usd: float = 0.0           # outflow - inflow : positif = accumulation

    # Whale activity
    large_tx_count: int = 0             # transactions >100k USD dernière heure
    whale_inflow_usd: float = 0.0
    whale_outflow_usd: float = 0.0

    # Supply metrics
    supply_in_profit_pct: float = 0.5
    active_addresses_24h: int = 0
    dormancy_flow: float = 0.0          # coins anciens qui bougent = distribution

    # Stablecoins
    stablecoin_inflow_usd: float = 0.0  # stablecoins entrant en exchange = risk-on

    # Sentiment on-chain
    net_sentiment: float = 0.0          # [-1,+1] synthèse on-chain

    # Qualité
    source: str = "synthetic"
    confidence: float = 0.5             # [0,1]

    def is_bullish(self) -> bool:
        return self.net_flow_usd > 0 and self.stablecoin_inflow_usd > 0

    def is_bearish(self) -> bool:
        return self.net_flow_usd < 0 and self.dormancy_flow > 0.5


class BlockchainIngester:
    """
    Fetch les données on-chain depuis les APIs disponibles.
    Dégrade gracieusement vers des données synthétiques si les APIs échouent.
    Architecture: essaie CryptoQuant → Glassnode → Coinglass → synthetic
    """

    # Seuils de fraîcheur (secondes)
    CACHE_TTL = 3600    # 1h pour les données on-chain (changent lentement)

    def __init__(self, api_keys: dict[str, str] | None = None) -> None:
        self._api_keys = api_keys or {}
        self._cache: dict[str, OnChainData] = {}
        self._last_fetch: dict[str, float] = {}

    def fetch(self, symbol: str, asset: str = "BTC") -> OnChainData:
        """
        Retourne les données on-chain les plus fraîches disponibles.
        Utilise le cache si les données sont récentes.
        """
        cached = self._cache.get(symbol)
        if cached and (time.time() - self._last_fetch.get(symbol, 0)) < self.CACHE_TTL:
            return cached

        data = None

        # Essai source 1: CryptoQuant (exchange flows)
        if self._api_keys.get("cryptoquant"):
            data = self._fetch_cryptoquant(symbol, asset)

        # Essai source 2: Glassnode
        if data is None and self._api_keys.get("glassnode"):
            data = self._fetch_glassnode(symbol, asset)

        # Fallback synthétique
        if data is None:
            data = self._synthetic_data(symbol)

        # Calcul sentiment synthétique
        data.net_sentiment = self._compute_sentiment(data)

        self._cache[symbol] = data
        self._last_fetch[symbol] = time.time()
        return data

    def fetch_all(self, symbols: list[str]) -> dict[str, OnChainData]:
        return {s: self.fetch(s, asset=s.split("/")[0]) for s in symbols}

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def _fetch_cryptoquant(self, symbol: str, asset: str) -> OnChainData | None:
        """Fetch CryptoQuant exchange flow data."""
        try:
            import requests
            key = self._api_keys["cryptoquant"]
            base = asset.lower()
            url = f"https://api.cryptoquant.com/v1/{base}/exchange-flows/inflow"
            resp = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=5)
            if resp.status_code == 200:
                raw = resp.json()
                inflow = float(raw.get("result", {}).get("value", 0))
                outflow_resp = requests.get(
                    f"https://api.cryptoquant.com/v1/{base}/exchange-flows/outflow",
                    headers={"Authorization": f"Bearer {key}"}, timeout=5
                )
                outflow = float(outflow_resp.json().get("result", {}).get("value", 0)) if outflow_resp.ok else 0.0
                return OnChainData(
                    symbol=symbol,
                    exchange_inflow_usd=inflow * 1e3,
                    exchange_outflow_usd=outflow * 1e3,
                    net_flow_usd=(outflow - inflow) * 1e3,
                    source="cryptoquant",
                    confidence=0.9,
                )
        except Exception as exc:
            logger.debug("[BlockchainIngester] CryptoQuant error: %s", exc)
        return None

    def _fetch_glassnode(self, symbol: str, asset: str) -> OnChainData | None:
        """Fetch Glassnode supply metrics."""
        try:
            import requests
            key = self._api_keys["glassnode"]
            ticker = asset.lower()
            url = "https://api.glassnode.com/v1/metrics/supply/profit_relative"
            resp = requests.get(url, params={"a": ticker, "api_key": key}, timeout=5)
            if resp.status_code == 200:
                items = resp.json()
                profit_pct = float(items[-1]["v"]) if items else 0.5
                return OnChainData(
                    symbol=symbol,
                    supply_in_profit_pct=profit_pct,
                    source="glassnode",
                    confidence=0.8,
                )
        except Exception as exc:
            logger.debug("[BlockchainIngester] Glassnode error: %s", exc)
        return None

    def _synthetic_data(self, symbol: str) -> OnChainData:
        """Données synthétiques neutres (fallback total)."""
        return OnChainData(
            symbol=symbol,
            exchange_inflow_usd=50_000_000,
            exchange_outflow_usd=50_000_000,
            net_flow_usd=0.0,
            supply_in_profit_pct=0.6,
            stablecoin_inflow_usd=100_000_000,
            source="synthetic",
            confidence=0.2,
        )

    def _compute_sentiment(self, data: OnChainData) -> float:
        """Score de sentiment on-chain [-1, +1]."""
        score = 0.0
        # Net flow : outflow > inflow = accum = bullish
        if data.exchange_inflow_usd > 0:
            flow_ratio = (data.exchange_outflow_usd - data.exchange_inflow_usd) / (
                data.exchange_inflow_usd + data.exchange_outflow_usd
            )
            score += flow_ratio * 0.4
        # Supply in profit : >70% = bullish, <30% = bearish
        if data.supply_in_profit_pct > 0.7:
            score += 0.3
        elif data.supply_in_profit_pct < 0.3:
            score -= 0.3
        # Stablecoin inflow = risk-on = bullish
        if data.stablecoin_inflow_usd > 200_000_000:
            score += 0.3
        # Dormancy = distribution = bearish
        score -= data.dormancy_flow * 0.2
        return max(-1.0, min(1.0, score))
