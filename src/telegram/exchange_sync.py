"""
src/telegram/exchange_sync.py — CCXT read-only sync pour @mon_portfolio_bot.

Connexion à n'importe quel exchange supporté par CCXT.
Aucune action directe (pas d'ordres, pas d'écritures).
Méthodes: balance, positions, historique trades, PnL estimé, drawdown.

Auto-connexion via env vars:
  EXCHANGE_ID              — slug de l'exchange (mexc, gate, binance…)
  {EXCHANGE}_API_KEY       — ex: MEXC_API_KEY
  {EXCHANGE}_API_SECRET    — ex: MEXC_API_SECRET

Connexion manuelle:
  sync.connect("gate", api_key, api_secret)
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("telegram.exchange_sync")

try:
    import ccxt

    _CCXT_OK = True
except ImportError:
    _CCXT_OK = False


# Symboles par défaut pour balayage multi-symbol
_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]


class ExchangeSync:
    """
    Sync lecture seule via CCXT.
    Thread-safe si chaque thread possède son instance.
    """

    def __init__(self) -> None:
        self._exchange: Any = None
        self._exchange_id: str = ""

    # ── Connexion ───────────────────────────────────────────────────────────────

    def connect(self, exchange_id: str, api_key: str, api_secret: str) -> str:
        if not _CCXT_OK:
            return "ERREUR: ccxt non installé (pip install ccxt)"
        eid = exchange_id.lower().strip()
        if eid not in ccxt.exchanges:
            top = ", ".join(sorted(ccxt.exchanges)[:15])
            return f"Exchange inconnu: {eid}\nExemples supportés: {top}…"
        try:
            cls = getattr(ccxt, eid)
            ex = cls(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                }
            )
            ex.load_markets()
            self._exchange = ex
            self._exchange_id = eid
            n_markets = len(ex.markets)
            return f"Connecté: {eid.upper()} | {n_markets} marchés chargés"
        except Exception as exc:
            self._exchange = None
            return f"Erreur connexion {exchange_id}: {exc}"

    def connect_from_env(self) -> str:
        """Connexion automatique depuis EXCHANGE_ID + {EXCHANGE}_API_KEY/SECRET."""
        eid = os.getenv("EXCHANGE_ID", "mexc").lower()
        key = os.getenv(f"{eid.upper()}_API_KEY") or os.getenv("MEXC_API_KEY", "")
        secret = os.getenv(f"{eid.upper()}_API_SECRET") or os.getenv(
            "MEXC_API_SECRET", ""
        )
        if not key or not secret:
            return f"Clés API manquantes pour {eid.upper()} — vérifie .env"
        return self.connect(eid, key, secret)

    def is_connected(self) -> bool:
        return self._exchange is not None

    def _check(self) -> str | None:
        if not self.is_connected():
            return "Non connecté — envoie /sync pour connecter un exchange."
        return None

    def get_status(self) -> str:
        if not self.is_connected():
            return "Exchange: non connecté\nUtilise /sync [exchange] pour connecter."
        n = len(self._exchange.markets)
        return f"Exchange: {self._exchange_id.upper()} (connecté)\nMarchés: {n}"

    # ── Balance ─────────────────────────────────────────────────────────────────

    def get_balances(self) -> str:
        err = self._check()
        if err:
            return err
        try:
            bal = self._exchange.fetch_balance()
            total: dict = bal.get("total", {}) or {}
            usdt = float(total.get("USDT", 0) or 0)
            assets = [
                (k, float(v))
                for k, v in total.items()
                if v and float(v) > 0 and k not in ("USDT", "info")
            ]
            assets.sort(key=lambda x: x[1], reverse=True)

            lines = [
                f"BALANCE — {self._exchange_id.upper()}",
                f"  USDT   : ${usdt:.4f}",
            ]
            for sym, qty in assets[:10]:
                lines.append(f"  {sym:<8}: {qty:.6g}")
            if not assets and usdt == 0:
                lines.append("  (aucun solde non-nul)")
            return "\n".join(lines)
        except Exception as exc:
            return f"Erreur balance: {exc}"

    # ── Positions futures ────────────────────────────────────────────────────────

    def get_positions(self) -> str:
        err = self._check()
        if err:
            return err
        try:
            ex = self._exchange.__class__(
                {
                    "apiKey": self._exchange.apiKey,
                    "secret": self._exchange.secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
            raw = ex.fetch_positions()
            open_pos = [p for p in raw if float(p.get("contracts") or 0) != 0]
        except Exception:
            open_pos = []

        if not open_pos:
            return "Aucune position futures ouverte."

        lines = ["POSITIONS OUVERTES (futures)"]
        for p in open_pos:
            sym = p.get("symbol", "?")
            side = (p.get("side") or "?").upper()
            entry = float(p.get("entryPrice") or 0)
            upnl = float(p.get("unrealizedPnl") or 0)
            notional = float(p.get("notional") or 0)
            sign = "+" if upnl >= 0 else ""
            lines.append(
                f"  {sym} {side} | entry={entry:.4g}"
                f" | uPnL={sign}{upnl:.4f}"
                f" | ${notional:.2f}"
            )
        return "\n".join(lines)

    # ── Historique trades ────────────────────────────────────────────────────────

    def get_trade_history(self, limit: int = 20, symbol: str | None = None) -> str:
        err = self._check()
        if err:
            return err
        try:
            trades: list[dict] = []
            if symbol:
                sym_full = _normalize_symbol(symbol)
                trades = self._exchange.fetch_my_trades(sym_full, limit=limit)
            else:
                for sym in _DEFAULT_SYMBOLS:
                    if sym not in self._exchange.markets:
                        continue
                    try:
                        batch = self._exchange.fetch_my_trades(sym, limit=10)
                        trades.extend(batch)
                    except Exception:
                        pass
                trades.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
                trades = trades[:limit]

            if not trades:
                return "Aucun trade dans l'historique exchange."

            lines = [f"HISTORIQUE — {len(trades)} trades ({self._exchange_id.upper()})"]
            for t in trades:
                sym = t.get("symbol", "?")
                side = (t.get("side") or "?").upper()
                price = float(t.get("price") or 0)
                cost = float(t.get("cost") or 0)
                fee = float((t.get("fee") or {}).get("cost") or 0)
                dt = (t.get("datetime") or "?")[:16]
                lines.append(
                    f"  {dt}  {sym:<12} {side:<4}"
                    f" ${cost:.4f} @ {price:.4g}"
                    f" fee={fee:.4g}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Erreur historique: {exc}"

    # ── PnL estimé ──────────────────────────────────────────────────────────────

    def get_pnl_summary(
        self, symbol: str | None = None, limit_per_sym: int = 100
    ) -> str:
        err = self._check()
        if err:
            return err
        try:
            trades: list[dict] = []
            symbols = [_normalize_symbol(symbol)] if symbol else _DEFAULT_SYMBOLS
            for sym in symbols:
                if sym not in self._exchange.markets:
                    continue
                try:
                    batch = self._exchange.fetch_my_trades(sym, limit=limit_per_sym)
                    trades.extend(batch)
                except Exception:
                    pass

            if not trades:
                return "Aucun trade exchange pour calcul PnL."

            buy_vol = sum(
                float(t.get("cost") or 0) for t in trades if t.get("side") == "buy"
            )
            sell_vol = sum(
                float(t.get("cost") or 0) for t in trades if t.get("side") == "sell"
            )
            fees = sum(float((t.get("fee") or {}).get("cost") or 0) for t in trades)
            net = sell_vol - buy_vol - fees
            n_buys = sum(1 for t in trades if t.get("side") == "buy")
            n_sells = sum(1 for t in trades if t.get("side") == "sell")
            sign = "+" if net >= 0 else ""

            lines = [
                f"PnL EXCHANGE — {self._exchange_id.upper()}",
                f"  Achats : {n_buys} trades | ${buy_vol:.4f}",
                f"  Ventes : {n_sells} trades | ${sell_vol:.4f}",
                f"  Fees   : ${fees:.6f}",
                f"  Net    : {sign}${net:.4f}",
                f"  (estimation — ventes - achats - fees)",
            ]
            return "\n".join(lines)
        except Exception as exc:
            return f"Erreur PnL: {exc}"

    # ── Drawdown estimé ──────────────────────────────────────────────────────────

    def get_drawdown(self, limit_per_sym: int = 200) -> str:
        err = self._check()
        if err:
            return err
        try:
            trades: list[dict] = []
            for sym in _DEFAULT_SYMBOLS:
                if sym not in self._exchange.markets:
                    continue
                try:
                    batch = self._exchange.fetch_my_trades(sym, limit=limit_per_sym)
                    trades.extend(batch)
                except Exception:
                    pass

            trades.sort(key=lambda x: x.get("timestamp") or 0)

            if len(trades) < 2:
                return "Données insuffisantes pour DD (min 2 trades)."

            equity = 0.0
            peak = 0.0
            max_dd = 0.0
            for t in trades:
                cost = float(t.get("cost") or 0)
                fee = float((t.get("fee") or {}).get("cost") or 0)
                if t.get("side") == "sell":
                    equity += cost - fee
                else:
                    equity -= cost + fee
                if equity > peak:
                    peak = equity
                if peak > 0:
                    dd = (peak - equity) / peak
                    max_dd = max(max_dd, dd)

            current_dd = (peak - equity) / peak if peak > 0 else 0.0

            lines = [
                f"DRAWDOWN — {self._exchange_id.upper()}",
                f"  DD actuel : -{current_dd:.2%}",
                f"  DD max    : -{max_dd:.2%}",
                f"  ({len(trades)} fills analysés)",
                f"  (proxy equity = cumul ventes - achats - fees)",
            ]
            return "\n".join(lines)
        except Exception as exc:
            return f"Erreur drawdown: {exc}"


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _normalize_symbol(sym: str) -> str:
    sym = sym.upper().strip()
    if "/" not in sym and not sym.endswith("USDT"):
        sym = sym + "USDT"
    return sym
