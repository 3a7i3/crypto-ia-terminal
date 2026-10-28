"""3C acceptance family C-12 (OWN-01..05) through the public scan_population().

The candidate's own home is written with the exact D3 storage bytes of the
plan (spec, record, qualification, then usage {runs:0}, then layout, as
Supervisor writes them). Variants change one fact each; codes are observed.
"""

import copy
import os

import pytest

from colony_admission import physical_evidence as p
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_population_observer as tpo
from tests.colony_admission.acceptance.corpus import case
from tests.colony_admission.test_oplog import raw

machine = tpo.machine
full_profile_machine = ao.full_profile_machine
proofs = tpo.proofs
NE = p.NE


def candidate(fixture, *, level=2, events=None, consumed=True, population=None):
    """Exact plan counting the founder only (own excluded), then the operation log."""
    config, op = fixture
    records = [tpo.counts.founder_record(config.observer, op)]
    tpo.counts.exact_plan(op, records + (population(op) if population else []))
    # The plan changes the operation digest: log events are built from the final op.
    events = events(op) if callable(events) else events
    proofs.own_machine(fixture, level=level, events=events, consumed=consumed)
    return config, op


def homes(result, op):
    child = next(x for x in result.homes if x.agent_id == op['child_agent_id'])
    founder = next(x for x in result.homes if x.agent_id == op['parent_agent_id'])
    return child, founder


def not_own(result, op):
    """No positive OWN anywhere: no exclusion usable, no exact count, no PASS."""
    current, = [x for x in result.operations if x.scope == 'CURRENT_OPEN']
    assert current.own_home == NE and current.own_agent_id is None
    assert current.counts.complete != 'PASS' and current.counts.population is None
    assert current.counts.included_agent_ids == () and current.plan_match == NE
    assert current.ceilings.aggregate == NE
    assert 'OWN_OPERATION' not in {x.classification for x in result.homes}
    assert result.status == 'BLOCKED'
    tpo.permanent(result)
    return current


OWN_01 = ['exact_open_d3', 'admission_not_consumed', 'plan_counting_own']


@pytest.mark.parametrize('variant', OWN_01, ids=OWN_01)
@case('3C:OWN-01')
def test_own_01_exact_open_d3_home_is_excluded_once_and_grants_nothing(full_profile_machine, variant):
    plan_record = (lambda op: [op['birth_plan']['record']]) if variant == 'plan_counting_own' else None
    config, op = candidate(full_profile_machine, consumed=variant != 'admission_not_consumed',
                           population=plan_record)
    proofs.home(config.observer, op)
    result = tpo.observe(config)
    child, founder = homes(result, op)
    current, = result.operations
    if variant == 'admission_not_consumed':
        # The /1 admission row is a precondition: without it, never OWN.
        assert child.classification == NE and child.counted == 'NE'
        assert 'BIRTH_COMMIT_UNPROVEN' in child.classification_codes
        not_own(result, op)
        return
    assert (child.classification, child.counted, child.classification_codes) == ('OWN_OPERATION', 'EXCLUDED_OWN', ())
    assert [x.classification for x in result.homes].count('OWN_OPERATION') == 1
    assert (founder.classification, founder.counted) == ('AUTHENTICATED', 'INCLUDED')
    assert (current.scope, current.own_home, current.own_agent_id) == ('CURRENT_OPEN', 'PASS', op['child_agent_id'])
    # Own excluded once before the comparison: the founder alone is counted.
    assert current.counts.complete == 'PASS' and current.counts.population == 1
    assert current.counts.included_agent_ids == (op['parent_agent_id'],)
    if variant == 'plan_counting_own':
        assert current.plan_match == 'FAIL' and 'POPULATION_CHANGED' in current.blockers
        assert result.status == 'BLOCKED' and 'POPULATION_CHANGED' in result.blockers
    else:
        assert current.plan_match == current.ceilings.aggregate == 'PASS'
        assert result.status == 'OBSERVED' and result.blockers == ()
    # No resume: the observation exposes no permission at all.
    for name in ('can_resume', 'can_parent', 'admitted', 'qualified'):
        assert not hasattr(result, name) and not hasattr(current, name) and not hasattr(child, name)
    tpo.permanent(result)


OWN_02 = ['done_d3_runtime_mutated', 'done_d3_layout_missing']


@pytest.mark.parametrize('variant', OWN_02, ids=OWN_02)
@case('3C:OWN-02')
def test_own_02_after_done_d3_identity_and_layout_only_never_mutable_content(full_profile_machine, monkeypatch,
                                                                            variant):
    config, op = candidate(full_profile_machine, level=3, events=())
    targets = proofs.home(config.observer, op, usage=b'{"runs": 7, "mutated": true}',
                          layout=variant != 'done_d3_layout_missing')
    root = config.observer.lab_root / 'individuals' / op['child_agent_id']
    mutable = {targets['usage.json'].stat().st_ino}
    if variant == 'done_d3_runtime_mutated':
        base.write(root / 'tasks' / 'probe.json', b'{"rewritten": "by a run"}')
        mutable |= {(root / 'tasks' / 'probe.json').stat().st_ino,
                    (root / 'j01-lab-memory' / 'activity.sqlite3').stat().st_ino}
    read = os.read

    def guard(fd, size):
        assert os.fstat(fd).st_ino not in mutable, 'mutable content read after DONE D3'
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guard)
    result = tpo.observe(config)
    child, _ = homes(result, op)
    if variant == 'done_d3_layout_missing':
        assert child.classification == NE and 'OWN_HOME_INCOMPLETE' in child.classification_codes
        assert 'D3_LAYOUT_INCOMPLETE' in child.classification_codes
        not_own(result, op)
        return
    assert (child.classification, child.counted, child.layout) == ('OWN_OPERATION', 'EXCLUDED_OWN', 'OBSERVED')
    assert {x.relative_path.rsplit('/', 1)[-1] for x in child.files} == {'record.json', 'spec.json', 'birth_qualification.json'}
    assert result.status == 'OBSERVED' and result.operations[0].own_home == 'PASS'
    tpo.permanent(result)


OWN_03 = ['spec_only', 'spec_and_record', 'without_usage', 'without_layout', 'short_write_record',
          'short_write_usage']


@pytest.mark.parametrize('variant', OWN_03, ids=OWN_03)
@case('3C:OWN-03')
def test_own_03_partial_open_d3_home_is_ne_incomplete_never_unauthenticated(full_profile_machine, variant):
    config, op = candidate(full_profile_machine)
    plan = op['birth_plan']
    record = p.storage_bytes(plan['record'])
    files = {
        'spec_only': {'record.json': None, 'birth_qualification.json': None, 'usage': False, 'layout': False},
        'spec_and_record': {'birth_qualification.json': None, 'usage': False, 'layout': False},
        'without_usage': {'usage': False, 'layout': False},
        'without_layout': {'layout': False},
        'short_write_record': {'record.json': record[:len(record) // 2], 'birth_qualification.json': None,
                               'usage': False, 'layout': False},
        'short_write_usage': {'usage': p.storage_bytes({'runs': 0})[:5], 'layout': False},
    }[variant]
    proofs.home(config.observer, op, **files)
    result = tpo.observe(config)
    child, _ = homes(result, op)
    assert (child.classification, child.counted) == (NE, 'NE')
    assert 'OWN_HOME_INCOMPLETE' in child.classification_codes and 'OWN_HOME_INCOMPLETE' in result.blockers
    assert 'HOME_CONFLICT' not in child.classification_codes
    assert 'POPULATION_UNAUTHENTICATED' not in child.classification_codes
    # Present files equal: no divergence. A divergent short write keeps its 3A refusal (section 6).
    assert ('STORED_FILE_DIVERGENT' in child.classification_codes) is variant.startswith('short_write')
    not_own(result, op)


OWN_04 = ['spec_divergent', 'record_divergent', 'qualification_divergent', 'previous_attempt_plan']


@pytest.mark.parametrize('variant', OWN_04, ids=OWN_04)
@case('3C:OWN-04')
def test_own_04_right_id_with_divergent_identity_or_plan_is_conflict_never_own(full_profile_machine, variant):
    config, op = full_profile_machine
    if variant == 'previous_attempt_plan':
        op['attempt'] = 2
    config, op = candidate(full_profile_machine)
    plan = op['birth_plan']
    if variant == 'previous_attempt_plan':
        # Attempt 1 (REFUSED) froze another valid plan; its record is on disk.
        old = copy.deepcopy(op)
        old['attempt'] = 1
        old['budget']['cpu_seconds'] -= 1
        old['birth_plan']['record']['budget'] = dict(old['budget'])
        base.write(config.observer.lab_root / 'admission-ops' / (op['child_agent_id'] + '.log'),
                   raw(*base.prefix(op=old), base.entry('REFUSED', op=old), *base.prefix(2, op=op),
                       *proofs.begin_d3(op)))
        files = {'record.json': p.storage_bytes(old['birth_plan']['record'])}
    else:
        name, key = {'spec_divergent': ('spec.json', 'child_spec'), 'record_divergent': ('record.json', 'record'),
                     'qualification_divergent': ('birth_qualification.json', 'qualification')}[variant]
        value = dict(plan[key])
        value['fixture_divergence'] = 1  # same ID, other valid JSON content, not a prefix
        files = {name: p.storage_bytes(value)}
    proofs.home(config.observer, op, **files)
    result = tpo.observe(config)
    child, _ = homes(result, op)
    assert (child.classification, child.counted) == ('UNAUTHENTICATED', 'BLOCKING')
    assert 'HOME_CONFLICT' in child.classification_codes and 'STORED_FILE_DIVERGENT' in child.classification_codes
    assert result.population == 'FAIL' and 'HOME_CONFLICT' in result.blockers
    not_own(result, op)


OWN_05 = ['home_before_begin_d3', 'begin_d3_cancelled']


@pytest.mark.parametrize('variant', OWN_05, ids=OWN_05)
@case('3C:OWN-05')
def test_own_05_home_without_effective_begin_d3_has_no_established_origin(full_profile_machine, variant):
    events = (lambda op: ()) if variant == 'home_before_begin_d3' else (
        lambda op: (*proofs.begin_d3(op), base.entry('BEGIN_CANCELLED', 'D3', op=op, code='LAB_STOPPED')))
    config, op = candidate(full_profile_machine, events=events)
    proofs.home(config.observer, op)
    result = tpo.observe(config)
    child, _ = homes(result, op)
    assert (child.classification, child.counted) == ('UNAUTHENTICATED', 'BLOCKING')
    assert 'OPERATION_STATE_INCONSISTENT' in child.classification_codes
    assert 'OPERATION_STATE_INCONSISTENT' in result.blockers
    not_own(result, op)
