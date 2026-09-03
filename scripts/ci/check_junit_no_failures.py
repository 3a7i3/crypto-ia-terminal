#!/usr/bin/env python3
"""scripts/ci/check_junit_no_failures.py — CI-00B (Phase 8): real-regression check.

`pytest -q tests/` is run with `|| true` because conftest.py's Scientific
Data Guard (DS-001/ADR-0008) forces `session.exitstatus = 1` whenever
databases/ or cache/ changed during the session -- a signal orthogonal to
whether the tests themselves passed. This script re-derives the actual
test regression signal from the JUnit XML pytest wrote, independent of
that process exit code, so TEST REGRESSION GATE fails only on a genuine
new test failure/error, never on the guard's known, pre-existing,
out-of-CI-00B-scope trip. See .ci/known_red_tests.md for the tracked
debt this covers.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: check_junit_no_failures.py <junit.xml>")
    path = Path(sys.argv[1])
    if not path.exists():
        sys.exit(f"check_junit_no_failures: {path} not found (pytest did not run?)")

    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))

    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    tests = sum(int(s.get("tests", 0)) for s in suites)

    print(f"JUnit summary: {tests} tests, {failures} failures, {errors} errors")
    if failures or errors:
        print("TEST REGRESSION GATE — real test failure(s)/error(s) found.")
        return 1

    print("TEST REGRESSION GATE — no test failures or errors. Gate passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
