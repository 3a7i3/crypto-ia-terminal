#!/usr/bin/env python3
"""
sqlite_contamination_audit.py — Audit LECTURE SEULE de databases/trade_log.sqlite

Sprint S4-B (Tickets A+B). Aucune écriture, aucune modification :
la base est ouverte en mode read-only via l'URI sqlite `mode=ro`.

Produit :
  1. Observations générales (Ticket A) : volumes, plage temporelle,
     répartition mode/status, symboles.
  2. Détection de contamination (Ticket B) : chaque heuristique est
     classée CRITICAL / HIGH / MEDIUM / INFO, avec les ids concernés.
  3. Conclusion PASS / FAIL + rapport markdown optionnel.

Signatures de test établies EMPIRIQUEMENT (exécution de tests/test_invariants.py
sur base vierge, S4-B) :
  - price IS NULL sur des lignes status='ok' (I01 auto-heal, sans prix)
  - error LIKE '%exceeds limit $100%'  (limite de test I12)
  - tailles rondes exactes 1.0 / 500.0 sur paires BTC/ETH quasi simultanées

Usage :
  python scripts/sqlite_contamination_audit.py [chemin/vers/trade_log.sqlite]
  python scripts/sqlite_contamination_audit.py --markdown trade_log_audit.md
Exit code : 0 = PASS, 1 = FAIL (suspects détectés), 2 = erreur d'accès.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = "databases/trade_log.sqlite"

# ── Heuristiques de contamination ─────────────────────────────────────────────
# (sévérité, étiquette, requête SQL retournant les ids suspects)
HEURISTICS: list[tuple[str, str, str]] = [
    (
        "CRITICAL",
        "message d'erreur de test I12 (limite $100)",
        "SELECT id FROM trades WHERE error LIKE '%exceeds limit $100%'",
    ),
    (
        "CRITICAL",
        "symbole explicitement factice (TEST/FAKE/DUMMY/MOCK)",
        "SELECT id FROM trades WHERE UPPER(symbol) LIKE '%TEST%' "
        "OR UPPER(symbol) LIKE '%FAKE%' OR UPPER(symbol) LIKE '%DUMMY%' "
        "OR UPPER(symbol) LIKE '%MOCK%'",
    ),
    (
        "HIGH",
        "trade 'ok' sans prix (signature I01 auto-heal)",
        "SELECT id FROM trades WHERE price IS NULL AND status = 'ok'",
    ),
    (
        "HIGH",
        "prix exactement 100.0 (valeur de test canonique)",
        "SELECT id FROM trades WHERE price = 100.0",
    ),
    (
        "HIGH",
        "timestamp impossible (avant 2020 ou dans le futur)",
        "SELECT id FROM trades WHERE ts < 1577836800 "
        "OR ts > strftime('%s','now') + 86400",
    ),
    (
        "MEDIUM",
        "taille ronde de test (exactement 1.0 ou 500.0)",
        "SELECT id FROM trades WHERE size IN (1.0, 500.0)",
    ),
    (
        "MEDIUM",
        "doublon strict (symbol, action, size, price, ts identiques)",
        "SELECT id FROM trades WHERE (symbol, action, size, "
        "COALESCE(price,-1), ts) IN (SELECT symbol, action, size, "
        "COALESCE(price,-1), ts FROM trades GROUP BY symbol, action, size, "
        "COALESCE(price,-1), ts HAVING COUNT(*) > 1)",
    ),
    (
        "MEDIUM",
        "rafale non humaine (>5 trades dans la même seconde)",
        "SELECT id FROM trades WHERE CAST(ts AS INTEGER) IN ("
        "SELECT CAST(ts AS INTEGER) FROM trades "
        "GROUP BY CAST(ts AS INTEGER) HAVING COUNT(*) > 5)",
    ),
    (
        "INFO",
        "notional NULL (champ jamais rempli par le flux réel ?)",
        "SELECT id FROM trades WHERE notional IS NULL",
    ),
    (
        "INFO",
        "order_id NULL",
        "SELECT id FROM trades WHERE order_id IS NULL",
    ),
]

# Sévérités qui font échouer l'audit
FAILING = {"CRITICAL", "HIGH"}


def fmt_ts(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Connexion strictement lecture seule (mode=ro, immutable off)."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", nargs="?", default=DEFAULT_DB)
    ap.add_argument(
        "--markdown",
        metavar="FICHIER",
        help="écrit aussi le rapport en markdown (ex: trade_log_audit.md)",
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERREUR: base introuvable: {db_path}", file=sys.stderr)
        return 2

    lines: list[str] = []
    out = lines.append

    out("=" * 62)
    out("SQLITE AUDIT — trade_log.sqlite (LECTURE SEULE)")
    out(f"Base   : {db_path}")
    out(f"Généré : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    out("=" * 62)

    try:
        conn = open_readonly(db_path)
    except sqlite3.Error as exc:
        print(f"ERREUR: ouverture read-only impossible: {exc}", file=sys.stderr)
        return 2

    with conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        out(f"\nTables : {', '.join(tables) or '(aucune)'}")
        if "trades" not in tables:
            out("\nCONCLUSION: FAIL — table 'trades' absente.")
            print("\n".join(lines))
            return 1

        # ── Ticket A — Observations ──────────────────────────────────────
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        ts_min, ts_max = conn.execute("SELECT MIN(ts), MAX(ts) FROM trades").fetchone()
        out("\n── Observations ─────────────────────────────────────────")
        out(f"Trades total ....... {total}")
        out(f"Premier ............ {fmt_ts(ts_min)}")
        out(f"Dernier ............ {fmt_ts(ts_max)}")

        for col in ("mode", "status", "action"):
            counts = Counter(
                dict(conn.execute(f"SELECT {col}, COUNT(*) FROM trades GROUP BY {col}"))
            )
            pretty = ", ".join(f"{k or '∅'}={v}" for k, v in counts.most_common())
            out(f"Répartition {col:<7}: {pretty or '—'}")

        symbols = [
            f"{s}({n})"
            for s, n in conn.execute(
                "SELECT symbol, COUNT(*) FROM trades "
                "GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 15"
            )
        ]
        out(f"Symboles (top 15) .. {', '.join(symbols) or '—'}")

        # ── Ticket B — Détection ─────────────────────────────────────────
        out("\n── Détection de contamination ───────────────────────────")
        suspect_ids: set[int] = set()
        fail = False
        for severity, label, sql in HEURISTICS:
            ids = [r[0] for r in conn.execute(sql)]
            if not ids:
                continue
            if severity in FAILING:
                suspect_ids.update(ids)
                fail = True
            shown = ", ".join(map(str, ids[:12])) + (
                f" … (+{len(ids) - 12})" if len(ids) > 12 else ""
            )
            out(f"[{severity:<8}] {len(ids):>5}  {label}")
            out(f"            ids: {shown}")

        if not fail and not suspect_ids:
            out("(aucune heuristique CRITICAL/HIGH déclenchée)")

        # ── Conclusion ───────────────────────────────────────────────────
        authentic = total - len(suspect_ids)
        out("\n── Conclusion ───────────────────────────────────────────")
        out(f"Trades total ....... {total}")
        out(f"Authentiques ....... {authentic}")
        out(f"Suspects (C/H) ..... {len(suspect_ids)}")
        out(f"\nRÉSULTAT : {'FAIL' if fail else 'PASS'}")
        if fail:
            out(
                "\nProchaine étape (Ticket C) : validation humaine des ids "
                "listés,\npuis backup SHA256 → suppression ciblée → "
                "re-audit → rapport."
            )

    report = "\n".join(lines)
    print(report)

    if args.markdown:
        md = Path(args.markdown)
        md.write_text(
            "# Audit trade_log.sqlite\n\n```\n" + report + "\n```\n",
            encoding="utf-8",
        )
        print(f"\nRapport markdown écrit : {md}")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
