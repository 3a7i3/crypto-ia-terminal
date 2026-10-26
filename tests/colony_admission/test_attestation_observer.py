"""Independent real-file 3B acquisition tests, temporary LAB_TEST material only."""

import copy
import dataclasses
import fcntl
import os
import shutil

import pytest

from colony_admission import _attestation_core as c
from colony_admission import attestation_observer as ao
from colony_admission import formats as f
from colony_admission import observer as o
from colony_admission import physical_evidence as p
from tests.colony_admission import test_attestation_core as pure
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_attestation_projection as projection
from tests.colony_admission.test_external_evidence import installed
from tests.colony_admission.test_oplog import raw
from tests.colony_trust.keys import ADMITTER, OPERATOR, REVIEWER, root

family = pure.family
machine = base.machine


def store(config, path, raw_bytes):
    target = config.lab_root / path
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    base.write(target, raw_bytes)
    return target


def fixture_log(config, op, level=0):
    path = config.lab_root / 'admission-ops' / (op['child_agent_id'] + '.log')
    base.write(path, raw(*base.prefix(level, op=op)))
    return path


@pytest.fixture
def signed_machine(machine, family):
    config, old = machine
    base.log_path(config).unlink()
    op, nodes, st, policy_bytes, policy_pin = copy.deepcopy(family)
    trust_root = root()
    reviewer = next(i for i in trust_root['issuers'] if i['issuer_id'] == REVIEWER)
    reviewer['scopes'].append(c.STATEMENT)
    reviewer['scopes'].sort()
    policy, history = installed(trust_root)
    config = dataclasses.replace(config, root_pin=policy['pin'])
    base.write(config.trust_directory / 'policy.json', f.canonical(policy))
    base.write(config.trust_directory / 'trust-history.log', f.canonical(history) + b'\n')
    op['historical_root_sha256'] = config.root_pin
    child = op['child_agent_id']
    parent = c.decode(nodes[0].record_bytes)
    a, q = op['birth_plan']['admission'], op['birth_plan']['qualification']
    envs = {
        child + '/admission': pure.signed(a, c.ADM, ADMITTER, 'admission', 'admitter-1'),
        child + '/qualification': pure.signed(q, c.QUAL, REVIEWER, 'qualification'),
        child + '/statement': pure.signed(st, c.STATEMENT, REVIEWER, 'statement'),
        parent['agent_id'] + '/individual': pure.signed(parent, c.IND, OPERATOR, 'individual', 'operator-1'),
    }
    for role, record in (('admission', a), ('qualification', q), ('statement', st)):
        op['presented'][role] = {'record_sha256': f.digest(record),
                                 'envelope_sha256': f.digest(envs[child + '/' + role])}
    op['items'] = [pure.item(c.IND, parent, env=f.digest(envs[parent['agent_id'] + '/individual']))]
    for role, kind, record in (('admission', c.ADM, a), ('qualification', c.QUAL, q), ('statement', c.STATEMENT, st)):
        op['items'].append(pure.item(kind, record, env=f.digest(envs[child + '/' + role])))
    pure.sort_items(op)
    f.validate_operation(op)
    for name in ('registrar-admissions', 'admission-envelopes', 'individuals'):
        (config.lab_root / name).mkdir(mode=0o700, exist_ok=True)
    store(config, 'individuals/' + parent['agent_id'] + '/record.json', nodes[0].record_bytes)
    store(config, 'individuals/' + parent['agent_id'] + '/spec.json', nodes[0].spec_bytes)
    store(config, 'registrar-admissions/' + child + '.json', f.canonical(a))
    qhash = f.digest(q)
    store(config, 'admission-envelopes/' + child + '/statement-' + qhash + '.json', f.canonical(st))
    for namespace, env in envs.items():
        owner, role = namespace.split('/')
        prefix = 'birth-qualification' if role == 'qualification' else role
        digest = qhash if role == 'statement' else env['record_sha256']
        store(config, 'admission-envelopes/' + owner + '/' + prefix + '-' + digest + '.envelope.json', f.canonical(env))
    fixture_log(config, op)
    return ao.AttestationConfig(config, policy_bytes, policy_pin), op, envs


def scan(fixture):
    return ao.AttestationObserver(fixture[0]).scan_attestations()


def discarded(result):
    assert result.status == 'BLOCKED'
    assert not result.sources and not result.metadata_sources and not result.operations
    assert not result.physical_operations and not result.pending_operations
    assert result.ledger_bytes is None and result.ledger_coverage == p.LedgerCoverage()


def test_signed_local_branch_has_no_scientific_or_global_authority(signed_machine):
    result = scan(signed_machine)
    assert len(result.operations) == 1, result
    op = result.operations[0]
    assert op.branch_structure == op.decision_partition == 'PASS', op
    assert len(op.items) == 4
    assert all(i.integrity == i.authenticity == i.issuer_authorization == 'PASS' for i in op.items)
    assert op.scientific_bindings == p.NE and op.branch_attestations != 'PASS'
    assert 'SCIENTIFIC_PROFILE_UNSUPPORTED' in result.blockers
    assert result.status == 'BLOCKED' and result.accepted is False and op.accepted is False
    for name in ('authorization', 'completeness', 'population', 'ceilings', 'durability', 'rotation', 'recovery', 'source_revision_provenance'):
        assert getattr(result, name) == p.NE
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.accepted = True


def test_one_ledger_snapshot_l1_before_l2_and_each_selected_file_read_once(signed_machine, monkeypatch):
    locks, inspected, reads = [], [], []
    flock, inspect, read = fcntl.flock, o.trust.inspect_operations_fd, os.read
    def take_lock(fd, operation):
        locks.append(operation)
        return flock(fd, operation)
    def inspect_once(fd, operations):
        inspected.append(operations)
        return inspect(fd, operations)
    def read_once(fd, count):
        value = os.fstat(fd)
        chunk = read(fd, count)
        if chunk:
            reads.append((value.st_dev, value.st_ino))
        return chunk
    monkeypatch.setattr(fcntl, 'flock', take_lock)
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', inspect_once)
    monkeypatch.setattr(os, 'read', read_once)
    result = scan(signed_machine)
    assert len(result.operations) == 1, result
    assert len(inspected) == 1 and inspected[0] == (f.digest(signed_machine[1]),)
    assert locks[0] & fcntl.LOCK_EX and any(x & fcntl.LOCK_SH for x in locks[1:])
    assert len(reads) == len(set(reads)), 'same tiny fixture file payload was read twice'


@pytest.mark.parametrize('which', ['missing', 'bad_signature', 'wrong_subject', 'extra_field'])
def test_individual_envelope_never_passes_on_missing_or_tampered_bytes(signed_machine, which):
    config, op, envs = signed_machine
    parent = op['parent_agent_id']
    env = copy.deepcopy(envs[parent + '/individual'])
    path = config.observer.lab_root / ('admission-envelopes/' + parent + '/individual-' + env['record_sha256'] + '.envelope.json')
    if which == 'missing':
        path.unlink()
    else:
        if which == 'bad_signature':
            env['signature'] = '0' * 128
        elif which == 'wrong_subject':
            env['subject']['agent_id'] = 'f' * 64
        else:
            env['extra'] = True
        base.write(path, f.canonical(env))
    result = scan(signed_machine)
    assert result.status == 'BLOCKED' and len(result.operations) == 1, result
    assert result.operations[0].branch_attestations != 'PASS'
    item = next(x for x in result.operations[0].items if x.key.kind == c.IND)
    assert item.authenticity != 'PASS'


@pytest.mark.parametrize('change', ['bad_policy', 'missing_pin', 'mutable_policy', 'bad_observer'])
def test_invalid_operator_configuration_has_no_filesystem_access(signed_machine, monkeypatch, change):
    config = signed_machine[0]
    if change == 'bad_policy':
        config = dataclasses.replace(config, registrar_policy_bytes=b'{}')
    elif change == 'missing_pin':
        config = dataclasses.replace(config, registrar_policy_pin=None)
    elif change == 'mutable_policy':
        config = dataclasses.replace(config, registrar_policy_bytes=bytearray(config.registrar_policy_bytes))
    else:
        config = dataclasses.replace(config, observer=object())
    def forbidden(*args, **kwargs):
        raise AssertionError('filesystem opened before rejecting operator configuration')
    monkeypatch.setattr(os, 'open', forbidden)
    discarded(ao.AttestationObserver(config).scan_attestations())


def test_policy_item_limit_refused_before_opening_ledger(signed_machine, monkeypatch):
    config, op, _ = signed_machine
    selected = f.loads(config.registrar_policy_bytes)
    selected['max_population'] = 2
    raw_policy, pin = f.canonical(selected), f.digest(selected)
    # cap=4. A fifth syntactically valid frozen population item exceeds it.
    extra = copy.deepcopy(op['items'][0])
    extra['role'] = 'POPULATION'
    extra['record_sha256'] = 'f' * 64
    op['items'].append(extra)
    pure.sort_items(op)
    fixture_log(config.observer, op)
    def forbidden(*args, **kwargs):
        raise AssertionError('ledger inspection before frozen item limit')
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', forbidden)
    result = ao.AttestationObserver(dataclasses.replace(config, registrar_policy_bytes=raw_policy, registrar_policy_pin=pin)).scan_attestations()
    discarded(result)
    assert result.blockers == ('SOURCE_LIMIT',) and result.limits.reached == ('item_references',)


def test_mutation_after_projection_invalidates_entire_payload(signed_machine, monkeypatch):
    original = ao._Attestations.project
    def mutate(self, *args):
        original(self, *args)
        config, op, _ = signed_machine
        path = config.observer.lab_root / ('individuals/' + op['parent_agent_id'] + '/record.json')
        base.write(path, path.read_bytes() + b' ')
    monkeypatch.setattr(ao._Attestations, 'project', mutate)
    result = scan(signed_machine)
    discarded(result)
    assert result.blockers == ('SOURCE_CHANGED',)


def test_close_failure_invalidates_entire_payload(signed_machine, monkeypatch):
    close, count = os.close, 0
    def fail_one(fd):
        nonlocal count
        count += 1
        close(fd)
        if count == 1:
            raise OSError('simulated close failure')
    monkeypatch.setattr(os, 'close', fail_one)
    discarded(scan(signed_machine))


def test_busy_registrar_refuses_without_retry(signed_machine):
    path = signed_machine[0].observer.lab_root / 'registrar.lock'
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = scan(signed_machine)
    finally:
        os.close(fd)
    discarded(result)
    assert result.blockers == ('REGISTRAR_BUSY',)


def test_read_only_scan_preserves_file_bytes_mode_and_mtime(signed_machine):
    root_path = signed_machine[0].observer.lab_root.parent
    paths = [p for p in root_path.rglob('*') if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths}
    result = scan(signed_machine)
    assert result.operations, result
    assert {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths} == before


def test_historical_attempt_does_not_receive_current_attestation(signed_machine):
    config, op, _ = signed_machine
    new = copy.deepcopy(op)
    new['attempt'] = 2
    old_events = base.prefix(op=op) + [base.entry('ABANDONED', op=op)]
    base.write(config.observer.lab_root / ('admission-ops/' + op['child_agent_id'] + '.log'),
               raw(*old_events, *base.prefix(op=new)))
    result = scan(signed_machine)
    assert len(result.operations) == 2, result
    historic, current = result.operations
    assert historic.latest is False and current.latest is True
    assert historic.branch_structure == historic.branch_attestations == p.NE
    assert not historic.items and not historic.needs
    assert 'HISTORICAL_ATTESTATIONS_NOT_EVALUATED' in historic.blockers
    assert current.branch_structure == 'PASS'


@pytest.mark.parametrize('invalid_signature', [False, True])
def test_revoked_envelope_classification_requires_valid_signature(signed_machine, invalid_signature):
    config, op, envs = signed_machine
    parent = op['parent_agent_id']
    envelope = copy.deepcopy(envs[parent + '/individual'])
    trust_root = root(version=2, revoked=(envelope['envelope_id'],))
    reviewer = next(i for i in trust_root['issuers'] if i['issuer_id'] == REVIEWER)
    reviewer['scopes'].append(c.STATEMENT)
    reviewer['scopes'].sort()
    policy, history = installed(trust_root)
    # A second valid root/history entry models current revocation of old signatures.
    original_history = (config.observer.trust_directory / 'trust-history.log').read_bytes()
    base.write(config.observer.trust_directory / 'policy.json', f.canonical(policy))
    base.write(config.observer.trust_directory / 'trust-history.log', original_history + f.canonical(history) + b'\n')
    config = dataclasses.replace(config, observer=dataclasses.replace(config.observer, root_pin=policy['pin']))
    if invalid_signature:
        envelope['signature'] = '0' * 128
        target = 'admission-envelopes/' + parent + '/individual-' + envelope['record_sha256'] + '.envelope.json'
        store(config.observer, target, f.canonical(envelope))
        frozen = next(x for x in op['items'] if x['kind'] == c.IND)
        frozen['envelope_sha256'] = f.digest(envelope)
        fixture_log(config.observer, op)
    result = ao.AttestationObserver(config).scan_attestations()
    assert result.operations, result
    item = next(x for x in result.operations[0].items if x.key.kind == c.IND)
    assert item.genuine_but_revoked is (not invalid_signature), item
    assert result.operations[0].branch_attestations != 'PASS'
    assert 'ENVELOPE_REVOKED' in item.codes
    if invalid_signature:
        assert 'SIGNATURE_INVALID' in item.codes


def test_malformed_stable_parent_is_local_divergence_with_raw_stamp(signed_machine):
    config, op, _ = signed_machine
    target = 'individuals/' + op['parent_agent_id'] + '/record.json'
    store(config.observer, target, b'{"duplicate":1,"duplicate":2}')
    result = scan(signed_machine)
    assert result.operations and result.operations[0].branch_structure == 'FAIL', result
    assert result.operations[0].branch_attestations == 'FAIL'
    assert any(x.resource == target for x in result.sources)


def test_missing_parent_is_no_complete_branch_prefix(signed_machine):
    config, op, _ = signed_machine
    path = config.observer.lab_root / ('individuals/' + op['parent_agent_id'] + '/record.json')
    path.unlink()
    result = scan(signed_machine)
    assert result.operations and result.operations[0].branch_structure == p.NE, result
    assert not result.operations[0].branch
    assert result.operations[0].branch_attestations != 'PASS'


@pytest.mark.parametrize('target', ['parent_record', 'parent_envelope'])
@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'fifo', 'public'])
def test_unsafe_branch_source_clears_all_payload(signed_machine, target, unsafe):
    config, op, envs = signed_machine
    parent = op['parent_agent_id']
    if target == 'parent_record':
        path = config.observer.lab_root / ('individuals/' + parent + '/record.json')
    else:
        digest = envs[parent + '/individual']['record_sha256']
        path = config.observer.lab_root / ('admission-envelopes/' + parent + '/individual-' + digest + '.envelope.json')
    path.unlink()
    if unsafe == 'symlink':
        path.symlink_to(config.observer.ledger)
    elif unsafe == 'hardlink':
        os.link(config.observer.ledger, path)
    elif unsafe == 'fifo':
        os.mkfifo(path, 0o600)
    else:
        path.write_bytes(b'{}')
        path.chmod(0o644)
    discarded(scan(signed_machine))


@pytest.fixture
def full_profile_machine(machine):
    config, _ = machine
    base.log_path(config).unlink()
    fixture = projection.complete.__wrapped__()
    op = c.operation(fixture['op_bytes'])
    policy, history = installed(c.decode(fixture['root_bytes']))
    config = dataclasses.replace(config, root_pin=policy['pin'])
    base.write(config.trust_directory / 'policy.json', f.canonical(policy))
    base.write(config.trust_directory / 'trust-history.log', f.canonical(history) + b'\n')
    op['historical_root_sha256'] = config.root_pin
    for name in ('registrar-admissions', 'admission-envelopes', 'individuals'):
        (config.lab_root / name).mkdir(mode=0o700, exist_ok=True)
    child = op['child_agent_id']
    for node in fixture['nodes']:
        store(config, 'individuals/' + node.agent_id + '/record.json', node.record_bytes)
        store(config, 'individuals/' + node.agent_id + '/spec.json', node.spec_bytes)
    store(config, 'registrar-admissions/' + child + '.json', f.canonical(op['birth_plan']['admission']))
    qhash = f.digest(op['birth_plan']['qualification'])
    store(config, 'admission-envelopes/' + child + '/statement-' + qhash + '.json', fixture['statement_raw'])
    for namespace, raw_envelope in fixture['envelopes'].items():
        owner, role = namespace.split('/')
        env = c.decode(raw_envelope)
        digest = qhash if role == 'statement' else env['record_sha256']
        prefix = 'birth-qualification' if role == 'qualification' else role
        store(config, 'admission-envelopes/' + owner + '/' + prefix + '-' + digest + '.envelope.json', raw_envelope)
    for source in ('colony_lab', 'sentinel_activity', 'governance_tower', 'observability'):
        shutil.copytree(pure.ROOT / source, config.checkout_root / source,
                        ignore=shutil.ignore_patterns('__pycache__'))
    for path, raw_artifact in fixture['artifacts'].items():
        target = config.checkout_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw_artifact)
    fixture_log(config, op)
    return ao.AttestationConfig(config, fixture['policy_bytes'], fixture['policy_pin']), op


def test_full_real_acquisition_proves_current_supported_local_branch(full_profile_machine):
    config, _ = full_profile_machine
    result = ao.AttestationObserver(config).scan_attestations()
    assert result.status == 'OBSERVED' and not result.blockers, result
    assert len(result.operations) == 1
    op = result.operations[0]
    assert op.branch_structure == op.branch_attestations == op.scientific_bindings == op.statements == 'PASS'
    assert op.known_identity_exclusions == op.decision_partition == 'PASS'
    assert op.accepted is result.accepted is False
    assert op.source_revision_provenance == result.source_revision_provenance == p.NE
    assert any(x.resource.startswith('CHECKOUT:') for x in result.sources)


@pytest.mark.parametrize('kind', ['artifact', 'code', 'extra_source', 'forbidden_source'])
def test_full_profile_checkout_mutation_never_keeps_scientific_pass(full_profile_machine, kind):
    config, _ = full_profile_machine
    root_path = config.observer.checkout_root
    if kind == 'artifact':
        target = root_path / 'docs/colony_lab/evidence/C9_sentinel_evidence.json'
        target.write_bytes(target.read_bytes() + b'\n')
    elif kind == 'code':
        target = root_path / 'colony_lab/workers/sentinel.py'
        target.write_bytes(target.read_bytes() + b'\n')
    elif kind == 'extra_source':
        (root_path / 'governance_tower/extra-fixture.txt').write_bytes(b'changes closure')
    else:
        (root_path / 'governance_tower/.env').write_bytes(b'never read')
    result = ao.AttestationObserver(config).scan_attestations()
    assert result.status == 'BLOCKED'
    assert all(x.scientific_bindings != 'PASS' and x.branch_attestations != 'PASS' for x in result.operations)
    if kind == 'forbidden_source':
        discarded(result)
        assert 'SOURCE_PATH_FORBIDDEN' in result.blockers


@pytest.mark.parametrize('capacity', ['ledger_bytes', 'ledger_entries'])
def test_real_ledger_capacity_clears_payload_with_named_limit(signed_machine, capacity):
    config, op, _ = signed_machine
    if capacity == 'ledger_bytes':
        with config.observer.ledger.open('r+b') as stream:
            stream.truncate(o.trust.INSPECTION_MAX_BYTES + 1)
    else:
        rows = []
        for index in range(o.trust.INSPECTION_MAX_ENTRIES + 1):
            row = {'ledger_schema': o.trust.OPERATION_LEDGER_SCHEMA,
                   'issuer_id': ADMITTER, 'envelope_id': f'{index:064x}',
                   'envelope_sha256': 'a' * 64, 'operation_sha256': f.digest(op)}
            rows.append(f.canonical(row) + b'\n')
        base.write(config.observer.ledger, b''.join(rows))
    result = scan(signed_machine)
    discarded(result)
    assert result.blockers == ('SOURCE_LIMIT',)
    assert result.limits.reached == (capacity,)
