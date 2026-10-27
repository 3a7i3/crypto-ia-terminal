"""3C-4 POPULATION partition, counts, plan and ceilings; temporary LAB_TEST only."""

import dataclasses
from types import SimpleNamespace

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _population_counts as pk
from colony_admission import _population_preflight as pf
from colony_admission import formats as f
from colony_admission import physical_evidence as p
from colony_admission._population_core import HomeInput
from colony_lab import lineage
from colony_registrar import registrar as reg
from tests.colony_admission import test_attestation_core as pure
from tests.colony_admission import test_population_proof as proofs
from tests.colony_lab import builders as b
from tests.colony_trust.keys import OPERATOR

machine = proofs.machine
full_profile_machine = proofs.full_profile_machine
G0 = reg.load_policy()[0]


def founder_record(config, op):
    return c.decode((config.lab_root / 'individuals' / op['parent_agent_id'] / 'record.json').read_bytes())


def exact_plan(op, records, parent_id=None):
    plan = op['birth_plan']
    plan['population'] = sorted(f.digest(r) for r in records)
    plan['population_count'] = len(records)
    plan['children_count'] = sum(r['role'] == 'DESCENDANT' and r['lineage']['parent_agent_id']
                                 == (parent_id or op['parent_agent_id']) for r in records)
    plan['budget_totals'] = {k: sum(r['budget'][k] for r in records) for k in f.BUDGET_KEYS}
    f.validate_operation(op)


def second_founder(config):
    spec = b.spec(name='second_founder')
    record = lineage.make_founder(spec, lab_permissions=['DIAGNOSTIC_PRODUCE'], budget=dict(b.BUDGET))
    env = pure.signed(record, c.IND, OPERATOR, 'individual', 'operator-1')
    agent = record['agent_id']
    proofs.ao.store(config, 'individuals/' + agent + '/record.json', f.canonical(record))
    proofs.ao.store(config, 'individuals/' + agent + '/spec.json', f.canonical(spec))
    proofs.ao.store(config, 'admission-envelopes/' + agent + '/individual-' + f.digest(record) + '.envelope.json',
                    f.canonical(env))
    return record, env


def current_of(result, op):
    return proofs.operation(result, op).current


def own_scan(fixture, *, prepare=None):
    config, op = fixture
    records = [founder_record(config.observer, op)]
    if prepare is not None:
        records += prepare(config.observer, op)
    exact_plan(op, records)
    proofs.own_machine(fixture)
    proofs.home(config.observer, op)
    return config, op, proofs.scan(config)


def test_exact_own_population_counts_plan_and_ceilings(full_profile_machine):
    config, op, result = own_scan(full_profile_machine)
    cur = current_of(result, op)
    assert proofs.proof(result, op['child_agent_id']).classification == 'OWN_OPERATION'
    assert cur.population_partition == cur.frozen_completeness == 'PASS', cur
    counts = cur.counts
    assert counts.complete == 'PASS' and counts.population == 1 and counts.founders == 1 and counts.children == 0
    assert counts.included_agent_ids == (op['parent_agent_id'],)  # own excluded, never +1
    assert cur.plan_match == 'PASS' and cur.ceilings.aggregate == 'PASS'
    assert cur.ceilings.bundle_bound == 'PASS'
    assert cur.ceilings.concurrency_enforcement == cur.ceilings.authorization == p.NE
    assert cur.accepted is counts.accepted is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        counts.population = 0


@pytest.mark.parametrize('field', ['population', 'children_count', 'budget_totals'])
def test_plan_divergence_is_population_changed(full_profile_machine, field):
    def change(config, op):
        return []
    config, op = full_profile_machine
    exact_plan(op, [founder_record(config.observer, op)])
    plan = op['birth_plan']
    if field == 'population':
        plan['population'] = ['0' * 64]
    elif field == 'children_count':
        plan['children_count'] = 1
    else:
        plan['budget_totals']['runs'] += 1
    proofs.own_machine(full_profile_machine)
    proofs.home(config.observer, op)
    cur = current_of(proofs.scan(config), op)
    assert cur.plan_match == 'FAIL' and 'POPULATION_CHANGED' in cur.codes


def test_second_founder_population_item_required_with_exact_copy(full_profile_machine):
    config, op = full_profile_machine
    record, env = second_founder(config.observer)
    op['items'].append(pure.item(c.IND, record, 'POPULATION', env=f.digest(env)))
    pure.sort_items(op)
    config, op, result = own_scan(full_profile_machine, prepare=lambda *_: [record])
    cur = current_of(result, op)
    assert cur.population_partition == cur.frozen_completeness == 'PASS', cur
    assert cur.counts.population == 2 and cur.counts.founders == 2 and cur.plan_match == 'PASS'


@pytest.mark.parametrize('case', ['omitted', 'substituted', 'decision_role', 'surplus'])
def test_population_partition_contradictions(full_profile_machine, case):
    config, op = full_profile_machine
    record, env = second_founder(config.observer)
    if case == 'substituted':
        op['items'].append(pure.item(c.IND, record, 'POPULATION', env='e' * 64))
    elif case == 'decision_role':
        op['items'].append(pure.item(c.IND, record, 'DECISION', env=f.digest(env)))
    elif case == 'surplus':
        op['items'].append(pure.item(c.IND, record, 'POPULATION', env=f.digest(env)))
        other = lineage.make_founder(b.spec(name='ghost'), lab_permissions=['DIAGNOSTIC_PRODUCE'],
                                     budget=dict(b.BUDGET))
        op['items'].append(pure.item(c.IND, other, 'POPULATION', env='d' * 64))
    pure.sort_items(op)
    config, op, result = own_scan(full_profile_machine, prepare=lambda *_: [record])
    cur = current_of(result, op)
    assert cur.frozen_completeness == 'FAIL'
    if case == 'decision_role':
        # The 3B DECISION partition already fails; the candidate is then not OWN.
        assert 'ATTESTATION_UNEXPECTED' in proofs.operation(result, op).decision.blockers
        assert proofs.proof(result, op['child_agent_id']).classification == p.NE
        assert cur.population_partition == p.NE and cur.counts.complete == p.NE
        return
    expected = {'omitted': 'ATTESTATION_MISSING', 'substituted': 'FROZEN_ITEM_DIVERGENT',
                'surplus': 'ATTESTATION_UNEXPECTED'}[case]
    assert cur.population_partition == 'FAIL' and expected in cur.codes, cur


def test_unclassified_home_nulls_exact_counts(full_profile_machine):
    config, op = full_profile_machine
    proofs.ao.store(config.observer, 'individuals/' + 'e' * 64 + '/record.json', b'{invalid stable json')
    proofs.ao.store(config.observer, 'individuals/' + 'e' * 64 + '/spec.json', b'{}')
    exact_plan(op, [founder_record(config.observer, op)])
    proofs.own_machine(full_profile_machine)
    proofs.home(config.observer, op)
    cur = current_of(proofs.scan(config), op)
    assert cur.counts.complete == 'FAIL' and cur.counts.population is None and cur.counts.budget_totals is None
    assert cur.plan_match == p.NE and cur.population_partition == p.NE
    assert cur.ceilings.population_limit == cur.ceilings.children_limit == cur.ceilings.colony_budget == p.NE


def test_operation_pending_has_no_current_population(full_profile_machine):
    config, op = full_profile_machine
    fault, terminal = proofs.logtests.external(config.observer, child='e' * 64, op='f' * 64, version=0, count=0)
    proofs.base.write(config.observer.fault_file, proofs.raw(fault, terminal))
    cur = current_of(proofs.scan(config), op)
    assert cur.counts.complete == p.NE and cur.plan_match == p.NE and 'OPERATION_PENDING' in cur.codes


# Detached pure checks of limits and COMP-08/COMP-10.

def detached(*records, envelopes=None):
    homes, proof = [], {}
    for record in records:
        homes.append(HomeInput(record['agent_id'], f.canonical(record), b'{}',
                               individual_envelope=(envelopes or {}).get(record['agent_id'])))
        proof[record['agent_id']] = SimpleNamespace(counted='INCLUDED', classification='AUTHENTICATED')
    return tuple(homes), proof


def fake(agent, role='FOUNDER', parent=None, **budget):
    values = {**b.BUDGET, **budget}
    return {'agent_id': agent, 'agent_spec_id': agent[::-1], 'role': role, 'budget': values,
            'lineage': {'parent_agent_id': parent, 'generation': 1 if role == 'FOUNDER' else 2},
            'lab_permissions': ['DIAGNOSTIC_PRODUCE']}


def plan_op(parent, child_budget=None, *, permissions=('DIAGNOSTIC_PRODUCE',)):
    child = {'budget': {**b.BUDGET, **(child_budget or {})}, 'lab_permissions': list(permissions),
             'genotype': {'declared_diff': []}}
    return {'parent_agent_id': parent['agent_id'], 'declared_diff': [], 'items': [],
            'birth_plan': {'record': child, 'parent': parent, 'child_spec': {}}}


def counts_of(op, records):
    homes, proof = detached(*records)
    return pk._counts(op, homes, proof, G0)


def test_population_children_and_budget_ceilings_equal_then_plus_one(monkeypatch):
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: [])
    parent = fake('a' * 64)
    others = [fake(f'{i:064x}', 'DESCENDANT', 'b' * 64) for i in range(1, 5)]
    op = plan_op(parent)
    counts = counts_of(op, [parent, *others])
    assert counts.population == 5
    assert pk._ceilings(op, counts, G0, None, {}).population_limit == 'PASS'  # 5+1 == 6
    counts = counts_of(op, [parent, *others, fake('c' * 64)])
    ceilings = pk._ceilings(op, counts, G0, None, {})
    assert ceilings.population_limit == 'FAIL' and 'POPULATION_LIMIT' in ceilings.codes
    children = [fake(f'{i:064x}', 'DESCENDANT', parent['agent_id']) for i in (1, 2)]
    ceilings = pk._ceilings(op, counts_of(op, [parent, *children]), G0, None, {})
    assert ceilings.children_limit == 'FAIL' and 'CHILDREN_LIMIT' in ceilings.codes
    ceilings = pk._ceilings(op, counts_of(op, [parent, children[0]]), G0, None, {})
    assert ceilings.children_limit == 'PASS'


@pytest.mark.parametrize('name', sorted(f.BUDGET_KEYS))
def test_each_colony_budget_at_cap_then_cap_plus_one(monkeypatch, name):
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: [])
    cap, unit = G0['colony_budget'][name], lineage.BUDGET_MAX[name]
    child = min(b.BUDGET[name], unit)
    parent = fake('a' * 64, **{name: child})
    records, remaining = [parent], cap - 2 * child
    while remaining > 0:
        value = min(unit, remaining)
        zero = {k: 0 for k in f.BUDGET_KEYS}
        records.append(fake(f'{len(records):064x}', **{**zero, name: value}))
        remaining -= value
    op = plan_op(parent, {name: child})
    counts = counts_of(op, records)
    assert dict(counts.budget_totals)[name] + child == cap
    assert pk._ceilings(op, counts, dict(G0, max_population=64), None, {}).colony_budget == 'PASS'
    records.append(fake('f' * 64, **{**{k: 0 for k in f.BUDGET_KEYS}, name: 1}))
    ceilings = pk._ceilings(op, counts_of(op, records), dict(G0, max_population=64), None, {})
    assert ceilings.colony_budget == 'FAIL' and 'COLONY_BUDGET_EXCEEDED' in ceilings.codes


@pytest.mark.parametrize('value', [True, 1.0, -1, 10 ** 40])
def test_budget_integers_are_strict(value):
    parent = fake('a' * 64, runs=value)
    with pytest.raises(c.CoreError):
        counts_of(plan_op(fake('b' * 64)), [parent])


def test_parent_budget_permissions_and_generation(monkeypatch):
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: [])
    parent = fake('a' * 64, runs=2)
    op = plan_op(parent, {'runs': 3})
    counts = counts_of(op, [parent])
    ceilings = pk._ceilings(op, counts, G0, None, {})
    assert ceilings.parent_budget == 'FAIL' and 'BUDGET_ESCALATION' in ceilings.codes
    op = plan_op(fake('a' * 64), permissions=('DIAGNOSTIC_PRODUCE', 'GOVERNED_ARTIFACT_READ'))
    ceilings = pk._ceilings(op, counts, G0, None, {})
    assert ceilings.permissions_and_diff == 'FAIL' and 'PERMISSION_ESCALATION' in ceilings.codes
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: ['name'])
    ceilings = pk._ceilings(plan_op(fake('a' * 64)), counts, G0, None, {})
    assert ceilings.permissions_and_diff == 'FAIL' and 'UNDECLARED_MUTATION' in ceilings.codes
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: [])
    deep = fake('a' * 64)
    deep['lineage']['generation'] = G0['max_generation']
    ceilings = pk._ceilings(plan_op(deep), counts, G0, None, {})
    assert ceilings.generation_limit == 'FAIL' and 'GENERATION_LIMIT' in ceilings.codes


def test_bundle_bound_exact_then_plus_one_is_named_limit(monkeypatch):
    monkeypatch.setattr(pk.lineage, 'spec_diff', lambda *a: [])
    parent = fake('a' * 64)
    op = plan_op(parent)
    counts = counts_of(op, [parent, fake('b' * 64, 'DESCENDANT', 'a' * 64)])  # P=2, F=1 => 8
    assert pk._ceilings(op, counts, G0, 8, {}).bundle_bound == 'PASS'
    with pytest.raises(pf.PreflightLimit) as exc:
        pk._ceilings(op, counts, G0, 9, {})
    assert exc.value.limit_name == 'item_references'


def partition(op, records, envelopes=None, decision_keys=()):
    homes, proof = detached(*records, envelopes=envelopes)
    decision = SimpleNamespace(needs=tuple(SimpleNamespace(key=k) for k in decision_keys))
    return pk._partition(op, homes, proof, decision, set(), None)


def env_bytes(tag):
    return f.canonical({'tag': tag})


def test_comp08_frozen_individual_now_absent_is_missing():
    founder, other = fake('a' * 64), fake('b' * 64)
    op = plan_op(founder)
    op['items'] = [{'kind': c.IND, 'subject': {'agent_id': other['agent_id'], 'agent_spec_id':
                    other['agent_spec_id']}, 'record_sha256': f.digest(other), 'role': 'POPULATION',
                    'envelope_sha256': 'e' * 64}]
    status, codes = partition(op, [other])
    assert status == 'FAIL' and 'ATTESTATION_MISSING' in codes


def test_comp10_descendant_individual_present_but_not_frozen_is_historical_ne():
    other = fake('b' * 64, 'DESCENDANT', 'a' * 64)
    op = plan_op(fake('a' * 64))
    homes, proof = detached(other, envelopes={other['agent_id']: env_bytes('ind')})
    # Its own triple is required and frozen; only the individual may be historical.
    op['items'] = []
    decision = SimpleNamespace(needs=())
    homes = (dataclasses.replace(homes[0], admission_bytes=f.canonical({'child_agent_id': other['agent_id'],
             'child_agent_spec_id': other['agent_spec_id']}), qualification_bytes=f.canonical(
             {'agent_id': 'a' * 64, 'agent_spec_id': 'f' * 64}), statement_bytes=f.canonical(
             {'subject_agent_id': 'a' * 64, 'subject_agent_spec_id': 'f' * 64})),)
    for raw, kind in ((homes[0].admission_bytes, c.ADM), (homes[0].qualification_bytes, c.QUAL),
                      (homes[0].statement_bytes, c.STATEMENT)):
        k = c.key(kind, c.decode(raw))
        op['items'].append({'kind': kind, 'subject': {'agent_id': k.agent_id, 'agent_spec_id': k.agent_spec_id},
                            'record_sha256': k.record_sha256, 'role': 'POPULATION', 'envelope_sha256': None})
    status, codes = pk._partition(op, homes, proof, decision, set(), None)
    assert status == p.NE and codes == ('HISTORICAL_POPULATION_ATTESTATION_UNAVAILABLE',)
    op['items'].pop()
    status, codes = pk._partition(op, homes, proof, decision, set(), None)
    assert status == 'FAIL' and 'ATTESTATION_MISSING' in codes  # never for a triple


def test_founder_individual_missing_from_prepared_is_missing_not_historical():
    founder = fake('b' * 64)
    status, codes = partition(plan_op(fake('a' * 64)), [founder], {founder['agent_id']: env_bytes('ind')})
    assert status == 'FAIL' and 'ATTESTATION_MISSING' in codes


def test_decision_key_copy_from_population_home_must_name_decision_envelope():
    founder = fake('b' * 64)
    k = c.key(c.IND, founder)
    raw = env_bytes('ind')
    op = plan_op(fake('a' * 64))
    item = {'kind': c.IND, 'subject': {'agent_id': k.agent_id, 'agent_spec_id': k.agent_spec_id},
            'record_sha256': k.record_sha256, 'role': 'DECISION', 'envelope_sha256': f.digest(c.decode(raw))}
    op['items'] = [item]
    assert partition(op, [founder], {founder['agent_id']: raw}, (k,)) == ('PASS', ())
    item['envelope_sha256'] = 'e' * 64
    status, codes = partition(op, [founder], {founder['agent_id']: raw}, (k,))
    assert status == 'FAIL' and 'FROZEN_ITEM_DIVERGENT' in codes


def test_population_need_frozen_as_decision_is_role_mismatch():
    founder = fake('b' * 64)
    raw = env_bytes('ind')
    op = plan_op(fake('a' * 64))
    op['items'] = [{'kind': c.IND, 'subject': {'agent_id': founder['agent_id'], 'agent_spec_id':
                    founder['agent_spec_id']}, 'record_sha256': f.digest(founder), 'role': 'DECISION',
                    'envelope_sha256': f.digest(c.decode(raw))}]
    status, codes = partition(op, [founder], {founder['agent_id']: raw})
    assert status == 'FAIL' and 'POPULATION_ROLE_MISMATCH' in codes
