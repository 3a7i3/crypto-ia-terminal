"""Weaker operation-only observations never authenticate or authorize a birth."""

import fcntl
import hashlib
import os
from pathlib import Path

import pytest

from colony_trust import trust

OP = "a" * 64
OTHER = "b" * 64


def row(label="one", *, operation=OP, legacy=False, **changes):
    result = {"ledger_schema": trust.LEDGER_SCHEMA if legacy else trust.OPERATION_LEDGER_SCHEMA,
              "issuer_id": "fixture-issuer", "envelope_id": hashlib.sha256(label.encode()).hexdigest(),
              "envelope_sha256": "c" * 64}
    if not legacy:
        result["operation_sha256"] = operation
    return {**result, **changes}


def ledger(path, *entries):
    path.write_bytes(b"".join(trust._canonical(e) + b"\n" for e in entries))
    path.chmod(0o600)
    return path


def inspect(path, op=OP):
    result = trust.inspect_operation_consumption(path, op)
    assert set(result) == {"inspection_schema", "status", "operation_sha256", "operation_entries",
                           "legacy_entries", "ledger_entries", "ledger_sha256", "entry", "failures",
                           "accepted", "authenticity", "authorization", "completeness", "provenance", "durability"}
    assert result["inspection_schema"] == "colony-trust.operation-inspection/0"
    assert result["accepted"] is False
    assert [result[k] for k in ("authenticity", "authorization", "completeness", "provenance", "durability")] == ["NOT_EVALUATED"] * 5
    return result


def full(path, status, count, legacy, total):
    result = inspect(path)
    assert result["status"] == status
    assert result["operation_entries"] == count and result["legacy_entries"] == legacy
    assert result["ledger_entries"] == total
    assert result["ledger_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert 0 <= count + legacy <= total
    assert (result["entry"] is not None) == (status == "OPERATION_ENTRY_PRESENT")
    return result


def unavailable(result, status):
    assert result["status"] == status
    for key in ("operation_entries", "legacy_entries", "ledger_entries", "ledger_sha256", "entry"):
        assert result[key] is None


def test_missing_existing_empty_and_missing_parent_distinct(tmp_path):
    path = tmp_path / "ledger"
    unavailable(inspect(path), "LEDGER_MISSING")
    assert not path.exists() and not list(tmp_path.iterdir())
    full(ledger(path), "NO_OPERATION_ENTRY", 0, 0, 0)
    unavailable(inspect(tmp_path / "missing" / "ledger"), "LEDGER_UNAVAILABLE")
    assert not (tmp_path / "missing").exists()


def test_unrelated_operation_cannot_prove_an_unknown_envelope_fresh(tmp_path):
    path = ledger(tmp_path / "ledger", row(operation=OTHER))
    result = full(path, "NO_OPERATION_ENTRY", 0, 0, 1)
    assert result["failures"] == []
    # The same envelope id is spent; only its operation differs. No freshness claim.
    assert result["authorization"] == "NOT_EVALUATED"


@pytest.mark.parametrize("legacy", [False, True])
def test_one_operation_entry_is_not_an_expected_envelope_match(tmp_path, legacy):
    entries = [row()]
    if legacy:
        entries.append(row("old", legacy=True))
    result = full(ledger(tmp_path / "ledger", *entries), "OPERATION_ENTRY_PRESENT", 1, int(legacy), len(entries))
    assert result["entry"] == row() and result["failures"] == []
    assert result["status"] != "CONSUMED_BY_OPERATION"


@pytest.mark.parametrize("other", [False, True])
def test_legacy_without_matching_operation_is_ambiguous(tmp_path, other):
    entries = [row(legacy=True)] + ([row("other", operation=OTHER)] if other else [])
    result = full(ledger(tmp_path / "ledger", *entries), "LEGACY_AMBIGUITY", 0, 1, len(entries))
    assert result["failures"] == ["LEGACY_OPERATION_UNBOUND"]


@pytest.mark.parametrize("legacy", [False, True])
def test_multiplicity_overrides_legacy_and_never_selects_one(tmp_path, legacy):
    entries = [row("one"), row("two")] + ([row("old", legacy=True)] if legacy else [])
    result = full(ledger(tmp_path / "ledger", *entries), "CONFLICT", 2, int(legacy), len(entries))
    assert result["failures"] == ["OPERATION_MULTIPLE_ENTRIES"]
    assert result["entry"] is None


@pytest.mark.parametrize("legacy", [False, True])
def test_duplicate_issuer_id_is_corruption_not_multiplicity(tmp_path, legacy):
    path = ledger(tmp_path / "ledger", row(), row(legacy=legacy))
    unavailable(inspect(path), "LEDGER_CORRUPT")


@pytest.mark.parametrize("tail", [b"bad\n", b"{}\n", b'{"torn":', b"{ }\n", b"\xff\n",
                                  b'{"ledger_schema":true}\n', b"\n"])
@pytest.mark.parametrize("matching", [False, True])
def test_entire_ledger_validated_before_any_zero_or_match(tmp_path, tail, matching):
    path = ledger(tmp_path / "ledger", row(operation=OP if matching else OTHER))
    path.write_bytes(path.read_bytes() + tail)
    unavailable(inspect(path), "LEDGER_CORRUPT")


@pytest.mark.parametrize("changes", [{"ledger_schema": "future/9"}, {"extra": "x"}, {"operation_sha256": "BAD"},
                                     {"issuer_id": "bad space"}, {"envelope_id": True}, {"envelope_sha256": "A" * 64}])
def test_shared_parser_shape_rules(tmp_path, changes):
    unavailable(inspect(ledger(tmp_path / "ledger", row(**changes))), "LEDGER_CORRUPT")


@pytest.mark.parametrize("op", [None, True, 0, [], {}, "bad", "A" * 64, "a" * 65])
def test_invalid_operation_before_any_io(tmp_path, monkeypatch, op):
    def never(*args, **kwargs):
        raise AssertionError("invalid operation reached filesystem")
    monkeypatch.setattr(trust.os, "open", never)
    monkeypatch.setattr(trust.os, "stat", never)
    result = inspect(tmp_path / "ledger", op)
    unavailable(result, "INVALID_INPUT")
    assert result["operation_sha256"] is None and result["failures"] == ["OPERATION_INVALID"]


@pytest.mark.parametrize("path", [None, "ledger", 1, {}])
def test_invalid_path_before_open(monkeypatch, path):
    def never(*args, **kwargs):
        raise AssertionError("invalid path reached open")
    monkeypatch.setattr(trust.os, "open", never)
    result = inspect(path)
    unavailable(result, "LEDGER_UNAVAILABLE")
    assert result["operation_sha256"] == OP


def test_symlink_parent_is_unavailable_even_with_existing_final_file(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    ledger(real / "ledger", row())
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    unavailable(inspect(alias / "ledger"), "LEDGER_UNAVAILABLE")


def test_no_mutations_and_exact_read_only_inode_flags(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    before, names = path.read_bytes(), list(tmp_path.iterdir())
    real_open, real_lock, seen = trust.os.open, trust.fcntl.flock, []
    def opened(target, flags, *args, **kwargs):
        assert flags & os.O_ACCMODE == os.O_RDONLY
        assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
        assert not flags & (os.O_CREAT | os.O_APPEND | os.O_TRUNC)
        seen.append("open")
        return real_open(target, flags, *args, **kwargs)
    def locked(fd, flags):
        assert flags == fcntl.LOCK_SH | fcntl.LOCK_NB
        seen.append("lock")
        return real_lock(fd, flags)
    def never(*args, **kwargs):
        raise AssertionError("mutation attempted")
    with monkeypatch.context() as patch:
        patch.setattr(trust.os, "open", opened)
        patch.setattr(trust.fcntl, "flock", locked)
        for method in ("write", "fsync", "chmod", "mkdir", "rename", "replace", "unlink", "truncate"):
            patch.setattr(trust.os, method, never)
        assert inspect(path)["status"] == "OPERATION_ENTRY_PRESENT"
    assert seen == ["open", "lock"]
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == names


def test_lock_contention_and_shared_readers(tmp_path):
    path = ledger(tmp_path / "ledger", row())
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unavailable(inspect(path), "LEDGER_BUSY")
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        assert inspect(path)["status"] == "OPERATION_ENTRY_PRESENT"
    finally:
        os.close(fd)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("site", ["open", "read", "lseek", "close"])
def test_io_fault_discards_all_snapshot_fields(tmp_path, monkeypatch, site):
    path = ledger(tmp_path / "ledger", row())
    real = getattr(trust.os, site)
    def fail(*args, **kwargs):
        if site == "close":
            real(*args, **kwargs)
        raise OSError("not echoed")
    monkeypatch.setattr(trust.os, site, fail)
    result = inspect(path)
    unavailable(result, "LEDGER_UNAVAILABLE")
    assert result["failures"] == ["LEDGER_UNAVAILABLE"]


def test_read_eagain_is_io_not_lock_contention(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    def fail(*args):
        raise BlockingIOError("read EAGAIN")
    monkeypatch.setattr(trust.os, "read", fail)
    unavailable(inspect(path), "LEDGER_UNAVAILABLE")


def test_non_regular_private_and_single_link_requirements(tmp_path):
    path = ledger(tmp_path / "ledger", row())
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    unavailable(inspect(alias), "LEDGER_UNAVAILABLE")
    alias.unlink()
    os.link(path, alias)
    unavailable(inspect(path), "LEDGER_CORRUPT")
    alias.unlink()
    path.chmod(0o644)
    unavailable(inspect(path), "LEDGER_CORRUPT")
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    unavailable(inspect(fifo), "LEDGER_CORRUPT")
    unavailable(inspect(Path("/dev/zero")), "LEDGER_CORRUPT")
    unavailable(inspect(tmp_path), "LEDGER_CORRUPT")


def test_bounds_include_complete_bytes_and_entry_limits(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row(), row("second", operation=OTHER))
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", path.stat().st_size)
    assert inspect(path)["status"] == "OPERATION_ENTRY_PRESENT"
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", path.stat().st_size - 1)
    result = inspect(path)
    unavailable(result, "LEDGER_UNAVAILABLE")
    assert result["failures"] == ["LEDGER_TOO_LARGE"]
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", 16 << 20)
    monkeypatch.setattr(trust, "INSPECTION_MAX_ENTRIES", 1)
    unavailable(inspect(path), "LEDGER_UNAVAILABLE")


def test_streaming_growth_bound_not_only_stat(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    real = trust.os.fstat
    def understated(fd):
        values = list(real(fd))
        values[6] = 0
        return os.stat_result(values)
    monkeypatch.setattr(trust.os, "fstat", understated)
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", 1)
    result = inspect(path)
    unavailable(result, "LEDGER_UNAVAILABLE")
    assert result["failures"] == ["LEDGER_TOO_LARGE"]


def test_hash_fingerprints_all_bytes_from_single_descriptor_pass(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row(), row("second", operation=OTHER))
    before = path.read_bytes()
    calls, real_open, real_read = [], trust.os.open, trust.os.read
    def opened(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        calls.append(fd)
        return fd
    def chunks(fd, size):
        assert calls == [fd]  # no second descriptor read for the fingerprint
        return real_read(fd, min(size, 17))
    with monkeypatch.context() as patch:
        patch.setattr(trust.os, "open", opened)
        patch.setattr(trust.os, "read", chunks)
        first = inspect(path)
    assert len(calls) == 1 and first["ledger_sha256"] == hashlib.sha256(before).hexdigest()
    ledger(path, row(), row("different", operation=OTHER))
    second = inspect(path)
    assert second["ledger_entries"] == first["ledger_entries"]
    assert second["operation_entries"] == first["operation_entries"]
    assert second["ledger_sha256"] != first["ledger_sha256"]


def test_returned_entry_detached_and_other_apis_unchanged(tmp_path):
    from tests.colony_trust.test_inspection import envelope, inspect as expected_inspect
    from tests.colony_trust.test_operations import consume
    path = tmp_path / "ledger"
    assert consume(path)["accepted"]
    before = path.read_bytes()
    result = inspect(path)
    result["entry"]["operation_sha256"] = OTHER
    assert inspect(path)["entry"]["operation_sha256"] == OP
    assert expected_inspect(path)["status"] == "CONSUMED_BY_OPERATION"
    assert trust.verify_consumed(envelope(), path, OP)["consumed"]
    assert path.read_bytes() == before


def test_parent_lost_during_missing_open_is_not_missing_file_evidence(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "ledger"
    real = trust.os.open
    def disappear(target, *args, **kwargs):
        parent.rmdir()  # simulate an external namespace race, not an inspector mutation
        return real(target, *args, **kwargs)
    monkeypatch.setattr(trust.os, "open", disappear)
    unavailable(inspect(path), "LEDGER_UNAVAILABLE")
