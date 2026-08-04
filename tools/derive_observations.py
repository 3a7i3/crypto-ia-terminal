#!/usr/bin/env python3
"""Exécute le lien Event -> Observation et vérifie sa reproductibilité.

Usage :
    python tools/derive_observations.py --list
    python tools/derive_observations.py --run close_pnl_distribution --epoch EPO-004
    python tools/derive_observations.py --run-all --epoch EPO-004
    python tools/derive_observations.py --reproduce
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scios import derive  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="knowledge")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run")
    ap.add_argument("--run-all", action="store_true")
    ap.add_argument("--epoch", default=None)
    ap.add_argument("--reproduce", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent / args.root

    if args.list:
        print("DÉRIVATIONS ENREGISTRÉES\n")
        for name, d in sorted(derive.DERIVATIONS.items()):
            print(f"  {name}  v{d.version}")
            print(f"      {d.description}")
            print(f"      entrées   : {', '.join(d.event_kinds)}")
            print(f"      limites   : {d.limitations}")
        return 0

    noms = (
        list(derive.DERIVATIONS) if args.run_all else ([args.run] if args.run else [])
    )
    for name in noms:
        try:
            obs = derive.derive(root, name, epoch_id=args.epoch)
        except derive.DerivationError as exc:
            print(f"{name} : ÉCHEC — {exc}")
            continue
        print(f"{obs.id}  [{name} v{derive.DERIVATIONS[name].version}]")
        print(f"    {obs.statement}")
        print(
            f"    {obs.source_event_count} événements, "
            f"empreinte {obs.source_event_digest[:16]}"
        )
        print()

    if args.reproduce or noms:
        problemes = derive.reproduce_all(root)
        if problemes:
            print(f"REPRODUCTIBILITÉ : {len(problemes)} écart(s)")
            for p in problemes:
                print(f"  - {p}")
            return 2
        print("REPRODUCTIBILITÉ : toutes les observations dérivées se reproduisent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
