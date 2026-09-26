"""HERM-02 — preventive isolation of ambient runtime persistence paths."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_MANAGED = (
    "OBS_LOG_ROOT",
    "REJECTION_STORE_DIR",
    "BB_PATH",
    "LMI_DIR",
    "ORDER_INTENT_JOURNAL_PATH",
    "DECISION_IDENTITY_JOURNAL_PATH",
)


def _run_python(code: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def test_module_level_isolation_overrides_ambient_persistence_paths(tmp_path):
    sentinel_root = tmp_path / "ambient"
    sentinel_root.mkdir()
    env = os.environ.copy()
    sentinels = {
        name: str(sentinel_root / f"{name.lower()}.sentinel")
        for name in _MANAGED
    }
    env.update(sentinels)

    code = (
        "import json, os; import conftest; "
        f"print(json.dumps({{k: os.environ[k] for k in {list(_MANAGED)!r}}}))"
    )
    completed = _run_python(code, env=env)
    resolved = json.loads(completed.stdout.strip().splitlines()[-1])

    for name, sentinel in sentinels.items():
        assert resolved[name] != sentinel
        assert "pytest_" in resolved[name]


def test_external_order_intent_path_is_unchanged_after_isolated_consumer(tmp_path):
    external = tmp_path / "fake_prod" / "order_intent_journal.jsonl"
    external.parent.mkdir()
    external.write_bytes(b'{"pretend":"REAL PRODUCTION RUNTIME JOURNAL"}\n')
    before = hashlib.sha256(external.read_bytes()).hexdigest()

    env = os.environ.copy()
    env["ORDER_INTENT_JOURNAL_PATH"] = str(external)
    code = """
import conftest
from pathlib import Path
from quant_hedge_ai.agents.execution import execution_engine
p = Path(execution_engine._DEFAULT_ORDER_INTENT_JOURNAL_PATH)
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as handle:
    handle.write('{"probe":"isolated"}\\n')
print(p)
"""
    completed = _run_python(code, env=env)
    resolved = Path(completed.stdout.strip().splitlines()[-1])

    assert resolved != external
    assert hashlib.sha256(external.read_bytes()).hexdigest() == before


def test_bb_path_is_redirected_per_test(tmp_path):
    assert os.environ["BB_PATH"] == str(tmp_path / "black_box_test.jsonl")
