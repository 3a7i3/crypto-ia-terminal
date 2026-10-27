"""Private current-ledger bindings; detached and temporary LAB_TEST material."""

import copy
import dataclasses
import importlib
import os

import pytest

from colony_admission import _population_external as pe
from colony_admission import _population_acquisition as owner
from colony_admission import formats as f
from colony_admission import physical_evidence as p
from tests.colony_admission import test_external_evidence as fx
from tests.colony_admission import test_population_acquisition as acquisition_tests
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_population_log_acquisition as logtests

family = ao.family
machine = base.machine
signed_machine = ao.signed_machine


def batch(rows=(), *, total=0, legacy=0):
    return {'inspection_schema': 'colony-trust.operations-inspection/0', 'status': 'OBSERVED',
        'ledger_entries': total, 'legacy_entries': legacy, 'ledger_sha256': 'f' * 64,
        'observations': list(rows), 'failures': [], 'accepted': False,
        **dict.fromkeys(('authenticity', 'authorization', 'completeness', 'provenance', 'durability'), p.NE)}


def material(count=1, *, version=1, extra=0, legacy=0):
    fault = fx.fault()
    terminal = fx.terminate(fault, count=count, version=version)
    row = fx.observation(count)
    row.update(ledger_entries=count + extra + legacy, legacy_entries=legacy, ledger_sha256='f' * 64)
    if not count and legacy:
        row.update(status='LEGACY_AMBIGUITY', failures=['LEGACY_OPERATION_UNBOUND'])
    return [fault, terminal], batch((row,), total=row['ledger_entries'], legacy=legacy)


def link(entries, current, ids=(fx.OP,)):
    return pe.link(fx.raw(*entries), fx.LAB, f.canonical(current), ids)


@pytest.mark.parametrize('count', [0, 1])
@pytest.mark.parametrize('extra', [0, 1, 7])
def test_exact_current_finding_matches_despite_later_ledger_digest_and_total(count, extra):
    entries, current = material(count, extra=extra)
    result = link(entries, current)
    fact, = result.terminals
    assert fact.terminal_linkage == 'PASS'
    assert fact.terminal_classification == ('FAILED_CONSUMED' if count else 'ABANDONED')
    assert fact.fault_sha256 == f.digest(entries[0])
    assert fact.termination_sha256 == f.digest(entries[1])
    assert f.loads(fact.current_observation_bytes) == current['observations'][0]
    assert fact.codes == ('OPERATION_LOG_FAULTY',)
    assert result.resolved_ids == (fx.OP,) and not result.unresolved_ids
    assert result.ledger_coverage.status == ('UNBOUND' if extra else 'MATCH')
    assert result.ledger_coverage.matched_entries == count
    assert result.ledger_coverage.unbound_entries == extra
    assert result.snapshot_completeness == result.pending_completeness == result.population == p.NE
    assert fact.birth_proof == fact.action_completion == fact.durability == p.NE
    assert fact.accepted is result.accepted is False


@pytest.mark.parametrize('count', [0, 1])
def test_legacy_external_reference_cannot_resolve_even_exact_current_match(count):
    entries, current = material(count, version=0)
    result = link(entries, current)
    fact, = result.terminals
    assert fact.terminal_linkage == p.NE and fact.terminal_classification is None
    assert result.unresolved_ids == (fx.OP,) and not result.resolved_ids
    assert 'EXTERNAL_TERMINATION_NOT_EVALUATED' in fact.codes


@pytest.mark.parametrize('field,value', [('issuer_id', 'different-issuer'),
    ('envelope_id', '1' * 64), ('envelope_sha256', '2' * 64)])
def test_every_full_current_entry_binding_is_required(field, value):
    entries, current = material()
    current['observations'][0]['entry'][field] = value
    result = link(entries, current)
    fact, = result.terminals
    assert fact.terminal_linkage == 'FAIL' and fact.terminal_classification is None
    assert 'EXTERNAL_FINDING_DIVERGENT' in fact.codes
    assert result.unresolved_ids == (fx.OP,)


@pytest.mark.parametrize('historical,current_count', [(0, 1), (1, 0)])
def test_changed_current_count_and_status_are_divergent(historical, current_count):
    entries, _ = material(historical)
    _, current = material(current_count)
    fact, = link(entries, current).terminals
    assert fact.terminal_linkage == 'FAIL' and fact.terminal_classification is None


@pytest.mark.parametrize('count', [0, 1])
def test_current_legacy_ambiguity_and_specific_present_entry_are_distinct(count):
    entries, current = material(count, legacy=1)
    result = link(entries, current)
    fact, = result.terminals
    assert fact.terminal_linkage == ('PASS' if count else p.NE)
    assert result.ledger_coverage.status == 'LEGACY_UNBOUND'
    assert 'LEGACY_LEDGER_UNBOUND' in result.ledger_codes
    assert 'LEDGER_OPERATION_UNBOUND' in result.ledger_codes
    assert result.snapshot_completeness == result.population == p.NE


def test_conflicting_current_entries_cannot_match_historical_single_entry():
    entries, current = material()
    current['ledger_entries'] = 2
    current['observations'][0].update(ledger_entries=2, operation_entries=2,
        status='CONFLICT', entry=None, failures=['OPERATION_MULTIPLE_ENTRIES'])
    result = link(entries, current)
    assert result.terminals[0].terminal_linkage == 'FAIL'
    assert result.ledger_coverage.status == 'UNBOUND'
    assert 'LEDGER_UNAVAILABLE' in result.ledger_codes


@pytest.mark.parametrize('case', ['fault_hash', 'observation_hash', 'child', 'attempt', 'code', 'no_fault'])
def test_strict_fault_and_terminal_binds_are_rechecked(case):
    entries, current = material()
    term = entries[1]
    if case == 'fault_hash':
        term['data']['fault_sha256'] = '0' * 64
    elif case == 'observation_hash':
        term['data']['ledger_finding']['observation_sha256'] = '0' * 64
    elif case == 'child':
        term['child_agent_id'] = '0' * 64
    elif case == 'attempt':
        term['attempt'] += 1
    elif case == 'code':
        term['code'] = 'WRONG'
    else:
        entries.pop(0)
    with pytest.raises(f.FormatError):
        link(entries, current)


@pytest.mark.parametrize('field,value', [('status', 'LEDGER_BUSY'), ('accepted', True),
    ('authenticity', 'PASS'), ('failures', ['LEDGER_CORRUPT']), ('ledger_entries', True),
    ('legacy_entries', -1), ('ledger_sha256', 'bad'), ('extra', 1)])
def test_batch_is_closed_observed_and_unprivileged(field, value):
    entries, current = material()
    current[field] = value
    with pytest.raises(f.FormatError):
        link(entries, current)


@pytest.mark.parametrize('field,value', [('operation_sha256', '0' * 64), ('operation_entries', True),
    ('status', 'NO_OPERATION_ENTRY'), ('ledger_entries', 2), ('legacy_entries', True),
    ('ledger_sha256', '0' * 64), ('accepted', True), ('authorization', 'PASS'),
    ('entry', None), ('failures', ['unknown']), ('extra', 1)])
def test_current_row_must_belong_to_this_complete_current_batch(field, value):
    entries, current = material()
    current['observations'][0][field] = value
    with pytest.raises(f.FormatError):
        link(entries, current)


@pytest.mark.parametrize('case', ['missing_row', 'extra_row', 'duplicate_ids', 'unsorted_ids', 'claim_outside_u'])
def test_exact_u_rows_no_omission_duplicates_or_late_id(case):
    entries, current = material()
    ids = (fx.OP,)
    if case == 'missing_row':
        current['observations'] = []
    elif case == 'extra_row':
        current['observations'] *= 2
    elif case == 'duplicate_ids':
        ids = (fx.OP, fx.OP)
    elif case == 'unsorted_ids':
        ids = (fx.OP, '0' * 64)
    else:
        current = batch()
        ids = ()
    with pytest.raises(f.FormatError):
        link(entries, current, ids)


def test_rows_cannot_claim_more_matched_entries_than_the_global_snapshot():
    entries, current = material()
    second = copy.deepcopy(current['observations'][0])
    second['operation_sha256'] = 'c' * 64
    second['entry']['operation_sha256'] = 'c' * 64
    current['observations'].append(second)
    with pytest.raises(f.FormatError):
        link(entries, current, (fx.OP, 'c' * 64))


@pytest.mark.parametrize('resource', ['operations', 'rows', 'bytes'])
def test_named_cap_before_unbounded_input_processing(resource):
    entries, current = material()
    ids = (fx.OP,)
    if resource == 'operations':
        ids = tuple(f'{i:064x}' for i in range(257))
    elif resource == 'rows':
        current['observations'] *= 257
    raw = b'x' * (16 * 1024 * 1024 + 1) if resource == 'bytes' else f.canonical(current)
    with pytest.raises(pe.ExternalLimit) as caught:
        pe.link(fx.raw(*entries), fx.LAB, raw, ids)
    assert caught.value.limit_name == ('ledger_snapshot_bytes' if resource == 'bytes' else 'operations')


def test_empty_faults_still_reconcile_whole_ledger_coverage():
    empty = link([], batch(), ())
    assert empty.terminals == empty.resolved_ids == empty.unresolved_ids == ()
    assert empty.ledger_coverage.status == 'MATCH'
    orphan = link([], batch(total=1), ())
    assert orphan.ledger_coverage.status == 'UNBOUND'
    assert orphan.ledger_codes == ('LEDGER_OPERATION_UNBOUND',)
    assert orphan.pending_completeness == orphan.population == p.NE


def test_immutable_results_keep_no_mutable_input_alias():
    entries, current = material()
    result = link(entries, current)
    before = result.terminals[0].current_observation_bytes
    current['observations'][0]['entry']['envelope_id'] = '0' * 64
    entries.clear()
    assert result.terminals[0].current_observation_bytes == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.resolved_ids = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.terminals[0].terminal_linkage = 'FAIL'


def test_module_reload_is_pure_and_has_no_public_export(monkeypatch):
    import colony_admission
    monkeypatch.setattr(os, 'open', lambda *a, **kw: pytest.fail('IO during pure import'))
    importlib.reload(pe)
    assert not hasattr(colony_admission, 'PopulationObserver')
    assert not hasattr(colony_admission, 'ExternalBindings')


@pytest.mark.parametrize('count', [0, 1])
def test_current_binding_uses_same_owner_unique_batch_without_reading_faulty_log(signed_machine, monkeypatch, count):
    config, op, _ = signed_machine
    fault, terminal = logtests.external(config.observer, count=count)
    base.write(config.observer.fault_file, fx.raw(fault, terminal))
    bad = ao.store(config.observer, 'admission-ops/' + fault['child_agent_id'] + '.log', b'faulty opaque\r\n')
    historical = terminal['data']['ledger_finding']['observation']
    base.write(config.observer.ledger, f.canonical(historical['entry']) + b'\n' if count else b'')
    inspected, read = [], os.read
    inspect = owner.o.trust.inspect_operations_fd
    def once(fd, ids):
        inspected.append(ids)
        return inspect(fd, ids)
    def guard(fd, size):
        assert os.fstat(fd).st_ino != bad.stat().st_ino
        return read(fd, size)
    monkeypatch.setattr(owner.o.trust, 'inspect_operations_fd', once)
    monkeypatch.setattr(os, 'read', guard)
    result = owner.acquire(config)
    assert result.status == 'ACQUIRED', result
    assert inspected == [tuple(sorted((f.digest(op), fault['operation_sha256'])))]
    fact, = result.external_bindings.terminals
    assert fact.terminal_linkage == 'PASS'
    assert fact.terminal_classification == ('FAILED_CONSUMED' if count else 'ABANDONED')
    assert result.external_bindings.ledger_coverage.status == 'MATCH'
    assert 'OPERATION_PENDING' not in result.preflight[0].codes
    assert result.log_inventory.unread_logs[0].terminal_linkage == p.NE
    assert result.terminal_linkage == result.snapshot_completeness == result.population == p.NE
    assert result.accepted is False


@pytest.mark.parametrize('cause', ['mutation', 'close', 'link_error', 'limit'])
def test_same_owner_erases_new_binding_payload_on_any_context_failure(signed_machine, monkeypatch, cause):
    config, op, _ = signed_machine
    if cause == 'mutation':
        science = owner._science
        def corrupt(*a, **kw):
            value = science(*a, **kw)
            path = config.observer.lab_root / 'individuals' / op['parent_agent_id'] / 'record.json'
            base.write(path, path.read_bytes() + b' ')
            return value
        monkeypatch.setattr(owner, '_science', corrupt)
    elif cause == 'close':
        close, calls = os.close, []
        def fail(fd):
            close(fd)
            calls.append(fd)
            if len(calls) == 1:
                raise OSError('fixture close')
        monkeypatch.setattr(os, 'close', fail)
    else:
        def fail(*a, **kw):
            if cause == 'limit':
                raise pe.ExternalLimit('operations')
            raise f.FormatError()
        monkeypatch.setattr(pe, 'link', fail)
    result = owner.acquire(config)
    acquisition_tests.discarded(result)
    if cause == 'limit':
        assert result.codes == ('SOURCE_LIMIT',) and result.limits == ('operations',)
