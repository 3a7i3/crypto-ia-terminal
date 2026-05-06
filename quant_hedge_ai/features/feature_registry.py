"""
feature_registry.py — Feature Metadata Catalog

Enregistre et décrit chaque feature : source, type, plage attendue,
importance relative. Permet la découverte et la validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class FeatureMeta:
    name: str
    source: str                          # "ohlcv", "microstructure", "onchain", "derived"
    dtype: Literal["float", "int", "bool"] = "float"
    expected_min: float = -1e9
    expected_max: float = 1e9
    description: str = ""
    importance: float = 0.5              # [0,1] : importance relative estimée
    tags: list[str] = field(default_factory=list)


# Catalogue de référence V2
_REGISTRY: dict[str, FeatureMeta] = {
    # --- OHLCV ---
    "rsi_14": FeatureMeta("rsi_14", "ohlcv", expected_min=0, expected_max=100, importance=0.7, description="RSI 14 périodes", tags=["momentum"]),
    "macd_hist": FeatureMeta("macd_hist", "ohlcv", expected_min=-1e4, expected_max=1e4, importance=0.65, description="MACD Histogram", tags=["momentum"]),
    "ema_cross": FeatureMeta("ema_cross", "ohlcv", expected_min=-1, expected_max=1, importance=0.6, description="EMA9/EMA21 crossover signal", tags=["trend"]),
    "bb_position": FeatureMeta("bb_position", "ohlcv", expected_min=0, expected_max=1, importance=0.55, description="Position dans les Bollinger Bands", tags=["volatility"]),
    "atr_pct": FeatureMeta("atr_pct", "ohlcv", expected_min=0, expected_max=0.5, importance=0.6, description="ATR en % du prix", tags=["volatility"]),
    "volume_ratio": FeatureMeta("volume_ratio", "ohlcv", expected_min=0, expected_max=20, importance=0.65, description="Volume vs moyenne 20 périodes", tags=["volume"]),
    "vwap_dist": FeatureMeta("vwap_dist", "ohlcv", expected_min=-0.5, expected_max=0.5, importance=0.6, description="Distance au VWAP", tags=["trend"]),

    # --- Microstructure ---
    "ob_imbalance": FeatureMeta("ob_imbalance", "microstructure", expected_min=-1, expected_max=1, importance=0.85, description="Order book imbalance bid vs ask", tags=["microstructure", "pressure"]),
    "spread_bps": FeatureMeta("spread_bps", "microstructure", expected_min=0, expected_max=50, importance=0.7, description="Spread bid-ask en bps", tags=["microstructure", "liquidity"]),
    "trade_aggressiveness": FeatureMeta("trade_aggressiveness", "microstructure", expected_min=0, expected_max=1, importance=0.8, description="Ratio trades agressifs buy vs total", tags=["microstructure", "pressure"]),
    "liquidity_depth_bps": FeatureMeta("liquidity_depth_bps", "microstructure", expected_min=0, expected_max=1e8, importance=0.75, description="Profondeur de liquidité ±50bps", tags=["microstructure", "liquidity"]),

    # --- Derivatives ---
    "funding_rate": FeatureMeta("funding_rate", "derivatives", expected_min=-0.05, expected_max=0.05, importance=0.8, description="Taux de financement", tags=["derivatives", "sentiment"]),
    "funding_velocity": FeatureMeta("funding_velocity", "derivatives", expected_min=-0.01, expected_max=0.01, importance=0.75, description="Variation du funding sur 4h", tags=["derivatives"]),
    "oi_delta_1h": FeatureMeta("oi_delta_1h", "derivatives", expected_min=-1e9, expected_max=1e9, importance=0.75, description="Delta Open Interest 1h", tags=["derivatives"]),
    "liquidation_risk": FeatureMeta("liquidation_risk", "derivatives", expected_min=0, expected_max=1, importance=0.85, description="Score de risque de liquidation", tags=["derivatives", "risk"]),

    # --- On-chain ---
    "exchange_netflow": FeatureMeta("exchange_netflow", "onchain", importance=0.8, description="Outflow - Inflow exchange USD", tags=["onchain", "sentiment"]),
    "whale_score": FeatureMeta("whale_score", "onchain", expected_min=-1, expected_max=1, importance=0.75, description="Score accumulation baleine", tags=["onchain"]),
    "stablecoin_inflow": FeatureMeta("stablecoin_inflow", "onchain", expected_min=0, expected_max=1e10, importance=0.7, description="Inflow stablecoins USD", tags=["onchain", "sentiment"]),

    # --- Régime ---
    "regime_bull_prob": FeatureMeta("regime_bull_prob", "regime", expected_min=0, expected_max=1, importance=0.9, description="Probabilité régime haussier", tags=["regime"]),
    "regime_bear_prob": FeatureMeta("regime_bear_prob", "regime", expected_min=0, expected_max=1, importance=0.9, description="Probabilité régime baissier", tags=["regime"]),
    "regime_transition_risk": FeatureMeta("regime_transition_risk", "regime", expected_min=0, expected_max=1, importance=0.85, description="Risque de transition de régime imminente", tags=["regime"]),
}


class FeatureRegistry:
    """Catalogue et valide les features du système."""

    def __init__(self) -> None:
        self._registry = dict(_REGISTRY)

    def register(self, meta: FeatureMeta) -> None:
        self._registry[meta.name] = meta

    def get(self, name: str) -> FeatureMeta | None:
        return self._registry.get(name)

    def all_features(self) -> list[str]:
        return list(self._registry.keys())

    def by_tag(self, tag: str) -> list[FeatureMeta]:
        return [m for m in self._registry.values() if tag in m.tags]

    def by_source(self, source: str) -> list[FeatureMeta]:
        return [m for m in self._registry.values() if m.source == source]

    def top_by_importance(self, n: int = 10) -> list[FeatureMeta]:
        sorted_metas = sorted(self._registry.values(), key=lambda m: m.importance, reverse=True)
        return sorted_metas[:n]

    def validate_value(self, name: str, value: float) -> bool:
        meta = self._registry.get(name)
        if meta is None:
            return True
        return meta.expected_min <= value <= meta.expected_max
