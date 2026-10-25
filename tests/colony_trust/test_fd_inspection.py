"""A borrowed descriptor is read once for a bounded batch, never authorized."""

import fcntl
import hashlib
import os

import pytest

from colony_trust import trust as t
from tests.colony_trust.test_operation_inspection import OP, OTHER, ledger, row


def inspect(path, ops=(OP,)):
    with path.open("rb") as stream:
        result = t.inspect_operations_fd(stream.fileno(), ops)
        assert not stream.closed
        assert result["accepted"] is False
        assert all(result[name] == "NOT_EVALUATED" for name in
                   ("authenticity", "authorization", "completeness", "provenance", "durability"))
        return result


def invalid(result, status):
    assert result["status"] == status
    assert result["observations"] == [] and result["ledger_sha256"] is None
    assert result["ledger_entries"] is None and result["legacy_entries"] is None


@pytest.mark.parametrize("ops", [(), (OP,), (OP, OTHER)])
def test_batch_uses_one_full_strict_parse_and_same_snapshot(tmp_path, monkeypatch, ops):
    path = ledger(tmp_path / "ledger", row())
    original, calls = t._read_entries, []
    def read(fd, **kwargs):
        calls.append((os.fstat(fd).st_ino, kwargs))
        return original(fd, **kwargs)
    monkeypatch.setattr(t, "_read_entries", read)
    result = inspect(path, ops)
    assert result["status"] == "OBSERVED" and len(calls) == 1
    assert calls[0][0] == path.stat().st_ino
    assert result["ledger_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [x["operation_sha256"] for x in result["observations"]] == list(ops)
    for actual, op in zip(result["observations"], ops):
        assert actual == t.inspect_operation_consumption(path, op)


@pytest.mark.parametrize("entries", [(row(legacy=True),), (row(), row("two")), (row(), row("old", legacy=True))])
def test_existing_ambiguity_and_conflict_semantics_preserved(tmp_path, entries):
    path = ledger(tmp_path / "ledger", *entries)
    result = inspect(path, (OP, OTHER))
    assert result["status"] == "OBSERVED"
    assert result["observations"] == [t.inspect_operation_consumption(path, op) for op in (OP, OTHER)]


@pytest.mark.parametrize("ops", [None, [], (OP, OP), (True,), ("x",), tuple(f"{n:064x}" for n in range(257))])
def test_invalid_operations_perform_no_io(monkeypatch, ops):
    monkeypatch.setattr(t.os, "fstat", lambda *_: pytest.fail("invalid batch performed IO"))
    invalid(t.inspect_operations_fd(7, ops), "INVALID_INPUT")


@pytest.mark.parametrize("fd", [True, -1, None, "4"])
def test_invalid_descriptor_type(fd):
    invalid(t.inspect_operations_fd(fd, ()), "INVALID_INPUT")


def test_writable_nonzero_offset_and_linked_descriptors_refuse(tmp_path):
    path = ledger(tmp_path / "ledger", row())
    with path.open("r+b") as stream:
        invalid(t.inspect_operations_fd(stream.fileno(), (OP,)), "LEDGER_CORRUPT")
    with path.open("rb") as stream:
        stream.read(1)
        invalid(t.inspect_operations_fd(stream.fileno(), (OP,)), "LEDGER_CORRUPT")
    os.link(path, tmp_path / "other")
    invalid(inspect(path), "LEDGER_CORRUPT")


@pytest.mark.parametrize("mode", [0o644, 0o400, 0o660])
def test_private_mode_required(tmp_path, mode):
    path = ledger(tmp_path / "ledger")
    path.chmod(mode)
    invalid(inspect(path), "LEDGER_CORRUPT")


def test_owner_checked(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger")
    monkeypatch.setattr(t.os, "geteuid", lambda: 999999)
    invalid(inspect(path), "LEDGER_CORRUPT")


def test_busy_l2_does_not_unlock_other_description(tmp_path):
    path = ledger(tmp_path / "ledger")
    with path.open("rb") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        invalid(inspect(path), "LEDGER_BUSY")
        # The other independently opened lock remains exclusive.
        invalid(inspect(path), "LEDGER_BUSY")


def test_lock_released_descriptor_not_closed_and_no_reopen(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    with path.open("rb") as stream:
        monkeypatch.setattr(t.os, "open", lambda *_a, **_k: pytest.fail("path reopened"))
        result = t.inspect_operations_fd(stream.fileno(), (OP,))
        assert result["status"] == "OBSERVED"
        assert os.fstat(stream.fileno()).st_ino == path.stat().st_ino
        assert stream.tell() == path.stat().st_size
        with path.open("rb") as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("raw", [b"broken\n", b"{}", b"{}\n", b"\n"])
def test_corrupt_whole_input_has_no_prefix(tmp_path, raw):
    path = ledger(tmp_path / "ledger", row())
    path.write_bytes(path.read_bytes() + raw)
    invalid(inspect(path), "LEDGER_CORRUPT")


def test_byte_and_entry_bounds(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    monkeypatch.setattr(t, "INSPECTION_MAX_BYTES", 1)
    invalid(inspect(path), "LEDGER_UNAVAILABLE")
    monkeypatch.setattr(t, "INSPECTION_MAX_BYTES", 16 * 1024 * 1024)
    monkeypatch.setattr(t, "INSPECTION_MAX_ENTRIES", 0)
    invalid(inspect(path), "LEDGER_UNAVAILABLE")


@pytest.mark.parametrize("where", ["read", "unlock"])
def test_io_or_unlock_failure_discards_payload(tmp_path, monkeypatch, where):
    path = ledger(tmp_path / "ledger", row())
    original = t.fcntl.flock
    def flock(fd, flags):
        if flags == fcntl.LOCK_UN and where == "unlock":
            raise OSError("synthetic unlock error")
        return original(fd, flags)
    monkeypatch.setattr(t.fcntl, "flock", flock)
    if where == "read":
        monkeypatch.setattr(t.os, "read", lambda *_: (_ for _ in ()).throw(OSError("synthetic")))
    invalid(inspect(path), "LEDGER_UNAVAILABLE")


def test_inode_metadata_change_during_read_refuses(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    original = t._read_entries
    def read(fd, **kwargs):
        value = original(fd, **kwargs)
        path.chmod(0o644)
        return value
    monkeypatch.setattr(t, "_read_entries", read)
    invalid(inspect(path), "LEDGER_CORRUPT")


def test_borrowed_descriptor_is_never_repositioned(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", row())
    original, calls = os.lseek, []
    def seek(fd, offset, whence):
        calls.append((offset, whence))
        return original(fd, offset, whence)
    monkeypatch.setattr(t.os, "lseek", seek)
    assert inspect(path)["status"] == "OBSERVED"
    assert calls == [(0, os.SEEK_CUR)]
