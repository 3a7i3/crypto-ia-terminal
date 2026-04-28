"""
Compat wrapper.

The real V9.1 entrypoint lives in `quant_hedge_ai/main_v91.py` (package form).
This script exists only so `python quant-hedge-ai/main_v91.py` works.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Execute the package entrypoint (equivalent to: python -m quant_hedge_ai.main_v91)
    runpy.run_module("quant_hedge_ai.main_v91", run_name="__main__")


if __name__ == "__main__":
    main()
