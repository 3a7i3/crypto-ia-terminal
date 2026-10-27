"""Private structural K/N/P/F preflight, before any envelope signature.

Detached inputs are not proof of acquisition/completeness. Provisional P/F and
an OWN candidate are NOT classified counts, an exclusion or birth authority.
"""

from dataclasses import dataclass, field

from . import _attestation_core as c
from . import _population_core as pc
from . import formats as f
from . import physical_evidence as p
from .oplog import project_log


class PreflightLimit(c.CoreError):
    def __init__(self, name):
        super().__init__('SOURCE_LIMIT')
        self.limit_name = name


def _limit(condition, name):
    if not condition:
        raise PreflightLimit(name)


@dataclass(frozen=True)
class OperationInput:
    operation_bytes: bytes
    log_bytes: bytes
    statement_bytes: bytes | None
    usage_bytes: bytes | None = None


@dataclass(frozen=True)
class OperationPreflight:
    operation_sha256: str
    scope: str
    derivation: str
    needs: tuple[c.Need, ...] = ()
    known_keys: int = 0
    derived_n: int | None = None
    provisional_p: int | None = None
    provisional_f: int | None = None
    pf_bound: int | None = None
    potential_own_agent_id: str | None = None
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    population: str = field(default=p.NE, init=False)
    counts: str = field(default=p.NE, init=False)
    own_home: str = field(default=p.NE, init=False)
    frozen_completeness: str = field(default=p.NE, init=False)
    ceilings: str = field(default=p.NE, init=False)
    authorization: str = field(default=p.NE, init=False)


def _bytes(raw, cap, name):
    if raw is not None:
        c.need(type(raw) is bytes, 'SOURCE_NAMESPACE_INVALID')
        _limit(len(raw) <= cap, name)


def _own_candidate(home, op, log, usage):
    # Physical potential only. Current crypto and exact /1 still required later.
    if home is None or not (log.pending_step == 'D3' or log.last_completed_step == 'D3'):
        return False
    try:
        if home.layout != 'OBSERVED':
            return None
        plan = op['birth_plan']
        values = ((home.record_bytes, plan['record']), (home.spec_bytes, plan['child_spec']),
                  (home.qualification_bytes, plan['qualification']))
        if any(raw is None for raw, _ in values):
            return None
        if any(raw != p.storage_bytes(expected) for raw, expected in values):
            return False
        observed = {'admission': home.admission_bytes, 'admission_envelope': home.admission_envelope,
                    'qualification_envelope': home.qualification_envelope, 'statement': home.statement_bytes,
                    'statement_envelope': home.statement_envelope}
        material = {path: (observed[role], 'LAB') for role, path, _ in p.d2_paths(op)}
        d2, _, errors = p.compare_d2(op, material, c.trust._envelope_shape)
        if errors:
            return False
        if d2.material_state != 'MATERIAL_MATCH':
            return None
        if log.last_completed_step != 'D3':
            if usage is None:
                return None
            if usage != p.storage_bytes({'runs': 0}):
                return False
        return True
    except (c.CoreError, f.FormatError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return False


def derive(homes, operations, policy_bytes, policy_pin, *, unresolved_external_ids=()):
    """Return per-operation structural facts; no trust, ledger or IO call.

Derive the union of required records independently of PREPARED's item roles.
Every structural home participates, including invalid/unclassified homes;
missing records leave the graph incomplete rather than removing that home.
The future owner must bind these detached inputs to its one retained snapshot.
"""
    c.need(type(homes) is tuple and type(operations) is tuple
           and type(unresolved_external_ids) is tuple, 'CONFIG_INVALID')
    _limit(len(homes) <= 65, 'homes')
    _limit(len(operations) <= 256 and len(unresolved_external_ids) <= 256, 'operations')
    c.need(all(type(h) is pc.HomeInput for h in homes), 'SOURCE_NAMESPACE_INVALID')
    c.need(all(type(x) is OperationInput for x in operations), 'CONFIG_INVALID')
    c.need(all(f.hex64(x) for x in unresolved_external_ids)
           and len(set(unresolved_external_ids)) == len(unresolved_external_ids), 'CONFIG_INVALID')
    selected = c.policy(policy_bytes, policy_pin)
    cap = min(252, 4 * selected['max_population'] - 4)
    for home in homes:
        for raw in (home.record_bytes, home.spec_bytes, home.qualification_bytes, home.admission_bytes):
            _bytes(raw, 65536, 'record_bytes')
        for raw in (home.statement_bytes, home.individual_envelope, home.admission_envelope,
                    home.qualification_envelope, home.statement_envelope):
            _bytes(raw, 16384, 'envelope_bytes')
    acquired = []
    ids = set(unresolved_external_ids)
    for source in operations:
        c.need(type(source.operation_bytes) is bytes and type(source.log_bytes) is bytes, 'CONFIG_INVALID')
        _limit(len(source.operation_bytes) < f.MAX_LINE, 'record_bytes')
        _bytes(source.operation_bytes, f.MAX_LINE, 'record_bytes')
        _bytes(source.log_bytes, f.MAX_LOG, 'per_log_bytes')
        _bytes(source.statement_bytes, 16384, 'envelope_bytes')
        _bytes(source.usage_bytes, 65536, 'record_bytes')
        op = c.operation(source.operation_bytes)
        log = project_log(source.log_bytes)
        digest = f.digest(op)
        c.need(log.operation_sha256 == digest and log.attempt == op['attempt']
               and log.status not in ('CORRUPT', 'TORN_TAIL', 'EMPTY', 'PREPARATION_INCOMPLETE'),
               'OPERATION_BINDING_MISMATCH')
        c.need(digest not in ids, 'DUPLICATE_OPERATION')
        ids.add(digest)
        _limit(len(ids) <= 256, 'operations')
        _limit(len(op['items']) <= cap, 'item_references')
        acquired.append((source, op, log, digest))
    try:
        structure = pc.structures(homes)
    except c.CoreError as exc:
        if str(exc) == 'SOURCE_LIMIT':
            raise PreflightLimit('branch_nodes') from None
        raise
    by_id = {h.agent_id: h for h in homes}
    facts = {x.agent_id: x for x in structure}
    latest = {}
    for _, op, _, _ in acquired:
        latest[op['child_agent_id']] = max(latest.get(op['child_agent_id'], 0), op['attempt'])
    current = [(src, op, log, digest) for src, op, log, digest in acquired
               if op['attempt'] == latest[op['child_agent_id']] and log.terminal_claim is None]
    unique_open = len(current) == 1 and not unresolved_external_ids
    results = []
    for src, op, log, digest in acquired:
        if op['attempt'] != latest[op['child_agent_id']] or log.terminal_claim is not None:
            results.append(OperationPreflight(digest, 'HISTORICAL', p.NE,
                                              codes=('HISTORICAL_POPULATION_NOT_EVALUATED',)))
            continue
        needs, codes = {}, []
        if not unique_open:
            codes.append('OPERATION_PENDING')
        if op['policy_sha256'] != policy_pin:
            codes.append('POLICY_CONTEXT_MISMATCH')
        parent_fact = facts.get(op['parent_agent_id'])
        branch = set(parent_fact.branch) if parent_fact is not None and parent_fact.status == 'PASS' else set()
        if not branch:
            codes.append('BRANCH_INCOMPLETE')
        for fact in structure:
            if fact.status != 'PASS':
                codes.extend(fact.codes)
        child = op['child_agent_id']
        own = _own_candidate(by_id.get(child), op, log, src.usage_bytes) if unique_open else False
        potential = child if own is True and child not in branch else None
        if own is None:
            codes.append('OWN_HOME_INCOMPLETE')
        missing, divergent = False, False
        def add(kind, raw, namespace):
            nonlocal missing, divergent
            if raw is None:
                missing = True
                return
            # Declared candidate q/admission records have not passed the home
            # byte checks. A size failure must escape, not become local FAIL.
            _bytes(raw, 16384 if kind == c.STATEMENT else 65536,
                   'envelope_bytes' if kind == c.STATEMENT else 'record_bytes')
            try:
                value = c.decode(raw, 16384 if kind == c.STATEMENT else 65536)
                c._add(needs, kind, value, namespace)
                _limit(len(needs) <= cap, 'item_references')
            except PreflightLimit:
                raise
            except (c.CoreError, f.FormatError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                divergent = True
        plan = op['birth_plan']
        add(c.ADM, f.canonical(plan['admission']), child + '/admission')
        add(c.QUAL, f.canonical(plan['qualification']), child + '/qualification')
        add(c.STATEMENT, src.statement_bytes, child + '/statement')
        for home in sorted(homes, key=lambda h: h.agent_id):
            try:
                record = c.decode(home.record_bytes) if home.record_bytes is not None else None
            except c.CoreError:
                record = None
                divergent = True
            if record is None:
                missing = True
                continue
            role = record.get('role')
            if role not in ('FOUNDER', 'DESCENDANT'):
                divergent = True
            if home.agent_id != potential and (role == 'FOUNDER' or home.individual_envelope is not None
                                               or home.agent_id in branch):
                add(c.IND, home.record_bytes, home.agent_id + '/individual')
            if role == 'DESCENDANT':
                for kind, raw, label in ((c.ADM, home.admission_bytes, 'admission'),
                                         (c.QUAL, home.qualification_bytes, 'qualification'),
                                         (c.STATEMENT, home.statement_bytes, 'statement')):
                    add(kind, raw, home.agent_id + '/' + label)
        if missing:
            codes.append('EVIDENCE_NOT_STORED')
        if divergent:
            codes.append('FROZEN_ITEM_DIVERGENT')
        all_structure = all(x.status == 'PASS' for x in structure)
        provisional_p = provisional_f = bound = None
        if (all_structure and branch and unique_open and own is not None
                and op['policy_sha256'] == policy_pin):
            population = [h for h in homes if h.agent_id != potential]
            provisional_p = len(population)
            provisional_f = sum(c.decode(h.record_bytes)['role'] == 'FOUNDER' for h in population)
            if provisional_p <= selected['max_population'] - 1 and provisional_f >= 1:
                bound = 4 * provisional_p - 3 * provisional_f + 3
                _limit(len(needs) <= bound, 'item_references')
        failed = divergent or not all_structure or 'POLICY_CONTEXT_MISMATCH' in codes
        status = 'FAIL' if failed else p.NE if codes else 'PASS'
        results.append(OperationPreflight(digest, 'CURRENT_OPEN', status,
            tuple(needs[k] for k in sorted(needs)), len(needs),
            None if codes else len(needs), provisional_p, provisional_f, bound,
            potential, p.unique(codes)))
    return tuple(sorted(results, key=lambda x: x.operation_sha256))
