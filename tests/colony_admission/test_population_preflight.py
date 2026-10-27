"""Private global graph bounds on detached temporary LAB_TEST data, no crypto."""

import copy
import dataclasses

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _population_preflight as pf
from colony_admission import formats as f
from colony_admission import physical_evidence as p
from tests.colony_admission import test_attestation_core as helpers
from tests.colony_admission import test_population_core as population_tests
from tests.colony_admission import test_attestation_projection as projection
from tests.colony_admission.test_observer import entry, prefix
from tests.colony_admission.test_oplog import raw

complete = projection.complete
population = population_tests.population


@pytest.fixture
def material(population):
    op = c.operation(population['snapshots'][0][0])
    return dict(homes=population['homes'], op=op, statement=population['homes'][1].statement_bytes,
                policy=population['policy_raw'], pin=population['policy_pin'])


def project(material, *, level=0, events=None, usage=None, external=()):
    op = material['op']
    events = prefix(level, op=op) if events is None else events
    inp = pf.OperationInput(f.canonical(op), raw(*events), material['statement'], usage)
    return pf.derive(material['homes'], (inp,), material['policy'], material['pin'],
                     unresolved_external_ids=external)[0]


def own_storage(material):
    home = material['homes'][1]
    plan = material['op']['birth_plan']
    material['homes'] = (material['homes'][0], dataclasses.replace(home,
        record_bytes=p.storage_bytes(plan['record']), spec_bytes=p.storage_bytes(plan['child_spec']),
        qualification_bytes=p.storage_bytes(plan['qualification']), layout='OBSERVED'))


def test_complete_graph_all_homes_and_no_crypto_or_count_authority(material, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('crypto or ledger before structural preflight')
    monkeypatch.setattr(c.trust, 'classify_envelope', forbidden)
    monkeypatch.setattr(c.trust, 'inspect_operations_fd', forbidden)
    result = project(material)
    assert result.derivation == 'PASS' and result.derived_n == result.known_keys == 5
    assert result.provisional_p == 2 and result.provisional_f == 1 and result.pf_bound == 8
    assert result.population == result.counts == result.own_home == result.ceilings == p.NE
    assert result.frozen_completeness == result.authorization == p.NE and result.accepted is False
    assert any(n.key == c.key(c.IND, c.decode(material['homes'][1].record_bytes)) for n in result.needs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.derived_n = 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.needs[0].namespaces = ()


def test_derived_graph_independent_of_frozen_missing_or_role_reclassification(material):
    original = project(material)
    material['op']['items'] = []
    assert project(material).needs == original.needs
    material['op']['items'] = [helpers.item(c.IND, c.decode(material['homes'][0].record_bytes), 'POPULATION')]
    assert project(material).needs == original.needs
    assert project(material).frozen_completeness == p.NE


@pytest.mark.parametrize('field', ['individual_envelope', 'qualification_envelope', 'admission_envelope', 'statement_envelope'])
def test_invalid_or_revoked_envelopes_never_filter_structural_homes(material, field):
    baseline = project(material)
    child = dataclasses.replace(material['homes'][1], **{field: b'not a signature'})
    material['homes'] = (material['homes'][0], child)
    changed = project(material)
    assert changed.needs == baseline.needs and changed.provisional_p == 2
    assert changed.population == p.NE


def test_absent_individual_off_branch_omitted_but_mandatory_founder_remains(material):
    parent, child = material['homes']
    material['homes'] = (dataclasses.replace(parent, individual_envelope=None),
                         dataclasses.replace(child, individual_envelope=None))
    result = project(material)
    assert result.derived_n == 4
    individual_ids = {n.key.agent_id for n in result.needs if n.key.kind == c.IND}
    assert individual_ids == {parent.agent_id}
    assert result.population == result.counts == p.NE


@pytest.mark.parametrize('field', ['qualification_bytes', 'admission_bytes', 'statement_bytes'])
def test_missing_descendant_record_incomplete_not_silently_removed(material, field):
    child = dataclasses.replace(material['homes'][1], **{field: None})
    material['homes'] = (material['homes'][0], child)
    result = project(material)
    assert result.derivation == p.NE and result.derived_n is None
    assert 'EVIDENCE_NOT_STORED' in result.codes
    assert result.provisional_p == 2


@pytest.mark.parametrize('field,value', [('record_bytes', None), ('spec_bytes', None),
    ('record_bytes', b'{}'), ('spec_bytes', b'{}')])
def test_structurally_invalid_home_kept_as_failure_without_exact_p_f(material, field, value):
    material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1], **{field: value}))
    result = project(material)
    assert result.derivation == 'FAIL' and result.provisional_p is result.provisional_f is None
    assert result.derived_n is None
    assert result.pf_bound is None and result.counts == p.NE


def test_branch_missing_parent_not_a_positive_subset(material):
    material['homes'] = (material['homes'][1],)
    result = project(material)
    assert result.derivation == 'FAIL' and 'BRANCH_INCOMPLETE' in result.codes
    assert result.provisional_p is result.derived_n is None


@pytest.mark.parametrize('level', [2, 3])
def test_potential_own_only_after_exact_d3_identity_and_d2_material(material, level):
    own_storage(material)
    op = material['op']
    events = prefix(level, op=op)
    if level == 2:
        events += [entry('BEGIN', 'D3', op=op)]
    result = project(material, events=events, usage=p.storage_bytes({'runs': 0}) if level == 2 else None)
    assert result.derivation == 'PASS' and result.potential_own_agent_id == op['child_agent_id']
    assert result.provisional_p == result.provisional_f == 1 and result.derived_n == result.pf_bound == 4
    assert result.own_home == result.counts == result.population == p.NE


def test_done_d3_does_not_need_or_parse_mutable_usage(material):
    own_storage(material)
    result = project(material, level=3, usage=b'opaque runtime bytes')
    assert result.potential_own_agent_id == material['op']['child_agent_id']
    assert result.own_home == p.NE


@pytest.mark.parametrize('change', ['layout', 'missing_record', 'missing_env', 'missing_usage'])
def test_incomplete_own_candidate_cannot_supply_tighter_p_f(material, change):
    own_storage(material)
    child = material['homes'][1]
    changes = {'layout': {'layout': 'PARTIAL'}, 'missing_record': {'record_bytes': None},
               'missing_env': {'statement_envelope': None}, 'missing_usage': {}}[change]
    material['homes'] = (material['homes'][0], dataclasses.replace(child, **changes))
    events = prefix(2, op=material['op']) + [entry('BEGIN', 'D3', op=material['op'])]
    result = project(material, events=events, usage=None if change == 'missing_usage' else p.storage_bytes({'runs': 0}))
    assert result.potential_own_agent_id is None and result.provisional_p is None
    assert result.derivation != 'PASS' and 'OWN_HOME_INCOMPLETE' in result.codes


@pytest.mark.parametrize('case', ['before_begin', 'cancelled', 'raw_identity', 'usage', 'd2_substitution'])
def test_matching_id_never_alone_establishes_own_potential(material, case):
    own_storage(material)
    op = material['op']
    events = prefix(2, op=op) + [entry('BEGIN', 'D3', op=op)]
    usage = p.storage_bytes({'runs': 0})
    if case == 'before_begin':
        events = prefix(2, op=op)
    elif case == 'cancelled':
        events += [entry('BEGIN_CANCELLED', 'D3', op=op, code='LAB_STOPPED')]
    elif case == 'raw_identity':
        material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1],
            record_bytes=f.canonical(op['birth_plan']['record'])))
    elif case == 'usage':
        usage = f.canonical({'runs': 0})
    else:
        material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1],
            statement_envelope=b'{}'))
    result = project(material, events=events, usage=usage)
    assert result.potential_own_agent_id is None and result.own_home == p.NE


def test_current_external_unknown_prevents_own_or_p_f_selection(material):
    own_storage(material)
    result = project(material, level=3, external=('f' * 64,))
    assert result.derivation == p.NE and 'OPERATION_PENDING' in result.codes
    assert result.potential_own_agent_id is result.provisional_p is result.derived_n is None


def test_historical_plan_not_compared_to_current_population(material):
    op = material['op']
    result = project(material, events=prefix(3, op=op) + [entry('COMMITTED', op=op)])
    assert result.scope == 'HISTORICAL' and result.derivation == p.NE
    assert not result.needs and result.provisional_p is None
    assert result.codes == ('HISTORICAL_POPULATION_NOT_EVALUATED',)


def test_two_open_operations_never_select_one_for_own(material):
    op = material['op']
    other = copy.deepcopy(op)
    other['child_agent_id'] = 'e' * 64
    other['birth_plan']['child_spec']['agent_id'] = 'e' * 64
    other['birth_plan']['record']['agent_id'] = 'e' * 64
    sources = tuple(pf.OperationInput(f.canonical(x), raw(*prefix(op=x)), material['statement']) for x in (op, other))
    result = pf.derive(material['homes'], sources, material['policy'], material['pin'])
    assert all('OPERATION_PENDING' in x.codes and x.provisional_p is x.derived_n is None for x in result)


def test_policy_count_limit_applies_even_when_graph_incomplete(material):
    policy = c.decode(material['policy'])
    policy['max_population'] = 2
    material['policy'], material['pin'] = f.canonical(policy), f.digest(policy)
    material['op']['policy_sha256'] = material['pin']
    material['op']['birth_plan']['policy_sha256'] = material['pin']
    # Frozen4 fits policy cap4, but five derived keys do not.
    material['statement'] = None
    # Missing the candidate statement can still be derived from the home copy.
    with pytest.raises(pf.PreflightLimit) as caught:
        project(material)
    assert caught.value.limit_name == 'item_references'


def test_bound_not_asserted_when_population_assumption_outside_policy(material):
    own_storage(material)
    # Keep two homes and a max_population=2 policy: prebirth P=2 violates assumption.
    policy = c.decode(material['policy'])
    policy['max_population'] = 2
    material['policy'], material['pin'] = f.canonical(policy), f.digest(policy)
    material['op']['policy_sha256'] = material['pin']
    material['op']['birth_plan']['policy_sha256'] = material['pin']
    # Avoid universal cap failure by omitting the off-branch optional individual.
    material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1], individual_envelope=None))
    result = project(material)
    assert result.provisional_p == 2 and result.pf_bound is None
    assert result.ceilings == p.NE


def test_no_current_operation_does_not_invent_birth_or_count_verdict(material):
    assert pf.derive(material['homes'], (), material['policy'], material['pin']) == ()


@pytest.mark.parametrize('which', ['homes', 'operations', 'union'])
def test_hard_counts_before_crypto(material, which):
    if which == 'homes':
        homes, ops, ext = material['homes'] * 33, (), ()
    elif which == 'operations':
        inp = pf.OperationInput(f.canonical(material['op']), raw(*prefix(op=material['op'])), material['statement'])
        homes, ops, ext = material['homes'], (inp,) * 257, ()
    else:
        inp = pf.OperationInput(f.canonical(material['op']), raw(*prefix(op=material['op'])), material['statement'])
        homes, ops, ext = material['homes'], (inp,), tuple(f'{i:064x}' for i in range(256))
    with pytest.raises(pf.PreflightLimit) as caught:
        pf.derive(homes, ops, material['policy'], material['pin'], unresolved_external_ids=ext)
    assert caught.value.limit_name == ('homes' if which == 'homes' else 'operations')


@pytest.mark.parametrize('field,limit', [('record_bytes', 65536), ('statement_bytes', 16384),
                                      ('individual_envelope', 16384)])
def test_byte_limit_not_downgraded_to_local_missing_record(material, field, limit):
    material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1], **{field: b'x' * (limit + 1)}))
    with pytest.raises(pf.PreflightLimit) as caught:
        project(material)
    assert caught.value.limit_name == ('record_bytes' if limit == 65536 else 'envelope_bytes')


@pytest.mark.parametrize('count,exceeds', [(17, False), (18, True)])
def test_g0_twenty_twentyone_derived_keys_not_taken_from_frozen_list(material, count, exceeds):
    from colony_admission._population_core import HomeInput
    from tests.colony_lab import builders
    homes = [material['homes'][0]]
    for i in range(count - 1):
        spec, record = builders.founder(name='other_founder_' + str(i))
        homes.append(HomeInput(record['agent_id'], f.canonical(record), f.canonical(spec)))
    material['homes'] = tuple(homes)
    material['op']['items'] = []  # A caller's empty declaration cannot shrink N.
    if exceeds:
        with pytest.raises(pf.PreflightLimit) as caught:
            project(material)
        assert caught.value.limit_name == 'item_references'
    else:
        result = project(material)
        assert result.derived_n == 20 and result.provisional_p == result.provisional_f == 17
        assert result.pf_bound is None and result.ceilings == p.NE


def test_same_qualification_two_namespaces_is_one_key_with_all_copies(material):
    from colony_admission._population_core import HomeInput
    from colony_lab import lineage
    from tests.colony_lab import builders
    parent = c.decode(material['homes'][0].record_bytes)
    parent_spec = c.decode(material['homes'][0].spec_bytes)
    q = c.decode(material['homes'][1].qualification_bytes)
    spec = builders.spec(name='shared_q_sibling')
    record = lineage.make_descendant(parent, parent_spec, spec, parent_qualification=q,
        lab_permissions=['DIAGNOSTIC_PRODUCE'], budget=dict(builders.BUDGET),
        declared_diff=lineage.spec_diff(parent_spec, spec))
    admission = helpers.admission(record, parent, q, material['pin'])
    home = HomeInput(record['agent_id'], f.canonical(record), f.canonical(spec), f.canonical(q),
        f.canonical(admission), material['statement'], individual_envelope=b'{}')
    material['homes'] += (home,)
    result = project(material)
    keys = [n for n in result.needs if n.key == c.key(c.QUAL, q)]
    assert len(keys) == 1 and set(keys[0].namespaces) == {
        material['homes'][1].agent_id + '/qualification', home.agent_id + '/qualification'}
    assert result.provisional_p == 3 and result.provisional_f == 1 and result.derived_n == 7


def test_two_qualifications_same_subject_keep_distinct_hash_keys(material):
    q = c.decode(material['homes'][1].qualification_bytes)
    q['reviewer_id'] = 'another-present-reviewer'
    new_statement = f.canonical(helpers.statement(q))
    material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1],
        qualification_bytes=f.canonical(q), statement_bytes=new_statement))
    result = project(material)
    qualified = [n for n in result.needs if n.key.kind == c.QUAL]
    assert len(qualified) == 2 and len({n.key.agent_id for n in qualified}) == 1
    assert len({n.key.record_sha256 for n in qualified}) == 2 and result.derived_n == 7


def test_fail_dominates_missing_and_unknown_external_prerequisite(material):
    material['homes'] = (material['homes'][0], dataclasses.replace(material['homes'][1],
        spec_bytes=b'{}', statement_bytes=None))
    result = project(material, external=('f' * 64,))
    assert result.derivation == 'FAIL' and result.derived_n is None
    assert 'OPERATION_PENDING' in result.codes and 'EVIDENCE_NOT_STORED' in result.codes
    assert result.provisional_p is None


def test_import_has_no_io_and_no_public_export(monkeypatch):
    import importlib
    import os
    import colony_admission
    def forbidden(*args, **kwargs):
        pytest.fail('IO at import')
    monkeypatch.setattr(os, 'open', forbidden)
    importlib.reload(pf)
    assert not hasattr(colony_admission, 'PopulationObserver')
    assert not hasattr(colony_admission, 'PopulationConfig')


@pytest.mark.parametrize('role,kind', [('qualification', c.QUAL), ('admission', c.ADM)])
def test_oversized_declared_candidate_record_is_global_limit_not_local_failure(material, role, kind):
    op = material['op']
    record = op['birth_plan'][role]
    record['padding'] = 'x' * 65536
    op['presented'][role]['record_sha256'] = f.digest(record)
    for item in op['items']:
        if item['kind'] == kind:
            item['record_sha256'] = f.digest(record)
    helpers.sort_items(op)
    f.validate_operation(op)
    assert len(f.canonical(op)) < f.MAX_LINE
    with pytest.raises(pf.PreflightLimit) as caught:
        project(material)
    assert caught.value.limit_name == 'record_bytes'


def test_declared_operation_at_strict_line_bound_has_named_limit(material):
    inp = pf.OperationInput(b'x' * f.MAX_LINE, b'', None)
    with pytest.raises(pf.PreflightLimit) as caught:
        pf.derive(material['homes'], (inp,), material['policy'], material['pin'])
    assert caught.value.limit_name == 'record_bytes'


def test_empty_home_universe_has_only_known_candidate_keys_not_exact_n(material):
    material['homes'] = ()
    result = project(material)
    assert result.known_keys == 3 and result.derived_n is None
    assert result.derivation == p.NE and 'BRANCH_INCOMPLETE' in result.codes
    assert result.provisional_p is result.provisional_f is result.pf_bound is None


@pytest.mark.parametrize('extra_founder', [False, True])
def test_absolute_252_253_derived_graph_boundary_under_policy64(material, extra_founder):
    from colony_admission._population_core import HomeInput
    from colony_lab import lineage
    from tests.colony_lab import builders
    selected = c.decode(material['policy'])
    selected['max_population'] = 64
    material['policy'], material['pin'] = f.canonical(selected), f.digest(selected)
    op = material['op']
    op['policy_sha256'] = op['birth_plan']['policy_sha256'] = material['pin']
    op['birth_plan']['admission']['policy_sha256'] = material['pin']
    op['presented']['admission']['record_sha256'] = f.digest(op['birth_plan']['admission'])
    for item in op['items']:
        if item['kind'] == c.ADM:
            item['record_sha256'] = op['presented']['admission']['record_sha256']
    helpers.sort_items(op)
    parent_home = material['homes'][0]
    parent, parent_spec = c.decode(parent_home.record_bytes), c.decode(parent_home.spec_bytes)
    homes = [parent_home]
    for i in range(62):
        spec = builders.spec(name='bounded_sibling_' + str(i))
        q = builders.qualification(parent, reviewer='independent-fixture-' + str(i))
        record = lineage.make_descendant(parent, parent_spec, spec, parent_qualification=q,
            lab_permissions=['DIAGNOSTIC_PRODUCE'], budget=dict(builders.BUDGET),
            declared_diff=lineage.spec_diff(parent_spec, spec))
        admission = helpers.admission(record, parent, q, material['pin'])
        homes.append(HomeInput(record['agent_id'], f.canonical(record), f.canonical(spec), f.canonical(q),
            f.canonical(admission), f.canonical(helpers.statement(q)), individual_envelope=b'{}'))
    if extra_founder:
        spec, record = builders.founder(name='one_extra_founder')
        homes.append(HomeInput(record['agent_id'], f.canonical(record), f.canonical(spec)))
    material['homes'] = tuple(homes)
    if extra_founder:
        with pytest.raises(pf.PreflightLimit) as caught:
            project(material)
        assert caught.value.limit_name == 'item_references'
    else:
        result = project(material)
        assert result.derived_n == result.pf_bound == 252
        assert result.provisional_p == 63 and result.provisional_f == 1
        assert result.counts == result.ceilings == p.NE
