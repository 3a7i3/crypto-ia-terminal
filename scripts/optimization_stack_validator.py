"""Manual validator for the optimization stack pytest slice."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    return pytest.main([str(repo_root / "tests" / "test_optimization_stack.py"), "-q"])


if __name__ == "__main__":
    raise SystemExit(main())