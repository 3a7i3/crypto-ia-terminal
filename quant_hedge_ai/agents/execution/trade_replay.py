"""
trade_replay.py -- Trade Replay System (Idée #5).

Permet de rejouer n'importe quel trade par son ID et de voir :
  - pourquoi il a été pris (score exact, régime, confirmations TF)
  - sizing exact
  - reason code
  - comparaison entrée/sortie

Les trades sont persistés par PaperTradingEngine + TradeLogger.
TradeReplaySystem lit ces logs et reconstitue le contexte complet.

Usage:
    replay = TradeReplaySystem(trade_log_path="databases/paper_trading/state.json")
    report = replay.replay(trade_id="SHD-1714300000-0001")
    print(report.render())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.execution.trade_replay")
_PAPER_STATE = Path("databases/paper_trading/state.json")
_SHADOW_LOG = Path("databases/shadow_execution/shadow_log.jsonl")
_TRADE_LOG = Path("databases/trades/trade_log.jsonl")


@dataclass
class ReplayReport:
    """Rapport complet d'un trade rejoué."""

    trade_id: str
    found: bool
    symbol: str = ""
    action: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    entry_score: int = 0
    regime: str = ""
    signal_confirmed: bool = False
    signal_strength: float = 0.0
    components: dict = field(default_factory=dict)
    gate_conditions: dict = field(default_factory=dict)
    size: float = 0.0
    notional: float = 0.0
    slippage_pct: float = 0.0
    latency_ms: float = 0.0
    reason_code: str = ""
    raw: dict = field(default_factory=dict)
    source: str = "unknown"  # paper_engine | shadow_log | trade_log

    def render(self) -> str:
        if not self.found:
            return f"[TradeReplay] Trade '{self.trade_id}' not found."

        lines = [
            f"{'='*60}",
            f"TRADE REPLAY -- {self.trade_id}",
            f"{'='*60}",
            f"Symbol    : {self.symbol}",
            f"Action    : {self.action}",
            f"Regime    : {self.regime}",
            f"Score     : {self.entry_score}/100",
            f"Confirmed : {'yes' if self.signal_confirmed else 'no'} "
            f"(strength {self.signal_strength:.0%})",
        ]

        if self.components:
            lines.append("Components:")
            for k, v in self.components.items():
                lines.append(f"  {k:<18} = {v:.2f}")

        if self.gate_conditions:
            lines.append("Gate conditions :")
            for k, v in self.gate_conditions.items():
                status = "[OK]" if v else "[KO]"
                lines.append(f"  {status} {k}")

        lines += [
            f"{'-'*40}",
            f"Entry     : {self.entry_price:.6f}",
            (
                f"Exit      : {self.exit_price:.6f}"
                if self.exit_price
                else "Exit      : (open position)"
            ),
            f"Size      : {self.size:.6f}",
            f"Notional  : {self.notional:,.2f} USD",
        ]

        if self.slippage_pct:
            lines.append(f"Slippage  : {self.slippage_pct:.3f}%")
        if self.latency_ms:
            lines.append(f"Latency   : {self.latency_ms:.1f}ms")

        if self.exit_price:
            sign = "+" if self.pnl >= 0 else ""
            lines += [
                f"{'-'*40}",
                f"PnL       : {sign}{self.pnl:.4f} USD ({sign}{self.pnl_pct:.2f}%)",
            ]

        if self.reason_code:
            lines.append(f"Reason    : {self.reason_code}")

        lines += [f"Source    : {self.source}", f"{'='*60}"]
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "found": self.found,
            "symbol": self.symbol,
            "action": self.action,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "entry_score": self.entry_score,
            "regime": self.regime,
            "signal_confirmed": self.signal_confirmed,
            "signal_strength": self.signal_strength,
            "components": self.components,
            "gate_conditions": self.gate_conditions,
            "size": self.size,
            "notional": self.notional,
            "slippage_pct": self.slippage_pct,
            "latency_ms": self.latency_ms,
            "reason_code": self.reason_code,
            "source": self.source,
        }


class TradeReplaySystem:
    """
    Reconstitue le contexte complet d'un trade depuis les logs persistés.

    Sources (par ordre de richesse d'information) :
      1. Shadow log (le plus riche : slippage, latence, gate, components)
      2. Trade log JSONL (trade_log.jsonl)
      3. Paper engine state.json (le moins riche)
    """

    def __init__(
        self,
        paper_state_path: Path | None = None,
        shadow_log_path: Path | None = None,
        trade_log_path: Path | None = None,
    ) -> None:
        self._paper_state = paper_state_path or _PAPER_STATE
        self._shadow_log = shadow_log_path or _SHADOW_LOG
        self._trade_log = trade_log_path or _TRADE_LOG

    # -- API principale ---------------------------------------------------------

    def replay(self, trade_id: str) -> ReplayReport:
        """Retrouve et reconstitue le contexte complet d'un trade."""
        # 1. Shadow log
        rec = self._find_in_shadow(trade_id)
        if rec:
            return self._from_shadow(trade_id, rec)

        # 2. Trade log JSONL
        rec = self._find_in_jsonl(self._trade_log, "id", trade_id)
        if rec:
            return self._from_trade_log(trade_id, rec)

        # 3. Paper engine state
        rec = self._find_in_paper_state(trade_id)
        if rec:
            return self._from_paper_state(trade_id, rec)

        return ReplayReport(trade_id=trade_id, found=False)

    def list_trades(self, n: int = 50, source: str = "shadow") -> list[dict]:
        """Retourne les N derniers trades depuis la source choisie."""
        if source == "shadow":
            return self._read_jsonl(self._shadow_log, n)
        if source == "trade_log":
            return self._read_jsonl(self._trade_log, n)
        trades = self._load_paper_state_trades()
        return trades[-n:]

    def search(
        self,
        symbol: str | None = None,
        regime: str | None = None,
        min_score: int = 0,
        n: int = 100,
    ) -> list[dict]:
        """Cherche des trades selon des critères dans le shadow log."""
        records = self._read_jsonl(self._shadow_log, 0)  # 0 = tout
        results = []
        for r in records:
            if symbol and r.get("symbol") != symbol:
                continue
            if regime and r.get("regime") != regime:
                continue
            if r.get("signal_score", 0) < min_score:
                continue
            results.append(r)
        return results[-n:]

    # -- Parseurs ---------------------------------------------------------------

    def _from_shadow(self, trade_id: str, rec: dict) -> ReplayReport:
        return ReplayReport(
            trade_id=trade_id,
            found=True,
            symbol=rec.get("symbol", ""),
            action=rec.get("action", ""),
            entry_price=rec.get("signal_price", 0.0),
            exit_price=0.0,
            pnl=0.0,
            pnl_pct=0.0,
            entry_score=rec.get("signal_score", 0),
            regime=rec.get("regime", ""),
            signal_confirmed=rec.get("components", {}).get("mtf", 0) >= 25,
            signal_strength=rec.get("components", {}).get("mtf", 0) / 40.0,
            components=rec.get("components", {}),
            gate_conditions=rec.get("gate_conditions", {}),
            size=rec.get("size", 0.0),
            notional=rec.get("notional", 0.0),
            slippage_pct=rec.get("slippage_pct", 0.0),
            latency_ms=rec.get("signal_to_order_ms", 0.0),
            reason_code="shadow_trade",
            raw=rec,
            source="shadow_log",
        )

    def _from_trade_log(self, trade_id: str, rec: dict) -> ReplayReport:
        entry = rec.get("entry_price", rec.get("price", 0.0))
        exit_p = rec.get("exit_price", 0.0)
        size = rec.get("size", 0.0)
        pnl = rec.get("pnl", 0.0)
        pnl_pct = (pnl / (entry * size) * 100) if (entry and size) else 0.0

        return ReplayReport(
            trade_id=trade_id,
            found=True,
            symbol=rec.get("symbol", ""),
            action=rec.get("action", ""),
            entry_price=entry,
            exit_price=exit_p,
            pnl=pnl,
            pnl_pct=round(pnl_pct, 4),
            entry_score=rec.get("score", rec.get("signal_score", 0)),
            regime=rec.get("regime", ""),
            signal_confirmed=rec.get("confirmed", False),
            signal_strength=rec.get("strength", 0.0),
            components=rec.get("components", {}),
            gate_conditions={},
            size=size,
            notional=rec.get("notional", round(size * entry, 2)),
            reason_code=rec.get("reason", ""),
            raw=rec,
            source="trade_log",
        )

    def _from_paper_state(self, trade_id: str, rec: dict) -> ReplayReport:
        price = rec.get("price", 0.0)
        size = rec.get("size", 0.0)
        pnl = rec.get("pnl", 0.0)
        pnl_pct = (pnl / (price * size) * 100) if (price and size) else 0.0

        return ReplayReport(
            trade_id=trade_id,
            found=True,
            symbol=rec.get("symbol", ""),
            action=rec.get("action", ""),
            entry_price=price,
            size=size,
            notional=rec.get("notional", 0.0),
            pnl=pnl,
            pnl_pct=round(pnl_pct, 4),
            raw=rec,
            source="paper_engine",
        )

    # -- Loaders ----------------------------------------------------------------

    def _find_in_shadow(self, trade_id: str) -> dict | None:
        return self._find_in_jsonl(self._shadow_log, "id", trade_id)

    def _find_in_jsonl(self, path: Path, key: str, value: str) -> dict | None:
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line.strip())
                        if rec.get(key) == value:
                            return rec
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            _log.debug("[TradeReplay] JSONL read error %s: %s", path, exc)
        return None

    def _read_jsonl(self, path: Path, n: int) -> list[dict]:
        if not path.exists():
            return []
        records = []
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        records.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return records[-n:] if n > 0 else records

    def _load_paper_state_trades(self) -> list[dict]:
        if not self._paper_state.exists():
            return []
        try:
            state = json.loads(self._paper_state.read_text(encoding="utf-8"))
            return state.get("trade_history", [])
        except Exception:
            return []

    def _find_in_paper_state(self, trade_id: str) -> dict | None:
        trades = self._load_paper_state_trades()
        for t in trades:
            if str(t.get("id", t.get("ts", ""))) == trade_id:
                return t
        return None
