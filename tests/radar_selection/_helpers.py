"""Shared helpers for the RADAR R0 tests (SYNTHETIC fixtures only, no network)."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from observability.radar_selection.engine import evaluate
from observability.radar_selection.terminal import FIXTURE_DIR, NAMED_FIXTURES, Session

ROOT = Path(__file__).resolve().parents[2]
NAMES = tuple(NAMED_FIXTURES)


def path(name: str) -> Path:
    return FIXTURE_DIR / NAMED_FIXTURES[name]


def doc(name: str) -> dict:
    return json.loads(path(name).read_text(encoding="utf-8"))


def raw(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True).encode("utf-8")


def ev(src, prefs=None, mission="DEEP_OBSERVATION", **kw):
    data = path(src).read_bytes() if isinstance(src, str) else raw(src)
    return evaluate(data, prefs, mission, **kw)


def market(evaluation: dict, mid: str) -> dict:
    for m in evaluation["markets"]:
        if m["market_id"] == mid:
            return m
    raise KeyError(mid)


def codes(m: dict) -> list:
    return [r["code"] for r in m["admissibility"]["reasons"]]


def clone(d: dict) -> dict:
    return copy.deepcopy(d)


def observation(d: dict, venue: str, mtype: str, native: str) -> dict:
    for o in d["observations"]:
        if (o["venue"], o["market_type"], o["native_symbol"]) == (venue, mtype, native):
            return o
    raise KeyError(native)


def session(name: str, width: int = 80, state_dir=None, mission="DEEP_OBSERVATION") -> Session:
    """In-process session WITHOUT the offline guard (render tests only)."""
    return Session(path(name), state_dir, width, mission)


def cli(args, cwd: Path, stdin: str | None = None, timeout: int = 60):
    """Run the real CLI in a separate process (the guard is irreversible per process)."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "COLUMNS")}
    env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    proc = subprocess.run([sys.executable, "-m", "observability.radar_selection", *args],
                          cwd=cwd, input=stdin, capture_output=True, text=False, env=env, timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def python(code: str, cwd: Path, timeout: int = 60):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True,
                          env=env, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def tree(directory: Path) -> dict:
    return {str(p.relative_to(directory)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(directory.rglob("*")) if p.is_file()}
