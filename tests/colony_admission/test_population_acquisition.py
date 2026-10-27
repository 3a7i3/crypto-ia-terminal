"""Single-context temporary LAB_TEST acquisition, never an operational scan."""

import dataclasses
import fcntl
import os

import pytest

from colony_admission import _population_acquisition as owner
from colony_admission import _population_inventory as inv
from colony_admission import _population_preflight as pf
from colony_admission import formats as f
from colony_admission import observer as o
from colony_admission import physical_evidence as p
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_population_log_acquisition as logtests
from tests.colony_admission.test_oplog import raw

family = ao.family
machine = base.machine
signed_machine = ao.signed_machine
full_profile_machine = ao.full_profile_machine


def quarantine_store(config, path, content):
    target = ao.store(config, path, content)
    for parent in target.parents:
        if parent == config.lab_root:
            break
        parent.chmod(0o700)
    return target


def discarded(result, code=None):
    assert result.status == 'BLOCKED'
    assert not result.sources and not result.metadata_sources
    assert not result.homes and not result.operations and not result.quarantined_homes
    assert not result.preflight and result.log_inventory is None
    assert result.ledger_bytes is result.root_bytes is result.minimum_version is None
    assert result.fault_bytes is result.trust_policy_bytes is result.trust_history_bytes is None
    assert result.policy_bytes is result.policy_pin is None
    assert not result.artifacts and result.subject_digest is result.evaluator_digest is None
    assert result.accepted is False
    if code:
        assert result.codes == (code,)


def test_one_owner_order_fresh_fd_and_deduplicated_private_reads(signed_machine, monkeypatch):
    config, op, _ = signed_machine
    events, reads = [], []
    inspect, read, flock = o.trust.inspect_operations_fd, os.read, fcntl.flock
    inventory, homes, derive = owner._private_inventory, inv.acquire_homes, pf.derive
    def inventoried(*args):
        events.append('inventory')
        return inventory(*args)
    def inspect_once(fd, ids):
        assert events == ['L1', 'inventory']
        assert ids == (f.digest(op),)
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        events.append('ledger')
        return inspect(fd, ids)
    def acquired_homes(*args):
        events.append('homes')
        return homes(*args)
    def preflight(*args, **kwargs):
        assert events == ['L1', 'inventory', 'ledger', 'L2', 'unlock', 'homes']
        events.append('preflight')
        return derive(*args, **kwargs)
    def lock(fd, how):
        events.append('unlock' if how == fcntl.LOCK_UN else 'L2' if how & fcntl.LOCK_SH else 'L1')
        return flock(fd, how)
    def counted(fd, size):
        chunk = read(fd, size)
        if chunk:
            reads.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
        return chunk
    monkeypatch.setattr(owner, '_private_inventory', inventoried)
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', inspect_once)
    monkeypatch.setattr(inv, 'acquire_homes', acquired_homes)
    monkeypatch.setattr(pf, 'derive', preflight)
    monkeypatch.setattr(fcntl, 'flock', lock)
    monkeypatch.setattr(os, 'read', counted)
    # Any signature/proof wiring would violate this acquisition-only tranche.
    monkeypatch.setattr(o.trust, 'classify_envelope', lambda *a, **kw: pytest.fail('signature before proof phase'))
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert len(reads) == len(set(reads))
    assert events[-2:] == ['preflight', 'unlock']
    assert result.log_inventory.operation_ids == (f.digest(op),)
    assert len(result.homes) == len(result.operations) == len(result.preflight) == 1
    assert result.root_bytes and result.minimum_version == 1
    assert result.population == result.counts == result.own_home == result.ceilings == p.NE
    assert result.snapshot_completeness == result.terminal_linkage == result.authorization == p.NE
    assert result.accepted is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.homes = ()


@pytest.mark.parametrize('case', ['type', 'path', 'overlap', 'policy', 'pin'])
def test_config_detached_before_any_io(signed_machine, monkeypatch, case):
    config = signed_machine[0]
    if case == 'type':
        config = object()
    elif case == 'path':
        config = dataclasses.replace(config, observer=dataclasses.replace(config.observer, lab_root='relative'))
    elif case == 'overlap':
        config = dataclasses.replace(config, observer=dataclasses.replace(config.observer, ledger=config.observer.lab_root / 'ledger'))
    elif case == 'policy':
        config = dataclasses.replace(config, registrar_policy_bytes=b'invalid')
    else:
        config = dataclasses.replace(config, registrar_policy_pin=None)
    monkeypatch.setattr(os, 'open', lambda *a, **kw: pytest.fail('IO on invalid config'))
    discarded(owner.acquire(config), 'CONFIG_INVALID')


@pytest.mark.parametrize('case', ['missing_individuals', 'bad_home', 'bad_layout', 'bad_admission',
    'bad_envelope_owner', 'bad_envelope_file', 'oversize_record', 'oversize_envelope',
    'bad_quarantine_op', 'bad_quarantine_attempt', 'bad_quarantine_layout'])
def test_global_private_inventory_before_ledger(signed_machine, monkeypatch, case):
    config, op, _ = signed_machine
    lab = config.observer.lab_root
    parent = lab / 'individuals' / op['parent_agent_id']
    if case == 'missing_individuals':
        import shutil
        shutil.rmtree(lab / 'individuals')
    elif case == 'bad_home':
        (lab / 'individuals' / 'bad').mkdir(mode=0o700)
    elif case == 'bad_layout':
        base.write(parent / 'unexpected', b'opaque')
    elif case == 'bad_admission':
        ao.store(config.observer, 'registrar-admissions/bad.json', b'{}')
    elif case == 'bad_envelope_owner':
        (lab / 'admission-envelopes' / 'bad').mkdir(mode=0o700)
    elif case == 'bad_envelope_file':
        ao.store(config.observer, 'admission-envelopes/' + op['parent_agent_id'] + '/bad', b'{}')
    elif case == 'oversize_record':
        base.write(parent / 'record.json', b'x' * 65537)
    elif case == 'oversize_envelope':
        target = next((lab / 'admission-envelopes' / op['parent_agent_id']).iterdir())
        base.write(target, b'x' * 16385)
    else:
        path = 'admission-quarantine/' + ('bad' if case == 'bad_quarantine_op' else f.digest(op))
        path += '/' + ('01' if case == 'bad_quarantine_attempt' else '1') + '/unexpected'
        quarantine_store(config.observer, path, b'opaque')
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('ledger before global namespace/known limits'))
    result = owner.acquire(config)
    discarded(result)
    if case.startswith('oversize'):
        assert result.limits == ('record_bytes' if case == 'oversize_record' else 'envelope_bytes',)


@pytest.mark.parametrize('version', [0, 1])
@pytest.mark.parametrize('count', [0, 1])
def test_complete_external_union_with_unread_faulty_log(signed_machine, monkeypatch, version, count):
    config, op, _ = signed_machine
    fault, terminal = logtests.external(config.observer, version=version, count=count)
    base.write(config.observer.fault_file, raw(fault, terminal))
    child = fault['child_agent_id']
    path = config.observer.lab_root / 'admission-ops' / (child + '.log')
    base.write(path, b'faulty no parse allowed\r\n')
    bad_inode = path.stat().st_ino
    read, inspect = os.read, o.trust.inspect_operations_fd
    calls = []
    def guarded(fd, size):
        assert os.fstat(fd).st_ino != bad_inode
        return read(fd, size)
    def union(fd, ids):
        calls.append(ids)
        return inspect(fd, ids)
    monkeypatch.setattr(os, 'read', guarded)
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', union)
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert calls == [tuple(sorted((f.digest(op), fault['operation_sha256'])))]
    assert result.log_inventory.unread_logs[0].terminal_linkage == p.NE
    assert result.terminal_linkage == p.NE
    assert 'OPERATION_PENDING' in result.preflight[0].codes
    assert result.preflight[0].derived_n is None


@pytest.mark.parametrize('level', [2, 3])
def test_initial_usage_only_before_done_d3(signed_machine, monkeypatch, level):
    config, op, _ = signed_machine
    child = op['child_agent_id']
    for name, value in [('spec.json', op['birth_plan']['child_spec']), ('record.json', op['birth_plan']['record']),
                        ('birth_qualification.json', op['birth_plan']['qualification'])]:
        ao.store(config.observer, 'individuals/' + child + '/' + name, p.storage_bytes(value))
    target = ao.store(config.observer, 'individuals/' + child + '/usage.json',
                      p.storage_bytes({'runs': 0}) if level == 2 else b'x' * 65537)
    events = base.prefix(level, op=op)
    if level == 2:
        events += [base.entry('BEGIN', 'D3', op=op)]
    base.write(config.observer.lab_root / 'admission-ops' / (child + '.log'), raw(*events))
    read, reads = os.read, []
    def guard(fd, size):
        if os.fstat(fd).st_ino == target.stat().st_ino:
            assert level == 2, 'read mutable usage after DONE D3'
            reads.append(fd)
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guard)
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert result.operations[0].source.usage_bytes == (p.storage_bytes({'runs': 0}) if level == 2 else None)
    assert bool(reads) == (level == 2)


def test_required_initial_usage_size_is_known_before_ledger(signed_machine, monkeypatch):
    config, op, _ = signed_machine
    child = op['child_agent_id']
    ao.store(config.observer, 'individuals/' + child + '/usage.json', b'x' * 65537)
    events = base.prefix(2, op=op) + [base.entry('BEGIN', 'D3', op=op)]
    base.write(config.observer.lab_root / 'admission-ops' / (child + '.log'), raw(*events))
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('ledger before required usage cap'))
    result = owner.acquire(config)
    discarded(result, 'SOURCE_LIMIT')
    assert result.limits == ('record_bytes',)


def test_quarantine_identity_is_detached_layout_runtime_unread_and_binding_ne(signed_machine, monkeypatch):
    config, op, _ = signed_machine
    path = 'admission-quarantine/' + f.digest(op) + '/1/'
    target = quarantine_store(config.observer, path + 'record.json', b'partial expected record prefix')
    opaque = quarantine_store(config.observer, path + 'usage.json', b'opaque mutable')
    read = os.read
    def guard(fd, size):
        assert os.fstat(fd).st_ino != opaque.stat().st_ino
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guard)
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    home, = result.quarantined_homes
    assert home.record_bytes == target.read_bytes() and home.spec_bytes is None
    assert home.location_binding == home.identity_binding == home.action_completion == p.NE


@pytest.mark.parametrize('case', ['home', 'listing', 'absence', 'checkout'])
def test_mutation_after_preflight_discards_whole_context(signed_machine, monkeypatch, case):
    config, op, _ = signed_machine
    derive = pf.derive
    def mutate(*args, **kw):
        value = derive(*args, **kw)
        if case == 'home':
            target = config.observer.lab_root / 'individuals' / op['parent_agent_id'] / 'record.json'
            base.write(target, target.read_bytes() + b' ')
        elif case == 'listing':
            (config.observer.lab_root / 'individuals' / ('e' * 64)).mkdir(mode=0o700)
        elif case == 'absence':
            (config.observer.lab_root / 'admission-quarantine').mkdir(mode=0o700)
        else:
            config.observer.checkout_root.chmod(0o777)
        return value
    monkeypatch.setattr(pf, 'derive', mutate)
    discarded(owner.acquire(config), 'SOURCE_CHANGED')


@pytest.mark.parametrize('case', ['close', 'unlock_l1', 'unlock_l2', 'preflight_limit'])
def test_exit_and_limit_failures_erase_all_payload(signed_machine, monkeypatch, case):
    if case == 'close':
        close, calls = os.close, []
        def broken(fd):
            close(fd)
            calls.append(fd)
            if len(calls) == 1:
                raise OSError('test close')
        monkeypatch.setattr(os, 'close', broken)
    elif case.startswith('unlock'):
        flock = fcntl.flock
        calls = []
        def broken(fd, how):
            flock(fd, how)
            if how == fcntl.LOCK_UN:
                calls.append(fd)
                if len(calls) == (2 if case == 'unlock_l1' else 1):
                    raise OSError('test unlock')
        monkeypatch.setattr(fcntl, 'flock', broken)
    else:
        def broken(*args, **kw):
            raise pf.PreflightLimit('derived_items')
        monkeypatch.setattr(pf, 'derive', broken)
    result = owner.acquire(signed_machine[0])
    discarded(result)
    if case == 'preflight_limit':
        assert result.codes == ('SOURCE_LIMIT',) and result.limits == ('derived_items',)


def test_busy_l1_never_opens_ledger_or_retries(signed_machine, monkeypatch):
    config = signed_machine[0]
    fd = os.open(config.observer.lab_root / 'registrar.lock', os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('L2 despite L1 busy'))
        discarded(owner.acquire(config), 'REGISTRAR_BUSY')
    finally:
        os.close(fd)


def test_no_public_export_or_product_execution():
    import colony_admission
    assert not hasattr(colony_admission, 'PopulationObserver')
    assert not hasattr(colony_admission, 'PopulationConfig')


def test_global_preflight_before_one_shared_scientific_checkout(full_profile_machine, monkeypatch):
    config, _ = full_profile_machine
    calls = []
    derive, science = pf.derive, owner.a.Checkout.science
    def preflight(*args, **kw):
        calls.append('preflight')
        return derive(*args, **kw)
    def checkout(self, **kw):
        assert calls == ['preflight']
        calls.append('checkout')
        return science(self, **kw)
    monkeypatch.setattr(pf, 'derive', preflight)
    monkeypatch.setattr(owner.a.Checkout, 'science', checkout)
    monkeypatch.setattr(o.trust, 'classify_envelope', lambda *a, **kw: pytest.fail('crypto in acquisition'))
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert calls == ['preflight', 'checkout']
    assert result.artifacts and result.subject_digest and result.evaluator_digest
    assert result.population == result.snapshot_completeness == p.NE


def test_offbranch_home_is_retained_despite_invalid_record(signed_machine):
    config = signed_machine[0]
    agent = 'e' * 64
    ao.store(config.observer, 'individuals/' + agent + '/record.json', b'{invalid stable json')
    ao.store(config.observer, 'individuals/' + agent + '/spec.json', b'{}')
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert {x.agent_id for x in result.homes} == {agent, signed_machine[1]['parent_agent_id']}
    assert result.preflight[0].derived_n is None
    assert result.preflight[0].derivation != 'PASS'


def test_66_homes_limit_before_ledger(signed_machine, monkeypatch):
    config = signed_machine[0]
    for i in range(65):
        (config.observer.lab_root / 'individuals' / f'{i:064x}').mkdir(mode=0o700)
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('ledger before homes cap'))
    result = owner.acquire(config)
    discarded(result, 'SOURCE_LIMIT')
    assert result.limits == ('homes',)


@pytest.mark.parametrize('resource,limit_name', [('fault', 'fault_bytes'),
    ('policy', 'trust_policy_bytes'), ('history', 'trust_history_bytes'), ('lock', 'registrar_lock_bytes')])
def test_external_and_lock_byte_limits_are_named_before_ledger(signed_machine, monkeypatch, resource, limit_name):
    config = signed_machine[0].observer
    path, cap = {
        'fault': (config.fault_file, owner.FAULT_MAX_LINES * owner.FAULT_LINE_BYTES),
        'policy': (config.trust_directory / 'policy.json', owner.POLICY_MAX_BYTES),
        'history': (config.trust_directory / 'trust-history.log', owner.HISTORY_MAX_LINES * owner.HISTORY_LINE_BYTES),
        'lock': (config.lab_root / 'registrar.lock', 0),
    }[resource]
    with path.open('r+b') as file:
        file.truncate(cap + 1)
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('ledger before external cap'))
    result = owner.acquire(signed_machine[0])
    discarded(result, 'SOURCE_LIMIT')
    assert result.limits == (limit_name,)


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'fifo', 'public'])
def test_unsafe_private_entry_invalidates_before_ledger(signed_machine, monkeypatch, unsafe):
    config, op, _ = signed_machine
    path = config.observer.lab_root / 'individuals' / op['parent_agent_id'] / 'record.json'
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
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', lambda *a, **kw: pytest.fail('ledger before unsafe metadata'))
    discarded(owner.acquire(config))
