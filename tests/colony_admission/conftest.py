"""Passive diagnostics for an intermittent SOURCE_CHANGED seen only on CI runners.

Every colony_admission test records where a SOURCE_CHANGED refusal is built and the
descriptor facts around it. Nothing changes the refusal, the code or the result; the
record is printed only in the report of a failing test, so a test that expects
SOURCE_CHANGED stays silent.
"""

import os
import sys
import traceback

import pytest

from colony_admission import observer

_KEY = pytest.StashKey()
_FD_NAMES = ('fd', 'parent', 'home', 'directory', 'operations')
_VALUE_NAMES = ('before', 'expected', 'result', 'names', 'name', 'path', 'resource', 'key')
_LIMIT = 2000


def _identity(value):
    return observer._identity(value)


def _describe_fd(fd):
    fact = {}
    try:
        fact['link'] = os.readlink('/proc/self/fd/%d' % fd)
    except OSError as error:
        fact['link'] = 'ERROR:' + type(error).__name__
    try:
        fact['fstat'] = _identity(os.fstat(fd))
    except OSError as error:
        fact['fstat'] = 'ERROR:' + type(error).__name__
    return fact


def _value(value):
    # stat results are shown as the compared identity: repr() would drop the nanoseconds.
    if isinstance(value, os.stat_result):
        value = _identity(value)
    text = repr(value)
    return text if len(text) <= _LIMIT else text[:_LIMIT] + '... [%d chars]' % len(text)


def _describe_frame(frame):
    facts = {'where': '%s:%d %s' % (frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)}
    local = frame.f_locals
    for key in _FD_NAMES:
        if type(local.get(key)) is int:
            facts[key] = _describe_fd(local[key])
    for key in _VALUE_NAMES:
        if key in local:
            facts[key] = _value(local[key])
    parent, name = local.get('parent'), local.get('name')
    if type(parent) is int and isinstance(name, str):
        try:
            facts['stat_by_name'] = _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
        except OSError as error:
            facts['stat_by_name'] = 'ERROR:' + type(error).__name__
    for owner in (local.get('self'), local.get('source')):
        inventories = getattr(owner, 'inventories', None)
        if isinstance(inventories, dict):
            # Inventories are keyed by descriptor (observers) or by path (attestation checkout).
            for key in _FD_NAMES + ('path',):
                value = local.get(key)
                if isinstance(value, (int, str)) and value in inventories:
                    facts['recorded_inventory[%s]' % key] = _value(inventories[value])
    return facts


@pytest.fixture(autouse=True)
def _source_changed_diagnostics(request, monkeypatch):
    records = request.node.stash.setdefault(_KEY, [])
    real = observer._Blocked.__init__

    def init(self, *args):
        try:
            if args and args[0] == 'SOURCE_CHANGED':
                frame, frames = sys._getframe(1), []
                while frame is not None and len(frames) < 4:
                    if frame.f_code.co_name != '_need':
                        frames.append(_describe_frame(frame))
                    frame = frame.f_back
                records.append({'frames': frames, 'stack': ''.join(traceback.format_stack(limit=8)[:-1])})
        except Exception as error:  # diagnostics never change the refusal
            records.append({'diagnostic_error': repr(error)})
        real(self, *args)

    monkeypatch.setattr(observer._Blocked, '__init__', init)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    records = item.stash.get(_KEY, None)
    if report.failed and records:
        lines = []
        for index, record in enumerate(records, 1):
            # Facts are read after the failed comparison; only frame 0 is the refusing check,
            # outer frames may show unrelated or stale loop variables.
            lines.append('--- SOURCE_CHANGED #%d' % index)
            for depth, frame in enumerate(record.get('frames', ())):
                lines.append('  [frame %d%s]' % (depth, ', refusing check' if depth == 0 else ', caller'))
                lines.extend('  %s: %s' % (k, v) for k, v in frame.items())
                lines.append('')
            lines.append(record.get('stack', record.get('diagnostic_error', '')))
        report.sections.append(('SOURCE_CHANGED diagnostics', '\n'.join(lines)))
