"""
paper_trading/mexc_simulator.py — Simulateur trading MEXC complet.

Miroir du compte MEXC réel :
  - Solde initial = solde MEXC réel lu via API (spot + futures USDT)
  - Ordres MARKET / LIMIT / STOP_LIMIT avec slippage et fees MEXC
  - Surveillance TP/SL toutes les 60s sur données MEXC réelles
  - Notifications Telegram formatées comme un vrai compte MEXC
  - Tracker 7 jours : PnL%, Sharpe, Max Drawdown, Win Rate

Variables d'env :
    MEXC_SIM_CAPITAL  : capital de départ forcé (défaut: lu depuis API)
    MEXC_SIM_FEE      : fee taker (défaut: 0.001 = 0.10%)
    MEXC_SIM_SLIP     : slippage simulé (défaut: 0.0005 = 0.05%)
"""

from __future__ import annotations

import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

try:
    from observability.json_logger import get_logger

    _log = get_logger("paper_trading.mexc_simulator")
except Exception:
    import logging

    _log = logging.getLogger("paper_trading.mexc_simulator")

# ── Constantes MEXC ───────────────────────────────────────────────────────────

_TAKER_FEE = float(os.getenv("MEXC_SIM_FEE", "0.001"))
_SLIPPAGE = float(os.getenv("MEXC_SIM_SLIP", "0.0005"))
_MONITOR_INTERVAL = 60  # secondes
_POSITION_SIZE_PCT = 0.15  # 15% du capital disponible par position
_MAX_POSITION_USD = 25.0  # plafond par position


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# ── Structures ────────────────────────────────────────────────────────────────


@dataclass
class MexcOrder:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty_usd: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float = 0.0
    fill_ts: float = 0.0
    created_ts: float = field(default_factory=time.time)
    tp_pct: float = 0.04
    sl_pct: float = 0.02
    score: int = 0
    personality: str = "unknown"
    regime: str = "unknown"


@dataclass
class MexcPosition:
    pos_id: str
    symbol: str
    side: OrderSide
    qty_usd: float
    entry_price: float
    tp_price: float
    sl_price: float
    fee_entry_usd: float
    score: int
    personality: str
    regime: str = "unknown"
    opened_ts: float = field(default_factory=time.time)
    exit_price: float = 0.0
    closed_ts: float = 0.0
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    close_reason: str = ""
    mae_pct: float = 0.0
    mfe_pct: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.closed_ts == 0.0

    def live_pnl_pct(self, price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == OrderSide.BUY:
            return (price - self.entry_price) / self.entry_price * 100.0
        return (self.entry_price - price) / self.entry_price * 100.0

    def hits_tp(self, price: float) -> bool:
        return (
            price >= self.tp_price
            if self.side == OrderSide.BUY
            else price <= self.tp_price
        )

    def hits_sl(self, price: float) -> bool:
        return (
            price <= self.sl_price
            if self.side == OrderSide.BUY
            else price >= self.sl_price
        )


# ── Tracker de performance ────────────────────────────────────────────────────


class PerformanceTracker:
    """Calcule PnL, Sharpe, Drawdown, Win Rate sur fenêtre glissante."""

    def __init__(self) -> None:
        self._daily_returns: list[float] = []
        self._equity_curve: list[float] = []
        self._peak: float = 0.0
        self._start_ts: float = time.time()

    def record_equity(self, equity: float) -> None:
        if self._equity_curve:
            prev = self._equity_curve[-1]
            if prev > 0:
                ret = (equity - prev) / prev
                self._daily_returns.append(ret)
        self._equity_curve.append(equity)
        self._peak = max(self._peak, equity)

    def pnl_pct(self, initial: float) -> float:
        if not self._equity_curve or initial == 0:
            return 0.0
        return (self._equity_curve[-1] - initial) / initial * 100.0

    def max_drawdown_pct(self) -> float:
        peak = 0.0
        max_dd = 0.0
        for eq in self._equity_curve:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (peak - eq) / peak * 100.0
                max_dd = max(max_dd, dd)
        return max_dd

    def sharpe(self, risk_free: float = 0.0) -> float:
        if len(self._daily_returns) < 2:
            return 0.0
        n = len(self._daily_returns)
        mean = sum(self._daily_returns) / n
        variance = sum((r - mean) ** 2 for r in self._daily_returns) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std == 0:
            return 0.0
        return (mean - risk_free) / std * math.sqrt(252)

    def days_running(self) -> float:
        return (time.time() - self._start_ts) / 86400.0


# ── Simulateur principal ──────────────────────────────────────────────────────


class MexcSimulator:
    """
    Simulateur de trading MEXC avec solde réel mirrored.

    Lit le solde MEXC réel au démarrage. Simule MARKET/LIMIT/STOP_LIMIT
    avec slippage et fees MEXC. Envoie tout sur Telegram.
    """

    def __init__(
        self,
        mexc_reader=None,
        telegram_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._mexc = mexc_reader
        self._telegram = telegram_fn
        self._capital: float = 0.0
        self._initial_capital: float = 0.0
        self._positions: dict[str, MexcPosition] = {}
        self._orders: dict[str, MexcOrder] = {}
        self._closed: list[MexcPosition] = []
        self._lock = threading.Lock()
        self._running = False
        self._perf = PerformanceTracker()

    # ── Démarrage ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        capital = self._read_mexc_balance()
        forced = os.getenv("MEXC_SIM_CAPITAL", "")
        if forced:
            capital = float(forced)
            _log.info("[SIM] Capital forcé via env: $%.2f", capital)

        if capital <= 0:
            _log.warning("[SIM] Solde MEXC non lisible — utilise $10 par défaut")
            capital = 10.0

        self._capital = capital
        self._initial_capital = capital
        self._perf.record_equity(capital)

        restored = self._restore_positions()

        self._running = True
        t = threading.Thread(target=self._monitor_loop, daemon=True, name="MEXC-SIM")
        t.start()

        _log.info(
            "[SIM] Démarré — capital=$%.2f (positions restaurées: %d)",
            capital,
            restored,
        )
        self._notify(
            f"MEXC SIM — Compte actif\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Capital   : ${capital:.2f} USDT\n"
            f"Source    : Solde reel MEXC\n"
            f"Ordres    : MARKET | LIMIT | STOP_LIMIT\n"
            f"Donnees   : MEXC temps reel\n"
            f"Mode      : SIMULATION — aucun ordre reel\n"
            f"Objectif  : 7 jours validation burn-in"
        )

    def _read_mexc_balance(self) -> float:
        if self._mexc is None:
            return 0.0
        try:
            sb = self._mexc.spot.fetch_balance()
            fb = self._mexc.futures.fetch_balance()
            spot = float((sb.get("free") or {}).get("USDT") or 0)
            fut = float((fb.get("free") or {}).get("USDT") or 0)
            total = spot + fut
            _log.info(
                "[SIM] Solde MEXC: spot=$%.2f futures=$%.2f total=$%.2f",
                spot,
                fut,
                total,
            )
            return total
        except Exception as exc:
            _log.warning("[SIM] Lecture solde MEXC echouee: %s", exc)
            return 0.0

    def stop(self) -> None:
        self._running = False

    def _restore_positions(self) -> int:
        """Restaure les positions OPEN sans CLOSE depuis paper_trades.jsonl."""
        try:
            from paper_trading.recorder import get_recorder

            trades = get_recorder().trades()
        except Exception as exc:
            _log.warning("[SIM] Restore impossible — recorder: %s", exc)
            return 0

        restored = 0
        for trade in trades:
            if not trade.is_open:
                continue
            if trade.symbol in self._positions:
                continue
            if trade.entry_price <= 0:
                _log.warning(
                    "[SIM] Restore skipped %s — entry_price invalide",
                    trade.symbol,
                )
                continue
            if self._capital < trade.size_usd * 1.01:
                _log.warning(
                    "[SIM] Restore skipped %s — capital insuffisant "
                    "(dispo=$%.2f requis=$%.2f)",
                    trade.symbol,
                    self._capital,
                    trade.size_usd,
                )
                continue

            side = (
                OrderSide.BUY
                if trade.side.upper() in ("BUY", "LONG")
                else OrderSide.SELL
            )
            entry = trade.entry_price
            tp_pct, sl_pct = 0.04, 0.02
            if side == OrderSide.BUY:
                tp = entry * (1 + tp_pct)
                sl = entry * (1 - sl_pct)
            else:
                tp = entry * (1 - tp_pct)
                sl = entry * (1 + sl_pct)

            pos = MexcPosition(
                pos_id=trade.trade_id,
                symbol=trade.symbol,
                side=side,
                qty_usd=trade.size_usd,
                entry_price=entry,
                tp_price=tp,
                sl_price=sl,
                fee_entry_usd=0.0,
                score=trade.score,
                personality="restored",
                opened_ts=trade.opened_at or time.time(),
            )
            self._positions[trade.symbol] = pos
            self._capital -= trade.size_usd
            restored += 1
            _log.info(
                "[SIM] RESTORE %s %s entry=%.5f size=$%.2f TP=%.5f SL=%.5f",
                side.value,
                trade.symbol,
                entry,
                trade.size_usd,
                tp,
                sl,
            )

        return restored

    # ── Passage d'ordres ──────────────────────────────────────────────────────

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty_usd: float,
        tp_pct: float = 0.04,
        sl_pct: float = 0.02,
        score: int = 0,
        personality: str = "unknown",
        current_price: float = 0.0,
        regime: str = "unknown",
    ) -> Optional[MexcOrder]:
        """Ordre MARKET : exécution immédiate au prix courant + slippage."""
        order = MexcOrder(
            order_id=str(uuid.uuid4())[:10].upper(),
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType.MARKET,
            qty_usd=qty_usd,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            score=score,
            personality=personality,
            regime=regime,
        )
        if current_price <= 0:
            current_price = self._fetch_price(symbol)
        if current_price <= 0:
            order.status = OrderStatus.REJECTED
            self._notify(f"[SIM] ORDRE REJETE — {symbol}: prix indisponible")
            return order

        return self._fill_market(order, current_price)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty_usd: float,
        limit_price: float,
        tp_pct: float = 0.04,
        sl_pct: float = 0.02,
        score: int = 0,
        personality: str = "unknown",
    ) -> MexcOrder:
        """Ordre LIMIT : en attente jusqu'à ce que le prix atteigne limit_price."""
        order = MexcOrder(
            order_id=str(uuid.uuid4())[:10].upper(),
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType.LIMIT,
            qty_usd=qty_usd,
            limit_price=limit_price,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            score=score,
            personality=personality,
        )
        with self._lock:
            self._orders[order.order_id] = order
        self._notify(
            f"[SIM] ORDRE LIMIT {side.upper()} — {symbol}\n"
            f"  Prix limite : ${limit_price:.4f}\n"
            f"  Taille      : ${qty_usd:.2f} USDT\n"
            f"  TP/SL       : +{tp_pct:.1%} / -{sl_pct:.1%}\n"
            f"  Statut      : EN ATTENTE (ID:{order.order_id})"
        )
        return order

    def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        qty_usd: float,
        stop_price: float,
        limit_price: float,
        tp_pct: float = 0.04,
        sl_pct: float = 0.02,
        score: int = 0,
        personality: str = "unknown",
    ) -> MexcOrder:
        """Ordre STOP_LIMIT : déclenché sur stop_price, exécuté à limit_price."""
        order = MexcOrder(
            order_id=str(uuid.uuid4())[:10].upper(),
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType.STOP_LIMIT,
            qty_usd=qty_usd,
            stop_price=stop_price,
            limit_price=limit_price,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            score=score,
            personality=personality,
        )
        with self._lock:
            self._orders[order.order_id] = order
        self._notify(
            f"[SIM] ORDRE STOP_LIMIT {side.upper()} — {symbol}\n"
            f"  Declencheur : ${stop_price:.4f}\n"
            f"  Prix limite : ${limit_price:.4f}\n"
            f"  Taille      : ${qty_usd:.2f} USDT\n"
            f"  Statut      : EN ATTENTE (ID:{order.order_id})"
        )
        return order

    # ── Exécution interne ─────────────────────────────────────────────────────

    def _fill_market(self, order: MexcOrder, price: float) -> MexcOrder:
        with self._lock:
            if order.symbol in self._positions:
                order.status = OrderStatus.REJECTED
                self._notify(f"[SIM] REJETE — position deja ouverte sur {order.symbol}")
                return order

            size = min(
                order.qty_usd or (self._capital * _POSITION_SIZE_PCT),
                _MAX_POSITION_USD,
            )
            if size < 1.0 or self._capital < size * 1.01:
                order.status = OrderStatus.REJECTED
                self._notify(
                    f"[SIM] REJETE — capital insuffisant "
                    f"(dispo=${self._capital:.2f}, requis=${size:.2f})"
                )
                return order

            slip = price * _SLIPPAGE
            fill = price + slip if order.side == OrderSide.BUY else price - slip
            fee = size * _TAKER_FEE
            self._capital -= size + fee

            if order.side == OrderSide.BUY:
                tp = fill * (1 + order.tp_pct)
                sl = fill * (1 - order.sl_pct)
            else:
                tp = fill * (1 - order.tp_pct)
                sl = fill * (1 + order.sl_pct)

            pos = MexcPosition(
                pos_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                qty_usd=size,
                entry_price=fill,
                tp_price=tp,
                sl_price=sl,
                fee_entry_usd=fee,
                score=order.score,
                personality=order.personality,
                regime=order.regime,
            )
            self._positions[order.symbol] = pos
            order.fill_price = fill
            order.fill_ts = time.time()
            order.status = OrderStatus.FILLED

        try:
            from paper_trading.recorder import get_recorder

            get_recorder().record_open(
                trade_id=pos.pos_id,
                symbol=pos.symbol,
                side=pos.side.value.lower(),
                price=pos.entry_price,
                size_usd=pos.qty_usd,
                score=pos.score,
                regime=pos.regime,
                mode="futures_demo",
            )
        except Exception as exc:
            _log.warning("[SIM] record_open échoué: %s", exc)

        wins = sum(1 for p in self._closed if p.pnl_usd >= 0)
        total = len(self._closed)
        wr = f"{wins/total*100:.0f}%" if total else "—"
        arrow = "BUY" if order.side == OrderSide.BUY else "SELL"
        self._notify(
            f"MEXC SIM — ORDRE {arrow}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Symbole  : {order.symbol}\n"
            f"Prix     : ${fill:.4g}\n"
            f"Taille   : ${size:.2f} USDT\n"
            f"TP       : ${tp:.4g}  (+{order.tp_pct:.1%})\n"
            f"SL       : ${sl:.4g}  (-{order.sl_pct:.1%})\n"
            f"Score    : {order.score}/100 | {order.personality}\n"
            f"Fee      : ${fee:.3f}\n"
            f"Capital  : ${self._capital:.2f} USDT\n"
            f"WR       : {wr}  ({total} trades fermes)"
        )
        _log.info(
            "[SIM] FILL %s %s fill=%.5f size=$%.2f TP=%.5f SL=%.5f",
            order.side.value,
            order.symbol,
            fill,
            size,
            tp,
            sl,
        )
        return order

    # ── Surveillance TP/SL + ordres LIMIT ────────────────────────────────────

    def _monitor_loop(self) -> None:
        tick = 0
        while self._running:
            try:
                self._check_positions()
                self._check_pending_orders()
                tick += 1
                if tick % 60 == 0:  # rapport toutes les heures (60 × 60s)
                    self._send_report()
                self._perf.record_equity(self._total_equity())
            except Exception as exc:
                _log.error("[SIM] Erreur surveillance: %s", exc)
            time.sleep(_MONITOR_INTERVAL)

    def _total_equity(self) -> float:
        """Capital libre + valeur mark-to-market des positions ouvertes."""
        with self._lock:
            open_pos = dict(self._positions)
        equity = self._capital
        for sym, p in open_pos.items():
            price = self._fetch_price(sym)
            if price > 0:
                live_pct = p.live_pnl_pct(price) / 100.0
                equity += p.qty_usd * (1.0 + live_pct)
            else:
                equity += p.qty_usd  # valeur d'entrée si prix indisponible
        return equity

    def _fetch_price(self, symbol: str) -> float:
        if self._mexc is None:
            return 0.0
        try:
            t = self._mexc.spot.fetch_ticker(symbol)
            return float(t.get("last") or t.get("close") or 0)
        except Exception:
            return 0.0

    def _check_positions(self) -> None:
        with self._lock:
            syms = list(self._positions.keys())
        for sym in syms:
            price = self._fetch_price(sym)
            if price == 0:
                continue
            with self._lock:
                pos = self._positions.get(sym)
            if pos is None:
                continue
            live = pos.live_pnl_pct(price)
            pos.mae_pct = min(pos.mae_pct, live)
            pos.mfe_pct = max(pos.mfe_pct, live)
            if pos.hits_tp(price):
                self._close_position(sym, price, "TP")
            elif pos.hits_sl(price):
                self._close_position(sym, price, "SL")

    def _check_pending_orders(self) -> None:
        with self._lock:
            pending = [
                o for o in self._orders.values() if o.status == OrderStatus.PENDING
            ]
        for order in pending:
            price = self._fetch_price(order.symbol)
            if price == 0:
                continue
            triggered = False
            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and price <= order.limit_price:
                    triggered = True
                elif order.side == OrderSide.SELL and price >= order.limit_price:
                    triggered = True
            elif order.order_type == OrderType.STOP_LIMIT:
                if order.side == OrderSide.BUY and price >= order.stop_price:
                    triggered = True
                elif order.side == OrderSide.SELL and price <= order.stop_price:
                    triggered = True
            if triggered:
                fill_price = order.limit_price or price
                self._fill_market(order, fill_price)
                with self._lock:
                    self._orders.pop(order.order_id, None)

    def _close_position(self, symbol: str, exit_price: float, reason: str) -> None:
        with self._lock:
            pos = self._positions.pop(symbol, None)
        if pos is None:
            return

        slip = exit_price * _SLIPPAGE
        fill = exit_price - slip if pos.side == OrderSide.BUY else exit_price + slip
        fee = pos.qty_usd * _TAKER_FEE

        if pos.side == OrderSide.BUY:
            gross_pct = (fill - pos.entry_price) / pos.entry_price
        else:
            gross_pct = (pos.entry_price - fill) / pos.entry_price

        pnl_usd = pos.qty_usd * gross_pct - fee - pos.fee_entry_usd
        pnl_pct = gross_pct * 100.0

        pos.exit_price = fill
        pos.closed_ts = time.time()
        pos.pnl_usd = pnl_usd
        pos.pnl_pct = pnl_pct
        pos.close_reason = reason

        with self._lock:
            self._capital += pos.qty_usd + pnl_usd
            self._closed.append(pos)

        try:
            from paper_trading.recorder import get_recorder

            get_recorder().record_close(
                trade_id=pos.pos_id,
                exit_price=fill,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct / 100.0,
                reason=reason,
                opened_at=pos.opened_ts,
                symbol=pos.symbol,
                side=pos.side.value.lower(),
                size_usd=pos.qty_usd,
                mode="futures_demo",
                mae_pct=pos.mae_pct,
                mfe_pct=pos.mfe_pct,
                score=pos.score,
                regime=pos.regime,
            )
        except Exception as exc:
            _log.warning("[SIM] record_close échoué: %s", exc)

        wins = sum(1 for p in self._closed if p.pnl_usd >= 0)
        losses = len(self._closed) - wins
        sign = "+" if pnl_usd >= 0 else ""
        global_pnl = (
            (self._capital - self._initial_capital) / self._initial_capital * 100
        )
        wr_str = (
            f"{wins/(wins+losses)*100:.0f}% (W={wins} L={losses})"
            if (wins + losses) > 0
            else "—"
        )
        icon = "TP atteint" if reason == "TP" else "SL touche"
        sl_efficiency = (
            f"{pos.mae_pct / pos.sl_pct_used * 100:.0f}%"
            if hasattr(pos, "sl_pct_used") and pos.sl_pct_used
            else "—"
        )
        self._notify(
            f"MEXC SIM — {icon}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Symbole  : {symbol}  {pos.side.value}\n"
            f"Entry    : ${pos.entry_price:.4g}\n"
            f"Exit     : ${fill:.4g}\n"
            f"P&L      : {sign}${pnl_usd:.4f}  ({sign}{pnl_pct:.2f}%)\n"
            f"MAE      : {pos.mae_pct:+.2f}%  (pire retour subi)\n"
            f"MFE      : {pos.mfe_pct:+.2f}%  (meilleur gain non realise)\n"
            f"Capital  : ${self._capital:.2f} USDT\n"
            f"Global   : {global_pnl:+.2f}%\n"
            f"Win Rate : {wr_str}"
        )
        _log.info(
            "[SIM] CLOSE %s %s exit=%.5f pnl=%+.4f$ (%+.2f%%) %s",
            symbol,
            pos.side.value,
            fill,
            pnl_usd,
            pnl_pct,
            reason,
        )

    # ── Rapport de performance ────────────────────────────────────────────────

    def _send_report(self) -> None:
        self._notify(self.performance_report())

    def performance_report(self) -> str:
        with self._lock:
            n_open = len(self._positions)
            closed = list(self._closed)
            open_pos = dict(self._positions)

        n_closed = len(closed)
        wins = sum(1 for p in closed if p.pnl_usd >= 0)
        wr = wins / n_closed * 100 if n_closed else 0.0
        realized_pnl = sum(p.pnl_usd for p in closed)

        # Unrealized P&L sur positions ouvertes (mark-to-market)
        unrealized_pnl = 0.0
        live_lines = []
        for sym, p in open_pos.items():
            price = self._fetch_price(sym)
            live = p.live_pnl_pct(price) if price > 0 else 0.0
            if price > 0:
                unrealized_pnl += p.qty_usd * live / 100.0
            sign = "+" if live >= 0 else ""
            from datetime import datetime, timezone

            opened_dt = datetime.fromtimestamp(p.opened_ts, tz=timezone.utc)
            opened_str = opened_dt.strftime("%d/%m %H:%M")
            live_lines.append(
                f"  {sym} {p.side.value}"
                f" entry=${p.entry_price:.4g}"
                f" live={sign}{live:.2f}%"
                f" ouvert={opened_str}"
            )

        # Equity totale = cash libre + capital déployé + PnL latent
        deployed = sum(p.qty_usd for p in open_pos.values())
        total_equity = self._capital + deployed + unrealized_pnl
        pnl_pct = (
            (total_equity - self._initial_capital) / self._initial_capital * 100
            if self._initial_capital > 0
            else 0.0
        )
        sharpe = self._perf.sharpe()
        dd = self._perf.max_drawdown_pct()
        days = self._perf.days_running()

        lines = [
            "MEXC SIM — Rapport performance",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"Duree    : J{days:.1f} / 7",
            f"Capital  : ${self._initial_capital:.2f} -> ${total_equity:.2f} USDT",
            f"P&L      : {pnl_pct:+.2f}%"
            f"  (R:{realized_pnl:+.4f}$ U:{unrealized_pnl:+.4f}$)",
            f"Sharpe   : {sharpe:.2f}",
            f"Max DD   : {dd:.2f}%",
            f"Trades   : {n_closed} fermes | {n_open} ouverts",
            f"Win Rate : {wr:.0f}%  (W={wins} L={n_closed-wins})",
        ]
        if live_lines:
            lines.append("Positions actives :")
            lines.extend(live_lines)
        return "\n".join(lines)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _notify(self, text: str) -> None:
        _log.info("[SIM] %s", text[:100])
        if self._telegram:
            try:
                self._telegram(text)
            except Exception as exc:
                _log.warning("[SIM] Telegram echec: %s", exc)
