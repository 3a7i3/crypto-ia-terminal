#!/usr/bin/env python3
"""
PREUVE — audit 2026-09-24, anomalie A-02.

Montre que `paper_trading.dataset_validator.validate_corpus()` classe un CLOSE
dont `pnl_usd` est UNKNOWN (`None`) comme une PERTE, en contradiction avec la
doctrine REM-C R1.1 documentée dans `paper_trading/recorder.py:495-499`
(« pnl_usd=None … must NOT be coerced into a LOSS »).

Le script est en LECTURE SEULE vis-à-vis du dépôt et du runtime : il écrit un
corpus synthétique dans un répertoire temporaire, n'ouvre aucun store PPL,
n'appelle aucun chemin de mutation PAPER et ne touche pas au VPS.

Exécution :
    python docs/audit/evidence/2026-09-24_unknown_pnl_repro.py

Sortie observée sur main@98082ef (Python 3.11.15) :
    paired_trades : 3
    win_count     : 1
    loss_count    : 2      <-- l'UNKNOWN est compté comme perte
    win_rate      : 0.3333333333333333   (attendu : 0.5 sur 1W/1L certifiables)
    violations    : []
    warnings      : []
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from paper_trading.dataset_validator import validate_corpus  # noqa: E402

# 3 trades appairés : 1 gain évidencé, 1 perte évidencée, 1 PnL inconnu (None).
SPECS = [
    ("T1", 2.0, "take_profit"),
    ("T2", -1.0, "stop_loss"),
    ("T3", None, "expired_unknown"),
]


def build_corpus(path: Path) -> None:
    ts = 1789000000.0
    rows = []
    for trade_id, pnl, reason in SPECS:
        rows.append(
            dict(
                event="OPEN", trade_id=trade_id, ts=ts, ts_iso="2026-09-01T00:00:00Z",
                symbol="BTC/USDT", side="buy", price=100.0, size_usd=10.0,
                mode="paper", schema_version=5,
            )
        )
        rows.append(
            dict(
                event="CLOSE", trade_id=trade_id, ts=ts + 600, ts_iso="2026-09-01T00:10:00Z",
                symbol="BTC/USDT", side="buy", price=None, size_usd=10.0,
                mode="paper", schema_version=5, exit_price=None,
                pnl_usd=pnl, pnl_pct=None, reason=reason, duration_s=600.0,
            )
        )
        ts += 3600
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main() -> int:
    log_path = Path(tempfile.mkdtemp(prefix="audit_unknown_pnl_")) / "paper_trades.jsonl"
    build_corpus(log_path)
    report = validate_corpus(log_path=str(log_path))
    print("paired_trades :", report.paired_trades)
    print("win_count     :", report.win_count)
    print("loss_count    :", report.loss_count)
    print("win_rate      :", report.win_rate)
    print("violations    :", report.violations)
    print("warnings      :", report.warnings[:4])
    os.remove(log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
