"""Proof 3 and 5: real process restarts on the same directory, and the Git boundary.

Each step runs the verification CLI in a fresh Python process. The directory is a
pytest temporary directory, never inside the repository.
"""

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from tests.derivatives_positioning.support import T0, iso, obs_a, obs_b

REPO = Path(__file__).resolve().parents[2]
LEG_A = ["--venue", "exchange_a", "--symbol", "BTC_USDT", "--contract-type", "PERPETUAL_LINEAR"]


def cli(data_dir, *args, stdin=None):
    proc = subprocess.run([sys.executable, "-m", "observability.derivatives_positioning", "--data-dir",
                           str(data_dir), *args], cwd=REPO, input=stdin, capture_output=True, text=True,
                          timeout=60)
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None), proc.stderr


def test_restart_rereads_history_then_accepts_a_new_observation(tmp_path):
    data = tmp_path / "state"
    data.mkdir()
    rc, st0, _ = cli(data, "status")
    assert rc == 0 and st0["observations"] == 0
    first = tmp_path / "first.json"
    first.write_text(json.dumps(obs_a()))
    rc, out, err = cli(data, "ingest", str(first))
    assert rc == 0, err
    assert out["results"][0]["status"] == "INSERTED"

    # process 2: restart on the same directory, same store, history intact, replay idempotent
    rc, st1, _ = cli(data, "status")
    assert rc == 0 and st1["store_id"] == st0["store_id"] and st1["observations"] == 1
    rc, latest, _ = cli(data, "latest", *LEG_A, "--as-of", iso(T0 + timedelta(seconds=5)))
    assert latest["observation"]["measures"]["open_interest"]["value"] == "1250000"
    rc, out, _ = cli(data, "ingest", str(first))
    assert rc == 0 and out["results"][0]["status"] == "DUPLICATE"

    # process 3: a second observation is written and read back with the first one
    second = obs_a(T0 + timedelta(minutes=5), oi="1250500")
    rc, out, _ = cli(data, "ingest", "-", stdin=json.dumps(second))
    assert rc == 0 and out["results"][0]["status"] == "INSERTED"
    rc, hist, _ = cli(data, "history", *LEG_A, "--start", iso(T0), "--end", iso(T0 + timedelta(minutes=10)),
                      "--cadence-s", "300")
    assert rc == 0
    assert [o["measures"]["open_interest"]["value"] for o in hist["observations"]] == ["1250000", "1250500"]
    assert hist["coverage"]["expected"] == 3

    # process 4: the second platform with other units, compared natively
    rc, out, _ = cli(data, "ingest", "-", stdin=json.dumps(obs_b()))
    assert rc == 0
    rc, cmp, _ = cli(data, "compare", "--leg", "exchange_a:BTC_USDT:PERPETUAL_LINEAR",
                     "--leg", "exchange_b:PF_XBTUSD:PERPETUAL_LINEAR", "--as-of", iso(T0 + timedelta(seconds=5)))
    assert cmp["pairs"][0]["open_interest"]["reason"] == "OPEN_INTEREST_UNITS_DIFFER"
    rc, st2, _ = cli(data, "status")
    assert st2["store_id"] == st0["store_id"] and st2["observations"] == 3


def test_cli_errors_are_explicit(tmp_path):
    rc, out, _ = cli(tmp_path / "missing", "status")
    assert rc == 3 and out["code"] == "STORAGE_DIRECTORY_MISSING"
    rc, out, _ = cli(tmp_path, "ingest", "-", stdin=json.dumps({"contract_version": "1.0.0"}))
    assert rc == 2 and out["results"][0]["status"] == "REJECTED"
    rc, out, _ = cli(tmp_path, "--read-only", "ingest", "-", stdin=json.dumps(obs_a()))
    assert rc == 3 and out["results"][0]["code"] == "STORAGE_READ_ONLY"
    rc, out, _ = cli(tmp_path, "status")
    assert rc == 0 and out["observations"] == 0


def test_data_files_are_excluded_from_git():
    names = ["positioning.sqlite3", "positioning.sqlite3-wal", "positioning.sqlite3-shm",
             "positioning.sqlite3-journal", "var/lib/cat-derivatives-positioning/positioning.sqlite3"]
    proc = subprocess.run(["git", "check-ignore", "--no-index", *names], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0
    assert sorted(proc.stdout.split()) == sorted(names)
