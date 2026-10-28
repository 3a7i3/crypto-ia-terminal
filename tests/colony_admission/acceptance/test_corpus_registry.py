"""The registry is traceability, not a result: it must match the matrices exactly."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.colony_admission.acceptance import corpus, report_plugin

HERE = Path(__file__).resolve().parent
CASE_KEYS = {'implementation', 'tests', 'fixture', 'variants', 'notes', 'negative', 'divergence',
             'name_tag_candidates', 'blocked_reason'}
REGRESSION_KEYS = {'implementation', 'value', 'relation', 'tests', 'fixture', 'variants', 'notes', 'negative'}


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
        assert entry['tests'] and entry.get('fixture') and entry.get('variants'), cid
        for node in entry['tests']:
            assert cid in corpus.test_function(node).acceptance_cases, (cid, node)
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


@pytest.mark.parametrize('bad', ['INV-01', '3D:INV-01', '3C:', 'REG'])
def test_case_ids_are_namespaced(bad):
    with pytest.raises(ValueError):
        corpus.case(bad)


def test_derive_never_reports_pass_without_every_item_passing():
    reg = {'cases': {
        'X:pass': {'implementation': 'IMPLEMENTED', 'tests': ['a', 'b']},
        'X:missing': {'implementation': 'IMPLEMENTED', 'tests': ['a', 'gone']},
        'X:fail': {'implementation': 'IMPLEMENTED', 'tests': ['a', 'f']},
        'X:skip': {'implementation': 'IMPLEMENTED', 'tests': ['s']},
        'X:xfail': {'implementation': 'IMPLEMENTED', 'tests': ['x']},
        'X:error': {'implementation': 'IMPLEMENTED', 'tests': ['e']},
        'X:none': {'implementation': 'NON_IMPLEMENTED'},
        'X:blocked': {'implementation': 'BLOCKED', 'blocked_reason': 'r'},
        'X:ext': {'implementation': 'CONTRACT_NOT_EXECUTABLE'}},
        'regressions': {'REG:r': {'implementation': 'IMPLEMENTED', 'tests': ['b']}}}
    outcomes = {'a': ['passed', 'passed'], 'b': ['passed'], 'f': ['passed', 'failed'], 's': ['passed', 'skipped'],
                'x': ['xfailed'], 'e': ['passed', 'error']}
    assert corpus.derive(reg, outcomes) == {
        'X:pass': 'PASS', 'X:missing': 'NOT_EXECUTED', 'X:fail': 'FAIL', 'X:skip': 'NOT_EXECUTED',
        'X:xfail': 'FAIL', 'X:error': 'FAIL', 'X:none': 'NON_IMPLEMENTED', 'X:blocked': 'BLOCKED',
        'X:ext': 'CONTRACT_NOT_EXECUTABLE', 'REG:r': 'PASS'}


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
    assert dict(recorder.outcomes) == {'m::ok': ['passed', 'failed'], 'm::setup': ['error'],
                                       'm::teardown': ['passed', 'error'], 'm::skip': ['skipped'],
                                       'm::xf': ['xfailed'], 'm::xp': ['xpassed']}
