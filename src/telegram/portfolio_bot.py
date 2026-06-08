"""
src/telegram/portfolio_bot.py — @mon_portfolio_bot

Rôle unique : Shadow Portfolio Engine — READ ONLY. Jamais d'ordres.

Commandes exchange (CCXT read-only):
  /sync [exchange]   Connecter exchange depuis .env (défaut: EXCHANGE_ID)
  /balance           Soldes live exchange
  /positions         Positions futures ouvertes
  /history [n] [sym] Historique trades exchange (défaut 20)
  /xpnl [sym]        PnL estimé exchange (ventes-achats-fees)
  /dd                Drawdown estimé depuis historique exchange

Commandes paper trading (fichiers locaux):
  /status            Résumé système + cycle
  /portfolio         Capital, PnL, ROI, Drawdown, Winrate, N trades
  /diagnostic        Sharpe, Sortino, Calmar, PF, Recovery, Expectancy
  /risk              Exposition, VaR 95%, Max DD
  /validate          Gatekeeper Final — go/no-go live
  /pnl               P&L réalisé total
  /trades [n]        Derniers N trades paper (défaut 10)
  /logs [n]          Derniers N lignes log (défaut 20)
  /help              Cette liste

Env vars:
  P10_PORTFOLIO_BOT_TOKEN   — token du bot
  P10_PORTFOLIO_CHAT_ID     — chat_id autorisé
  EXCHANGE_ID               — exchange par défaut (mexc, gate, binance…)
  {EXCHANGE}_API_KEY        — ex: MEXC_API_KEY
  {EXCHANGE}_API_SECRET     — ex: MEXC_API_SECRET
  VIRTUAL_CAPITAL_USD       — capital initial virtuel (défaut 100)

Lancement:
  python -m src.telegram.portfolio_bot
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from src.telegram.exchange_sync import ExchangeSync

log = logging.getLogger("telegram.portfolio_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_API = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 25
_RETRY_DELAY = 3.0
_MAX_MSG = 4000

_SNAPSHOT = Path(os.getenv("LIVE_SNAPSHOT", "databases/live_snapshot.json"))
_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_LOG_PATH = Path(os.getenv("ADVISOR_LOG", "logs/advisor_loop.log"))
_RUNTIME_CFG = Path(os.getenv("RUNTIME_CONFIG", "databases/runtime_config.json"))

# Singleton ExchangeSync partagé pour la durée de vie du processus
_sync = ExchangeSync()


# ── Helpers fichiers locaux ───────────────────────────────────────────────────


def _read_snapshot() -> dict:
    try:
        return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_runtime() -> dict:
    try:
        return json.loads(_RUNTIME_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_paused() -> bool:
    rt = _read_runtime()
    override = str(rt.get("GATE_MIN_SCORE_OVERRIDE", ""))
    return override == "100"


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


def _tail_log(n: int) -> list[str]:
    if not _LOG_PATH.exists():
        return ["(log absent)"]
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return ["(erreur lecture log)"]


# ── Commandes exchange (CCXT) ─────────────────────────────────────────────────


def cmd_sync(arg: str) -> str:
    """
    /sync           → connexion via EXCHANGE_ID depuis .env
    /sync mexc      → connexion MEXC via MEXC_API_KEY/SECRET depuis .env
    /sync gate      → connexion Gate via GATE_API_KEY/SECRET depuis .env
    """
    if arg:
        # Connexion vers l'exchange demandé, clés depuis .env
        eid = arg.strip().lower()
        key = os.getenv(f"{eid.upper()}_API_KEY", "")
        secret = os.getenv(f"{eid.upper()}_API_SECRET", "")
        if not key or not secret:
            return (
                f"Clés manquantes pour {eid.upper()}\n"
                f"Ajoute {eid.upper()}_API_KEY et {eid.upper()}_API_SECRET dans .env"
            )
        return _sync.connect(eid, key, secret)
    return _sync.connect_from_env()


def cmd_balance(_arg: str) -> str:
    return _sync.get_balances()


def cmd_positions_exchange(_arg: str) -> str:
    return _sync.get_positions()


def cmd_history(arg: str) -> str:
    """
    /history        → 20 derniers trades (tous symboles)
    /history 50     → 50 derniers trades
    /history 20 btc → 20 trades sur BTC
    """
    parts = arg.split()
    limit = 20
    symbol = None
    if parts:
        if parts[0].isdigit():
            limit = min(int(parts[0]), 100)
            if len(parts) > 1:
                symbol = parts[1]
        else:
            symbol = parts[0]
    return _sync.get_trade_history(limit=limit, symbol=symbol)


def cmd_xpnl(arg: str) -> str:
    """
    /xpnl           → PnL estimé global (top symboles)
    /xpnl btc       → PnL estimé sur BTC
    """
    symbol = arg.strip() if arg.strip() else None
    return _sync.get_pnl_summary(symbol=symbol)


def cmd_dd(_arg: str) -> str:
    return _sync.get_drawdown()


# ── Commandes paper trading (fichiers locaux) ─────────────────────────────────


def cmd_status(_arg: str) -> str:
    snap = _read_snapshot()
    if not snap:
        return "Snapshot indisponible — advisor_loop peut-être arrêté."

    capital = snap.get("capital", 0.0)
    cycle = snap.get("cycle", 0)
    safe = snap.get("safe_mode", False)
    dur = snap.get("cycle_duration_ms", 0)
    n_sym = snap.get("n_symbols", 0)
    n_act = snap.get("n_actionable", 0)
    n_traded = snap.get("n_traded", 0)
    positions = snap.get("positions", [])
    ts = snap.get("ts", 0)

    age_s = int(time.time() - ts) if ts else 0
    age_str = f"{age_s}s" if age_s < 60 else f"{age_s//60}m{age_s%60}s"
    mode = "PAUSE" if _is_paused() else ("SAFE" if safe else "ACTIF")
    xstatus = _sync.get_status()

    lines = [
        f"STATUS — {mode}",
        f"  Capital    : ${capital:.2f} USDT",
        f"  Cycle      : #{cycle} | {dur:.0f}ms | {age_str} ago",
        f"  Symboles   : {n_sym} | Actionnables: {n_act} | Tradés: {n_traded}",
        f"  Positions  : {len(positions)} ouvertes",
        "",
        xstatus,
    ]
    return "\n".join(lines)


def cmd_paper_positions(_arg: str) -> str:
    snap = _read_snapshot()
    positions = snap.get("positions", [])
    if not positions:
        return "Aucune position paper ouverte."

    lines = ["POSITIONS PAPER OUVERTES"]
    for p in positions:
        sym = p.get("symbol", "?")
        side = p.get("side", "?").upper()
        entry = p.get("entry_price", 0)
        price = p.get("current_price", 0)
        size = p.get("qty_usd", 0)
        pnl = p.get("live_pnl_pct", 0.0)
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"  {sym} {side} | entry=${entry:.4g} | live={sign}{pnl:.2f}% | ${size:.2f}"
        )
    return "\n".join(lines)


def cmd_pnl(_arg: str) -> str:
    events = _read_trades()
    closes = [e for e in events if e.get("event") == "CLOSE"]

    if not closes:
        return "Aucun trade fermé enregistré dans paper_trades.jsonl."

    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    n = len(closes)
    wr = wins / n * 100 if n else 0
    sign = "+" if total >= 0 else ""

    lines = [
        f"P&L PAPER — {n} trades",
        f"  Total    : {sign}${total:.4f}",
        f"  Win Rate : {wr:.0f}%  (W={wins} L={n-wins})",
    ]
    return "\n".join(lines)


def cmd_trades(arg: str) -> str:
    n = int(arg) if arg.isdigit() else 10
    n = min(n, 50)
    events = _read_trades()
    closes = [e for e in events if e.get("event") == "CLOSE"][-n:]

    if not closes:
        return "Aucun trade paper fermé."

    lines = [f"DERNIERS {len(closes)} TRADES PAPER"]
    for c in reversed(closes):
        sym = c.get("symbol", "?")
        pnl = float(c.get("pnl_usd", 0) or 0)
        reason = c.get("reason", "?")
        sign = "+" if pnl >= 0 else ""
        lines.append(f"  {sym} {reason} {sign}${pnl:.4f}")
    return "\n".join(lines)


def cmd_logs(arg: str) -> str:
    n = int(arg) if arg.isdigit() else 20
    n = min(n, 100)
    lines = _tail_log(n)
    return "\n".join(lines) or "(log vide)"


def _compute_metrics(closes: list[dict]) -> dict:
    """Métriques quantitatives depuis les trades fermés."""
    if not closes:
        return {}

    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    pcts = [float(c.get("pnl_pct", 0) or 0) for c in closes]
    n = len(closes)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_pnl = sum(pnls)
    win_rate = len(wins) / n * 100 if n else 0
    expectancy = total_pnl / n if n else 0

    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # Courbe d'équité depuis les trades (capital initial depuis env)
    initial = float(os.getenv("VIRTUAL_CAPITAL_USD", "100"))
    equity = [initial]
    for p in pnls:
        equity.append(equity[-1] + p)

    # Max Drawdown
    peak = equity[0]
    max_dd_pct = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd_pct:
            max_dd_pct = dd

    # Sharpe / Sortino per-trade (non annualisé — N trop faible pour daily returns)
    mean_pct = sum(pcts) / n if n else 0
    var_pct = sum((p - mean_pct) ** 2 for p in pcts) / n if n > 1 else 0
    std_pct = math.sqrt(var_pct) if var_pct > 0 else 0
    sharpe = mean_pct / std_pct if std_pct > 0 else 0.0

    neg_pcts = [p for p in pcts if p < 0]
    var_down = sum(p**2 for p in neg_pcts) / n if n > 0 else 0
    downside_std = math.sqrt(var_down) if var_down > 0 else 0
    sortino = mean_pct / downside_std if downside_std > 0 else 0.0

    # Calmar = ROI% / MaxDD%
    total_pnl_pct = (equity[-1] - equity[0]) / equity[0] * 100 if equity[0] > 0 else 0
    calmar = total_pnl_pct / max_dd_pct if max_dd_pct > 0 else 0.0

    # Recovery Factor = total_pnl / max_drawdown_$
    max_dd_usd = max_dd_pct / 100 * initial
    recovery = total_pnl / max_dd_usd if max_dd_usd > 0 else 0.0

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "pf": pf,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_dd_pct": max_dd_pct,
        "recovery": recovery,
        "initial": initial,
    }


def cmd_portfolio(_arg: str) -> str:
    snap = _read_snapshot()
    closes = [e for e in _read_trades() if e.get("event") == "CLOSE"]
    m = _compute_metrics(closes)

    capital = snap.get("capital", m.get("initial", 100.0))
    initial = m.get("initial", 100.0)
    roi = (capital - initial) / initial * 100 if initial > 0 else 0

    lines = ["PORTFOLIO"]
    lines.append(f"  Capital  : ${capital:.2f} USDT")
    lines.append(f"  PnL      : {m.get('total_pnl', 0):+.4f}$")
    lines.append(f"  ROI      : {roi:+.2f}%")
    lines.append(f"  Max DD   : {m.get('max_dd_pct', 0):.1f}%")
    lines.append(f"  Win Rate : {m.get('win_rate', 0):.0f}%")
    lines.append(f"  N Trades : {m.get('n', 0)}")
    return "\n".join(lines)


def cmd_diagnostic(_arg: str) -> str:
    closes = [e for e in _read_trades() if e.get("event") == "CLOSE"]
    m = _compute_metrics(closes)

    if not m:
        return "Aucun trade fermé — diagnostic impossible."

    n = m["n"]
    pf = m["pf"]
    pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"

    lines = [f"DIAGNOSTIC — {n} trades (métriques per-trade)"]
    lines.append(f"  Sharpe        : {m['sharpe']:.2f}")
    lines.append(f"  Sortino       : {m['sortino']:.2f}")
    lines.append(f"  Calmar        : {m['calmar']:.2f}")
    lines.append(f"  Profit Factor : {pf_str}")
    lines.append(f"  Recovery      : {m['recovery']:.2f}")
    lines.append(f"  Expectancy    : {m['expectancy']:+.4f}$")
    return "\n".join(lines)


def cmd_risk(_arg: str) -> str:
    snap = _read_snapshot()
    closes = [e for e in _read_trades() if e.get("event") == "CLOSE"]
    m = _compute_metrics(closes)

    capital = snap.get("capital", m.get("initial", 100.0))
    positions = snap.get("positions", [])
    exposure_usd = sum(float(p.get("qty_usd", 0)) for p in positions)
    exposure_pct = exposure_usd / capital * 100 if capital > 0 else 0

    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    var_str = "N/A (N<10)"
    if len(pnls) >= 10:
        idx = max(0, int(len(pnls) * 0.05))
        var_5 = sorted(pnls)[idx]
        var_str = f"{var_5:+.4f}$"

    lines = ["RISK"]
    lines.append(f"  Max DD       : {m.get('max_dd_pct', 0):.1f}%")
    lines.append(f"  Exposure     : ${exposure_usd:.2f} ({exposure_pct:.1f}%)")
    lines.append(f"  Positions    : {len(positions)}")
    lines.append(f"  VaR 95%      : {var_str}")
    return "\n".join(lines)


# Critères Gatekeeper Final pour passage en live
_LIVE_CRITERIA: list[tuple[str, float, str, bool]] = [
    # (label, seuil, clé_metric, plus_grand_que) — seuils exclusifs donc N>=100 → N>99
    ("N >= 100 trades", 99.0, "n", True),
    ("Profit Factor > 1.5", 1.5, "pf", True),
    ("Sharpe > 1.0", 1.0, "sharpe", True),
    ("Max DD < 10%", 10.0, "max_dd_pct", False),
    ("Win Rate > 45%", 45.0, "win_rate", True),
]


def cmd_validate(_arg: str) -> str:
    closes = [e for e in _read_trades() if e.get("event") == "CLOSE"]
    m = _compute_metrics(closes)

    if not m:
        return "Aucun trade fermé — validation impossible."

    results = []
    for label, threshold, key, gt in _LIVE_CRITERIA:
        val = m.get(key, 0.0)
        if val == float("inf"):
            passed = gt  # inf > threshold → True si gt
        else:
            passed = (val > threshold) if gt else (val < threshold)
        display = f"{val:.2f}" if key != "n" else str(int(val))
        results.append((label, passed, display))

    passed_count = sum(1 for _, ok, _ in results if ok)
    go = passed_count == len(results)
    verdict = "GO ✓" if go else "NO-GO ✗"

    lines = [f"VALIDATION FINALE — {verdict}"]
    lines.append(f"Score : {passed_count}/{len(results)}")
    lines.append("")
    for label, ok, display in results:
        lines.append(f"  {'✓' if ok else '✗'} {label} ({display})")
    lines.append("")
    if go:
        lines.append("Tous les critères atteints. Passage en live autorisé.")
    else:
        lines.append("Critères non atteints. Passage en live refusé.")
    return "\n".join(lines)


def cmd_help(_arg: str) -> str:
    return (
        "COMMANDES @mon_portfolio_bot — READ ONLY\n"
        "\n"
        "— Exchange (CCXT) —\n"
        "  /sync [exchange]   Connecter exchange (.env)\n"
        "  /balance           Soldes live exchange\n"
        "  /positions         Positions futures ouvertes\n"
        "  /history [n] [sym] Historique trades exchange\n"
        "  /xpnl [sym]        PnL estimé exchange\n"
        "  /dd                Drawdown estimé\n"
        "\n"
        "— Paper Trading —\n"
        "  /status            Résumé système + exchange\n"
        "  /portfolio         Capital, PnL, ROI, DD, WR, N\n"
        "  /diagnostic        Sharpe / Sortino / Calmar / PF / Recovery / Expectancy\n"
        "  /risk              Exposition, VaR 95%, Max DD\n"
        "  /validate          Gatekeeper Final — go/no-go live\n"
        "  /pnl               P&L paper réalisé total\n"
        "  /trades [n]        Derniers N trades paper\n"
        "  /logs [n]          Derniers N lignes log\n"
        "  /help              Cette aide"
    )


# ── Dispatch ──────────────────────────────────────────────────────────────────

_DISPATCH: dict[str, Callable[[str], str]] = {
    # Exchange (read-only)
    "/sync": cmd_sync,
    "/balance": cmd_balance,
    "/positions": cmd_positions_exchange,
    "/history": cmd_history,
    "/xpnl": cmd_xpnl,
    "/dd": cmd_dd,
    # Paper — observation
    "/status": cmd_status,
    "/portfolio": cmd_portfolio,
    "/diagnostic": cmd_diagnostic,
    "/risk": cmd_risk,
    "/validate": cmd_validate,
    "/pnl": cmd_pnl,
    "/trades": cmd_trades,
    "/logs": cmd_logs,
    "/help": cmd_help,
    "/start": cmd_help,
}


def handle(text: str) -> str:
    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    fn = _DISPATCH.get(cmd)
    if fn is None:
        return f"Commande inconnue: {cmd}\nTape /help pour la liste."
    try:
        reply = fn(arg)
    except Exception as exc:
        log.exception("handle %s", cmd)
        reply = f"Erreur interne: {exc}"
    return reply[:_MAX_MSG]


# ── Polling HTTP ──────────────────────────────────────────────────────────────


def _call(token: str, method: str, params: dict | None = None) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT + 10) as resp:
        return json.loads(resp.read())


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        _call(token, "sendMessage", {"chat_id": chat_id, "text": text})
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
    # Auto-connexion exchange au démarrage
    result = _sync.connect_from_env()
    log.info("ExchangeSync: %s", result)

    offset = _clear_conflict(token)
    seen: set[int] = set()
    log.info("PortfolioBot démarré — chat: %s | offset: %d", chat_id, offset)

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
