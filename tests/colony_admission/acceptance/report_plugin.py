"""Opt-in pytest plugin writing one acceptance-corpus run report.

    python -m pytest -p tests.colony_admission.acceptance.report_plugin \
        --acceptance-report=REPORT.json tests/colony_admission/acceptance

The report holds observed outcomes of this run only, with the registry and
matrix digests it was derived from. It carries no tree or HEAD claim: the
caller records the exact tree next to it.
"""

import json
import platform
import sys
from collections import defaultdict

import pytest

from tests.colony_admission.acceptance import corpus


def pytest_addoption(parser):
    parser.addoption('--acceptance-report', default=None, help='write the acceptance-corpus run report here')


class _Recorder:
    def __init__(self, path):
        self.path = path
        self.outcomes = defaultdict(list)
        self.claims = {}

    def pytest_collection_modifyitems(self, items):
        for item in items:
            fn = getattr(item, 'function', None)
            ids = getattr(fn, 'acceptance_cases', ())
            if ids:
                self.claims[item.nodeid.split('[')[0]] = ids

    def pytest_runtest_logreport(self, report):
        node = report.nodeid.split('[')[0]
        if report.when == 'call':
            if hasattr(report, 'wasxfail'):
                self.outcomes[node].append('xfailed' if report.skipped else 'xpassed')
            else:
                self.outcomes[node].append(report.outcome)
        elif report.failed:
            self.outcomes[node].append('error')
        elif report.skipped:
            self.outcomes[node].append('xfailed' if hasattr(report, 'wasxfail') else 'skipped')

    def pytest_sessionfinish(self, session):
        reg = corpus.registry()
        states = corpus.derive(reg, self.outcomes)
        counts = {ns: {s: sum(1 for k, v in states.items() if k.startswith(ns + ':') and v == s)
                       for s in corpus.EXECUTION} for ns in corpus.NAMESPACES}
        report = {
            'schema': 'colony-admission.acceptance-run/0',
            'run': {'python': platform.python_version(), 'pytest': pytest.__version__,
                    'optimize': sys.flags.optimize, 'dont_write_bytecode': sys.dont_write_bytecode,
                    'exitstatus': int(session.exitstatus)},
            'registry_sha256': corpus.sha256(corpus.REGISTRY),
            'matrix_sha256': {ns: corpus.sha256(corpus.DOCS / f) for ns, (f, _) in corpus.MATRICES.items()},
            'counts': counts,
            'cases': states,
            'tests': {k: v for k, v in sorted(self.outcomes.items()) if k in self.claims},
        }
        with open(self.path, 'w', encoding='utf-8') as out:
            json.dump(report, out, indent=1, sort_keys=True, ensure_ascii=False)
            out.write('\n')


def pytest_configure(config):
    path = config.getoption('--acceptance-report')
    if path:
        config.pluginmanager.register(_Recorder(path), 'acceptance-recorder')
