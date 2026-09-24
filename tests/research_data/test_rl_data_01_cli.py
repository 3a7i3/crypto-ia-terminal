"""RL-DATA-01 CLI invocation tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cli_help_resolves_research_package_outside_repo_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "rl_data_01_export.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Export one immutable PAPER boundary" in completed.stdout
