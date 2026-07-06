"""
tools/decision_trace.py — Audit trail décisionnel depuis le RejectionStore.

Affiche la chaîne causale complète pour chaque (cycle, symbole). Ce CLI est un
client texte de DecisionTraceService (visualization/decision_trace_service.py) —
la même logique alimente la SDOS Data API (visualization/api/decision_api.py)
consommée par le terminal web. Aucune écriture. Outil de mesure scientifique —
conforme Phase II gel fonctionnel.

Usage:
    python tools/decision_trace.py
    python tools/decision_trace.py --date 2026-06-30
    python tools/decision_trace.py --date 2026-06-30 --symbol SLX
    python tools/decision_trace.py --date 2026-06-30 --cycle 87
    python tools/decision_trace.py --date 2026-06-30 --symbol SLX --cycle 87
    python tools/decision_trace.py --file /path/to/rejections.jsonl
    python tools/decision_trace.py --summary   # stats par bloqueur uniquement
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from visualization.decision_trace_service import DecisionTraceService, DecisionTrace, label_for

# Force UTF-8 sur Windows (PowerShell / cmd encodent en cp1252 par defaut)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_service = DecisionTraceService()

_PASS = "PASS"
_BLOCK = "BLOCK"
_UNKNOWN = "?"
_BOLD = ""
_RESET = ""
_DIM = ""


# -- Affichage d'une trace -------------------------------------------------

def print_trace(trace: DecisionTrace) -> None:
    print(f"\n{_BOLD}{'-'*60}{_RESET}")
    print(f"{_BOLD}[C{trace.cycle}] {trace.symbol}  {trace.side}  score={trace.score}  régime={trace.regime}{_RESET}")
    print(f"{_DIM}{(trace.ts_iso or '')[:19]}  obs={trace.observation_id}{_RESET}")

    for step in trace.steps:
        prefix = "\n" if step.step > 1 else ""
        print(f"{prefix}  ÉTAPE {step.step}  {step.name}")
        icon = _PASS if step.status else (_BLOCK if step.status is False else _UNKNOWN)
        print(f"  [{icon}]  {_DIM}{step.detail}{_RESET}")

    print(f"\n{'-'*40}")
    if trace.all_blockers:
        print(f"  {_BLOCK} PREMIER BLOQUEUR : {label_for(trace.all_blockers[0])}")
        if len(trace.all_blockers) > 1:
            others = ", ".join(label_for(b) for b in trace.all_blockers[1:])
            print(f"  {_DIM}autres bloqueurs: {others}{_RESET}")
    else:
        if trace.trade_allowed:
            print(f"  {_PASS} AUTORISÉ")
        else:
            print(f"  {_UNKNOWN} Refusé — bloqueur non enregistré")
    print(f"  Verdict: {trace.verdict}")
    print(f"  Taille base: ${trace.base_size_usd:.2f}")


# -- Vue résumée (plusieurs entrées) ------------------------------------------

def print_summary_table(entries: list[dict[str, Any]]) -> None:
    if not entries:
        print("Aucune entrée trouvée.")
        return

    stats = _service.statistics(entries)

    groups: dict[tuple, dict] = {}
    for e in entries:
        key = (e.get("cycle", 0), e.get("symbol", "?"))
        if key not in groups:
            groups[key] = e

    print(f"\n{_BOLD}{'='*70}{_RESET}")
    print(f"{_BOLD}  DECISION TRACE — RÉSUMÉ  ({len(entries)} entrées, {len(groups)} uniques){_RESET}")
    print(f"{'='*70}{_RESET}")

    print(f"\n  {'CYC':>4}  {'SYMBOLE':<12}  {'SIDE':<5}  {'SCR':>3}  {'RÉGIME':<15}  {'PERSONNALITÉ':<18}  BLOQUEUR")
    print(f"  {'-'*4}  {'-'*12}  {'-'*5}  {'-'*3}  {'-'*15}  {'-'*18}  {'-'*30}")

    for (cyc, sym), e in sorted(groups.items()):
        side = e.get("side", "?")
        score = int(e.get("score", 0))
        regime = e.get("regime", "?")[:15]
        pers = e.get("personality_name", "?")[:18]
        first_b = (e.get("first_blocker") or "—")[:30]
        allowed = e.get("trade_allowed", False)
        verdict_icon = "✓" if allowed else "✗"
        print(f"  {cyc:>4}  {sym:<12}  {side:<5}  {score:>3}  {regime:<15}  {pers:<18}  {verdict_icon} {first_b}")

    print(f"\n  {_BOLD}Bloqueurs par fréquence:{_RESET}")
    for blocker, count in Counter(stats["by_layer"]).most_common():
        pct = stats["by_layer_pct"].get(blocker, 0.0)
        bar = "█" * int(pct / 5)
        print(f"    {blocker:<30} {count:>5}  ({pct:5.1f}%)  {bar}")

    print(f"\n  {_BOLD}Régimes:{_RESET}")
    for regime, count in Counter(stats["by_regime"]).most_common():
        print(f"    {regime:<25} {count:>5}")

    print(f"\n  {_BOLD}Personnalités:{_RESET}")
    for pers, count in Counter(stats["by_personality"]).most_common():
        print(f"    {pers:<25} {count:>5}")


def print_blocker_stats(entries: list[dict[str, Any]]) -> None:
    """Statistiques agrégées uniquement — mode --summary/--stats."""
    stats = _service.statistics(entries)
    n = stats["n_entries"]

    by_symbol: dict[str, Counter] = {}
    by_regime: dict[str, Counter] = {}
    for e in entries:
        sym = e.get("symbol", "?").replace("/USDT", "")
        regime = e.get("regime", "?")
        for b in e.get("all_blockers") or []:
            bkey = b.split("(")[0]
            by_symbol.setdefault(sym, Counter())[bkey] += 1
            by_regime.setdefault(regime, Counter())[bkey] += 1

    print(f"\n{_BOLD}BLOCKER STATS — {n} signaux analysés{_RESET}")
    print(f"{'-'*50}")
    print(f"\n  Par bloqueur :")
    for bk, cnt in Counter(stats["by_layer"]).most_common():
        pct = stats["by_layer_pct"].get(bk, 0.0)
        print(f"    {label_for(bk):<40} {cnt:>4}  ({pct:.1f}%)")

    print(f"\n  Par symbole (top bloqueurs) :")
    for sym in sorted(by_symbol):
        top = by_symbol[sym].most_common(1)
        if top:
            bk, cnt = top[0]
            print(f"    {sym:<12}  {label_for(bk):<30}  {cnt}×")

    print(f"\n  Par régime :")
    for regime in sorted(by_regime):
        top = by_regime[regime].most_common(2)
        tops = ", ".join(f"{label_for(b)}({c})" for b, c in top)
        print(f"    {regime:<20}  {tops}")


# -- CLI -----------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Audit trail décisionnel — RejectionStore reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--date", default=str(date.today()), help="Date YYYY-MM-DD (défaut: aujourd'hui)")
    p.add_argument("--file", help="Chemin explicite vers le fichier JSONL")
    p.add_argument("--symbol", help="Filtrer par symbole (ex: SLX ou SLX/USDT)")
    p.add_argument("--cycle", type=int, help="Filtrer par numéro de cycle")
    p.add_argument("--summary", action="store_true", help="Résumé tabulaire seulement (pas de trace détaillée)")
    p.add_argument("--stats", action="store_true", help="Stats bloqueurs uniquement")
    p.add_argument("--limit", type=int, default=20, help="Nombre max d'entrées détaillées (défaut: 20)")
    args = p.parse_args()

    jsonl_path = Path(args.file) if args.file else None
    day = date.fromisoformat(args.date) if not args.file else None

    print(f"\nLecture : {jsonl_path or _service.path_for_date(day)}")

    sym_filter = args.symbol
    if sym_filter and "/" not in sym_filter:
        sym_filter = sym_filter.upper()

    entries = _service.load_entries(day=day, file=jsonl_path, symbol=sym_filter, cycle=args.cycle)

    if not entries:
        print("Aucune entrée correspondant aux filtres.")
        return

    print(f"{len(entries)} entrée(s) chargée(s).")

    if args.stats:
        print_blocker_stats(entries)
        return

    if args.summary:
        print_summary_table(entries)
        return

    # Affichage détaillé limité + résumé
    to_show = entries[:args.limit]
    for e in to_show:
        print_trace(_service.build_trace(e))

    if len(entries) > args.limit:
        print(f"\n{_DIM}[{len(entries) - args.limit} entrées supplémentaires — utilisez --limit N pour en voir plus]{_RESET}")

    print_summary_table(entries)


if __name__ == "__main__":
    main()
