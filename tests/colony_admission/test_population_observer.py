"""3C-5 public PopulationObserver: fault scopes, actions, aggregation; LAB_TEST only."""

import dataclasses
from types import SimpleNamespace

import pytest

from colony_admission import _population_acquisition as owner
from colony_admission import formats as f
from colony_admission import physical_evidence as p
from colony_admission import population_observer as po
from tests.colony_admission import test_external_evidence as fx
from tests.colony_admission import test_population_counts as counts
from tests.colony_admission import test_population_proof as proofs
from tests.colony_admission.test_oplog import COLD

machine = proofs.machine
family = proofs.family
signed_machine = proofs.signed_machine
full_profile_machine = proofs.full_profile_machine
base, ao, raw = proofs.base, proofs.ao, proofs.raw


def observe(config):
    return po.PopulationObserver(po.PopulationConfig(config)).scan_population()


def permanent(result):
    assert result.accepted is False and result.schema == 'colony-admission.population-evidence/0'
    assert result.completeness == result.authorization == result.durability == result.rotation == p.NE
    assert result.recovery == result.source_revision_provenance == result.operational_completeness == p.NE
    for home in result.homes:
        assert home.accepted is False and home.authorization == home.filiation == p.NE
    for op in result.operations:
        assert op.accepted is False and op.authorization == p.NE
        assert op.ceilings.authorization == op.ceilings.concurrency_enforcement == p.NE
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = 'OBSERVED'


def exact_own(fixture, *, events=None, prepare=None, tweak=None):
    config, op = fixture
    records = [counts.founder_record(config.observer, op)]
    if prepare is not None:
        records += prepare(config.observer, op)
    counts.exact_plan(op, records)
    if tweak is not None:
        tweak(op['birth_plan'])
    proofs.own_machine(fixture, events=None if events is None else events(op))
    return config, op


def test_complete_own_snapshot_is_observed_without_authority(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    result = observe(config)
    assert result.status == 'OBSERVED' and result.blockers == (), result.blockers
    assert result.inventory == result.population == result.snapshot_completeness == 'PASS'
    assert result.global_identity_exclusions == 'PASS'
    assert 'NO_RUNTIME_OBSERVATION' in result.warnings and 'NOT_APPLICABLE_FOUNDER' in result.warnings
    current, = result.operations
    assert current.scope == 'CURRENT_OPEN' and current.own_home == 'PASS' and current.plan_match == 'PASS'
    assert current.counts.population == 1 and current.ceilings.aggregate == 'PASS'
    assert current.needs and {x.role for x in current.needs} <= {'DECISION', 'POPULATION'}
    assert {(x.kind, x.agent_id, x.record_sha256, x.role) for x in current.items} == {
        (x['kind'], x['subject']['agent_id'], x['record_sha256'], x['role']) for x in op['items']}
    assert all(type(x.namespaces) is tuple and type(x.envelope_sha256s) is tuple
               for x in current.needs + current.items)
    child = next(x for x in result.homes if x.agent_id == op['child_agent_id'])
    assert child.classification == 'OWN_OPERATION' and child.generation == 1
    assert all(x.presence == 'PRESENT' and x.raw_sha256 for x in child.files)
    permanent(result)
    assert not hasattr(result, 'can_parent') and not hasattr(result, 'admitted')


def test_no_current_open_operation_is_non_blocking_warning(full_profile_machine):
    config, op = full_profile_machine
    proofs.log(config.observer, op, base.entry('COMMITTED', op=op), level=3)
    proofs.spend(config.observer, op, proofs.admission_envelope(config.observer, op))
    proofs.home(config.observer, op, usage=b'{"runs": 2}')
    result = observe(config)
    assert result.status == 'OBSERVED', result.blockers
    assert 'NO_CURRENT_OPEN_OPERATION' in result.warnings
    assert 'HISTORICAL_POPULATION_NOT_EVALUATED' in result.warnings
    assert {x.classification for x in result.homes} == {'AUTHENTICATED', 'AWAITING_INDIVIDUAL_ATTESTATION'}
    assert result.operations[0].counts.complete == p.NE and result.operations[0].plan_match == p.NE
    permanent(result)


def test_unsupported_profile_blocks(signed_machine):
    config, op, envs = signed_machine
    proofs.log(config.observer, op, *proofs.begin_d3(op), level=2)
    proofs.spend(config.observer, op, f.canonical(envs[op['child_agent_id'] + '/admission']))
    proofs.home(config.observer, op)
    result = observe(config)
    assert result.status == 'BLOCKED' and 'SCIENTIFIC_PROFILE_UNSUPPORTED' in result.blockers
    assert result.population == p.NE and result.snapshot_completeness != 'PASS'
    assert result.global_identity_exclusions == p.NE  # unknown prerequisites never give PASS
    permanent(result)


@pytest.mark.parametrize('resource,scope', [(x, 'GLOBAL') for x in (
    'LEDGER', 'LEDGER_DIRECTORY', 'INDIVIDUALS_DIRECTORY', 'LAB_DIRECTORY', 'OPERATION_LOG_DIRECTORY',
    'ADMISSION_DIRECTORY', 'ENVELOPE_DIRECTORY')])
def test_global_faults_always_block(full_profile_machine, resource, scope):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    kind = 'FILE' if resource == 'LEDGER' else 'DIRECTORY'
    fault = fx.fault(lab_id=config.observer.lab_id, child_agent_id='e' * 64, operation_sha256='f' * 64,
                     data={'origin': 'CONTROLLER', 'failure': 'FSYNC',
                           'target': {'resource': resource, 'object_kind': kind, 'relative_path': ''}})
    base.write(config.observer.fault_file, raw(fault))
    result = observe(config)
    assert result.status == 'BLOCKED' and 'STICKY_FAULT' in result.blockers
    binding, = result.fault_bindings
    assert binding.scope == scope and binding.blocking and binding.cleared == p.NE


def test_trust_install_fault_blocks(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    fault = fx.fault(lab_id=config.observer.lab_id, scope='LAB', child_agent_id=None, operation_sha256=None,
                     attempt=None, phase='TRUST_INSTALL', step=None,
                     data={'origin': 'CONTROLLER', 'failure': 'WRITE',
                           'target': {'resource': 'TRUST_POLICY', 'object_kind': 'FILE', 'relative_path': ''}})
    base.write(config.observer.fault_file, raw(fault))
    result = observe(config)
    assert result.status == 'BLOCKED' and result.fault_bindings[0].scope == 'GLOBAL'


def test_historical_fault_of_linked_termination_is_not_a_global_veto(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    other, digest = 'e' * 64, 'f' * 64
    fault, terminal = proofs.logtests.external(config.observer, child=other, op=digest, version=1, count=0)
    base.write(config.observer.fault_file, raw(fault, terminal))
    result = observe(config)
    assert result.external_terminations[0].terminal_linkage == 'PASS'
    binding, = result.fault_bindings
    assert binding.scope == 'OPERATION_HISTORICAL' and not binding.blocking
    assert result.status == 'OBSERVED', result.blockers
    assert result.log_coverage == p.NE  # its log is unread, never a false exhaustive PREPARED


def test_current_operation_fault_blocks_that_operation(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    fault = fx.fault(lab_id=config.observer.lab_id, child_agent_id=op['child_agent_id'],
                     operation_sha256=f.digest(op), data={'origin': 'CONTROLLER', 'failure': 'WRITE',
                     'target': {'resource': 'HOME_ENTRY', 'object_kind': 'FILE',
                                'relative_path': op['child_agent_id'] + '/spec.json'}})
    base.write(config.observer.fault_file, raw(fault))
    result = observe(config)
    assert result.fault_bindings[0].scope == 'OPERATION_CURRENT' and result.status == 'BLOCKED'


@pytest.mark.parametrize('path', ['unknown.json', 'tasks/../x.json', 'tasks/UPPER.json', 'tasks/Upper.json'])
def test_target_outside_closed_mapping_is_unbound(full_profile_machine, path):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    fault = fx.fault(lab_id=config.observer.lab_id, child_agent_id=op['child_agent_id'],
                     operation_sha256=f.digest(op), data={'origin': 'CONTROLLER', 'failure': 'WRITE',
                     'target': {'resource': 'HOME_ENTRY', 'object_kind': 'FILE',
                                'relative_path': op['child_agent_id'] + '/' + path}})
    base.write(config.observer.fault_file, raw(fault))
    result = observe(config)
    if result.fault_bindings:
        assert result.fault_bindings[0].scope == 'UNBOUND'
        assert 'TARGET_BINDING_UNAVAILABLE' in result.blockers
    else:  # lexically refused by the existing strict fault parser: whole scan refused
        assert result.status == 'BLOCKED' and not result.homes
    assert result.status == 'BLOCKED'


def quarantine_events(op, *, done=True, rebegin=True, cancel=False):
    events = [*proofs.begin_d3(op), base.entry('INTERRUPTED_RECOVERED', 'D3', op=op, boot=COLD,
              data={'result': 'PARTIAL'}), base.entry('QUARANTINE_BEGIN', 'D3', op=op)]
    if done:
        events.append(base.entry('QUARANTINE_DONE', 'D3', op=op))
        if rebegin:
            events.append(base.entry('BEGIN', 'D3', op=op, boot=COLD))
            if cancel:
                events.append(base.entry('BEGIN_CANCELLED', 'D3', op=op, boot=COLD))
    return tuple(events)


def quarantined(config, op, record=None):
    path = 'admission-quarantine/' + f.digest(op) + '/1/record.json'
    value = p.storage_bytes(op['birth_plan']['record']) if record is None else record
    return proofs.acquisition.quarantine_store(config, path, value)


def test_quarantine_then_new_effective_d3_incarnation_is_observed(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=quarantine_events)
    quarantined(config.observer, op)
    proofs.home(config.observer, op)
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'QUARANTINE' and action.action_location == action.identity_binding == 'PASS'
    assert action.quarantine_journal_semantics == action.durability == action.permission == p.NE
    assert next(x for x in result.homes if x.agent_id == op['child_agent_id']).classification == 'OWN_OPERATION'
    assert result.status == 'OBSERVED', result.blockers


def test_new_incarnation_before_first_write_is_location_pass(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=quarantine_events)
    quarantined(config.observer, op)
    result = observe(config)
    action, = result.action_facts
    assert action.action_location == 'PASS' and not action.blocking


@pytest.mark.parametrize('case', ['no_rebegin', 'cancelled'])
def test_source_still_present_without_incarnation_is_divergent(full_profile_machine, case):
    events = lambda op: quarantine_events(op, rebegin=case == 'cancelled', cancel=True)  # noqa: E731
    config, op = exact_own(full_profile_machine, events=events)
    quarantined(config.observer, op)
    proofs.home(config.observer, op)
    result = observe(config)
    action, = result.action_facts
    assert action.action_location == 'FAIL' and 'ACTION_LOCATION_DIVERGENT' in result.blockers
    assert result.status == 'BLOCKED'


def test_lying_done_without_destination_is_divergent(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=lambda op: quarantine_events(op, rebegin=False))
    result = observe(config)
    action, = result.action_facts
    assert action.action_location == 'FAIL' and action.blocking


def test_begin_without_done_is_located_but_incomplete(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=lambda op: quarantine_events(op, done=False))
    quarantined(config.observer, op)
    result = observe(config)
    action, = result.action_facts
    assert action.action_location == 'PASS' and action.action_completion == p.NE and action.blocking
    assert result.status == 'BLOCKED'


def test_quarantine_identity_prefix_is_not_tolerated(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=quarantine_events)
    record = p.storage_bytes(op['birth_plan']['record'])
    quarantined(config.observer, op, record[:10])
    result = observe(config)
    action, = result.action_facts
    assert action.identity_binding == 'FAIL' and action.blocking


def test_orphan_destination_blocks(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.acquisition.quarantine_store(config.observer, 'admission-quarantine/' + 'f' * 64 + '/terminal/spec.json',
                                        b'{}')
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'UNKNOWN' and 'ACTION_EVIDENCE_NOT_EVALUATED' in result.blockers


def test_external_set_aside_without_birthplan_keeps_identity_ne(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    other, digest = 'e' * 64, 'f' * 64
    fault, terminal = proofs.logtests.external(config.observer, child=other, op=digest, version=1, count=0)
    done = fx.aside(terminal, done=True, lab_id=config.observer.lab_id, child_agent_id=other,
                    operation_sha256=digest)
    begin = fx.aside(terminal, lab_id=config.observer.lab_id, child_agent_id=other, operation_sha256=digest)
    base.write(config.observer.fault_file, raw(fault, terminal, begin, done))
    proofs.acquisition.quarantine_store(config.observer, 'admission-quarantine/' + digest + '/terminal/spec.json',
                                        b'{"partial"')
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'SET_ASIDE_EXTERNAL' and action.action_location == 'PASS'
    assert action.identity_binding == p.NE and action.blocking and result.status == 'BLOCKED'


def test_invalid_config_and_acquisition_failure_have_no_payload(full_profile_machine):
    result = po.PopulationObserver(full_profile_machine[0]).scan_population()
    assert result.status == 'BLOCKED' and result.blockers == ('CONFIG_INVALID',) and not result.homes
    config, op = full_profile_machine
    base.write(config.observer.lab_root / 'individuals' / op['parent_agent_id'] / 'record.json', b'x' * 65537)
    result = observe(config)
    assert result.status == 'BLOCKED' and result.blockers == ('SOURCE_LIMIT',)
    assert result.limits.reached == ('record_bytes',) and not result.homes and result.ledger_bytes is None
    permanent(result)


def test_public_export_is_the_only_new_api():
    import colony_admission
    assert not hasattr(colony_admission, 'PopulationObserver')  # module-level, not package re-export
    assert set(dir(po)) >= {'PopulationObserver', 'PopulationConfig', 'PopulationEvidence'}
    assert owner.acquire.__module__.endswith('_population_acquisition')


def test_self_issued_individual_makes_global_exclusions_fail(full_profile_machine):
    def self_issued(observer, op):
        spec = counts.b.spec(name='self_founder')
        record = counts.lineage.make_founder(spec, lab_permissions=['DIAGNOSTIC_PRODUCE'],
                                             budget=dict(counts.b.BUDGET))
        agent = record['agent_id']
        env = counts.pure.signed(record, counts.c.IND, 'operator-' + agent[:16], 'individual', 'operator-1')
        ao.store(observer, 'individuals/' + agent + '/record.json', f.canonical(record))
        ao.store(observer, 'individuals/' + agent + '/spec.json', f.canonical(spec))
        ao.store(observer, 'admission-envelopes/' + agent + '/individual-' + f.digest(record) + '.envelope.json',
                 f.canonical(env))
        return [record]
    config, op = exact_own(full_profile_machine, prepare=self_issued)
    proofs.home(config.observer, op)
    result = observe(config)
    assert result.global_identity_exclusions == 'FAIL' and result.snapshot_completeness == 'FAIL'
    assert result.status == 'BLOCKED' and 'SELF_QUALIFICATION_DENIED' in result.blockers


def test_failed_branch_attestations_block_with_decision_codes(full_profile_machine, monkeypatch):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    prove = owner.pp.prove

    def failed_branch(*args, **kwargs):
        result = prove(*args, **kwargs)
        ops = tuple(dataclasses.replace(x, decision=dataclasses.replace(
            x.decision, branch_attestations='FAIL', blockers=('BRANCH_FAIL_PROBE',))) for x in result.operations)
        return dataclasses.replace(result, operations=ops)
    monkeypatch.setattr(owner.pp, 'prove', failed_branch)
    result = observe(config)
    assert result.status == 'BLOCKED' and 'BRANCH_FAIL_PROBE' in result.blockers


def test_owner_wires_every_home_id_and_candidate_envelopes_into_the_contradiction(full_profile_machine,
                                                                                  monkeypatch):
    seen = []
    contradiction = owner.pp._own_contradiction

    def spy(decision, op, envelopes=None, excluded=frozenset()):
        seen.append((envelopes, excluded))
        return contradiction(decision, op, envelopes, excluded)
    monkeypatch.setattr(owner.pp, '_own_contradiction', spy)
    config, op = exact_own(full_profile_machine, prepare=lambda observer, op: [
        counts.second_founder(observer)[0]])
    proofs.home(config.observer, op)
    result = observe(config)  # the unfrozen sibling blocks POPULATION, not this wiring
    (envelopes, excluded), = seen
    assert envelopes and {x.agent_id for x in result.homes} <= excluded
    assert result.status == 'BLOCKED'
    current, = result.operations  # the extended needs name the unfrozen sibling as POPULATION
    sibling = next(x for x in result.homes if x.agent_id not in (op['parent_agent_id'], op['child_agent_id']))
    assert any(x.role == 'POPULATION' and x.kind == counts.c.IND and x.agent_id == sibling.agent_id
               for x in current.needs)
    assert op['child_agent_id'] in excluded


def fault_on(config, op, resource, path, *, child=None, failure='WRITE', kind='FILE'):
    return fx.fault(lab_id=config.observer.lab_id, child_agent_id=child or op['child_agent_id'],
                    operation_sha256=f.digest(op) if child is None else 'f' * 64,
                    data={'origin': 'CONTROLLER', 'failure': failure,
                          'target': {'resource': resource, 'object_kind': kind, 'relative_path': path}})


def test_plan_divergence_blocks_the_observation(full_profile_machine):
    config, op = exact_own(full_profile_machine, tweak=lambda plan: plan.update(children_count=1))
    proofs.home(config.observer, op)
    result = observe(config)
    current, = result.operations
    assert current.plan_match == 'FAIL' and 'POPULATION_CHANGED' in result.blockers
    assert result.status == 'BLOCKED'


@pytest.mark.parametrize('part', ['ceilings', 'counts'])
def test_ceiling_fail_or_counts_ne_blocks_the_observation(full_profile_machine, monkeypatch, part):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    current = owner.pp.pk.current

    def degraded(*args, **kwargs):
        result = current(*args, **kwargs)
        if part == 'ceilings':
            return dataclasses.replace(result, ceilings=dataclasses.replace(result.ceilings, aggregate='FAIL'))
        return dataclasses.replace(result, counts=counts.pk.Counts(complete=p.NE))
    monkeypatch.setattr(owner.pp.pk, 'current', degraded)
    result = observe(config)
    assert result.status == 'BLOCKED' and result.blockers


def test_fault_of_an_operation_unknown_to_u_is_unbound_and_blocks(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    base.write(config.observer.fault_file, raw(fault_on(config, op, 'HOME_ENTRY', 'e' * 64 + '/spec.json',
                                                         child='e' * 64)))
    result = observe(config)
    binding, = result.fault_bindings
    assert binding.scope == 'UNBOUND' and binding.blocking
    assert result.status == 'BLOCKED' and 'TARGET_BINDING_UNAVAILABLE' in result.blockers


def test_quarantine_root_fault_is_global(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    base.write(config.observer.fault_file, raw(fault_on(config, op, 'QUARANTINE_DIRECTORY', '',
                                                         failure='FSYNC', kind='DIRECTORY')))
    result = observe(config)
    assert result.fault_bindings[0].scope == 'GLOBAL' and result.status == 'BLOCKED'


def test_envelope_entry_outside_mapping_is_unbound(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    base.write(config.observer.fault_file, raw(fault_on(config, op, 'ENVELOPE_ENTRY',
                                                         op['child_agent_id'] + '/unknown.json')))
    result = observe(config)
    assert result.fault_bindings[0].scope == 'UNBOUND' and result.status == 'BLOCKED'


def test_home_directory_fsync_fault_restricts_actions(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    base.write(config.observer.fault_file, raw(fault_on(config, op, 'HOME_DIRECTORY', op['child_agent_id'],
                                                         failure='FSYNC', kind='DIRECTORY')))
    result = observe(config)
    binding, = result.fault_bindings
    assert binding.scope == 'OPERATION_CURRENT' and 'ACTION_RESTRICTED' in binding.codes
    assert result.status == 'BLOCKED'


def test_fault_of_a_closed_readable_operation_is_historical(full_profile_machine):
    config, op = full_profile_machine
    proofs.log(config.observer, op, base.entry('COMMITTED', op=op), level=3)
    proofs.spend(config.observer, op, proofs.admission_envelope(config.observer, op))
    proofs.home(config.observer, op, usage=b'{"runs": 2}')
    base.write(config.observer.fault_file, raw(fault_on(config, op, 'HOME_ENTRY',
                                                         op['child_agent_id'] + '/spec.json')))
    result = observe(config)
    binding, = result.fault_bindings
    assert binding.scope == 'OPERATION_HISTORICAL' and not binding.blocking
    assert result.status == 'OBSERVED', result.blockers


def test_observed_needs_every_required_comparison_evaluated(full_profile_machine, monkeypatch):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    monkeypatch.setattr(po, '_global_exclusions', lambda *args: p.NE)
    result = observe(config)
    assert result.snapshot_completeness == p.NE
    assert result.status == 'BLOCKED' and result.blockers == ('CLASSIFICATION_NOT_EVALUATED',)


@pytest.mark.parametrize('case', ['other_child', 'other_attempt'])
def test_fault_naming_a_closed_operation_with_another_child_or_attempt_is_unbound(full_profile_machine, case):
    config, op = full_profile_machine
    proofs.log(config.observer, op, base.entry('COMMITTED', op=op), level=3)
    proofs.spend(config.observer, op, proofs.admission_envelope(config.observer, op))
    proofs.home(config.observer, op, usage=b'{"runs": 2}')
    child = 'e' * 64 if case == 'other_child' else op['child_agent_id']
    fault = fx.fault(lab_id=config.observer.lab_id, child_agent_id=child, operation_sha256=f.digest(op),
                     attempt=7 if case == 'other_attempt' else op['attempt'],
                     data={'origin': 'CONTROLLER', 'failure': 'WRITE',
                           'target': {'resource': 'HOME_ENTRY', 'object_kind': 'FILE',
                                      'relative_path': child + '/spec.json'}})
    base.write(config.observer.fault_file, raw(fault))
    result = observe(config)
    binding, = result.fault_bindings
    assert binding.scope == 'UNBOUND' and binding.blocking
    assert result.status == 'BLOCKED' and 'TARGET_BINDING_UNAVAILABLE' in result.blockers


def test_home_role_is_exposed_only_validated_never_as_a_raw_value(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    agent = 'a' * 64
    ao.store(config.observer, 'individuals/' + agent + '/record.json',
             f.canonical({'role': ['x'], 'agent_spec_id': ['y'], 'lineage': {'founder_agent_id': agent}}))
    ao.store(config.observer, 'individuals/' + agent + '/spec.json', f.canonical({}))
    result = observe(config)
    bad = next(x for x in result.homes if x.agent_id == agent)
    assert bad.role is bad.spec_id is None
    assert bad.parent_agent_id is bad.founder_agent_id is bad.generation is None
    assert result.status == 'BLOCKED'
    good = next(x for x in result.homes if x.agent_id == op['parent_agent_id'])
    assert good.role == 'FOUNDER'


def test_unproven_external_termination_is_unresolved_and_blocks(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    fault, terminal = proofs.logtests.external(config.observer, child='e' * 64, op='f' * 64, version=0, count=0)
    base.write(config.observer.fault_file, raw(fault, terminal))
    result = observe(config)
    assert result.external_terminations[0].terminal_linkage == p.NE
    binding, = result.fault_bindings
    assert binding.scope == 'OPERATION_UNRESOLVED' and binding.blocking
    assert 'EXTERNAL_TERMINATION_UNPROVEN' in binding.codes and 'EXTERNAL_TERMINATION_UNPROVEN' in result.blockers
    assert result.status == 'BLOCKED'


def test_divergent_external_finding_is_unresolved_and_blocks(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    fault, terminal = proofs.logtests.external(config.observer, child='e' * 64, op='f' * 64, version=1, count=1)
    base.write(config.observer.fault_file, raw(fault, terminal))
    result = observe(config)
    assert result.external_terminations[0].terminal_linkage == 'FAIL'
    binding, = result.fault_bindings
    assert binding.scope == 'OPERATION_UNRESOLVED' and binding.blocking
    assert 'EXTERNAL_TERMINATION_DIVERGENT' in result.blockers and result.status == 'BLOCKED'


def set_aside_events(op, *, done=True):
    events = [*proofs.begin_d3(op), base.entry('TERMINATED', op=op, code='OPERATOR_TERMINATED'),
              base.entry('FAILED_CONSUMED', op=op, code='OPERATOR_TERMINATED'),
              base.entry('SET_ASIDE_BEGIN', 'D3', op=op)]
    if done:
        events.append(base.entry('SET_ASIDE_DONE', 'D3', op=op))
    return tuple(events)


def set_aside(config, op, record=None):
    path = 'admission-quarantine/' + f.digest(op) + '/terminal/record.json'
    value = p.storage_bytes(op['birth_plan']['record']) if record is None else record
    return proofs.acquisition.quarantine_store(config, path, value)


@pytest.mark.parametrize('identity', ['equal', 'prefix'])
def test_log_set_aside_done_accepts_equal_or_prefix_identity(full_profile_machine, identity):
    config, op = exact_own(full_profile_machine, events=set_aside_events)
    record = p.storage_bytes(op['birth_plan']['record'])
    set_aside(config.observer, op, record if identity == 'equal' else record[:10])
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'SET_ASIDE' and action.destination == 'terminal' and action.claim == 'DONE'
    assert action.action_location == action.identity_binding == action.action_completion == 'PASS'
    assert not action.blocking and action.durability == action.permission == p.NE


def test_log_set_aside_done_with_source_still_present_is_divergent(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=set_aside_events)
    set_aside(config.observer, op)
    proofs.home(config.observer, op)  # no incarnation exception for a set-aside
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'SET_ASIDE' and action.action_location == 'FAIL' and action.blocking
    assert 'ACTION_LOCATION_DIVERGENT' in result.blockers and result.status == 'BLOCKED'


def test_log_set_aside_identity_divergence_fails(full_profile_machine):
    config, op = exact_own(full_profile_machine, events=set_aside_events)
    set_aside(config.observer, op, b'{"other": 1}')
    action, = observe(config).action_facts
    assert action.identity_binding == 'FAIL' and action.blocking


@pytest.mark.parametrize('locations', [0, 2])
def test_begin_without_done_needs_exactly_one_location(full_profile_machine, locations):
    config, op = exact_own(full_profile_machine, events=lambda op: quarantine_events(op, done=False))
    if locations == 2:
        quarantined(config.observer, op)
        proofs.home(config.observer, op)
    result = observe(config)
    action, = result.action_facts
    assert action.action_location == 'FAIL' and action.action_completion == p.NE and action.blocking
    assert 'ACTION_LOCATION_DIVERGENT' in result.blockers and result.status == 'BLOCKED'


def test_current_decision_exclusions_not_pass_keep_global_exclusions_ne(full_profile_machine, monkeypatch):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    prove = owner.pp.prove

    def unknown(*args, **kwargs):
        result = prove(*args, **kwargs)
        ops = tuple(dataclasses.replace(x, decision=dataclasses.replace(
            x.decision, known_identity_exclusions=p.NE)) for x in result.operations)
        return dataclasses.replace(result, operations=ops)
    monkeypatch.setattr(owner.pp, 'prove', unknown)
    result = observe(config)
    assert result.global_identity_exclusions == result.snapshot_completeness == p.NE
    assert result.status == 'BLOCKED' and result.blockers == ('CLASSIFICATION_NOT_EVALUATED',)


@pytest.mark.parametrize('resource,failure,restricted', [('HOME_DIRECTORY', 'FSYNC', True),
                                                         ('HOME_DIRECTORY', 'RENAME', True),
                                                         ('HOME_DIRECTORY', 'WRITE', False),
                                                         ('HOME_ENTRY', 'FSYNC', False)])
def test_action_restriction_only_for_home_directory_fsync_or_rename(full_profile_machine, resource, failure,
                                                                    restricted):
    config, op = exact_own(full_profile_machine)
    proofs.home(config.observer, op)
    path = op['child_agent_id'] + ('' if resource == 'HOME_DIRECTORY' else '/spec.json')
    kind = 'DIRECTORY' if resource == 'HOME_DIRECTORY' else 'FILE'
    base.write(config.observer.fault_file, raw(fault_on(config, op, resource, path, failure=failure, kind=kind)))
    binding, = observe(config).fault_bindings
    assert ('ACTION_RESTRICTED' in binding.codes) is restricted and binding.blocking


def test_external_pending_set_aside_begin_is_located_but_incomplete(full_profile_machine):
    config, op = exact_own(full_profile_machine)
    other, digest = 'e' * 64, 'f' * 64
    fault, terminal = proofs.logtests.external(config.observer, child=other, op=digest, version=1, count=0)
    begin = fx.aside(terminal, lab_id=config.observer.lab_id, child_agent_id=other, operation_sha256=digest)
    base.write(config.observer.fault_file, raw(fault, terminal, begin))
    proofs.acquisition.quarantine_store(config.observer, 'admission-quarantine/' + digest + '/terminal/spec.json',
                                        b'{"p"')
    result = observe(config)
    action, = result.action_facts
    assert action.action == 'SET_ASIDE_EXTERNAL' and action.claim == 'BEGIN'
    assert action.action_completion == p.NE and action.blocking and result.status == 'BLOCKED'


def home_state(structure='PASS', counted='INCLUDED', exclusions='PASS', individual='PASS'):
    return SimpleNamespace(structure=structure, counted=counted, identity_exclusions=exclusions,
                           individual_proof=individual)


def current_state(exclusions='PASS'):
    return SimpleNamespace(decision=SimpleNamespace(known_identity_exclusions=exclusions))


@pytest.mark.parametrize('homes,current,expected', [
    ([home_state()], [current_state()], 'PASS'),
    ([home_state(structure='FAIL')], [current_state()], p.NE),
    ([home_state(counted=p.NE)], [current_state()], p.NE),
    ([home_state(exclusions=p.NE)], [current_state()], p.NE),  # a present individual left unchecked
    ([home_state(exclusions=p.NE, individual=p.NE)], [current_state()], 'PASS'),  # absent: no issuer
    ([home_state()], [current_state(p.NE)], p.NE),
    ([home_state()], [current_state('FAIL')], 'FAIL'),
    ([home_state(exclusions='FAIL', structure='FAIL')], [current_state(p.NE)], 'FAIL'),  # FAIL dominates
])
def test_global_identity_exclusions_never_pass_on_unknown_prerequisites(homes, current, expected):
    assert po._global_exclusions(homes, current) == expected


def test_extended_needs_items_and_home_digests_are_exact(full_profile_machine, monkeypatch):
    config, op = full_profile_machine
    record, env = counts.second_founder(config.observer)
    op['items'].append(counts.pure.item(counts.c.IND, record, 'POPULATION', env=f.digest(env)))
    counts.pure.sort_items(op)
    seen = []
    prove = owner.pp.prove

    def spy(*args, **kwargs):
        seen.append(prove(*args, **kwargs))
        return seen[-1]
    monkeypatch.setattr(owner.pp, 'prove', spy)
    config, op = exact_own(full_profile_machine, prepare=lambda *_: [record])
    proofs.home(config.observer, op)
    result = observe(config)
    assert result.status == 'OBSERVED', result.blockers
    current, = result.operations
    decision = seen[-1].operations[0].decision
    key = counts.c.key(counts.c.IND, record)
    expected = {(n.key.kind, n.key.agent_id, n.key.agent_spec_id, n.key.record_sha256, 'DECISION', n.namespaces,
                 n.envelope_sha256s) for n in decision.needs}
    expected.add((key.kind, key.agent_id, key.agent_spec_id, key.record_sha256, 'POPULATION',
                  (record['agent_id'] + '/individual',), (f.digest(env),)))
    actual = [(x.kind, x.agent_id, x.agent_spec_id, x.record_sha256, x.role, x.namespaces, x.envelope_sha256s)
              for x in current.needs]
    assert set(actual) == expected and len(actual) == len(expected)
    assert all(x.namespaces and x.envelope_sha256s for x in current.needs)
    assert [x.role for x in current.needs if x.agent_id == record['agent_id']] == ['POPULATION']
    assert {x.agent_id for x in current.needs if x.role == 'POPULATION'} == {record['agent_id']}  # no branch/OWN
    keys = [counts.c.Key(x.kind, x.agent_id, x.agent_spec_id, x.record_sha256) for x in current.needs]
    assert keys == sorted(keys)
    assert [(x.kind, x.agent_id, x.agent_spec_id, x.record_sha256, x.role, x.envelope_sha256s)
            for x in current.items] == [
        (x['kind'], x['subject']['agent_id'], x['subject']['agent_spec_id'], x['record_sha256'], x['role'],
         (x['envelope_sha256'],)) for x in op['items']]
    with pytest.raises(dataclasses.FrozenInstanceError):
        current.items[0].role = 'POPULATION'
    founder = next(x for x in result.homes if x.agent_id == op['parent_agent_id'])
    assert founder.record_sha256 == f.digest(counts.founder_record(config.observer, op))
    assert founder.spec_id == counts.founder_record(config.observer, op)['agent_spec_id']
