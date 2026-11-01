"""Kernel proof uses a child and local denied probes, never an exchange."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from observability.market_venues.public_us_sandbox import supervise, disk_usage


def parent(tmp_path):
    p = tmp_path / "market-venue-pilot-runs"
    p.mkdir(mode=0o700)
    return p


def test_kernel_confinement_keeps_uid_and_refuses_outside_writes_and_tcp_bind(tmp_path):
    p = parent(tmp_path)
    root = Path(__file__).resolve().parents[2]
    # No host change if ABI4 is unavailable: the helper refuses. This VM proof
    # is meaningful here; CI can run the mock tests on other hosts.
    script = """
import sys,json,os,socket,errno
from pathlib import Path
from observability.market_venues.public_us_sandbox import restrict_child
p=Path(sys.argv[1])
try:
 report=restrict_child(p)
except (OSError,RuntimeError) as e:
 print(json.dumps({"unsupported":str(e)}));sys.exit(77)
assert os.getuid()==1001
inside=p/"proof";inside.mkdir()
(inside/"allowed").write_text("ok")
outside=p.parent/"outside-must-not-exist"
try:outside.write_text("denied");raise AssertionError("outside write allowed")
except PermissionError:pass
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
try:s.bind(("127.0.0.1",0));raise AssertionError("TCP bind allowed")
except PermissionError:pass
finally:s.close()
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
try:s.connect(("127.0.0.1",9));raise AssertionError("TCP port9 allowed")
except PermissionError:pass
finally:s.close()
print(json.dumps(report))
"""
    env = {
        "PYTHONPATH": str(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": "/usr/bin:/bin",
    }
    r = subprocess.run(
        [sys.executable, "-c", script, str(p)],
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
    )
    if r.returncode == 77 and os.environ.get("REQUIRE_US_CAPTURE_SANDBOX") != "1":
        pytest.skip("Landlock ABI4/UID1001 proof runs on the explicit target VM")
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report["no_new_privs"] and report["tcp_connect_ports"] == [443]
    assert not (p.parent / "outside-must-not-exist").exists()
    assert (p / "proof/allowed").read_text() == "ok"


def test_outer_watchdog_kills_only_its_child_after_deadline(tmp_path):
    p = parent(tmp_path)
    root = Path(__file__).resolve().parents[2]
    r = supervise(
        [sys.executable, "-c", "import time;time.sleep(5)"],
        source_directory=root,
        run_parent=p,
        timeout_seconds=1,
    )
    assert r["stopped_reason"] == "OUTER_DEADLINE"
    assert r["elapsed_seconds"] < 4 and r["returncode"] != 0


def test_outer_disk_budget_and_symlinks_are_refused(tmp_path):
    p = parent(tmp_path)
    (p / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match="OBJECT"):
        disk_usage(p)


def test_preexisting_run_parent_or_enlarged_deadline_is_refused(tmp_path):
    p = parent(tmp_path)
    (p / "foreign").write_text("keep")
    with pytest.raises(ValueError, match="FRESH"):
        supervise(["false"], source_directory=tmp_path, run_parent=p)
    with pytest.raises(ValueError, match="DEADLINE"):
        supervise(
            ["false"], source_directory=tmp_path, run_parent=p, timeout_seconds=36
        )
    assert (p / "foreign").read_text() == "keep"


def test_outer_output_budget_does_not_wait_for_a_full_pipe(tmp_path):
    p = parent(tmp_path)
    root = Path(__file__).resolve().parents[2]
    result = supervise(
        [sys.executable, "-c", "print('x'*20000)"], source_directory=root, run_parent=p
    )
    assert result["stopped_reason"] == "OUTPUT_BUDGET"
    assert len(result["output"].encode()) <= 8192
