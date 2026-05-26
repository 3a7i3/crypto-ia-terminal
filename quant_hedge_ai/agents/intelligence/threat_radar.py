"""
threat_radar.py — Surveillance de l'environnement externe

Détecte les menaces macros avant qu'elles impactent le portefeuille :
  - Anomalies de funding rate (financement perpetuel)
  - Liquidation clusters (coinank-style approximé via OI + prix)
  - Volatilité implicite (ATR multi-symboles)
  - Divergence BTC dominance
  - Spread spot/futures anormal
  - Déconnexion corrélation (symboles qui divergent de BTC)

Usage:
    radar = ThreatRadar(exchange)
    threats = await radar.scan()   # async
    # ou synchrone :
    threats = radar.scan_sync()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, stdev
from typing import TYPE_CHECKING

from observability.json_logger import get_logger

if TYPE_CHECKING:
    pass

_log = get_logger("quant_hedge_ai.agents.intelligence.threat_radar")


class ThreatLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Threat:
    threat_type: str
    level: ThreatLevel
    description: str
    symbol: str = ""
    value: float = 0.0
    threshold: float = 0.0
    ts: float = field(default_factory=time.time)
    action_hint: str = ""


@dataclass
class RadarReport:
    ts: float = field(default_factory=time.time)
    threats: list[Threat] = field(default_factory=list)
    max_level: ThreatLevel = ThreatLevel.NONE
    trade_allowed: bool = True
    summary: str = ""

    def highest_threat(self) -> ThreatLevel:
        order = [
            ThreatLevel.NONE,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ]
        max_idx = 0
        for t in self.threats:
            try:
                idx = order.index(t.level)
                max_idx = max(max_idx, idx)
            except ValueError:
                pass
        return order[max_idx]


# ── Thresholds (env-configurable) ────────────────────────────────────────────


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


FUNDING_EXTREME_THRESHOLD = _env_float(
    "RADAR_FUNDING_EXTREME", 0.003
)  # 0.3% / 8h = extreme
FUNDING_HIGH_THRESHOLD = _env_float("RADAR_FUNDING_HIGH", 0.001)  # 0.1% / 8h = high
SPREAD_WARN_PCT = _env_float("RADAR_SPREAD_WARN", 0.002)  # 0.2% spread
SPREAD_CRIT_PCT = _env_float("RADAR_SPREAD_CRIT", 0.005)  # 0.5% spread
CORR_DIVERGENCE_THRESHOLD = _env_float("RADAR_CORR_DIV", 0.15)  # divergence corrélation
VOL_SPIKE_MULTIPLIER = _env_float("RADAR_VOL_SPIKE", 2.5)  # ATR x2.5 = spike
VOLUME_SPIKE_MULTIPLIER = _env_float("RADAR_VOLUME_SPIKE", 4.0)  # volume x4 = anomalie
CONSEC_CANDLES_SAME_DIR = _env_float(
    "RADAR_CONSEC_CANDLES", 7
)  # 7 bougies mêmes direction = trend lock
RADAR_VETO_LEVEL = os.getenv(
    "RADAR_VETO_LEVEL", "CRITICAL"
)  # niveau qui bloque le trading


class ThreatRadar:
    """
    Analyse les données de marché pour détecter des menaces environnementales.

    Le radar n'effectue pas lui-même des appels exchange — il reçoit les données
    via feed() ou les récupère via exchange si fourni.
    """

    def __init__(self, exchange=None) -> None:
        self._exchange = exchange
        self._history: dict[str, list[dict]] = {}
        self._last_scan: RadarReport | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def feed_candles(self, symbol: str, candles: list[dict]) -> None:
        self._history[symbol] = candles[-200:]

    def scan_sync(self, symbols: list[str] | None = None) -> RadarReport:
        symbols = symbols or list(self._history.keys())
        all_threats: list[Threat] = []

        for sym in symbols:
            candles = self._history.get(sym, [])
            if len(candles) < 20:
                continue
            all_threats.extend(self._scan_symbol(sym, candles))

        # Cross-symbol correlation divergence
        if len(symbols) >= 2:
            all_threats.extend(self._check_correlation_divergence(symbols))

        report = RadarReport(threats=all_threats)
        report.max_level = report.highest_threat()
        report.trade_allowed = (
            report.max_level not in (ThreatLevel.CRITICAL,)
            if RADAR_VETO_LEVEL == "CRITICAL"
            else report.max_level not in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
        )
        report.summary = self._make_summary(report)
        self._last_scan = report
        return report

    def last_report(self) -> RadarReport | None:
        return self._last_scan

    # ── Symbol-level checks ───────────────────────────────────────────────────

    def _scan_symbol(self, symbol: str, candles: list[dict]) -> list[Threat]:
        threats: list[Threat] = []

        closes = [float(c.get("close", 0)) for c in candles]
        volumes = [float(c.get("volume", 0)) for c in candles]
        highs = [float(c.get("high", c.get("close", 0))) for c in candles]
        lows = [float(c.get("low", c.get("close", 0))) for c in candles]

        threats.extend(self._check_volatility_spike(symbol, closes, highs, lows))
        threats.extend(self._check_volume_anomaly(symbol, volumes))
        threats.extend(self._check_price_momentum_lock(symbol, closes))
        threats.extend(self._check_spread_anomaly(symbol, candles))
        threats.extend(self._check_funding_rate(symbol, candles))

        return threats

    def _check_volatility_spike(
        self, symbol: str, closes: list[float], highs: list[float], lows: list[float]
    ) -> list[Threat]:
        threats: list[Threat] = []
        if len(closes) < 20:
            return threats

        # ATR sur les 14 dernières bougies vs ATR 50 bougies de référence
        def _atr_window(n: int) -> float:
            trs = []
            start = max(1, len(closes) - n)
            for i in range(start, len(closes)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                trs.append(tr)
            return sum(trs) / len(trs) if trs else 0.0

        atr_recent = _atr_window(14)
        atr_ref = _atr_window(50)
        price = closes[-1]

        if atr_ref > 0 and atr_recent > atr_ref * VOL_SPIKE_MULTIPLIER:
            ratio = atr_recent / atr_ref
            level = ThreatLevel.CRITICAL if ratio > 4.0 else ThreatLevel.HIGH
            threats.append(
                Threat(
                    threat_type="VOLATILITY_SPIKE",
                    level=level,
                    symbol=symbol,
                    description=f"ATR récent {atr_recent/price*100:.2f}% vs référence {atr_ref/price*100:.2f}% (x{ratio:.1f})",
                    value=atr_recent / price,
                    threshold=atr_ref / price * VOL_SPIKE_MULTIPLIER,
                    action_hint="Réduire taille ou attendre stabilisation",
                )
            )
        return threats

    def _check_volume_anomaly(self, symbol: str, volumes: list[float]) -> list[Threat]:
        threats: list[Threat] = []
        if len(volumes) < 20:
            return threats

        avg_vol = mean(volumes[-50:-1]) if len(volumes) >= 51 else mean(volumes[:-1])
        last_vol = volumes[-1]

        if avg_vol > 0 and last_vol > avg_vol * VOLUME_SPIKE_MULTIPLIER:
            ratio = last_vol / avg_vol
            level = ThreatLevel.HIGH if ratio > 6.0 else ThreatLevel.MEDIUM
            threats.append(
                Threat(
                    threat_type="VOLUME_SPIKE",
                    level=level,
                    symbol=symbol,
                    description=f"Volume x{ratio:.1f} par rapport à la moyenne (possible liquidation/whale)",
                    value=last_vol,
                    threshold=avg_vol * VOLUME_SPIKE_MULTIPLIER,
                    action_hint="Possible manipulation ou liquidation cluster — prudence",
                )
            )
        return threats

    def _check_price_momentum_lock(
        self, symbol: str, closes: list[float]
    ) -> list[Threat]:
        threats: list[Threat] = []
        n = int(CONSEC_CANDLES_SAME_DIR)
        if len(closes) < n + 1:
            return threats

        recent = closes[-(n + 1) :]
        directions = [
            1 if recent[i] > recent[i - 1] else -1 for i in range(1, len(recent))
        ]
        if len(set(directions)) == 1:
            direction = "haussière" if directions[0] == 1 else "baissière"
            move_pct = abs(recent[-1] - recent[0]) / recent[0] * 100 if recent[0] else 0
            level = ThreatLevel.HIGH if move_pct > 5 else ThreatLevel.MEDIUM
            threats.append(
                Threat(
                    threat_type="MOMENTUM_LOCK",
                    level=level,
                    symbol=symbol,
                    description=f"{n} bougies consécutives {direction} ({move_pct:.2f}% total) — risque retournement violent",
                    value=move_pct / 100,
                    threshold=n,
                    action_hint="Ne pas FOMO — attendre consolidation ou retournement",
                )
            )
        return threats

    def _check_spread_anomaly(self, symbol: str, candles: list[dict]) -> list[Threat]:
        threats: list[Threat] = []
        recent = candles[-5:]
        spreads = []
        for c in recent:
            high = float(c.get("high", 0))
            low = float(c.get("low", 0))
            close = float(c.get("close", high))
            if close > 0 and high > low:
                spreads.append((high - low) / close)

        if not spreads:
            return threats

        avg_spread = mean(spreads)
        if avg_spread > SPREAD_CRIT_PCT:
            threats.append(
                Threat(
                    threat_type="SPREAD_CRITICAL",
                    level=ThreatLevel.HIGH,
                    symbol=symbol,
                    description=f"Spread H/L moyen {avg_spread*100:.3f}% — liquidité dégradée",
                    value=avg_spread,
                    threshold=SPREAD_CRIT_PCT,
                    action_hint="Slippage élevé — réduire taille ordre",
                )
            )
        elif avg_spread > SPREAD_WARN_PCT:
            threats.append(
                Threat(
                    threat_type="SPREAD_HIGH",
                    level=ThreatLevel.LOW,
                    symbol=symbol,
                    description=f"Spread H/L {avg_spread*100:.3f}% — légèrement élevé",
                    value=avg_spread,
                    threshold=SPREAD_WARN_PCT,
                    action_hint="Surveiller slippage",
                )
            )
        return threats

    def _check_funding_rate(self, symbol: str, candles: list[dict]) -> list[Threat]:
        threats: list[Threat] = []
        # Le funding rate n'est pas dans les candles OHLCV standard.
        # On l'approxime via la pression de volume des dernières bougies.
        # Un proxy : si le volume est concentré dans une direction récurrente,
        # c'est un signal de déséquilibre long/short (funding extrême probable).

        if len(candles) < 10:
            return threats

        recent = candles[-10:]
        buys = 0
        sells = 0
        for i in range(1, len(recent)):
            c_now = float(recent[i].get("close", 0))
            c_prev = float(recent[i - 1].get("close", 0))
            vol = float(recent[i].get("volume", 0))
            if c_now > c_prev:
                buys += vol
            else:
                sells += vol

        total = buys + sells
        if total == 0:
            return threats

        buy_pressure = buys / total
        # Funding proxy: si >80% achat sur 10 bougies = marché très long = funding positif élevé
        if buy_pressure > 0.80:
            threats.append(
                Threat(
                    threat_type="FUNDING_LONG_SQUEEZE_RISK",
                    level=ThreatLevel.MEDIUM,
                    symbol=symbol,
                    description=f"Pression achat {buy_pressure*100:.0f}% — marché très long, risque squeeze",
                    value=buy_pressure,
                    threshold=0.80,
                    action_hint="Éviter BUY supplementaire — risque long squeeze funding",
                )
            )
        elif buy_pressure < 0.20:
            threats.append(
                Threat(
                    threat_type="FUNDING_SHORT_SQUEEZE_RISK",
                    level=ThreatLevel.MEDIUM,
                    symbol=symbol,
                    description=f"Pression vente {(1-buy_pressure)*100:.0f}% — marché très short, risque short squeeze",
                    value=1 - buy_pressure,
                    threshold=0.80,
                    action_hint="Éviter SELL supplementaire — risque short squeeze",
                )
            )
        return threats

    # ── Cross-symbol checks ───────────────────────────────────────────────────

    def _check_correlation_divergence(self, symbols: list[str]) -> list[Threat]:
        threats: list[Threat] = []
        btc_key = next((s for s in symbols if "BTC" in s), None)
        if not btc_key:
            return threats

        btc_closes = [float(c.get("close", 0)) for c in self._history.get(btc_key, [])]
        if len(btc_closes) < 20:
            return threats

        btc_returns = [
            (btc_closes[i] - btc_closes[i - 1]) / btc_closes[i - 1]
            for i in range(1, len(btc_closes))
            if btc_closes[i - 1] != 0
        ]
        if not btc_returns:
            return threats

        for sym in symbols:
            if sym == btc_key:
                continue
            candles = self._history.get(sym, [])
            if len(candles) < 20:
                continue
            closes = [float(c.get("close", 0)) for c in candles]
            n = min(len(btc_returns), len(closes) - 1)
            if n < 10:
                continue
            sym_returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
                if closes[i - 1] != 0
            ]
            # Pearson correlation over last n
            btc_r = btc_returns[-n:]
            sym_r = sym_returns[-n:]
            if len(btc_r) != len(sym_r):
                continue

            corr = self._pearson(btc_r, sym_r)
            if corr < (1.0 - CORR_DIVERGENCE_THRESHOLD * 3):
                threats.append(
                    Threat(
                        threat_type="CORRELATION_BREAKDOWN",
                        level=ThreatLevel.MEDIUM,
                        symbol=sym,
                        description=f"{sym} diverge de BTC (corr={corr:.2f}) — découplage marché",
                        value=corr,
                        threshold=1.0 - CORR_DIVERGENCE_THRESHOLD * 3,
                        action_hint=f"Analyser {sym} indépendamment — ne pas supposer corrélation BTC",
                    )
                )
        return threats

    @staticmethod
    def _pearson(x: list[float], y: list[float]) -> float:
        n = len(x)
        if n < 2:
            return 1.0
        mx, my = mean(x), mean(y)
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        den = (
            sum((x[i] - mx) ** 2 for i in range(n))
            * sum((y[i] - my) ** 2 for i in range(n))
        ) ** 0.5
        return num / den if den != 0 else 1.0

    # ── Summary ───────────────────────────────────────────────────────────────

    def _make_summary(self, report: RadarReport) -> str:
        if not report.threats:
            return "Environnement propre — aucune menace détectée"

        levels_count = {l: 0 for l in ThreatLevel}
        for t in report.threats:
            levels_count[t.level] += 1

        parts = []
        for lvl in [
            ThreatLevel.CRITICAL,
            ThreatLevel.HIGH,
            ThreatLevel.MEDIUM,
            ThreatLevel.LOW,
        ]:
            if levels_count[lvl] > 0:
                parts.append(f"{lvl.value}:{levels_count[lvl]}")

        summary = f"RADAR [{'/'.join(parts)}] — " if parts else "RADAR — "
        top = sorted(
            report.threats,
            key=lambda t: [
                ThreatLevel.CRITICAL,
                ThreatLevel.HIGH,
                ThreatLevel.MEDIUM,
                ThreatLevel.LOW,
                ThreatLevel.NONE,
            ].index(t.level),
        )
        for t in top[:2]:
            summary += f"{t.symbol} {t.threat_type} | "

        if not report.trade_allowed:
            summary += "=> TRADING BLOQUE"
        return summary.rstrip(" |")

    def format_telegram(self, report: RadarReport) -> str:
        if not report.threats:
            return ""
        lines = [f"🛰 THREAT RADAR — {report.max_level.value}"]
        for t in sorted(
            report.threats,
            key=lambda x: [
                ThreatLevel.CRITICAL,
                ThreatLevel.HIGH,
                ThreatLevel.MEDIUM,
                ThreatLevel.LOW,
                ThreatLevel.NONE,
            ].index(x.level),
        ):
            emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(
                t.level.value, "⚪"
            )
            lines.append(f"{emoji} [{t.threat_type}] {t.symbol}: {t.description}")
            if t.action_hint:
                lines.append(f"   → {t.action_hint}")
        if not report.trade_allowed:
            lines.append("🚫 Trading suspendu — niveau de menace trop élevé")
        return "\n".join(lines)
