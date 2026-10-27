"""Private first phase of 3C's future single-owner acquisition.

Build the complete bounded ledger query universe before any ledger access.
This phase does not verify terminal findings, classify homes or expose a scan.
The enclosing owner must hold L1 and retain/revalidate/close this same source.
"""

import os
from dataclasses import dataclass, field

from . import evidence_observer as e
from . import formats as f
from . import observer as o
from . import physical_evidence as p
from .external_evidence import project_fault_log
from .oplog import LogProjection, project_log


@dataclass(frozen=True)
class ReadableAttempt:
    child_agent_id: str
    operation_bytes: bytes
    log_bytes: bytes
    projection: LogProjection
    latest: bool


@dataclass(frozen=True)
class UnreadLog:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    termination_entry_bytes: bytes
    presence: str
    size: int | None
    terminal_linkage: str = field(default=p.NE, init=False)


@dataclass(frozen=True)
class LogInventory:
    names: tuple[str, ...]
    attempts: tuple[ReadableAttempt, ...]
    unread_logs: tuple[UnreadLog, ...]
    operation_ids: tuple[str, ...]
    pending_from_readable_logs: tuple[str, ...]
    fault_entry_bytes: tuple[bytes, ...]
    accepted: bool = field(default=False, init=False)
    snapshot_completeness: str = field(default=p.NE, init=False)
    external_facts: str = field(default=p.NE, init=False)


def _names(source, parent):
    names = []
    with os.scandir(parent) as entries:
        for entry in entries:
            e._limit(len(names) < 256, 'logs')
            name = entry.name
            o._need(name.endswith('.log') and f.hex64(name[:-4]), 'OPERATION_NAMESPACE_INVALID')
            source._entry(parent, name)
            names.append(name)
    result = tuple(sorted(names))
    if parent in source.inventories:
        o._need(source.inventories[parent] == result, 'SOURCE_CHANGED')
    else:
        source.inventories[parent] = result
    return result


def _unread_metadata(source, parent, name):
    # Only an ENOENT from open establishes absence; errors after open propagate.
    key = parent, name
    o._need(key not in source.fds, 'SOURCE_CHANGED')
    try:
        fd = source._fd(name, os.O_RDONLY, parent=parent)
    except FileNotFoundError:
        source.absent(parent, name)
        return 'ABSENT', None
    _, before = source.checked_file_descriptor(fd, parent, name, 2**63 - 1)
    e._limit(before.st_size <= f.MAX_LOG, 'per_log_bytes')
    source.fds[key] = fd
    source._entry(parent, name)
    source.stamp(fd, 'UNREAD_OPERATION_LOG:' + name[:-4])
    return 'PRESENT', before.st_size


def acquire_logs(source, lab, fault_raw, lab_id, *, item_cap):
    """Acquire one provisional log phase using the caller's retained owner.

External claims are strictly re-derived from supplied acquired raw bytes, not
caller-made projection objects. All their IDs (including /0) enter U. Logs with
an exact prior OPERATION_LOG fault and termination claim are never read, even
when the later ledger linkage will fail. No terminal classification is granted.
Neither this function nor any helper opens/inspects a ledger or checks a signature.
"""
    o._need(type(item_cap) is int and 0 <= item_cap <= 252, 'CONFIG_INVALID')
    o._need(type(lab_id) is str and bool(f.NAME.fullmatch(lab_id)), 'CONFIG_INVALID')
    faults = project_fault_log(fault_raw, lab_id)
    o._need(faults.status in ('EMPTY', 'STRUCTURAL_ONLY'), 'FAULT_LOG_UNAVAILABLE')
    parent = source.optional_directory(lab, 'admission-ops', 'admission-ops')
    o._need(parent is not None, 'SOURCE_UNAVAILABLE')
    names = _names(source, parent)
    # project_fault_log already requires each termination to link a preceding
    # exact OPERATION_LOG fault with the same child/op/attempt. /0 stays opaque,
    # but its finding remains explicitly unproven just like /1 until ledger join.
    terminals = {claim.child_agent_id: claim for claim in faults.termination_claims}
    e._limit(len(terminals) <= 256, 'operations')
    entries = {f.digest(f.loads(raw)): raw for raw in faults.entry_bytes}
    operation_ids = {claim.operation_sha256 for claim in faults.termination_claims}
    e._limit(len(operation_ids) <= 256, 'operations')
    unread, attempts, pending, seen = [], [], set(), set()
    total = 0
    for child, claim in sorted(terminals.items()):
        presence, size = _unread_metadata(source, parent, child + '.log')
        if size is not None:
            total += size
            e._limit(total <= o.MAX_SCAN_BYTES, 'log_bytes')
        unread.append(UnreadLog(child, claim.operation_sha256, claim.attempt,
                                entries[claim.entry_sha256], presence, size))
    for name in names:
        child = name[:-4]
        if child in terminals:
            continue
        raw = source.file(parent, name, 'OPERATION_LOG:' + child,
                          min(f.MAX_LOG, o.MAX_SCAN_BYTES - total))
        total += len(raw)
        whole = project_log(raw)
        o._need(whole.status not in ('CORRUPT', 'TORN_TAIL', 'EMPTY', 'PREPARATION_INCOMPLETE'),
                'OPERATION_LOG_UNAVAILABLE')
        for prefix, log, op in e._attempts(raw, whole):
            o._need(log.operation_sha256 not in seen, 'DUPLICATE_OPERATION')
            o._need(op['lab_id'] == lab_id and op['child_agent_id'] == child,
                    'OPERATION_BINDING_MISMATCH')
            # Same digest cannot simultaneously refer to a readable PREPARED
            # for another child and an external claim about a faulty child.
            o._need(log.operation_sha256 not in operation_ids, 'OPERATION_BINDING_MISMATCH')
            seen.add(log.operation_sha256)
            operation_ids.add(log.operation_sha256)
            e._limit(len(seen) <= 256 and len(operation_ids) <= 256, 'operations')
            e._limit(len(op['items']) <= item_cap, 'item_references')
            attempts.append(ReadableAttempt(child, f.canonical(op), prefix, log,
                                            log.operation_sha256 == whole.operation_sha256))
        if whole.terminal_claim is None:
            pending.add(whole.operation_sha256)
    o._need(_names(source, parent) == names, 'SOURCE_CHANGED')
    return LogInventory(names, tuple(attempts), tuple(unread), tuple(sorted(operation_ids)),
                        tuple(sorted(pending)), faults.entry_bytes)
