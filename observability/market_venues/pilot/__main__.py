"""Offline plan check/simulation only; real activation is a separate governed task."""

import argparse
from pathlib import Path
import json
from .plan import PilotPlan
from .runner import run_bounded_pilot
from .synthetic import SyntheticClock, SyntheticTransport
from .verify import verify_run


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-plan", action="store_true")
    mode.add_argument("--simulate", action="store_true")
    mode.add_argument("--verify-run", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--cycles", type=int, default=2)
    a = p.parse_args(argv)
    if a.verify_run is not None:
        print(json.dumps(verify_run(a.verify_run), indent=2))
        return
    if a.check_plan:
        print(json.dumps(PilotPlan().document(), indent=2))
        return
    if a.out is None:
        p.error("--out must name an existing private market-venue-pilot-runs directory")
    clock = SyntheticClock()
    result = run_bounded_pilot(
        SyntheticTransport(clock),
        a.out,
        source_sha="0" * 40,
        plan=PilotPlan(cycles=a.cycles),
        clock=clock,
        sleeper=clock.sleep,
    )
    print(json.dumps(result, indent=2))
    if result["status"] != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
