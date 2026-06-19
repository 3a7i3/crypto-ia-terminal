"""
black_box.py — Black Box Recorder

Inspiré de la boîte noire aviation.
Enregistre CHAQUE décision importante avec :
  - Timestamp + symbole + prix
  - Signal + score + régime + personnalité
  - Pourquoi BUY / SELL / HOLD / REFUS
  - Quel module a refusé et pourquoi
  - Contexte complet (features, positions ouvertes, capital)
  - Ordre exécuté ou non, et raison

En cas de crash ou comportement inattendu :
  on sait EXACTEMENT ce qui s'est passé et pourquoi.

Format JSONL, lecture facile, rotation automatique.
Requêtes rapides : filtre par type, symbole, régime, décision.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.black_box")
_BB_PATH = os.getenv("BB_PATH", "databases/black_box.jsonl")
_BB_MAX_SIZE = int(os.getenv("BB_MAX", "5000"))  # max entrées en mémoire

# Chiffrement AES-256-GCM des entrées (C-01) — singleton lazy
_bb_enc = None


def _get_enc():
    global _bb_enc
    if _bb_enc is None:
        from crypto.blackbox_encryption import BlackBoxEncryption

        _bb_enc = BlackBoxEncryption()
    return _bb_enc


class DecisionType(str, Enum):
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_REFUSED = "TRADE_REFUSED"
    HOLD = "HOLD"
    POSITION_CLOSED = "POSITION_CLOSED"
    HALT_TRIGGERED = "HALT_TRIGGERED"
    SAFE_MODE = "SAFE_MODE"
    REGIME_CHANGE = "REGIME_CHANGE"
    AWARENESS_ALERT = "AWARENESS_ALERT"
    RULE_TRIGGERED = "RULE_TRIGGERED"
    SYSTEM_EVENT = "SYSTEM_EVENT"


@dataclass
class BlackBoxEntry:
    ts: float
    decision_type: str
    symbol: str
    signal: str  # BUY / SELL / HOLD
    score: int
    regime: str
    personality: str
    price: float
    # Raison principale
    reason: str
    # Couches qui ont refusé (vide si exécuté)
    refused_by: list = field(default_factory=list)
    # Couches OK
    passed_by: list = field(default_factory=list)
    # Contexte clé
    conviction_level: str = "unknown"
    conviction_score: float = 0.0
    awareness_level: str = "OK"
    portfolio_exposure: float = 0.0
    open_positions: int = 0
    capital_available: float = 0.0
    order_size: float = 0.0
    kelly_fraction: float = 0.0
    # Features clés (résumé)
    rsi: float = 0.0
    atr_ratio: float = 0.0
    macd_bullish: bool = False
    ema_bullish: bool = False
    bb_pct: float = 0.5
    # Résultat (rempli à la fermeture)
    pnl_pct: float = 0.0
    close_reason: str = ""
    # ID ordre si exécuté
    order_id: str = ""
    cycle: int = 0
    # Enrichissements P1
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    drawdown_session_pct: float = 0.0
    n_trades_today: int = 0


class BlackBox:
    """
    Enregistre chaque décision du système dans un journal indestructible.

    Usage :
        bb = BlackBox()
        bb.record_decision(result_dict, cycle)
        bb.record_position_closed(pos, reason)
        bb.record_halt(reason, level)
        bb.query(decision_type="TRADE_EXECUTED", symbol="BTC/USDT", limit=10)
    """

    def __init__(self, path: str = _BB_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[BlackBoxEntry] = []
        self._loaded = False
        self._session_capital_peak: float = 0.0

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        enc = _get_enc()
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = enc.decrypt_line(line)
                    except Exception:
                        # Fallback migration : entrée en clair (fichier pré-C-01)
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue
                    try:
                        self._entries.append(BlackBoxEntry(**data))
                    except Exception:
                        pass
            self._entries = self._entries[-_BB_MAX_SIZE:]
        except Exception as exc:
            _log.warning("[BlackBox] Chargement partiel: %s", exc)

    # ── Helpers enrichissement ────────────────────────────────────────────────

    def _compute_drawdown(self, capital: float) -> float:
        """Drawdown depuis le pic de capital de session (%)."""
        if capital > self._session_capital_peak:
            self._session_capital_peak = capital
        if self._session_capital_peak <= 0:
            return 0.0
        return round(
            (self._session_capital_peak - capital) / self._session_capital_peak * 100, 2
        )

    def _count_trades_today(self) -> int:
        """Nombre de TRADE_EXECUTED depuis minuit UTC."""
        midnight = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        return sum(
            1
            for e in self._entries
            if e.decision_type == DecisionType.TRADE_EXECUTED.value and e.ts >= midnight
        )

    # ── Enregistrement des décisions ──────────────────────────────────────────

    def record_decision(self, r: dict, cycle: int = 0) -> BlackBoxEntry:
        """
        Enregistre une décision d'analyse de symbole depuis le résultat
        de analyze_symbol() dans advisor_loop.py.
        """
        self._ensure_loaded()

        signal = r.get("signal")
        gate = r.get("gate")
        conviction = r.get("conviction")
        awareness = r.get("awareness_state")
        pb = r.get("pb_verdict")
        allocation = r.get("allocation")
        mm = r.get("mm_check")
        persona = r.get("personality")
        feat = r.get("features", {})
        no_trade = r.get("no_trade_verdict")

        trade_allowed = r.get("trade_allowed", False)
        meta_allowed = r.get("meta_allowed", True)

        # Déterminer le type de décision
        if signal and signal.actionable:
            if (
                trade_allowed
                and r.get("futures_result", {})
                and r["futures_result"].get("mode") == "futures_demo"
            ):
                dtype = DecisionType.TRADE_EXECUTED
            elif signal.actionable:
                dtype = DecisionType.TRADE_REFUSED
            else:
                dtype = DecisionType.HOLD
        else:
            dtype = DecisionType.HOLD

        # Construire la liste des refus
        refused_by = []
        passed_by = []

        def _check(name: str, ok: bool, reason: str = "") -> None:
            if ok:
                passed_by.append(name)
            else:
                refused_by.append(f"{name}: {reason}" if reason else name)

        if signal:
            _check(
                "gate",
                gate.allowed if gate else True,
                " | ".join(gate.failed[:2]) if gate and not gate.allowed else "",
            )
            _check(
                "meta",
                meta_allowed,
                r.get("meta_reason", "") if not meta_allowed else "",
            )
            _check(
                "conviction",
                conviction is None or not conviction.blocks_trade(),
                (
                    conviction.level.value
                    if conviction and conviction.blocks_trade()
                    else ""
                ),
            )
            _check(
                "no_trade",
                no_trade is None or bool(no_trade),
                (
                    f"score={no_trade.rejection_score:.0f}"
                    if no_trade and not bool(no_trade)
                    else ""
                ),
            )
            _check(
                "awareness",
                awareness is None
                or awareness.level.value == "OK"
                or not hasattr(awareness, "is_trading_halted")
                or True,
                awareness.level.name if awareness else "",
            )
            _check(
                "mistake_mem",
                mm is None or bool(mm),
                mm.reason[:60] if mm and not bool(mm) else "",
            )
            _check(
                "portfolio",
                pb is None or bool(pb),
                pb.reason[:60] if pb and not bool(pb) else "",
            )
            _check(
                "capital_eng",
                allocation is None or bool(allocation),
                allocation.reason[:60] if allocation and not bool(allocation) else "",
            )

        # Raison principale lisible
        if refused_by:
            reason = f"Refus: {refused_by[0]}"
        elif dtype == DecisionType.TRADE_EXECUTED:
            reason = f"Ordre {signal.signal if signal else '?'} exécuté"
        elif signal and not signal.actionable:
            reason = f"Score insuffisant: {signal.score}/100"
        else:
            reason = "HOLD — pas de signal"

        _capital = pb.capital_available if pb else 0.0
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=dtype.value,
            symbol=r.get("symbol", "?"),
            signal=signal.signal if signal else "HOLD",
            score=signal.score if signal else 0,
            regime=r.get("regime", "unknown"),
            personality=persona.name if persona else "N/A",
            price=r.get("prix", 0.0),
            reason=reason,
            refused_by=refused_by,
            passed_by=passed_by,
            conviction_level=conviction.level.value if conviction else "unknown",
            conviction_score=conviction.score if conviction else 0.0,
            awareness_level=awareness.level.name if awareness else "OK",
            portfolio_exposure=(
                pb.metrics.get("total_exposure_pct", 0.0)
                if pb and hasattr(pb, "metrics")
                else 0.0
            ),
            open_positions=(
                r.get("open_positions", 0)
                if isinstance(r.get("open_positions"), int)
                else len(r.get("open_positions", []))
            ),
            capital_available=_capital,
            order_size=r.get("order_size", 0.0),
            kelly_fraction=allocation.kelly_fraction if allocation else 0.0,
            rsi=float(feat.get("rsi", 0.0)),
            atr_ratio=float(feat.get("atr_ratio", 0.0)),
            macd_bullish=bool(feat.get("macd_bullish", False)),
            ema_bullish=bool(feat.get("ema_bullish", False)),
            bb_pct=float(feat.get("bb_pct", 0.5)),
            order_id=(
                r.get("futures_result", {}).get("id", "")
                if r.get("futures_result")
                else ""
            ),
            cycle=cycle,
            drawdown_session_pct=self._compute_drawdown(_capital),
            n_trades_today=self._count_trades_today(),
        )

        self._append(entry)
        return entry

    def record_position_closed(self, pos, reason) -> BlackBoxEntry:
        """Enregistre la fermeture d'une position."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.POSITION_CLOSED.value,
            symbol=getattr(pos, "symbol", "?"),
            signal=(
                "BUY"
                if getattr(pos, "side", None) and pos.side.value == "long"
                else "SELL"
            ),
            score=getattr(pos, "signal_score", 0),
            regime=getattr(pos, "regime", "unknown"),
            personality=getattr(pos, "symbol", "main"),
            price=getattr(pos, "current_price", 0.0),
            reason=f"Fermé: {reason.value if hasattr(reason, 'value') else reason}",
            pnl_pct=getattr(pos, "pnl_pct", 0.0),
            close_reason=reason.value if hasattr(reason, "value") else str(reason),
            order_id=getattr(pos, "order_id", ""),
            conviction_level=getattr(pos, "conviction_level", "unknown"),
            order_size=getattr(pos, "size_usd", 0.0),
        )
        self._append(entry)
        return entry

    def record_halt(
        self, reason: str, level: str = "WARNING", source: str = "system"
    ) -> BlackBoxEntry:
        """Enregistre un halt ou safe mode."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.HALT_TRIGGERED.value,
            symbol="ALL",
            signal="HALT",
            score=0,
            regime="unknown",
            personality=source,
            price=0.0,
            reason=reason,
            awareness_level=level,
        )
        self._append(entry)
        return entry

    def record_system_event(
        self, event: str, detail: str = "", symbol: str = "SYSTEM"
    ) -> BlackBoxEntry:
        """Enregistre un événement système (démarrage, crash, reconnexion)."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.SYSTEM_EVENT.value,
            symbol=symbol,
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="system",
            price=0.0,
            reason=f"{event}: {detail}" if detail else event,
        )
        self._append(entry)
        return entry

    def record_regime_change(
        self, symbol: str, old_regime: str, new_regime: str, price: float
    ) -> BlackBoxEntry:
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.REGIME_CHANGE.value,
            symbol=symbol,
            signal="REGIME",
            score=0,
            regime=new_regime,
            personality="regime_detector",
            price=price,
            reason=f"Régime: {old_regime} -> {new_regime}",
        )
        self._append(entry)
        return entry

    # ── Requêtes ──────────────────────────────────────────────────────────────

    def query(
        self,
        decision_type: str = None,
        symbol: str = None,
        regime: str = None,
        since_ts: float = None,
        limit: int = 50,
    ) -> list[BlackBoxEntry]:
        """Filtre les entrées. Retourne les N plus récentes."""
        self._ensure_loaded()
        results = self._entries
        if decision_type:
            results = [e for e in results if e.decision_type == decision_type]
        if symbol:
            results = [e for e in results if e.symbol == symbol]
        if regime:
            results = [e for e in results if e.regime == regime]
        if since_ts:
            results = [e for e in results if e.ts >= since_ts]
        return sorted(results, key=lambda e: e.ts, reverse=True)[:limit]

    def last_refused_trades(self, limit: int = 10) -> list[BlackBoxEntry]:
        return self.query(decision_type=DecisionType.TRADE_REFUSED.value, limit=limit)

    def last_executed_trades(self, limit: int = 10) -> list[BlackBoxEntry]:
        return self.query(decision_type=DecisionType.TRADE_EXECUTED.value, limit=limit)

    def stats(self) -> dict:
        self._ensure_loaded()
        if not self._entries:
            return {"total": 0}
        by_type: dict[str, int] = {}
        for e in self._entries:
            by_type[e.decision_type] = by_type.get(e.decision_type, 0) + 1
        refused = [
            e
            for e in self._entries
            if e.decision_type == DecisionType.TRADE_REFUSED.value
        ]
        refusal_reasons: dict[str, int] = {}
        for e in refused:
            top = e.refused_by[0].split(":")[0] if e.refused_by else "unknown"
            refusal_reasons[top] = refusal_reasons.get(top, 0) + 1
        return {
            "total": len(self._entries),
            "by_type": by_type,
            "top_refusals": sorted(refusal_reasons.items(), key=lambda x: -x[1])[:5],
            "executed_today": sum(
                1
                for e in self._entries
                if e.decision_type == DecisionType.TRADE_EXECUTED.value
                and time.time() - e.ts < 86400
            ),
        }

    def last_n_summary(self, n: int = 5) -> list[str]:
        """Résumé texte des N dernières entrées — pour Telegram."""
        self._ensure_loaded()
        recent = sorted(self._entries, key=lambda e: e.ts, reverse=True)[:n]
        lines = []
        for e in recent:
            t = datetime.fromtimestamp(e.ts).strftime("%H:%M")
            lines.append(
                f"[{t}] {e.decision_type} | {e.symbol} {e.signal} "
                f"score={e.score} {e.regime} | {e.reason[:60]}"
            )
        return lines

    # ── Persistance ───────────────────────────────────────────────────────────

    def _append(self, entry: BlackBoxEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > _BB_MAX_SIZE:
            self._entries = self._entries[-_BB_MAX_SIZE:]
        try:
            enc = _get_enc()
            line = enc.encrypt_line(asdict(entry)) + "\n"
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as exc:
            _log.warning("[BlackBox] Sauvegarde échouée: %s", exc)
        _log.debug(
            "[BlackBox] %s | %s %s score=%d | %s",
            entry.decision_type,
            entry.symbol,
            entry.signal,
            entry.score,
            entry.reason,
        )
