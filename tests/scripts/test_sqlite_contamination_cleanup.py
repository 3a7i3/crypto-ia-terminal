from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.sqlite_contamination_cleanup import main


def _create_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                ts REAL,
                symbol TEXT,
                status TEXT,
                price REAL,
                error TEXT,
                mode TEXT,
                action TEXT,
                size REAL,
                notional REAL,
                order_id TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO trades (id, ts, symbol, status, price, error, mode, action, size, notional, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1780047308.0, "BTC/USDT", "ok", None, None, "paper", "BUY", 1.0, None, None),
                (2, 1780047309.0, "BTC/USDT", "rejected", None, "Order size $500.00 exceeds limit $100.00", "paper", "BUY", 500.0, None, None),
                (3, 1780047310.0, "ETH/USDT", "ok", None, None, "paper", "BUY", 1.0, None, None),
            ],
        )
        conn.commit()


def _create_review_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "timestamp", "symbol", "status", "price", "error", "rule", "severity"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "id": 1,
                    "timestamp": 1780047308.0,
                    "symbol": "BTC/USDT",
                    "status": "ok",
                    "price": "",
                    "error": "",
                    "rule": "HIGH_NO_PRICE_OK",
                    "severity": "HIGH",
                },
                {
                    "id": 2,
                    "timestamp": 1780047309.0,
                    "symbol": "BTC/USDT",
                    "status": "rejected",
                    "price": "",
                    "error": "Order size $500.00 exceeds limit $100.00",
                    "rule": "CRITICAL_I12",
                    "severity": "CRITICAL",
                },
                {
                    "id": 3,
                    "timestamp": 1780047310.0,
                    "symbol": "ETH/USDT",
                    "status": "ok",
                    "price": "",
                    "error": "",
                    "rule": "HIGH_NO_PRICE_OK",
                    "severity": "HIGH",
                },
            ]
        )


def test_cleanup_dry_run_keeps_database(tmp_path: Path) -> None:
    db_path = tmp_path / "trade_log.sqlite"
    review_csv = tmp_path / "reports" / "trade_log_review.csv"
    backup_dir = tmp_path / "reports"
    post_audit = tmp_path / "trade_log_audit_post_cleanup.md"
    _create_db(db_path)
    _create_review_csv(review_csv)

    result = main(
        [
            str(db_path),
            "--review-csv",
            str(review_csv),
            "--backup-dir",
            str(backup_dir),
            "--post-audit-markdown",
            str(post_audit),
            "--expected-ids",
            "3",
        ]
    )

    assert result == 0
    backups = list(backup_dir.glob("trade_log_backup_*.sqlite"))
    assert len(backups) == 1
    assert not post_audit.exists()

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert remaining == 3


def test_cleanup_confirm_deletes_and_reaudits(tmp_path: Path) -> None:
    db_path = tmp_path / "trade_log.sqlite"
    review_csv = tmp_path / "reports" / "trade_log_review.csv"
    backup_dir = tmp_path / "reports"
    post_audit = tmp_path / "trade_log_audit_post_cleanup.md"
    manifest = tmp_path / "reports" / "manifest.json"
    _create_db(db_path)
    _create_review_csv(review_csv)

    result = main(
        [
            str(db_path),
            "--review-csv",
            str(review_csv),
            "--backup-dir",
            str(backup_dir),
            "--post-audit-markdown",
            str(post_audit),
            "--manifest",
            str(manifest),
            "--expected-ids",
            "3",
            "--confirm",
        ]
    )

    assert result == 0
    assert post_audit.exists()
    assert manifest.exists()

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert remaining == 0

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["deleted_rows"] == 3
    assert payload["reaudit"]["critical"] == 0
    assert payload["reaudit"]["high"] == 0
    assert payload["reaudit"]["union"] == 0


def test_cleanup_aborts_on_rule_drift(tmp_path: Path) -> None:
    db_path = tmp_path / "trade_log.sqlite"
    review_csv = tmp_path / "reports" / "trade_log_review.csv"
    backup_dir = tmp_path / "reports"
    _create_db(db_path)
    _create_review_csv(review_csv)

    with review_csv.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([99, 1780047999.0, "BTC/USDT", "ok", "", "", "HIGH_NO_PRICE_OK", "HIGH"])

    result = main(
        [
            str(db_path),
            "--review-csv",
            str(review_csv),
            "--backup-dir",
            str(backup_dir),
            "--expected-ids",
            "3",
        ]
    )

    assert result == 1
    assert not list(backup_dir.glob("trade_log_backup_*.sqlite"))
