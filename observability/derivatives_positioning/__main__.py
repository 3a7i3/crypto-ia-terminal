"""Verification CLI of the positioning store. Local file access only, no network.

    python -m observability.derivatives_positioning --data-dir DIR [--config FILE] COMMAND

Commands: ``status``, ``ingest FILE|-`` (one object or a list), ``latest``, ``history``,
``oi-change``, ``compare``. Output is JSON on stdout.
Exit codes: 0 ok, 2 input rejected or conflict, 3 storage error, 4 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys

from .contract import parse_utc_ms, ContractError
from .policy import PositioningPolicy
from .store import PositioningStore, StorageError

EXIT_OK, EXIT_INPUT, EXIT_STORAGE, EXIT_USAGE = 0, 2, 3, 4


def _emit(doc):
    sys.stdout.write(json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def _leg_args(p):
    p.add_argument("--venue", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--contract-type", required=True)


def _time(value):
    if value is None:
        return None
    try:
        return int(value) if value.isdigit() else parse_utc_ms(value, "cli")
    except ContractError as exc:
        raise argparse.ArgumentTypeError(exc.code) from None


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m observability.derivatives_positioning")
    ap.add_argument("--data-dir", required=True, help="existing persistent directory")
    ap.add_argument("--config", help="JSON policy file (see config/derivatives_positioning.example.json)")
    ap.add_argument("--read-only", action="store_true", help="open the database read-only")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("ingest")
    p.add_argument("source", help="JSON file or - for stdin")
    p = sub.add_parser("latest")
    _leg_args(p)
    p.add_argument("--as-of", type=_time)
    p = sub.add_parser("history")
    _leg_args(p)
    p.add_argument("--start", type=_time, required=True)
    p.add_argument("--end", type=_time, required=True)
    p.add_argument("--limit", type=int)
    p.add_argument("--cadence-s", type=int)
    p = sub.add_parser("oi-change")
    _leg_args(p)
    p.add_argument("--as-of", type=_time, required=True)
    p.add_argument("--cadence-s", type=int, help="declared collection cadence; absent => unavailable")
    p = sub.add_parser("compare")
    p.add_argument("--leg", action="append", required=True, help="venue:native_symbol:contract_type")
    p.add_argument("--as-of", type=_time, required=True)
    return ap


def main(argv=None):
    ap = build_parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    try:
        policy = PositioningPolicy.from_file(args.config) if args.config else PositioningPolicy()
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "code": "POLICY_INVALID", "detail": str(exc)})
        return EXIT_USAGE
    try:
        store = PositioningStore(args.data_dir, policy=policy, read_only=args.read_only)
    except StorageError as exc:
        _emit({"ok": False, "code": exc.code, "detail": exc.detail})
        return EXIT_STORAGE
    try:
        with store:
            return _run(store, args)
    except StorageError as exc:
        _emit({"ok": False, "code": exc.code, "detail": exc.detail})
        return EXIT_STORAGE


def _run(store, args):
    if args.command == "status":
        _emit({"ok": True, **store.status()})
        return EXIT_OK
    if args.command == "ingest":
        try:
            text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()
            payload = json.loads(text)
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "code": "INPUT_UNREADABLE", "detail": str(exc)})
            return EXIT_INPUT
        batch = store.ingest_batch(payload if isinstance(payload, list) else [payload])
        _emit(batch.as_dict())
        if not batch.ok:
            return EXIT_STORAGE
        if any(r.status in ("REJECTED", "CONFLICT") for r in batch.results):
            return EXIT_INPUT
        return EXIT_OK
    if args.command == "latest":
        _emit(store.latest(args.venue, args.symbol, args.contract_type, as_of_ms=args.as_of))
        return EXIT_OK
    if args.command == "history":
        try:
            _emit(store.history(args.venue, args.symbol, args.contract_type, args.start, args.end,
                                limit=args.limit, cadence_s=args.cadence_s))
        except ValueError as exc:
            _emit({"ok": False, "code": str(exc)})
            return EXIT_USAGE
        return EXIT_OK
    if args.command == "oi-change":
        _emit(store.oi_change(args.venue, args.symbol, args.contract_type, as_of_ms=args.as_of,
                              cadence_s=args.cadence_s))
        return EXIT_OK
    if args.command == "compare":
        legs = []
        for leg in args.leg:
            # The native symbol may contain ':'; venue and contract type never do.
            venue, _, rest = leg.partition(":")
            symbol, _, ctype = rest.rpartition(":")
            if not venue or not symbol or not ctype:
                _emit({"ok": False, "code": "INVALID_LEG", "detail": leg})
                return EXIT_USAGE
            legs.append((venue, symbol, ctype))
        _emit(store.compare(legs, as_of_ms=args.as_of))
        return EXIT_OK
    return EXIT_USAGE  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
