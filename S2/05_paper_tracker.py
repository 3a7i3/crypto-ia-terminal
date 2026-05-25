"""
05_paper_tracker.py — Suivi quotidien du paper trading S2.

Objectif S2: win rate > 50% maintenu sur 14 jours.

Commandes:
    python S2/05_paper_tracker.py --init --day 1
    python S2/05_paper_tracker.py --update --day 2 --trades 8 --wins 5 --pnl 0.023
    python S2/05_paper_tracker.py --report
    python S2/05_paper_tracker.py --auto   # lit paper_trades.jsonl automatiquement
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

TRACKER_PATH = "databases/paper_tracking.jsonl"
PT_PATH = "databases/paper_trades.jsonl"
TARGET_WR = 0.50
TARGET_DAYS = 14


def load_tracker() -> list[dict]:
    p = Path(TRACKER_PATH)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def save_entry(entry: dict) -> None:
    Path(TRACKER_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_paper_trades_today() -> dict:
    """Lit paper_trades.jsonl et retourne stats du jour courant."""
    p = Path(PT_PATH)
    if not p.exists():
        return {"trades": 0, "wins": 0, "pnl": 0.0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trades = 0
    wins = 0
    total_pnl = 0.0

    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("event") != "CLOSE":
                continue
            ts_iso = d.get("ts_iso", "")
            if not ts_iso.startswith(today):
                continue
            trades += 1
            pnl = d.get("pnl_pct", 0) or 0
            if pnl > 0:
                wins += 1
            total_pnl += pnl

    return {"trades": trades, "wins": wins, "pnl": round(total_pnl, 4)}


def cmd_init(day: int) -> None:
    existing = load_tracker()
    if existing:
        print(
            f"[paper_tracker] Tracker existant ({len(existing)} entrées). Ajout jour {day}."
        )
    entry = {
        "ts": time.time(),
        "day": day,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "trades": 0,
        "wins": 0,
        "pnl": 0.0,
        "note": "init",
    }
    save_entry(entry)
    print(f"[paper_tracker] Jour {day} initialisé — {entry['date']}")


def cmd_update(day: int, trades: int, wins: int, pnl: float, note: str = "") -> None:
    entry = {
        "ts": time.time(),
        "day": day,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "trades": trades,
        "wins": wins,
        "pnl": round(pnl, 4),
        "note": note,
    }
    save_entry(entry)
    wr = wins / trades if trades else 0
    print(
        f"[paper_tracker] Jour {day} enregistré: "
        f"{wins}/{trades} trades gagnants (WR={wr:.0%}) pnl={pnl:+.2%}"
    )


def cmd_auto(day: int) -> None:
    """Récupère automatiquement les stats du jour depuis paper_trades.jsonl."""
    stats = load_paper_trades_today()
    cmd_update(day, stats["trades"], stats["wins"], stats["pnl"], note="auto")


def cmd_report() -> None:
    entries = load_tracker()
    if not entries:
        print("[paper_tracker] Aucune donnée. Lancer --init d'abord.")
        return

    # Dédupliquer par jour (garder la dernière entrée par jour)
    by_day: dict[int, dict] = {}
    for e in entries:
        d = e.get("day", 0)
        if d not in by_day or e["ts"] > by_day[d]["ts"]:
            by_day[d] = e

    days_data = sorted(by_day.values(), key=lambda x: x["day"])

    total_trades = sum(d["trades"] for d in days_data)
    total_wins = sum(d["wins"] for d in days_data)
    total_pnl = sum(d["pnl"] for d in days_data)
    global_wr = total_wins / total_trades if total_trades else 0
    days_active = len([d for d in days_data if d["trades"] > 0])

    # Streak de jours avec WR > 50%
    streak = 0
    for d in reversed(days_data):
        if d["trades"] > 0 and d["wins"] / d["trades"] >= TARGET_WR:
            streak += 1
        else:
            break

    print(f"\n{'='*60}")
    print(f"  PAPER TRACKER — OBJECTIF S2 ({TARGET_DAYS} jours, WR>{TARGET_WR:.0%})")
    print(f"{'='*60}")
    print(f"  Jours actifs : {days_active}/{TARGET_DAYS}")
    print(
        f"  Trades total : {total_trades}  |  Wins: {total_wins}  |  WR: {global_wr:.1%}"
    )
    print(f"  PnL cumulé  : {total_pnl:+.2%}")
    print(f"  Streak WR>50%: {streak} jour(s) consécutifs")

    target_reached = global_wr >= TARGET_WR and days_active >= TARGET_DAYS
    if target_reached:
        print(f"\n  ✓ OBJECTIF S2 ATTEINT — passage en live autorisé!")
    elif days_active >= TARGET_DAYS:
        gap = TARGET_WR - global_wr
        print(f"\n  ✗ 14 jours complets mais WR={global_wr:.1%} (manque {gap:.1%})")
    else:
        remaining = TARGET_DAYS - days_active
        print(f"\n  En cours — {remaining} jours restants")

    print(
        f"\n  {'Jour':>5}  {'Date':<12}  {'T':>4}  {'W':>4}  {'WR':>7}  {'PnL':>8}  {'Status'}"
    )
    print(f"  {'─'*55}")
    for d in days_data:
        t, w = d["trades"], d["wins"]
        wr = w / t if t > 0 else 0
        pnl = d["pnl"]
        status = "✓" if t > 0 and wr >= TARGET_WR else ("✗" if t > 0 else "—")
        print(
            f"  {d['day']:>5}  {d['date']:<12}  {t:>4}  {w:>4}  "
            f"{wr:>6.0%}  {pnl:>+7.2%}  {status}"
        )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper Tracker S2")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument(
        "--auto", action="store_true", help="Auto-lecture paper_trades.jsonl"
    )
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--day", type=int, default=1)
    parser.add_argument("--trades", type=int, default=0)
    parser.add_argument("--wins", type=int, default=0)
    parser.add_argument("--pnl", type=float, default=0.0)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.init:
        cmd_init(args.day)
    elif args.auto:
        cmd_auto(args.day)
    elif args.update:
        cmd_update(args.day, args.trades, args.wins, args.pnl, args.note)
    elif args.report:
        cmd_report()
    else:
        cmd_report()


if __name__ == "__main__":
    main()
