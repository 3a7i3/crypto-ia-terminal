"""Real-file diagnostic acquisition, with no admission or recovery authority."""

import dataclasses
import fcntl
import hashlib
import os
from pathlib import Path

import pytest

from colony_admission import formats as f
from colony_admission import observer as o
from tests.colony_admission.test_external_evidence import installed
from tests.colony_admission.test_oplog import entry as fixture_entry
from tests.colony_admission.test_oplog import operation, raw
from tests.colony_trust.keys import LAB

CHILD = "1" * 64


def entry(event, step=None, *, op, **changes):
    return fixture_entry(event, step, op=op, current_root_sha256=op["historical_root_sha256"],
                         current_root_version=op["historical_root_version"], **changes)


def prefix(level=0, *, op):
    result = [entry("PREPARED", op=op)]
    for k in range(1, level + 1):
        result += [entry("BEGIN", f"D{k}", op=op), entry("DONE", f"D{k}", op=op)]
    return result


def write(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


@pytest.fixture
def machine(tmp_path):
    for name in ("lab", "ledger", "trust", "faults", "checkout"):
        (tmp_path / name).mkdir(mode=0o700)
    (tmp_path / "lab/admission-ops").mkdir(mode=0o700)
    policy, history = installed()
    config = o.ObserverConfig(tmp_path / "lab", tmp_path / "ledger/consumed.log", tmp_path / "trust",
                              tmp_path / "faults/fault.log", tmp_path / "checkout", LAB, policy["pin"], 1)
    write(config.lab_root / "registrar.lock", b"")
    write(config.fault_file, b"")
    write(config.trust_directory / "policy.json", f.canonical(policy))
    write(config.trust_directory / "trust-history.log", f.canonical(history) + b"\n")
    write(config.ledger, b"")
    op = operation(lab_id=LAB, historical_root_sha256=policy["pin"])
    write(config.lab_root / "admission-ops" / (CHILD + ".log"), raw(*prefix(op=op)))
    return config, op


def observe(machine):
    return o.FileObserver(machine[0]).observe(CHILD)


def log_path(config):
    return config.lab_root / "admission-ops" / (CHILD + ".log")


def spend(config, op, **changes):
    value = {"ledger_schema": "colony-trust.consumed/1", "issuer_id": "fixture-issuer",
             "envelope_id": "c" * 64, "envelope_sha256": op["presented"]["admission"]["envelope_sha256"],
             "operation_sha256": f.digest(op), **changes}
    write(config.ledger, f.canonical(value) + b"\n")


def test_valid_sources_are_readonly_immutable_and_never_authority(machine):
    config, _ = machine
    paths = [p for p in config.lab_root.parent.rglob("*") if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths}
    result = observe(machine)
    assert result.status == "OBSERVED", result
    assert result.root_status == "CURRENT_ROOT_VALIDATED"
    assert result.provenance == "BOUND_FILES_OBSERVED"
    assert not result.accepted
    assert result.authorization == result.completeness == result.durability == result.rotation == "NOT_EVALUATED"
    assert len(result.sources) == 6
    assert {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths} == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = "PASS"
    assert f.loads(result.ledger_bytes)["status"] == "NO_OPERATION_ENTRY"


@pytest.mark.parametrize("field", ["root_pin", "minimum_root_version", "lab_id"])
def test_invalid_constructor_binding(machine, field):
    config, _ = machine
    value = {"root_pin": "bad", "minimum_root_version": True, "lab_id": "../escape"}[field]
    with pytest.raises((o._Blocked, f.FormatError)):
        o.FileObserver(dataclasses.replace(config, **{field: value}))


@pytest.mark.parametrize("field", ["lab_root", "ledger", "trust_directory", "fault_file", "checkout_root"])
def test_relative_paths_refused(machine, field):
    with pytest.raises(o._Blocked):
        o.FileObserver(dataclasses.replace(machine[0], **{field: Path("relative")}))


def test_overlapping_namespaces_refused(machine):
    config, _ = machine
    with pytest.raises(o._Blocked):
        o.FileObserver(dataclasses.replace(config, fault_file=config.lab_root / "fault.log"))
    with pytest.raises(o._Blocked):
        o.FileObserver(dataclasses.replace(config, checkout_root=config.trust_directory))


@pytest.mark.parametrize("label", ["lock", "fault", "policy", "history", "log", "ledger"])
def test_missing_source_never_created_or_healthy(machine, label):
    config, _ = machine
    path = {"lock": config.lab_root / "registrar.lock", "fault": config.fault_file,
            "policy": config.trust_directory / "policy.json", "history": config.trust_directory / "trust-history.log",
            "log": log_path(config), "ledger": config.ledger}[label]
    path.unlink()
    result = observe(machine)
    assert result.status == "BLOCKED" and not result.sources and result.log is None
    assert not path.exists()


@pytest.mark.parametrize("label", ["fault", "policy", "log", "ledger"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "public"])
def test_unsafe_leaf_refused(machine, label, kind):
    config, _ = machine
    path = {"fault": config.fault_file, "policy": config.trust_directory / "policy.json",
            "log": log_path(config), "ledger": config.ledger}[label]
    saved = path.with_name("saved")
    path.rename(saved)
    if kind == "symlink":
        path.symlink_to(saved)
    elif kind == "hardlink":
        os.link(saved, path)
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    else:
        write(path, saved.read_bytes())
        path.chmod(0o644)
    assert observe(machine).status == "BLOCKED"


@pytest.mark.parametrize("label", ["lab", "trust", "ops", "ancestor"])
def test_symlink_directory_components_refused(machine, label):
    config, _ = machine
    if label == "ancestor":
        alias = config.lab_root.parent / "alias"
        alias.symlink_to(config.lab_root.parent, target_is_directory=True)
        config = dataclasses.replace(config, lab_root=alias / "lab")
    else:
        path = {"lab": config.lab_root, "trust": config.trust_directory,
                "ops": config.lab_root / "admission-ops"}[label]
        saved = path.with_name(path.name + "-saved")
        path.rename(saved)
        path.symlink_to(saved, target_is_directory=True)
    assert o.FileObserver(config).observe(CHILD).status == "BLOCKED"


def test_nonprivate_bound_directory_refused(machine):
    machine[0].trust_directory.chmod(0o755)
    assert "SOURCE_PERMISSIONS" in observe(machine).blockers


@pytest.mark.parametrize("name", ["lock", "ledger"])
def test_busy_locks_block_without_wait(machine, name):
    config, _ = machine
    path = config.lab_root / "registrar.lock" if name == "lock" else config.ledger
    with path.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = observe(machine)
    assert result.status == "BLOCKED" and not result.sources


@pytest.mark.parametrize("pin,floor", [("0" * 64, 1), (None, 2)])
def test_operator_pin_and_floor_required(machine, pin, floor):
    config, _ = machine
    config = dataclasses.replace(config, root_pin=pin or config.root_pin, minimum_root_version=floor)
    result = o.FileObserver(config).observe(CHILD)
    assert result.status == "BLOCKED" and result.root_status == "NOT_EVALUATED"


@pytest.mark.parametrize("lab,child", [("foreign-lab", CHILD), (LAB, "9" * 64)])
def test_prepared_source_identity_crosscheck(machine, lab, child):
    config, _ = machine
    op = operation(lab_id=lab, child_agent_id=child, historical_root_sha256=config.root_pin)
    op["birth_plan"]["record"]["agent_id"] = child
    op["birth_plan"]["child_spec"]["agent_id"] = child
    write(log_path(config), raw(*prefix(op=op)))
    assert "OPERATION_BINDING_MISMATCH" in observe(machine).blockers


@pytest.mark.parametrize("level", [1, 2, 3])
def test_completed_d1_without_consumption_is_inconsistent(machine, level):
    config, op = machine
    write(log_path(config), raw(*prefix(level, op=op)))
    assert "OPERATION_STATE_INCONSISTENT" in observe(machine).blockers


def test_present_entry_is_bound_to_frozen_admission_digest(machine):
    config, op = machine
    spend(config, op, envelope_sha256="e" * 64)
    assert "LEDGER_ENVELOPE_MISMATCH" in observe(machine).blockers
    spend(config, op)
    write(log_path(config), raw(*prefix(1, op=op)))
    assert observe(machine).status == "OBSERVED"


def test_interrupted_d1_never_recovers_automatically(machine):
    config, op = machine
    write(log_path(config), raw(*prefix(op=op), entry("BEGIN", "D1", op=op)))
    for present in (False, True):
        if present:
            spend(config, op)
        result = observe(machine)
        assert result.status == "OBSERVED" and result.log.status == "INTERRUPTED"
        assert result.log.recovery_result is None and not result.accepted


def test_fault_reference_requires_matching_acquired_fault(machine):
    config, op = machine
    write(log_path(config), raw(*prefix(op=op), entry("BEGIN", "D1", op=op),
                               entry("DURABILITY_FAULT", "D1", op=op)))
    assert "FAULT_LINK_MISMATCH" in observe(machine).blockers


def test_corrupt_fault_log_never_healthy_prefix(machine):
    write(machine[0].fault_file, b"broken\n")
    assert "FAULT_LOG_UNAVAILABLE" in observe(machine).blockers


def test_source_change_and_close_errors_discard_payload(machine, monkeypatch):
    original = o._Acquisition.verify

    def mutate(self):
        write(machine[0].fault_file, b"changed")
        original(self)

    monkeypatch.setattr(o._Acquisition, "verify", mutate)
    result = observe(machine)
    assert result.status == "BLOCKED" and not result.sources and result.ledger_bytes is None


def test_close_error_discards_payload(machine, monkeypatch):
    original = os.close

    def close(fd):
        original(fd)
        raise OSError("closed")

    monkeypatch.setattr(o.os, "close", close)
    result = observe(machine)
    assert result.status == "BLOCKED" and not result.sources and result.log is None


def test_open_flags_always_read_only_no_creates(machine, monkeypatch):
    original, seen = os.open, []

    def opened(path, flags, *args, **kwargs):
        seen.append(flags)
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(o.os, "open", opened)
    assert observe(machine).status == "OBSERVED"
    assert seen


@pytest.mark.parametrize("child", ["../escape", "a" * 63, None, True])
def test_invalid_selection_never_acquires(machine, child):
    assert o.FileObserver(machine[0]).observe(child).sources == ()


def test_ledger_snapshot_crosscheck_is_not_asserted_by_caller(machine, monkeypatch):
    original = o.trust.inspect_operation_consumption

    def substitute(*args):
        value = original(*args)
        value["ledger_sha256"] = hashlib.sha256(b"different").hexdigest()
        return value

    monkeypatch.setattr(o.trust, "inspect_operation_consumption", substitute)
    assert observe(machine).blockers == ("LEDGER_SNAPSHOT_MISMATCH",)


@pytest.mark.parametrize("version,pin", [(2, None), (1, "9" * 64)])
def test_operation_cannot_claim_future_or_other_same_version_root(machine, version, pin):
    config, op = machine
    op.update(historical_root_version=version, historical_root_sha256=pin or config.root_pin)
    write(log_path(config), raw(*prefix(op=op)))
    assert "OPERATION_ROOT_INCONSISTENT" in observe(machine).blockers


def test_semantically_invalid_key_never_validates_current_root(machine):
    config, _ = machine
    policy, _ = installed()
    policy["root"]["issuers"][0]["keys"][0]["public_key"] = "0" * 64
    policy, history = installed(policy["root"])
    write(config.trust_directory / "policy.json", f.canonical(policy))
    write(config.trust_directory / "trust-history.log", f.canonical(history) + b"\n")
    result = o.FileObserver(dataclasses.replace(config, root_pin=policy["pin"])).observe(CHILD)
    assert result.root_status == "NOT_EVALUATED" and "TRUST_CURRENT_UNAVAILABLE" in result.blockers


def test_matching_fault_is_still_sticky_and_never_repaired(machine):
    from tests.colony_admission.test_external_evidence import fault
    config, op = machine
    value = fault(lab_id=LAB, operation_sha256=f.digest(op), child_agent_id=CHILD, step="D1", phase="D1")
    value["data"]["target"]["relative_path"] = CHILD + ".log"
    write(config.fault_file, f.canonical(value) + b"\n")
    write(log_path(config), raw(*prefix(op=op), entry("BEGIN", "D1", op=op),
                               entry("DURABILITY_FAULT", "D1", op=op, data={"fault_sha256": f.digest(value)})))
    result = observe(machine)
    assert "STICKY_FAULT" in result.blockers and "FAULT_LINK_MISMATCH" not in result.blockers
    assert result.log.status == "BLOCKED_DURABILITY"


def test_owner_is_checked_even_when_modes_are_private(machine, monkeypatch):
    monkeypatch.setattr(o.os, "geteuid", lambda: 999999)
    assert "SOURCE_PERMISSIONS" in observe(machine).blockers


def test_oversized_policy_blocks_without_partial_evidence(machine):
    write(machine[0].trust_directory / "policy.json", b"x" * (o.POLICY_MAX_BYTES + 1))
    result = observe(machine)
    assert result.blockers == ("SOURCE_LIMIT",) and result.sources == ()


def test_inplace_read_mutation_is_detected(machine, monkeypatch):
    original, changed = os.read, False
    def read(fd, size):
        nonlocal changed
        value = original(fd, size)
        if value and not changed:
            changed = True
            path = machine[0].trust_directory / "policy.json"
            write(path, path.read_bytes() + b"x")
        return value
    monkeypatch.setattr(o.os, "read", read)
    assert observe(machine).status == "BLOCKED"
