"""
no_trade_layer.py — No-Trade Intelligence Layer

Les meilleurs bots refusent énormément.
Ce module donne au bot la capacité de dire NON de manière intelligente.

Composantes :
  1. Rejection Scoring     — score de rejet [0-100], trade bloqué si > seuil
  2. Market Quality Filter — détecte les marchés sales (spread, volume, chop)
  3. Anti-FOMO Layer       — refuse les entrées tardives sur moves déjà faits
  4. Signal Disqualifier   — invalide les signaux pour raisons structurelles
  5. Tactical Pause        — bloque toute activité si contexte globalement mauvais

Retourne :
  NoTradeVerdict(allowed=False, reason=..., rejection_score=85)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.no_trade_layer")


@dataclass
class NoTradeVerdict:
    allowed: bool
    rejection_score: float  # [0, 100] — plus c'est haut, plus le rejet est fort
    reason: str
    category: str  # "market_quality" | "fomo" | "signal" | "tactical_pause" | "ok"
    details: list = None

    def __post_init__(self):
        if self.details is None:
            self.details = []

    def __bool__(self) -> bool:
        return self.allowed


class NoTradeIntelligence:
    """
    Couche de refus intelligent.

    Appelée AVANT toute décision d'ordre.
    Un seul verdict suffit à bloquer.
    """

    # ── Seuils ────────────────────────────────────────────────────────────────

    # Market quality
    MIN_VOLUME_RATIO = float(
        os.getenv("NTL_MIN_VOLUME_RATIO", "0.3")
    )  # vol récent / avg
    MAX_SPREAD_PCT = float(os.getenv("NTL_MAX_SPREAD_PCT", "0.005"))  # 0.5%
    MIN_CANDLES = int(os.getenv("NTL_MIN_CANDLES", "50"))  # min bougies valides
    CHOP_THRESHOLD = float(
        os.getenv("NTL_CHOP_THRESHOLD", "0.6")
    )  # ADX chop si < 20 pts score

    # Anti-FOMO
    MAX_MOVE_PCT = float(os.getenv("NTL_MAX_MOVE_PCT", "0.03"))  # move déjà fait > 3%
    FOMO_WINDOW_CANDLES = int(
        os.getenv("NTL_FOMO_WINDOW", "3")
    )  # sur les N dernières bougies
    MAX_ATR_MULTIPLIER = float(
        os.getenv("NTL_MAX_ATR_MULT", "2.5")
    )  # prix déjà à 2.5× ATR du low

    # Signal quality
    MIN_SCORE = int(os.getenv("NTL_MIN_SCORE", "65"))
    MAX_AGE_SECONDS = float(
        os.getenv("NTL_MAX_SIGNAL_AGE", "300")
    )  # signal > 5min = expiré
    CONTRADICTION_SCORE = float(
        os.getenv("NTL_CONTRADICTION", "0.4")
    )  # MTF contradiction > 40%

    # Rejection scoring weights
    W_MARKET = float(os.getenv("NTL_W_MARKET", "35"))
    W_FOMO = float(os.getenv("NTL_W_FOMO", "25"))
    W_SIGNAL = float(os.getenv("NTL_W_SIGNAL", "25"))
    W_TACTICAL = float(os.getenv("NTL_W_TACTICAL", "15"))

    REJECT_THRESHOLD = float(os.getenv("NTL_REJECT_THRESHOLD", "50"))

    def __init__(self) -> None:
        self._tactical_pause_until: float = 0.0
        self._tactical_pause_reason: str = ""
        self._rejection_log: list[dict] = []
        self._stats = {"checked": 0, "rejected": 0, "by_category": {}}

    # ── API principale ────────────────────────────────────────────────────────

    def check(
        self,
        signal,  # SignalResult
        candles: list,  # bougies 1h
        features: dict,
        regime: str,
        signal_age_s: float = 0.0,
        personality_name: str = "unknown",
    ) -> NoTradeVerdict:
        """
        Vérifie si le trade est acceptable.
        Retourne NoTradeVerdict(allowed=True/False, ...).
        """
        self._stats["checked"] += 1
        details = []
        scores = {}

        # ── 1. Tactical pause ─────────────────────────────────────────────────
        if self._tactical_pause_until > time.time():
            remaining = (self._tactical_pause_until - time.time()) / 60
            return self._reject(
                "tactical_pause",
                f"Pause tactique active ({remaining:.0f}min restantes) — {self._tactical_pause_reason}",
                rejection_score=100.0,
            )

        # ── 2. Market quality ─────────────────────────────────────────────────
        mq_score, mq_issues = self._check_market_quality(candles, features)
        scores["market"] = mq_score
        details += mq_issues

        # ── 3. Anti-FOMO ──────────────────────────────────────────────────────
        fomo_score, fomo_issues = self._check_fomo(candles, features, signal)
        scores["fomo"] = fomo_score
        details += fomo_issues

        # ── 4. Signal quality ─────────────────────────────────────────────────
        sig_score, sig_issues = self._check_signal_quality(
            signal, signal_age_s, regime, personality_name
        )
        scores["signal"] = sig_score
        details += sig_issues

        # ── Score de rejet composite ──────────────────────────────────────────
        rejection = (
            scores["market"] * self.W_MARKET / 100
            + scores["fomo"] * self.W_FOMO / 100
            + scores["signal"] * self.W_SIGNAL / 100
        )

        if rejection >= self.REJECT_THRESHOLD:
            worst = max(scores, key=scores.get)
            return self._reject(
                worst,
                f"Score rejet {rejection:.0f}/100 — {', '.join(details[:2])}",
                rejection_score=rejection,
                details=details,
            )

        self._stats["checked"] += 0  # déjà incrémenté
        return NoTradeVerdict(
            allowed=True,
            rejection_score=rejection,
            reason="OK",
            category="ok",
            details=details,
        )

    def engage_tactical_pause(
        self, reason: str, duration_minutes: float = 60.0
    ) -> None:
        """Bloque tout trading pour une durée donnée."""
        self._tactical_pause_until = time.time() + duration_minutes * 60
        self._tactical_pause_reason = reason
        _log.warning(
            "[NoTrade] Pause tactique %dmin — %s", int(duration_minutes), reason
        )

    def lift_tactical_pause(self) -> None:
        self._tactical_pause_until = 0.0
        _log.info("[NoTrade] Pause tactique levée")

    def stats(self) -> dict:
        total = self._stats["checked"]
        rejected = self._stats["rejected"]
        return {
            "checked": total,
            "rejected": rejected,
            "rejection_rate": round(rejected / total, 3) if total else 0.0,
            "by_category": self._stats["by_category"],
            "recent": self._rejection_log[-10:],
        }

    # ── Vérifications ─────────────────────────────────────────────────────────

    def _check_market_quality(
        self, candles: list, features: dict
    ) -> tuple[float, list[str]]:
        """Score de rejet [0-100] pour qualité du marché."""
        score = 0.0
        issues = []

        if not candles or len(candles) < self.MIN_CANDLES:
            issues.append(
                f"Données insuffisantes ({len(candles) if candles else 0} bougies)"
            )
            return 80.0, issues

        # Volume anormalement bas
        volumes = [float(c.get("volume", 0)) for c in candles[-20:]]
        avg_vol = sum(volumes[:-5]) / max(1, len(volumes[:-5]))
        recent_vol = sum(volumes[-5:]) / 5
        if avg_vol > 0:
            vol_ratio = recent_vol / avg_vol
            if vol_ratio < self.MIN_VOLUME_RATIO:
                score += 40
                issues.append(f"Volume bas: {vol_ratio:.0%} de la moyenne")

        # Marché choppy (faible trend strength)
        trend = float(features.get("trend_strength", 0.5))
        vol_r = float(features.get("realized_volatility", 0.05))
        if trend < 0.3 and vol_r < 0.03:
            score += 30
            issues.append(f"Marché choppy: trend_strength={trend:.2f}")

        # Bougies incomplètes (closes nulles)
        nulls = sum(1 for c in candles[-10:] if float(c.get("close", 1)) <= 0)
        if nulls >= 2:
            score += 25
            issues.append(f"{nulls} bougies invalides (close=0)")

        return min(100.0, score), issues

    def _check_fomo(
        self, candles: list, features: dict, signal
    ) -> tuple[float, list[str]]:
        """Score de rejet [0-100] pour FOMO / entrée tardive."""
        score = 0.0
        issues = []

        if not candles or len(candles) < self.FOMO_WINDOW_CANDLES + 2:
            return 0.0, issues

        closes = [float(c.get("close", 0)) for c in candles]
        recent = closes[-self.FOMO_WINDOW_CANDLES :]
        ref = closes[-(self.FOMO_WINDOW_CANDLES + 1)]

        if ref <= 0:
            return 0.0, issues

        # Move déjà fait dans le sens du signal
        move = (recent[-1] - ref) / ref
        sig_dir = 1 if getattr(signal, "signal", "HOLD") == "BUY" else -1

        if sig_dir * move >= self.MAX_MOVE_PCT:
            score += 50
            issues.append(
                f"Entrée tardive: move {move:.1%} déjà fait dans la direction du signal"
            )

        # Prix trop loin de la moyenne (ATR)
        atr = float(features.get("atr", 0.0))
        if atr > 0:
            price = closes[-1]
            ma = sum(closes[-20:]) / 20
            dist = abs(price - ma) / atr
            if dist >= self.MAX_ATR_MULTIPLIER:
                score += 35
                issues.append(
                    f"Prix à {dist:.1f}× ATR de la moyenne — extension excessive"
                )

        return min(100.0, score), issues

    def _check_signal_quality(
        self, signal, age_s: float, regime: str, personality_name: str
    ) -> tuple[float, list[str]]:
        """Score de rejet [0-100] pour qualité du signal."""
        score = 0.0
        issues = []

        # Score signal trop bas
        sig_score = getattr(signal, "score", 0)
        if sig_score < self.MIN_SCORE:
            score += 45
            issues.append(
                f"Score signal faible: {sig_score}/100 (min {self.MIN_SCORE})"
            )

        # Signal expiré
        if age_s > self.MAX_AGE_SECONDS:
            score += 40
            issues.append(f"Signal expiré: {age_s:.0f}s > {self.MAX_AGE_SECONDS:.0f}s")

        # Contradiction MTF — signal sur 1h mais contexte 4h/1d opposé
        components = getattr(signal, "components", {})
        mtf = float(components.get("mtf", 20)) / 40  # normalise sur 1.0
        if mtf < self.CONTRADICTION_SCORE:
            score += 30
            issues.append(f"Contradiction MTF: alignement {mtf:.0%}")

        # Signal HOLD dans une direction forte
        if getattr(signal, "signal", "HOLD") == "HOLD":
            score += 20
            issues.append("Signal HOLD — pas d'action directionnelle")

        return min(100.0, score), issues

    # ── Interne ───────────────────────────────────────────────────────────────

    def _reject(
        self, category: str, reason: str, rejection_score: float, details: list = None
    ) -> NoTradeVerdict:
        self._stats["rejected"] += 1
        self._stats["by_category"][category] = (
            self._stats["by_category"].get(category, 0) + 1
        )
        self._rejection_log.append(
            {
                "ts": time.time(),
                "category": category,
                "reason": reason,
                "score": rejection_score,
            }
        )
        if len(self._rejection_log) > 200:
            self._rejection_log = self._rejection_log[-200:]
        _log.info(
            "[NoTrade] REJET (%s) score=%.0f — %s", category, rejection_score, reason
        )
        return NoTradeVerdict(
            allowed=False,
            rejection_score=rejection_score,
            reason=reason,
            category=category,
            details=details or [],
        )
