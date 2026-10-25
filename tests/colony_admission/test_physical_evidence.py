"""Adversarial real-file evidence joins; all fixtures are temporary LAB_TEST data."""

import copy
import dataclasses
import fcntl
import hashlib
import json
import os

import pytest

from colony_admission import formats as f
from colony_admission import observer as o
from colony_admission import evidence_observer as io
from colony_admission import physical_evidence as p
from tests.colony_admission import test_observer as base
from tests.colony_admission.test_observer import entry, prefix, raw, write, log_path, CHILD
from tests.colony_admission.test_oplog import COLD
from tests.colony_trust.test_operation_inspection import row as ledger_row

machine = base.machine


def envelope(op, role, record, identity):
    kind = {"admission": "colony-registrar.admission/0", "qualification": "colony-lab.qualification/0",
            "statement": "colony-admission.attestation-statement/0"}[role]
    subject = {"agent_id": op["child_agent_id"], "agent_spec_id": op["child_agent_spec_id"]} if role == "admission" else {
        "agent_id": op["parent_agent_id"], "agent_spec_id": op["birth_plan"]["parent"]["agent_spec_id"]}
    return {"envelope_schema": "colony-trust.envelope/0", "envelope_id": identity * 64,
        "lab_id": op["lab_id"], "root_version": 1, "issuer_id": "fixture-issuer", "key_id": "a" * 64,
        "record_kind": kind, "record_sha256": f.digest(record), "subject": subject,
        "purpose": {"admission": "BIRTH_ADMITTED", "qualification": "QUALIFICATION_ATTESTED",
                    "statement": "QUALIFICATION_STATEMENT_ATTESTED"}[role], "signature": "0" * 128}


def seal(op):
    plan = op["birth_plan"]
    plan["parent"]["agent_spec_id"] = "8" * 64
    q = plan["qualification"] = {"qualification_schema": "colony-lab.qualification/0",
        "agent_id": op["parent_agent_id"], "agent_spec_id": "8" * 64,
        "reviewer_id": "fixture-issuer", "reviewer_kind": "HUMAN"}
    a = plan["admission"] = {"admission_schema": "colony-registrar.admission/0",
        "child_agent_id": op["child_agent_id"], "child_agent_spec_id": op["child_agent_spec_id"],
        "parent_agent_id": op["parent_agent_id"], "policy_sha256": op["policy_sha256"],
        "parent_qualification_sha256": f.digest(q), "budget": op["budget"], "lab_permissions": op["permissions"],
        "declared_diff": op["declared_diff"], "admitter_id": "fixture-issuer", "admitter_kind": "HUMAN"}
    statement = dict.fromkeys(p.STATEMENT_FIELDS, None)
    statement.update(statement_schema="colony-admission.attestation-statement/0", subject_agent_id=q["agent_id"],
        subject_agent_spec_id=q["agent_spec_id"], issuer_id=q["reviewer_id"], issuer_kind=q["reviewer_kind"],
        issuer_root_version=1, qualification_record_sha256=f.digest(q), historical_record_path=".env.secret",
        evidence=[{"path": "/never/read/this", "sha256": "a" * 64}], historical_signature_claimed=False)
    records = {"admission": a, "qualification": q, "statement": statement}
    envs = {role: envelope(op, role, record, str(i + 5)) for i, (role, record) in enumerate(records.items())}
    op["presented"] = {role: {"record_sha256": f.digest(records[role]), "envelope_sha256": f.digest(envs[role])}
                       for role in records}
    op["items"] = sorted([{"role": "DECISION", "kind": envs[role]["record_kind"], "subject": envs[role]["subject"],
        **op["presented"][role]} for role in records], key=lambda x: (x["kind"], x["subject"]["agent_id"],
            x["subject"]["agent_spec_id"], x["record_sha256"]))
    return op, {"admission": a, "admission_envelope": envs["admission"], "qualification_envelope": envs["qualification"],
                "statement": statement, "statement_envelope": envs["statement"]}


@pytest.fixture
def physical(machine):
    config, op = machine
    for name in ("registrar-admissions", "admission-envelopes", "individuals"):
        (config.lab_root / name).mkdir(mode=0o700)
    op, values = seal(op)
    write(log_path(config), raw(*prefix(op=op)))
    return config, op, values


def scan(fixture):
    result = o.FileObserver(fixture[0]).scan_evidence()
    assert result.accepted is False
    assert all(getattr(result, k) == p.NE for k in ("authenticity", "authorization", "completeness", "durability",
        "rotation", "attestations", "population", "ceilings", "recovery"))
    return result


def phase(physical, level=0, pending=None, terminal=None):
    config, op, _ = physical
    events = prefix(level, op=op)
    if pending:
        events.append(entry("BEGIN", pending, op=op))
    if terminal:
        if terminal == "FAILED_CONSUMED":
            events.append(entry("TERMINATED", op=op, code="OPERATOR_TERMINATED"))
            events.append(entry(terminal, op=op, code="OPERATOR_TERMINATED"))
        else:
            events.append(entry(terminal, op=op))
    write(log_path(config), raw(*events))
    if level or pending == "D1" or terminal == "FAILED_CONSUMED":
        base.spend(config, op, envelope_id="5" * 64)


def d2(physical, roles=None):
    config, op, values = physical
    for role, path, _ in p.d2_paths(op):
        if roles is not None and role not in roles:
            continue
        target = config.lab_root / path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write(target, p.storage_bytes(values[role]))


def home(physical, *, all_files=True, layout=True):
    config, op, _ = physical
    target = config.lab_root / "individuals" / CHILD
    target.mkdir(mode=0o700, exist_ok=True)
    if all_files:
        for name, value in (("spec.json", op["birth_plan"]["child_spec"]), ("record.json", op["birth_plan"]["record"]),
                ("birth_qualification.json", op["birth_plan"]["qualification"]), ("usage.json", {"runs": 0})):
            write(target / name, p.storage_bytes(value))
    if layout:
        for name in ("tasks", "results", "j01-lab-memory"):
            (target / name).mkdir(mode=0o700, exist_ok=True)
        write(target / "j01-lab-memory/activity.sqlite3", b"metadata-only-not-a-database")
    return target


def discarded(result):
    assert result.status == "BLOCKED"
    assert not result.sources and not result.metadata_sources and not result.operations
    assert result.ledger_bytes is None and result.pending_operations == ()
    assert result.ledger_coverage == p.LedgerCoverage()


def test_empty_roots_and_ledger_once(physical, monkeypatch):  # ACQ-09 / LED-06
    log_path(physical[0]).unlink()
    original, calls = o.trust.inspect_operations_fd, []
    def inspect(fd, operations):
        calls.append(operations)
        return original(fd, operations)
    monkeypatch.setattr(o.trust, "inspect_operations_fd", inspect)
    result = scan(physical)
    assert result.status == "OBSERVED" and calls == [()]
    assert result.ledger_coverage == p.LedgerCoverage("MATCH", 0, 0, 0, 0)


@pytest.mark.parametrize("name", ["admission-ops", "registrar-admissions", "admission-envelopes", "individuals"])
def test_missing_bound_roots(physical, name):  # ACQ-01
    if name == "admission-ops":
        log_path(physical[0]).unlink()
    (physical[0].lab_root / name).rmdir()
    discarded(scan(physical))


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "public", "directory", "foreign"])
def test_unsafe_selected_file(physical, monkeypatch, kind):  # ACQ-03
    d2(physical)
    path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
    path.unlink()
    if kind == "symlink":
        path.symlink_to(physical[0].ledger)
    elif kind == "hardlink":
        os.link(physical[0].ledger, path)
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    elif kind == "directory":
        path.mkdir(mode=0o700)
    elif kind == "foreign":
        write(path, b"{}")
        original = os.fstat
        inode = path.stat().st_ino
        def changed(fd):
            v = original(fd)
            return os.stat_result((*v[:4], v.st_uid + 1, *v[5:])) if v.st_ino == inode else v
        monkeypatch.setattr(io.os, "fstat", changed)
    else:
        write(path, b"{}")
        path.chmod(0o644)
    discarded(scan(physical))


@pytest.mark.parametrize("kind", ["public", "symlink"])
def test_unsafe_selected_directory(physical, kind):  # ACQ-04
    d2(physical)
    target = physical[0].lab_root / "admission-envelopes" / CHILD
    if kind == "public":
        target.chmod(0o755)
    else:
        target.rename(target.with_name("saved"))
        target.symlink_to(target.with_name("saved"))
    discarded(scan(physical))


@pytest.mark.parametrize("error", [PermissionError, OSError, FileNotFoundError])
def test_read_failure_is_not_absence(physical, monkeypatch, error):  # ACQ-02
    d2(physical)
    path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
    inode, original = path.stat().st_ino, os.read
    def read(fd, size):
        if os.fstat(fd).st_ino == inode:
            raise error("fixture only")
        return original(fd, size)
    monkeypatch.setattr(io.os, "read", read)
    discarded(scan(physical))


@pytest.mark.parametrize("mutation", ["absent", "identity", "inventory"])
def test_final_changes_discard_everything(physical, monkeypatch, mutation):  # ACQ-05 / ACQ-06
    d2(physical)
    target = physical[0].lab_root / "individuals" / CHILD
    original = io._EvidenceAcquisition.verify
    def verify(source):
        if mutation == "absent":
            target.mkdir(mode=0o700)
        elif mutation == "identity":
            path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
            path.rename(path.with_suffix(".old"))
            write(path, b"{}")
        else:
            write(physical[0].lab_root / "individuals" / "new", b"{}")
        return original(source)
    monkeypatch.setattr(io._EvidenceAcquisition, "verify", verify)
    result = scan(physical)
    discarded(result)
    assert result.blockers == ("SOURCE_CHANGED",)


def test_close_failure_clears_all(physical, monkeypatch):  # ACQ-07 / LED-07
    original = os.close
    def close(fd):
        original(fd)
        raise OSError("fixture")
    monkeypatch.setattr(io.os, "close", close)
    discarded(scan(physical))


@pytest.mark.parametrize("name", ["L1", "L2"])
def test_busy_lock_no_retry(physical, name):  # ACQ-12
    config = physical[0]
    path = config.ledger if name == "L2" else config.lab_root / "registrar.lock"
    with path.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        discarded(scan(physical))


def test_io_one_read_no_effects_metadata_only_and_immutable(physical, monkeypatch):  # ACQ-08 / RESULT-01 / RESULT-02
    phase(physical, 3, terminal="COMMITTED")
    d2(physical)
    target = home(physical)
    write(target / "usage.json", b"changed usage - not read")
    write(target / "usage.json.tmp", b"also unread")
    write(target / "inflight.json", b"also unread")
    write(target / "tasks" / "unopened", b"ignored task contents")
    paths = [x for x in physical[0].lab_root.parent.rglob("*") if x.is_file()]
    before = {x: (x.read_bytes(), x.stat().st_mode, x.stat().st_mtime_ns) for x in paths}
    opens, reads, locks = {}, {}, []
    open0, read0, flock0 = os.open, os.read, fcntl.flock
    def opened(path, flags, **kw):
        assert flags & os.O_ACCMODE == os.O_RDONLY and not flags & os.O_CREAT
        fd = open0(path, flags, **kw)
        ino = os.fstat(fd).st_ino
        opens[ino] = opens.get(ino, 0) + 1
        return fd
    def read(fd, count):
        chunk = read0(fd, count)
        ino = os.fstat(fd).st_ino
        reads[ino] = reads.get(ino, 0) + len(chunk)
        return chunk
    def flock(fd, flags):
        locks.append((os.fstat(fd).st_ino, flags))
        return flock0(fd, flags)
    def forbidden(*a, **kw):
        pytest.fail("effect or extra reader invoked")
    monkeypatch.setattr(io.os, "open", opened)
    monkeypatch.setattr(io.os, "read", read)
    monkeypatch.setattr(io.o.fcntl, "flock", flock)
    monkeypatch.setattr(o.FileObserver, "scan", forbidden)
    monkeypatch.setattr(o.trust, "check_bundle", forbidden)
    monkeypatch.setattr(o.trust, "verify_consumed", forbidden)
    for name in ("write", "fsync", "rename", "unlink", "mkdir", "chmod"):
        monkeypatch.setattr(io.os, name, forbidden)
    result = scan(physical)
    assert result.status == "OBSERVED", result.blockers
    assert result.operations[0].d3.identity_state == "IDENTITY_MATCH"
    assert result.operations[0].d3.usage_content == p.NE
    assert locks == [( (physical[0].lab_root / "registrar.lock").stat().st_ino, fcntl.LOCK_EX | fcntl.LOCK_NB),
                     (physical[0].ledger.stat().st_ino, fcntl.LOCK_SH | fcntl.LOCK_NB),
                     (physical[0].ledger.stat().st_ino, fcntl.LOCK_UN)]
    for path in paths:
        assert (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) == before[path]
        if path.name not in ("usage.json", "usage.json.tmp", "inflight.json", "activity.sqlite3", "unopened"):
            assert opens[path.stat().st_ino] == 1
            assert reads[path.stat().st_ino] == path.stat().st_size
    for path in (target / "usage.json", target / "usage.json.tmp", target / "inflight.json", target / "j01-lab-memory/activity.sqlite3"):
        assert path.stat().st_ino not in reads
    assert any(s.resource.endswith("activity.sqlite3") for s in result.metadata_sources)
    assert not any(s.resource.endswith("activity.sqlite3") for s in result.sources)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.operations[0].d1.operation_entries = 9


@pytest.mark.parametrize("terminal", ["REFUSED", "ABANDONED"])
def test_history_all_ids_latest_material_only(physical, monkeypatch, terminal):  # HIST-01 / HIST-06
    config, old, _ = physical
    new, values = seal(copy.deepcopy(old))
    new["attempt"] = 2
    new["birth_plan"]["child_spec"]["label"] = "new material"
    newfixture = config, new, values
    events = prefix(op=old) + [entry(terminal, op=old)] + prefix(2, op=new)
    write(log_path(config), raw(*events))
    base.spend(config, new, envelope_id="5" * 64)
    d2(newfixture)
    original, calls = o.trust.inspect_operations_fd, []
    def inspect(fd, operations):
        calls.append(operations)
        return original(fd, operations)
    monkeypatch.setattr(o.trust, "inspect_operations_fd", inspect)
    result = scan(newfixture)
    assert result.status == "OBSERVED", result.blockers
    assert calls == [tuple(sorted((f.digest(old), f.digest(new))))]
    assert result.operations[0].d2.material_state == "SUPERSEDED_NOT_EVALUATED"
    assert result.operations[0].d1.operation_entries == 0
    assert result.operations[1].d2.material_state == "MATERIAL_MATCH"


def history_boundary(physical, count):
    config, initial, _ = physical
    log_path(config).unlink()
    # 2 attempts per log, demonstrating the ID cap independently of log count.
    for n in range((count + 1) // 2):
        child = f"{n:064x}"
        op = copy.deepcopy(initial)
        op["child_agent_id"] = child
        op["birth_plan"]["child_spec"]["agent_id"] = child
        op["birth_plan"]["record"]["agent_id"] = child
        op, _ = seal(op)
        events = prefix(op=op) + [entry("REFUSED", op=op)]
        if 2 * n + 1 < count:
            new = copy.deepcopy(op)
            new["attempt"] = 2
            events += prefix(op=new) + [entry("REFUSED", op=new)]
        write(config.lab_root / "admission-ops" / (child + ".log"), raw(*events))


@pytest.mark.parametrize("count", [256, 257])
def test_history_cap_before_ledger_open(physical, monkeypatch, count):  # HIST-02 / HIST-03
    history_boundary(physical, count)
    original, calls = o._ledger, []
    def ledger(*a, **kw):
        calls.append(True)
        return original(*a, **kw)
    monkeypatch.setattr(o, "_ledger", ledger)
    result = scan(physical)
    if count == 257:
        assert calls == [] and result.blockers == ("HISTORY_OPERATION_LIMIT",)
        discarded(result)
    else:
        assert calls == [True] and len(result.operations) == 256 and result.status == "OBSERVED", result.blockers


def test_duplicate_not_coalesced(physical):  # HIST-04
    write(log_path(physical[0]).with_name("2" * 64 + ".log"), log_path(physical[0]).read_bytes())
    assert "DUPLICATE_OPERATION" in scan(physical).blockers


def test_historical_consumption_not_hidden(physical):  # HIST-05
    config, old, _ = physical
    new = copy.deepcopy(old)
    new["attempt"] = 2
    write(log_path(config), raw(*prefix(op=old), entry("REFUSED", op=old), *prefix(op=new)))
    base.spend(config, old)
    assert "OPERATION_STATE_INCONSISTENT" in scan(physical).operations[0].blockers


def test_ack_cr_fragment_is_opaque(physical):  # HIST-07
    config, op, _ = physical
    fragment = b'bad\r' + f.canonical((entry("PREPARED", op=op) | {"current_root_version":99}))
    ack = entry("TORN_TAIL_ACKNOWLEDGED", op=op, data={"fragment_sha256": hashlib.sha256(fragment).hexdigest()})
    write(log_path(config), raw(*prefix(op=op)) + fragment + b"\n" + raw(ack))
    assert scan(physical).status == "OBSERVED"


def test_original_reserve_positions(physical):  # HIST-08
    config, op, _ = physical
    events = prefix(op=op)
    # Canonical schema-valid events after reserve line56 must still be rejected.
    for i in range(28):
        fragment = f'bad{i}'.encode()
        ack = entry("TORN_TAIL_ACKNOWLEDGED", op=op, data={"fragment_sha256": hashlib.sha256(fragment).hexdigest()})
        events_raw = fragment + b"\n" + raw(ack)
        if i == 0:
            data = raw(*events)
        data += events_raw
    write(log_path(config), data + raw(entry("REFUSED", op=op)))
    assert scan(physical).blockers == ("OPERATION_LOG_UNAVAILABLE",)


def test_two_pending_births(physical):  # HIST-09
    config, op, _ = physical
    second = copy.deepcopy(op)
    second["child_agent_id"] = "9" * 64
    second["birth_plan"]["child_spec"]["agent_id"] = "9" * 64
    second["birth_plan"]["record"]["agent_id"] = "9" * 64
    second, _ = seal(second)
    write(log_path(config).with_name("9" * 64 + ".log"), raw(*prefix(op=second)))
    result = scan(physical)
    assert result.blockers == ("OPERATION_PENDING",) and len(result.pending_operations) == 2


@pytest.mark.parametrize("data", [b"broken\n", b'{"torn":', f.canonical(ledger_row()) + b"\nbad\n"])
def test_ledger_whole_parse_discards_prefix(physical, data):  # LED-01
    write(physical[0].ledger, data)
    discarded(scan(physical))


@pytest.mark.parametrize("legacy,empty", [(True, False), (False, False), (False, True)])
def test_unbound_ledger_counts(physical, legacy, empty):  # LED-02 / LED-03 / LED-04
    if empty:
        log_path(physical[0]).unlink()
    write(physical[0].ledger, f.canonical(ledger_row(legacy=legacy)) + b"\n")
    result = scan(physical)
    assert ("LEGACY_LEDGER_UNBOUND" if legacy else "LEDGER_OPERATION_UNBOUND") in result.blockers
    assert result.ledger_coverage.unbound_entries == 1
    assert result.ledger_coverage.status == ("LEGACY_UNBOUND" if legacy else "UNBOUND")


def test_conflicting_requested_entries_never_match(physical):  # LED-05
    phase(physical, 1)
    path = physical[0].ledger
    row = json.loads(path.read_bytes())
    row["envelope_id"] = "d" * 64
    write(path, path.read_bytes() + f.canonical(row) + b"\n")
    result = scan(physical)
    assert "LEDGER_UNAVAILABLE" in result.blockers and result.ledger_coverage.status == "UNBOUND"


@pytest.mark.parametrize("level,pending,spent,expected", [(1,None,False,"OPERATION_STATE_INCONSISTENT"),
    (0,"D1",False,None), (0,"D1",True,None), (0,None,True,"OPERATION_STATE_INCONSISTENT"), (1,None,True,None)])
def test_d1_phases(physical, level, pending, spent, expected):  # D1-01..D1-05
    phase(physical, level, pending)
    if spent:
        base.spend(physical[0], physical[1], envelope_id="5" * 64)
    else:
        write(physical[0].ledger, b"")
    result = scan(physical)
    if expected:
        assert expected in result.blockers
    else:
        assert result.status == "OBSERVED", result.blockers
    assert result.operations[0].d1.frozen_hash_match == ("MATCH" if spent else "ABSENT")
    assert result.operations[0].d1.envelope_binding == "NOT_AVAILABLE_BEFORE_D2"


def test_foreign_d1_hash(physical):  # D1-04
    phase(physical, 1)
    base.spend(physical[0], physical[1], envelope_sha256="f" * 64)
    assert "LEDGER_ENVELOPE_MISMATCH" in scan(physical).blockers


@pytest.mark.parametrize("field", ["issuer_id", "envelope_id"])
def test_d1_stored_identity_mismatch(physical, field):  # D1-06
    phase(physical, 1)
    d2(physical)
    base.spend(physical[0], physical[1], **{field: "foreign-issuer" if field == "issuer_id" else "e" * 64})
    result = scan(physical)
    assert "LEDGER_ENVELOPE_MISMATCH" in result.blockers
    assert result.operations[0].d1.envelope_binding != "MATCH"


@pytest.mark.parametrize("roles,state", [((),"ABSENT"), (("admission",),"PARTIAL"), (None,"MATERIAL_MATCH")])
def test_d2_interrupted_material(physical, roles, state):  # D2-01 / D2-02 / D2-03
    phase(physical, 1, "D2")
    d2(physical, roles)
    result = scan(physical)
    assert result.status == "OBSERVED", result.blockers
    assert result.operations[0].d2.material_state == state
    assert result.operations[0].log.pending_step == "D2"


@pytest.mark.parametrize("role", [x[0] for x in p.d2_paths(base.operation())])
def test_completed_d2_requires_each_file(physical, role):  # D2-04
    phase(physical, 2)
    d2(physical)
    path = next(path for r,path,_ in p.d2_paths(physical[1]) if r == role)
    (physical[0].lab_root / path).unlink()
    assert "OPERATION_STATE_INCONSISTENT" in scan(physical).blockers


@pytest.mark.parametrize("data", [b"{", b"{}", b'{"x":1,"x":2}', b'{"x":1.1}', b'{"x":NaN}', b'{"x":-0}',
    b'{"x":' + b'['*33 + b'0' + b']'*33 + b'}'])
@pytest.mark.parametrize("role_index", range(5))
def test_divergent_strict_d2_content(physical, data, role_index):  # D2-05
    d2(physical)
    write(physical[0].lab_root / p.d2_paths(physical[1])[role_index][1], data)
    result = scan(physical)
    assert "STORED_FILE_DIVERGENT" in result.blockers and result.sources


def test_d2_canonical_equality_namespace_paths_no_individual_required(physical):  # D2-06 / D2-09..D2-12
    d2(physical)
    admission_path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
    write(admission_path, json.dumps(physical[2]["admission"], indent=4).encode())
    result = scan(physical)
    assert result.status == "OBSERVED", result.blockers
    row = result.operations[0]
    assert row.d2.material_state == "MATERIAL_MATCH" and row.d3.identity_state == "ABSENT"
    assert row.d2.files[0].comparison == "CANONICAL_MATCH"
    assert row.log.last_completed_step == "D0"


@pytest.mark.parametrize("field", ["child_agent_id", "child_agent_spec_id", "parent_agent_id", "policy_sha256",
    "parent_qualification_sha256", "budget", "lab_permissions", "declared_diff"])
def test_invalid_frozen_admission_bindings(physical, field):  # D2-07
    config, op, _ = physical
    a = op["birth_plan"]["admission"]
    a[field] = {"runs": 99} if field == "budget" else ["foreign"] if field in ("lab_permissions","declared_diff") else "f"*64
    op["presented"]["admission"]["record_sha256"] = f.digest(a)
    write(log_path(config), raw(*prefix(op=op)))
    assert "FROZEN_MATERIAL_INVALID" in scan(physical).blockers


@pytest.mark.parametrize("change", ["missing", "contradictory", "wrong_subject", "duplicate"])
def test_frozen_decision_bindings(physical, change):  # D2-08
    config, op, _ = physical
    if change == "missing":
        op["items"].pop()
    elif change == "contradictory":
        op["items"][0]["envelope_sha256"] = "e" * 64
    elif change == "wrong_subject":
        op["items"][0]["subject"]["agent_spec_id"] = "e" * 64
    else:
        op["items"].append(copy.deepcopy(op["items"][0]))
        op["items"].sort(key=lambda x: (x["kind"],x["subject"]["agent_id"],x["subject"]["agent_spec_id"],x["record_sha256"]))
    write(log_path(config), raw(*prefix(op=op)))
    result = scan(physical)
    assert ("OPERATION_LOG_UNAVAILABLE" if change == "duplicate" else "FROZEN_MATERIAL_INVALID") in result.blockers


def test_foreign_qualification_subject(physical):  # D2-13
    d2(physical)
    role, path, _ = p.d2_paths(physical[1])[2]
    value = copy.deepcopy(physical[2][role])
    value["subject"]["agent_id"] = CHILD
    physical[1]["presented"]["qualification"]["envelope_sha256"] = f.digest(value)
    for item in physical[1]["items"]:
        if item["kind"] == "colony-lab.qualification/0":
            item["envelope_sha256"] = f.digest(value)
    phase(physical, 1)
    write(physical[0].lab_root/path, p.storage_bytes(value))
    assert "STORED_FILE_DIVERGENT" in scan(physical).blockers


@pytest.mark.parametrize("level,pending,expected", [(0,None,"OPERATION_STATE_INCONSISTENT"),
    (2,None,"HOME_ORIGIN_NOT_EVALUATED"), (2,"D3",None)])
def test_home_phase_and_no_origin_inference(physical, level, pending, expected):  # D3-01 / D3-02 / D3-03 / D3-06
    phase(physical, level, pending)
    d2(physical)
    home(physical)
    result = scan(physical)
    if expected:
        assert expected in result.blockers
    else:
        assert result.status == "OBSERVED", result.blockers
        assert result.operations[0].d3.identity_state == "INITIAL_MATCH"


def test_partial_d3_whole_files_only(physical):  # D3-04
    phase(physical, 2, "D3")
    d2(physical)
    target = home(physical, all_files=False, layout=False)
    write(target / "spec.json", p.storage_bytes(physical[1]["birth_plan"]["child_spec"]))
    result = scan(physical)
    assert result.status == "OBSERVED" and result.operations[0].d3.identity_state == "PARTIAL"


@pytest.mark.parametrize("name", ["spec.json", "record.json", "birth_qualification.json", "usage.json"])
@pytest.mark.parametrize("kind", ["short", "different"])
def test_open_d3_short_or_different_not_partial(physical, name, kind):  # D3-05
    phase(physical, 2, "D3")
    d2(physical)
    target = home(physical) / name
    write(target, target.read_bytes()[:4] if kind == "short" else b"different")
    result = scan(physical)
    assert "STORED_FILE_DIVERGENT" in result.blockers
    assert result.operations[0].d3.identity_state == "DIVERGENT"


def test_recovery_present_d3_usage_excluded(physical):  # D3-08
    phase(physical, 2, "D3")
    config, op, _ = physical
    events = log_path(config).read_bytes() + raw(entry("INTERRUPTED_RECOVERED", "D3", op=op, boot=COLD, data={"result":"PRESENT"}))
    write(log_path(config), events)
    d2(physical)
    target = home(physical)
    write(target / "usage.json", b"changed after recovery")
    result = scan(physical)
    assert result.status == "OBSERVED", result.blockers
    assert result.operations[0].d3.usage_content == p.NE
    assert result.operations[0].d3.identity_state == "IDENTITY_MATCH"


@pytest.mark.parametrize("name", ["spec.json", "record.json", "birth_qualification.json"])
@pytest.mark.parametrize("kind", ["missing", "different"])
def test_completed_d3_requires_identity(physical, name, kind):  # D3-09
    phase(physical, 3, terminal="COMMITTED")
    d2(physical)
    path = home(physical) / name
    if kind == "missing":
        path.unlink()
    else:
        write(path, b"different")
    assert "OPERATION_STATE_INCONSISTENT" in scan(physical).blockers


def test_unicode_writer_encoding_parity(physical, tmp_path):  # D3-10
    from colony_lab.supervisor import _dump
    config, op, _ = physical
    op["birth_plan"]["child_spec"]["name"] = "étoile 星"
    phase(physical, 2, "D3")
    d2(physical)
    target = home(physical)
    sample = tmp_path / "writer.json"
    sample.write_bytes(_dump(op["birth_plan"]["child_spec"]))
    assert sample.read_bytes() == (target / "spec.json").read_bytes() == p.storage_bytes(op["birth_plan"]["child_spec"])
    write(target / "spec.json", f.canonical(op["birth_plan"]["child_spec"]))
    assert "STORED_FILE_DIVERGENT" in scan(physical).blockers


@pytest.mark.parametrize("missing", ["tasks", "results", "j01-lab-memory", "store", "empty_store"])
def test_completed_layout_metadata_required(physical, missing):  # D3-11
    phase(physical, 3)
    d2(physical)
    target = home(physical)
    store = target / "j01-lab-memory/activity.sqlite3"
    if missing in ("store", "j01-lab-memory"):
        store.unlink()
    if missing in ("tasks", "results", "j01-lab-memory"):
        (target / missing).rmdir()
    elif missing == "empty_store":
        write(store, b"")
    assert "D3_LAYOUT_INCOMPLETE" in scan(physical).blockers


@pytest.mark.parametrize("location,kind", [("root","unknown"),("journal","unknown"),("root","symlink"),
    ("journal","hardlink"),("root","overflow")])
def test_layout_namespace_safety(physical, location, kind):  # D3-12
    phase(physical, 2, "D3")
    d2(physical)
    target = home(physical)
    if location == "journal":
        target /= "j01-lab-memory"
    if kind == "unknown":
        write(target / "unknown", b"not inspected")
    elif kind == "symlink":
        (target / "usage.json.tmp").symlink_to(target / "usage.json")
    elif kind == "hardlink":
        os.link(target / "activity.sqlite3", target / "activity.sqlite3-wal")
    else:
        for n in range(17):
            write(target / str(n), b"")
    discarded(scan(physical))


def test_terminal_prefix_and_action_retained(physical):  # D3-13 / D3-14
    phase(physical, 2, "D3", "FAILED_CONSUMED")
    d2(physical)
    path = home(physical) / "spec.json"
    write(path, path.read_bytes()[:3])
    result = scan(physical)
    assert "ACTION_EVIDENCE_NOT_EVALUATED" in result.blockers
    assert result.operations[0].d3.identity_state == "TERMINAL_PREFIX"
    assert result.operations[0].d1.frozen_hash_match == "MATCH"


def test_set_aside_is_not_pending_birth(physical):  # HIST-10
    test_terminal_prefix_and_action_retained(physical)
    config, op, _ = physical
    write(log_path(config), log_path(config).read_bytes() + raw(entry("SET_ASIDE_BEGIN", "D3", op=op)))
    second = copy.deepcopy(op)
    second["child_agent_id"] = "9" * 64
    second["birth_plan"]["child_spec"]["agent_id"] = "9" * 64
    second["birth_plan"]["record"]["agent_id"] = "9" * 64
    second, _ = seal(second)
    write(log_path(config).with_name("9" * 64 + ".log"), raw(*prefix(op=second)))
    result = scan(physical)
    assert result.pending_operations == (f.digest(second),)
    assert "OPERATION_PENDING" not in result.blockers and "ACTION_EVIDENCE_NOT_EVALUATED" in result.blockers


@pytest.mark.parametrize("target", ["record", "envelope", "aggregate", "descriptors"])
def test_resource_limits_discard(physical, monkeypatch, target):  # LIMIT-01
    d2(physical)
    if target in ("record","envelope"):
        i = 0 if target == "record" else 1
        _, path, limit = p.d2_paths(physical[1])[i]
        write(physical[0].lab_root / path, b" " * (limit+1))
    else:
        values = {"content_bytes": 10} if target == "aggregate" else {"descriptors": 4}
        original = p.Limits
        monkeypatch.setattr(p, "Limits", lambda **kw: original(**(values | kw)))
    result = scan(physical)
    assert result.blockers == ("SOURCE_LIMIT",)
    discarded(result)


def test_strict_foundation_no_partial_rows(physical):
    write(log_path(physical[0]), raw(*prefix(op=physical[1])) + b"broken\n")
    discarded(scan(physical))


def test_sticky_fault_cannot_be_cleared(physical):  # ACQ-11
    from tests.colony_admission.test_external_evidence import fault
    config, op, _ = physical
    value = fault(lab_id=config.lab_id, operation_sha256=f.digest(op), child_agent_id=CHILD, step="D1", phase="D1")
    value["data"]["target"]["relative_path"] = CHILD + ".log"
    write(config.fault_file, f.canonical(value) + b"\n")
    write(log_path(config), raw(*prefix(op=op), entry("BEGIN", "D1", op=op),
        entry("DURABILITY_FAULT", "D1", op=op, data={"fault_sha256": f.digest(value)})))
    result = scan(physical)
    assert "STICKY_FAULT" in result.blockers and result.operations
    assert "FAULT_LINK_MISMATCH" not in result.blockers


@pytest.mark.parametrize("corrupt", [False, True])
def test_external_termination_never_skips_neighbor(physical, corrupt):  # ACQ-10 / D3-14
    from tests.colony_admission.test_external_evidence import fault, terminate
    config, op, _ = physical
    source = fault()
    # External evidence keeps its own frozen operation ID; no authority follows.
    term = terminate(source)
    write(config.fault_file, raw(source, term))
    if corrupt:
        write(log_path(config).with_name("9"*64 + ".log"), b"broken\n")
    result = scan(physical)
    assert "EXTERNAL_TERMINATION_NOT_EVALUATED" in result.blockers
    if corrupt:
        discarded(result)
    else:
        assert "ACTION_EVIDENCE_NOT_EVALUATED" in result.blockers


@pytest.mark.parametrize("kind", ["metadata", "unlock", "read"])
def test_ledger_failures_have_null_counts(physical, monkeypatch, kind):  # LED-07
    config = physical[0]
    inode = config.ledger.stat().st_ino
    if kind == "read":
        original = os.read
        def read(fd, size):
            if os.fstat(fd).st_ino == inode:
                raise OSError("fixture")
            return original(fd, size)
        monkeypatch.setattr(io.os, "read", read)
    elif kind == "unlock":
        original = fcntl.flock
        def flock(fd, flags):
            if flags == fcntl.LOCK_UN:
                raise OSError("fixture")
            return original(fd, flags)
        monkeypatch.setattr(io.o.fcntl, "flock", flock)
    else:
        original = o.trust.inspect_operations_fd
        def inspect(fd, operations):
            result = original(fd, operations)
            # Same-content replacement still invalidates the acquired identity.
            config.ledger.rename(config.ledger.with_suffix(".saved"))
            write(config.ledger, b"")
            return result
        monkeypatch.setattr(o.trust, "inspect_operations_fd", inspect)
    discarded(scan(physical))


@pytest.mark.parametrize("action", ["QUARANTINE_BEGIN", "QUARANTINE_DONE", "SET_ASIDE_DONE"])
def test_all_structural_actions_stay_unevaluated(physical, action):  # D3-14
    config, op, _ = physical
    if action == "SET_ASIDE_DONE":
        phase(physical, 2, "D3", "FAILED_CONSUMED")
        data = log_path(config).read_bytes() + raw(entry("SET_ASIDE_BEGIN", "D3", op=op), entry(action, "D3", op=op))
    else:
        phase(physical, 2, "D3")
        data = log_path(config).read_bytes() + raw(entry("INTERRUPTED_RECOVERED", "D3", op=op,
            boot=COLD, data={"result":"PARTIAL"}), entry("QUARANTINE_BEGIN", "D3", op=op))
        if action == "QUARANTINE_DONE":
            data += raw(entry(action, "D3", op=op))
    write(log_path(config), data)
    result = scan(physical)
    assert "ACTION_EVIDENCE_NOT_EVALUATED" in result.blockers


@pytest.mark.parametrize("count", [256,257])
def test_log_count_boundary_separate_from_history(physical, count):
    config, initial, _ = physical
    log_path(config).unlink()
    for n in range(count):
        op = copy.deepcopy(initial)
        child = f"{n:064x}"
        op["child_agent_id"] = child
        op["birth_plan"]["child_spec"]["agent_id"] = child
        op["birth_plan"]["record"]["agent_id"] = child
        op, _ = seal(op)
        write(config.lab_root / "admission-ops" / (child + ".log"), raw(*prefix(op=op),entry("REFUSED",op=op)))
    result = scan(physical)
    if count == 256:
        assert result.status == "OBSERVED" and len(result.operations) == 256, result.blockers
    else:
        assert result.blockers == ("OPERATION_LOGS_FULL",)
        discarded(result)


@pytest.mark.parametrize("version", [99, True])
def test_statement_visible_issuer_version_even_when_hashes_rebound(physical, version):
    config, op, values = physical
    values["statement"]["issuer_root_version"] = version
    values["statement_envelope"]["record_sha256"] = f.digest(values["statement"])
    op["presented"]["statement"] = {"record_sha256": f.digest(values["statement"]),
                                   "envelope_sha256": f.digest(values["statement_envelope"])}
    for item in op["items"]:
        if item["kind"] == "colony-admission.attestation-statement/0":
            item.update(op["presented"]["statement"])
    phase(physical, 2)
    d2(physical)
    result = scan(physical)
    assert "STORED_FILE_DIVERGENT" in result.blockers
    assert next(x for x in result.operations[0].d2.files if x.role == "statement").comparison == "MISMATCH"


def test_strict_duplicate_even_when_last_value_matches_frozen(physical):
    d2(physical)
    path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
    encoded = f.canonical(physical[2]["admission"])
    write(path, b'{"admission_schema":"foreign",' + encoded[1:])
    result = scan(physical)
    assert "STORED_FILE_DIVERGENT" in result.blockers
    assert result.operations[0].d2.material_state == "DIVERGENT"


def test_completed_usage_can_be_absent(physical):
    phase(physical, 3)
    d2(physical)
    target = home(physical)
    (target / "usage.json").unlink()
    result = scan(physical)
    assert result.status == "OBSERVED", result.blockers
    assert result.operations[0].d3.identity_state == "IDENTITY_MATCH"
    assert result.operations[0].d3.usage_content == p.NE


def test_selected_metadata_enoent_is_not_absence(physical, monkeypatch):
    d2(physical)
    path = physical[0].lab_root / p.d2_paths(physical[1])[0][1]
    inode, original = path.stat().st_ino, os.fstat
    def fstat(fd):
        result = original(fd)
        if result.st_ino == inode:
            raise FileNotFoundError("fixture")
        return result
    monkeypatch.setattr(io.os, "fstat", fstat)
    discarded(scan(physical))


@pytest.mark.parametrize("count", [252, 253])
def test_item_reference_bound_is_diagnostic_not_policy_completeness(physical, count, monkeypatch):
    config, op, _ = physical
    for n in range(count - 3):
        op["items"].append({"role":"POPULATION", "kind":"colony-lab.individual/0",
            "subject":{"agent_id":f"{n:064x}","agent_spec_id":"a"*64},
            "record_sha256":"b"*64,"envelope_sha256":"c"*64})
    op["items"].sort(key=lambda x:(x["kind"],x["subject"]["agent_id"],x["subject"]["agent_spec_id"],x["record_sha256"]))
    phase(physical)
    original, calls = o._ledger, []
    def ledger(*args, **kw):
        calls.append(True)
        return original(*args, **kw)
    monkeypatch.setattr(o, "_ledger", ledger)
    result = scan(physical)
    if count == 252:
        assert result.status == "OBSERVED" and calls == [True], result.blockers
    else:
        discarded(result)
        assert result.blockers == ("SOURCE_LIMIT",) and result.limits.reached == ("item_references",)
        assert calls == []


def test_sticky_ledger_fault_preserved(physical):
    from tests.colony_admission.test_external_evidence import fault, target
    config, op, _ = physical
    value = fault(operation_sha256=f.digest(op), child_agent_id=CHILD, phase="D1", step="D1",
        data={"origin":"TRUST","failure":"CONSUMPTION_IO_UNKNOWN","target":target("LEDGER",path="")})
    write(config.fault_file, raw(value))
    result = scan(physical)
    assert "STICKY_FAULT" in result.blockers and result.operations


def test_aggregate_log_cap_no_partial_result(physical, monkeypatch):
    monkeypatch.setattr(o, "MAX_SCAN_BYTES", 10)
    result = scan(physical)
    discarded(result)
    assert result.blockers == ("SOURCE_LIMIT",) and result.limits.reached == ("log_bytes",)


@pytest.mark.parametrize("binding", ["lab_id", "child_agent_id"])
def test_filename_and_lab_binding_precede_ledger(physical, monkeypatch, binding):
    config, op, _ = physical
    if binding == "lab_id":
        op["lab_id"] = "foreign-lab"
    else:
        op["child_agent_id"] = "9" * 64
        op["birth_plan"]["child_spec"]["agent_id"] = "9" * 64
        op["birth_plan"]["record"]["agent_id"] = "9" * 64
    write(log_path(config), raw(*prefix(op=op)))
    monkeypatch.setattr(o, "_ledger", lambda *args: pytest.fail("ledger opened before log binding"))
    result = scan(physical)
    discarded(result)
    assert result.blockers == ("OPERATION_BINDING_MISMATCH",)
