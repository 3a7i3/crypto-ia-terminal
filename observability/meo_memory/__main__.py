"""Local operator CLI of the MEO-04 memory (no network, no service, explicit root only).

    python3 -m observability.meo_memory init    --root ROOT --partition HISTORICAL|SYNTHETIC [--budget-bytes N]
    python3 -m observability.meo_memory import  --root ROOT --partition P (--capture DIR | --archive TAR.GZ)
                                                [--reading READING.json]
    python3 -m observability.meo_memory recover --root ROOT
    python3 -m observability.meo_memory rebuild --root ROOT
    python3 -m observability.meo_memory verify  --root ROOT
    python3 -m observability.meo_memory now     --root ROOT
    python3 -m observability.meo_memory events  --root ROOT [--limit N] [--cursor C] [--include-excluded]
                                                [--first-only]
    python3 -m observability.meo_memory summary --root ROOT [--limit N] [--cursor C]

Exit codes: 0 done (IMPORTED, NO_OP, EMPTY included), 4 refused (typed category on stderr),
5 PUBLICATION_UNCERTAIN (nothing acknowledged; run ``recover``).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import canon as c
from .reads import Reader
from .store import Store, init_root


def _parser():
    ap = argparse.ArgumentParser(prog="meo_memory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "import", "recover", "rebuild", "verify", "now", "events", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        if name in ("init", "import"):
            p.add_argument("--partition", required=True, choices=c.PARTITIONS)
        if name == "init":
            p.add_argument("--budget-bytes", type=int, default=None)
        if name == "import":
            src = p.add_mutually_exclusive_group(required=True)
            src.add_argument("--capture")
            src.add_argument("--archive")
            p.add_argument("--reading", default=None)
        if name in ("events", "summary"):
            p.add_argument("--limit", type=int, default=None)
            p.add_argument("--cursor", default=None)
        if name == "events":
            p.add_argument("--include-excluded", action="store_true")
            p.add_argument("--first-only", action="store_true")
    return ap


def main(argv=None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.cmd == "init":
            out = init_root(a.root, a.partition, a.budget_bytes)
        elif a.cmd == "import":
            out = Store(a.root).import_capture(partition=a.partition, capture_dir=a.capture, archive=a.archive,
                                               reading=a.reading)
        elif a.cmd in ("recover", "rebuild", "verify"):
            out = getattr(Store(a.root), a.cmd)()
        elif a.cmd == "now":
            out = Reader(a.root).now()
        elif a.cmd == "events":
            out = Reader(a.root).events(limit=a.limit, cursor=a.cursor, include_excluded=a.include_excluded,
                                        first_only=a.first_only)
        else:
            out = Reader(a.root).summary(limit=a.limit, cursor=a.cursor)
    except c.MemoryRefusal as exc:
        print(json.dumps({"refused": exc.category, "detail": exc.detail}, sort_keys=True), file=sys.stderr)
        return 5 if exc.category == c.PUBLICATION_UNCERTAIN else 4
    print(json.dumps(out, indent=2, sort_keys=True))
    if a.cmd == "verify" and out.get("state") != "CONSISTENT":
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
