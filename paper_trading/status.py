"""
paper_trading/status.py — Affichage terminal de l'état paper trading.

Usage :
    python -m paper_trading.status
    python paper_trading/status.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.recorder import PaperTradeRecorder  # noqa: E402


def main() -> None:
    r = PaperTradeRecorder()
    s = r.summary()
    trades = r.trades()

    print("=" * 60)
    print("  PAPER TRADING — Bilan")
    print("=" * 60)
    print(f"  Trades complétés : {s['total_closed']:>4}  /  objectif 30")
    print(f"  Positions ouvertes : {s['total_open']:>3}")
    print()

    if s["total_closed"] == 0:
        print("  Aucun trade complété enregistré.")
        print(f"  Log : {r._path}")
        print("=" * 60)
        return

    wr = s["win_rate"]
    print(f"  Win rate    : {wr:.1f}%" if wr is not None else "  Win rate    : —")
    print(f"  PnL total   : ${s['pnl_total_usd']:.2f}")
    pnl_avg = s["pnl_avg_pct"]
    print(
        f"  PnL moyen   : {pnl_avg:.3f}%"
        if pnl_avg is not None
        else "  PnL moyen   : —"
    )
    best = s["best_trade_pct"]
    worst = s["worst_trade_pct"]
    print(f"  Meilleur    : +{best:.3f}%" if best is not None else "  Meilleur    : —")
    print(f"  Pire        : {worst:.3f}%" if worst is not None else "  Pire        : —")
    dur = s["avg_duration_min"]
    print(f"  Durée moy   : {dur:.1f} min" if dur is not None else "  Durée moy   : —")
    print()
    go = s.get("go_live_ready", False)
    status = "GO LIVE ✓" if go else f"EN COURS ({s['total_closed']}/30)"
    print(f"  Statut GO/LIVE : {status}")
    print()

    closed = [t for t in trades if not t.is_open]
    if closed:
        print("  Derniers trades fermés :")
        hdr = (
            f"  {'#':>3} {'Symbole':<14} {'Side':<5}"
            f" {'Entrée':>9} {'Sortie':>9} {'PnL%':>7}"
            f" {'Raison':<15} {'W/L'}"
        )
        print(hdr)
        print("  " + "-" * 75)
        for i, t in enumerate(reversed(closed[-10:]), 1):
            pnl_s = f"{(t.pnl_pct or 0)*100:+.2f}%" if t.pnl_pct is not None else "  ?"
            wl = "WIN" if t.is_win else "LOSS"
            ep = f"{t.entry_price:.2f}" if t.entry_price else "?"
            xp = f"{t.exit_price:.2f}" if t.exit_price else "?"
            row = (
                f"  {i:>3} {t.symbol:<14} {t.side:<5}"
                f" {ep:>9} {xp:>9} {pnl_s:>7}"
                f" {t.exit_reason:<15} {wl}"
            )
            print(row)

    open_pos = [t for t in trades if t.is_open]
    if open_pos:
        print()
        print("  Positions ouvertes :")
        print(
            f"  {'Symbole':<14} {'Side':<5} {'Entrée':>9} {'Régime':<16} {'Score':>5}"
        )
        print("  " + "-" * 55)
        for t in open_pos:
            ep = f"{t.entry_price:.2f}" if t.entry_price else "?"
            print(f"  {t.symbol:<14} {t.side:<5} {ep:>9} {t.regime:<16} {t.score:>5}")

    print()
    print(f"  Log : {r._path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
