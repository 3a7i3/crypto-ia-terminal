"""
signal_engine_mvp.py — Signal Engine MVP

3 signaux seulement. Pas plus. Chacun a un rôle clair :

  1. MOMENTUM     — suivre une tendance établie
  2. MEAN_REVERT  — capter un retour à la moyenne
  3. BREAKOUT     — capter une rupture de liquidité

Modèle : LightGBM entraîné en ligne sur features simples.
Fallback heuristique si pas assez de données pour ML.

Chaque signal retourne : direction, score [0-100], confiance [0-1].
"""
from __future__ import annotations

import json
import logging
import pickle
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_DIR = Path("databases/mvp_models")


class SignalType(str, Enum):
    MOMENTUM    = "momentum"
    MEAN_REVERT = "mean_revert"
    BREAKOUT    = "breakout"
    NONE        = "none"


@dataclass
class MVPSignal:
    symbol: str
    signal_type: SignalType
    direction: str          # "long" | "short" | "neutral"
    score: float            # [0, 100]
    confidence: float       # [0, 1]
    timestamp: float = field(default_factory=time.time)
    features_used: dict[str, float] = field(default_factory=dict)
    model_source: str = "heuristic"   # "heuristic" | "lightgbm"
    reasoning: str = ""

    @property
    def actionable(self) -> bool:
        return self.score >= 60 and self.confidence >= 0.45 and self.direction != "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type": self.signal_type.value,
            "direction": self.direction,
            "score": round(self.score, 1),
            "confidence": round(self.confidence, 3),
            "actionable": self.actionable,
            "model": self.model_source,
            "reasoning": self.reasoning,
        }


class SignalEngineMVP:
    """
    Génère les 3 signaux MVP.

    Phase 1 : heuristiques claires, auditables.
    Phase 2 : LightGBM entraîné en ligne remplace progressivement les heuristiques.

    La transition heuristique → ML se fait automatiquement quand
    le modèle a >= MIN_SAMPLES_ML trades labellisés.
    """

    MIN_SAMPLES_ML = 100     # trades minimum avant d'activer LightGBM
    RETRAIN_EVERY  = 50      # refit tous les 50 nouveaux trades

    def __init__(self) -> None:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        # Buffers d'entraînement par type de signal
        self._train_X: dict[str, deque] = {t.value: deque(maxlen=2000) for t in SignalType if t != SignalType.NONE}
        self._train_y: dict[str, deque] = {t.value: deque(maxlen=2000) for t in SignalType if t != SignalType.NONE}
        self._models:  dict[str, Any]   = {}
        self._n_since_retrain: int = 0
        self._load_models()

    # ──────────────────────────────────────────────────────────────────────────
    # API principale
    # ──────────────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        symbol: str,
        candles_1h: list,
        market_state=None,
        candles_4h: list | None = None,
    ) -> list[MVPSignal]:
        """Retourne la liste des signaux actifs (peut être vide si rien d'actionable)."""
        if not candles_1h or len(candles_1h) < 30:
            return []

        features = self._build_features(candles_1h, candles_4h)
        if not features:
            return []

        signals = [
            self._momentum_signal(symbol, features, market_state),
            self._mean_revert_signal(symbol, features, market_state),
            self._breakout_signal(symbol, features, market_state),
        ]

        # Filtre par marché : désactiver mean-revert en tendance forte,
        # désactiver momentum en chop
        signals = self._apply_market_filter(signals, market_state)

        active = [s for s in signals if s.signal_type != SignalType.NONE]
        if active:
            best = max(active, key=lambda s: s.score)
            logger.debug("[SignalMVP] %s best=%s score=%.0f conf=%.0%",
                         symbol, best.signal_type.value, best.score, best.confidence)
        return active

    def best_signal(
        self,
        symbol: str,
        candles_1h: list,
        market_state=None,
        candles_4h: list | None = None,
    ) -> MVPSignal | None:
        signals = self.evaluate(symbol, candles_1h, market_state, candles_4h)
        actionable = [s for s in signals if s.actionable]
        if not actionable:
            return None
        return max(actionable, key=lambda s: s.score * s.confidence)

    def record_outcome(
        self,
        signal_type: str,
        features: dict[str, float],
        direction: str,
        pnl_pct: float,
    ) -> None:
        """Enregistre un résultat pour l'entraînement ML."""
        label = 1 if pnl_pct > 0 else 0
        feat_vec = self._dict_to_vector(features)
        if signal_type in self._train_X:
            self._train_X[signal_type].append(feat_vec)
            self._train_y[signal_type].append(label)
        self._n_since_retrain += 1
        if self._n_since_retrain >= self.RETRAIN_EVERY:
            self._fit_all()
            self._n_since_retrain = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Signaux heuristiques (Phase 1 — toujours actifs comme fallback)
    # ──────────────────────────────────────────────────────────────────────────

    def _momentum_signal(self, symbol: str, features: dict, market_state) -> MVPSignal:
        """
        Momentum continuation.
        Conditions : EMA cross bullish/bearish + RSI dans zone saine + volume confirmé.
        """
        ema_cross   = features.get("ema_cross_21_55", 0.0)
        rsi         = features.get("rsi_14", 50.0)
        vol_ratio   = features.get("volume_ratio_20", 1.0)
        macd_hist   = features.get("macd_hist", 0.0)
        slope_10    = features.get("price_slope_10", 0.0)

        # Long momentum
        if ema_cross > 0 and 45 < rsi < 72 and vol_ratio > 0.8:
            base_score  = 40.0
            base_score += min(ema_cross * 1000, 20)
            base_score += max(0, (rsi - 50) * 0.5)
            base_score += min(vol_ratio * 5, 10)
            base_score += (1 if macd_hist > 0 else 0) * 8
            direction  = "long"
            confidence = self._ml_confidence("momentum", features, base_score)
            return MVPSignal(symbol, SignalType.MOMENTUM, direction,
                             min(base_score, 95), confidence,
                             features_used=features,
                             model_source="lightgbm" if "momentum" in self._models else "heuristic",
                             reasoning=f"EMA_cross={ema_cross:.4f} RSI={rsi:.0f} vol×{vol_ratio:.1f}")

        # Short momentum
        if ema_cross < 0 and 28 < rsi < 55 and vol_ratio > 0.8:
            base_score  = 40.0
            base_score += min(abs(ema_cross) * 1000, 20)
            base_score += max(0, (50 - rsi) * 0.5)
            base_score += min(vol_ratio * 5, 10)
            base_score += (1 if macd_hist < 0 else 0) * 8
            direction  = "short"
            confidence = self._ml_confidence("momentum", features, base_score)
            return MVPSignal(symbol, SignalType.MOMENTUM, direction,
                             min(base_score, 95), confidence,
                             features_used=features,
                             model_source="lightgbm" if "momentum" in self._models else "heuristic",
                             reasoning=f"EMA_cross={ema_cross:.4f} RSI={rsi:.0f} vol×{vol_ratio:.1f}")

        return MVPSignal(symbol, SignalType.NONE, "neutral", 0, 0)

    def _mean_revert_signal(self, symbol: str, features: dict, market_state) -> MVPSignal:
        """
        Mean reversion.
        Conditions : Prix aux extrêmes des Bollinger Bands + RSI oversold/overbought
                     + volatilité normale (pas d'expansion de tendance).
        """
        bb_pos  = features.get("bb_position", 0.5)     # 0=bas bande, 1=haut bande
        rsi     = features.get("rsi_14", 50.0)
        atr_pct = features.get("atr_pct_14", 0.01)
        vwap_dist = features.get("vwap_dist", 0.0)

        # Long mean-revert : prix sous la bande basse
        if bb_pos < 0.1 and rsi < 35 and atr_pct < 0.04:
            score = 50 + (35 - rsi) * 1.2 + (0.1 - bb_pos) * 200
            score += (1 if vwap_dist < -0.01 else 0) * 10
            confidence = self._ml_confidence("mean_revert", features, score)
            return MVPSignal(symbol, SignalType.MEAN_REVERT, "long",
                             min(score, 92), confidence,
                             features_used=features,
                             reasoning=f"BB={bb_pos:.2f} RSI={rsi:.0f} vwap_dist={vwap_dist:.3f}")

        # Short mean-revert : prix sur la bande haute
        if bb_pos > 0.9 and rsi > 65 and atr_pct < 0.04:
            score = 50 + (rsi - 65) * 1.2 + (bb_pos - 0.9) * 200
            score += (1 if vwap_dist > 0.01 else 0) * 10
            confidence = self._ml_confidence("mean_revert", features, score)
            return MVPSignal(symbol, SignalType.MEAN_REVERT, "short",
                             min(score, 92), confidence,
                             features_used=features,
                             reasoning=f"BB={bb_pos:.2f} RSI={rsi:.0f} vwap_dist={vwap_dist:.3f}")

        return MVPSignal(symbol, SignalType.NONE, "neutral", 0, 0)

    def _breakout_signal(self, symbol: str, features: dict, market_state) -> MVPSignal:
        """
        Breakout / liquidity event.
        Conditions : cassure d'un range avec volume fort + momentum confirmé.
        """
        range_break   = features.get("range_breakout", 0.0)   # >0 = breakout haussier
        vol_ratio     = features.get("volume_ratio_20", 1.0)
        atr_expansion = features.get("atr_expansion", 1.0)    # ATR vs moyenne 20 ATRs
        rsi           = features.get("rsi_14", 50.0)

        # Breakout haussier
        if range_break > 0 and vol_ratio > 1.8 and atr_expansion > 1.3:
            score = 50 + range_break * 2000 + min((vol_ratio - 1.8) * 15, 15)
            score += min((atr_expansion - 1.3) * 20, 10)
            direction = "long"
            confidence = self._ml_confidence("breakout", features, score)
            return MVPSignal(symbol, SignalType.BREAKOUT, direction,
                             min(score, 95), confidence,
                             features_used=features,
                             reasoning=f"break={range_break:.4f} vol×{vol_ratio:.1f} ATR_exp×{atr_expansion:.1f}")

        # Breakout baissier
        if range_break < 0 and vol_ratio > 1.8 and atr_expansion > 1.3:
            score = 50 + abs(range_break) * 2000 + min((vol_ratio - 1.8) * 15, 15)
            score += min((atr_expansion - 1.3) * 20, 10)
            direction = "short"
            confidence = self._ml_confidence("breakout", features, score)
            return MVPSignal(symbol, SignalType.BREAKOUT, direction,
                             min(score, 95), confidence,
                             features_used=features,
                             reasoning=f"break={range_break:.4f} vol×{vol_ratio:.1f} ATR_exp×{atr_expansion:.1f}")

        return MVPSignal(symbol, SignalType.NONE, "neutral", 0, 0)

    # ──────────────────────────────────────────────────────────────────────────
    # Filtre marché (cohérence signal ↔ market state)
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_market_filter(self, signals: list[MVPSignal], market_state) -> list[MVPSignal]:
        if market_state is None:
            return signals

        filtered = []
        for sig in signals:
            if sig.signal_type == SignalType.NONE:
                continue

            # En chop : mean-revert OK, momentum réduit
            if market_state.trend == "chop":
                if sig.signal_type == SignalType.MOMENTUM:
                    sig.score  *= 0.7
                    sig.confidence *= 0.8

            # En panic : tout réduit sauf sortie
            if market_state.volatility == "panic":
                sig.score  *= 0.5
                sig.confidence *= 0.5

            # Contradiction direction vs tendance forte : pénalité
            if market_state.trend_confidence >= 0.7:
                if market_state.trend == "bullish" and sig.direction == "short":
                    sig.score  *= 0.6
                elif market_state.trend == "bearish" and sig.direction == "long":
                    sig.score  *= 0.6

            filtered.append(sig)

        return filtered

    # ──────────────────────────────────────────────────────────────────────────
    # Feature engineering
    # ──────────────────────────────────────────────────────────────────────────

    def _build_features(self, candles_1h: list, candles_4h: list | None) -> dict[str, float]:
        try:
            c = candles_1h
            closes = [float(x[4]) for x in c if len(x) >= 5]
            highs  = [float(x[2]) for x in c if len(x) >= 5]
            lows   = [float(x[3]) for x in c if len(x) >= 5]
            vols   = [float(x[5]) for x in c if len(x) >= 6]

            if len(closes) < 30:
                return {}

            price = closes[-1]

            # EMA cross
            ema21 = self._ema(closes, 21)
            ema55 = self._ema(closes, min(55, len(closes)))
            ema_cross = (ema21 - ema55) / ema55 if ema55 else 0.0

            # MACD
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, min(26, len(closes)))
            macd_line = ema12 - ema26
            signal_line = self._ema([macd_line] * 9, 9)  # approximation
            macd_hist = macd_line - signal_line

            # RSI
            rsi = self._rsi(closes, 14)

            # ATR %
            atr = self._atr(highs, lows, closes, 14)
            atr_pct = atr / price if price else 0.01

            # ATR expansion
            if len(closes) >= 35:
                prev_atrs = [self._atr(highs[i-14:i], lows[i-14:i], closes[i-14:i], 14)
                             for i in range(20, min(35, len(closes)))]
                avg_prev_atr = sum(prev_atrs) / len(prev_atrs) if prev_atrs else atr
                atr_expansion = atr / avg_prev_atr if avg_prev_atr else 1.0
            else:
                atr_expansion = 1.0

            # Bollinger Bands position
            sma20 = sum(closes[-20:]) / 20
            std20 = (sum((c - sma20)**2 for c in closes[-20:]) / 20) ** 0.5
            upper = sma20 + 2 * std20
            lower = sma20 - 2 * std20
            bb_range = upper - lower
            bb_position = (price - lower) / bb_range if bb_range > 0 else 0.5

            # VWAP distance
            if vols:
                vwap = sum(closes[-20:][i] * vols[-20:][i] for i in range(min(20, len(closes)))) / max(sum(vols[-20:]), 1e-8)
                vwap_dist = (price - vwap) / vwap if vwap else 0.0
            else:
                vwap_dist = 0.0

            # Volume ratio
            avg_vol = sum(vols[-20:]) / 20 if vols else 1.0
            vol_ratio = vols[-1] / avg_vol if avg_vol and vols else 1.0

            # Range breakout : prix au-dessus/en-dessous du range des 20 dernières bougies
            high20 = max(highs[-21:-1]) if len(highs) >= 21 else highs[-1]
            low20  = min(lows[-21:-1])  if len(lows)  >= 21 else lows[-1]
            if price > high20:
                range_breakout = (price - high20) / high20
            elif price < low20:
                range_breakout = (price - low20) / low20
            else:
                range_breakout = 0.0

            # Price slope
            slope_10 = (closes[-1] - closes[-10]) / closes[-10] if len(closes) >= 10 and closes[-10] else 0.0

            return {
                "ema_cross_21_55": ema_cross,
                "macd_hist": macd_hist,
                "rsi_14": rsi,
                "atr_pct_14": atr_pct,
                "atr_expansion": atr_expansion,
                "bb_position": bb_position,
                "vwap_dist": vwap_dist,
                "volume_ratio_20": vol_ratio,
                "range_breakout": range_breakout,
                "price_slope_10": slope_10,
                "price": price,
            }
        except Exception as exc:
            logger.debug("[SignalMVP] feature error: %s", exc)
            return {}

    # ──────────────────────────────────────────────────────────────────────────
    # LightGBM — entraînement et prédiction
    # ──────────────────────────────────────────────────────────────────────────

    def _ml_confidence(self, signal_type: str, features: dict, heuristic_score: float) -> float:
        """Retourne la confiance ML si modèle dispo, sinon heuristique."""
        model = self._models.get(signal_type)
        if model is None or len(self._train_X.get(signal_type, [])) < self.MIN_SAMPLES_ML:
            # Confiance heuristique : normalisée depuis le score
            return min(heuristic_score / 100.0 * 0.9, 0.85)

        try:
            vec = np.array([self._dict_to_vector(features)])
            prob = model.predict_proba(vec)[0][1]
            return float(prob)
        except Exception:
            return min(heuristic_score / 100.0 * 0.9, 0.85)

    def _fit_all(self) -> None:
        for sig_type in ("momentum", "mean_revert", "breakout"):
            X_buf = self._train_X.get(sig_type, deque())
            y_buf = self._train_y.get(sig_type, deque())
            if len(X_buf) < self.MIN_SAMPLES_ML:
                continue
            self._fit_one(sig_type, list(X_buf), list(y_buf))

    def _fit_one(self, sig_type: str, X_list: list, y_list: list) -> None:
        try:
            import lightgbm as lgb
            from sklearn.model_selection import train_test_split

            X = np.array(X_list)
            y = np.array(y_list)
            if len(np.unique(y)) < 2:
                return

            X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
            model = lgb.LGBMClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=10,
                verbose=-1,
            )
            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(10, verbose=False)])
            self._models[sig_type] = model
            self._save_model(sig_type, model)
            logger.info("[SignalMVP] LightGBM '%s' entraîné sur %d samples", sig_type, len(X))
        except Exception as exc:
            logger.warning("[SignalMVP] fit error %s: %s", sig_type, exc)

    def _dict_to_vector(self, features: dict) -> list[float]:
        keys = ["ema_cross_21_55", "macd_hist", "rsi_14", "atr_pct_14",
                "atr_expansion", "bb_position", "vwap_dist", "volume_ratio_20",
                "range_breakout", "price_slope_10"]
        return [float(features.get(k, 0.0)) for k in keys]

    def _save_model(self, name: str, model: Any) -> None:
        try:
            with (_MODEL_DIR / f"{name}.pkl").open("wb") as f:
                pickle.dump(model, f)
        except Exception as exc:
            logger.debug("[SignalMVP] save error: %s", exc)

    def _load_models(self) -> None:
        for sig_type in ("momentum", "mean_revert", "breakout"):
            path = _MODEL_DIR / f"{sig_type}.pkl"
            if path.exists():
                try:
                    with path.open("rb") as f:
                        self._models[sig_type] = pickle.load(f)
                    logger.info("[SignalMVP] Modèle '%s' chargé", sig_type)
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if not values or len(values) < 1:
            return 0.0
        period = min(period, len(values))
        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains  = [max(d, 0) for d in deltas[-period:]]
        losses = [abs(min(d, 0)) for d in deltas[-period:]]
        avg_g  = sum(gains) / period
        avg_l  = sum(losses) / period
        return 100 - 100 / (1 + avg_g / avg_l) if avg_l else 100.0

    @staticmethod
    def _atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
               for i in range(1, len(closes))]
        return sum(trs[-period:]) / period
