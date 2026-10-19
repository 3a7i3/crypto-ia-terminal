# Order history and descriptive statistics — 2026-10-19

## Question and baseline

Can the operator inspect all captured PPL lifecycles and reproducible closed-order statistics without changing the active experiment?

Verified GitHub main: d7ca4f106a94f56be35116e5a18d80a4bf302343. #286 remains OPEN/ACTIVE. Runtime checkpoint during this mission: GET burn-in200/FRESH, sequence353,177lifecycles (175CLOSED,2OPEN,0UNRESOLVED). The API already includes all177history rows; the event center separately caps its event projection at100. Source code already has a BurnInStatusView history, so no duplicate ledger or reconstruction is needed.

Confirmed cause: presentation navigation, lack of filters/pagination and lack of published descriptive statistics. Research Lab503 remains a separate missing-publication problem. Old FIN/PPL accounting products cannot be represented as reconciled to the live lifecycle population.

## Change and reuse

Reuse validated BurnInStatusSnapshotReader, canonical lifecycle_history, existing mobile/desktop cards, source boundaries,20second frontend polling and the separately deployed presentation bridge. Add filters and20row pagination in the existing Burn-in view; expose its navigation as Orders & Burn-in. Add GET-only /api/operator/v1/burn-in/statistics over the same validated presentation artifact. No raw ledger reads, new writer, database, timer or runtime import is introduced.

The UI may format/filter but does not derive financial metrics. It rejects statistics from another epoch/config/stream/sequence. A publisher rotation between requests can temporarily yield unavailable statistics; no mixed-boundary fallback is allowed.

## Metric contract

Population is every CLOSED lifecycle in the validated captured epoch; OPEN and UNRESOLVED remain explicitly excluded. Validate all three status subcounts against history before aggregating. Net and gross PnL and fees preserve PPL fields; these are descriptive PPL results, not FIN certification. Decimal sums use sufficient precision for all finite decimal input renderings; division has40significant digits. This does not restore precision already lost in original binary floats.

Wins have netPnL>0, losses<0, breakeven=0. Winrate=100*wins/allclosed, including breakeven in denominator. Profitfactor=sumpositive/netabsolute sumnegative; absent loss denominator means null, never infinity. Averagegain and averageloss use their respective subsets; mean net result uses allclosed. Fees include entry+exit fees for closed lifecycles only. No closures means all metrics null. No annualized Sharpe, risk/rewardR, equity drawdown, ROI or strategy ranking is inferred from this population.

## Runtime and rollback

Source-only until a reviewed SHA and CI are accepted. Deploy only a separate presentation release; preserve the old API/frontend release and the existing publisher timer. The frozen Advisor checkout, epoch/config/strategies/risk/sizing/PPL/FIN and secrets remain untouched. Rollback restores only API/frontend presentation references. Source review and HTTP proof do not establish mobile render proof.

## Acceptance

All history remains accessible across pagination; filters reset to first page and cannot create missing results. Empty filter result differs from unavailable data. IDs and gross/net/fees are visible. Statistics fail closed on missing/invalid artifacts, inconsistent population, wrong source boundary and invalid numeric domains. Targeted Python/API and frontend tests, full frontend suite, runtime node tests, build, Ruff gate and independent review precede publication.

## Remaining ordered work

1. Audit and reuse: completed within this bounded history scope.
2. Plan: this contract.
3. History: implemented, pending publication proof.
4. Statistics: implemented, pending publication proof.
5. Deployment: separate reviewed release with rollback, then mobile proof.
6. P12/supervision/Research: inspect configured producer paths and actual admitted artifacts; do not fabricate publications, substitute synthetic research or run replay/diagnostics to populate UI. Missing Research admission is a valid unresolved gate.
7. SentinelJ02: resume only after presentation publication verification; isolated read-only feed server outside GovernanceTower, retain J01journal and address redaction evolution/write-latency findings with their own tests. No governor authority, agent execution, autonomous merge/deploy or production agent service is implied.
