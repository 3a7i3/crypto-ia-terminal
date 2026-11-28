"""Operator CLI for MEO-01: verify and replay a sealed Kraken ``trade`` capture.

Sealed files in, one document out at a destination the operator names (a new
file, never overwritten). No network, no clock, no runtime wiring: the
calculation is ``observability.market_flow.kraken_trades.replay_journal``.

    python3 -m observability.meo_trades_replay verify DIR
    python3 -m observability.meo_trades_replay replay DIR --out REPORT.json [--as-of-ns N]
    python3 -m observability.meo_trades_replay read DIR --out READING.json [--as-of-ns N]

``read`` (MEO-03) replays the same way, then projects the report with
``observability.market_flow.meo_reading.read_report`` (DESALIGN-1 v1, PROBATION).

Exit codes: 0 ok, 4 refused (unsealed, altered or unreadable evidence, existing output).
"""

import argparse
import hashlib
import json
import os
import sys

from observability.market_flow import kraken_trades as kt
from observability.market_flow import meo_reading as mr

MAX_MANIFEST_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 64 * 1024 * 1024


def _read(path, cap):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(cap + 1)
    if len(data) > cap:
        raise kt.JournalRefusal("FILE_TOO_LARGE")
    return data


def load(directory):
    """Read the three sealed files and return (manifest, verified events)."""
    try:
        manifest = json.loads(_read(os.path.join(directory, "manifest.json"), MAX_MANIFEST_BYTES))
        log = _read(os.path.join(directory, "events.jsonl"), MAX_JOURNAL_BYTES)
        frames = _read(os.path.join(directory, "frames.bin"), MAX_JOURNAL_BYTES)
    except (OSError, ValueError) as exc:
        if isinstance(exc, kt.JournalRefusal):
            raise
        raise kt.JournalRefusal("EVIDENCE_UNREADABLE") from None
    return manifest, kt.verify_journal(manifest, log, frames)


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meo_trades_replay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("dir")
    r = sub.add_parser("replay")
    r.add_argument("dir")
    r.add_argument("--out", required=True)
    r.add_argument("--as-of-ns", type=int, default=None)
    rd = sub.add_parser("read")
    rd.add_argument("dir")
    rd.add_argument("--out", required=True)
    rd.add_argument("--as-of-ns", type=int, default=None)
    a = ap.parse_args(argv)
    try:
        manifest, events = load(a.dir)
        if a.cmd == "verify":
            print(json.dumps({"verified": True, "events": len(events),
                              "events_sha256": manifest["sealed"]["events_sha256"],
                              "frames_sha256": manifest["sealed"]["frames_sha256"],
                              "evidence_kind": manifest.get("evidence_kind")}, indent=2, sort_keys=True))
            return 0
        report = kt.replay_journal(manifest, events, as_of_ns=a.as_of_ns)
        if a.cmd == "read":
            reading = mr.read_report(report)
            data = mr.canonical(reading)
        else:
            data = kt.canonical(report)
        try:
            write_new(a.out, data)
        except FileExistsError:
            raise kt.JournalRefusal("OUTPUT_EXISTS") from None
        except OSError:
            raise kt.JournalRefusal("OUTPUT_UNWRITABLE") from None
        if a.cmd == "read":
            print(json.dumps({"reading": a.out, "reading_sha256": hashlib.sha256(data).hexdigest(),
                              "source_report_sha256": reading["corpus_ref"]["source_report_sha256"],
                              "evidence_kind": reading["evidence_kind"],
                              "first_desalignment": reading["first_desalignment"],
                              "alignment": {w["start_ns"]: w["alignment"] for w in reading["windows"]}},
                             indent=2, sort_keys=True))
            return 0
        print(json.dumps({"report": a.out, "report_sha256": hashlib.sha256(data).hexdigest(),
                          "exit_window": report["exit_window"],
                          "trade_coverage_state": report["trade_coverage"]["state"]},
                         indent=2, sort_keys=True))
        return 0
    except (kt.JournalRefusal, mr.ReadingRefusal) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
