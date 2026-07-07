"""
src/telegram/portfolio_bot.py — @mon_portfolio_bot

Rôle unique : résultats paper trading en un coup d'œil.
Pas de connexion exchange, pas de métriques techniques.

Commandes :
  /portfolio         Capital, PnL%, WR, N trades, Max DD, par symbole
  /validate          Go/No-Go pour passage en live (critères burn-in)
  /trades [n]        Derniers N trades fermés (défaut 10)
  /help              Cette liste

Rapport automatique toutes les 6h (configurable via PORTFOLIO_REPORT_EVERY_H).

Env vars :
  P10_PORTFOLIO_BOT_TOKEN     token du bot
  P10_PORTFOLIO_CHAT_ID       chat_id autorisé
  PORTFOLIO_REPORT_EVERY_H    intervalle rapport auto en heures (défaut 6)
  PAPER_TRADE_LOG             chemin du JSONL (défaut databases/paper_trades.jsonl)
  VIRTUAL_CAPITAL_USD         capital initial (défaut 100)

Lancement :
  python -m src.telegram.portfolio_bot
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("telegram.portfolio_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_API = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 25
_RETRY_DELAY = 3.0
_MAX_MSG = 4000

_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_BURNIN_TARGET = 100


def _initial_capital() -> float:
    """Capital de départ — source unique via WalletSync (cf infra/wallet_sync.py)."""
    from infra.wallet_sync import get_wallet_sync

    return get_wallet_sync().initial_capital()


# ── Lecture des données ────────────────────────────────────────────────────────


def _read_trades() -> list[dict]:
    if not _TRADES_LOG.exists():
        return []
    trades: list[dict] = []
    try:
        for line in _TRADES_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    except Exception:
        pass
    return trades


def _closes(trades: list[dict]) -> list[dict]:
    return [e for e in trades if e.get("event") == "CLOSE"]


# ── Métriques ──────────────────────────────────────────────────────────────────


def _compute(closes: list[dict]) -> dict:
    if not closes:
        return {}

    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    n = len(closes)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    win_rate = len(wins) / n * 100 if n else 0

    # Courbe equity + Max DD
    initial_capital = _initial_capital()
    equity = [initial_capital]
    for p in pnls:
        equity.append(equity[-1] + p)

    peak = equity[0]
    max_dd_pct = 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak * 100
            if dd > max_dd_pct:
                max_dd_pct = dd

    capital_now = equity[-1]
    roi_pct = (capital_now - initial_capital) / initial_capital * 100

    # Profit factor
    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe per-trade (non annualisé)
    pcts = [float(c.get("pnl_pct", 0) or 0) for c in closes]
    mean_pct = sum(pcts) / n if n else 0
    var_pct = sum((p - mean_pct) ** 2 for p in pcts) / n if n > 1 else 0
    std_pct = math.sqrt(var_pct) if var_pct > 0 else 0
    sharpe = mean_pct / std_pct if std_pct > 0 else 0.0

    # Par symbole
    by_symbol: dict[str, dict] = {}
    for c in closes:
        sym = c.get("symbol", "?").replace("/USDT", "")
        pnl = float(c.get("pnl_usd", 0) or 0)
        if sym not in by_symbol:
            by_symbol[sym] = {"n": 0, "pnl": 0.0, "wins": 0}
        by_symbol[sym]["n"] += 1
        by_symbol[sym]["pnl"] += pnl
        if pnl > 0:
            by_symbol[sym]["wins"] += 1

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "total_pnl": total_pnl,
        "roi_pct": roi_pct,
        "win_rate": win_rate,
        "max_dd_pct": max_dd_pct,
        "capital_now": capital_now,
        "pf": pf,
        "sharpe": sharpe,
        "by_symbol": by_symbol,
    }


# ── Formatteurs ────────────────────────────────────────────────────────────────


def _fmt_portfolio(m: dict) -> str:
    if not m:
        return "Aucun trade fermé — burn-in en cours."

    n = m["n"]
    total_pnl = m["total_pnl"]
    roi = m["roi_pct"]
    wr = m["win_rate"]
    wins = m["wins"]
    losses = m["losses"]
    max_dd = m["max_dd_pct"]
    capital = m["capital_now"]
    burnin_pct = min(n / _BURNIN_TARGET * 100, 100)

    sign = "+" if total_pnl >= 0 else ""
    roi_sign = "+" if roi >= 0 else ""
    icon = "🟢" if total_pnl >= 0 else "🔴"

    lines = [
        f"{icon} Capital  : ${capital:.2f}  ({sign}${total_pnl:.2f} | {roi_sign}{roi:.1f}%)",
        f"📊 Trades  : {n} | WR {wr:.0f}%  (W:{wins} L:{losses})",
        f"📉 Max DD  : {max_dd:.1f}%",
        f"⏳ Burn-in : {n}/{_BURNIN_TARGET}  ({burnin_pct:.0f}%)",
    ]

    # Par symbole — trié par PnL décroissant, top 8
    by_sym = m.get("by_symbol", {})
    if by_sym:
        lines.append("")
        sorted_syms = sorted(by_sym.items(), key=lambda x: x[1]["pnl"], reverse=True)
        for sym, d in sorted_syms[:8]:
            s_n = d["n"]
            s_pnl = d["pnl"]
            s_wr = d["wins"] / s_n * 100 if s_n else 0
            s_sign = "+" if s_pnl >= 0 else ""
            lines.append(f"  {sym:<6} {s_n:>3}T  {s_sign}${s_pnl:.2f}  WR {s_wr:.0f}%")

    return "\n".join(lines)


def cmd_portfolio(_arg: str) -> str:
    trades = _read_trades()
    m = _compute(_closes(trades))
    ts = datetime.now(tz=timezone.utc).strftime("%d %b %H:%M UTC")
    header = f"Portfolio — {ts}\n"
    return header + _fmt_portfolio(m)


_LIVE_CRITERIA: list[tuple[str, float, str, bool]] = [
    ("N >= 100 trades", 99.0, "n", True),
    ("Profit Factor > 1.5", 1.5, "pf", True),
    ("Sharpe > 1.0", 1.0, "sharpe", True),
    ("Max DD < 10%", 10.0, "max_dd_pct", False),
    ("Win Rate > 45%", 45.0, "win_rate", True),
]


def cmd_validate(_arg: str) -> str:
    trades = _read_trades()
    m = _compute(_closes(trades))

    if not m:
        return "Aucun trade fermé — validation impossible."

    results = []
    for label, threshold, key, gt in _LIVE_CRITERIA:
        val = m.get(key, 0.0)
        ok = (val > threshold) if gt else (val < threshold)
        if val == float("inf"):
            ok = gt
        display = f"{val:.2f}" if key != "n" else str(int(val))
        results.append((label, ok, display))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    go = passed == total
    verdict = "GO ✅" if go else f"NO-GO ✗  ({passed}/{total})"

    lines = [f"Validation live — {verdict}", ""]
    for label, ok, display in results:
        lines.append(f"  {'✅' if ok else '❌'}  {label}  ({display})")
    lines.append("")
    lines.append("Passage en live autorisé." if go else "Critères non atteints.")
    return "\n".join(lines)


def cmd_trades(arg: str) -> str:
    n = min(int(arg) if arg.isdigit() else 10, 50)
    trades = _read_trades()
    cl = _closes(trades)[-n:]

    if not cl:
        return "Aucun trade paper fermé."

    lines = [f"Derniers {len(cl)} trades"]
    for c in reversed(cl):
        sym = c.get("symbol", "?").replace("/USDT", "")
        pnl = float(c.get("pnl_usd", 0) or 0)
        reason = c.get("reason", "?")
        sign = "+" if pnl >= 0 else ""
        icon = "🟢" if pnl >= 0 else "🔴"
        lines.append(f"  {icon} {sym:<6} {reason:<8} {sign}${pnl:.4f}")
    return "\n".join(lines)


def cmd_help(_arg: str) -> str:
    return (
        "@mon_portfolio_bot — Résultats paper trading\n"
        "\n"
        "  /portfolio    Capital, PnL%, WR, DD, par symbole\n"
        "  /validate     Go/No-Go passage en live\n"
        "  /trades [n]   Derniers N trades (défaut 10)\n"
        "  /help         Cette liste\n"
        "\n"
        "Rapport automatique toutes les 6h."
    )


# ── Dispatch ──────────────────────────────────────────────────────────────────


_DISPATCH: dict[str, Callable[[str], str]] = {
    "/portfolio": cmd_portfolio,
    "/validate": cmd_validate,
    "/trades": cmd_trades,
    "/help": cmd_help,
    "/start": cmd_help,
}


def handle(text: str) -> str:
    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    fn = _DISPATCH.get(cmd)
    if fn is None:
        return f"Commande inconnue: {cmd}\nTape /help"
    try:
        return fn(arg)[:_MAX_MSG]
    except Exception as exc:
        log.exception("handle %s", cmd)
        return f"Erreur: {exc}"


# ── Rapport automatique ────────────────────────────────────────────────────────


def _auto_report_loop(token: str, chat_id: str) -> None:
    interval_h = float(os.getenv("PORTFOLIO_REPORT_EVERY_H", "6"))
    interval_s = interval_h * 3600
    # Premier rapport après 10 min (laisser le temps au système de démarrer)
    time.sleep(600)
    while True:
        try:
            msg = cmd_portfolio("")
            _send(token, chat_id, f"Rapport auto\n\n{msg}")
        except Exception as exc:
            log.error("[AutoReport] %s", exc)
        time.sleep(interval_s)


# ── Polling HTTP ──────────────────────────────────────────────────────────────


def _call(token: str, method: str, params: dict | None = None) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT + 10) as resp:
        return json.loads(resp.read())


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        _call(token, "sendMessage", {"chat_id": chat_id, "text": text[:_MAX_MSG]})
    except Exception as exc:
        log.error("sendMessage failed: %s", exc)


def _clear_conflict(token: str) -> int:
    try:
        _call(token, "deleteWebhook", {"drop_pending_updates": "true"})
    except Exception:
        pass
    offset = 0
    try:
        r = _call(token, "getUpdates", {"timeout": 0, "offset": -1})
        updates = r.get("result", [])
        if updates:
            offset = updates[-1]["update_id"] + 1
    except Exception:
        pass
    time.sleep(1)
    return offset


def run_forever(token: str, chat_id: str) -> None:
    offset = _clear_conflict(token)

    # Lancer le rapport automatique en arrière-plan
    t = threading.Thread(
        target=_auto_report_loop,
        args=(token, chat_id),
        daemon=True,
        name="PortfolioAutoReport",
    )
    t.start()

    _send(token, chat_id, "@mon_portfolio_bot démarré\nTape /portfolio pour un résumé.")
    log.info("PortfolioBot démarré — chat: %s | offset: %d", chat_id, offset)

    seen: set[int] = set()
    while True:
        try:
            r = _call(
                token,
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": _POLL_TIMEOUT,
                    "allowed_updates": json.dumps(["message"]),
                },
            )
            for upd in r.get("result", []):
                uid = upd["update_id"]
                offset = uid + 1
                if uid in seen:
                    continue
                seen.add(uid)
                if len(seen) > 500:
                    seen.clear()

                msg = upd.get("message", {})
                from_chat = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()

                if from_chat != chat_id:
                    log.warning("Ignoré — chat non autorisé: %s", from_chat)
                    continue
                if not text.startswith("/"):
                    continue

                log.info("Commande: %s", text)
                reply = handle(text)
                _send(token, chat_id, reply)

        except KeyboardInterrupt:
            log.info("Arrêt.")
            break
        except Exception as exc:
            err = str(exc)
            if "409" in err:
                log.warning("409 Conflict — nettoyage et reprise dans 10s")
                time.sleep(10)
                offset = _clear_conflict(token)
            else:
                log.error("Erreur polling: %s — retry dans %ss", exc, _RETRY_DELAY)
                time.sleep(_RETRY_DELAY)


if __name__ == "__main__":
    _token = os.environ.get("P10_PORTFOLIO_BOT_TOKEN", "")
    _chat = os.environ.get("P10_PORTFOLIO_CHAT_ID", "")
    if not _token or not _chat:
        raise SystemExit("P10_PORTFOLIO_BOT_TOKEN et P10_PORTFOLIO_CHAT_ID requis.")
    run_forever(_token, _chat)
