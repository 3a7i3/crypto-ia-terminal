#!/usr/bin/env python3
"""
sqlite_contamination_cleanup.py - Ticket C (cleanup tracable et reproductible).

Sequence:
1. Preconditions en lecture seule
2. BEGIN IMMEDIATE + backup cible des ids candidats
3. Point d'arret sans DELETE (par defaut)
4. DELETE uniquement avec --confirm
5. COMMIT puis VACUUM
6. Re-audit automatique avec les memes regles que sqlite_contamination_audit.py
7. Manifeste JSON de l'operation
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

DEFAULT_DB = Path("databases/trade_log.sqlite")
DEFAULT_REVIEW_CSV = Path("reports/trade_log_review_171.csv")
DEFAULT_BACKUP_DIR = Path("reports")
DEFAULT_POST_AUDIT_MD = Path("trade_log_audit_post_cleanup.md")
EXPECTED_IDS = 171
RULE_CRITICAL = "CRITICAL_I12"
RULE_HIGH = "HIGH_NO_PRICE_OK"
RULE_SQL = {
    RULE_CRITICAL: "SELECT id FROM trades WHERE error LIKE '%exceeds limit $100%'",
    RULE_HIGH: "SELECT id FROM trades WHERE price IS NULL AND status = 'ok'",
}


class CleanupError(RuntimeError):
    """Erreur metier pour arreter proprement le cleanup."""


@dataclass(frozen=True)
class CandidateSet:
    ids: tuple[int, ...]
    critical_ids: frozenset[int]
    high_ids: frozenset[int]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_audit_module() -> ModuleType:
    audit_path = Path(__file__).resolve().with_name("sqlite_contamination_audit.py")
    spec = importlib.util.spec_from_file_location("sqlite_contamination_audit_module", audit_path)
    if spec is None or spec.loader is None:
        raise CleanupError(f"Impossible de charger le module d'audit: {audit_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_audit_rules() -> tuple[list[tuple[str, str, str]], set[str], Path]:
    module = _load_audit_module()
    heuristics = getattr(module, "HEURISTICS", None)
    failing = getattr(module, "FAILING", None)
    if not isinstance(heuristics, list) or not isinstance(failing, set):
        raise CleanupError("HEURISTICS/FAILING introuvables dans sqlite_contamination_audit.py")
    audit_path = Path(module.__file__ or "").resolve()
    return heuristics, failing, audit_path


def load_candidates(review_csv: Path, expected_ids: int) -> CandidateSet:
    if not review_csv.exists():
        raise CleanupError(f"CSV introuvable: {review_csv}")

    with review_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        required_fields = {"id", "rule"}
        if not required_fields.issubset(fieldnames):
            raise CleanupError(
                f"CSV invalide: colonnes attendues {sorted(required_fields)}, trouvees {sorted(fieldnames)}"
            )

        all_ids: set[int] = set()
        critical_ids: set[int] = set()
        high_ids: set[int] = set()
        rules_found: set[str] = set()

        for row in reader:
            raw_id = (row.get("id") or "").strip()
            raw_rule = (row.get("rule") or "").strip()
            if not raw_id or not raw_rule:
                raise CleanupError("CSV invalide: ligne avec id/rule vide")

            try:
                trade_id = int(raw_id)
            except ValueError as exc:
                raise CleanupError(f"CSV invalide: id non entier '{raw_id}'") from exc

            if raw_rule not in RULE_SQL:
                raise CleanupError(f"Regle inattendue dans le CSV: {raw_rule}")

            all_ids.add(trade_id)
            rules_found.add(raw_rule)
            if raw_rule == RULE_CRITICAL:
                critical_ids.add(trade_id)
            else:
                high_ids.add(trade_id)

    if len(all_ids) != expected_ids:
        raise CleanupError(
            f"Precondition echouee: {len(all_ids)} ids uniques trouves (attendu: {expected_ids})"
        )

    missing_rules = set(RULE_SQL) - rules_found
    if missing_rules:
        raise CleanupError(f"Precondition echouee: regles manquantes dans le CSV: {sorted(missing_rules)}")

    overlap = critical_ids & high_ids
    if overlap:
        shown = ", ".join(str(x) for x in sorted(overlap)[:10])
        suffix = " ..." if len(overlap) > 10 else ""
        raise CleanupError(
            "Precondition echouee: intersection CRITICAL_I12/HIGH_NO_PRICE_OK non vide: "
            f"{shown}{suffix}"
        )

    return CandidateSet(
        ids=tuple(sorted(all_ids)),
        critical_ids=frozenset(critical_ids),
        high_ids=frozenset(high_ids),
    )


def _placeholders(size: int) -> str:
    return ",".join("?" for _ in range(size))


def _fetch_id_set(conn: sqlite3.Connection, sql: str) -> set[int]:
    return {int(row[0]) for row in conn.execute(sql)}


def validate_db_state(
    conn: sqlite3.Connection,
    candidates: CandidateSet,
    heuristics: list[tuple[str, str, str]],
    failing: set[str],
) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if "trades" not in tables:
        raise CleanupError("Table 'trades' absente de la base")

    db_critical = _fetch_id_set(conn, RULE_SQL[RULE_CRITICAL])
    db_high = _fetch_id_set(conn, RULE_SQL[RULE_HIGH])
    overlap = db_critical & db_high
    if overlap:
        shown = ", ".join(str(x) for x in sorted(overlap)[:10])
        suffix = " ..." if len(overlap) > 10 else ""
        raise CleanupError(f"Intersection en base entre {RULE_CRITICAL}/{RULE_HIGH}: {shown}{suffix}")

    if db_critical != set(candidates.critical_ids):
        raise CleanupError(
            f"Derive detectee: ids {RULE_CRITICAL} en base ({len(db_critical)}) "
            f"!= CSV ({len(candidates.critical_ids)})"
        )
    if db_high != set(candidates.high_ids):
        raise CleanupError(
            f"Derive detectee: ids {RULE_HIGH} en base ({len(db_high)}) "
            f"!= CSV ({len(candidates.high_ids)})"
        )

    failing_union: set[int] = set()
    for severity, _label, sql in heuristics:
        if severity in failing:
            failing_union.update(_fetch_id_set(conn, sql))

    if failing_union != set(candidates.ids):
        raise CleanupError(
            f"Derive detectee: union CRITICAL/HIGH en base ({len(failing_union)}) "
            f"!= CSV ({len(candidates.ids)})"
        )


def backup_candidates(
    conn: sqlite3.Connection,
    backup_path: Path,
    candidate_ids: tuple[int, ...],
    expected_ids: int,
) -> int:
    if backup_path.exists():
        raise CleanupError(f"Backup deja existant: {backup_path}")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    placeholders = _placeholders(len(candidate_ids))
    params = tuple(candidate_ids)

    in_db = conn.execute(
        f"SELECT COUNT(*) FROM trades WHERE id IN ({placeholders})",
        params,
    ).fetchone()[0]
    if in_db != expected_ids:
        raise CleanupError(
            f"Precondition DB echouee: {in_db} lignes candidates presentes (attendu: {expected_ids})"
        )

    create_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='trades'"
    ).fetchone()
    if not create_sql_row or not create_sql_row[0]:
        raise CleanupError("Definition SQL de la table trades indisponible")
    create_sql = str(create_sql_row[0])

    columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(trades)")]
    if not columns:
        raise CleanupError("Schema de la table trades illisible")

    quoted_cols = ", ".join(f'"{column}"' for column in columns)
    rows = conn.execute(
        f"SELECT {quoted_cols} FROM trades WHERE id IN ({placeholders}) ORDER BY id",
        params,
    ).fetchall()

    with sqlite3.connect(str(backup_path), timeout=30) as backup_conn:
        backup_conn.execute(create_sql)
        backup_conn.executemany(
            f"INSERT INTO trades ({quoted_cols}) VALUES ({_placeholders(len(columns))})",
            rows,
        )
        backup_conn.commit()
        saved = backup_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    return int(saved)


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_post_audit(
    audit_script: Path,
    db_path: Path,
    markdown_path: Path,
    heuristics: list[tuple[str, str, str]],
    failing: set[str],
) -> dict[str, object]:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(audit_script), str(db_path), "--markdown", str(markdown_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        stderr = (result.stderr or result.stdout).strip()
        raise CleanupError(f"Echec du re-audit: {stderr or 'sortie vide'}")

    uri = f"file:{db_path.as_posix()}?mode=ro"
    critical_ids: set[int] = set()
    high_ids: set[int] = set()
    findings: list[dict[str, object]] = []
    with sqlite3.connect(uri, uri=True, timeout=30) as conn:
        for severity, label, sql in heuristics:
            if severity not in failing:
                continue
            ids = _fetch_id_set(conn, sql)
            if not ids:
                continue
            findings.append(
                {
                    "severity": severity,
                    "label": label,
                    "count": len(ids),
                    "ids_sample": sorted(ids)[:12],
                }
            )
            if severity == "CRITICAL":
                critical_ids.update(ids)
            elif severity == "HIGH":
                high_ids.update(ids)

    union_ids = critical_ids | high_ids
    return {
        "critical": len(critical_ids),
        "high": len(high_ids),
        "union": len(union_ids),
        "pass": len(union_ids) == 0,
        "findings": findings,
        "audit_exit_code": result.returncode,
    }


def rollback_if_needed(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_slug() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", nargs="?", default=str(DEFAULT_DB))
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW_CSV))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--post-audit-markdown", default=str(DEFAULT_POST_AUDIT_MD))
    parser.add_argument("--manifest", help="chemin explicite du manifeste JSON")
    parser.add_argument("--confirm", action="store_true", help="autorise le DELETE puis le COMMIT")
    parser.add_argument("--expected-ids", type=int, default=EXPECTED_IDS)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    review_csv = Path(args.review_csv)
    backup_dir = Path(args.backup_dir)
    post_audit_markdown = Path(args.post_audit_markdown)

    if not db_path.exists():
        print(f"ERREUR: base introuvable: {db_path}", file=sys.stderr)
        return 2

    try:
        heuristics, failing, audit_script = load_audit_rules()
        candidates = load_candidates(review_csv, expected_ids=args.expected_ids)
        db_sha_before = sha256_file(db_path)
    except (CleanupError, OSError) as exc:
        print(f"ERREUR preconditions: {exc}", file=sys.stderr)
        return 1

    slug = timestamp_slug()
    backup_path = backup_dir / f"trade_log_backup_{slug}.sqlite"
    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else backup_dir / f"trade_log_cleanup_manifest_{slug}.json"
    )

    backup_sha = ""
    backup_size = 0
    deleted_rows = 0
    db_sha_after = db_sha_before
    reaudit: dict[str, object] | None = None
    vacuum_error: str | None = None
    reaudit_error: str | None = None

    try:
        with sqlite3.connect(str(db_path), timeout=30, isolation_level=None) as conn:
            validate_db_state(conn, candidates, heuristics, failing)
            conn.execute("BEGIN IMMEDIATE")
            try:
                saved = backup_candidates(conn, backup_path, candidates.ids, args.expected_ids)
                if saved != args.expected_ids:
                    raise CleanupError(
                        f"Backup incomplet: {saved} lignes sauvegardees (attendu: {args.expected_ids})"
                    )
            except (CleanupError, OSError, sqlite3.Error):
                rollback_if_needed(conn)
                raise

            backup_sha = sha256_file(backup_path)
            backup_size = backup_path.stat().st_size

            print("=== Ticket C - Point d'arret avant suppression ===")
            print(f"candidats............... {len(candidates.ids)}")
            print(f"backup.................. {backup_path}")
            print(f"backup sha256........... {backup_sha}")
            print(f"backup size (bytes)..... {backup_size}")

            if not args.confirm:
                rollback_if_needed(conn)
                print("\nAucun DELETE execute. Relancer avec --confirm pour appliquer la suppression.")
                return 0

            cursor = conn.execute(
                f"DELETE FROM trades WHERE id IN ({_placeholders(len(candidates.ids))})",
                tuple(candidates.ids),
            )
            deleted_rows = int(cursor.rowcount)
            if deleted_rows != args.expected_ids:
                raise CleanupError(
                    f"DELETE incomplet: {deleted_rows} lignes supprimees (attendu: {args.expected_ids})"
                )

            conn.execute("COMMIT")
    except (CleanupError, OSError, sqlite3.Error) as exc:
        print(f"ERREUR cleanup: {exc}", file=sys.stderr)
        return 1

    try:
        with sqlite3.connect(str(db_path), timeout=30, isolation_level=None) as conn:
            conn.execute("VACUUM")
    except sqlite3.Error as exc:
        vacuum_error = str(exc)

    db_sha_after = sha256_file(db_path)
    try:
        reaudit = run_post_audit(
            audit_script=audit_script,
            db_path=db_path,
            markdown_path=post_audit_markdown,
            heuristics=heuristics,
            failing=failing,
        )
    except (CleanupError, OSError, sqlite3.Error) as exc:
        reaudit_error = str(exc)

    manifest = {
        "timestamp_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "db_path": str(db_path),
        "review_csv": str(review_csv),
        "candidate_count": len(candidates.ids),
        "db_sha256_before": db_sha_before,
        "backup_path": str(backup_path),
        "backup_sha256": backup_sha,
        "backup_size_bytes": backup_size,
        "deleted_rows": deleted_rows,
        "db_sha256_after": db_sha_after,
        "post_audit_markdown": str(post_audit_markdown),
        "reaudit": reaudit,
        "reaudit_error": reaudit_error,
        "vacuum_error": vacuum_error,
    }
    write_manifest(manifest_path, manifest)

    print("\n=== Ticket C - Execution confirmee ===")
    print(f"supprimees.............. {deleted_rows}")
    print(f"db sha256 avant......... {db_sha_before}")
    print(f"db sha256 apres......... {db_sha_after}")
    if reaudit is not None:
        print(f"re-audit CRITICAL....... {reaudit['critical']}")
        print(f"re-audit HIGH........... {reaudit['high']}")
        print(f"re-audit union.......... {reaudit['union']}")
    else:
        print("re-audit................ ECHEC")
    print(f"rapport post-cleanup.... {post_audit_markdown}")
    print(f"manifeste............... {manifest_path}")
    if vacuum_error:
        print(f"vacuum error............ {vacuum_error}")
        return 1
    if reaudit_error:
        print(f"re-audit error.......... {reaudit_error}")
        return 1
    return 0 if reaudit is not None and bool(reaudit["pass"]) else 1


if __name__ == "__main__":
    sys.exit(main())
