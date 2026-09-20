# CI-SCOPE-01 — Maintained Corpus Contract

## Purpose

CI-SCOPE-01 defines which test population the repository's general CI
workflows are allowed to collect.

The objective is to prevent historical/out-of-maintenance test entrypoints from
making otherwise healthy maintained-suite evidence red or from being silently
presented as certified.

## Maintained correctness corpus

The maintained correctness population is:

`tests/`

The canonical correctness gate remains owned by `.github/workflows/ci.yml`.

Resource-sensitive tests marked `performance` or `slow` remain owned by the
dedicated long-run performance gate and are not part of the publication
coverage workflows.

## Coverage workflows

The following publication workflows must invoke pytest with an explicit
`tests/` positional path:

- `.github/workflows/coverage.yml`
- `.github/workflows/codecov.yml`
- `.github/workflows/coveralls.yml`

They may measure `--cov=.`, but pytest collection itself must remain rooted in
`tests/`.

A bare repository-root invocation such as:

`pytest --cov=.`

is forbidden because it may collect historical tests outside the maintained
corpus and make the coverage transport workflow claim a broader certification
than actually intended.

## Panels workflow

`.github/workflows/test-panels.yml` must:

1. run the maintained `tests/` corpus;
2. execute the historical root E2E entrypoint
   `test_panels_with_report.py` only if that file is actually versioned;
3. record the entrypoint as unavailable when it is absent instead of failing
   the maintained-suite certification.

The workflow must never manufacture or silently substitute a different E2E
entrypoint.

## Separation of evidence

Coverage publication, maintained test correctness, long-run/performance
evidence and optional panel E2E evidence are distinct signals.

A green coverage upload does not certify an unmaintained historical test tree.
An absent optional panel E2E script does not invalidate the maintained
`tests/` corpus.

## Runtime boundary

CI-SCOPE-01 is repository CI governance only.

It does not modify or authorize:

- PAPER/PPL lifecycle;
- F00 epoch, T0, configuration or capital;
- signal/strategy/risk/sizing/execution;
- VPS deployment;
- Watchdog;
- TESTNET/LIVE.

Active F00 remains pinned independently of GitHub `main`.
