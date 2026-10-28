"""Private 3C fault scopes and quarantine/set-aside correspondences.

Pure comparisons on the single owner's retained fault bytes, readable logs and
quarantine identities. No fault is cleared, no action performed or permitted.
"""

import re
from dataclasses import dataclass, field

from . import formats as f
from . import physical_evidence as p
from .external_evidence import project_fault_log

NE = p.NE
_GLOBAL = frozenset({'LEDGER', 'LEDGER_DIRECTORY', 'LAB_DIRECTORY', 'INDIVIDUALS_DIRECTORY',
                     'OPERATION_LOG_DIRECTORY', 'ADMISSION_DIRECTORY', 'ENVELOPE_DIRECTORY'})
_HOME = re.compile(r'(?:spec|record|birth_qualification|usage|inflight)\.json|usage\.json\.tmp'
                   r'|(?:tasks|results|j01-lab-memory)'
                   r'|tasks/[a-z0-9][a-z0-9_.-]{0,63}\.json(?:\.tmp)?|results/[a-z0-9][a-z0-9_.-]{0,63}\.json'
                   r'|j01-lab-memory/activity\.sqlite3(?:-wal|-shm|-journal)?', re.ASCII)
_ENVELOPE = re.compile(r'(?:individual|admission|birth-qualification|statement)-[0-9a-f]{64}\.envelope\.json'
                       r'|statement-[0-9a-f]{64}\.json', re.ASCII)
_IDENTITY = ('spec.json', 'record.json', 'birth_qualification.json')


@dataclass(frozen=True)
class FaultBinding:
    fault_sha256: str
    resource: str
    relative_path: str
    operation_sha256: str | None
    scope: str
    blocking: bool
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    cleared: str = field(default=NE, init=False)


@dataclass(frozen=True)
class ActionFact:
    operation_sha256: str
    action: str
    destination: str
    claim: str
    action_location: str
    identity_binding: str
    action_completion: str
    blocking: bool
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    quarantine_journal_semantics: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)
    permission: str = field(default=NE, init=False)


def _events(log_bytes, digest):
    """Strict events of this attempt only; acknowledged torn fragments are skipped."""
    events = []
    for line in log_bytes.split(b'\n'):
        try:
            event = f.loads(line)
        except f.FormatError:
            continue  # empty tail or a fragment already acknowledged by the strict parser
        if event.get('operation_sha256') == digest:
            events.append(event)
    return events


def faults(fault_raw, lab_id, attempts, terminals):
    """Scope every recorded fault; global ledger/trust faults always block."""
    projection = project_fault_log(fault_raw, lab_id)
    f.require(projection.status in ('EMPTY', 'STRUCTURAL_ONLY'))
    latest, owners = {}, {}
    for attempt in attempts:
        digest = attempt.projection.operation_sha256
        latest[digest] = attempt
        owners[digest] = (f.loads(attempt.operation_bytes)['child_agent_id'], attempt.projection.attempt)
    linked = {x.operation_sha256: x.terminal_linkage for x in terminals}
    owners.update({x.operation_sha256: (x.child_agent_id, x.attempt) for x in terminals})
    result = []
    for claim in projection.fault_claims:
        target = claim.target
        resource = target.resource if target is not None else 'SUPERVISOR_ADMIT'
        path = target.relative_path if target is not None else ''
        op = claim.operation_sha256
        if claim.scope == 'LAB' or resource in _GLOBAL or (resource == 'QUARANTINE_DIRECTORY' and path == ''):
            scope, blocking, codes = 'GLOBAL', True, ('STICKY_FAULT',)
        elif (resource == 'HOME_ENTRY' and not _HOME.fullmatch(path.split('/', 1)[1])) or (
                resource == 'ENVELOPE_ENTRY' and not _ENVELOPE.fullmatch(path.split('/', 1)[1])):
            scope, blocking, codes = 'UNBOUND', True, ('TARGET_BINDING_UNAVAILABLE',)
        elif op not in owners or owners[op] != (claim.child_agent_id, claim.attempt):
            # §3/§10: the digest alone never binds; child and attempt must be those it designates.
            scope, blocking, codes = 'UNBOUND', True, ('TARGET_BINDING_UNAVAILABLE',)
        elif op in linked:
            if linked[op] == 'PASS':
                scope, blocking, codes = 'OPERATION_HISTORICAL', False, ('OPERATION_LOG_FAULTY',)
            else:
                scope, blocking, codes = 'OPERATION_UNRESOLVED', True, ('EXTERNAL_TERMINATION_UNPROVEN',)
        else:
            attempt = latest[op]
            open_now = attempt.latest and attempt.projection.terminal_claim is None
            scope = 'OPERATION_CURRENT' if open_now else 'OPERATION_HISTORICAL'
            blocking, codes = open_now, ('STICKY_FAULT',) if open_now else ()
        if (target is not None and claim.origin == 'CONTROLLER' and claim.failure in ('FSYNC', 'RENAME')
                and resource == 'HOME_DIRECTORY'):
            codes += ('ACTION_RESTRICTED',)
        result.append(FaultBinding(claim.entry_sha256, resource, path, op, scope, blocking, p.unique(codes)))
    return tuple(sorted(result, key=lambda x: x.fault_sha256)), projection


def _identity(destination, plan, prefix_allowed):
    if plan is None:
        return NE
    for name, raw in zip(_IDENTITY, (destination.spec_bytes, destination.record_bytes,
                                     destination.qualification_bytes)):
        expected = p.storage_bytes(plan[{'spec.json': 'child_spec', 'record.json': 'record',
                                         'birth_qualification.json': 'qualification'}[name]])
        # An absent file is allowed; a quarantine needs exact bytes, a set-aside a prefix.
        if raw is not None and raw != expected and not (prefix_allowed and expected.startswith(raw)):
            return 'FAIL'
    return 'PASS'


def _claims(attempts, projection):
    """Action claims from strict readable logs and from external set-aside lines."""
    claims = {}
    for attempt in attempts:
        op = f.loads(attempt.operation_bytes)
        digest = attempt.projection.operation_sha256
        events = _events(attempt.log_bytes, digest)
        quarantine = set_aside = None
        incarnation = False
        for event in events:
            name = event['event']
            if name == 'QUARANTINE_BEGIN':
                quarantine, incarnation = 'BEGIN', False
            elif name == 'QUARANTINE_DONE':
                quarantine = 'DONE'
            elif name == 'BEGIN' and event['step'] == 'D3' and quarantine == 'DONE':
                incarnation = True
            elif name == 'BEGIN_CANCELLED' and event['step'] == 'D3':
                incarnation = False
            elif name == 'SET_ASIDE_BEGIN':
                set_aside = 'BEGIN'
            elif name == 'SET_ASIDE_DONE':
                set_aside = 'DONE'
        if quarantine:
            claims[(digest, str(op['attempt']))] = ('QUARANTINE', quarantine, op, incarnation)
        if set_aside:
            claims[(digest, 'terminal')] = ('SET_ASIDE', set_aside, op, False)
    pending = set(projection.pending_set_aside)
    for raw in projection.entry_bytes:
        entry = f.loads(raw)
        if entry['event'] in ('SET_ASIDE_BEGIN', 'SET_ASIDE_DONE'):
            op = entry['operation_sha256']
            state = 'BEGIN' if op in pending else 'DONE'
            claims[(op, 'terminal')] = ('SET_ASIDE_EXTERNAL', state, {'child_agent_id': entry['child_agent_id']},
                                       False)
    return claims


def actions(attempts, projection, quarantined, home_ids):
    """Correspondence of every destination with exactly one known action claim."""
    claims = _claims(attempts, projection)
    destinations = {(x.operation_sha256, x.destination): x for x in quarantined}
    homes = set(home_ids)
    facts = []
    for key in sorted(set(claims) | set(destinations)):
        digest, name = key
        destination = destinations.get(key)
        if key not in claims:
            facts.append(ActionFact(digest, 'UNKNOWN', name, 'NONE', 'FAIL', NE, NE, True,
                                    ('ACTION_EVIDENCE_NOT_EVALUATED',)))
            continue
        action, state, op, incarnation = claims[key]
        source = op['child_agent_id'] in homes
        codes = []
        if state == 'BEGIN':
            location = 'PASS' if source != (destination is not None) else 'FAIL'
            completion = NE
            codes.append('ACTION_EVIDENCE_NOT_EVALUATED')
        else:
            completion = 'PASS'
            location = 'PASS' if destination is not None and (not source or incarnation) else 'FAIL'
        if location == 'FAIL':
            codes.append('ACTION_LOCATION_DIVERGENT')
        plan = op.get('birth_plan')
        identity = NE
        if destination is not None:
            identity = _identity(destination, plan, action != 'QUARANTINE')
            if identity == 'FAIL':
                codes.append('ACTION_LOCATION_DIVERGENT')
            elif identity == NE:
                codes.append('ACTION_EVIDENCE_NOT_EVALUATED')
        blocking = (location != 'PASS' or completion != 'PASS'
                    or (destination is not None and identity != 'PASS'))
        facts.append(ActionFact(digest, action, name, state, location, identity, completion, blocking,
                                p.unique(codes)))
    return tuple(facts)
