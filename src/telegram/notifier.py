"""
src/telegram/notifier.py — Notifications push vers Telegram.

Utilisé par mexc_simulator et advisor_loop pour envoyer automatiquement
les événements importants : trades, alertes, rapport quotidien.

Env vars :
  P10_PORTFOLIO_BOT_TOKEN  — token du bot Telegram
  P10_PORTFOLIO_CHAT_ID    — chat_id destinataire
"""

from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("telegram.notifier")

_API = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 8


class Notifier:
    """
    Push notifications vers un canal Telegram.
    Thread-safe — chaque appel est une requête HTTP indépendante.
    """

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self._token = token or os.environ.get("P10_PORTFOLIO_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("P10_PORTFOLIO_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id)
        if not self._enabled:
            log.warning(
                "Notifier désactivé — P10_PORTFOLIO_BOT_TOKEN ou CHAT_ID manquant"
            )

    # ── Événements de trading ─────────────────────────────────────────────────

    def trade_opened(
        self,
        symbol: str,
        side: str,
        price: float,
        size_usd: float,
        score: int,
        personality: str,
        tp_pct: float,
        sl_pct: float,
        capital_remaining: float,
    ) -> None:
        arrow = "BUY" if side.upper() in ("BUY", "LONG") else "SELL"
        self._send(
            f"[SIM] {arrow} {symbol}\n"
            f"  Prix: ${price:.4g} | Taille: ${size_usd:.2f}\n"
            f"  TP: +{tp_pct:.1%} | SL: -{sl_pct:.1%}\n"
            f"  Score: {score} | {personality}\n"
            f"  Capital: ${capital_remaining:.2f}"
        )

    def trade_closed(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl_usd: float,
        pnl_pct: float,
        reason: str,
        capital: float,
        global_pnl_pct: float,
        win_rate: float | None,
        n_closed: int,
    ) -> None:
        icon = "✅ TP" if reason == "TP" else "❌ SL"
        sign = "+" if pnl_usd >= 0 else ""
        wr_str = f"{win_rate:.0f}%" if win_rate is not None else "—"
        self._send(
            f"[SIM] {icon} {symbol} {side.upper()}\n"
            f"  Entry: ${entry_price:.4g} → Exit: ${exit_price:.4g}\n"
            f"  P&L: {sign}${pnl_usd:.4f} ({sign}{pnl_pct:.2f}%)\n"
            f"  Capital: ${capital:.2f} | Global: {global_pnl_pct:+.2f}%\n"
            f"  WR: {wr_str} ({n_closed} trades)"
        )

    def performance_report(self, report_text: str) -> None:
        self._send(report_text)

    # ── Événements simulation (compatibilité SimBot) ──────────────────────────

    def run_completed(self, report: dict, source: str = "") -> None:
        sign = "+" if report.get("total_pnl", 0) >= 0 else ""
        regime_emoji = {"trending": "📈", "sideways": "↔️", "volatile": "⚡"}.get(
            report.get("regime", ""), "❓"
        )
        src = f" | {source}" if source else ""
        self._send(
            f"[SIM] Run {report.get('run_id', '?')}{src}\n"
            f"  Strat: {report.get('strategy_id', '?')}\n"
            f"  Régime: {regime_emoji} {report.get('regime', '?')}\n"
            f"  Trades: {report.get('total_trades', 0)} | "
            f"PnL: {sign}{report.get('total_pnl', 0):.2f}$ | "
            f"WR: {report.get('win_rate', 0):.0%}"
        )

    def stress_completed(
        self, n_runs: int, avg_pnl: float, pf: float, win_rate: float
    ) -> None:
        sign = "+" if avg_pnl >= 0 else ""
        self._send(
            f"[SIM] Stress test — {n_runs} runs\n"
            f"  Avg PnL: {sign}{avg_pnl:.2f}$ | PF: {pf:.2f} | WR: {win_rate:.0%}"
        )

    def robust_completed(self, n_folds: int, avg_exp: float, ratio_pos: float) -> None:
        sign = "+" if avg_exp >= 0 else ""
        verdict = "OK" if ratio_pos >= 0.65 else "LIMITE" if ratio_pos >= 0.5 else "NON"
        self._send(
            f"[SIM] Robustesse [{verdict}] — {n_folds} folds\n"
            f"  Avg exp: {sign}{avg_exp:.3f} | Folds+: {ratio_pos:.0%}"
        )

    def race_completed(
        self, symbol: str, interval: str, winner: str, exp: float
    ) -> None:
        sign = "+" if exp >= 0 else ""
        self._send(
            f"[SIM] Race {symbol} {interval}\n"
            f"  Gagnant: {winner} ({sign}{exp:.3f} exp/trade)"
        )

    def paper_trade(
        self,
        symbol: str,
        side: str,
        price: float,
        size: float,
        strategy: str,
        confidence: float,
    ) -> None:
        emoji = "BUY" if side == "buy" else "SELL"
        self._send(
            f"[PAPER] {emoji} {symbol}\n"
            f"  Prix: {price:.4f} | Size: {size:.4f}\n"
            f"  Strat: {strategy} | Conf: {confidence:.0%}"
        )

    # ── Événements système ────────────────────────────────────────────────────

    def kill_switch(self, reason: str) -> None:
        self._send(f"KILL SWITCH\n  {reason}")

    def alert(self, message: str) -> None:
        self._send(f"ALERTE {message}")

    def info(self, message: str) -> None:
        self._send(f"INFO {message}")

    # ── Interne ───────────────────────────────────────────────────────────────

    def _send(self, text: str) -> None:
        if not self._enabled:
            log.debug("[Notifier] (disabled) %s", text[:80])
            return
        ts = datetime.now(timezone.utc).strftime("%H:%M")
        full = f"[{ts}] {text}"
        try:
            params = {"chat_id": self._chat_id, "text": full}
            data = urllib.parse.urlencode(params).encode()
            url = _API.format(token=self._token, method="sendMessage")
            urllib.request.urlopen(
                urllib.request.Request(url, data=data), timeout=_TIMEOUT
            )
        except Exception as exc:
            log.warning("[Notifier] Envoi échoué: %s", exc)


# ── Singleton partagé ─────────────────────────────────────────────────────────

_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier
