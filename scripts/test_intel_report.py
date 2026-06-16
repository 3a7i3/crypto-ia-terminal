"""
scripts/test_intel_report.py — Envoie un briefing Intel de test.

Appelle directement SystemIntelReporter.build_report() — le même module
utilisé en production par advisor_loop.py toutes les 6h. Le message envoyé
est donc identique (pas une simulation) à ce que le bot Intel produirait.

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

from quant_hedge_ai.agents.intelligence.system_intel_reporter import (  # noqa: E402
    SystemIntelReporter,
)

_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_INTEL_TOKEN = os.getenv("INTEL_BOT_TOKEN", "")
_INTEL_CHAT = os.getenv("INTEL_BOT_CHAT_ID", "")


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


def _fake_results(events: list[dict]) -> list[dict]:
    """Reconstruit une liste 'results' minimale à partir du dernier régime connu
    par symbole — suffisant pour la section PERCEPTION MARCHÉ du rapport."""
    last_regime: dict[str, str] = {}
    for e in events:
        sym = e.get("symbol")
        regime = e.get("regime")
        if sym and regime:
            last_regime[sym] = regime
    return [
        {"symbol": sym, "regime": regime, "trade_allowed": False, "signal": None}
        for sym, regime in last_regime.items()
    ]


def send_to_intel(text: str) -> bool:
    token = _INTEL_TOKEN
    chat = _INTEL_CHAT
    if not token or not chat:
        print("[ERREUR] INTEL_BOT_TOKEN / INTEL_BOT_CHAT_ID non configurés dans .env")
        print("         Ajouter ces vars dans le .env du VPS puis relancer.")
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
    parser = argparse.ArgumentParser(description="Test diagnostic Intel")
    parser.add_argument(
        "--print", dest="print_only", action="store_true", help="Affiche sans envoyer"
    )
    args = parser.parse_args()

    events = _read_events()
    cycle_est = max(len(events) // 2, 1)

    reporter = SystemIntelReporter()
    text = reporter.build_report(
        cycle=cycle_est,
        results=_fake_results(events),
    )

    header = (
        f"[TEST — {time.strftime('%d %b %H:%M UTC', time.gmtime())}]\n"
        + ("─" * 30)
        + "\n"
    )
    full_msg = header + text

    print(full_msg)
    print()

    if args.print_only:
        print("[--print] Message non envoyé.")
        return 0

    if send_to_intel(full_msg):
        print("[OK] Envoyé → @rapport_automatique_bot")
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
