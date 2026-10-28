"""Private 3C POPULATION partition, classified counts, plan match and ceilings.

Pure comparisons for the unique CURRENT_OPEN operation only, on homes already
classified inside the single owner. Never a birth, admission or authority.
"""

from dataclasses import dataclass, field

from colony_lab import lineage

from . import _attestation_core as c
from . import attestation_evidence as a
from . import formats as f
from . import physical_evidence as p
from . import _population_preflight as pf

NE = p.NE


@dataclass(frozen=True)
class Counts:
    scope: str = 'CURRENT_BEFORE_BIRTH'
    complete: str = NE
    included_agent_ids: tuple[str, ...] = ()
    record_sha256s: tuple[str, ...] = ()
    population: int | None = None
    founders: int | None = None
    children: int | None = None
    budget_totals: tuple[tuple[str, int], ...] | None = None
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)


@dataclass(frozen=True)
class Ceilings:
    population_limit: str = NE
    children_limit: str = NE
    generation_limit: str = NE
    colony_budget: str = NE
    parent_budget: str = NE
    permissions_and_diff: str = NE
    bundle_bound: str = NE
    concurrency_enforcement: str = field(default=NE, init=False)
    aggregate: str = NE
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)


@dataclass(frozen=True)
class CurrentPopulation:
    population_partition: str = NE
    frozen_completeness: str = NE
    counts: Counts = field(default_factory=Counts)
    plan_match: str = NE
    ceilings: Ceilings = field(default_factory=Ceilings)
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)


def _digest(raw, limit=16384):
    try:
        return f.digest(c.decode(raw, limit))
    except (c.CoreError, ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _needs(homes, proofs, branch, own):
    """POPULATION needs of every other INCLUDED home, with each envelope copy."""
    needs, absent_individuals = {}, set()
    for home in homes:
        proof = proofs[home.agent_id]
        if home.agent_id in branch or home.agent_id == own or proof.counted != 'INCLUDED':
            continue
        record = c.decode(home.record_bytes)
        objects = []
        if home.individual_envelope is not None:
            objects.append((c.IND, record, home.individual_envelope, home.agent_id + '/individual'))
        else:
            absent_individuals.add(c.key(c.IND, record))
        if record['role'] == 'DESCENDANT':
            for kind, role, raw, envelope in (
                    (c.ADM, 'admission', home.admission_bytes, home.admission_envelope),
                    (c.QUAL, 'qualification', home.qualification_bytes, home.qualification_envelope),
                    (c.STATEMENT, 'statement', home.statement_bytes, home.statement_envelope)):
                value = c.decode(raw, 16384 if kind == c.STATEMENT else 65536)
                objects.append((kind, value, envelope, home.agent_id + '/' + role))
        for kind, value, envelope, namespace in objects:
            k = c.key(kind, value)
            copies = needs.setdefault(k, [])
            copies.append((namespace, _digest(envelope)))
    return needs, absent_individuals


def _partition(op, homes, proofs, decision, branch, own):
    frozen = {}
    for item in op['items']:
        k = c.Key(item['kind'], item['subject']['agent_id'], item['subject']['agent_spec_id'], item['record_sha256'])
        frozen[k] = (item['role'], item['envelope_sha256'])
    decision_keys = {x.key for x in decision.needs}
    needs, absent = _needs(homes, proofs, branch, own)
    codes, historical = [], False
    for k, copies in needs.items():
        role, envelope = frozen.get(k, (None, None))
        if k in decision_keys:
            # DECISION keeps the single role; POPULATION copies must name its envelope.
            if role != 'DECISION' or any(digest != envelope for _, digest in copies):
                codes.append('FROZEN_ITEM_DIVERGENT')
            continue
        if role is None:
            if k.kind == c.IND and c.decode(next(h for h in homes if h.agent_id == k.agent_id).record_bytes)[
                    'role'] == 'DESCENDANT':
                # COMP-10: may have been AWAITING at D0; no absence history exists.
                historical = True
            else:
                codes.append('ATTESTATION_MISSING')
        elif role != 'POPULATION':
            codes.append('POPULATION_ROLE_MISMATCH')
        elif any(digest != envelope for _, digest in copies):
            codes.append('FROZEN_ITEM_DIVERGENT')
    for k, (role, _) in frozen.items():
        if role != 'POPULATION' or k in needs:
            continue
        if k in decision_keys:
            continue  # already DECISION_ROLE_MISMATCH in the 3B partition
        # COMP-08: a frozen individual now absent stays MISSING, never dropped.
        codes.append('ATTESTATION_MISSING' if k in absent else 'ATTESTATION_UNEXPECTED')
    if codes:
        return 'FAIL', p.unique(codes)
    if historical:
        return NE, ('HISTORICAL_POPULATION_ATTESTATION_UNAVAILABLE',)
    return 'PASS', ()


def _counts(op, homes, proofs, policy):
    classes = [proofs[h.agent_id].counted for h in homes]
    if any(x not in ('INCLUDED', 'EXCLUDED_OWN') for x in classes):
        status = 'FAIL' if 'BLOCKING' in classes else NE
        return Counts(complete=status, codes=('POPULATION_UNAUTHENTICATED',) if status == 'FAIL'
                      else ('CLASSIFICATION_NOT_EVALUATED',))
    included = [h for h in homes if proofs[h.agent_id].counted == 'INCLUDED']
    records = [c.decode(h.record_bytes) for h in included]
    totals = {}
    for name in sorted(f.BUDGET_KEYS):
        values = [r['budget'][name] for r in records]
        c.need(all(type(x) is int and 0 <= x <= lineage.BUDGET_MAX[name] for x in values), 'BUDGET_INVALID')
        totals[name] = sum(values)
    children = sum(r['role'] == 'DESCENDANT' and r['lineage']['parent_agent_id'] == op['parent_agent_id']
                   for r in records)
    return Counts(complete='PASS', included_agent_ids=tuple(sorted(h.agent_id for h in included)),
                  record_sha256s=tuple(sorted(f.digest(r) for r in records)), population=len(records),
                  founders=sum(r['role'] == 'FOUNDER' for r in records), children=children,
                  budget_totals=tuple(totals.items()))


def _plan(op, counts):
    if counts.complete != 'PASS':
        return NE
    plan = op['birth_plan']
    same = (list(counts.record_sha256s) == plan['population'] and counts.population == plan['population_count']
            and counts.children == plan['children_count']
            and dict(counts.budget_totals) == plan['budget_totals'])
    return 'PASS' if same else 'FAIL'


def _ceilings(op, counts, policy, n, parent_spec):
    plan = op['birth_plan']
    child, parent = plan['record'], plan['parent']
    codes = []
    def check(condition, code):
        if not condition:
            codes.append(code)
        return 'PASS' if condition else 'FAIL'
    generation = check(type(parent['lineage']['generation']) is int
                       and parent['lineage']['generation'] + 1 <= policy['max_generation'], 'GENERATION_LIMIT')
    parent_budget = check(all(child['budget'][k] <= parent['budget'][k] for k in f.BUDGET_KEYS),
                          'BUDGET_ESCALATION')
    permissions = check(set(child['lab_permissions']) <= set(parent['lab_permissions']), 'PERMISSION_ESCALATION')
    diff = check(f.canonical(op['declared_diff']) == f.canonical(child['genotype']['declared_diff'])
                 == f.canonical(lineage.spec_diff(parent_spec, plan['child_spec'])), 'UNDECLARED_MUTATION')
    permissions = a.aggregate((permissions, diff))
    if counts.complete != 'PASS':
        return Ceilings(NE, NE, generation, NE, parent_budget, permissions, NE,
                        aggregate=a.aggregate((generation, parent_budget, permissions, NE)),
                        codes=p.unique(codes))
    population = check(counts.population + 1 <= policy['max_population'], 'POPULATION_LIMIT')
    children = check(counts.children + 1 <= policy['max_children_per_parent'], 'CHILDREN_LIMIT')
    totals = dict(counts.budget_totals)
    colony = check(all(totals[k] + child['budget'][k] <= policy['colony_budget'][k] for k in f.BUDGET_KEYS),
                   'COLONY_BUDGET_EXCEEDED')
    bound = NE
    if population == 'PASS' and counts.founders >= 1 and n is not None:
        # Same bound as the preflight; an excess is a named limit, never a FAIL.
        if n > 4 * counts.population - 3 * counts.founders + 3:
            raise pf.PreflightLimit('item_references')
        bound = 'PASS'
    return Ceilings(population, children, generation, colony, parent_budget, permissions, bound,
                    aggregate=a.aggregate((population, children, generation, colony, parent_budget,
                                           permissions, bound)), codes=p.unique(codes))


def current(op, homes, proofs, decision, own, policy, n):
    """Partition/counts/plan/ceilings of the unique CURRENT_OPEN operation."""
    proofs = {x.agent_id: x for x in proofs}
    branch = set(decision.branch)
    if decision.branch_structure != 'PASS' or any(proofs[h.agent_id].counted not in ('INCLUDED', 'EXCLUDED_OWN')
                                                  for h in homes):
        partition, codes = NE, ('CLASSIFICATION_NOT_EVALUATED',)
    else:
        partition, codes = _partition(op, homes, proofs, decision, branch, own)
    frozen = a.aggregate((decision.decision_partition, partition))
    counts = _counts(op, homes, proofs, policy)
    plan = _plan(op, counts)
    parent = next((h for h in homes if h.agent_id == op['parent_agent_id']), None)
    if decision.branch_structure == 'PASS' and parent is not None:
        ceilings = _ceilings(op, counts, policy, n, c.decode(parent.spec_bytes))
    else:
        ceilings = Ceilings(codes=('BRANCH_INCOMPLETE',))
    codes = codes + counts.codes + ceilings.codes + (('POPULATION_CHANGED',) if plan == 'FAIL' else ())
    return CurrentPopulation(partition, frozen, counts, plan, ceilings, p.unique(codes))
