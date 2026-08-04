#!/usr/bin/env python3
"""État du laboratoire : indicateurs, validité historique, snapshot.

Lecture seule par défaut. `--write-snapshot` est la seule action d'écriture,
et elle n'écrit que le manifeste — jamais un journal.

Usage :
    python tools/lab_status.py
    python tools/lab_status.py --write-snapshot
    python tools/lab_status.py --verify-snapshot
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scios import history, indicators, snapshot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="knowledge")
    ap.add_argument("--write-snapshot", action="store_true")
    ap.add_argument("--verify-snapshot", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent / args.root
    exit_code = 0

    print(indicators.compute(root).render())
    print()

    report = history.check(root)
    print(report.render())
    if not report.ok:
        exit_code = 2
    print()

    if args.write_snapshot:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dest = snapshot.write(root, now)
        print(f"manifeste écrit -> {dest.relative_to(dest.parents[1])}")
        print()

    snap_path = root / snapshot.MANIFEST_NAME
    if snap_path.exists():
        problems = snapshot.verify(root)
        if problems:
            print("SNAPSHOT : " + f"{len(problems)} écart(s)")
            for p in problems:
                print(f"  - {p}")
            exit_code = 3
        else:
            print("SNAPSHOT : le ledger est conforme à son manifeste versionné.")
    elif args.verify_snapshot:
        print(f"SNAPSHOT : {snapshot.MANIFEST_NAME} absent.")
        exit_code = 3

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
