"""
tests/test_t1_herm_01_r1_conftest_bootstrap_isolation.py — T1-HERM-01-R1 / DS-001.

Proves that an ambient PAPER_TRADE_LOG set in the environment BEFORE pytest
starts cannot survive root conftest.py's module-level bootstrap. Before this
fix, conftest.py used os.environ.setdefault("PAPER_TRADE_LOG", ...), which
preserves any pre-existing value — so a residual passive reader resolving
PAPER_TRADE_LOG at import time (during collection) could bind to a real/
production-like ledger path if the launching shell/CI/VPS environment
already had PAPER_TRADE_LOG set. conftest.py now uses unconditional
assignment instead.

Runs in a fresh subprocess (not just monkeypatch) because the defect is
about module-import-time behavior of conftest.py itself, before any pytest
fixture machinery exists to intervene.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SENTINEL_PRODUCTION_LIKE_PATH = "/tmp/T1_HERM_01_R1_SENTINEL_databases/paper_trades.jsonl"


def test_ambient_paper_trade_log_does_not_survive_conftest_bootstrap():
    script = (
        "import os\n"
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import runpy\n"
        "runpy.run_path(%r, run_name='conftest')\n"
        "assert os.environ['PAPER_TRADE_LOG'] != %r, "
        "'ambient PAPER_TRADE_LOG survived conftest bootstrap'\n"
        "assert os.path.isabs(os.environ['PAPER_TRADE_LOG']), "
        "'PAPER_TRADE_LOG must be absolute after bootstrap'\n"
        "import tempfile\n"
        "tmp_root = os.path.realpath(tempfile.gettempdir())\n"
        "resolved = os.path.realpath(os.environ['PAPER_TRADE_LOG'])\n"
        "assert resolved.startswith(tmp_root), "
        "'PAPER_TRADE_LOG must be a temp path after bootstrap, got ' + resolved\n"
        "print('OK')\n"
    ) % (str(_REPO_ROOT), str(_REPO_ROOT / "conftest.py"), _SENTINEL_PRODUCTION_LIKE_PATH)

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "PAPER_TRADE_LOG": _SENTINEL_PRODUCTION_LIKE_PATH,
    }

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"subprocess failed — ambient PAPER_TRADE_LOG may have survived "
        f"conftest bootstrap.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout

    # Never touched a real/production-like ledger: the sentinel path itself
    # must not have been created by this test.
    assert not Path(_SENTINEL_PRODUCTION_LIKE_PATH).exists()
