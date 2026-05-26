"""
sweep_detector.py — Couche de perception : détection de sweeps de liquidité.

Deux types détectés sur OHLCV + volume (pas d'orderbook) :

  1. LIQUIDATION SWEEP
     Wick brutal cassant un high/low récent, reclaim rapide dans la range.
     Signal : manipulation, piège, absorption.
     Conditions LONG sweep (lows liquidés) :
       - low actuel < min des N derniers lows
       - (high - low) / max(|close - open|, ε) > WICK_BODY_RATIO
       - close > low_récent  (reclaim dans la range)
       - volume > moyenne × VOL_RATIO

  2. ABSORPTION SWEEP
     Volume anormalement élevé mais faible déplacement prix.
     Signal : gros acteur absorbant l'offre/demande.
     Conditions :
       - volume > moyenne × ABSORB_VOL_RATIO
       - |close - open| / atr < ABSORB_BODY_ATR_RATIO

Outputs : list[SweepEvent]
  Trié par sweep_strength DESC.
  Liste vide si aucun sweep détecté.

RÈGLE ARCHITECTURALE :
  Ce module perçoit. Il ne décide PAS.
  Le SweepEvent alimente conviction_engine et DecisionPacket.
  Il n'émet jamais BUY/SELL.

Intégration advisor_loop :
    sweep_events = sweep_detector.detect(symbol, candles_1h, atr, regime)
    # → enrichit features["sweep_*"]
    # → _dp.add_reasoning() si DecisionPacket présent

Logging : chaque sweep détecté → logs/decisions/<date>.jsonl (event SWEEP_DETECTED)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Sequence

from observability.json_logger import get_logger

_log = get_logger("sweep_detector")

# ---------------------------------------------------------------------------
# Constantes — paramètres de détection
# ---------------------------------------------------------------------------

# Liquidation sweep
_N_LOCAL_LEVELS = 20  # fenêtre de recherche du high/low récent
_WICK_BODY_RATIO = 1.8  # wick doit être > 1.8× le corps
_RECLAIM_PCT = 0.002  # le close doit reclaimer > 0.2% dans la range
_VOL_RATIO = 1.6  # volume > 1.6× la moyenne 20 bougies
_VOL_WINDOW = 20  # fenêtre moyenne volume

# Absorption sweep
_ABSORB_VOL_RATIO = 2.0  # volume > 2× la moyenne
_ABSORB_BODY_ATR = 0.35  # corps < 35% de l'ATR → faible déplacement réel

# Seuil minimum pour émettre un SweepEvent (évite le bruit)
_MIN_SWEEP_STRENGTH = 30.0

# Mapping régime → alignement sweep (bonus ou malus de confiance)
_REGIME_ALIGNMENT: dict[str, float] = {
    "sideways": 0.8,  # range → sweeps très fréquents et fiables
    "RANGE": 0.8,
    "bull_trend": 0.6,  # tendance → beaucoup de faux sweeps baissiers
    "TREND_BULL": 0.6,
    "bear_trend": 0.6,
    "TREND_BEAR": 0.6,
    "volatile": 0.4,  # chaos → difficile à valider
    "VOLATILE": 0.4,
    "unknown": 0.5,
    "UNKNOWN": 0.5,
}


# ---------------------------------------------------------------------------
# SweepEvent — structure de sortie
# ---------------------------------------------------------------------------


@dataclass
class SweepEvent:
    """
    Événement de sweep détecté.

    Ce n'est PAS un signal de trading.
    C'est une observation contextuelle qui enrichit la couche de conviction.

    sweep_strength  : score composite 0-100
    volume_ratio    : volume relatif à la moyenne 20 bougies
    wick_ratio      : (high - low) / max(|close - open|, ε)
    reclaim_pct     : % de reclaim dans la range après le sweep
    regime_alignment: 0.0-1.0, fiabilité du pattern dans le régime actuel
    liquidity_level : prix du high/low récent qui a été cassé
    candle_ts       : timestamp de la bougie déclenchante (epoch float)
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    timeframe: str = "1h"
    direction: str = "long"  # "long" | "short"
    sweep_type: str = "liquidation"  # "liquidation" | "absorption"
    sweep_strength: float = 0.0  # 0-100
    liquidity_level: float = 0.0
    reclaim_pct: float = 0.0  # 0.0-1.0
    wick_ratio: float = 0.0
    volume_ratio: float = 0.0
    volatility_context: float = 1.0  # vol_actuelle / atr_moyen
    regime_alignment: float = 0.5
    confidence: float = 0.0  # 0-100, calculée à partir de sweep_strength × régime
    timestamp: float = field(default_factory=time.time)
    candle_ts: float = 0.0

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "sweep_type": self.sweep_type,
            "sweep_strength": round(self.sweep_strength, 1),
            "liquidity_level": self.liquidity_level,
            "reclaim_pct": round(self.reclaim_pct, 4),
            "wick_ratio": round(self.wick_ratio, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "volatility_context": round(self.volatility_context, 2),
            "regime_alignment": round(self.regime_alignment, 2),
            "confidence": round(self.confidence, 1),
            "timestamp": self.timestamp,
            "candle_ts": self.candle_ts,
        }


# ---------------------------------------------------------------------------
# SweepDetector
# ---------------------------------------------------------------------------


class SweepDetector:
    """
    Détecte liquidation sweeps et absorption sweeps sur OHLCV.

    Usage :
        detector = SweepDetector()
        events = detector.detect(
            symbol   = "BTC/USDT",
            candles  = candles_1h,      # list[dict] OHLCV, ordre chronologique
            atr      = features["atr"], # float, ATR courant
            regime   = "sideways",      # str, régime détecté
            timeframe= "1h",
        )
        # events est trié par sweep_strength DESC
        # events peut être vide si aucun sweep qualifié
    """

    def __init__(
        self,
        n_local_levels: int = _N_LOCAL_LEVELS,
        wick_body_ratio: float = _WICK_BODY_RATIO,
        vol_ratio: float = _VOL_RATIO,
        absorb_vol_ratio: float = _ABSORB_VOL_RATIO,
        absorb_body_atr: float = _ABSORB_BODY_ATR,
        min_strength: float = _MIN_SWEEP_STRENGTH,
    ) -> None:
        self._n = n_local_levels
        self._wick_body = wick_body_ratio
        self._vol_ratio = vol_ratio
        self._absorb_vol = absorb_vol_ratio
        self._absorb_body = absorb_body_atr
        self._min_strength = min_strength

    # ── Point d'entrée public ──────────────────────────────────────────────────

    def detect(
        self,
        symbol: str,
        candles: Sequence[dict],
        atr: float = 0.0,
        regime: str = "unknown",
        timeframe: str = "1h",
    ) -> list[SweepEvent]:
        """
        Analyse la dernière bougie des candles pour détecter un sweep.

        Retourne une liste de SweepEvent triée par strength DESC.
        Retourne [] si les candles sont insuffisantes ou aucun sweep qualifié.
        """
        if len(candles) < self._n + 5:
            return []

        events: list[SweepEvent] = []

        liq = self._detect_liquidation(symbol, candles, atr, regime, timeframe)
        if liq:
            events.extend(liq)

        absorb = self._detect_absorption(symbol, candles, atr, regime, timeframe)
        if absorb:
            events.append(absorb)

        qualified = [e for e in events if e.sweep_strength >= self._min_strength]
        qualified.sort(key=lambda e: e.sweep_strength, reverse=True)

        for evt in qualified:
            _log.decision(
                "SWEEP_DETECTED",
                symbol=symbol,
                timeframe=timeframe,
                direction=evt.direction,
                sweep_type=evt.sweep_type,
                sweep_strength=round(evt.sweep_strength, 1),
                volume_ratio=round(evt.volume_ratio, 2),
                wick_ratio=round(evt.wick_ratio, 2),
                regime=regime,
                regime_alignment=evt.regime_alignment,
                confidence=round(evt.confidence, 1),
                liquidity_level=evt.liquidity_level,
                event_id=evt.event_id,
            )

        return qualified

    # ── Détection Liquidation Sweep ───────────────────────────────────────────

    def _detect_liquidation(
        self,
        symbol: str,
        candles: Sequence[dict],
        atr: float,
        regime: str,
        timeframe: str,
    ) -> list[SweepEvent]:
        """
        Cherche un sweep de liquidation sur la dernière bougie.
        Teste LONG (lows liquidés) et SHORT (highs liquidés).
        """
        events = []
        c = candles[-1]
        prev = candles[-(self._n + 1) : -1]

        o = float(c.get("open", 0))
        h = float(c.get("high", 0))
        lo = float(c.get("low", 0))
        cl = float(c.get("close", 0))
        vol = float(c.get("volume", 0))
        ts = float(c.get("ts", c.get("timestamp", time.time())))

        if h <= 0 or lo <= 0 or cl <= 0:
            return []

        body = abs(cl - o)
        candle_range = h - lo
        eps = atr * 0.001 if atr > 0 else 1e-8
        wick_ratio = candle_range / max(body, eps)

        # Volume moyen
        vols = [
            float(x.get("volume", 0)) for x in prev if float(x.get("volume", 0)) > 0
        ]
        avg_vol = sum(vols) / len(vols) if vols else 1.0
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0

        prev_lows = [float(x.get("low", 0)) for x in prev if float(x.get("low", 0)) > 0]
        prev_highs = [
            float(x.get("high", 0)) for x in prev if float(x.get("high", 0)) > 0
        ]

        regime_align = _REGIME_ALIGNMENT.get(regime, 0.5)
        vol_ctx = (candle_range / atr) if atr > 0 else 1.0

        # ── LONG sweep : lows liquidés ────────────────────────────────────────
        if prev_lows:
            recent_low = min(prev_lows)
            if (
                lo < recent_low  # a cassé le low
                and wick_ratio >= self._wick_body  # wick > corps
                and cl > recent_low  # reclaim
                and vol_ratio >= self._vol_ratio  # volume anormal
            ):
                reclaim_pct = (cl - lo) / max(candle_range, eps)
                strength = self._score_liquidation(
                    wick_ratio, vol_ratio, reclaim_pct, regime_align
                )
                confidence = min(100.0, strength * regime_align)
                events.append(
                    SweepEvent(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction="long",
                        sweep_type="liquidation",
                        sweep_strength=strength,
                        liquidity_level=recent_low,
                        reclaim_pct=reclaim_pct,
                        wick_ratio=wick_ratio,
                        volume_ratio=vol_ratio,
                        volatility_context=vol_ctx,
                        regime_alignment=regime_align,
                        confidence=confidence,
                        candle_ts=ts,
                    )
                )

        # ── SHORT sweep : highs liquidés ──────────────────────────────────────
        if prev_highs:
            recent_high = max(prev_highs)
            if (
                h > recent_high  # a cassé le high
                and wick_ratio >= self._wick_body  # wick > corps
                and cl < recent_high  # reclaim
                and vol_ratio >= self._vol_ratio  # volume anormal
            ):
                reclaim_pct = (h - cl) / max(candle_range, eps)
                strength = self._score_liquidation(
                    wick_ratio, vol_ratio, reclaim_pct, regime_align
                )
                confidence = min(100.0, strength * regime_align)
                events.append(
                    SweepEvent(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction="short",
                        sweep_type="liquidation",
                        sweep_strength=strength,
                        liquidity_level=recent_high,
                        reclaim_pct=reclaim_pct,
                        wick_ratio=wick_ratio,
                        volume_ratio=vol_ratio,
                        volatility_context=vol_ctx,
                        regime_alignment=regime_align,
                        confidence=confidence,
                        candle_ts=ts,
                    )
                )

        return events

    # ── Détection Absorption Sweep ────────────────────────────────────────────

    def _detect_absorption(
        self,
        symbol: str,
        candles: Sequence[dict],
        atr: float,
        regime: str,
        timeframe: str,
    ) -> Optional[SweepEvent]:
        """
        Volume très élevé, faible déplacement prix → absorption passive.
        Direction déterminée par la clôture vs ouverture.
        """
        c = candles[-1]
        prev = candles[-(self._n + 1) : -1]

        o = float(c.get("open", 0))
        h = float(c.get("high", 0))
        lo = float(c.get("low", 0))
        cl = float(c.get("close", 0))
        vol = float(c.get("volume", 0))
        ts = float(c.get("ts", c.get("timestamp", time.time())))

        if cl <= 0 or atr <= 0:
            return None

        body = abs(cl - o)
        vols = [
            float(x.get("volume", 0)) for x in prev if float(x.get("volume", 0)) > 0
        ]
        avg_vol = sum(vols) / len(vols) if vols else 1.0
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0

        # Conditions absorption : gros volume + petit corps
        if vol_ratio < self._absorb_vol:
            return None
        if body / atr >= self._absorb_body:
            return None

        # Direction : si close > open → absorption à la vente (acheteurs gagnent) → long
        direction = "long" if cl >= o else "short"

        regime_align = _REGIME_ALIGNMENT.get(regime, 0.5)
        vol_ctx = body / atr

        # Score absorption : moins fort qu'une liquidation (moins de context)
        strength = self._score_absorption(vol_ratio, body / atr, regime_align)
        confidence = min(100.0, strength * regime_align)

        return SweepEvent(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            sweep_type="absorption",
            sweep_strength=strength,
            liquidity_level=(h + lo) / 2,  # centre de la bougie
            reclaim_pct=0.0,
            wick_ratio=(h - lo) / max(body, 1e-8),
            volume_ratio=vol_ratio,
            volatility_context=vol_ctx,
            regime_alignment=regime_align,
            confidence=confidence,
            candle_ts=ts,
        )

    # ── Scoring ───────────────────────────────────────────────────────────────

    @staticmethod
    def _score_liquidation(
        wick_ratio: float,
        vol_ratio: float,
        reclaim_pct: float,
        regime_align: float,
    ) -> float:
        """
        Score composite 0-100.

        Composantes :
          - wick_ratio   : 0-35 pts  (wick dominant = liquidation franche)
          - vol_ratio    : 0-30 pts  (volume anormal = conviction)
          - reclaim_pct  : 0-25 pts  (reclaim rapide = piège confirmé)
          - regime_align : 0-10 pts  (bonus si régime favorable)
        """
        # wick : plafonné à 5× le corps → 35 pts max
        wick_score = min(35.0, (wick_ratio - 1.8) / (5.0 - 1.8) * 35.0)
        # volume : plafonné à 4× la moyenne → 30 pts max
        vol_score = min(30.0, (vol_ratio - 1.6) / (4.0 - 1.6) * 30.0)
        # reclaim : 0.3 → full reclaim → 25 pts max
        reclaim_score = min(25.0, reclaim_pct / 0.8 * 25.0)
        # régime : 0-10 pts
        regime_score = regime_align * 10.0

        total = wick_score + vol_score + reclaim_score + regime_score
        return max(0.0, min(100.0, total))

    @staticmethod
    def _score_absorption(
        vol_ratio: float,
        body_atr_ratio: float,
        regime_align: float,
    ) -> float:
        """
        Score composite 0-100 pour absorption.

        Composantes :
          - vol_ratio      : 0-50 pts (volume très élevé = signal fort)
          - body_atr_ratio : 0-40 pts (plus le corps est petit, plus fort)
          - regime_align   : 0-10 pts
        """
        # volume : 2× → 0 pts, 5× → 50 pts
        vol_score = min(50.0, (vol_ratio - 2.0) / (5.0 - 2.0) * 50.0)
        # corps : 0% ATR → 40 pts, 35% ATR → 0 pts
        body_score = min(40.0, (1.0 - body_atr_ratio / 0.35) * 40.0)
        regime_score = regime_align * 10.0

        total = vol_score + max(0.0, body_score) + regime_score
        return max(0.0, min(100.0, total))
