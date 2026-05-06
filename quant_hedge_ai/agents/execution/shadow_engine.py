"""
shadow_engine.py — Live Shadow Execution Mode (Idée #1).

Génère les vrais ordres, calcule le vrai sizing, log exactement ce qu'il aurait
fait, MAIS n'envoie jamais l'ordre à l'exchange.

Compare ensuite :
  - prix théorique (moment du signal)
  - prix réel (moment où l'ordre aurait été rempli)
  - slippage simulé
  - timing réel (latence signal→order)

Usage:
    engine = ShadowExecutionEngine(signal_engine, risk_gate, order_sizer)
    result = engine.shadow_execute(signal_result, live_price, capital=50_000)
    print(result.summary())
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHADOW_LOG = Path("databases/shadow_execution/shadow_log.jsonl")


@dataclass
class ShadowTrade:
    """Un ordre virtuel jamais envoyé à l'exchange."""

    id: str
    symbol: str
    action: str                  # BUY | SELL
    signal_score: int
    signal_price: float          # prix au moment du signal
    theoretical_price: float     # prix qu'on aurait payé (signal_price)
    simulated_fill_price: float  # prix avec slippage simulé
    size: float
    notional: float
    slippage_pct: float
    signal_to_order_ms: float    # latence signal→ordre (ms)
    regime: str
    gate_conditions: dict[str, bool]
    components: dict[str, float]
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    @property
    def simulated_pnl_if_closed_now(self) -> float:
        return 0.0  # rempli par compare_with_real()

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "action": self.action,
            "signal_score": self.signal_score,
            "signal_price": self.signal_price,
            "theoretical_price": self.theoretical_price,
            "simulated_fill_price": self.simulated_fill_price,
            "size": round(self.size, 6),
            "notional": round(self.notional, 2),
            "slippage_pct": round(self.slippage_pct, 4),
            "signal_to_order_ms": round(self.signal_to_order_ms, 2),
            "regime": self.regime,
            "gate_conditions": self.gate_conditions,
            "components": self.components,
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        return (
            f"[SHADOW] {self.action} {self.symbol} "
            f"score={self.signal_score} "
            f"théo={self.theoretical_price:.4f} "
            f"fill_sim={self.simulated_fill_price:.4f} "
            f"slippage={self.slippage_pct:.3f}% "
            f"latence={self.signal_to_order_ms:.1f}ms"
        )


class ShadowExecutionEngine:
    """
    Moteur d'exécution fantôme — aucun ordre réel envoyé.

    Branché sur LiveSignalEngine + GlobalRiskGate + OrderSizer, il simule
    l'exécution complète et loggue tout dans databases/shadow_execution/.
    """

    # Modèle de slippage par défaut (en %)
    _SLIPPAGE_BY_REGIME = {
        "bull_trend": 0.05,
        "bear_trend": 0.08,
        "sideways": 0.04,
        "high_volatility_regime": 0.25,
        "flash_crash": 1.20,
        "unknown": 0.10,
    }

    def __init__(
        self,
        risk_gate=None,
        order_sizer=None,
        base_slippage_pct: float = 0.08,
        log_path: Path | None = None,
    ) -> None:
        self._risk_gate = risk_gate
        self._order_sizer = order_sizer
        self._base_slippage = base_slippage_pct
        self._log_path = log_path or _SHADOW_LOG
        self._trades: list[ShadowTrade] = []
        self._trade_counter: int = 0

    # ── API principale ─────────────────────────────────────────────────────────

    def shadow_execute(
        self,
        signal_result,
        live_price: float,
        capital: float = 100_000.0,
        portfolio_drawdown: float = 0.0,
        extra_metadata: dict | None = None,
    ) -> ShadowTrade | None:
        """
        Simule un ordre complet sans l'envoyer.

        Returns:
            ShadowTrade si le gate passe, None si le gate bloque
        """
        t_signal = time.perf_counter()

        # ① Vérification gate
        gate_result = self._run_gate(signal_result, portfolio_drawdown, live_price)
        if not gate_result.allowed:
            logger.info(
                "[Shadow] GATE BLOCK %s — %s", signal_result.symbol, gate_result.failed
            )
            return None

        # ② Calcul du sizing
        size = self._compute_size(signal_result, capital, live_price)
        if size <= 0:
            return None

        # ③ Calcul slippage simulé
        slippage_pct = self._estimate_slippage(signal_result.regime)
        direction = 1.0 if signal_result.signal == "BUY" else -1.0
        fill_price = live_price * (1.0 + direction * slippage_pct / 100.0)

        # ④ Mesure latence
        t_order = time.perf_counter()
        latency_ms = (t_order - t_signal) * 1000.0

        self._trade_counter += 1
        trade_id = f"SHD-{int(time.time())}-{self._trade_counter:04d}"

        trade = ShadowTrade(
            id=trade_id,
            symbol=signal_result.symbol,
            action=signal_result.signal,
            signal_score=signal_result.score,
            signal_price=live_price,
            theoretical_price=live_price,
            simulated_fill_price=round(fill_price, 6),
            size=size,
            notional=round(size * live_price, 2),
            slippage_pct=slippage_pct,
            signal_to_order_ms=latency_ms,
            regime=signal_result.regime,
            gate_conditions=gate_result.conditions,
            components=signal_result.components,
            metadata=extra_metadata or {},
        )

        self._trades.append(trade)
        self._persist(trade)

        logger.info(trade.summary())
        return trade

    def compare_with_real(
        self, shadow_id: str, real_fill_price: float
    ) -> dict[str, Any]:
        """Compare un trade shadow avec son prix réel de fill."""
        trade = next((t for t in self._trades if t.id == shadow_id), None)
        if trade is None:
            return {"error": "trade not found"}

        price_gap = real_fill_price - trade.simulated_fill_price
        price_gap_pct = price_gap / trade.theoretical_price * 100.0

        return {
            "id": shadow_id,
            "symbol": trade.symbol,
            "action": trade.action,
            "theoretical_price": trade.theoretical_price,
            "simulated_fill": trade.simulated_fill_price,
            "real_fill": real_fill_price,
            "gap_usd": round(price_gap, 6),
            "gap_pct": round(price_gap_pct, 4),
            "model_error_usd": round(abs(price_gap) * trade.size, 2),
        }

    def stats(self) -> dict:
        """Statistiques agrégées sur les trades shadow."""
        if not self._trades:
            return {"n_trades": 0}

        slippages = [t.slippage_pct for t in self._trades]
        latencies = [t.signal_to_order_ms for t in self._trades]
        by_regime: dict[str, int] = {}
        for t in self._trades:
            by_regime[t.regime] = by_regime.get(t.regime, 0) + 1

        return {
            "n_trades": len(self._trades),
            "avg_slippage_pct": round(sum(slippages) / len(slippages), 4),
            "max_slippage_pct": round(max(slippages), 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "max_latency_ms": round(max(latencies), 2),
            "by_regime": by_regime,
        }

    def last_trades(self, n: int = 20) -> list[dict]:
        return [t.as_dict() for t in self._trades[-n:]]

    # ── Sous-fonctions ─────────────────────────────────────────────────────────

    def _run_gate(self, signal_result, drawdown: float, price: float):
        if self._risk_gate is None:
            from dataclasses import dataclass as _dc, field as _f

            @_dc
            class _FakeGate:
                allowed: bool = True
                conditions: dict = _f(default_factory=dict)
                failed: list = _f(default_factory=list)

            return _FakeGate(allowed=True, conditions={}, failed=[])
        return self._risk_gate.check(signal_result, portfolio_drawdown=drawdown)

    def _compute_size(
        self, signal_result, capital: float, price: float
    ) -> float:
        if self._order_sizer is None:
            notional = capital * 0.01  # 1 % du capital par défaut
            return round(notional / price, 6) if price > 0 else 0.0
        try:
            result = self._order_sizer.compute_from_signal(signal_result, capital)
            return result.size_base
        except Exception as exc:
            logger.debug("[Shadow] OrderSizer error: %s", exc)
            return 0.0

    def _estimate_slippage(self, regime: str) -> float:
        return self._SLIPPAGE_BY_REGIME.get(regime, self._base_slippage)

    def _persist(self, trade: ShadowTrade) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(trade.as_dict()) + "\n")
        except Exception as exc:
            logger.warning("[Shadow] Persist error: %s", exc)
