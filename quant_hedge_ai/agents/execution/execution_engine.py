from __future__ import annotations

import logging
import os

from supervision.alert_manager import Alert, AlertManager

logger = logging.getLogger(__name__)

alert_manager = AlertManager()


def execution_autoheal(alert):
    return {"action": "force_size", "new_size": 1.0}


alert_manager.register_autoheal("execution", execution_autoheal)


class ExecutionEngine:
    """Moteur d'exécution — mode paper par défaut, live si BINANCE_API_KEY est défini."""

    def __init__(self, live: bool = False) -> None:
        self._size_factor: float = 1.0
        self._live = live
        self._exchange = None
        if live:
            self._exchange = self._init_exchange()

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

    def set_size_factor(self, factor: float) -> None:
        self._size_factor = max(0.0, min(1.0, float(factor)))

    def create_order(self, symbol: str, action: str, size: float) -> dict:
        size = size * self._size_factor
        if size <= 0 or size > 1e6:
            alert = Alert(
                type_="order_size_anomaly",
                severity="critical",
                module="execution",
                message=f"Taille d'ordre anormale : {size}",
                context={"symbol": symbol, "action": action, "size": size},
            )
            alert_manager.raise_alert(alert)
            size = 1.0

        if self._live and self._exchange is not None:
            return self._place_live_order(symbol, action, size)

        return {
            "symbol": symbol,
            "action": action,
            "size": round(max(0.0, size), 4),
            "mode": "paper",
        }

    def _place_live_order(self, symbol: str, action: str, size: float) -> dict:
        """Passe un ordre market réel via ccxt."""
        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_symbol = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        try:
            order = self._exchange.create_order(ccxt_symbol, "market", side, size)
            logger.info(
                "[ExecutionEngine] Ordre live: %s %s %s → id=%s",
                action,
                size,
                symbol,
                order.get("id"),
            )
            return {**order, "mode": "live"}
        except Exception as exc:
            logger.error(
                "[ExecutionEngine] Échec ordre live %s %s: %s", action, symbol, exc
            )
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "live_failed",
                "error": str(exc),
            }
