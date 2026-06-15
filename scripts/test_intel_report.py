"""
scripts/test_intel_report.py — Envoie un briefing Intel de test.

Simule exactement ce que le bot Intel enverrait dans 6h :
  - Lit paper_trades.jsonl pour le PnL/positions
  - Appelle ChiefOfficer._deterministic_analysis (même fallback que le VPS)
  - Envoie vers INTEL_BOT_TOKEN / INTEL_BOT_CHAT_ID

Usage :
    python scripts/test_intel_report.py
    python scripts/test_intel_report.py --print   # affiche sans envoyer
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows: forcer UTF-8 pour l'affichage terminal
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import requests  # noqa: E402

from quant_hedge_ai.agents.intelligence.chief_officer import ChiefOfficer  # noqa: E402

_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_INITIAL_CAPITAL = float(os.getenv("VIRTUAL_CAPITAL_USD", "100"))
_INTEL_TOKEN = os.getenv("INTEL_BOT_TOKEN", "")
_INTEL_CHAT = os.getenv("INTEL_BOT_CHAT_ID", "")
_MAIN_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_MAIN_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def _read_events() -> list[dict]:
    if not _TRADES_LOG.exists():
        return []
    events = []
    try:
        for line in _TRADES_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
    except Exception:
        pass
    return events


def _build_context(events: list[dict], cycle: int) -> dict:
    closes = [e for e in events if e.get("event") == "CLOSE"]
    opens = [e for e in events if e.get("event") == "OPEN"]

    # Positions ouvertes
    open_symbols = {e.get("symbol") for e in opens}
    closed_symbols = {e.get("symbol") for e in closes}
    truly_open = open_symbols - closed_symbols

    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    n = len(closes)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    wr = len(wins) / n if n else 0

    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0

    # Equity curve pour PnL ouvert approximatif
    equity = _INITIAL_CAPITAL + total_pnl
    open_pnl = 0.0
    for e in events:
        if e.get("event") == "OPEN" and e.get("symbol") in truly_open:
            open_pnl += float(e.get("pnl_usd", 0) or 0)

    # Régime actuel — dernier signal connu
    last_regimes = {}
    for e in events:
        sym = e.get("symbol", "")
        regime = e.get("regime", "")
        if regime:
            last_regimes[sym] = regime
    dominant_regime = (
        max(set(last_regimes.values()), key=list(last_regimes.values()).count)
        if last_regimes
        else "unknown"
    )

    ctx: dict = {
        "cycle": cycle,
        "symbols": list(set(e.get("symbol", "") for e in events if e.get("symbol"))),
        "signals": [],
        "positions": {
            "open": len(truly_open),
            "pnl_open": round(open_pnl, 2),
            "pnl_total": round(total_pnl, 2),
            "win_rate": wr,
            "closed": n,
        },
    }

    # Activité du capital — si 0 trades fermés, capital gelé
    cycles_since = 0 if n > 0 else 999
    ctx["activity"] = {
        "inactivity_ratio": 0.0 if n > 0 else 0.9,
        "execution_ratio": 1.0 if n > 0 else 0.1,
        "cycles_since_last_trade": cycles_since,
        "alert_overfiltered": n == 0,
        "stalled": n == 0,
        "stall_label": "stalled" if n == 0 else "active",
        "stall_confidence": 0.85 if n == 0 else 0.0,
        "top_blockers": (
            [{"name": "portfolio", "count": 12}, {"name": "score", "count": 8}]
            if n == 0
            else []
        ),
    }

    # Regrets — approximatif
    ctx["regret"] = {
        "missed_wins": 0,
        "refusal_accuracy": 1.0,
    }

    return ctx


def build_briefing(ctx: dict, cycle: int) -> str:
    coo = ChiefOfficer()
    return coo._deterministic_analysis(ctx, cycle)  # type: ignore[attr-defined]


def send_to_intel(text: str) -> bool:
    token = _INTEL_TOKEN or _MAIN_TOKEN
    chat = _INTEL_CHAT or _MAIN_CHAT
    if not token or not chat:
        print("[ERREUR] INTEL_BOT_TOKEN / INTEL_BOT_CHAT_ID non configurés dans .env")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        print(f"[ERREUR] Telegram: {r.status_code} — {r.text[:200]}")
        return False
    except Exception as exc:
        print(f"[ERREUR] Envoi Telegram: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Test briefing Intel")
    parser.add_argument(
        "--print", dest="print_only", action="store_true", help="Affiche sans envoyer"
    )
    args = parser.parse_args()

    events = _read_events()
    closes = [e for e in events if e.get("event") == "CLOSE"]
    n_closed = len(closes)

    # Cycle estimé depuis le nombre d'événements
    cycle_est = max(len(events) // 2, 1)

    ctx = _build_context(events, cycle_est)
    text = build_briefing(ctx, cycle_est)

    # Ajouter un header de contexte test
    header = (
        f"[TEST INTEL — {time.strftime('%d %b %H:%M UTC', time.gmtime())}]\n"
        f"Dataset: {n_closed} trades fermés | {len(events)} événements\n"
        "─────────────────────────────\n"
    )
    full_msg = header + text

    print(full_msg)
    print()

    if args.print_only:
        print("[--print] Message non envoyé.")
        return 0

    if send_to_intel(full_msg):
        dest = "Intel bot" if _INTEL_TOKEN else "bot principal (fallback)"
        print(f"[OK] Envoyé → {dest}")
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
