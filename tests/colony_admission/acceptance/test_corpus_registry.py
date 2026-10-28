"""The registry is traceability, not a result: it must match the matrices exactly."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.colony_admission.acceptance import corpus, report_plugin

HERE = Path(__file__).resolve().parent
CASE_KEYS = {'implementation', 'tests', 'fixture', 'notes', 'negative', 'divergence',
             'name_tag_candidates', 'blocked_reason'}
REGRESSION_KEYS = {'implementation', 'value', 'relation', 'tests', 'fixture', 'notes', 'negative'}


@pytest.fixture(scope='module')
def reg():
    return corpus.registry()


def claimed():
    """Every case() claim in the acceptance test modules, from their source."""
    result = {}
    for path in sorted(HERE.glob('test_*.py')):
        module = importlib.import_module('tests.colony_admission.acceptance.' + path.stem)
        for node in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(node, ast.FunctionDef):
                ids = getattr(getattr(module, node.name), 'acceptance_cases', ())
                if ids:
                    result['tests/colony_admission/acceptance/' + path.name + '::' + node.name] = ids
    return result


def test_registry_lists_exactly_the_matrix_cases(reg):
    cases = corpus.matrix_cases()
    assert list(reg['cases']) == list(cases)
    counts = {ns: sum(1 for x in cases if x.startswith(ns + ':')) for ns in corpus.MATRICES}
    assert counts == {'3A': 66, '3B': 75, '3C': 107, 'EXT': 27}
    assert {ns: m['cases'] for ns, m in reg['matrices'].items()} == counts


def test_matrices_are_pinned_and_keep_their_contract_status(reg):
    for ns, (name, status) in corpus.MATRICES.items():
        entry = reg['matrices'][ns]
        assert entry['path'] == 'docs/colony_admission/' + name
        assert entry['sha256'] == corpus.sha256(corpus.DOCS / name), ns + ' matrix changed: review the registry'
        assert entry['status'] == corpus.matrix(ns)['status'] == status
    assert corpus.matrix('3C')['defaults']['cases_are_executed'] is False


def test_registry_carries_no_execution_result(reg):
    assert reg['status'] == 'TRACEABILITY_ONLY_NOT_AN_EXECUTION_RESULT' and reg['accepted'] is False
    assert set(reg['entry_points']) == set(corpus.MATRICES)
    for cid, entry in reg['cases'].items():
        assert set(entry) <= CASE_KEYS, cid
        assert entry['implementation'] in corpus.IMPLEMENTATION, cid
        assert (entry['implementation'] == 'CONTRACT_NOT_EXECUTABLE') is cid.startswith('EXT:'), cid
    for rid, entry in reg['regressions'].items():
        assert rid.startswith('REG:') and set(entry) <= REGRESSION_KEYS, rid
        assert entry['implementation'] in {'NON_IMPLEMENTED', 'IMPLEMENTED', 'BLOCKED'}, rid


def test_implemented_entries_resolve_to_tests_that_claim_them(reg):
    for cid, entry in list(reg['cases'].items()) + list(reg['regressions'].items()):
        if entry['implementation'] == 'BLOCKED':
            assert entry.get('blocked_reason'), cid
        if entry['implementation'] != 'IMPLEMENTED':
            assert 'tests' not in entry, cid
            continue
        assert entry['tests'] and entry.get('fixture'), cid
        for node, ids in entry['tests'].items():
            fn = corpus.test_function(node)
            assert cid in fn.acceptance_cases, (cid, node)
            # Every variant is an explicit parametrize id, registered exactly.
            assert ids == corpus.parametrize_ids(fn) and len(set(ids)) == len(ids), (cid, node)
    for node in (n for e in reg['cases'].values() for n in e.get('name_tag_candidates', ())):
        corpus.test_function(node)  # candidates exist; they are never counted


def test_every_claim_is_registered(reg):
    entries = {**reg['cases'], **reg['regressions']}
    for node, ids in claimed().items():
        for cid in ids:
            assert entries[cid]['implementation'] == 'IMPLEMENTED' and node in entries[cid]['tests'], (node, cid)


def test_plan_document_is_rendered_from_the_current_registry():
    assert corpus.PLAN.read_text(encoding='utf-8') == corpus.render_plan(), \
        'regenerate: python -m tests.colony_admission.acceptance.corpus plan > ' + str(corpus.PLAN)


def test_assertions_are_enabled():
    # Under -O --assert=plain no assert runs anywhere: such a run proves nothing.
    try:
        assert False
    except AssertionError:
        return
    pytest.fail('assert statements are disabled in this run')


BAD_IDS = ['INV-01', '3D:INV-01', '3C:', 'REG']


@pytest.mark.parametrize('bad', BAD_IDS, ids=BAD_IDS)
def test_case_ids_are_namespaced(bad):
    with pytest.raises(ValueError):
        corpus.case(bad)


def test_derive_never_reports_pass_without_every_item_passing():
    reg = {'cases': {
        'X:pass': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1', '2'], 'b': []}},
        'X:missing': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1', '2'], 'gone': []}},
        'X:partial': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1', '2', '3']}},
        'X:extra': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1']}},
        'X:fail': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1', '2'], 'f': []}},
        'X:skip': {'implementation': 'IMPLEMENTED', 'tests': {'s': ['1', '2']}},
        'X:xfail': {'implementation': 'IMPLEMENTED', 'tests': {'x': []}},
        'X:error': {'implementation': 'IMPLEMENTED', 'tests': {'e': []}},
        'X:empty': {'implementation': 'IMPLEMENTED', 'tests': {'a': ['1', '2'], 'z': []}},
        'X:none': {'implementation': 'NON_IMPLEMENTED'},
        'X:blocked': {'implementation': 'BLOCKED', 'blocked_reason': 'r'},
        'X:ext': {'implementation': 'CONTRACT_NOT_EXECUTABLE'}},
        'regressions': {'REG:r': {'implementation': 'IMPLEMENTED', 'tests': {'b': []}}}}
    outcomes = {'a': {'1': ['passed'], '2': ['passed']}, 'b': {'': ['passed']},
                'f': {'': ['failed']}, 's': {'1': ['passed'], '2': ['skipped']},
                'x': {'': ['xfailed']}, 'e': {'': ['passed', 'error']}, 'z': {'': []}}
    assert corpus.derive(reg, outcomes) == {
        'X:pass': 'PASS', 'X:missing': 'NOT_EXECUTED', 'X:partial': 'NOT_EXECUTED', 'X:extra': 'NOT_EXECUTED',
        'X:fail': 'FAIL', 'X:skip': 'NOT_EXECUTED', 'X:xfail': 'FAIL', 'X:error': 'FAIL', 'X:empty': 'NOT_EXECUTED',
        'X:none': 'NON_IMPLEMENTED', 'X:blocked': 'BLOCKED', 'X:ext': 'CONTRACT_NOT_EXECUTABLE', 'REG:r': 'PASS'}
    # An invalid run (digests or registry checks) never yields PASS.
    states = corpus.derive(reg, outcomes, ('REGISTRY_CHECKS_NOT_PASSED',))
    assert 'PASS' not in states.values() and states['X:pass'] == states['REG:r'] == 'NOT_EXECUTED'


def test_recorder_maps_reports_to_outcomes(tmp_path):
    recorder = report_plugin._Recorder(tmp_path / 'r.json')
    def report(node, when, outcome, **extra):
        return SimpleNamespace(nodeid=node, when=when, outcome=outcome, failed=outcome == 'failed',
                               skipped=outcome == 'skipped', **extra)
    for r in (report('m::ok[1]', 'setup', 'passed'), report('m::ok[1]', 'call', 'passed'),
              report('m::ok[1]', 'teardown', 'passed'), report('m::ok[2]', 'call', 'failed'),
              report('m::setup', 'setup', 'failed'), report('m::teardown', 'call', 'passed'),
              report('m::teardown', 'teardown', 'failed'), report('m::skip', 'setup', 'skipped'),
              report('m::xf', 'call', 'skipped', wasxfail=''), report('m::xp', 'call', 'passed', wasxfail='')):
        recorder.pytest_runtest_logreport(r)
    assert {k: dict(v) for k, v in recorder.outcomes.items()} == {
        'm::ok': {'1': ['passed'], '2': ['failed']}, 'm::setup': {'': ['error']},
        'm::teardown': {'': ['passed', 'error']}, 'm::skip': {'': ['skipped']},
        'm::xf': {'': ['xfailed']}, 'm::xp': {'': ['xpassed']}}


def test_run_is_invalid_without_matching_digests_checks_and_registered_claims(reg, tmp_path, monkeypatch):
    recorder = report_plugin._Recorder(tmp_path / 'r.json')
    assert recorder.invalid(reg) == ['REGISTRY_CHECKS_NOT_PASSED']
    for node, ids in report_plugin._registry_checks().items():
        for x in ids or ['']:
            recorder.outcomes[node][x].append('passed')
    assert recorder.invalid(reg) == []
    partial = sorted(k for k, ids in report_plugin._registry_checks().items() if ids)[0]
    kept = recorder.outcomes[partial].pop(report_plugin._registry_checks()[partial][0])
    assert recorder.invalid(reg) == ['REGISTRY_CHECKS_NOT_PASSED']
    recorder.outcomes[partial][report_plugin._registry_checks()[partial][0]] = kept
    recorder.outcomes[sorted(report_plugin._registry_checks())[0]]['x'].append('failed')
    assert recorder.invalid(reg) == ['REGISTRY_CHECKS_NOT_PASSED']
    del recorder.outcomes[sorted(report_plugin._registry_checks())[0]]['x']
    recorder.claims['m::orphan'] = ('3C:INV-01',)
    assert recorder.invalid(reg) == ['UNREGISTERED_CLAIM:m::orphan']
    del recorder.claims['m::orphan']
    changed = {**reg, 'matrices': {**reg['matrices'], '3C': {**reg['matrices']['3C'], 'sha256': '0' * 64}}}
    assert recorder.invalid(changed) == ['MATRIX_DIGEST_MISMATCH:3C']
    # Under -p no:assertion the option does not exist: the run is invalid, never a crash.
    def config(mode):
        return SimpleNamespace(getoption=lambda name, default=None: mode if mode else default)
    assert recorder.run_invalid(reg, config('rewrite')) == ([], 'rewrite')
    assert recorder.run_invalid(reg, config(None)) == (['ASSERTMODE_UNAVAILABLE'], None)
