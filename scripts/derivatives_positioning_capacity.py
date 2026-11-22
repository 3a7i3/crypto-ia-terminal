"""Measure the real size of the positioning store (database + WAL) on a synthetic load.

Writes invented observations into an EMPTY directory outside the repository, then
reports file sizes and bytes per observation, and extrapolates per day and per
retention period. No network. Example:

    python scripts/derivatives_positioning_capacity.py --data-dir /tmp/x --instruments 60 \
        --cadence-s 300 --days 7 --batch 60
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from observability.derivatives_positioning import PositioningStore  # noqa: E402


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def observation(i, at, k):
    """Representative shape: two unit conventions, one partial field, realistic digit counts."""
    venue = "exchange_a" if i % 2 == 0 else "exchange_b"
    symbol = ("SYN%03d_USDT" % i) if venue == "exchange_a" else ("PF_SYN%03dUSD" % i)
    oi = ({"value": str(1_250_000 + k * 7 + i), "unit": "CONTRACTS", "contract_size_base": "0.0001"}
          if venue == "exchange_a" else {"value": "%d.%04d" % (125 + i, k % 10_000), "unit": "BASE"})
    return {
        "contract_version": "1.0.0", "venue": venue, "native_symbol": symbol,
        "contract_type": "PERPETUAL_LINEAR", "quote_currency": "USDT" if venue == "exchange_a" else "USD",
        "base_currency": "SYN%03d" % i, "source_time_utc": iso(at),
        "received_at_utc": iso(at + timedelta(milliseconds=350)),
        "provenance": {"source": "synthetic:%s/ticker" % venue,
                       "payload_sha256": hashlib.sha256(("%s%d%d" % (venue, i, k)).encode()).hexdigest(),
                       "mapping_id": "SYNTHETIC-%s-%s" % (venue, symbol),
                       "mapping_sha256": hashlib.sha256(symbol.encode()).hexdigest(),
                       "collector_run_id": "capacity-run"},
        "measures": {
            "mark_price": {"value": "%d.%02d" % (65_000 + k % 997, k % 100)},
            "index_price": {"value": "%d.%02d" % (64_990 + k % 991, k % 97)},
            "spot_reference": ({"value": "%d.%02d" % (64_980 + k % 983, k % 89), "qualification": "QUALIFIED",
                                "venue": venue, "native_symbol": symbol.replace("_", ""),
                                "qualification_ref": "SYNTHETIC-SPOT-QUAL"}
                               if venue == "exchange_a" else {"unavailable": "SPOT_REFERENCE_NOT_QUALIFIED"}),
            "open_interest": oi,
            "funding_rate": {"value": "0.000%03d" % (k % 997), "interval_s": 28800 if venue == "exchange_a" else 3600,
                             "interval_attested_by": "synthetic:contract-detail",
                             "next_funding_utc": iso(at + timedelta(hours=1))},
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--instruments", type=int, default=60)
    ap.add_argument("--cadence-s", type=int, default=300)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--batch", type=int, default=60, help="observations per transaction")
    ap.add_argument("--retention-days", type=int, default=365)
    args = ap.parse_args(argv)
    data = Path(args.data_dir).resolve()
    if REPO in (data, *data.parents):
        sys.exit("refused: the data directory must be outside the repository")
    if not data.is_dir() or any(data.iterdir()):
        sys.exit("refused: --data-dir must be an existing empty directory")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    steps = args.days * 86_400 // args.cadence_s
    t0 = time.monotonic()
    peak_wal = 0
    with PositioningStore(data) as store:
        pending = []
        for k in range(steps):
            at = start + timedelta(seconds=k * args.cadence_s)
            for i in range(args.instruments):
                pending.append(observation(i, at, k))
                if len(pending) >= args.batch:
                    assert store.ingest_batch(pending).ok
                    pending = []
            peak_wal = max(peak_wal, (data / "positioning.sqlite3-wal").stat().st_size)
        if pending:
            assert store.ingest_batch(pending).ok
        before = store.status()
        store.checkpoint()
        after = store.status()
    elapsed = time.monotonic() - t0
    rows = after["observations"]
    db_bytes = after["files_bytes"]["positioning.sqlite3"]
    per_row = db_bytes / rows
    per_day_rows = args.instruments * 86_400 / args.cadence_s
    report = {
        "load": {"instruments": args.instruments, "cadence_s": args.cadence_s, "days": args.days,
                 "batch": args.batch, "observations": rows},
        "before_checkpoint_bytes": before["files_bytes"],
        "after_checkpoint_bytes": after["files_bytes"],
        "peak_wal_bytes": peak_wal,
        "database_bytes_before_checkpoint": before["files_bytes"]["positioning.sqlite3"],
        "wal_bytes_before_checkpoint": before["files_bytes"]["positioning.sqlite3-wal"],
        "database_bytes_after_checkpoint": db_bytes,
        "wal_bytes_after_checkpoint": after["files_bytes"]["positioning.sqlite3-wal"],
        "shm_bytes": after["files_bytes"]["positioning.sqlite3-shm"],
        "budget_bytes_forecast": 5_000_000_000,
        "purge_active": False,
        "bytes_per_observation": round(per_row, 1),
        "extrapolated_bytes_per_day": round(per_row * per_day_rows),
        "extrapolated_bytes_retention": round(per_row * per_day_rows * args.retention_days),
        "retention_days": args.retention_days,
        "ingest_seconds": round(elapsed, 1),
        "evidence_kind": "SYNTHETIC",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
