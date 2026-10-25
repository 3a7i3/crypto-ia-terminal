"""Whole directory inventory without population/admission authority."""

import dataclasses
import hashlib
import os

import pytest

from colony_admission import formats as f
from colony_admission import observer as o
from tests.colony_admission import test_observer as fixtures
from tests.colony_admission.test_observer import CHILD, entry, log_path, operation, prefix, raw, write

machine = fixtures.machine


def scan(machine):
    result = o.FileObserver(machine[0]).scan()
    assert not result.accepted
    assert result.authorization == result.completeness == result.durability == result.rotation == "NOT_EVALUATED"
    return result


def additional(machine, label="2", *, terminal=False):
    config, base = machine
    child = label * 64
    op = operation(lab_id=config.lab_id, historical_root_sha256=config.root_pin, child_agent_id=child)
    op["birth_plan"]["record"]["agent_id"] = child
    op["birth_plan"]["child_spec"]["agent_id"] = child
    events = prefix(op=op)
    if terminal:
        events.append(entry("REFUSED", op=op))
    write(log_path(config).with_name(child + ".log"), raw(*events))
    return op


def test_complete_sorted_inventory_one_ledger_read_and_immutable_result(machine, monkeypatch):
    config, _ = machine
    additional(machine, "3", terminal=True)
    additional(machine, "2", terminal=True)
    original, calls = o.trust._read_entries, []
    def reader(fd, **kwargs):
        calls.append(os.fstat(fd).st_ino)
        return original(fd, **kwargs)
    monkeypatch.setattr(o.trust, "_read_entries", reader)
    result = scan(machine)
    assert result.status == "OBSERVED", result
    assert [c.child_agent_id for c in result.children] == [CHILD, "2" * 64, "3" * 64]
    assert calls == [config.ledger.stat().st_ino]
    assert len(result.pending_operations) == 1
    batch = f.loads(result.ledger_bytes)
    assert batch["ledger_sha256"] == hashlib.sha256(config.ledger.read_bytes()).hexdigest()
    assert len(batch["observations"]) == 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.children[0].child_agent_id = "bad"


def test_multiple_pending_logs_block_without_resuming(machine):
    additional(machine)
    result = scan(machine)
    assert "OPERATION_PENDING" in result.blockers and len(result.children) == 2
    assert len(result.pending_operations) == 2
    assert all(c.log.recovery_result is None for c in result.children)


def test_corrupt_neighbor_is_not_ignored(machine):
    additional(machine, terminal=True)
    write(log_path(machine[0]).with_name("2" * 64 + ".log"), b"broken\n")
    result = scan(machine)
    assert result.status == "BLOCKED" and "OPERATION_LOG_UNAVAILABLE" in result.blockers
    assert len(result.children) == 2


@pytest.mark.parametrize("raw_log", [b"", b'{"torn":', b"bad"])
def test_invalid_existing_log_blocks_even_without_operation_id(machine, raw_log):
    write(log_path(machine[0]), raw_log)
    result = scan(machine)
    assert result.status == "BLOCKED" and len(result.children) == 1


def test_empty_existing_inventory_still_validates_ledger(machine, monkeypatch):
    log_path(machine[0]).unlink()
    result = scan(machine)
    assert result.status == "OBSERVED" and result.children == () and result.pending_operations == ()
    assert f.loads(result.ledger_bytes)["ledger_entries"] == 0
    write(machine[0].ledger, b"broken\n")
    result = scan(machine)
    assert result.status == "BLOCKED" and not result.sources


@pytest.mark.parametrize("name", ["README", ".hidden", "x.log", "A" * 64 + ".log", CHILD + ".log.tmp"])
def test_unknown_directory_entry_never_silently_ignored(machine, name):
    write(log_path(machine[0]).with_name(name), b"")
    result = scan(machine)
    assert result.blockers == ("OPERATION_NAMESPACE_INVALID",) and result.children == ()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory"])
def test_unsafe_neighbor_blocks_inventory(machine, kind):
    path = log_path(machine[0]).with_name("2" * 64 + ".log")
    if kind == "symlink":
        path.symlink_to(log_path(machine[0]))
    elif kind == "hardlink":
        os.link(log_path(machine[0]), path)
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.mkdir(mode=0o700)
    result = scan(machine)
    assert result.status == "BLOCKED" and result.sources == () and result.children == ()


def test_257_entries_refuse_before_reading_any_log(machine):
    for n in range(256):
        write(log_path(machine[0]).with_name(f"{n:064x}.log"), b"")
    assert scan(machine).blockers == ("OPERATION_LOGS_FULL",)


def test_aggregate_cap_discards_partial_inventory(machine, monkeypatch):
    additional(machine, terminal=True)
    monkeypatch.setattr(o, "MAX_SCAN_BYTES", log_path(machine[0]).stat().st_size)
    result = scan(machine)
    assert result.blockers == ("SOURCE_LIMIT",) and result.children == () and result.sources == ()


def test_duplicate_operation_across_children_not_coalesced(machine):
    write(log_path(machine[0]).with_name("2" * 64 + ".log"), log_path(machine[0]).read_bytes())
    result = scan(machine)
    assert "DUPLICATE_OPERATION" in result.blockers and "OPERATION_BINDING_MISMATCH" in result.blockers


def test_d1_contradiction_in_any_neighbor_blocks(machine):
    op = additional(machine)
    write(log_path(machine[0]).with_name("2" * 64 + ".log"), raw(*prefix(1, op=op)))
    assert "OPERATION_STATE_INCONSISTENT" in scan(machine).blockers


def test_missing_directory_is_not_empty(machine):
    log_path(machine[0]).unlink()
    log_path(machine[0]).parent.rmdir()
    result = scan(machine)
    assert result.status == "BLOCKED" and not result.children


def test_inventory_mutation_between_listings_discards_payload(machine, monkeypatch):
    original, calls = o._names, 0
    def names(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            additional(machine, terminal=True)
        return original(fd)
    monkeypatch.setattr(o, "_names", names)
    result = scan(machine)
    assert result.blockers == ("SOURCE_CHANGED",) and not result.sources and not result.children


def test_selected_observer_now_uses_one_descriptor_pass(machine, monkeypatch):
    original, calls = o.trust._read_entries, []
    def reader(fd, **kwargs):
        calls.append(os.fstat(fd).st_ino)
        return original(fd, **kwargs)
    monkeypatch.setattr(o.trust, "_read_entries", reader)
    monkeypatch.setattr(o.trust, "inspect_operation_consumption", lambda *_a: pytest.fail("path reader reused"))
    assert o.FileObserver(machine[0]).observe(CHILD).status == "OBSERVED"
    assert calls == [machine[0].ledger.stat().st_ino]


def test_256_logs_are_fully_inventoried_at_the_supported_boundary(machine):
    config, _ = machine
    for n in range(255):
        child = f"{n:064x}"
        op = operation(lab_id=config.lab_id, historical_root_sha256=config.root_pin, child_agent_id=child)
        op["birth_plan"]["record"]["agent_id"] = child
        op["birth_plan"]["child_spec"]["agent_id"] = child
        write(log_path(config).with_name(child + ".log"), raw(*prefix(op=op), entry("REFUSED", op=op)))
    result = scan(machine)
    assert result.status == "OBSERVED", result.blockers
    assert len(result.children) == 256 and len(result.pending_operations) == 1
    assert len(f.loads(result.ledger_bytes)["observations"]) == 256


def test_ledger_open_and_byte_stream_are_single_even_for_many_logs(machine, monkeypatch):
    config, op = machine
    write(log_path(config), raw(*prefix(1, op=op)))
    fixtures.spend(config, op)
    additional(machine, terminal=True)
    original_read, original_open = os.read, os.open
    ledger_inode, byte_count, open_count = config.ledger.stat().st_ino, 0, 0
    def read(fd, size):
        nonlocal byte_count
        chunk = original_read(fd, size)
        if os.fstat(fd).st_ino == ledger_inode:
            byte_count += len(chunk)
        return chunk
    def opened(*args, **kwargs):
        nonlocal open_count
        fd = original_open(*args, **kwargs)
        if os.fstat(fd).st_ino == ledger_inode:
            open_count += 1
        return fd
    monkeypatch.setattr(o.os, "read", read)
    monkeypatch.setattr(o.os, "open", opened)
    assert scan(machine).status == "OBSERVED"
    assert open_count == 1 and byte_count == config.ledger.stat().st_size


def test_empty_inventory_with_legacy_ledger_is_explicitly_ambiguous(machine):
    from tests.colony_trust.test_operation_inspection import ledger, row
    log_path(machine[0]).unlink()
    ledger(machine[0].ledger, row(legacy=True))
    assert scan(machine).blockers == ("LEGACY_LEDGER_UNBOUND",)


def test_scan_close_error_discards_entire_provisional_inventory(machine, monkeypatch):
    original = os.close
    def close(fd):
        original(fd)
        raise OSError("synthetic close failure")
    monkeypatch.setattr(o.os, "close", close)
    result = scan(machine)
    assert result.status == "BLOCKED" and not result.children and not result.sources
    assert result.ledger_bytes is None


def test_terminal_birth_with_pending_set_aside_is_not_an_open_birth(machine):
    config, op = machine
    fixtures.spend(config, op)
    events = prefix(3, op=op) + [entry("TERMINATED", op=op, code="OPERATOR_TERMINATED"),
                                entry("FAILED_CONSUMED", op=op, code="OPERATOR_TERMINATED"),
                                entry("SET_ASIDE_BEGIN", "D3", op=op)]
    write(log_path(config), raw(*events))
    other = additional(machine)
    result = scan(machine)
    assert result.status == "OBSERVED", result.blockers
    assert result.pending_operations == (f.digest(other),)
    assert result.children[0].log.status == "SETTING_ASIDE"
    assert result.children[0].log.terminal_claim == "FAILED_CONSUMED"
