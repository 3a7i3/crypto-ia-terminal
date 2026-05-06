"""
position_manager.py — Position Intelligence Layer (complet)

Suivi des positions ouvertes sur Futures Demo / Live avec :

  SORTIES INTELLIGENTES
  - TP dynamique adaptatif (ATR × multiplicateur)
  - SL adaptatif ATR / volatilité réalisée
  - Trailing stop intelligent (déclenché seulement après +break_even)
  - Break-even automatique
  - Partial take profit (ferme X% à Y% de profit)
  - Partial stop reduction (réduit le risque après partial TP)
  - Time stop (ferme si la position stagne > N minutes)
  - Position aging management (dégradation du TP si trade trop vieux)

  PROTECTION
  - Liquidation risk defense (fermeture d'urgence si dist < seuil)
  - Hedging detection (positions opposées)

Usage :
    pm = PositionManager(exchange_futures)
    pm.start()
    pm.add_position(pos)
    pm.update_market_data(symbol, atr, volatility)  # nourrit TP/SL adaptatifs
    pm.stop()
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PositionSide(str, Enum):
    LONG  = "long"
    SHORT = "short"


class CloseReason(str, Enum):
    TP               = "take_profit"
    SL               = "stop_loss"
    TRAILING         = "trailing_stop"
    PARTIAL          = "partial_close"
    BREAK_EVEN       = "break_even_triggered"
    TIME_STOP        = "time_stop"
    LIQUIDATION_DEF  = "liquidation_defense"
    MANUAL           = "manual"
    LIQUIDATION      = "liquidation_risk"


@dataclass
class Position:
    """Représente une position Futures ouverte."""

    symbol:        str
    side:          PositionSide
    entry_price:   float
    size_usd:      float            # notionnel USD à l'entrée
    qty:           float            # quantité base (ex: BTC)
    leverage:      int   = 1
    order_id:      str   = ""
    subaccount:    str   = "default"

    # Paramètres TP/SL de base
    tp_pct:        float = 0.04
    sl_pct:        float = 0.02
    trailing_pct:  float = 0.0      # 0 = désactivé

    # TP / SL adaptatifs ATR (prioritaires si atr > 0)
    atr:                    float = 0.0   # ATR injecté par update_market_data
    volatility:             float = 0.0   # vol réalisée [0-1]
    tp_atr_mult:            float = float(os.getenv("PM_TP_ATR_MULT", "2.5"))
    sl_atr_mult:            float = float(os.getenv("PM_SL_ATR_MULT", "1.5"))
    use_atr:                bool  = True

    # Partial take profit
    partial_close_pct:          float = float(os.getenv("PM_PARTIAL_PCT",     "0.5"))
    partial_close_trigger_pct:  float = float(os.getenv("PM_PARTIAL_TRIGGER", "0.02"))
    partial_done:               bool  = False

    # Break even
    break_even_trigger_pct: float = float(os.getenv("PM_BE_TRIGGER", "0.015"))
    break_even_done:         bool  = False

    # Time stop
    max_age_minutes: float = float(os.getenv("PM_MAX_AGE_MIN", "240"))  # 4h max par défaut
    time_stop_enabled: bool = True

    # Position aging — TP se resserre avec le temps si pas en profit
    aging_tp_decay:  bool  = bool(int(os.getenv("PM_AGING_DECAY", "1")))
    aging_start_min: float = float(os.getenv("PM_AGING_START",   "60"))  # commence à dégrader après 1h

    # Liquidation defense — fermeture urgence avant liquidation
    liq_defense_pct: float = float(os.getenv("PM_LIQ_DEFENSE_PCT", "0.08"))  # ferme si dist < 8%

    # Contexte décision (pour MistakeMemory)
    signal_score:       int   = 70
    conviction_level:   str   = "medium"
    signal_age_sec:     float = 0.0

    # État interne
    highest_price:  float = 0.0
    lowest_price:   float = 0.0
    sl_price:       float = 0.0
    tp_price:       float = 0.0
    tp_price_init:  float = 0.0     # TP original (avant aging)
    current_price:  float = 0.0
    pnl_usd:        float = 0.0
    pnl_pct:        float = 0.0
    opened_at:      float = field(default_factory=time.time)
    closed:         bool  = False
    close_reason:   str   = ""
    regime:         str   = "unknown"   # régime au moment de l'entrée

    def __post_init__(self) -> None:
        self._recalc_tp_sl()
        self.tp_price_init  = self.tp_price
        self.highest_price  = self.entry_price
        self.lowest_price   = self.entry_price

    def _recalc_tp_sl(self) -> None:
        """Recalcule TP/SL — ATR prioritaire si disponible, sinon % fixe."""
        if self.use_atr and self.atr > 0:
            tp_dist = self.atr * self.tp_atr_mult
            sl_dist = self.atr * self.sl_atr_mult
        else:
            tp_dist = self.entry_price * self.tp_pct
            sl_dist = self.entry_price * self.sl_pct
        if self.tp_price == 0.0:
            if self.side == PositionSide.LONG:
                self.tp_price = self.entry_price + tp_dist
                self.sl_price = self.entry_price - sl_dist
            else:
                self.tp_price = self.entry_price - tp_dist
                self.sl_price = self.entry_price + sl_dist

    def age_minutes(self) -> float:
        return (time.time() - self.opened_at) / 60

    def update_price(self, price: float) -> None:
        self.current_price = price
        if self.side == PositionSide.LONG:
            self.pnl_pct = (price - self.entry_price) / self.entry_price
        else:
            self.pnl_pct = (self.entry_price - price) / self.entry_price
        self.pnl_usd = self.pnl_pct * self.size_usd * self.leverage
        self.highest_price = max(self.highest_price, price)
        self.lowest_price  = min(self.lowest_price,  price)

    def update_market_data(self, atr: float, volatility: float = 0.0) -> None:
        """
        Met à jour les données de marché et recalcule TP/SL adaptatifs.
        Appelé à chaque tick par le PositionManager depuis les features.
        """
        if atr <= 0:
            return
        old_atr = self.atr
        self.atr        = atr
        self.volatility = volatility

        # Recalcule seulement si ATR a changé de plus de 5% (évite oscillation)
        if old_atr <= 0 or abs(atr - old_atr) / old_atr > 0.05:
            sl_dist = atr * self.sl_atr_mult
            tp_dist = atr * self.tp_atr_mult
            if self.side == PositionSide.LONG:
                new_sl = self.entry_price - sl_dist
                new_tp = self.entry_price + tp_dist
                # SL ne peut que monter (protège les gains)
                if not self.break_even_done:
                    self.sl_price = max(self.sl_price, new_sl) if self.sl_price > 0 else new_sl
                self.tp_price = max(self.tp_price, new_tp) if self.tp_price_init > 0 else new_tp
            else:
                new_sl = self.entry_price + sl_dist
                new_tp = self.entry_price - tp_dist
                if not self.break_even_done:
                    self.sl_price = min(self.sl_price, new_sl) if self.sl_price > 0 else new_sl
                self.tp_price = min(self.tp_price, new_tp) if self.tp_price_init > 0 else new_tp

    def liquidation_price(self) -> float:
        """Estimation prix de liquidation (simplifié, 1/leverage marge)."""
        if self.leverage <= 1:
            return 0.0
        margin_rate = 1.0 / self.leverage
        if self.side == PositionSide.LONG:
            return self.entry_price * (1 - margin_rate + 0.005)
        else:
            return self.entry_price * (1 + margin_rate - 0.005)

    def liquidation_distance_pct(self) -> float:
        liq = self.liquidation_price()
        if liq <= 0 or self.current_price <= 0:
            return 1.0
        if self.side == PositionSide.LONG:
            return (self.current_price - liq) / self.current_price
        else:
            return (liq - self.current_price) / self.current_price

    def summary(self) -> str:
        sign = "+" if self.pnl_usd >= 0 else ""
        return (
            f"{self.side.value.upper()} {self.symbol} "
            f"entry=${self.entry_price:.2f} now=${self.current_price:.2f} "
            f"PnL={sign}{self.pnl_usd:.2f}$ ({sign}{self.pnl_pct:.2%}) "
            f"SL=${self.sl_price:.2f} TP=${self.tp_price:.2f}"
        )


class PositionManager:
    """
    Surveille les positions ouvertes et déclenche TP/SL/trailing automatiquement.

    Fonctionne en mode exchange réel (Futures Demo) ou simulation (paper).
    """

    def __init__(
        self,
        exchange=None,
        check_interval_s: float = float(os.getenv("PM_CHECK_INTERVAL", "10")),
        paper_mode: bool = False,
    ) -> None:
        self._exchange       = exchange
        self._interval       = check_interval_s
        self._paper          = paper_mode or (exchange is None)
        self._positions:     dict[str, Position] = {}   # order_id → Position
        self._closed:        list[Position]       = []
        self._lock           = threading.Lock()
        self._running        = False
        self._thread:        threading.Thread | None = None
        self._callbacks:     list = []            # fn(pos, reason) appelée à chaque close

    # ── Cycle de vie ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(
            target=self._watch_loop, daemon=True, name="PositionManager"
        )
        self._thread.start()
        logger.info("[PositionManager] Démarré (paper=%s, interval=%ds)",
                    self._paper, self._interval)

    def stop(self) -> None:
        self._running = False
        logger.info("[PositionManager] Arrêté")

    def on_close(self, fn) -> None:
        """Enregistre un callback appelé à chaque fermeture de position."""
        self._callbacks.append(fn)

    # ── API publique ───────────────────────────────────────────────────────────

    def add_position(self, pos: Position) -> None:
        key = pos.order_id or f"{pos.symbol}_{pos.opened_at}"
        with self._lock:
            self._positions[key] = pos
        logger.info("[PositionManager] Position ajoutée: %s", pos.summary())

    def get_open(self) -> list[Position]:
        with self._lock:
            return [p for p in self._positions.values() if not p.closed]

    def get_closed(self, n: int = 50) -> list[Position]:
        return self._closed[-n:]

    def stats(self) -> dict:
        open_pos  = self.get_open()
        closed    = self._closed
        total_pnl = sum(p.pnl_usd for p in closed)
        wins      = [p for p in closed if p.pnl_usd > 0]
        return {
            "open_count":    len(open_pos),
            "closed_count":  len(closed),
            "total_pnl_usd": round(total_pnl, 2),
            "win_rate":      round(len(wins) / len(closed), 3) if closed else 0.0,
            "open_pnl_usd":  round(sum(p.pnl_usd for p in open_pos), 2),
        }

    def snapshot(self) -> list[dict]:
        """Retourne un snapshot JSON-serializable des positions ouvertes."""
        return [
            {
                "symbol":       p.symbol,
                "side":         p.side.value,
                "entry":        p.entry_price,
                "current":      p.current_price,
                "pnl_usd":      round(p.pnl_usd, 2),
                "pnl_pct":      round(p.pnl_pct * 100, 2),
                "sl":           round(p.sl_price, 4),
                "tp":           round(p.tp_price, 4),
                "liq_dist_pct": round(p.liquidation_distance_pct() * 100, 2),
                "leverage":     p.leverage,
                "size_usd":     p.size_usd,
                "subaccount":   p.subaccount,
                "regime":       p.regime,
                "age_min":      round(p.age_minutes(), 1),
                "atr":          round(p.atr, 4),
                "volatility":   round(p.volatility, 4),
                "time_stop_in": round(max(0, p.max_age_minutes - p.age_minutes()), 1),
                "break_even":   p.break_even_done,
                "partial_done": p.partial_done,
            }
            for p in self.get_open()
        ]

    def update_market_data(self, symbol: str, atr: float, volatility: float = 0.0) -> None:
        """Propage les données de marché à toutes les positions ouvertes sur ce symbole."""
        with self._lock:
            for pos in self._positions.values():
                if pos.symbol == symbol and not pos.closed:
                    pos.update_market_data(atr, volatility)

    def update_price_and_check(self, symbol: str, price: float) -> None:
        """
        Alimente le prix courant et déclenche TP/SL/trailing pour toutes les
        positions ouvertes sur ce symbole. Appelé depuis advisor_loop après
        chaque cycle d'analyse pour que les checks fonctionnent même en
        paper_mode (où _fetch_price() retourne None).
        """
        if price <= 0:
            return
        with self._lock:
            positions = [
                p for p in self._positions.values()
                if p.symbol == symbol and not p.closed
            ]
        for pos in positions:
            pos.update_price(price)
            self._check_liquidation_defense(pos)
            if pos.closed:
                continue
            self._check_time_stop(pos)
            if pos.closed:
                continue
            self._check_aging_tp(pos)
            self._check_break_even(pos)
            self._check_partial_close(pos)
            self._check_trailing(pos)
            self._check_tp_sl(pos)

    # ── Boucle de surveillance ──────────────────────────────────────────────────

    def _watch_loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("[PositionManager] Erreur tick: %s", exc)
            time.sleep(self._interval)

    def _tick(self) -> None:
        with self._lock:
            positions = list(self._positions.values())

        for pos in positions:
            if pos.closed:
                continue
            price = self._fetch_price(pos.symbol)
            if price is None or price <= 0:
                continue
            pos.update_price(price)
            # Ordre des vérifications : sécurité d'abord, puis gestion des gains
            self._check_liquidation_defense(pos)
            if pos.closed:
                continue
            self._check_time_stop(pos)
            if pos.closed:
                continue
            self._check_aging_tp(pos)
            self._check_break_even(pos)
            self._check_partial_close(pos)
            self._check_trailing(pos)
            self._check_tp_sl(pos)

    def _fetch_price(self, symbol: str) -> Optional[float]:
        if self._paper or self._exchange is None:
            return None
        try:
            ccxt_symbol = self._to_ccxt_symbol(symbol)
            ticker = self._exchange.fetch_ticker(ccxt_symbol)
            return float(ticker["last"])
        except Exception as exc:
            logger.warning("[PositionManager] fetch_price %s: %s", symbol, exc)
            return None

    # ── Logique TP/SL/Trailing ─────────────────────────────────────────────────

    def _check_tp_sl(self, pos: Position) -> None:
        p = pos.current_price
        if p <= 0:
            return
        if pos.side == PositionSide.LONG:
            if p >= pos.tp_price:
                self._close_position(pos, CloseReason.TP)
            elif p <= pos.sl_price:
                self._close_position(pos, CloseReason.SL)
        else:
            if p <= pos.tp_price:
                self._close_position(pos, CloseReason.TP)
            elif p >= pos.sl_price:
                self._close_position(pos, CloseReason.SL)

    def _check_trailing(self, pos: Position) -> None:
        if pos.trailing_pct <= 0 or pos.closed:
            return
        p = pos.current_price
        if pos.side == PositionSide.LONG:
            new_sl = pos.highest_price * (1 - pos.trailing_pct)
            if new_sl > pos.sl_price:
                logger.debug("[PositionManager] Trailing SL LONG %s: %.2f → %.2f",
                             pos.symbol, pos.sl_price, new_sl)
                pos.sl_price = new_sl
            if p <= pos.sl_price:
                self._close_position(pos, CloseReason.TRAILING)
        else:
            new_sl = pos.lowest_price * (1 + pos.trailing_pct)
            if new_sl < pos.sl_price:
                logger.debug("[PositionManager] Trailing SL SHORT %s: %.2f → %.2f",
                             pos.symbol, pos.sl_price, new_sl)
                pos.sl_price = new_sl
            if p >= pos.sl_price:
                self._close_position(pos, CloseReason.TRAILING)

    def _check_partial_close(self, pos: Position) -> None:
        if pos.partial_close_pct <= 0 or pos.partial_done or pos.closed:
            return
        if pos.pnl_pct >= pos.partial_close_trigger_pct:
            close_qty = pos.qty * pos.partial_close_pct
            logger.info("[PositionManager] Partial close %s: %.4f (%.0f%%) PnL=%.2f$",
                        pos.symbol, close_qty, pos.partial_close_pct * 100, pos.pnl_usd)
            self._send_close_order(pos, qty_override=close_qty, reason=CloseReason.PARTIAL)
            pos.qty      -= close_qty
            pos.size_usd  = pos.qty * pos.current_price
            pos.partial_done = True
            # Partial stop reduction — déplace le SL à l'entrée après le partial TP
            if not pos.break_even_done:
                pos.sl_price = pos.entry_price * (1.001 if pos.side == PositionSide.LONG else 0.999)
                pos.break_even_done = True
                logger.info("[PositionManager] Partial stop reduction %s: SL → entry %.2f",
                            pos.symbol, pos.entry_price)

    def _check_break_even(self, pos: Position) -> None:
        if pos.break_even_done or pos.closed:
            return
        if pos.pnl_pct >= pos.break_even_trigger_pct:
            logger.info("[PositionManager] Break even %s: SL déplacé à entry %.2f",
                        pos.symbol, pos.entry_price)
            pos.sl_price     = pos.entry_price * (1.0005 if pos.side == PositionSide.LONG else 0.9995)
            pos.break_even_done = True

    def _check_liquidation_defense(self, pos: Position) -> None:
        """Ferme la position d'urgence si on approche de la liquidation."""
        dist = pos.liquidation_distance_pct()
        # Alerte Telegram si dist < 15%
        if 0.08 < dist < 0.15:
            logger.warning(
                "[PositionManager] ALERTE LIQUIDATION %s — dist=%.1f%%",
                pos.symbol, dist * 100,
            )
            try:
                from supervision.notifications.telegram_notifier import TelegramNotifier
                TelegramNotifier().send(
                    f"ALERTE LIQUIDATION {pos.symbol}\n"
                    f"Prix: ${pos.current_price:.2f} | Distance: {dist*100:.1f}%\n"
                    f"PnL: {pos.pnl_usd:+.2f}$"
                )
            except Exception:
                pass
        # Fermeture d'urgence si dist < seuil defense
        if dist < pos.liq_defense_pct:
            logger.critical(
                "[PositionManager] LIQUIDATION DEFENSE %s — fermeture urgence dist=%.1f%%",
                pos.symbol, dist * 100,
            )
            self._close_position(pos, CloseReason.LIQUIDATION_DEF)

    def _check_time_stop(self, pos: Position) -> None:
        """Ferme la position si elle dépasse l'âge maximum sans atteindre le TP."""
        if not pos.time_stop_enabled:
            return
        age = pos.age_minutes()
        if age >= pos.max_age_minutes:
            logger.info(
                "[PositionManager] TIME STOP %s — âge %.0fmin ≥ max %.0fmin | PnL=%.2f$",
                pos.symbol, age, pos.max_age_minutes, pos.pnl_usd,
            )
            self._close_position(pos, CloseReason.TIME_STOP)

    def _check_aging_tp(self, pos: Position) -> None:
        """
        Position aging — resserre le TP avec le temps si la position n'est pas en profit.
        Évite de garder indéfiniment une position qui stagne.
        """
        if not pos.aging_tp_decay or pos.pnl_pct >= 0.01:
            return   # ne dégrade pas si en profit
        age = pos.age_minutes()
        if age < pos.aging_start_min:
            return
        # Decay linéaire : TP se resserre de 10% par heure après aging_start_min
        elapsed_hours = (age - pos.aging_start_min) / 60
        decay = min(0.5, elapsed_hours * 0.10)   # max 50% de réduction
        if pos.side == PositionSide.LONG:
            new_tp = pos.tp_price_init * (1 - decay)
            if new_tp < pos.tp_price:
                pos.tp_price = max(pos.entry_price * 1.005, new_tp)
        else:
            new_tp = pos.tp_price_init * (1 + decay)
            if new_tp > pos.tp_price:
                pos.tp_price = min(pos.entry_price * 0.995, new_tp)

    # ── Fermeture et ordres ────────────────────────────────────────────────────

    def _close_position(self, pos: Position, reason: CloseReason) -> None:
        if pos.closed:
            return
        logger.info("[PositionManager] Fermeture %s — raison=%s PnL=%.2f$ (%.2f%%)",
                    pos.symbol, reason.value, pos.pnl_usd, pos.pnl_pct * 100)
        self._send_close_order(pos, reason=reason)
        pos.closed      = True
        pos.close_reason = reason.value
        with self._lock:
            self._closed.append(pos)
        for fn in self._callbacks:
            try:
                fn(pos, reason)
            except Exception:
                pass

    def _send_close_order(
        self,
        pos: Position,
        qty_override: Optional[float] = None,
        reason: CloseReason = CloseReason.MANUAL,
    ) -> None:
        qty  = qty_override or pos.qty
        side = "sell" if pos.side == PositionSide.LONG else "buy"
        if self._paper or self._exchange is None:
            logger.info("[PositionManager][PAPER] close %s %s qty=%.4f reason=%s",
                        side, pos.symbol, qty, reason.value)
            return
        try:
            ccxt_symbol = self._to_ccxt_symbol(pos.symbol)
            order = self._exchange.create_order(ccxt_symbol, "market", side, qty,
                                                params={"reduceOnly": True})
            logger.info("[PositionManager] Ordre close envoyé id=%s", order.get("id"))
        except Exception as exc:
            logger.error("[PositionManager] Echec close order %s: %s", pos.symbol, exc)

    @staticmethod
    def _to_ccxt_symbol(symbol: str) -> str:
        if ":" in symbol:
            return symbol
        if "/" in symbol:
            quote = symbol.split("/")[1]
            return f"{symbol}:{quote}"
        return f"{symbol[:3]}/USDT:USDT"

    # ── Hedging detection ──────────────────────────────────────────────────────

    def detect_hedges(self) -> list[tuple[Position, Position]]:
        """Retourne les paires long/short sur le même symbole."""
        open_pos = self.get_open()
        by_symbol: dict[str, list[Position]] = {}
        for p in open_pos:
            by_symbol.setdefault(p.symbol, []).append(p)
        hedges = []
        for sym, positions in by_symbol.items():
            longs  = [p for p in positions if p.side == PositionSide.LONG]
            shorts = [p for p in positions if p.side == PositionSide.SHORT]
            for l in longs:
                for s in shorts:
                    hedges.append((l, s))
                    logger.warning("[PositionManager] Hedge détecté: %s LONG + SHORT", sym)
        return hedges

    # ── Injection depuis ExecutionEngine ──────────────────────────────────────

    @classmethod
    def from_futures_order(
        cls,
        order:    dict,
        symbol:   str,
        action:   str,
        size_usd: float,
        leverage: int   = 1,
        tp_pct:   float = float(os.getenv("PM_TP_PCT",       "0.04")),
        sl_pct:   float = float(os.getenv("PM_SL_PCT",       "0.02")),
        trailing: float = float(os.getenv("PM_TRAILING_PCT", "0.015")),
        atr:      float = 0.0,
        volatility: float = 0.0,
        regime:   str   = "unknown",
    ) -> "Position":
        """Crée une Position à partir d'un résultat create_futures_order()."""
        price = float(
            order.get("price") or order.get("average")
            or (order.get("info") or {}).get("avgPrice") or 0
        )
        qty  = float(order.get("amount") or order.get("filled") or 0)
        side = PositionSide.LONG if action.upper() == "BUY" else PositionSide.SHORT
        return Position(
            symbol        = symbol,
            side          = side,
            entry_price   = price,
            size_usd      = size_usd,
            qty           = qty,
            leverage      = leverage,
            order_id      = str(order.get("id", "")),
            tp_pct        = tp_pct,
            sl_pct        = sl_pct,
            trailing_pct  = trailing,
            atr           = atr,
            volatility    = volatility,
            regime        = regime,
        )
