"""Acknowledged fragments stay opaque at the real-file observer boundary."""

import copy
import hashlib

import pytest

from colony_admission import formats as f
from colony_admission import observer as o
from colony_admission.oplog import project_log
from tests.colony_admission import test_observer as fixtures
from tests.colony_admission.test_observer import CHILD, entry, log_path, prefix, raw, write

machine = fixtures.machine


def read(config, reader):
    observer = o.FileObserver(config)
    return observer.observe(CHILD) if reader == "observe" else observer.scan()


@pytest.mark.parametrize("reader", ["observe", "scan"])
@pytest.mark.parametrize("fragment_kind", ["split-object", "leading-cr", "trailing-cr", "forged-event"])
def test_acknowledged_cr_fragment_is_opaque(machine, reader, fragment_kind):
    config, op = machine
    foreign = copy.deepcopy(op)
    foreign["lab_id"] = "foreign-lab"
    forged_entry = entry("PREPARED", op=foreign)
    forged_entry["current_root_version"] = 999
    forged = f.canonical(forged_entry)
    fragment = {"split-object": b"{}\r{", "leading-cr": b"\r{}", "trailing-cr": b"{\r",
                "forged-event": b"broken\r" + forged}[fragment_kind]
    ack = entry("TORN_TAIL_ACKNOWLEDGED", op=op,
                data={"fragment_sha256": hashlib.sha256(fragment).hexdigest()})
    data = raw(*prefix(op=op)) + fragment + b"\n" + raw(ack)
    assert project_log(data).status == "OPEN"
    write(log_path(config), data)
    files = [p for p in config.lab_root.parent.rglob("*") if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files}

    result = read(config, reader)

    assert result.status == "OBSERVED", result.blockers
    assert not result.accepted
    assert result.authorization == result.completeness == result.durability == result.rotation == "NOT_EVALUATED"
    log = result.log if reader == "observe" else result.children[0].log
    assert log.operation_sha256 == f.digest(op) and log.status == "OPEN"
    resource = "OPERATION_LOG:" + CHILD if reader == "scan" else "OPERATION_LOG"
    assert any(s.resource == resource and s.sha256 == hashlib.sha256(data).hexdigest()
               for s in result.sources)
    assert {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files} == before


@pytest.mark.parametrize("reader", ["observe", "scan"])
@pytest.mark.parametrize("case", ["canonical-invalid-ack", "unacknowledged-cr", "crlf-event"])
def test_physical_line_fix_does_not_relax_strict_log_validation(machine, reader, case):
    config, op = machine
    if case == "crlf-event":
        data = raw(*prefix(op=op)).replace(b"\n", b"\r\n")
    else:
        fragment = b"{}" if case == "canonical-invalid-ack" else b"{}\r{"
        data = raw(*prefix(op=op)) + fragment + b"\n"
        if case == "canonical-invalid-ack":
            data += raw(entry("TORN_TAIL_ACKNOWLEDGED", op=op,
                              data={"fragment_sha256": hashlib.sha256(fragment).hexdigest()}))
    assert project_log(data).status == "CORRUPT"
    write(log_path(config), data)
    result = read(config, reader)
    assert result.status == "BLOCKED" and "OPERATION_LOG_UNAVAILABLE" in result.blockers
    assert not result.accepted
