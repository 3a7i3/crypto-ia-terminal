from __future__ import annotations

import logging
import os

from supervision.alert_manager import Alert, AlertManager
from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.trade_logger import TradeLogger
from quant_hedge_ai.agents.risk.session_guard import (
    OrderTooLargeError,
    SessionGuard,
    SessionHaltedError,
)

logger = logging.getLogger(__name__)

alert_manager = AlertManager()


def execution_autoheal(alert):
    return {"action": "force_size", "new_size": 1.0}


alert_manager.register_autoheal("execution", execution_autoheal)


class ExecutionEngine:
    """
    Moteur d'exécution — mode paper par défaut, live si BINANCE_API_KEY est défini.

    Safety layer (toujours actif, paper et live) :
      1. OrderDeduplicator  — bloque les ordres dupliqués (< 30 s)
      2. SessionGuard       — halt si drawdown / pertes consécutives dépassent les seuils
      3. TradeLogger        — log SQLite de tous les ordres (audit)
    """

    def __init__(self, live: bool = False) -> None:
        self._size_factor: float = 1.0
        self._live = live
        self._exchange = None
        if live:
            self._exchange = self._init_exchange()

        # Safety layer
        self._dedup = OrderDeduplicator(
            window_seconds=float(os.getenv("EXEC_DEDUP_WINDOW", "30"))
        )
        self._guard = SessionGuard(
            max_session_drawdown=float(os.getenv("EXEC_MAX_DD", "0.05")),
            max_session_loss=float(os.getenv("EXEC_MAX_LOSS", "0.03")),
            max_consecutive_losses=int(os.getenv("EXEC_MAX_CONSEC_LOSSES", "3")),
            max_order_size_usd=float(os.getenv("EXEC_MAX_ORDER_USD", "10000")),
        )
        self._logger = TradeLogger(
            db_path=os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite")
        )

    def _init_exchange(self):
        """Initialise un exchange ccxt avec les clés API depuis l'environnement."""
        try:
            import ccxt

            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if not api_key or not api_secret:
                logger.warning(
                    "[ExecutionEngine] BINANCE_API_KEY/SECRET manquants — bascule paper"
                )
                self._live = False
                return None
            config: dict = {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
            if os.getenv("BINANCE_TESTNET", "false").lower() == "true":
                config["options"] = {"defaultType": "spot"}
                config["urls"] = {
                    "api": {
                        "public": "https://testnet.binance.vision/api",
                        "private": "https://testnet.binance.vision/api",
                    }
                }
                logger.info("[ExecutionEngine] Mode TESTNET Binance activé")
            else:
                logger.info("[ExecutionEngine] Mode LIVE Binance activé")
            return ccxt.binance(config)
        except Exception as exc:
            logger.error("[ExecutionEngine] Impossible d'initialiser ccxt: %s", exc)
            self._live = False
            return None

    @classmethod
    def from_env(cls) -> "ExecutionEngine":
        """Retourne un moteur live si les clés API sont présentes, sinon paper."""
        live = bool(os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET"))
        return cls(live=live)

    # ── Configuration ──────────────────────────────────────────────────────────

    def set_size_factor(self, factor: float) -> None:
        self._size_factor = max(0.0, min(1.0, float(factor)))

    def start_session(self, equity: float) -> None:
        """Reset session-level risk counters. Call once per trading session."""
        self._guard.start_session(equity)

    # ── Main API ───────────────────────────────────────────────────────────────

    def create_order(self, symbol: str, action: str, size: float) -> dict:
        """
        Place an order through the full safety pipeline.

        Returns an order dict with a `mode` field:
          - "paper"       — paper trade accepted
          - "live"        — live order filled
          - "live_failed" — live order failed (exchange error)
          - "rejected"    — blocked by safety layer
        """
        size = size * self._size_factor

        # ── 1. Sanity check on size ────────────────────────────────────────────
        if size <= 0 or size > 1e9:
            alert = Alert(
                type_="order_size_anomaly",
                severity="critical",
                module="execution",
                message=f"Taille d'ordre anormale : {size}",
                context={"symbol": symbol, "action": action, "size": size},
            )
            alert_manager.raise_alert(alert)
            size = 1.0

        # ── 2. SessionGuard ────────────────────────────────────────────────────
        try:
            self._guard.check_order(symbol, action, size_usd=size)
        except (SessionHaltedError, OrderTooLargeError) as exc:
            reason = str(exc)
            logger.warning("[ExecutionEngine] Order rejected by SessionGuard: %s", reason)
            self._logger.log_rejected(symbol, action, size, reason)
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "rejected",
                "error": reason,
            }

        # ── 3. Deduplication ───────────────────────────────────────────────────
        if self._dedup.is_duplicate(symbol, action, size):
            reason = f"duplicate order within {self._dedup._window:.0f}s window"
            self._logger.log_rejected(symbol, action, size, reason)
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "rejected",
                "error": reason,
            }

        # ── 4. Execute ────────────────────────────────────────────────────────
        if self._live and self._exchange is not None:
            result = self._place_live_order(symbol, action, size)
        else:
            result = {
                "symbol": symbol,
                "action": action,
                "size": round(max(0.0, size), 4),
                "mode": "paper",
            }

        # ── 5. Register dedup + audit log ─────────────────────────────────────
        self._dedup.register(symbol, action, size)
        status = "ok" if result.get("mode") != "live_failed" else "error"
        self._logger.log(result, status=status)

        return result

    # ── Live order placement ───────────────────────────────────────────────────

    def _place_live_order(self, symbol: str, action: str, size: float) -> dict:
        """Passe un ordre market réel via ccxt."""
        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_symbol = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        try:
            order = self._exchange.create_order(ccxt_symbol, "market", side, size)
            logger.info(
                "[ExecutionEngine] Ordre live: %s %s %s → id=%s",
                action, size, symbol, order.get("id"),
            )
            return {**order, "mode": "live"}
        except Exception as exc:
            logger.error(
                "[ExecutionEngine] Echec ordre live %s %s: %s", action, symbol, exc
            )
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "live_failed",
                "error": str(exc),
            }

    # ── Observability ──────────────────────────────────────────────────────────

    def safety_status(self) -> dict:
        """Return a snapshot of all safety-layer state."""
        return {
            "session": self._guard.state(),
            "trade_log": self._logger.stats(),
            "live_mode": self._live,
        }
