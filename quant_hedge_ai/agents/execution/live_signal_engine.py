"""
live_signal_engine.py — Moteur de signaux live 0-100 par symbole.

Agrège :
  - Signal MTF (MultiTimeframeSignal, poids 40 %)
  - Régime de marché (AdvancedRegimeDetector, poids 25 %)
  - Qualité OHLCV (OHLCVValidator, poids 15 %)
  - Contexte de mémoire stratégique (StrategyMemoryStore, poids 20 %)

Un score ≥ SIGNAL_MIN_SCORE (défaut 70) déclenche une opportunité de trading.

Migration DecisionPacket :
  - SignalResult.to_decision_packet() — conversion vers le contrat central
  - LiveSignalEngine.evaluate_as_packet() — évalue et retourne un DecisionPacket
  Les appelants existants d'evaluate() ne sont pas impactés.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Mapping régimes LSE → MarketRegime (déclaré ici pour éviter import circulaire)
_REGIME_MAP: dict[str, str] = {
    "bull_trend": "TREND_BULL",
    "bear_trend": "TREND_BEAR",
    "sideways": "RANGE",
    "high_volatility_regime": "VOLATILE",
    "flash_crash": "VOLATILE",
    "unknown": "UNKNOWN",
}

_DEFAULT_MIN_SCORE: int = int(os.getenv("SIGNAL_MIN_SCORE", "70"))

try:
    from errors.error_bus import ErrorCategory as _ErrCat
    from errors.error_bus import error_bus as _error_bus
    from observability.metrics_bus import metrics_bus as _metrics_bus

    _OBS_AVAILABLE = True
except Exception:
    _OBS_AVAILABLE = False


@dataclass
class SignalResult:
    symbol: str
    score: int  # 0-100
    signal: str  # BUY | SELL | HOLD
    regime: str = "unknown"
    confirmed: bool = False
    strength: float = 0.0
    components: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def actionable(self) -> bool:
        return self.score >= _DEFAULT_MIN_SCORE and self.signal in ("BUY", "SELL")

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "signal": self.signal,
            "regime": self.regime,
            "confirmed": self.confirmed,
            "strength": self.strength,
            "actionable": self.actionable,
            "components": self.components,
            "timestamp": self.timestamp,
        }


class LiveSignalEngine:
    """
    Agrège plusieurs sources d'analyse pour produire un score 0-100 par symbole.

    Usage:
        engine = LiveSignalEngine(strategy=my_strategy)
        result = engine.evaluate(symbol="BTCUSDT", mtf_candles={...}, features={...})
        if result.actionable:
            ...
    """

    def __init__(
        self,
        strategy: dict | None = None,
        min_score: int = _DEFAULT_MIN_SCORE,
        regime_blacklist: set[str] | None = None,
    ) -> None:
        self.strategy = strategy or {}
        self.min_score = min_score
        self.regime_blacklist: set[str] = regime_blacklist or set()
        self._last_results: dict[str, SignalResult] = {}

    # ── API principale ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        symbol: str,
        mtf_candles: dict[str, list[dict]],
        features: dict | None = None,
        memory_sharpe: float | None = None,
    ) -> SignalResult:
        """
        Calcule le score de signal pour un symbole.

        Args:
            symbol       : ex. "BTCUSDT"
            mtf_candles  : {timeframe: [candles]} — doit avoir ≥1 TF
            features     : dict de features de marché (issu de FeatureEngineer)
            memory_sharpe: meilleur Sharpe mémorisé pour ce régime (optionnel)

        Returns:
            SignalResult avec score 0-100
        """
        features = features or {}
        components: dict[str, float] = {}

        # ① Score MTF (40 points max)
        mtf_score, mtf_signal, mtf_confirmed, mtf_strength = self._score_mtf(
            mtf_candles, components
        )

        # ② Score régime (25 points max)
        regime, regime_score = self._score_regime(features, components)

        # ③ Score qualité données (15 points max)
        data_score = self._score_data_quality(mtf_candles, components)

        # ④ Score mémoire stratégique (20 points max)
        mem_score = self._score_memory(memory_sharpe, components)

        raw = mtf_score + regime_score + data_score + mem_score
        score = max(0, min(100, int(raw)))

        # Veto si régime blacklisté
        if regime in self.regime_blacklist:
            score = min(score, 30)
            components["regime_blacklist_veto"] = -1.0
            logger.debug(
                "[LSE] %s — régime blacklisté (%s), score plafonné à 30", symbol, regime
            )

        result = SignalResult(
            symbol=symbol,
            score=score,
            signal=mtf_signal,
            regime=regime,
            confirmed=mtf_confirmed,
            strength=mtf_strength,
            components=components,
        )
        self._last_results[symbol] = result
        logger.info(
            "[LSE] %s → score=%d signal=%s régime=%s actionable=%s",
            symbol,
            score,
            mtf_signal,
            regime,
            result.actionable,
        )
        if _OBS_AVAILABLE:
            try:
                _metrics_bus.record("live_signal_engine", "score", float(score))
                _metrics_bus.gauge(
                    "live_signal_engine", f"score.{symbol}", float(score)
                )
                if result.actionable:
                    _metrics_bus.increment("live_signal_engine", "actionable_signals")
            except Exception:
                pass
        return result

    def evaluate_batch(
        self,
        symbols_data: dict[str, dict],
    ) -> list[SignalResult]:
        """
        Évalue plusieurs symboles en un appel.

        Args:
            symbols_data: {symbol: {"mtf_candles": {...},
                           "features": {...}, "memory_sharpe": float}}

        Returns:
            Liste triée par score décroissant
        """
        results = []
        for symbol, data in symbols_data.items():
            try:
                r = self.evaluate(
                    symbol=symbol,
                    mtf_candles=data.get("mtf_candles", {}),
                    features=data.get("features"),
                    memory_sharpe=data.get("memory_sharpe"),
                )
                results.append(r)
            except Exception as exc:
                logger.warning("[LSE] Erreur %s: %s", symbol, exc)
                if _OBS_AVAILABLE:
                    try:
                        _error_bus.emit(
                            module="live_signal_engine",
                            error=exc,
                            category=_ErrCat.AI,
                            context={"symbol": symbol},
                        )
                    except Exception:
                        pass
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def top_opportunities(self, n: int = 3) -> list[SignalResult]:
        """Retourne les N meilleures opportunités actionnables du dernier batch."""
        actionable = [r for r in self._last_results.values() if r.actionable]
        return sorted(actionable, key=lambda r: r.score, reverse=True)[:n]

    def blacklist_regime(self, regime: str) -> None:
        self.regime_blacklist.add(regime)
        logger.info("[LSE] Régime blacklisté: %s", regime)

    def unblacklist_regime(self, regime: str) -> None:
        self.regime_blacklist.discard(regime)

    # ── Sous-scores ───────────────────────────────────────────────────────────

    def _score_mtf(
        self, mtf_candles: dict, components: dict
    ) -> tuple[float, str, bool, float]:
        """
        Score MTF enrichi : combine le vote multi-timeframe classique
        avec les indicateurs techniques (RSI, MACD, EMA) de chaque TF.
        Retourne (score 0-40, signal, confirmed, strength).
        """
        if not mtf_candles:
            components["mtf"] = 0.0
            return 0.0, "HOLD", False, 0.0

        from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer

        fe = FeatureEngineer()

        # ── Vote indicateurs par TF ────────────────────────────────────────
        tf_weights = {"1d": 3.0, "4h": 2.0, "1h": 1.0, "15m": 0.5, "1m": 0.2}
        buy_score = 0.0
        sell_score = 0.0
        total_w = 0.0
        tf_signals: dict[str, str] = {}

        for tf, candles in mtf_candles.items():
            if not candles or len(candles) < 20:
                continue
            w = tf_weights.get(tf, 1.0)
            feat = fe.extract_features(candles)
            sig = self._indicator_signal(feat)
            tf_signals[tf] = sig
            if sig == "BUY":
                buy_score += w
            elif sig == "SELL":
                sell_score += w
            total_w += w

        # ── Vote classique (fallback si pas assez de TF) ──────────────────
        try:
            from quant_hedge_ai.agents.execution.multi_timeframe_signal import (
                MultiTimeframeSignal,
            )

            mtf = MultiTimeframeSignal()
            result = mtf.confirm(self.strategy, mtf_candles)
            classic = result.get("signal", "HOLD")
            if classic == "BUY":
                buy_score += 1.0
            elif classic == "SELL":
                sell_score += 1.0
            total_w += 1.0
        except ImportError as _ie:
            logger.warning("[LSE] MultiTimeframeSignal indisponible: %s", _ie)
        except Exception as _exc:
            logger.warning("[LSE] MultiTimeframeSignal erreur: %s", _exc)

        if total_w == 0:
            components["mtf"] = 0.0
            return 0.0, "HOLD", False, 0.0

        if buy_score > sell_score:
            candidate = "BUY"
            strength = buy_score / total_w
        elif sell_score > buy_score:
            candidate = "SELL"
            strength = sell_score / total_w
        else:
            components["mtf"] = 5.0
            return 5.0, "HOLD", False, 0.0

        n_agree = sum(1 for s in tf_signals.values() if s == candidate)
        confirmed = strength >= 0.5 and n_agree >= int(
            os.getenv("LSE_MTF_MIN_AGREE", "2")
        )

        if not confirmed:
            score = strength * 15.0
        else:
            score = 20.0 + strength * 20.0  # 20-40 pts si confirmé

        signal = candidate if confirmed else "HOLD"
        logger.debug(
            "[LSE] MTF: %s strength=%.2f n_agree=%d tfs=%s",
            signal,
            strength,
            n_agree,
            tf_signals,
        )

        components["mtf"] = round(score, 2)
        components["mtf_tfs"] = tf_signals
        return score, signal, confirmed, round(strength, 3)

    @staticmethod
    def _indicator_signal(feat: dict) -> str:
        """
        Signal composite depuis RSI + MACD + EMA + Bollinger.
        Retourne BUY / SELL / HOLD.
        """
        buy_votes = 0
        sell_votes = 0

        # RSI — clamp 0-100 (valeurs hors bornes = artefact de calcul)
        rsi = float(feat.get("rsi", 50.0))
        if rsi < 0.0 or rsi > 100.0:
            logger.warning("[LSE] RSI hors bornes (%.2f) — clamp 0-100", rsi)
            rsi = max(0.0, min(100.0, rsi))
        if rsi < 35:
            buy_votes += 2  # sur-vendu = fort signal BUY
        elif rsi < 45:
            buy_votes += 1
        elif rsi > 65:
            sell_votes += 2  # sur-acheté = fort signal SELL
        elif rsi > 55:
            sell_votes += 1

        # MACD histogramme
        macd_h = feat.get("macd_hist", 0.0)
        if macd_h > 0:
            buy_votes += 1
        elif macd_h < 0:
            sell_votes += 1

        # EMA alignment
        if feat.get("ema_bullish", False) and feat.get("ema_cross", 0) > 0:
            buy_votes += 1
        elif not feat.get("ema_bullish", True) and feat.get("ema_cross", 0) < 0:
            sell_votes += 1

        # Bollinger position
        bb_pct = feat.get("bb_pct", 0.5)
        if bb_pct < 0.2:
            buy_votes += 1  # proche de la bande inférieure
        elif bb_pct > 0.8:
            sell_votes += 1  # proche de la bande supérieure

        # Momentum
        mom = feat.get("momentum", 0.0)
        if mom > 0.01:
            buy_votes += 1
        elif mom < -0.01:
            sell_votes += 1

        total = buy_votes + sell_votes
        if total == 0:
            return "HOLD"
        if buy_votes >= 3 and buy_votes > sell_votes * 1.5:
            return "BUY"
        if sell_votes >= 3 and sell_votes > buy_votes * 1.5:
            return "SELL"
        return "HOLD"

    def _score_regime(self, features: dict, components: dict) -> tuple[str, float]:
        """Retourne (regime, score 0-25)."""
        if not features:
            components["regime"] = 0.0
            return "unknown", 0.0

        try:
            from quant_hedge_ai.agents.intelligence.regime_detector import (
                AdvancedRegimeDetector,
            )

            det = AdvancedRegimeDetector()
            regime = det.classify(features)
        except ImportError as _ie:
            logger.warning("[LSE] AdvancedRegimeDetector indisponible: %s", _ie)
            regime = "unknown"
        except Exception as _exc:
            logger.warning("[LSE] RegimeDetector erreur: %s", _exc)
            regime = "unknown"

        # Bonus selon régime favorable à un signal directionnel
        regime_scores = {
            "bull_trend": 25.0,
            "bear_trend": 20.0,
            "high_volatility_regime": 15.0,
            "flash_crash": 5.0,
            "sideways": 12.0,
            "unknown": 0.0,
        }
        score = regime_scores.get(regime, 10.0)
        components["regime"] = round(score, 2)
        return regime, score

    def _score_data_quality(self, mtf_candles: dict, components: dict) -> float:
        """Retourne un score 0-15 selon la qualité des données."""
        if not mtf_candles:
            components["data_quality"] = 0.0
            return 0.0

        try:
            from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles

            total_score = 0.0
            total_weight = 0.0
            tf_weights = {"1d": 3.0, "4h": 2.0, "1h": 1.0, "15m": 0.5, "1m": 0.2}

            for tf, candles in mtf_candles.items():
                if not candles:
                    continue
                w = tf_weights.get(tf, 1.0)
                valid, report = validate_candles(candles)
                quality = report.valid / report.total if report.total > 0 else 0.5
                total_score += quality * w
                total_weight += w

            ratio = (total_score / total_weight) if total_weight > 0 else 0.5
            score = ratio * 15.0
        except Exception as exc:
            logger.debug("[LSE] Qualité données error: %s", exc)
            score = 7.5  # score neutre si validator indisponible

        components["data_quality"] = round(score, 2)
        return score

    def _score_memory(self, memory_sharpe: float | None, components: dict) -> float:
        """Retourne 0-20 selon le meilleur Sharpe mémorisé pour ce régime."""
        if memory_sharpe is None:
            components["memory"] = 10.0  # neutre si pas de mémoire
            return 10.0

        if memory_sharpe <= 0:
            score = 0.0
        elif memory_sharpe >= 2.0:
            score = 20.0
        else:
            score = memory_sharpe / 2.0 * 20.0

        components["memory"] = round(score, 2)
        return score

    # ── API DecisionPacket ────────────────────────────────────────────────────

    def evaluate_as_packet(
        self,
        symbol: str,
        mtf_candles: dict[str, list[dict]],
        features: dict | None = None,
        memory_sharpe: float | None = None,
        cycle_id: str | None = None,
    ) -> "DecisionPacket":
        """
        Évalue le symbole et retourne un DecisionPacket prêt pour les couches suivantes.

        Wrapper autour d'evaluate() — zéro duplication de logique signal.
        Les appelants existants d'evaluate() ne sont pas impactés.
        """
        result = self.evaluate(symbol, mtf_candles, features, memory_sharpe)
        timeframe = self.strategy.get("timeframe", "1h")
        return result.to_decision_packet(
            timeframe=timeframe,
            cycle_id=cycle_id,
            actor="live_signal_engine",
        )


# ── Conversion SignalResult → DecisionPacket ──────────────────────────────────


def _split_components(components: dict) -> tuple[dict[str, float], dict]:
    """
    Sépare les composantes en :
      - features : dict[str, float]  — valeurs numériques ML-ready
      - metadata  : dict             — tout le reste (dicts, strings, booleans)

    Révèle un couplage implicite dans live_signal_engine :
    components["mtf_tfs"] est un dict de strings (pas un float) — il va en metadata.
    """
    features: dict[str, float] = {}
    meta: dict = {}
    for k, v in components.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            features[k] = float(v)
        else:
            meta[k] = v
    return features, meta


def _to_decision_packet(
    result: "SignalResult",
    timeframe: str = "1h",
    cycle_id: str | None = None,
    actor: str = "live_signal_engine",
) -> "DecisionPacket":
    """
    Convertit un SignalResult en DecisionPacket.

    Mapping :
      score      → confidence (0-100)
      signal     → side (BUY→LONG, SELL→SHORT, HOLD→FLAT)
      regime     → regime (via _REGIME_MAP)
      components → features (float) + metadata (reste)
      confirmed  → metadata["mtf_confirmed"]
      strength   → features["mtf_strength"]
    """
    from core.decision_packet import (
        DecisionPacket,
        DecisionSide,
        DecisionState,
        MarketRegime,
        ReasoningCategory,
    )

    side_map = {
        "BUY": DecisionSide.LONG,
        "SELL": DecisionSide.SHORT,
        "HOLD": DecisionSide.FLAT,
    }
    side = side_map.get(result.signal, DecisionSide.FLAT)

    regime_str = _REGIME_MAP.get(result.regime, "UNKNOWN")
    try:
        regime = MarketRegime(regime_str)
    except ValueError:
        regime = MarketRegime.UNKNOWN

    features, extra_meta = _split_components(result.components)
    features["mtf_strength"] = result.strength

    metadata = {
        "signal_raw": result.signal,
        "mtf_confirmed": result.confirmed,
        "lse_timestamp": result.timestamp,
        **extra_meta,
    }

    packet = DecisionPacket(
        symbol=result.symbol,
        timeframe=timeframe,
        side=side,
        confidence=float(result.score),
        regime=regime,
        created_cycle_id=cycle_id,
        features=features,
        metadata=metadata,
    )
    packet.add_agent(actor)
    packet.add_reasoning(
        actor=actor,
        message=(
            f"score={result.score} signal={result.signal} "
            f"régime={result.regime} confirmé={result.confirmed}"
        ),
        confidence_impact=0.0,
        category=ReasoningCategory.SIGNAL_QUALITY,
    )

    # Le signal engine constate une opportunité statistique — il ne juge pas le risque.
    # Le rejet appartient à risk_gate, pas ici.
    # confidence, signal_raw et actionable sont en metadata pour que risk_gate décide.
    packet.metadata["lse_actionable"] = result.actionable
    packet.transition_to(
        DecisionState.SIGNAL_GENERATED,
        actor,
        f"Signal détecté : score={result.score} direction={result.signal}",
    )

    return packet


# Attache la méthode à SignalResult sans modifier sa définition originale
SignalResult.to_decision_packet = _to_decision_packet  # type: ignore[attr-defined]


# Nécessaire pour le type hint forward dans evaluate_as_packet
try:
    from core.decision_packet import DecisionPacket  # noqa: F401 (import de référence)
except ImportError:
    pass
