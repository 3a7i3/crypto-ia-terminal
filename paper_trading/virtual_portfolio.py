"""
paper_trading/virtual_portfolio.py — Portefeuille virtuel $100, données MEXC réelles.

Simule des trades complets en mode observation :
  - Ouvre des positions au prix MEXC réel au moment du signal
  - Surveille TP/SL toutes les 60s via fetch_ticker MEXC
  - Ferme les positions et calcule le P&L net (slippage + fees simulés)
  - Envoie une notification Telegram à chaque événement

Capital de départ : $100 (configurable via VIRTUAL_CAPITAL_USD env)
Taille par position : 15% du capital disponible (max $20)
Fees simulées : 0.10% taker (tarif MEXC spot)

Usage dans advisor_loop :
    vp = VirtualPortfolio(mexc_reader=reader, telegram_fn=_telegram_alert)
    vp.start()
    # Sur signal TRADE_OK :
    vp.open_position(symbol, side, price, tp_pct, sl_pct, score, personality)
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    from observability.json_logger import get_logger

    _log = get_logger("paper_trading.virtual_portfolio")
except Exception:
    import logging

    _log = logging.getLogger("paper_trading.virtual_portfolio")

_TAKER_FEE = 0.001  # 0.10% MEXC spot taker
_MONITOR_INTERVAL = 60  # secondes entre chaque vérification TP/SL
_POSITION_SIZE_PCT = 0.15  # 15% du capital par position
_MAX_POSITION_USD = 20.0  # plafond absolu par position


@dataclass
class VirtualPosition:
    pos_id: str
    symbol: str
    side: str  # "buy" | "sell"
    size_usd: float
    entry_price: float
    tp_price: float
    sl_price: float
    score: int
    personality: str
    opened_at: float = field(default_factory=time.time)

    # Rempli à la clôture
    exit_price: float = 0.0
    closed_at: float = 0.0
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    close_reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.closed_at == 0.0

    def current_pnl_pct(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == "buy":
            return (current_price - self.entry_price) / self.entry_price * 100.0
        else:
            return (self.entry_price - current_price) / self.entry_price * 100.0

    def hits_tp(self, price: float) -> bool:
        if self.side == "buy":
            return price >= self.tp_price
        return price <= self.tp_price

    def hits_sl(self, price: float) -> bool:
        if self.side == "buy":
            return price <= self.sl_price
        return price >= self.sl_price


class VirtualPortfolio:
    """
    Portefeuille virtuel $100 connecté aux données MEXC réelles.

    Thread-safe. Lance un thread de surveillance TP/SL en arrière-plan.
    """

    def __init__(
        self,
        mexc_reader=None,
        telegram_fn: Optional[Callable[[str], None]] = None,
        initial_capital: Optional[float] = None,
    ) -> None:
        self._capital = float(
            initial_capital or os.getenv("VIRTUAL_CAPITAL_USD", "100")
        )
        self._initial_capital = self._capital
        self._mexc = mexc_reader
        self._telegram = telegram_fn
        self._positions: dict[str, VirtualPosition] = {}
        self._closed: list[VirtualPosition] = []
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        _log.info("[VirtualPortfolio] Initialise — capital=$%.2f", self._capital)

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="VP-Monitor"
        )
        self._monitor_thread.start()
        _log.info("[VirtualPortfolio] Surveillance TP/SL démarrée")
        self._notify(
            f"[PORTFOLIO VIRTUEL] Démarré\n"
            f"Capital initial : ${self._initial_capital:.2f}\n"
            f"Source données  : MEXC (réel)\n"
            f"Mode            : SIMULATION — aucun ordre réel"
        )

    def stop(self) -> None:
        self._running = False

    # ── Ouverture position ────────────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        tp_pct: float,
        sl_pct: float,
        score: int = 0,
        personality: str = "unknown",
    ) -> Optional[VirtualPosition]:
        with self._lock:
            if symbol in self._positions:
                _log.debug("[VP] Position déjà ouverte sur %s — ignoré", symbol)
                return None

            size_usd = min(self._capital * _POSITION_SIZE_PCT, _MAX_POSITION_USD)
            if size_usd < 5.0:
                _log.warning(
                    "[VP] Capital insuffisant ($%.2f) pour ouvrir %s",
                    self._capital,
                    symbol,
                )
                return None

            # Simuler slippage entry (0.05%)
            slip = price * 0.0005
            entry = price + slip if side == "buy" else price - slip
            fee_usd = size_usd * _TAKER_FEE

            if side == "buy":
                tp_price = entry * (1 + tp_pct)
                sl_price = entry * (1 - sl_pct)
            else:
                tp_price = entry * (1 - tp_pct)
                sl_price = entry * (1 + sl_pct)

            self._capital -= size_usd + fee_usd

            pos = VirtualPosition(
                pos_id=str(uuid.uuid4())[:8],
                symbol=symbol,
                side=side,
                size_usd=size_usd,
                entry_price=entry,
                tp_price=tp_price,
                sl_price=sl_price,
                score=score,
                personality=personality,
            )
            self._positions[symbol] = pos

        arrow = "BUY" if side == "buy" else "SELL"
        self._notify(
            f"[SIM] ORDRE {arrow} — {symbol}\n"
            f"  Prix entry : ${entry:.4f} (slippage +0.05%)\n"
            f"  Taille     : ${size_usd:.2f}\n"
            f"  TP         : ${tp_price:.4f} (+{tp_pct:.1%})\n"
            f"  SL         : ${sl_price:.4f} (-{sl_pct:.1%})\n"
            f"  Score      : {score}/100 | {personality}\n"
            f"  Capital restant : ${self._capital:.2f}"
        )
        _log.info(
            "[VP] Ouverture %s %s entry=%.4f size=$%.2f TP=%.4f SL=%.4f",
            arrow,
            symbol,
            entry,
            size_usd,
            tp_price,
            sl_price,
        )
        return pos

    # ── Surveillance TP/SL ────────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_positions()
            except Exception as exc:
                _log.error("[VP] Erreur surveillance: %s", exc)
            time.sleep(_MONITOR_INTERVAL)

    def _check_positions(self) -> None:
        with self._lock:
            symbols = list(self._positions.keys())

        if not symbols or self._mexc is None:
            return

        for symbol in symbols:
            try:
                ticker = self._mexc.spot.fetch_ticker(symbol)
                price = float(ticker.get("last") or ticker.get("close") or 0)
                if price == 0:
                    continue
                with self._lock:
                    pos = self._positions.get(symbol)
                    if pos is None:
                        continue
                if pos.hits_tp(price):
                    self._close_position(symbol, price, "TP")
                elif pos.hits_sl(price):
                    self._close_position(symbol, price, "SL")
                else:
                    pnl = pos.current_pnl_pct(price)
                    _log.debug(
                        "[VP] %s | current=%.4f | PnL=%.2f%%",
                        symbol,
                        price,
                        pnl,
                    )
            except Exception as exc:
                _log.warning("[VP] fetch_ticker %s: %s", symbol, exc)

    def _close_position(self, symbol: str, exit_price: float, reason: str) -> None:
        with self._lock:
            pos = self._positions.pop(symbol, None)
        if pos is None:
            return

        slip = exit_price * 0.0005
        fill = exit_price - slip if pos.side == "buy" else exit_price + slip
        fee_usd = pos.size_usd * _TAKER_FEE

        if pos.side == "buy":
            gross = (fill - pos.entry_price) / pos.entry_price
        else:
            gross = (pos.entry_price - fill) / pos.entry_price

        pnl_usd = pos.size_usd * gross - fee_usd * 2
        pnl_pct = gross * 100.0 - (_TAKER_FEE * 2 * 100.0)

        pos.exit_price = fill
        pos.closed_at = time.time()
        pos.pnl_usd = pnl_usd
        pos.pnl_pct = pnl_pct
        pos.close_reason = reason

        with self._lock:
            self._capital += pos.size_usd + pnl_usd
            self._closed.append(pos)

        icon = "TP" if reason == "TP" else "SL"
        sign = "+" if pnl_usd >= 0 else ""
        self._notify(
            f"[SIM] FERMETURE {icon} — {symbol}\n"
            f"  Entry : ${pos.entry_price:.4f}\n"
            f"  Exit  : ${fill:.4f}\n"
            f"  P&L   : {sign}${pnl_usd:.2f} ({sign}{pnl_pct:.2f}%)\n"
            f"  Capital total : ${self._capital:.2f}\n"
            f"  Perf globale  : {self._global_pnl_pct():+.2f}%"
        )
        _log.info(
            "[VP] Fermeture %s %s exit=%.4f pnl=%+.2f$ (%+.2f%%) raison=%s",
            symbol,
            pos.side,
            fill,
            pnl_usd,
            pnl_pct,
            reason,
        )

    # ── Rapport ──────────────────────────────────────────────────────────────

    def _global_pnl_pct(self) -> float:
        if self._initial_capital == 0:
            return 0.0
        return (self._capital - self._initial_capital) / self._initial_capital * 100.0

    def report(self) -> str:
        with self._lock:
            open_count = len(self._positions)
            closed_count = len(self._closed)
            wins = sum(1 for p in self._closed if p.pnl_usd >= 0)
            losses = closed_count - wins
            total_pnl = sum(p.pnl_usd for p in self._closed)
            win_rate = (wins / closed_count * 100) if closed_count else 0.0

        lines = [
            "[RAPPORT PORTEFEUILLE VIRTUEL]",
            f"  Capital initial  : ${self._initial_capital:.2f}",
            f"  Capital actuel   : ${self._capital:.2f}",
            f"  P&L global       : {self._global_pnl_pct():+.2f}%  (${total_pnl:+.2f})",
            f"  Positions ouvertes : {open_count}",
            f"  Trades fermés    : {closed_count}  (W={wins} L={losses})",
            f"  Win rate         : {win_rate:.1f}%",
        ]
        if self._positions:
            lines.append("  Positions actives :")
            for sym, p in self._positions.items():
                lines.append(
                    f"    {sym} {p.side.upper()} entry=${p.entry_price:.4f}"
                    f" TP=${p.tp_price:.4f} SL=${p.sl_price:.4f}"
                )
        return "\n".join(lines)

    def send_report(self) -> None:
        self._notify(self.report())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _notify(self, text: str) -> None:
        _log.info("[VP] Telegram: %s", text[:80])
        if self._telegram:
            try:
                self._telegram(text)
            except Exception as exc:
                _log.warning("[VP] Telegram echec: %s", exc)
