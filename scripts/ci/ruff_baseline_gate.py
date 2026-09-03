#!/usr/bin/env python3
"""scripts/ci/ruff_baseline_gate.py — CI-00B (Phase 3): differential ruff gate.

The repository carries ~1000 pre-existing ruff findings (historical debt,
frozen under the project's Scientific Debt Rule — see CLAUDE.md). Blocking
CI on that debt is not viable, but silently ignoring *new* violations is
not viable either. This script implements a differential regression gate:

  * `.ci/ruff_baseline.json` is a versioned, committed snapshot of the
    findings that are tolerated today (the historical debt set).
  * `generate` recomputes that snapshot from the current tree — used only
    to deliberately update the baseline (a visible diff in a PR, never a
    silent side effect of a normal run).
  * `check` (the CI entry point) reruns ruff, diffs the result against the
    baseline, and fails ONLY if there are findings not present in the
    baseline ("new" — i.e. a real regression). Findings that are in the
    baseline are reported but never fail the gate. Findings that were in
    the baseline but are no longer produced (fixed debt) never fail the
    gate either — the check is "no NEW findings", not "same count".

Forbidden by design: no `continue-on-error`, no mass `# noqa`, no
`ruff ... --exit-zero`, no autofix. A new violation fails the job with a
clear, itemized report.

IMPORTANT — ruff version pin: findings (including which syntax errors are
raised) can change between ruff releases with no code change at all. The
baseline is only meaningful if generated and checked with the SAME ruff
version. CI pins `ruff==0.15.8` (see .github/workflows/ci.yml) — use the
identical version locally when regenerating the baseline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / ".ci" / "ruff_baseline.json"

RUFF_ARGS = [
    "ruff",
    "check",
    ".",
    "--select=E,F,W",
    "--ignore=E501,E402",
    # .ipynb excluded: ruff's invalid-syntax location for unparseable
    # notebooks is non-deterministic between runs (observed: same file,
    # same ruff version, different row/col across invocations), which
    # breaks position-keyed baseline matching. Notebooks are docs, not
    # lint-enforced source, in this project.
    "--exclude=__pycache__,.venv,*.ipynb",
    "--output-format=json",
]


def _run_ruff() -> list[dict]:
    """Runs ruff and returns the parsed JSON findings.

    ruff exits non-zero when it finds violations — that is expected and
    not itself an error condition here; only a genuine invocation failure
    (bad json / missing binary) should raise.
    """
    proc = subprocess.run(  # noqa: S603
        RUFF_ARGS, cwd=ROOT, capture_output=True, text=True, check=False
    )
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"ruff_baseline_gate: could not parse ruff output: {exc}") from exc


def _key(finding: dict) -> str:
    """Stable, portable identity for one finding.

    Filenames are normalized to repo-relative POSIX paths so the baseline
    is identical whether generated from a local checkout or a CI runner's
    working directory.
    """
    filename = Path(finding["filename"]).resolve()
    try:
        rel = filename.relative_to(ROOT).as_posix()
    except ValueError:
        rel = filename.as_posix()
    row = finding["location"]["row"]
    col = finding["location"]["column"]
    return f"{rel}:{row}:{col}:{finding['code']}"


def _load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return set(data.get("findings", []))


def cmd_generate(_args: argparse.Namespace) -> int:
    findings = _run_ruff()
    keys = sorted({_key(f) for f in findings})
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "$schema": "CI-00B ruff differential baseline v1",
        "rule_selection": "E,F,W (ignore E501,E402)",
        "count": len(keys),
        "findings": keys,
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(keys)} baseline findings to {BASELINE_PATH.relative_to(ROOT)}")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    baseline = _load_baseline()
    findings = _run_ruff()
    current = {_key(f): f for f in findings}

    new_keys = sorted(set(current) - baseline)
    fixed_count = len(baseline - set(current))

    print("LINT REGRESSION GATE — ruff baseline diff")
    print(f"  baseline findings : {len(baseline)}")
    print(f"  current findings  : {len(current)}")
    print(f"  fixed since baseline (tolerated, not required) : {fixed_count}")
    print(f"  NEW findings (would fail the gate) : {len(new_keys)}")

    if new_keys:
        print("\nNew violations not present in .ci/ruff_baseline.json:")
        for key in new_keys:
            f = current[key]
            print(f"  {key}  {f['message']}")
        print(
            "\nEither fix the new violation(s), or — if this is a deliberate, "
            "reviewed baseline update — regenerate the baseline explicitly "
            "with `python scripts/ci/ruff_baseline_gate.py generate` and "
            "commit the resulting .ci/ruff_baseline.json diff for review."
        )
        return 1

    print("\nNo new violations beyond the committed baseline. Gate passes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Regenerate .ci/ruff_baseline.json from the current tree.")
    sub.add_parser("check", help="Fail if there are ruff findings beyond the committed baseline.")
    args = parser.parse_args()

    if args.command == "generate":
        return cmd_generate(args)
    return cmd_check(args)


if __name__ == "__main__":
    raise SystemExit(main())
