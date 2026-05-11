"""
subaccount_manager.py — Architecture Multi-Subcompte

Chaque subcompte est une unité isolée avec :
  - ses propres clés API
  - sa propre stratégie (momentum, volatility, experimental, shadow, genetic)
  - son propre SessionGuard (drawdown indépendant)
  - son propre PositionManager
  - son propre TradeLogger
  - un kill switch individuel

Architecture recommandée :
  Master Account   → supervision globale, audit, dashboard
  Subaccount A     → BTC Momentum (conservateur, swing MTF)
  Subaccount B     → ETH Volatility (agressif, futures rapides)
  Subaccount C     → SOL Experimental (tests nouvelles stratégies)
  Subaccount D     → Shadow / Validation (dry-run réaliste)
  Subaccount E     → Genetic Optimizer (stratégies auto-générées)

Usage :
    mgr = SubaccountManager.from_env()
    mgr.get("btc_momentum").create_order("BTC/USDT", "BUY", 55)
    mgr.global_stats()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SubaccountConfig:
    """Configuration d'un subcompte."""

    name:         str
    label:        str                    # ex: "BTC Momentum"
    exchange:     str = "binance"        # binance | bybit | okx
    mode:         str = "futures_demo"   # futures_demo | spot_testnet | live | paper

    # Clés API — vides = hérite du master ou paper mode
    api_key:      str = ""
    api_secret:   str = ""

    # Stratégie
    strategy:     str = "momentum"       # momentum | volatility | experimental | shadow | genetic
    symbols:      list = field(default_factory=lambda: ["BTC/USDT"])
    leverage:     int  = 1

    # Risk individuel
    max_dd:             float = 0.03     # drawdown max session (3%)
    max_loss:           float = 0.02     # perte cumulée max (2%)
    max_consec_losses:  int   = 3
    max_order_usd:      float = 50.0
    tp_pct:             float = 0.04
    sl_pct:             float = 0.02
    trailing_pct:       float = 0.0
    kelly_safety:       float = 0.25

    # Flags
    active:       bool = True
    shadow_only:  bool = False           # True = jamais d'ordres réels


# ── Subcomptes préconfigurés (recommandation architecture) ────────────────────

PRESET_SUBACCOUNTS = {
    "btc_momentum": SubaccountConfig(
        name="btc_momentum",
        label="BTC Momentum",
        strategy="momentum",
        symbols=["BTC/USDT"],
        mode="futures_demo",
        leverage=1,
        tp_pct=0.04, sl_pct=0.02, trailing_pct=0.015,
        max_order_usd=float(os.getenv("SUB_BTC_MAX_ORDER", "50")),
        api_key=os.getenv("BINANCE_FUTURES_DEMO_KEY", ""),
        api_secret=os.getenv("BINANCE_FUTURES_DEMO_SECRET", ""),
    ),
    "eth_volatility": SubaccountConfig(
        name="eth_volatility",
        label="ETH Volatility",
        strategy="volatility",
        symbols=["ETH/USDT"],
        mode="futures_demo",
        leverage=2,
        tp_pct=0.06, sl_pct=0.025, trailing_pct=0.02,
        max_order_usd=float(os.getenv("SUB_ETH_MAX_ORDER", "55")),
        max_dd=0.04,
        api_key=os.getenv("BINANCE_FUTURES_DEMO_KEY", ""),
        api_secret=os.getenv("BINANCE_FUTURES_DEMO_SECRET", ""),
    ),
    "sol_experimental": SubaccountConfig(
        name="sol_experimental",
        label="SOL Experimental",
        strategy="experimental",
        symbols=["SOL/USDT"],
        mode="futures_demo",
        leverage=1,
        tp_pct=0.08, sl_pct=0.03,
        max_order_usd=float(os.getenv("SUB_SOL_MAX_ORDER", "55")),
        max_dd=0.05,
        api_key=os.getenv("BINANCE_FUTURES_DEMO_KEY", ""),
        api_secret=os.getenv("BINANCE_FUTURES_DEMO_SECRET", ""),
    ),
    "shadow_validation": SubaccountConfig(
        name="shadow_validation",
        label="Shadow / Validation",
        strategy="shadow",
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        mode="paper",
        leverage=1,
        shadow_only=True,
        max_order_usd=50.0,
    ),
    "genetic_optimizer": SubaccountConfig(
        name="genetic_optimizer",
        label="Genetic Optimizer Live Test",
        strategy="genetic",
        symbols=["BTC/USDT"],
        mode="futures_demo",
        leverage=1,
        tp_pct=0.05, sl_pct=0.02,
        max_order_usd=float(os.getenv("SUB_GENETIC_MAX_ORDER", "55")),
        active=False,   # désactivé jusqu'à validation backtest
        api_key=os.getenv("BINANCE_FUTURES_DEMO_KEY", ""),
        api_secret=os.getenv("BINANCE_FUTURES_DEMO_SECRET", ""),
    ),
}


class SubaccountUnit:
    """
    Unité d'exécution isolée pour un subcompte.
    Possède son propre exchange, SessionGuard, PositionManager, TradeLogger.
    """

    def __init__(self, cfg: SubaccountConfig) -> None:
        self.cfg     = cfg
        self._halted = False
        self._exchange = None
        self._position_manager = None
        self._guard  = None
        self._logger = None
        self._init()

    def _init(self) -> None:
        from quant_hedge_ai.agents.risk.session_guard import SessionGuard
        from quant_hedge_ai.agents.execution.trade_logger import TradeLogger
        from quant_hedge_ai.agents.execution.position_manager import PositionManager

        self._guard = SessionGuard(
            max_session_drawdown=self.cfg.max_dd,
            max_session_loss=self.cfg.max_loss,
            max_consecutive_losses=self.cfg.max_consec_losses,
            max_order_size_usd=self.cfg.max_order_usd,
        )
        db_path = f"databases/trade_log_{self.cfg.name}.sqlite"
        self._logger = TradeLogger(db_path=db_path)

        if self.cfg.mode == "futures_demo" and self.cfg.api_key:
            self._exchange = self._init_futures_exchange()
        elif self.cfg.mode == "spot_testnet" and self.cfg.api_key:
            self._exchange = self._init_spot_exchange()

        self._position_manager = PositionManager(
            exchange=self._exchange,
            paper_mode=(self.cfg.mode in ("paper", "shadow") or self.cfg.shadow_only),
        )
        self._position_manager.start()
        logger.info("[SubaccountUnit] %s initialisé (mode=%s, active=%s)",
                    self.cfg.label, self.cfg.mode, self.cfg.active)

    def _init_futures_exchange(self):
        try:
            import ccxt
            ex = ccxt.binanceusdm({
                "apiKey": self.cfg.api_key,
                "secret": self.cfg.api_secret,
                "enableRateLimit": True,
                "options": {"adjustForTimeDifference": True},
            })
            ex.enable_demo_trading(True)
            return ex
        except Exception as exc:
            logger.warning("[SubaccountUnit] %s init futures échoué: %s", self.cfg.name, exc)
            return None

    def _init_spot_exchange(self):
        try:
            import ccxt
            ex = ccxt.binance({
                "apiKey": self.cfg.api_key,
                "secret": self.cfg.api_secret,
                "enableRateLimit": True,
            })
            ex.set_sandbox_mode(True)
            return ex
        except Exception as exc:
            logger.warning("[SubaccountUnit] %s init spot échoué: %s", self.cfg.name, exc)
            return None

    def halt(self) -> None:
        self._halted = True
        logger.critical("[SubaccountUnit] %s HALTED", self.cfg.label)

    def resume(self) -> None:
        self._halted = False
        logger.info("[SubaccountUnit] %s repris", self.cfg.label)

    def is_active(self) -> bool:
        return self.cfg.active and not self._halted and not self.cfg.shadow_only

    def create_order(self, symbol: str, action: str, size_usd: float) -> dict:
        """Place un ordre avec vérification du SessionGuard."""
        if not self.is_active():
            return {"mode": "inactive", "subaccount": self.cfg.name,
                    "reason": "halted ou shadow_only"}

        from quant_hedge_ai.agents.risk.session_guard import (
            OrderTooLargeError, SessionHaltedError,
        )
        from quant_hedge_ai.agents.execution.position_manager import (
            Position,
        )

        try:
            self._guard.check_order(symbol, action, size_usd=size_usd)
        except (SessionHaltedError, OrderTooLargeError) as exc:
            reason = str(exc)
            logger.warning("[SubaccountUnit] %s order rejected: %s", self.cfg.name, reason)
            self._logger.log_rejected(symbol, action, size_usd, reason)
            self.halt()
            return {"mode": "rejected", "subaccount": self.cfg.name, "error": reason}

        if self.cfg.mode == "futures_demo" and self._exchange:
            result = self._place_futures(symbol, action, size_usd)
        else:
            result = {"symbol": symbol, "action": action,
                      "size": size_usd, "mode": "paper",
                      "subaccount": self.cfg.name}

        result["subaccount"] = self.cfg.name
        self._logger.log(result)

        # Enregistre la position dans le PositionManager
        if result.get("mode") in ("futures_demo", "paper") and result.get("id") or result.get("mode") == "paper":
            try:
                pos = Position(
                    symbol      = symbol,
                    side        = __import__(
                        "quant_hedge_ai.agents.execution.position_manager",
                        fromlist=["PositionSide"]
                    ).PositionSide.LONG if action.upper() == "BUY"
                    else __import__(
                        "quant_hedge_ai.agents.execution.position_manager",
                        fromlist=["PositionSide"]
                    ).PositionSide.SHORT,
                    entry_price = float(result.get("price") or result.get("average") or result.get("size_usd", size_usd) / max(1, size_usd) * size_usd or 1),
                    size_usd    = size_usd,
                    qty         = float(result.get("amount") or result.get("filled") or 0.001),
                    leverage    = self.cfg.leverage,
                    order_id    = str(result.get("id", f"{symbol}_{action}")),
                    subaccount  = self.cfg.name,
                    tp_pct      = self.cfg.tp_pct,
                    sl_pct      = self.cfg.sl_pct,
                    trailing_pct= self.cfg.trailing_pct,
                )
                self._position_manager.add_position(pos)
            except Exception as exc:
                logger.warning("[SubaccountUnit] add_position échoué: %s", exc)

        return result

    def _place_futures(self, symbol: str, action: str, size_usd: float) -> dict:
        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_sym = PositionManager._to_ccxt_symbol(symbol)
        try:
            if self.cfg.leverage != 1:
                try:
                    self._exchange.set_leverage(self.cfg.leverage, ccxt_sym)
                except Exception:
                    pass
            ticker = self._exchange.fetch_ticker(ccxt_sym)
            price  = float(ticker["last"])
            raw_qty = size_usd / price
            qty = round(max(0.001, raw_qty), 3)
            order = self._exchange.create_order(ccxt_sym, "market", side, qty)
            logger.info("[SubaccountUnit] %s FUTURES %s %s qty=%.4f @ $%.2f id=%s",
                        self.cfg.label, action, symbol, qty, price, order.get("id"))
            return {**order, "mode": "futures_demo", "usd_size": round(qty * price, 2)}
        except Exception as exc:
            logger.error("[SubaccountUnit] %s futures échoué: %s", self.cfg.name, exc)
            return {"symbol": symbol, "action": action, "size": size_usd,
                    "mode": "futures_failed", "error": str(exc)}

    def stats(self) -> dict:
        return {
            "name":     self.cfg.name,
            "label":    self.cfg.label,
            "active":   self.is_active(),
            "halted":   self._halted,
            "guard":    self._guard.state() if self._guard else {},
            "positions": self._position_manager.stats() if self._position_manager else {},
            "logger":   self._logger.stats() if self._logger else {},
        }

    @property
    def position_manager(self) -> "PositionManager":
        return self._position_manager


class SubaccountManager:
    """
    Gestionnaire global de tous les subcomptes.
    Point d'entrée unique pour passer des ordres, lire les stats, kill switch global.
    """

    def __init__(self, configs: Optional[dict[str, SubaccountConfig]] = None) -> None:
        cfgs = configs or PRESET_SUBACCOUNTS
        self._units: dict[str, SubaccountUnit] = {
            name: SubaccountUnit(cfg)
            for name, cfg in cfgs.items()
            if cfg.active
        }
        logger.info("[SubaccountManager] %d subcomptes initialisés: %s",
                    len(self._units), list(self._units.keys()))

    @classmethod
    def from_env(cls) -> "SubaccountManager":
        """Instancie avec les presets, overridable via .env."""
        return cls(PRESET_SUBACCOUNTS)

    def get(self, name: str) -> Optional[SubaccountUnit]:
        return self._units.get(name)

    def all_active(self) -> list[SubaccountUnit]:
        return [u for u in self._units.values() if u.is_active()]

    def halt_all(self) -> None:
        for u in self._units.values():
            u.halt()
        logger.critical("[SubaccountManager] TOUS les subcomptes HALTED")

    def resume_all(self) -> None:
        for u in self._units.values():
            u.resume()
        logger.info("[SubaccountManager] Tous les subcomptes repris")

    def halt_one(self, name: str) -> None:
        if name in self._units:
            self._units[name].halt()

    def route_signal(self, symbol: str, action: str, score: int) -> list[dict]:
        """
        Route un signal vers les subcomptes pertinents.
        Chaque subcompte actif qui couvre le symbole reçoit l'ordre.
        """
        results = []
        for unit in self.all_active():
            if symbol not in unit.cfg.symbols:
                continue
            size = unit.cfg.max_order_usd
            result = unit.create_order(symbol, action, size)
            results.append(result)
            logger.info("[SubaccountManager] Signal routé → %s: %s",
                        unit.cfg.label, result.get("mode"))
        return results

    def global_stats(self) -> dict:
        return {
            name: unit.stats()
            for name, unit in self._units.items()
        }

    def global_pnl(self) -> dict:
        total_open = 0.0
        total_closed = 0.0
        for unit in self._units.values():
            if unit._position_manager:
                s = unit._position_manager.stats()
                total_open   += s.get("open_pnl_usd", 0)
                total_closed += s.get("total_pnl_usd", 0)
        return {
            "open_pnl_usd":   round(total_open, 2),
            "closed_pnl_usd": round(total_closed, 2),
            "total_pnl_usd":  round(total_open + total_closed, 2),
        }

    def all_open_positions(self) -> list[dict]:
        positions = []
        for unit in self._units.values():
            if unit._position_manager:
                for snap in unit._position_manager.snapshot():
                    positions.append({**snap, "subaccount": unit.cfg.label})
        return positions
