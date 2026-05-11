"""
feature_materializer.py — Feature Computation Pipeline

Orchestre le calcul complet des features depuis les données brutes :
OHLCV → features techniques + microstructure + dérivés + on-chain.
Utilise le FeatureStore pour le cache et la détection de recalcul.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FeatureMaterializer:
    """
    Pipeline de matérialisation des features.
    Appelle le FeatureEngineer existant + enrichit avec
    les données V2 (microstructure, dérivés, on-chain, régime).
    """

    def __init__(
        self,
        store,
        validator=None,
        feature_engineer=None,
    ) -> None:
        self._store = store
        self._validator = validator
        self._engineer = feature_engineer  # FeatureEngineer V1 (réutilisé)

    def materialize(
        self,
        symbol: str,
        timeframe: str,
        candles: list,
        market_snapshot=None,
        force: bool = False,
    ) -> dict[str, float]:
        """
        Calcule et stocke les features pour (symbol, timeframe).
        Utilise le cache si les candles n'ont pas changé.
        """
        if not force and not self._store.needs_recompute(symbol, timeframe, candles):
            cached = self._store.get(symbol, timeframe)
            if cached:
                logger.debug("[Materializer] %s/%s — cache hit", symbol, timeframe)
                return cached.features

        features: dict[str, float] = {}

        # 1. Features techniques via FeatureEngineer V1
        if self._engineer and candles:
            try:
                eng_features = self._engineer.extract_features(candles)
                features.update(eng_features)
            except Exception as exc:
                logger.warning("[Materializer] FeatureEngineer error: %s", exc)

        # 2. Features techniques directes si pas d'engineer
        if not features and candles and len(candles) >= 20:
            features.update(self._compute_basic_features(candles))

        # 3. Enrichissement depuis MarketSnapshot V2
        if market_snapshot:
            features.update(self._extract_snapshot_features(market_snapshot))

        # 4. Validation et nettoyage
        if self._validator and features:
            report = self._validator.validate(features, symbol)
            features = report.cleaned

        # 5. Stockage dans le store
        if features:
            self._store.put(symbol, timeframe, features, candles)

        return features

    def materialize_all(
        self,
        symbols: list[str],
        candles_by_symbol: dict[str, list],
        snapshots_by_symbol: dict | None = None,
        timeframe: str = "1h",
    ) -> dict[str, dict[str, float]]:
        result = {}
        for symbol in symbols:
            candles = candles_by_symbol.get(symbol, [])
            snap = (snapshots_by_symbol or {}).get(symbol)
            result[symbol] = self.materialize(symbol, timeframe, candles, snap)
        return result

    # ------------------------------------------------------------------
    # Calcul features de base (fallback sans FeatureEngineer)
    # ------------------------------------------------------------------

    def _compute_basic_features(self, candles: list) -> dict[str, float]:
        closes = [c[4] for c in candles if len(c) >= 5]
        volumes = [c[5] for c in candles if len(c) >= 6]
        if len(closes) < 14:
            return {}

        features: dict[str, float] = {}

        # RSI 14
        features["rsi_14"] = self._rsi(closes, 14)

        # EMA cross (9 vs 21)
        if len(closes) >= 21:
            ema9 = self._ema(closes, 9)
            ema21 = self._ema(closes, 21)
            features["ema_cross"] = 1.0 if ema9 > ema21 else -1.0

        # ATR %
        if len(candles) >= 15:
            highs = [c[2] for c in candles if len(c) >= 5]
            lows = [c[3] for c in candles if len(c) >= 5]
            atr = self._atr(highs, lows, closes, 14)
            features["atr_pct"] = atr / closes[-1] if closes[-1] else 0.0

        # Volume ratio
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            features["volume_ratio"] = volumes[-1] / avg_vol if avg_vol else 1.0

        return features

    def _extract_snapshot_features(self, snap) -> dict[str, float]:
        return {
            "ob_imbalance": snap.order_book_imbalance,
            "spread_bps": snap.bid_ask_spread * 10000,
            "trade_aggressiveness": snap.trade_aggressiveness,
            "funding_rate": snap.funding_rate,
            "funding_velocity": snap.funding_velocity,
            "oi_delta_1h": snap.open_interest_delta_1h,
            "liquidation_risk": snap.liquidation_risk_score,
            "exchange_netflow": (snap.exchange_outflow_usd - snap.exchange_inflow_usd) / 1e6,
            "whale_score": snap.whale_accumulation_score,
            "regime_bull_prob": snap.regime_bull_prob,
            "regime_bear_prob": snap.regime_bear_prob,
        }

    # ------------------------------------------------------------------
    # Helpers calcul technique
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0.0
        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in deltas[-period:]]
        losses = [abs(min(d, 0)) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
        if len(highs) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        return sum(trs[-period:]) / period
