"""3C-3 home classification and exact OWN in the one owner, temporary LAB_TEST only."""

import ast
import dataclasses
import inspect
import os

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _population_acquisition as owner
from colony_admission import _population_proof as pp
from colony_admission import attestation_evidence as a
from colony_admission import formats as f
from colony_admission import physical_evidence as p
from tests.colony_admission import test_attestation_core as pure
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_population_acquisition as acquisition
from tests.colony_admission import test_population_log_acquisition as logtests
from tests.colony_admission.test_oplog import COLD, raw
from tests.colony_trust.keys import OPERATOR

machine = base.machine
family = ao.family
signed_machine = ao.signed_machine
full_profile_machine = ao.full_profile_machine


def log(config, op, *events, level=0):
    path = config.lab_root / 'admission-ops' / (op['child_agent_id'] + '.log')
    base.write(path, raw(*base.prefix(level, op=op), *events))


def begin_d3(op):
    return (base.entry('BEGIN', 'D3', op=op),)


def home(config, op, *, usage=True, layout=True, **overrides):
    """Write the exact D3 identity storage bytes and closed runtime layout."""
    child, plan = op['child_agent_id'], op['birth_plan']
    files = {'spec.json': p.storage_bytes(plan['child_spec']), 'record.json': p.storage_bytes(plan['record']),
             'birth_qualification.json': p.storage_bytes(plan['qualification'])}
    if usage:
        files['usage.json'] = p.storage_bytes({'runs': 0}) if usage is True else usage
    files.update(overrides)
    targets = {}
    for name, value in files.items():
        if value is not None:
            targets[name] = ao.store(config, 'individuals/' + child + '/' + name, value)
    if layout:
        root = config.lab_root / 'individuals' / child
        for name in ('tasks', 'results', 'j01-lab-memory'):
            (root / name).mkdir(mode=0o700, exist_ok=True)
        base.write(root / 'j01-lab-memory' / 'activity.sqlite3', b'opaque journal')
        base.write(root / 'tasks' / 'probe.json', b'opaque task')
    return targets


def spend(config, op, envelope):
    env = c.decode(envelope)
    base.spend(config, op, issuer_id=env['issuer_id'], envelope_id=env['envelope_id'],
               envelope_sha256=f.digest(env))


def admission_envelope(config, op):
    child = op['child_agent_id']
    digest = op['presented']['admission']['record_sha256']
    return (config.lab_root / 'admission-envelopes' / child / ('admission-' + digest + '.envelope.json')).read_bytes()


def scan(config):
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    return result


def proof(result, agent):
    return next(x for x in result.proofs.homes if x.agent_id == agent)


def operation(result, op):
    return next(x for x in result.proofs.operations if x.operation_sha256 == f.digest(op))


def own_machine(fixture, *, level=2, events=None, consumed=True):
    config, op = fixture
    log(config.observer, op, *(begin_d3(op) if events is None else events), level=level)
    if consumed:
        spend(config.observer, op, admission_envelope(config.observer, op))
    return config, op


def no_authority(result):
    proofs = result.proofs
    assert proofs.accepted is result.accepted is False
    assert proofs.population == proofs.snapshot_completeness == proofs.counts == p.NE
    assert proofs.ceilings == proofs.authorization == proofs.global_identity_exclusions == p.NE
    assert result.population == result.counts == result.ceilings == result.own_home == p.NE
    for x in proofs.operations:
        assert x.accepted is False
        assert x.authorization == x.current.authorization == p.NE
        assert x.current.accepted is x.current.counts.accepted is x.current.ceilings.accepted is False
        assert x.current.ceilings.concurrency_enforcement == x.current.ceilings.authorization == p.NE
    for x in proofs.homes:
        assert x.accepted is False and x.completeness == x.authorization == x.filiation == p.NE


def test_founder_classified_and_open_operation_without_home_is_not_own(full_profile_machine):
    config, op = full_profile_machine
    result = scan(config)
    founder = proof(result, op['parent_agent_id'])
    assert founder.classification == 'AUTHENTICATED' and founder.counted == 'INCLUDED'
    assert founder.birth_proof == p.NE and 'NOT_APPLICABLE_FOUNDER' in founder.codes
    current = operation(result, op)
    assert current.scope == 'CURRENT_OPEN' and current.decision.branch_attestations == 'PASS'
    assert current.own_home == p.NE and current.own_agent_id is None
    assert result.proofs.classification == 'PASS'
    no_authority(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.proofs.classification = 'FAIL'


@pytest.mark.parametrize('level', [2, 3])
def test_exact_own_after_effective_d3_and_exact_current_admission_consumption(full_profile_machine, monkeypatch, level):
    config, op = own_machine(full_profile_machine, level=level, events=begin_d3(op=full_profile_machine[1])
                             if level == 2 else ())
    targets = home(config.observer, op, usage=True if level == 2 else b'{"runs": 7, "mutated": true}')
    opaque = (config.observer.lab_root / 'individuals' / op['child_agent_id'] / 'tasks' / 'probe.json').stat().st_ino
    usage = targets['usage.json'].stat().st_ino
    read = os.read
    def guard(fd, size):
        ino = os.fstat(fd).st_ino
        assert ino != opaque, 'runtime content read'
        assert level == 2 or ino != usage, 'mutable usage read after DONE D3'
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guard)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == 'OWN_OPERATION' and child.counted == 'EXCLUDED_OWN', child
    assert child.birth_proof == child.individual_proof == p.NE
    current = operation(result, op)
    assert current.own_home == 'PASS' and current.own_agent_id == op['child_agent_id']
    assert result.proofs.classification == 'PASS'
    assert [x.classification for x in result.proofs.homes].count('OWN_OPERATION') == 1
    no_authority(result)


def test_own_incomplete_home_is_ne_not_unauthenticated(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op, usage=False)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == p.NE and child.counted == 'NE'
    assert 'OWN_HOME_INCOMPLETE' in child.codes
    assert result.proofs.classification == p.NE and operation(result, op).own_home == p.NE


def test_own_prefix_short_write_is_incomplete_but_other_content_is_conflict(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    spec = p.storage_bytes(op['birth_plan']['child_spec'])
    home(config.observer, op, **{'spec.json': spec[:len(spec) // 2]})
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == p.NE and 'OWN_HOME_INCOMPLETE' in child.codes
    home(config.observer, op, **{'spec.json': spec.replace(b'"', b"'", 1)})
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and child.counted == 'BLOCKING'
    assert 'HOME_CONFLICT' in child.codes


@pytest.mark.parametrize('case', ['before_d3', 'cancelled', 'quarantined'])
def test_home_without_effective_d3_is_inconsistent(full_profile_machine, case):
    config, op = full_profile_machine
    events = {'before_d3': (), 'cancelled': (*begin_d3(op), base.entry('BEGIN_CANCELLED', 'D3', op=op)),
              'quarantined': (*begin_d3(op), base.entry('INTERRUPTED_RECOVERED', 'D3', op=op,
                  boot=COLD, data={'result': 'PARTIAL'}), base.entry('QUARANTINE_BEGIN', 'D3', op=op),
                  base.entry('QUARANTINE_DONE', 'D3', op=op))}[case]
    own_machine(full_profile_machine, events=events)
    home(config.observer, op)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED', child
    assert 'OPERATION_STATE_INCONSISTENT' in child.codes and 'POPULATION_UNAUTHENTICATED' in child.codes
    assert result.proofs.classification == 'FAIL' and operation(result, op).own_home == p.NE


def test_partial_d3_awaiting_quarantine_is_ne_never_own(full_profile_machine):
    config, op = full_profile_machine
    own_machine(full_profile_machine, events=(*begin_d3(op), base.entry('INTERRUPTED_RECOVERED', 'D3', op=op,
        boot=COLD, data={'result': 'PARTIAL'})))
    home(config.observer, op)
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == p.NE and 'OWN_HOME_INCOMPLETE' in child.codes


def test_own_requires_current_exact_admission_row(full_profile_machine):
    config, op = own_machine(full_profile_machine, consumed=False)
    home(config.observer, op)
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == p.NE and 'BIRTH_COMMIT_UNPROVEN' in child.codes
    env = c.decode(admission_envelope(config.observer, op))
    base.spend(config.observer, op, issuer_id=env['issuer_id'], envelope_id='d' * 64,
               envelope_sha256=f.digest(env))
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED', child


def test_forged_candidate_signature_is_unauthenticated(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op)
    qhash = op['presented']['qualification']['record_sha256']
    path = config.observer.lab_root / 'admission-envelopes' / op['child_agent_id'] / (
        'birth-qualification-' + qhash + '.envelope.json')
    env = c.decode(path.read_bytes())
    env['signature'] = '0' * 128
    base.write(path, f.canonical(env))
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and child.counted == 'BLOCKING'


def test_unsupported_science_keeps_candidate_and_population_ne(signed_machine):
    config, op, envs = signed_machine
    log(config.observer, op, *begin_d3(op), level=2)
    spend(config.observer, op, f.canonical(envs[op['child_agent_id'] + '/admission']))
    home(config.observer, op)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == p.NE and 'SCIENTIFIC_PROFILE_UNSUPPORTED' in child.codes
    assert operation(result, op).decision.scientific_bindings == p.NE
    assert result.proofs.classification == p.NE


@pytest.mark.parametrize('individual', [False, True])
def test_committed_child_is_member_never_excluded_by_old_operation(full_profile_machine, individual):
    config, op = full_profile_machine
    log(config.observer, op, base.entry('COMMITTED', op=op), level=3)
    spend(config.observer, op, admission_envelope(config.observer, op))
    home(config.observer, op, usage=b'{"runs": 3}')
    if individual:
        record = op['birth_plan']['record']
        env = pure.signed(record, c.IND, OPERATOR, 'child', 'operator-1')
        ao.store(config.observer, 'admission-envelopes/' + op['child_agent_id'] + '/individual-'
                 + f.digest(record) + '.envelope.json', f.canonical(env))
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == ('AUTHENTICATED' if individual else 'AWAITING_INDIVIDUAL_ATTESTATION'), child
    assert child.counted == 'INCLUDED' and child.birth_proof == 'PASS'
    assert operation(result, op).scope == 'HISTORICAL' and operation(result, op).own_home == p.NE
    assert result.proofs.classification == 'PASS'


@pytest.mark.parametrize('terminal', ['ABANDONED', 'REFUSED'])
def test_terminal_home_present_is_unauthenticated(full_profile_machine, terminal):
    config, op = full_profile_machine
    log(config.observer, op, base.entry(terminal, op=op))
    home(config.observer, op)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and 'BIRTH_COMMIT_UNPROVEN' in child.codes
    assert result.proofs.classification == 'FAIL'


@pytest.mark.parametrize('version,count,expected', [(1, 0, 'UNAUTHENTICATED'), (0, 0, p.NE), (1, 1, 'UNAUTHENTICATED')])
def test_externally_terminated_home_is_never_counted_and_log_stays_unread(full_profile_machine, monkeypatch,
                                                                          version, count, expected):
    config, op = full_profile_machine
    obs = config.observer
    fault, terminal = logtests.external(obs, child=op['child_agent_id'], op=f.digest(op), version=version, count=count)
    base.write(obs.fault_file, raw(fault, terminal))
    path = obs.lab_root / 'admission-ops' / (op['child_agent_id'] + '.log')
    base.write(path, b'faulty no parse allowed\r\n')
    home(obs, op)
    bad = path.stat().st_ino
    read = os.read
    def guard(fd, size):
        assert os.fstat(fd).st_ino != bad
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guard)
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == expected and child.counted != 'INCLUDED', child
    assert 'OPERATION_LOG_FAULTY' in child.codes
    linkage = result.external_bindings.terminals[0].terminal_linkage
    assert linkage == ('PASS' if (version, count) == (1, 0) else 'FAIL' if version else p.NE)
    if version == 0:
        assert 'EXTERNAL_TERMINATION_UNPROVEN' in child.codes
    elif count:
        assert 'EXTERNAL_TERMINATION_DIVERGENT' in child.codes
    assert not result.proofs.operations


def test_unresolved_external_claim_prevents_own(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op)
    other = 'e' * 64
    fault, terminal = logtests.external(config.observer, child=other, op='f' * 64, version=0, count=0)
    base.write(config.observer.fault_file, raw(fault, terminal))
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == p.NE and 'OPERATION_PENDING' in child.codes
    assert operation(result, op).own_home == p.NE


def test_empty_stable_individuals_is_classified_empty(full_profile_machine):
    config, op = full_profile_machine
    import shutil
    shutil.rmtree(config.observer.lab_root / 'individuals' / op['parent_agent_id'])
    result = scan(config)
    assert result.proofs.homes == () and result.proofs.classification == 'PASS'
    no_authority(result)


@pytest.mark.parametrize('case', ['mutation', 'error'])
def test_failure_after_classification_erases_every_proof(full_profile_machine, monkeypatch, case):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op)
    prove = pp.prove
    def broken(*args, **kw):
        value = prove(*args, **kw)
        assert value.homes
        if case == 'error':
            raise c.CoreError('STORED_FILE_DIVERGENT')
        target = config.observer.lab_root / 'individuals' / op['child_agent_id'] / 'record.json'
        base.write(target, target.read_bytes() + b' ')
        return value
    monkeypatch.setattr(pp, 'prove', broken)
    result = owner.acquire(config)
    acquisition.discarded(result, 'SOURCE_CHANGED' if case == 'mutation' else 'SOURCE_UNAVAILABLE')
    assert result.proofs is None


def test_own_contradiction_considers_only_candidate_presented_items(complete_decision):
    op, decision = complete_decision
    assert not pp._own_contradiction(decision, op)
    ancestor = next(x for x in decision.items if x.key.kind == c.IND)
    forged = dataclasses.replace(ancestor, authenticity='FAIL', genuine_but_revoked=False)
    assert not pp._own_contradiction(dataclasses.replace(decision, items=(forged,)), op)
    own = next(x for x in decision.items if x.key.kind == c.QUAL)
    revoked = dataclasses.replace(own, authenticity='FAIL', genuine_but_revoked=True)
    assert not pp._own_contradiction(dataclasses.replace(decision, items=(revoked,)), op)
    forged = dataclasses.replace(own, authenticity='FAIL', genuine_but_revoked=False)
    assert pp._own_contradiction(dataclasses.replace(decision, items=(forged,)), op)
    # Project-wide exclusions alone (e.g. an ancestor's self issue) are not the candidate's.
    assert not pp._own_contradiction(dataclasses.replace(decision, known_identity_exclusions='FAIL'), op)
    child = op['child_agent_id']
    envelopes = {child + '/qualification': f.canonical({'issuer_id': 'review-' + child[:16]})}
    assert pp._own_contradiction(decision, op, envelopes, frozenset({child}))
    assert not pp._own_contradiction(decision, op, envelopes, frozenset({'e' * 64}))


@pytest.fixture
def complete_decision():
    from tests.colony_admission import test_attestation_projection as projection
    fixture = projection.complete.__wrapped__()
    op = c.operation(fixture['op_bytes'])
    keys = ('op_bytes', 'nodes', 'statement_raw', 'envelopes', 'operation_snapshots', 'root_bytes')
    decision = a.project(*(fixture[k] for k in keys), root_pin=fixture['root_pin'],
        minimum_version=1, lab_id=fixture['lab_id'], policy_bytes=fixture['policy_bytes'],
        policy_pin=fixture['policy_pin'], artifacts=fixture['artifacts'],
        subject_digest=fixture['subject_digest'], evaluator_digest=fixture['evaluator_digest'])
    assert decision.branch_attestations == 'PASS'
    return op, decision


def test_pure_module_without_io_or_public_export():
    import colony_admission
    tree = ast.parse(inspect.getsource(pp))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {'open', 'os', 'fcntl', 'ExitStack'}
    assert not hasattr(colony_admission, 'PopulationObserver')
    assert not hasattr(colony_admission, 'PopulationConfig')


def test_unbound_ledger_line_prevents_own(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op)
    with config.observer.ledger.open('ab') as ledger:
        env = c.decode(admission_envelope(config.observer, op))
        ledger.write(f.canonical({'ledger_schema': 'colony-trust.consumed/1', 'issuer_id': env['issuer_id'],
            'envelope_id': 'a' * 64, 'envelope_sha256': 'b' * 64, 'operation_sha256': 'c' * 64}) + b'\n')
    result = scan(config)
    assert result.external_bindings.ledger_coverage.status == 'UNBOUND'
    child = proof(result, op['child_agent_id'])
    assert child.classification == p.NE and 'LEDGER_OPERATION_UNBOUND' in child.codes


def test_done_d3_without_complete_layout_is_not_own(full_profile_machine):
    config, op = own_machine(full_profile_machine, level=3, events=())
    home(config.observer, op, usage=b'opaque', layout=False)
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == p.NE and 'OWN_HOME_INCOMPLETE' in child.codes
    assert 'D3_LAYOUT_INCOMPLETE' in child.codes


def test_candidate_without_structural_parent_is_unauthenticated(full_profile_machine):
    import shutil
    config, op = own_machine(full_profile_machine)
    home(config.observer, op)
    shutil.rmtree(config.observer.lab_root / 'individuals' / op['parent_agent_id'])
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and child.structure == 'FAIL', child
    assert result.proofs.classification == 'FAIL'


def test_operator_terminating_after_done_d3_is_never_own(full_profile_machine):
    config, op = own_machine(full_profile_machine, level=3, events=(base.entry('TERMINATED', op=op_of(
        full_profile_machine), code='OPERATOR_TERMINATED'),))
    home(config.observer, op, usage=b'opaque')
    result = scan(config)
    child = proof(result, op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and child.counted == 'BLOCKING', child
    assert operation(result, op).own_home == p.NE


def op_of(fixture):
    return fixture[1]


def test_divergent_initial_usage_before_done_d3_is_conflict(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op, usage=b'{"runs":9}')
    child = proof(scan(config), op['child_agent_id'])
    assert child.classification == 'UNAUTHENTICATED' and 'HOME_CONFLICT' in child.codes


def test_fail_dominates_ne_in_population_classification(full_profile_machine):
    config, op = own_machine(full_profile_machine)
    home(config.observer, op, usage=False)  # candidate NE/OWN_HOME_INCOMPLETE
    ao.store(config.observer, 'individuals/' + 'e' * 64 + '/record.json', b'{invalid stable json')
    ao.store(config.observer, 'individuals/' + 'e' * 64 + '/spec.json', b'{}')
    result = scan(config)
    classes = {x.classification for x in result.proofs.homes}
    assert 'UNAUTHENTICATED' in classes and p.NE in classes
    assert result.proofs.classification == 'FAIL'
