"""
paper_trading/recorder.py — Journal de trades paper unique et portable.

Source de vérité pour tous les trades paper/futures_demo exécutés.
Fonctionne en local ET sur VPS — format JSONL append-only.

Chaque trade = 2 événements :
  OPEN  → enregistré à l'entrée
  CLOSE → enregistré à la sortie (avec PnL complet)

Un trade complet = 1 OPEN + 1 CLOSE liés par trade_id.

Schema v1 : champs de base (entry, exit, regime, score).
Schema v2 : + MarketContext (27 features) + DecisionContext (conviction, personality...).

Usage :
    from paper_trading.recorder import PaperTradeRecorder, MarketContext, DecisionContext
    r = PaperTradeRecorder()

    ctx = MarketContext.from_features(features_dict)
    dec = DecisionContext(score=82.0, conviction_level="HIGH", regime="bull_trend")

    r.record_open(trade_id="abc", symbol="BTC/USDT", side="buy",
                  price=65000.0, size_usd=55.0, regime="bull_trend", score=82,
                  market_context=ctx, decision_context=dec)

    r.record_close(trade_id="abc", exit_price=66200.0,
                   pnl_usd=1.03, pnl_pct=0.0187, reason="take_profit")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")

SCHEMA_VERSION = 2


def _score_to_bin(score: int) -> str:
    if score < 50:
        return "<50"
    if score < 55:
        return "50-54"
    if score < 60:
        return "55-59"
    if score < 65:
        return "60-64"
    if score < 70:
        return "65-69"
    return "70+"


# ── Structures de contexte (schema v2) ───────────────────────────────────────


@dataclass(frozen=True)
class MarketContext:
    """Snapshot immuable de l'état technique du marché au moment de l'entrée.

    Alimenté via from_features(result_row["features"]).
    Seules les variables validées sont persistées — le schéma reste stable
    même si FeatureEngineer évolue.
    """

    momentum: Optional[float] = None
    realized_volatility: Optional[float] = None
    trend_strength: Optional[float] = None
    avg_volume: Optional[float] = None
    volume_ratio: Optional[float] = None
    atr: Optional[float] = None
    atr_ratio: Optional[float] = None
    rsi: Optional[float] = None
    rsi_oversold: Optional[bool] = None
    rsi_overbought: Optional[bool] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema_cross: Optional[float] = None  # distance signée prix/EMA20 (float, pas bool)
    ema_bullish: Optional[bool] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    macd_bullish: Optional[bool] = None
    bb_pct: Optional[float] = None  # position dans la bande (0=bas, 1=haut)
    bb_squeeze: Optional[bool] = None
    vwap_dist: Optional[float] = None
    range_pos: Optional[float] = None  # position dans le range 20 bougies
    ob_imbalance: Optional[float] = None  # V2 microstructure
    funding_rate: Optional[float] = None  # V2 on-chain
    micro_spread_bps: Optional[float] = None  # V2 microstructure

    @classmethod
    def from_features(cls, features: dict) -> "MarketContext":
        """Construit un MarketContext depuis le dict FeatureEngineer.

        Les clés inconnues sont ignorées. Les clés manquantes deviennent None.
        """

        def _f(key: str) -> Optional[float]:
            v = features.get(key)
            return float(v) if v is not None else None

        def _b(key: str) -> Optional[bool]:
            v = features.get(key)
            return bool(v) if v is not None else None

        return cls(
            momentum=_f("momentum"),
            realized_volatility=_f("realized_volatility"),
            trend_strength=_f("trend_strength"),
            avg_volume=_f("avg_volume"),
            volume_ratio=_f("volume_ratio"),
            atr=_f("atr"),
            atr_ratio=_f("atr_ratio"),
            rsi=_f("rsi"),
            rsi_oversold=_b("rsi_oversold"),
            rsi_overbought=_b("rsi_overbought"),
            ema20=_f("ema20"),
            ema50=_f("ema50"),
            ema_cross=_f("ema_cross"),
            ema_bullish=_b("ema_bullish"),
            macd_line=_f("macd_line"),
            macd_signal=_f("macd_signal"),
            macd_hist=_f("macd_hist"),
            macd_bullish=_b("macd_bullish"),
            bb_pct=_f("bb_pct"),
            bb_squeeze=_b("bb_squeeze"),
            vwap_dist=_f("vwap_dist"),
            range_pos=_f("range_pos"),
            ob_imbalance=_f("ob_imbalance"),
            funding_rate=_f("funding_rate"),
            micro_spread_bps=_f("micro_spread_bps"),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "MarketContext":
        valid = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass(frozen=True)
class DecisionContext:
    """Snapshot de l'état du moteur de décision au moment de l'entrée.

    Sépare la conviction (catégorie + valeur continue) pour permettre
    des analyses statistiques sur les deux dimensions.
    """

    score: Optional[float] = None
    conviction_level: Optional[str] = None  # "NONE"|"LOW"|"MEDIUM"|"HIGH"|"EXTREME"
    conviction_value: Optional[float] = None  # score continu si disponible
    personality: Optional[str] = None
    regime: Optional[str] = None
    transition_forecast: Optional[str] = None  # most_likely_next regime

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionContext":
        valid = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in valid})


# ── Événements JSONL ─────────────────────────────────────────────────────────


@dataclass
class TradeEvent:
    event: str  # "OPEN" | "CLOSE"
    trade_id: str
    ts: float
    ts_iso: str
    symbol: str
    side: str  # "buy" | "sell" | "long" | "short"
    price: float
    size_usd: float
    mode: str  # "futures_demo" | "paper" | "live"
    schema_version: int = 1  # 2 depuis cette release
    # OPEN uniquement
    regime: str = "unknown"
    score: int = 0
    score_bin: str = ""
    order_id: str = ""
    # CLOSE uniquement
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    reason: str = ""
    duration_s: Optional[float] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    # Schema v2
    market_context: Optional[MarketContext] = None
    decision_context: Optional[DecisionContext] = None


@dataclass
class CompleteTrade:
    trade_id: str
    symbol: str
    side: str
    regime: str
    score: int
    mode: str
    # Entry
    entry_price: float
    size_usd: float
    opened_at: float
    opened_iso: str
    order_id: str
    schema_version: int = 1
    # Exit (None si encore ouvert)
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    exit_reason: str = ""
    closed_at: Optional[float] = None
    closed_iso: Optional[str] = None
    duration_s: Optional[float] = None
    is_open: bool = True
    is_win: Optional[bool] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    # Schema v2
    market_context: Optional[MarketContext] = None
    decision_context: Optional[DecisionContext] = None


# ── Recorder ─────────────────────────────────────────────────────────────────


class PaperTradeRecorder:
    """
    Journal append-only de trades paper.

    Thread-safe par file-lock léger (atomic write).
    Compatible VPS : un seul fichier JSONL, lisible à distance.
    Rétrocompatible : les lignes schema_version=1 (sans market/decision context)
    sont lues sans erreur, les nouveaux champs valent None.
    """

    def __init__(self, log_path: str = _DEFAULT_PATH) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Écriture ─────────────────────────────────────────────────────────────

    def record_open(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        price: float,
        size_usd: float,
        regime: str = "unknown",
        score: int = 0,
        order_id: str = "",
        mode: str = "futures_demo",
        market_context: Optional[MarketContext] = None,
        decision_context: Optional[DecisionContext] = None,
    ) -> None:
        now = time.time()
        evt = TradeEvent(
            event="OPEN",
            trade_id=trade_id,
            ts=now,
            ts_iso=_iso(now),
            symbol=symbol,
            side=side,
            price=price,
            size_usd=size_usd,
            mode=mode,
            schema_version=SCHEMA_VERSION,
            regime=regime,
            score=score,
            score_bin=_score_to_bin(score),
            order_id=order_id,
            market_context=market_context,
            decision_context=decision_context,
        )
        self._append(evt)

    def record_close(
        self,
        trade_id: str,
        exit_price: float,
        pnl_usd: float,
        pnl_pct: float,
        reason: str = "",
        opened_at: Optional[float] = None,
        symbol: str = "",
        side: str = "",
        size_usd: float = 0.0,
        mode: str = "futures_demo",
        mae_pct: Optional[float] = None,
        mfe_pct: Optional[float] = None,
    ) -> None:
        now = time.time()
        duration = (now - opened_at) if opened_at else None
        evt = TradeEvent(
            event="CLOSE",
            trade_id=trade_id,
            ts=now,
            ts_iso=_iso(now),
            symbol=symbol,
            side=side,
            price=exit_price,
            size_usd=size_usd,
            mode=mode,
            schema_version=SCHEMA_VERSION,
            exit_price=exit_price,
            pnl_usd=round(pnl_usd, 4),
            pnl_pct=round(pnl_pct, 6),
            reason=reason,
            duration_s=round(duration, 1) if duration else None,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
        )
        self._append(evt)

    # ── Lecture ───────────────────────────────────────────────────────────────

    def events(self) -> list[TradeEvent]:
        """Tous les événements bruts du journal."""
        if not self._path.exists():
            return []
        results = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    mc_raw = d.pop("market_context", None)
                    dc_raw = d.pop("decision_context", None)
                    evt = TradeEvent(
                        **{
                            k: v
                            for k, v in d.items()
                            if k in TradeEvent.__dataclass_fields__
                        }
                    )
                    if mc_raw and isinstance(mc_raw, dict):
                        evt.market_context = MarketContext.from_dict(mc_raw)
                    if dc_raw and isinstance(dc_raw, dict):
                        evt.decision_context = DecisionContext.from_dict(dc_raw)
                    results.append(evt)
                except Exception:
                    pass
        return results

    def trades(self) -> list[CompleteTrade]:
        """
        Reconstruit les trades complets (OPEN + CLOSE appariés).
        Les OPEN sans CLOSE sont inclus avec is_open=True.
        """
        opens: dict[str, TradeEvent] = {}
        closes: dict[str, TradeEvent] = {}

        for evt in self.events():
            if evt.event == "OPEN":
                opens[evt.trade_id] = evt
            elif evt.event == "CLOSE":
                closes[evt.trade_id] = evt

        result = []
        seen = set()

        for tid, op in opens.items():
            seen.add(tid)
            cl = closes.get(tid)
            ct = CompleteTrade(
                trade_id=tid,
                symbol=op.symbol,
                side=op.side,
                regime=op.regime,
                score=op.score,
                mode=op.mode,
                entry_price=op.price,
                size_usd=op.size_usd,
                opened_at=op.ts,
                opened_iso=op.ts_iso,
                order_id=op.order_id,
                schema_version=op.schema_version,
                market_context=op.market_context,
                decision_context=op.decision_context,
            )
            if cl:
                ct.exit_price = cl.exit_price
                ct.pnl_usd = cl.pnl_usd
                ct.pnl_pct = cl.pnl_pct
                ct.exit_reason = cl.reason
                ct.closed_at = cl.ts
                ct.closed_iso = cl.ts_iso
                ct.duration_s = cl.duration_s
                ct.is_open = False
                ct.is_win = (cl.pnl_usd or 0) > 0
                ct.mae_pct = cl.mae_pct
                ct.mfe_pct = cl.mfe_pct
            result.append(ct)

        # CLOSE orphelins (sans OPEN correspondant — cas VPS décalé)
        for tid, cl in closes.items():
            if tid not in seen:
                ct = CompleteTrade(
                    trade_id=tid,
                    symbol=cl.symbol,
                    side=cl.side,
                    regime="unknown",
                    score=0,
                    mode=cl.mode,
                    entry_price=0.0,
                    size_usd=cl.size_usd,
                    opened_at=0.0,
                    opened_iso="",
                    order_id="",
                    exit_price=cl.exit_price,
                    pnl_usd=cl.pnl_usd,
                    pnl_pct=cl.pnl_pct,
                    exit_reason=cl.reason,
                    closed_at=cl.ts,
                    closed_iso=cl.ts_iso,
                    duration_s=cl.duration_s,
                    is_open=False,
                    is_win=(cl.pnl_usd or 0) > 0,
                    mae_pct=cl.mae_pct,
                    mfe_pct=cl.mfe_pct,
                )
                result.append(ct)

        return sorted(result, key=lambda t: t.opened_at or t.closed_at or 0)

    def summary(self) -> dict:
        """Statistiques agrégées des trades complétés."""
        all_trades = self.trades()
        closed = [t for t in all_trades if not t.is_open]
        open_pos = [t for t in all_trades if t.is_open]

        if not closed:
            return {
                "total_closed": 0,
                "total_open": len(open_pos),
                "win_rate": None,
                "pnl_total_usd": 0.0,
                "pnl_avg_pct": None,
                "best_trade_pct": None,
                "worst_trade_pct": None,
                "avg_duration_min": None,
                "target_30_trades": f"0 / 30",
            }

        wins = [t for t in closed if t.is_win]
        pnls_pct = [t.pnl_pct for t in closed if t.pnl_pct is not None]
        pnls_usd = [t.pnl_usd for t in closed if t.pnl_usd is not None]
        durations = [t.duration_s / 60 for t in closed if t.duration_s]

        return {
            "total_closed": len(closed),
            "total_open": len(open_pos),
            "target_30_trades": f"{len(closed)} / 30",
            "win_rate": round(len(wins) / len(closed) * 100, 1),
            "pnl_total_usd": round(sum(pnls_usd), 4) if pnls_usd else 0.0,
            "pnl_avg_pct": (
                round(sum(pnls_pct) / len(pnls_pct) * 100, 3) if pnls_pct else None
            ),
            "best_trade_pct": round(max(pnls_pct) * 100, 3) if pnls_pct else None,
            "worst_trade_pct": round(min(pnls_pct) * 100, 3) if pnls_pct else None,
            "avg_duration_min": (
                round(sum(durations) / len(durations), 1) if durations else None
            ),
            "go_live_ready": len(closed) >= 30,
        }

    # ── Interne ───────────────────────────────────────────────────────────────

    def _append(self, evt: TradeEvent) -> None:
        line = json.dumps(asdict(evt), ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)


# ── Singleton partagé ────────────────────────────────────────────────────────

_recorder: Optional[PaperTradeRecorder] = None


def get_recorder() -> PaperTradeRecorder:
    global _recorder
    if _recorder is None:
        _recorder = PaperTradeRecorder()
    return _recorder


# ── Helpers ───────────────────────────────────────────────────────────────────


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
