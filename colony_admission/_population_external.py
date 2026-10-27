"""Private bindings of strict external claims to the single current ledger batch.

Detached inputs do not establish acquisition. A matching terminal is only a
termination fact, never a birth, reconstructed log, fault clearance or action.
"""

from dataclasses import dataclass, field

from . import formats as f
from .external_evidence import OBS_KEYS, project_fault_log
from .physical_evidence import NE, LedgerCoverage

_FIELDS = ('authenticity', 'authorization', 'completeness', 'provenance', 'durability')
_BATCH_KEYS = (OBS_KEYS - {'operation_sha256', 'operation_entries', 'entry'}) | {'observations'}
_ENTRY_KEYS = {'ledger_schema', 'issuer_id', 'envelope_id', 'envelope_sha256', 'operation_sha256'}


class ExternalLimit(ValueError):
    def __init__(self, name):
        super().__init__('SOURCE_LIMIT')
        self.limit_name = name


@dataclass(frozen=True)
class TerminalBinding:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    fault_sha256: str
    termination_sha256: str
    terminal_linkage: str
    terminal_classification: str | None
    current_observation_bytes: bytes
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    birth_proof: str = field(default=NE, init=False)
    action_completion: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)


@dataclass(frozen=True)
class ExternalBindings:
    terminals: tuple[TerminalBinding, ...]
    resolved_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]
    ledger_coverage: LedgerCoverage
    ledger_codes: tuple[str, ...]
    accepted: bool = field(default=False, init=False)
    snapshot_completeness: str = field(default=NE, init=False)
    pending_completeness: str = field(default=NE, init=False)
    population: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)


def _entry(entry, operation):
    f.closed(entry, _ENTRY_KEYS)
    f.require(entry['ledger_schema'] == 'colony-trust.consumed/1'
              and entry['operation_sha256'] == operation)
    f.require(type(entry['issuer_id']) is str and bool(f.NAME.fullmatch(entry['issuer_id'])))
    f.require(f.hex64(entry['envelope_id']) and f.hex64(entry['envelope_sha256']))


def _batch(raw, operation_ids):
    f.require(type(raw) is bytes and type(operation_ids) is tuple)
    if len(raw) > 16 * 1024 * 1024:
        raise ExternalLimit('ledger_snapshot_bytes')
    if len(operation_ids) > 256:
        raise ExternalLimit('operations')
    f.require(all(f.hex64(x) for x in operation_ids)
              and operation_ids == tuple(sorted(set(operation_ids))))
    batch = f.loads(raw)
    f.closed(batch, _BATCH_KEYS)
    f.require(batch['inspection_schema'] == 'colony-trust.operations-inspection/0'
              and batch['status'] == 'OBSERVED' and batch['failures'] == [] and batch['accepted'] is False)
    f.require(all(batch[x] == NE for x in _FIELDS))
    total, legacy = batch['ledger_entries'], batch['legacy_entries']
    f.require(f.integer(total) and f.integer(legacy) and legacy <= total <= 16384
              and f.hex64(batch['ledger_sha256']))
    rows = batch['observations']
    f.require(type(rows) is list)
    if len(rows) > 256:
        raise ExternalLimit('operations')
    f.require(len(rows) == len(operation_ids))
    matched = 0
    for operation, row in zip(operation_ids, rows):
        f.closed(row, OBS_KEYS)
        f.require(row['inspection_schema'] == 'colony-trust.operation-inspection/0'
                  and row['operation_sha256'] == operation and row['accepted'] is False
                  and all(row[x] == NE for x in _FIELDS))
        f.require(type(row['ledger_entries']) is int and row['ledger_entries'] == total
                  and type(row['legacy_entries']) is int and row['legacy_entries'] == legacy
                  and row['ledger_sha256'] == batch['ledger_sha256'])
        count = row['operation_entries']
        f.require(f.integer(count) and count <= total - legacy)
        matched += count
        if count > 1:
            status, errors = 'CONFLICT', ['OPERATION_MULTIPLE_ENTRIES']
        elif count == 1:
            status, errors = 'OPERATION_ENTRY_PRESENT', []
            _entry(row['entry'], operation)
        elif legacy:
            status, errors = 'LEGACY_AMBIGUITY', ['LEGACY_OPERATION_UNBOUND']
        else:
            status, errors = 'NO_OPERATION_ENTRY', []
        f.require(row['status'] == status and row['failures'] == errors)
        if count != 1:
            f.require(row['entry'] is None)
    f.require(matched + legacy <= total)
    codes = []
    if legacy:
        codes.append('LEGACY_LEDGER_UNBOUND')
    if total != matched:
        codes.append('LEDGER_OPERATION_UNBOUND')
    conflict = any(row['status'] == 'CONFLICT' for row in rows)
    if conflict:
        codes.append('LEDGER_UNAVAILABLE')
    status = 'LEGACY_UNBOUND' if legacy else 'UNBOUND' if total != matched or conflict else 'MATCH'
    return {row['operation_sha256']: row for row in rows}, LedgerCoverage(
        status, total, legacy, matched, total - matched), tuple(codes)


def link(fault_raw, lab_id, ledger_bytes, operation_ids):
    """Compare only current per-operation findings, not historical ledger digests.

The owner supplies the retained raw faults and exactly its single U/batch. No
IO, signature, log parser, history reconstruction, action or global scan occurs.
"""
    rows, coverage, ledger_codes = _batch(ledger_bytes, operation_ids)
    faults = project_fault_log(fault_raw, lab_id)
    f.require(faults.status in ('EMPTY', 'STRUCTURAL_ONLY'))
    if len(faults.termination_claims) > 256:
        raise ExternalLimit('operations')
    entries = {f.digest(f.loads(raw)): f.loads(raw) for raw in faults.entry_bytes}
    bindings, resolved, unresolved = [], [], []
    for claim in sorted(faults.termination_claims, key=lambda x: x.operation_sha256):
        f.require(claim.operation_sha256 in rows)
        row = rows[claim.operation_sha256]
        terminal = entries[claim.entry_sha256]
        status, classification, codes = NE, None, ('OPERATION_LOG_FAULTY', 'EXTERNAL_TERMINATION_NOT_EVALUATED')
        if claim.evidence == 'EMBEDDED_HISTORICAL':
            historical = terminal['data']['ledger_finding']['observation']
            if row['status'] == 'LEGACY_AMBIGUITY':
                codes = ('LEGACY_OPERATION_UNBOUND', 'OPERATION_LOG_FAULTY', 'EXTERNAL_TERMINATION_NOT_EVALUATED')
            elif (row['status'] == historical['status']
                  and row['operation_entries'] == historical['operation_entries']
                  and row['entry'] == historical['entry']):
                status, classification, codes = 'PASS', claim.classification, ('OPERATION_LOG_FAULTY',)
            else:
                status, codes = 'FAIL', ('EXTERNAL_FINDING_DIVERGENT', 'OPERATION_LOG_FAULTY')
        (resolved if status == 'PASS' else unresolved).append(claim.operation_sha256)
        bindings.append(TerminalBinding(claim.child_agent_id, claim.operation_sha256, claim.attempt,
            claim.fault_sha256, claim.entry_sha256, status, classification, f.canonical(row), codes))
    return ExternalBindings(tuple(bindings), tuple(resolved), tuple(unresolved), coverage, ledger_codes)
