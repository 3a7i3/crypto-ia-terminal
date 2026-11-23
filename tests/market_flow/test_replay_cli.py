"""Operator CLI of the CH1-02 Kraken-only replay. SYNTHETIC journals only.

The journal comes from ``bbo_pilot.dry_run`` (fake clock, fake venues). Nothing here is
provider output or runtime proof; replaying the real corpus stays an operator gesture.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

from observability import market_perception_replay as cli
from observability.market_flow import kraken_replay as kr
from observability.radar_composite import bbo_pilot

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = "SYNTH-BBO-BTC"
NAMES = {"manifest": "manifest.json", "events": "events.jsonl", "frames": "frames.bin"}


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("bbo") / "run"
    _pilot, code = bbo_pilot.dry_run("BTC", out)
    assert code == 0
    return out


@pytest.fixture(scope="module")
def total(run_dir):
    return len((run_dir / "events.jsonl").read_bytes().splitlines())


def journal_args(run_dir):
    return [arg for key, name in NAMES.items() for arg in (f"--{key}", str(run_dir / name))]


def replay_args(run_dir, out, bound, *extra):
    return ["replay", *journal_args(run_dir), "--receipt-bound", str(bound), "--corpus-id", CORPUS,
            "--evidence-kind", "SYNTHETIC", "--out", str(out), *extra]


def call(capsys, argv):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def sealed_bytes(run_dir):
    return tuple((run_dir / name).read_bytes() for name in NAMES.values())


def test_replay_writes_the_document_and_prints_count_size_and_hash(run_dir, total, tmp_path, capsys):
    out = tmp_path / "replay.json"
    code, stdout, stderr = call(capsys, replay_args(run_dir, out, total))
    assert (code, stderr) == (0, "")
    summary = json.loads(stdout)
    data = out.read_bytes()
    assert summary["status"] == "WRITTEN" and summary["out"] == str(out)
    assert summary["bytes"] == len(data) == out.stat().st_size
    assert summary["sha256"] == hashlib.sha256(data).hexdigest()
    expected, seal = kr.replay(*sealed_bytes(run_dir), corpus_id=CORPUS, evidence_kind="SYNTHETIC",
                               receipt_bound=total)
    assert data == expected  # the CLI publishes the replay itself, byte for byte
    doc = json.loads(data)
    counts = {kind: sum(1 for r in doc["records"] if r["type"] == kind) for kind in ("RAW_EVENT", "BOOK_STATE", "QUALITY_REPORT")}
    assert summary["records"] == counts and summary["records_total"] == len(doc["records"]) == sum(counts.values())
    assert (summary["receipt_bound"], summary["events_total"]) == (total, total)
    assert summary["seal"] == {k: v for k, v in seal.items() if k != "events_total"}
    assert (summary["silences"], summary["breaks"]) == (len(doc["silences"]), len(doc["breaks"]))
    assert summary["manifest_pin"] == "NOT_GIVEN" and summary["replay_version"] == kr.REPLAY_VERSION
    assert sorted(p.name for p in tmp_path.iterdir()) == ["replay.json"]  # no temporary file left


def test_two_runs_publish_identical_bytes(run_dir, tmp_path, capsys):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert call(capsys, replay_args(run_dir, first, 5029))[0] == 0
    assert call(capsys, replay_args(run_dir, second, 5029))[0] == 0
    assert first.read_bytes() == second.read_bytes()


def test_the_bound_is_explicit_and_bounds_the_document(run_dir, tmp_path, capsys):
    out = tmp_path / "bounded.json"
    code, stdout, _ = call(capsys, replay_args(run_dir, out, 5023))
    assert code == 0 and json.loads(stdout)["receipt_bound"] == 5023
    expected, _seal = kr.replay(*sealed_bytes(run_dir), corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=5023)
    assert out.read_bytes() == expected
    args = replay_args(run_dir, tmp_path / "x.json", 1)
    without = args[:args.index("--receipt-bound")] + args[args.index("--receipt-bound") + 2:]
    for argv in [without] + [replay_args(run_dir, tmp_path / "x.json", bad) for bad in ("0", "+5", "05", "5_000", "all", "-1")]:
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == cli.EXIT_USAGE
    capsys.readouterr()
    assert not (tmp_path / "x.json").exists()


def test_a_bound_beyond_the_seal_is_refused_without_writing(run_dir, total, tmp_path, capsys):
    out = tmp_path / "beyond.json"
    code, stdout, stderr = call(capsys, replay_args(run_dir, out, total + 1))
    assert (code, stdout) == (cli.EXIT_REFUSED, "")
    assert json.loads(stderr)["reason"] == "RECEIPT_BOUND_INVALID"
    assert list(tmp_path.iterdir()) == []


def test_verify_checks_the_seal_and_writes_nothing(run_dir, total, tmp_path, capsys):
    manifest_sha = hashlib.sha256((run_dir / "manifest.json").read_bytes()).hexdigest()
    before = sorted(os.listdir(run_dir))
    code, stdout, _ = call(capsys, ["verify", *journal_args(run_dir), "--manifest-sha256", manifest_sha])
    assert code == 0
    summary = json.loads(stdout)
    assert summary["status"] == "SEAL_VERIFIED" and summary["events_total"] == total
    assert summary["seal"]["manifest_sha256"] == manifest_sha and summary["manifest_pin"] == "MATCHED"
    assert sorted(os.listdir(run_dir)) == before


def test_a_broken_seal_is_refused_before_any_publication(run_dir, total, tmp_path, capsys):
    copy = tmp_path / "copy"
    copy.mkdir()
    for name in NAMES.values():
        (copy / name).write_bytes((run_dir / name).read_bytes())
    frames = bytearray((copy / "frames.bin").read_bytes())
    frames[-1] ^= 1
    (copy / "frames.bin").write_bytes(bytes(frames))
    dest = tmp_path / "out"
    dest.mkdir()
    for argv in (["verify", *journal_args(copy)], replay_args(copy, dest / "replay.json", total)):
        code, stdout, stderr = call(capsys, argv)
        assert (code, stdout) == (cli.EXIT_REFUSED, "")
        assert json.loads(stderr) == {"status": "REFUSED", "reason": "FRAMES_HASH_MISMATCH", "subject": "journal"}
    assert list(dest.iterdir()) == []


def test_historical_needs_a_matching_manifest_pin(run_dir, total, tmp_path, capsys):
    out = tmp_path / "h.json"
    manifest_sha = hashlib.sha256((run_dir / "manifest.json").read_bytes()).hexdigest()
    historical = [a if a != "SYNTHETIC" else "HISTORICAL" for a in replay_args(run_dir, out, total)]
    cases = ((historical, "MANIFEST_PIN_REQUIRED_FOR_HISTORICAL"),
             (historical + ["--manifest-sha256", "0" * 64], "MANIFEST_PIN_MISMATCH"),
             (historical + ["--manifest-sha256", manifest_sha], "SYNTHETIC_JOURNAL_DECLARED_HISTORICAL"),
             (replay_args(run_dir, out, total, "--manifest-sha256", "f" * 64), "MANIFEST_PIN_MISMATCH"))
    for argv, reason in cases:
        code, _stdout, stderr = call(capsys, argv)
        assert (code, json.loads(stderr)["reason"]) == (cli.EXIT_REFUSED, reason)
    assert not out.exists()
    with pytest.raises(SystemExit):
        cli.main(replay_args(run_dir, out, total, "--manifest-sha256", "ABC"))
    capsys.readouterr()


def test_the_destination_is_never_replaced_and_its_directory_never_created(run_dir, total, tmp_path, capsys):
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"operator file")
    for out, reason in ((existing, "OUTPUT_EXISTS"), (tmp_path / "missing" / "replay.json", "OUTPUT_DIRECTORY_MISSING"),
                        (str(tmp_path) + os.sep, "OUTPUT_PATH_INVALID")):
        code, _stdout, stderr = call(capsys, replay_args(run_dir, out, total))
        assert (code, json.loads(stderr)["reason"]) == (cli.EXIT_REFUSED, reason)
    assert existing.read_bytes() == b"operator file"
    assert not (tmp_path / "missing").exists()


def test_a_destination_created_during_the_replay_is_not_replaced(run_dir, total, tmp_path, capsys, monkeypatch):
    out = tmp_path / "race.json"
    real = kr.replay

    def replay_then_race(*args, **kwargs):
        result = real(*args, **kwargs)
        out.write_bytes(b"someone else")
        return result

    monkeypatch.setattr(cli.kr, "replay", replay_then_race)
    code, _stdout, stderr = call(capsys, replay_args(run_dir, out, total))
    assert (code, json.loads(stderr)["reason"]) == (cli.EXIT_REFUSED, "OUTPUT_EXISTS")
    assert out.read_bytes() == b"someone else"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["race.json"]


def test_a_failed_write_leaves_nothing_at_the_destination(run_dir, total, tmp_path, capsys, monkeypatch):
    out = tmp_path / "fail.json"

    def no_link(_src, _dst):
        raise PermissionError("hard links not supported here")

    monkeypatch.setattr(cli.os, "link", no_link)
    code, _stdout, stderr = call(capsys, replay_args(run_dir, out, total))
    assert (code, json.loads(stderr)["reason"]) == (cli.EXIT_WRITE_FAILED, "OUTPUT_WRITE_FAILED")
    assert list(tmp_path.iterdir()) == []


def test_a_document_that_does_not_read_back_identically_is_removed(run_dir, total, tmp_path, capsys, monkeypatch):
    out = tmp_path / "corrupt.json"
    real = cli.read_regular_file

    def corrupted(path, subject):
        data = real(path, subject)
        return data[:-1] if subject == "out" else data

    monkeypatch.setattr(cli, "read_regular_file", corrupted)
    code, _stdout, stderr = call(capsys, replay_args(run_dir, out, total))
    assert (code, json.loads(stderr)["reason"]) == (cli.EXIT_WRITE_FAILED, "OUTPUT_READBACK_MISMATCH")
    assert list(tmp_path.iterdir()) == []


def test_inputs_must_be_readable_regular_files(run_dir, total, tmp_path, capsys):
    for target, reason in ((tmp_path / "absent.bin", "INPUT_UNREADABLE"), (tmp_path, "INPUT_NOT_REGULAR_FILE")):
        argv = replay_args(run_dir, tmp_path / "x.json", total)
        argv[argv.index("--frames") + 1] = str(target)
        code, _stdout, stderr = call(capsys, argv)
        assert (code, json.loads(stderr)) == (cli.EXIT_REFUSED, {"status": "REFUSED", "reason": reason, "subject": "frames"})
    assert not (tmp_path / "x.json").exists()


def test_the_module_runs_as_an_operator_command(run_dir, total):
    proc = subprocess.run([sys.executable, "-m", "observability.market_perception_replay", "verify",
                           *journal_args(run_dir)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["events_total"] == total
