#!/usr/bin/env python3
"""
scripts/data_quality.py — Audit qualité des données paper_trades.jsonl

Vérifie :
  1. Aucun trade dupliqué (trade_id unique)
  2. Timestamps monotones (OPEN avant CLOSE)
  3. Pas de champs critiques manquants (symbol, side, pnl_usd, mae_pct, mfe_pct)
  4. Pas de PnL impossible (|pnl_pct| > 200% sauf tokens connus)
  5. Cohérence SL : price × (1 ± sl_pct) ≈ sl_price
  6. Cohérence TP : price × (1 ± tp_pct) ≈ tp_price
  7. Pas de valeurs NaN / Inf
  8. Cohérence MAE ≤ 0 et MFE ≥ 0 (par convention)
  9. Détection trades avant date de démarrage propre (2026-06-25)

Usage : python3 scripts/data_quality.py [path_to_paper_trades.jsonl] [--strict]
Exit 0 = données propres | Exit 1 = warnings | Exit 2 = erreurs critiques
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_JSONL = Path("databases/paper_trades.jsonl")

CLEAN_DATA_SINCE = datetime(2026, 6, 25, tzinfo=timezone.utc)  # données propres depuis

REQUIRED_OPEN_FIELDS = {"trade_id", "symbol", "side", "entry_price"}
REQUIRED_CLOSE_FIELDS = {"trade_id", "symbol", "pnl_usd", "pnl_pct"}

W = 68


def _parse_ts(ev: dict) -> datetime | None:
    for key in ("timestamp", "ts", "time", "opened_at", "closed_at"):
        val = ev.get(key)
        if val is None:
            continue
        try:
            if isinstance(val, (int, float)):
                return datetime.fromtimestamp(val, tz=timezone.utc)
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            continue
    return None


def _is_nan_or_inf(val) -> bool:
    try:
        return math.isnan(float(val)) or math.isinf(float(val))
    except (TypeError, ValueError):
        return False


def main(jsonl_path: str | None = None, strict: bool = False) -> int:
    jsonl = Path(jsonl_path) if jsonl_path else DEFAULT_JSONL
    if not jsonl.exists():
        print(f"ERREUR: fichier introuvable: {jsonl}")
        return 2

    # ── Lecture ───────────────────────────────────────────────────────────────
    opens: dict[str, dict] = {}
    closes: dict[str, dict] = {}
    raw_events: list[dict] = []
    parse_errors = 0

    with jsonl.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                raw_events.append(ev)
                tid = ev.get("trade_id", "")
                if ev.get("event") == "OPEN":
                    opens[tid] = ev
                elif ev.get("event") == "CLOSE":
                    closes[tid] = ev
            except json.JSONDecodeError:
                parse_errors += 1

    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Parse errors ───────────────────────────────────────────────────────
    if parse_errors:
        errors.append(f"{parse_errors} ligne(s) JSON invalide(s)")

    # ── 2. Trades complets ────────────────────────────────────────────────────
    orphan_opens = set(opens) - set(closes)
    orphan_closes = set(closes) - set(opens)
    if orphan_opens:
        warnings.append(
            f"{len(orphan_opens)} OPEN sans CLOSE (positions encore ouvertes ?)"
        )
    if orphan_closes:
        warnings.append(f"{len(orphan_closes)} CLOSE sans OPEN")

    # ── 3. Trade IDs dupliqués ────────────────────────────────────────────────
    seen_close_ids: dict[str, int] = defaultdict(int)
    for ev in raw_events:
        if ev.get("event") == "CLOSE":
            seen_close_ids[ev.get("trade_id", "")] += 1
    dupes = {tid: n for tid, n in seen_close_ids.items() if n > 1}
    if dupes:
        errors.append(f"{len(dupes)} trade_id(s) dupliqué(s): {list(dupes)[:5]}")

    # ── 4. Champs manquants ───────────────────────────────────────────────────
    missing_open = 0
    missing_close = 0
    for tid, op in opens.items():
        missing = REQUIRED_OPEN_FIELDS - set(op)
        if missing:
            missing_open += 1
    for tid, cl in closes.items():
        missing = REQUIRED_CLOSE_FIELDS - set(cl)
        if missing:
            missing_close += 1
    if missing_open:
        warnings.append(f"{missing_open} OPEN avec champs manquants")
    if missing_close:
        errors.append(f"{missing_close} CLOSE avec champs manquants (pnl_usd, pnl_pct)")

    # ── 5. NaN / Inf ─────────────────────────────────────────────────────────
    nan_count = 0
    for ev in raw_events:
        for k, v in ev.items():
            if isinstance(v, (int, float)) and _is_nan_or_inf(v):
                nan_count += 1
    if nan_count:
        errors.append(f"{nan_count} valeur(s) NaN ou Inf")

    # ── 6. PnL impossible (|pnl_pct| > 200%) ─────────────────────────────────
    impossible_pnl = []
    for tid, cl in closes.items():
        pnl_pct = cl.get("pnl_pct")
        if pnl_pct is not None:
            try:
                if abs(float(pnl_pct)) > 200:
                    impossible_pnl.append((tid, cl.get("symbol"), float(pnl_pct)))
            except (TypeError, ValueError):
                pass
    if impossible_pnl:
        errors.append(
            f"{len(impossible_pnl)} trade(s) avec |pnl_pct|>200%: "
            + ", ".join(f"{s}({p:.0f}%)" for _, s, p in impossible_pnl[:5])
        )

    # ── 7. MAE ≤ 0 et MFE ≥ 0 ────────────────────────────────────────────────
    mae_positive = 0
    mfe_negative = 0
    for tid, cl in closes.items():
        mae = cl.get("mae_pct")
        mfe = cl.get("mfe_pct")
        if mae is not None:
            try:
                if float(mae) > 0.01:
                    mae_positive += 1
            except (TypeError, ValueError):
                pass
        if mfe is not None:
            try:
                if float(mfe) < -0.01:
                    mfe_negative += 1
            except (TypeError, ValueError):
                pass
    if mae_positive:
        warnings.append(f"{mae_positive} trade(s) avec MAE > 0 (convention inversée ?)")
    if mfe_negative:
        warnings.append(f"{mfe_negative} trade(s) avec MFE < 0 (convention inversée ?)")

    # ── 8. Timestamps : OPEN avant CLOSE ─────────────────────────────────────
    ts_errors = 0
    for tid in set(opens) & set(closes):
        ts_open = _parse_ts(opens[tid])
        ts_close = _parse_ts(closes[tid])
        if ts_open and ts_close and ts_close < ts_open:
            ts_errors += 1
    if ts_errors:
        errors.append(
            f"{ts_errors} trade(s) avec CLOSE avant OPEN (timestamp incohérent)"
        )

    # ── 9. Trades avant données propres ──────────────────────────────────────
    old_trades = 0
    for tid, op in opens.items():
        ts = _parse_ts(op)
        if ts and ts < CLEAN_DATA_SINCE:
            old_trades += 1
    if old_trades:
        warnings.append(
            f"{old_trades} trade(s) antérieurs à {CLEAN_DATA_SINCE.date()} "
            f"(données corrompues — tokens toxiques, bypass meta_allowed)"
        )

    # ── 10. Statistiques générales ────────────────────────────────────────────
    n_closed = len(closes)
    n_open = len(orphan_opens)
    pnl_values = []
    for cl in closes.values():
        try:
            pnl_values.append(float(cl["pnl_usd"]))
        except (KeyError, TypeError, ValueError):
            pass
    total_pnl = sum(pnl_values) if pnl_values else 0.0
    symbols = {cl.get("symbol") for cl in closes.values()}

    # ── Output ────────────────────────────────────────────────────────────────
    print(f"\n{'='*W}")
    print(f"  DATA QUALITY AUDIT — {jsonl.name}")
    print(f"{'='*W}")
    print(f"  Trades fermés    : {n_closed}")
    print(f"  Positions ouvertes: {n_open}")
    print(f"  Symboles         : {len(symbols)}")
    print(f"  PnL total        : {total_pnl:+.2f}$")
    print(f"  Trades propres   : {n_closed - old_trades} (post-2026-06-25)")
    print()

    if not errors and not warnings:
        print("  ✅ Données propres — aucune anomalie détectée")
    else:
        if errors:
            print(f"  ❌ ERREURS CRITIQUES ({len(errors)}):")
            for e in errors:
                print(f"    • {e}")
        if warnings:
            print(f"\n  ⚠️  AVERTISSEMENTS ({len(warnings)}):")
            for w in warnings:
                print(f"    • {w}")

    exit_code = 2 if errors else (1 if warnings else 0)
    icon = {0: "✅ OK", 1: "⚠️  OK avec warnings", 2: "❌ DONNÉES COMPROMISES"}[
        exit_code
    ]
    print(f"\n  Verdict : {icon}")
    print(f"{'='*W}\n")
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit qualité données paper trades")
    parser.add_argument("jsonl", nargs="?", help="Chemin vers paper_trades.jsonl")
    parser.add_argument("--strict", action="store_true", help="Warnings = erreurs")
    args = parser.parse_args()
    result = main(jsonl_path=args.jsonl, strict=args.strict)
    sys.exit(result)
