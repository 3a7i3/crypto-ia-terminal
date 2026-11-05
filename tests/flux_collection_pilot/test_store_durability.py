"""Exact byte budget, durable closure, interrupted writes, private storage."""

import json
import os
import shutil
from pathlib import Path

import pytest

from observability.flux_collection_pilot import analysis, protocol as P
from observability.flux_collection_pilot.store import (CampaignStore, DiskBudgetExceeded, WriteFailed, _canonical,
                                                   raw_record, verify_campaign)
from observability.market_venues.pilot.capture import Instant
from .helpers import final, healthy_items, run, script

HERE = Path(__file__).resolve().parent


def line_len(sid, i, raw, caps):
    return len(_canonical(raw_record(sid, i, i, Instant(1, 1), raw))) + 1


def test_exact_byte_boundary_of_the_raw_budget_and_the_reserve(tmp_path):
    raw = b'{"channel":"heartbeats","sequence_num":0}'
    n = line_len("S01", 0, raw, None)
    caps = P.Caps(max_disk_bytes=10 * n + 5_000, reserve_bytes=5_000)  # raw budget = exactly 10 lines
    st = CampaignStore(tmp_path, "b", caps)
    st.open_raw("S01")
    for i in range(10):
        st.append_raw("S01", raw_record("S01", i, i, Instant(1, 1), raw))
    assert st.used == 10 * n  # exactly at the limit: accepted
    with pytest.raises(DiskBudgetExceeded):
        st.append_raw("S01", raw_record("S01", 10, 10, Instant(1, 1), raw))  # one line over: refused, nothing written
    assert st.used == 10 * n and st.raw_state("S01")["lines"] == 10
    st.write_atomic("trigger.json", {"x": "y" * 4000}, final=True)  # the reserve is usable by final writes
    with pytest.raises(DiskBudgetExceeded):
        st.write_atomic("final.receipt.json", {"x": "y" * 2000}, final=True)  # but not beyond the hard cap
    assert sum(p.stat().st_size for p in st.path.iterdir()) <= caps.max_disk_bytes
    st.close()


def test_storage_is_private_exclusive_and_outside_git(tmp_path):
    st = CampaignStore(tmp_path, "p", P.PROTOCOL_CAPS)
    st.open_raw("S01")
    assert oct(os.stat(st.path).st_mode & 0o777) == "0o700"
    assert oct(os.stat(st.path / "S01.raw.jsonl").st_mode & 0o777) == "0o600"
    st.close()
    with pytest.raises(FileExistsError):
        CampaignStore(tmp_path, "p", P.PROTOCOL_CAPS)  # a campaign directory is never reused
    with pytest.raises(ValueError, match="INSIDE_GIT_WORKTREE"):
        CampaignStore(HERE, "x", P.PROTOCOL_CAPS)  # this very directory is in the repository
    link = tmp_path / "link"
    os.symlink(tmp_path, link)
    with pytest.raises(ValueError, match="SYMLINK_FREE"):
        CampaignStore(str(link), "y", P.PROTOCOL_CAPS)
    with pytest.raises(ValueError, match="ABSOLUTE"):
        CampaignStore("relative/dir", "y", P.PROTOCOL_CAPS)


def test_closure_is_durable_hash_bound_and_tamper_evident(tmp_path):
    syncs = []

    def fsync(fd):
        syncs.append(fd)
        os.fsync(fd)
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))], store_kw={"fsync": fsync})
    assert res.complete and len(syncs) >= 10  # raw files, every tmp file, the directory after every rename
    v = verify_campaign(path)
    assert v["status"] == "COMPLETE_VERIFIED" and v["problems"] == []
    f = final(path)
    assert set(f["files"]) >= {"S01.raw.jsonl", "S02.raw.jsonl", "s01.receipt.json", "s02.receipt.json", "intent.json"}
    # tamper one byte of a raw file: the final receipt's hash no longer matches
    p = path / "S01.raw.jsonl"
    data = bytearray(p.read_bytes())
    data[50] ^= 1
    p.write_bytes(bytes(data))
    assert verify_campaign(path)["status"] == "CORRUPT"


def test_interrupted_write_is_reported_incomplete_and_the_partial_line_is_never_read(tmp_path):
    _, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))])
    crashed = tmp_path / "crashed"
    shutil.copytree(path, crashed)
    (crashed / "final.receipt.json").unlink()
    raw = (crashed / "S02.raw.jsonl").read_bytes()
    (crashed / "S02.raw.jsonl").write_bytes(raw[: len(raw) - 25])  # torn last line
    (crashed / "s02.receipt.json.tmp").write_bytes(b"{")
    v = verify_campaign(crashed)
    assert v["status"] == "INCOMPLETE"
    assert {"FINAL_RECEIPT_MISSING", "TMP_FILE_PRESENT:s02.receipt.json.tmp", "S02:RAW_PARTIAL_LAST_LINE"} <= set(v["problems"])
    rep = analysis.analyze(crashed)
    assert "S02:RAW_PARTIAL_LAST_LINE" in rep["read_problems"]
    assert rep["sessions"]["S02"]["messages"] == 180  # 181 complete lines minus the torn one; the torn one is not parsed


def test_write_failure_ends_incomplete_but_the_receipt_still_closes_when_the_disk_recovers(tmp_path):
    calls = []

    def flaky(fd, data):
        calls.append(1)
        if len(calls) == 6:
            raise OSError(28, "No space left on device")
        return os.write(fd, data)
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))], store_kw={"write": flaky})
    assert (res.end_reason, res.complete, res.final_receipt_written) == (P.WRITE_FAILED, False, True)
    f = final(path)
    assert f["complete"] is False and f["end_reason"] == P.WRITE_FAILED
    assert verify_campaign(path)["status"] == "INCOMPLETE_BY_RECEIPT"


def test_total_write_failure_leaves_no_final_receipt_and_is_never_reported_complete(tmp_path):
    state = {"n": 0}

    def dying(fd, data):
        state["n"] += 1
        if state["n"] > 6:
            raise OSError(5, "I/O error")
        return os.write(fd, data)
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))], store_kw={"write": dying})
    assert (res.complete, res.final_receipt_written) == (False, False)
    assert any(p.startswith("FINAL_RECEIPT_NOT_WRITTEN") for p in res.problems)
    v = verify_campaign(path)
    assert v["status"] == "INCOMPLETE" and "FINAL_RECEIPT_MISSING" in v["problems"]


def test_short_writes_are_completed_not_truncated(tmp_path):
    def two_bytes(fd, data):
        return os.write(fd, bytes(data[:2]))  # the OS may accept fewer bytes than asked
    st = CampaignStore(tmp_path, "s", P.PROTOCOL_CAPS, write=two_bytes)
    st.open_raw("S01")
    st.append_raw("S01", raw_record("S01", 0, 0, Instant(1, 1), b'{"channel":"heartbeats","sequence_num":0}'))
    st.close()
    assert json.loads((tmp_path / "s" / "S01.raw.jsonl").read_bytes())["idx"] == 0
    st2 = CampaignStore(tmp_path, "z", P.PROTOCOL_CAPS, write=lambda fd, d: 0)  # a zero-byte write can never loop forever
    st2.open_raw("S01")
    with pytest.raises(WriteFailed):
        st2.append_raw("S01", raw_record("S01", 0, 0, Instant(1, 1), b'{"channel":"heartbeats","sequence_num":0}'))
    st2.close()
