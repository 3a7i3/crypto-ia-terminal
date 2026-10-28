"""Temporary private log-phase fixtures; no public scan/ledger/crypto authority."""

import dataclasses
import os
from contextlib import ExitStack

import pytest

from colony_admission import _population_inventory as inv
from colony_admission import _population_log_acquisition as logs
from colony_admission import evidence_observer as e
from colony_admission import formats as f
from colony_admission import observer as o
from tests.colony_admission import test_external_evidence as fx
from tests.colony_admission import test_observer as base
from tests.colony_admission.test_observer import entry, prefix
from tests.colony_admission.test_oplog import raw

machine = base.machine


def external(config, *, child=fx.CHILD, op=fx.OP, version=1, count=1):
    changes = dict(lab_id=config.lab_id, child_agent_id=child, operation_sha256=op)
    fault = fx.fault(**changes, data={'origin': 'CONTROLLER', 'failure': 'WRITE',
        'target': {'resource': 'OPERATION_LOG', 'object_kind': 'FILE', 'relative_path': child + '.log'}})
    term = fx.terminate(fault, count=count, version=version, **changes)
    finding = term['data']['ledger_finding']
    if version:
        obs = finding['observation']
        obs['operation_sha256'] = op
        if obs['entry'] is not None:
            obs['entry']['operation_sha256'] = op
        finding['observation_sha256'] = f.digest(obs)
    return fault, term


def acquire(config, fault_raw=b'', cap=252, *, hook=None):
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        lab = source.directory(config.lab_root)
        source.file(lab, 'registrar.lock', 'L1', 0, lock=True)
        result = logs.acquire_logs(source, lab, fault_raw, config.lab_id, item_cap=cap)
        if hook is not None:
            hook(source, result)
        source.verify()
    return result


def test_plain_history_and_pending_are_retained_without_global_proof(machine, monkeypatch):
    config, old = machine
    new = {**old, 'attempt': 2}
    base.write(base.log_path(config), raw(*prefix(op=old), entry('REFUSED', op=old), *prefix(op=new)))
    def forbidden(*args, **kwargs):
        pytest.fail('ledger or signature used in log inventory phase')
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', forbidden)
    monkeypatch.setattr(o.trust, 'classify_envelope', forbidden)
    result = acquire(config)
    assert result.operation_ids == tuple(sorted((f.digest(old), f.digest(new))))
    assert [a.latest for a in result.attempts] == [False, True]
    assert f.loads(result.attempts[0].operation_bytes) == old
    assert result.pending_from_readable_logs == (f.digest(new),)
    assert result.snapshot_completeness == result.external_facts == 'NOT_EVALUATED'
    assert result.accepted is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.operation_ids = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.attempts[0].latest = True


@pytest.mark.parametrize('version', [0, 1])
@pytest.mark.parametrize('count', [0, 1])
@pytest.mark.parametrize('present', [False, True])
def test_external_union_and_faulty_log_never_read_even_legacy_or_absent(machine, monkeypatch, version, count, present):
    config, op = machine
    fault, term = external(config, version=version, count=count)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    if present:
        base.write(path, b'corrupt\r\nnot a log')
    unread_inode = path.stat().st_ino if present else None
    read = os.read
    def guarded(fd, size):
        assert os.fstat(fd).st_ino != unread_inode, 'faulty bytes were read'
        return read(fd, size)
    monkeypatch.setattr(os, 'read', guarded)
    result = acquire(config, raw(fault, term))
    assert result.operation_ids == tuple(sorted((f.digest(op), fx.OP)))
    assert len(result.attempts) == 1 and len(result.unread_logs) == 1
    opaque = result.unread_logs[0]
    assert opaque.presence == ('PRESENT' if present else 'ABSENT')
    assert opaque.size == (len(b'corrupt\r\nnot a log') if present else None)
    assert opaque.termination_entry_bytes == f.canonical(term)
    assert opaque.terminal_linkage == 'NOT_EVALUATED'
    # Neither historical count nor existence of an embedded observation settles pending.
    assert result.external_facts == 'NOT_EVALUATED'
    with pytest.raises(dataclasses.FrozenInstanceError):
        opaque.terminal_linkage = 'PASS'


@pytest.mark.parametrize('case', ['fault_only', 'no_fault', 'bad_fault_hash', 'wrong_child', 'wrong_attempt', 'ledger_target'])
def test_no_generic_exception_for_corrupt_logs_or_forged_external_claim(machine, case):
    config, _ = machine
    fault, term = external(config)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    base.write(path, b'corrupt\n')
    entries = [fault, term]
    if case == 'fault_only':
        entries = [fault]
    elif case == 'no_fault':
        entries = [term]
    elif case == 'bad_fault_hash':
        term['data']['fault_sha256'] = 'f' * 64
    elif case == 'wrong_child':
        term['child_agent_id'] = 'f' * 64
    elif case == 'wrong_attempt':
        term['attempt'] = 2
    else:
        fault['data']['target'] = {'resource': 'LEDGER', 'object_kind': 'FILE', 'relative_path': ''}
        term['data']['fault_sha256'] = f.digest(fault)
    with pytest.raises(o._Blocked, match='OPERATION_LOG_UNAVAILABLE|FAULT_LOG_UNAVAILABLE'):
        acquire(config, raw(*entries))


@pytest.mark.parametrize('present', [False, True])
def test_faulty_log_absence_and_replacement_are_revalidated(machine, present):
    config, _ = machine
    fault, term = external(config)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    if present:
        base.write(path, b'corrupt\n')
    def mutate(source, result):
        if present:
            path.unlink()
        base.write(path, b'replacement\n')
    with pytest.raises(o._Blocked, match='SOURCE_CHANGED'):
        acquire(config, raw(fault, term), hook=mutate)


@pytest.mark.parametrize('case', ['symlink', 'hardlink', 'fifo', 'directory', 'mode'])
def test_unread_log_still_requires_regular_private_single_link_metadata(machine, case):
    config, _ = machine
    fault, term = external(config)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    if case == 'symlink':
        path.symlink_to(base.log_path(config))
    elif case == 'hardlink':
        os.link(base.log_path(config), path)
    elif case == 'fifo':
        os.mkfifo(path, 0o600)
    elif case == 'directory':
        path.mkdir(mode=0o700)
    else:
        base.write(path, b'opaque')
        path.chmod(0o644)
    with pytest.raises((o._Blocked, OSError)):
        acquire(config, raw(fault, term))


def test_enoent_after_open_is_not_absence(machine, monkeypatch):
    config, _ = machine
    fault, term = external(config)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    base.write(path, b'opaque')
    original = inv.InventorySource.checked_file_descriptor
    def gone(self, fd, parent, name, limit, **kwargs):
        if name == fx.CHILD + '.log':
            raise FileNotFoundError('after open')
        return original(self, fd, parent, name, limit, **kwargs)
    monkeypatch.setattr(inv.InventorySource, 'checked_file_descriptor', gone)
    with pytest.raises(FileNotFoundError, match='after open'):
        acquire(config, raw(fault, term))


@pytest.mark.parametrize('normal_count,external_count,limit', [(0, 256, False), (0, 257, True),
    (1, 255, False), (1, 256, True)])
def test_full_union_bound_includes_absent_external_logs_before_any_ledger(machine, monkeypatch, normal_count, external_count, limit):
    config, _ = machine
    if not normal_count:
        base.log_path(config).unlink()
    entries = []
    for i in range(external_count):
        entries.extend(external(config, child=f'{1000 + i:064x}', op=f'{10000 + i:064x}', version=i % 2, count=0))
    def forbidden(*args, **kwargs):
        pytest.fail('ledger opened during pre-ledger phase')
    monkeypatch.setattr(o.trust, 'inspect_operations_fd', forbidden)
    if limit:
        with pytest.raises(e._Capacity) as caught:
            acquire(config, raw(*entries))
        assert caught.value.limit_name == 'operations'
    else:
        result = acquire(config, raw(*entries))
        assert len(result.operation_ids) == 256


def test_frozen_item_bound_precedes_any_signature_or_ledger(machine, monkeypatch):
    config, op = machine
    op['items'] = [{'kind': 'colony-lab.individual/0', 'subject': {'agent_id': 'a' * 64,
        'agent_spec_id': 'b' * 64}, 'record_sha256': 'c' * 64, 'envelope_sha256': 'd' * 64,
        'role': 'POPULATION'}]
    f.validate_operation(op)
    base.write(base.log_path(config), raw(*prefix(op=op)))
    with pytest.raises(e._Capacity) as caught:
        acquire(config, cap=0)
    assert caught.value.limit_name == 'item_references'


@pytest.mark.parametrize('which', ['foreign_lab', 'foreign_child'])
def test_readable_log_cannot_claim_other_lab_or_child(machine, which):
    config, op = machine
    if which == 'foreign_lab':
        op['lab_id'] = 'another-lab'
    else:
        wrong = config.lab_root / 'admission-ops' / ('e' * 64 + '.log')
        base.log_path(config).rename(wrong)
    path = base.log_path(config) if which == 'foreign_lab' else wrong
    base.write(path, raw(*prefix(op=op)))
    with pytest.raises(o._Blocked, match='OPERATION_BINDING_MISMATCH'):
        acquire(config)


def test_external_hash_cannot_bind_readable_operation_of_another_child(machine):
    config, op = machine
    fault, term = external(config, op=f.digest(op))
    with pytest.raises(o._Blocked, match='OPERATION_BINDING_MISMATCH'):
        acquire(config, raw(fault, term))


def test_257_names_refused_before_reading_any_log_content(machine, monkeypatch):
    config, _ = machine
    for i in range(256):
        base.write(config.lab_root / 'admission-ops' / (f'{i:064x}' + '.log'), b'')
    def no_log(self, parent, name, *args, **kwargs):
        assert name == 'registrar.lock'
        return original(self, parent, name, *args, **kwargs)
    original = inv.InventorySource.file
    monkeypatch.setattr(inv.InventorySource, 'file', no_log)
    with pytest.raises(e._Capacity) as caught:
        acquire(config)
    assert caught.value.limit_name == 'logs'


@pytest.mark.parametrize('value', [True, -1, 253, None])
def test_invalid_detached_item_cap_is_not_used(machine, value):
    with pytest.raises(o._Blocked, match='CONFIG_INVALID'):
        acquire(machine[0], cap=value)


def test_close_failure_prevents_return_of_provisional_log_inventory(machine, monkeypatch):
    original = os.close
    first = True
    def fail_once(fd):
        nonlocal first
        original(fd)
        if first:
            first = False
            raise OSError('close failed')
    monkeypatch.setattr(os, 'close', fail_once)
    with pytest.raises(OSError, match='close failed'):
        acquire(machine[0])


def test_read_only_and_no_public_population_api(machine):
    config, _ = machine
    files = [p for p in config.lab_root.rglob('*') if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files}
    acquire(config)
    assert before == {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files}
    import colony_admission
    assert not hasattr(colony_admission, 'PopulationObserver')
    assert not hasattr(colony_admission, 'PopulationConfig')


def test_empty_log_namespace_is_not_a_population_completeness_claim(machine):
    config, _ = machine
    base.log_path(config).unlink()
    result = acquire(config)
    assert result.operation_ids == result.names == result.attempts == ()
    assert result.snapshot_completeness == 'NOT_EVALUATED'


@pytest.mark.parametrize('name', ['unknown', 'UPPER.log', 'a.log', 'a' * 64 + '.json'])
def test_closed_log_namespace_never_ignores_unknown_entries(machine, name):
    config, _ = machine
    base.write(config.lab_root / 'admission-ops' / name, b'')
    with pytest.raises(o._Blocked, match='OPERATION_NAMESPACE_INVALID'):
        acquire(config)


@pytest.mark.parametrize('case', ['per_log', 'sum'])
def test_unread_log_sizes_share_existing_log_byte_limits(machine, monkeypatch, case):
    config, _ = machine
    fault, term = external(config)
    path = config.lab_root / 'admission-ops' / (fx.CHILD + '.log')
    base.write(path, b'opaque')
    if case == 'per_log':
        with path.open('r+b') as handle:
            handle.truncate(f.MAX_LOG + 1)
    else:
        monkeypatch.setattr(o, 'MAX_SCAN_BYTES', 5)
    with pytest.raises(e._Capacity) as caught:
        acquire(config, raw(fault, term))
    assert caught.value.limit_name == ('per_log_bytes' if case == 'per_log' else 'log_bytes')


def test_ack_fragment_with_cr_keeps_original_parser_boundaries(machine):
    import hashlib
    config, op = machine
    # A CR inside an acknowledged non-JSON fragment is not an event boundary.
    fragment = b'opaque\r' + f.canonical(entry('BEGIN', 'D1', op=op))
    acknowledgement = entry('TORN_TAIL_ACKNOWLEDGED', op=op,
                            data={'fragment_sha256': hashlib.sha256(fragment).hexdigest()})
    base.write(base.log_path(config), raw(*prefix(op=op)) + fragment + b'\n' + raw(acknowledgement))
    result = acquire(config)
    assert result.attempts[0].projection.status == 'OPEN'
    assert result.attempts[0].projection.last_completed_step == 'D0'


@pytest.mark.parametrize('tail', [b'{}\n', b'bad', b'\r\n'])
def test_unclaimed_corrupt_or_torn_log_never_salvages_prepared_prefix(machine, tail):
    config, _ = machine
    path = base.log_path(config)
    base.write(path, path.read_bytes() + tail)
    with pytest.raises(o._Blocked, match='OPERATION_LOG_UNAVAILABLE'):
        acquire(config)
