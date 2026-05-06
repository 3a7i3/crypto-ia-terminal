"""
execution_engine_mvp.py — Execution Engine MVP

"Le plus sous-estimé."

Objectif : transformer une bonne décision en exécution propre.

  1. THIN_LIQUIDITY CHECK — ne pas entrer si spread ou liquidité dégradés
  2. TWAP léger            — découper les gros ordres dans le temps
  3. FEE-AWARE             — calculer le coût réel avant d'entrer
  4. SL/TP automatique     — poser les niveaux à l'entrée, pas après

Tout est synchrone et simple. Pas de complexité inutile.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    symbol: str
    direction: str
    status: str             # "executed" | "rejected" | "partial"
    executed_size_usd: float = 0.0
    entry_price: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    estimated_slippage_bps: float = 0.0
    total_fee_usd: float = 0.0
    net_cost_usd: float = 0.0
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def risk_reward(self) -> float:
        if self.entry_price == 0 or self.stop_loss_price == 0 or self.take_profit_price == 0:
            return 0.0
        risk  = abs(self.entry_price - self.stop_loss_price)
        reward = abs(self.take_profit_price - self.entry_price)
        return reward / risk if risk > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def summary(self) -> str:
        return (
            f"{self.status.upper()} {self.direction} {self.symbol} "
            f"@ {self.entry_price:.4f} | SL={self.stop_loss_price:.4f} TP={self.take_profit_price:.4f} "
            f"RR={self.risk_reward:.1f} | fee=${self.total_fee_usd:.3f}"
        )


class ExecutionEngineMVP:
    """
    Exécution fee-aware avec TWAP léger et vérification de liquidité.

    SL/TP calculés automatiquement depuis l'ATR :
      - SL = entry ± 1.5 × ATR
      - TP = entry ± 2.5 × ATR  (RR = 1.67)

    Ces valeurs sont les défauts conservateurs. Configurables.
    """

    MAX_SPREAD_BPS = 25.0       # refuse si spread > 25bps
    MIN_LIQUIDITY_USD = 20_000  # refuse si depth < 20k USD
    SL_ATR_MULT = 1.5
    TP_ATR_MULT = 2.5
    TWAP_THRESHOLD_USD = 500.0  # découpe si ordre > 500$

    def __init__(
        self,
        exchange=None,
        taker_fee: float = 0.0004,
        maker_fee: float = 0.0002,
        paper_mode: bool = True,
    ) -> None:
        self._exchange = exchange
        self._taker_fee = taker_fee
        self._maker_fee = maker_fee
        self._paper = paper_mode
        self._executed: list[ExecutionResult] = []

    def execute(
        self,
        symbol: str,
        direction: str,
        size_usd: float,
        signal_score: float,
        atr_pct: float = 0.01,
        current_price: float = 0.0,
        spread_bps: float = 5.0,
        liquidity_depth_usd: float = 500_000.0,
    ) -> ExecutionResult:
        """
        Exécute ou simule un ordre.
        Retourne un ExecutionResult avec tous les détails.
        """
        # ── 1. Liquidity check ─────────────────────────────────────────────
        liq_ok, liq_reason = self._check_liquidity(spread_bps, liquidity_depth_usd, size_usd)
        if not liq_ok:
            return ExecutionResult(symbol, direction, "rejected", reason=f"LIQUIDITY: {liq_reason}")

        # ── 2. Prix d'entrée (live ou paper) ──────────────────────────────
        entry_price = self._get_entry_price(symbol, direction, current_price)
        if entry_price <= 0:
            return ExecutionResult(symbol, direction, "rejected", reason="Prix indisponible")

        # ── 3. Fee calculation ─────────────────────────────────────────────
        fee_usd = size_usd * self._taker_fee   # on suppose taker par défaut
        slippage_bps = self._estimate_slippage(size_usd, spread_bps, liquidity_depth_usd)
        slippage_cost = size_usd * slippage_bps / 10000.0
        net_cost = fee_usd + slippage_cost

        # ── 4. SL / TP automatiques ───────────────────────────────────────
        atr_abs = entry_price * atr_pct
        if direction == "long":
            sl_price = entry_price - atr_abs * self.SL_ATR_MULT
            tp_price = entry_price + atr_abs * self.TP_ATR_MULT
        else:
            sl_price = entry_price + atr_abs * self.SL_ATR_MULT
            tp_price = entry_price - atr_abs * self.TP_ATR_MULT

        # ── 5. TWAP si ordre trop gros ────────────────────────────────────
        if size_usd > self.TWAP_THRESHOLD_USD:
            result = self._execute_twap(symbol, direction, size_usd, entry_price)
        else:
            result = self._execute_single(symbol, direction, size_usd, entry_price)

        if result.status == "executed":
            result.stop_loss_price    = round(sl_price, 8)
            result.take_profit_price  = round(tp_price, 8)
            result.estimated_slippage_bps = slippage_bps
            result.total_fee_usd      = round(fee_usd + slippage_cost, 4)
            result.net_cost_usd       = round(net_cost, 4)
            self._executed.append(result)
            logger.info("[ExecMVP] %s", result.summary())

        return result

    def check_exit(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        entry_result: ExecutionResult,
    ) -> tuple[bool, str]:
        """
        Vérifie si SL ou TP est atteint.
        Retourne (should_exit, reason).
        """
        if direction == "long":
            if current_price <= entry_result.stop_loss_price:
                return True, f"SL atteint @ {current_price:.4f}"
            if current_price >= entry_result.take_profit_price:
                return True, f"TP atteint @ {current_price:.4f}"
        else:
            if current_price >= entry_result.stop_loss_price:
                return True, f"SL atteint @ {current_price:.4f}"
            if current_price <= entry_result.take_profit_price:
                return True, f"TP atteint @ {current_price:.4f}"
        return False, ""

    def history(self, n: int = 20) -> list[dict]:
        return [r.to_dict() for r in self._executed[-n:]]

    # ──────────────────────────────────────────────────────────────────────────
    # Interne
    # ──────────────────────────────────────────────────────────────────────────

    def _check_liquidity(
        self, spread_bps: float, depth_usd: float, order_size: float
    ) -> tuple[bool, str]:
        if spread_bps > self.MAX_SPREAD_BPS:
            return False, f"spread {spread_bps:.1f}bps > {self.MAX_SPREAD_BPS}bps"
        if depth_usd < self.MIN_LIQUIDITY_USD:
            return False, f"profondeur ${depth_usd:.0f} < ${self.MIN_LIQUIDITY_USD}"
        # Ne pas prendre plus de 3% de la liquidité disponible
        if order_size > depth_usd * 0.03:
            return False, f"ordre ${order_size:.0f} > 3% liquidité (${depth_usd:.0f})"
        return True, "OK"

    def _get_entry_price(self, symbol: str, direction: str, fallback: float) -> float:
        if self._paper or self._exchange is None:
            return fallback
        try:
            ob = self._exchange.fetch_order_book(symbol, limit=5)
            if direction == "long":
                return float(ob["asks"][0][0]) if ob["asks"] else fallback
            else:
                return float(ob["bids"][0][0]) if ob["bids"] else fallback
        except Exception:
            return fallback

    def _estimate_slippage(self, size_usd: float, spread_bps: float, depth_usd: float) -> float:
        base = spread_bps * 0.5
        impact = (size_usd / max(depth_usd, 1.0)) * 100
        return min(base + impact, 50.0)

    def _execute_single(self, symbol: str, direction: str, size_usd: float, price: float) -> ExecutionResult:
        if self._paper:
            return ExecutionResult(symbol, direction, "executed",
                                   executed_size_usd=size_usd, entry_price=price,
                                   reason="paper_trade")
        try:
            side = "buy" if direction == "long" else "sell"
            qty  = size_usd / price
            order = self._exchange.create_market_order(symbol, side, qty)
            actual_price = float(order.get("average", order.get("price", price)))
            return ExecutionResult(symbol, direction, "executed",
                                   executed_size_usd=size_usd,
                                   entry_price=actual_price,
                                   reason=f"order_id={order.get('id','?')}")
        except Exception as exc:
            logger.error("[ExecMVP] Order failed: %s", exc)
            return ExecutionResult(symbol, direction, "rejected", reason=str(exc))

    def _execute_twap(
        self, symbol: str, direction: str, size_usd: float, price: float, n_chunks: int = 3
    ) -> ExecutionResult:
        """TWAP léger : divise en n chunks avec délai de 10s entre chaque."""
        chunk = size_usd / n_chunks
        total_executed = 0.0
        avg_price = 0.0

        for i in range(n_chunks):
            result = self._execute_single(symbol, direction, chunk, price)
            if result.status == "executed":
                total_executed += chunk
                avg_price += result.entry_price / n_chunks
            if i < n_chunks - 1 and not self._paper:
                time.sleep(10)

        if total_executed > 0:
            return ExecutionResult(symbol, direction, "executed",
                                   executed_size_usd=total_executed,
                                   entry_price=avg_price,
                                   reason=f"TWAP {n_chunks} chunks")
        return ExecutionResult(symbol, direction, "rejected", reason="TWAP: tous les chunks ont échoué")
