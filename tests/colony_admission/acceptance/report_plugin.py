"""Opt-in pytest plugin writing one acceptance-corpus run report.

    python -m pytest -p tests.colony_admission.acceptance.report_plugin \
        --acceptance-report=REPORT.json tests/colony_admission/acceptance

The report holds observed outcomes of this run only, with the registry and
matrix digests it was derived from. It carries no tree or HEAD claim: the
caller records the exact tree next to it. The run is invalid, and no case is
PASS, unless the matrix digests match the registry and every registry check
of test_corpus_registry.py passed in this same run.
"""

import ast
import json
import os
import platform
import sys
from collections import defaultdict

import pytest

from tests.colony_admission.acceptance import corpus

REGISTRY_CHECKS = 'tests/colony_admission/acceptance/test_corpus_registry.py'


def pytest_addoption(parser):
    parser.addoption('--acceptance-report', default=None, help='write the acceptance-corpus run report here')


def _registry_checks():
    tree = ast.parse((corpus.ROOT / REGISTRY_CHECKS).read_text(encoding='utf-8'))
    return {REGISTRY_CHECKS + '::' + x.name for x in tree.body
            if isinstance(x, ast.FunctionDef) and x.name.startswith('test_')}


class _Recorder:
    def __init__(self, path):
        self.path = path
        self.outcomes = defaultdict(lambda: defaultdict(list))
        self.claims = {}

    def pytest_collection_modifyitems(self, items):
        for item in items:
            fn = getattr(item, 'function', None)
            ids = getattr(fn, 'acceptance_cases', ())
            if ids:
                self.claims[item.nodeid.split('[')[0]] = ids

    def pytest_runtest_logreport(self, report):
        if report.when == 'call':
            if hasattr(report, 'wasxfail'):
                outcome = 'xfailed' if report.skipped else 'xpassed'
            else:
                outcome = report.outcome
        elif report.failed:
            outcome = 'error'
        elif report.skipped:
            outcome = 'xfailed' if hasattr(report, 'wasxfail') else 'skipped'
        else:
            return  # a passed setup/teardown is not an executed item
        node, _, param = report.nodeid.partition('[')
        self.outcomes[node][param[:-1]].append(outcome)

    def invalid(self, reg):
        reasons = []
        for ns, (name, _) in corpus.MATRICES.items():
            if corpus.sha256(corpus.DOCS / name) != reg['matrices'][ns]['sha256']:
                reasons.append('MATRIX_DIGEST_MISMATCH:' + ns)
        checks = {k: v for k, v in self.outcomes.items() if k.startswith(REGISTRY_CHECKS + '::')}
        if set(checks) != _registry_checks() or any(
                x != 'passed' for r in checks.values() for v in r.values() for x in v):
            reasons.append('REGISTRY_CHECKS_NOT_PASSED')
        entries = {**reg['cases'], **reg['regressions']}
        for node, ids in self.claims.items():
            if any(node not in entries.get(cid, {}).get('tests', {}) for cid in ids):
                reasons.append('UNREGISTERED_CLAIM:' + node)
        return reasons

    def pytest_sessionfinish(self, session):
        reg = corpus.registry()
        invalid = self.invalid(reg)
        states = corpus.derive(reg, self.outcomes, invalid)
        counts = {ns: {s: sum(1 for k, v in states.items() if k.startswith(ns + ':') and v == s)
                       for s in corpus.EXECUTION} for ns in corpus.NAMESPACES}
        report = {
            'schema': 'colony-admission.acceptance-run/0',
            'run': {'python': platform.python_version(), 'pytest': pytest.__version__,
                    'optimize': sys.flags.optimize, 'dont_write_bytecode': sys.dont_write_bytecode,
                    'euid': os.geteuid(),
                    'exitstatus': int(session.exitstatus)},
            'registry_sha256': corpus.sha256(corpus.REGISTRY),
            'matrix_sha256': {ns: corpus.sha256(corpus.DOCS / f) for ns, (f, _) in corpus.MATRICES.items()},
            'valid': not invalid,
            'invalid_reasons': invalid,
            'counts': counts,
            'cases': states,
            'tests': {k: dict(v) for k, v in sorted(self.outcomes.items()) if k in self.claims},
        }
        with open(self.path, 'w', encoding='utf-8') as out:
            json.dump(report, out, indent=1, sort_keys=True, ensure_ascii=False)
            out.write('\n')


def pytest_configure(config):
    path = config.getoption('--acceptance-report')
    if path:
        config.pluginmanager.register(_Recorder(path), 'acceptance-recorder')
