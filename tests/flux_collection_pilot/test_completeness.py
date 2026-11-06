"""Review findings on #564: a campaign is complete only with a usable snapshot per session,
and the verifier never believes complete=true without the whole, consistent campaign."""

import hashlib
import json
import shutil

import pytest

from observability.flux_collection_pilot import analysis, protocol as P
from observability.flux_collection_pilot.simulated import BOOK0
from observability.flux_collection_pilot.store import REQUIRED_COMPLETE_FILES, verify_campaign
from .helpers import final, healthy_items, run, script


def nominal(tmp_path, cid="n"):
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))], cid=cid)
    assert res.complete
    return path


def rewrite(path, name, mutate, relist=False):
    p = path / name
    doc = json.loads(p.read_bytes())
    mutate(doc)
    data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    p.write_bytes(data)
    if relist:  # a forger who also fixes the final inventory hashes
        f = json.loads((path / "final.receipt.json").read_bytes())
        f["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        f["bytes_written"] = sum(m["bytes"] for m in f["files"].values())
        (path / "final.receipt.json").write_bytes(json.dumps(f, sort_keys=True, separators=(",", ":")).encode() + b"\n")


# --- 1. reconnection without a snapshot is never a complete campaign ----------------------------------
def test_reconnection_without_snapshot_is_incomplete_through_runner_receipt_and_verifier(tmp_path):
    res, factory, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130, snapshot=False))])
    assert len(factory.built) == 2 and res.end_reason == P.DURATION_CAP  # the run did reach its duration cap...
    assert res.complete is False                                        # ...but is NOT declared complete
    f = final(path)
    assert f["complete"] is False and f["incomplete_reasons"] == ["SESSION_WITHOUT_SNAPSHOT:S02"]
    assert json.loads((path / "s02.receipt.json").read_bytes())["snapshots"] == 0
    v = verify_campaign(path)
    assert v["status"] == "INCOMPLETE_BY_RECEIPT" and v["status"] != "COMPLETE_VERIFIED"


def test_a_forged_complete_flag_on_a_snapshotless_campaign_is_refused_by_the_verifier(tmp_path):
    _, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130, snapshot=False))])
    rewrite(path, "final.receipt.json", lambda d: d.update(complete=True))
    v = verify_campaign(path)
    assert v["status"] == "INCOMPLETE" and "SESSION_WITHOUT_SNAPSHOT:S02" in v["problems"]


def test_a_snapshot_in_each_session_keeps_the_nominal_campaign_complete(tmp_path):
    path = nominal(tmp_path)
    assert verify_campaign(path) == {**verify_campaign(path), "status": "COMPLETE_VERIFIED", "problems": []}
    assert final(path)["incomplete_reasons"] == []


# --- 1 bis. an EMPTY or ONE-SIDED snapshot is not a usable snapshot --------------------------------------
def _with_book(levels, seconds=130):
    items = [it for it in healthy_items(seconds, snapshot=False)]
    items.append((P.S // 10, lambda f: f.snapshot(levels)))
    return script(items)


@pytest.mark.parametrize("levels", [[], [("bid", "100", "1")], [("offer", "101", "1")]],
                         ids=["empty", "bid-only", "offer-only"])
def test_reconnection_followed_only_by_an_unusable_snapshot_is_never_complete(tmp_path, levels):
    res, factory, path = run(tmp_path, [script(healthy_items(62)), _with_book(levels)])
    assert len(factory.built) == 2 and res.end_reason == P.DURATION_CAP
    assert res.complete is False
    f = final(path)
    assert f["complete"] is False and f["incomplete_reasons"] == ["SESSION_WITHOUT_SNAPSHOT:S02"]
    r2 = json.loads((path / "s02.receipt.json").read_bytes())
    assert r2["snapshots"] == 0 and r2["snapshot_events"] == 1  # the event is labelled, not counted as usable
    v = verify_campaign(path)
    assert v["status"] != "COMPLETE_VERIFIED"


def _replay_book(path, sid):
    return analysis.analyze(path)["sessions"][sid]["book"]


@pytest.mark.parametrize("levels,reason", [
    ([], "SNAPSHOT_EMPTY"),
    ([("bid", "100", "1")], "SNAPSHOT_ONE_SIDED"),
    ([("offer", "101", "1")], "SNAPSHOT_ONE_SIDED"),
    ([("bid", "102", "1"), ("offer", "101", "1")], "SNAPSHOT_CROSSED_OR_LOCKED"),
    ([("bid", "101", "1"), ("offer", "101", "1")], "SNAPSHOT_CROSSED_OR_LOCKED"),
], ids=["empty", "bid-only", "offer-only", "crossed", "locked"])
def test_runner_verifier_and_replay_share_one_snapshot_criterion(tmp_path, levels, reason):
    """Reconnection followed by an unusable snapshot, THEN L2 updates: all three layers agree."""
    res, _, path = run(tmp_path, [script(healthy_items(62)), _with_book(levels)])
    assert res.complete is False
    assert final(path)["incomplete_reasons"] == ["SESSION_WITHOUT_SNAPSHOT:S02"]
    assert verify_campaign(path)["status"] != "COMPLETE_VERIFIED"
    book = _replay_book(path, "S02")
    assert book["final_state"] == "INVALID" and book["final_reason"] == reason
    assert book["publications"] == 0 and book["snapshots_applied"] == 0      # updates waited, nothing published
    assert book["updates_ignored_without_valid_book"] > 0
    assert _replay_book(path, "S01")["final_state"] == "LIVE"                # the healthy session is untouched


def test_a_valid_snapshot_after_an_unusable_one_restores_the_book(tmp_path):
    items = healthy_items(130, snapshot=False)
    items.append((P.S // 10, lambda f: f.snapshot([])))
    items.append((P.S // 10 + 5, lambda f: f.snapshot(BOOK0)))
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(items)])
    assert res.complete is True and verify_campaign(path)["status"] == "COMPLETE_VERIFIED"
    assert _replay_book(path, "S02")["final_state"] == "LIVE"


def test_a_forged_complete_flag_and_forged_counter_do_not_make_an_empty_snapshot_usable(tmp_path):
    _, _, path = run(tmp_path, [script(healthy_items(62)), _with_book([])])
    rewrite(path, "s02.receipt.json", lambda d: d.update(snapshots=1), relist=True)
    rewrite(path, "final.receipt.json", lambda d: d.update(complete=True))
    v = verify_campaign(path)
    assert v["status"] == "INCOMPLETE"
    assert "SESSION_SNAPSHOT_COUNT_MISMATCH:S02" in v["problems"] or "SESSION_WITHOUT_SNAPSHOT:S02" in v["problems"]


# --- 2. the verifier demands the whole campaign -----------------------------------------------------------
def test_an_empty_inventory_is_not_a_complete_campaign(tmp_path):
    d = tmp_path / "forged"
    d.mkdir()
    (d / "final.receipt.json").write_text('{"complete":true,"files":{}}')
    v = verify_campaign(d)
    assert v["status"] == "INCOMPLETE" and v["sessions"] == {}
    assert "FILE_INVENTORY_EMPTY" in v["problems"]
    assert {"REQUIRED_FILE_NOT_LISTED:" + n for n in REQUIRED_COMPLETE_FILES} <= set(v["problems"])


@pytest.mark.parametrize("name", REQUIRED_COMPLETE_FILES)
def test_each_required_piece_missing_is_refused_whether_or_not_the_inventory_still_lists_it(tmp_path, name):
    path = nominal(tmp_path)
    (path / name).unlink()
    assert "LISTED_FILE_MISSING:" + name in verify_campaign(path)["problems"]       # inventory still lists it
    assert verify_campaign(path)["status"] != "COMPLETE_VERIFIED"
    rewrite(path, "final.receipt.json", lambda d: d["files"].pop(name))              # forger removes the listing too
    v = verify_campaign(path)
    assert "REQUIRED_FILE_NOT_LISTED:" + name in v["problems"] and v["status"] != "COMPLETE_VERIFIED"


@pytest.mark.parametrize("label, name, mutate, relist, expected", [
    ("final message counter", "final.receipt.json", lambda d: d.update(messages=d["messages"] + 1), False, "MESSAGE_COUNT_MISMATCH"),
    ("final connection counter", "final.receipt.json", lambda d: d.update(connections_opened=1), False, "CONNECTION_COUNT_MISMATCH"),
    ("final bytes counter", "final.receipt.json", lambda d: d.update(bytes_written=d["bytes_written"] + 1), False, "BYTES_WRITTEN_MISMATCH"),
    ("session message counter, hashes fixed", "s01.receipt.json", lambda d: d.update(messages=d["messages"] + 1), True, "SESSION_MESSAGE_COUNT_MISMATCH:S01"),
    ("session raw digest, hashes fixed", "s02.receipt.json", lambda d: d["raw"].update(sha256="0" * 64), True, "SESSION_RAW_DIGEST_MISMATCH:S02"),
    ("session raw line counter, hashes fixed", "s02.receipt.json", lambda d: d["raw"].update(lines=d["raw"]["lines"] - 1), True, "SESSION_MESSAGE_COUNT_MISMATCH:S02"),
    ("session id", "s02.receipt.json", lambda d: d.update(session="S01"), True, "SESSION_ID_MISMATCH:S02"),
    ("session end reason", "s01.receipt.json", lambda d: d.update(end_reason="DURATION_CAP"), True, "SESSION_END_REASON_MISMATCH"),
    ("snapshot counter zeroed, hashes fixed", "s01.receipt.json", lambda d: d.update(snapshots=0), True, "SESSION_SNAPSHOT_COUNT_MISMATCH:S01"),
    ("non-completing end reason", "final.receipt.json", lambda d: d.update(end_reason="MESSAGE_CAP"), False, "END_REASON_NOT_COMPLETING"),
])
def test_inconsistent_counters_are_refused(tmp_path, label, name, mutate, relist, expected):
    path = nominal(tmp_path)
    assert verify_campaign(path)["status"] == "COMPLETE_VERIFIED"  # control: the same directory passes before the change
    rewrite(path, name, mutate, relist=relist)
    v = verify_campaign(path)
    assert expected in v["problems"], (label, v["problems"])
    assert v["status"] != "COMPLETE_VERIFIED"


def test_an_unlisted_extra_file_is_refused(tmp_path):
    path = nominal(tmp_path)
    (path / "S03.raw.jsonl").write_bytes(b"")
    assert "FILE_NOT_IN_INVENTORY:S03.raw.jsonl" in verify_campaign(path)["problems"]


def test_a_copy_of_the_nominal_campaign_still_verifies(tmp_path):
    path = nominal(tmp_path)
    copy = tmp_path / "copy"
    shutil.copytree(path, copy)
    assert verify_campaign(copy)["status"] == "COMPLETE_VERIFIED"
