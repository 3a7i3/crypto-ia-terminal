# WEB-DIR-01 / D1 — UX and Product Navigation Contract

**Mission:** WEB-DIR-01 / D1  
**Parent issue:** #288  
**Active roadmap:** #285  
**Burn-in immutability guard:** #286  
**Related UX mission:** #283  
**Related forensic mission:** #287  
**Future agent economy:** #284  
**Baseline source:** `116634be0d3c015cce1cfa58be7da7255414fbfd`  
**Date:** 2026-09-27 UTC  
**Status:** CONTRACT DEFINED — NOT SOURCE CERTIFIED — NOT RUNTIME CERTIFIED

## 1. Purpose

Define the product navigation, page architecture, UI boundaries, data
availability semantics, API needs, tests, and first implementation scope for
three clearly separated surfaces in one canonical application:

- PAPER LIVE;
- DIRECTION;
- RESEARCH.

This document creates no runtime authority and authorizes no deployment.

## 2. Constitutional boundary

The active burn-in remains immutable:

- epoch: `BURN-IN-EPOCH-01-20260926T064144Z`;
- runtime source: `116634be0d3c015cce1cfa58be7da7255414fbfd`;
- config hash:
  `9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`;
- admission: `PB_MAX_POSITIONS=2`;
- scientific T0: `2026-09-27T03:06:03.086973Z`.

This mission MUST NOT:

- modify strategy, signals, calibration, thresholds, risk, or sizing;
- modify PPL or FIN authoritative state;
- modify the epoch, manifest, experiment config, or initial capital;
- restart Advisor or modify production systemd;
- enable Watchdog, FIN-02 runtime, TESTNET, or LIVE;
- write to an exchange;
- apply a Research candidate to the active epoch;
- grant an autonomous agent merge or deployment authority.

The UI is a presentation and governance surface. It never becomes a source of
scientific truth.

## 3. Verified source baseline

Inspection of `main@116634be0d3c015cce1cfa58be7da7255414fbfd`
establishes the following SOURCE facts:

1. The canonical frontend is React 18 + TypeScript + Vite under `frontend/`.
2. `frontend/src/App.tsx` uses local React state for domain and subview
   selection. It does not expose product routes.
3. No routing dependency is declared in `frontend/package.json`.
4. The current domains are Overview, Market Observatory, Paper Science,
   Research Lab, and System / Governance.
5. `frontend/scripts/web01_local_frontend_server.mjs` already serves
   `index.html` as a fallback for non-API frontend paths.
6. The fallback never applies to `/api/*` or `/healthz`.
7. The frontend server permits only GET and HEAD.
8. The Operator API is read-only and exposes existing governed projections.
9. No atomic Direction projection exists today.

These are SOURCE PROOFS. This document makes no new RUNTIME claim.

## 4. Product language

### 4.1 PAPER LIVE

PAPER LIVE means:

> real market data + real machine decisions + PAPER financial execution.

It does not mean:

- fake market data;
- a toy market simulator;
- exchange order execution;
- TESTNET;
- REAL trading.

The existing label `Paper Science` may remain as a scientific subdomain or
supporting label, but the primary product surface is `PAPER LIVE`.

### 4.2 DIRECTION

DIRECTION is a separate owner/governance product surface. It is not:

- a PAPER tab;
- an Overview card;
- a modal;
- a side panel;
- a scientific authority;
- a deployment console.

### 4.3 RESEARCH

RESEARCH is offline/non-authoritative analysis. Its permanent visible marker is:

`RESEARCH NON-AUTORITAIRE`

Allowed flow:

`PAPER -> DATASET -> RESEARCH -> CANDIDATE -> FUTURE EPOCH`

Forbidden flow:

`RESEARCH -> ACTIVE PAPER EPOCH`

## 5. Canonical route architecture

```text
/
└── redirect -> /paper-live

/paper-live
├── /paper-live/overview
├── /paper-live/market
├── /paper-live/portfolio
├── /paper-live/decisions
├── /paper-live/lifecycle
├── /paper-live/finance
└── /paper-live/events

/direction
├── /direction/decisions      [future]
├── /direction/agents         [future]
├── /direction/bounties       [future]
└── /direction/economy        [future]

/research
├── /research/datasets        [future]
├── /research/replay          [future]
├── /research/diagnostics     [future]
├── /research/candidates      [future]
└── /research/arena           [future]
```

### 5.1 Route behavior

- `/` MUST redirect deterministically to `/paper-live`.
- Direct deep links and browser refresh MUST work.
- Browser back/forward navigation MUST work.
- Unknown routes MUST render an explicit safe not-found state or follow an
  explicitly tested deterministic redirect.
- API paths MUST never enter the SPA fallback.
- Route selection MUST NOT alter scientific data or authority.

### 5.2 Cross-surface navigation

From PAPER LIVE:

`[ Ouvrir Direction -> ]`

From DIRECTION:

`[ <- Retour à PAPER LIVE ]`

The return control MUST be:

- visible without opening a menu;
- available on desktop and mobile;
- at least 44 CSS pixels in its interactive dimension;
- keyboard reachable;
- unambiguous;
- present at the top of the Direction surface.

DIRECTION and RESEARCH MUST have distinct visual identities from PAPER LIVE.

## 6. Route and authority matrix

| Route | Shell | Initial view | Existing source | Authority rule |
|---|---|---|---|---|
| `/paper-live` | `PaperLiveShell` | overview | canonical snapshot | presentation only |
| `/paper-live/market` | `PaperLiveShell` | current Market view | market snapshot | observational telemetry |
| `/paper-live/portfolio` | `PaperLiveShell` | current Portfolio view | canonical snapshot | render producer values |
| `/paper-live/decisions` | `PaperLiveShell` | current Decisions view | canonical snapshot | preserve per-field authority |
| `/paper-live/lifecycle` | `PaperLiveShell` | current PPL comparison view | PPL comparison snapshot | observational projection |
| `/paper-live/finance` | `PaperLiveShell` | current FIN view | financial reconciliation | financial observation |
| `/paper-live/events` | `PaperLiveShell` | placeholder | none | NON DÉPLOYÉ |
| `/direction` | `DirectionShell` | `DirectionOverview` | existing GET projections initially | no recomputation, no mutation |
| `/research` | `ResearchShell` | current Research Lab view | Research Lab snapshot | RESEARCH_NON_AUTHORITATIVE |

## 7. Component architecture

### 7.1 `AppRouter`

Responsibilities:

- route matching;
- safe redirect from `/`;
- safe not-found handling;
- shell selection.

Forbidden responsibilities:

- metric calculation;
- state reconciliation;
- direct JSONL/database access;
- exchange access;
- mutation requests.

### 7.2 `PaperLiveShell`

Contains:

- PAPER LIVE identity;
- navigation to Overview, Market, Portfolio, Decisions, Lifecycle, Finance,
  and Events;
- a visible `Ouvrir Direction ->` action;
- the explicit explanation that execution is PAPER.

It reuses existing views rather than copying them.

### 7.3 `DirectionShell`

Contains:

- permanent DIRECTION identity;
- permanent `<- Retour à PAPER LIVE` action;
- owner-oriented layout;
- presentation and governance links only.

It MUST NOT expose a control whose click directly merges, deploys, restarts,
changes an epoch, or mutates PAPER.

### 7.4 `ResearchShell`

Contains:

- permanent `RESEARCH NON-AUTORITAIRE` marker;
- current Research Lab view at the first stage;
- future Research-only navigation.

### 7.5 `DirectionOverview`

Top-level reading order:

1. global state;
2. active experiment / burn-in;
3. operator decisions requiring attention;
4. market summary;
5. Research summary;
6. agents and bounties;
7. AIC economy and real costs;
8. security, debt, and incidents;
9. detailed provenance.

### 7.6 `HonestAvailabilityCard`

Allowed display states include:

- governed producer value;
- `NON DÉPLOYÉ`;
- `NON DISPONIBLE`;
- `UNKNOWN`;
- `UNRESOLVED`;
- `NOT_AVAILABLE`;
- `NOT_APPLICABLE`.

No unavailable state may be rendered as numeric zero.

## 8. Direction level-one design

### 8.1 Global state banner

May show only governed facts such as:

- source/snapshot identity;
- mode;
- freshness;
- runtime evidence status;
- system-health projection.

A synthetic global status MUST NOT be inferred in React. Until a governed
producer defines it, display `INCONNU`.

### 8.2 Active experiment

Priority fields when producer-authored and available:

- epoch;
- OPEN / CLOSED / UNRESOLVED counts;
- population;
- available cash;
- reserved principal;
- realized PnL;
- fees;
- reconciliation status.

PF, WR, expectancy, and maximum drawdown appear only when supplied by a
governed scientific producer with population and evidence status.

### 8.3 Market

May summarize the existing observational projection:

- universe size;
- freshness;
- regime;
- opportunity counts;
- CryptoRadar provenance.

It MUST remain labelled `OBSERVATIONAL_TELEMETRY`.

### 8.4 Research

May summarize:

- dataset_id;
- source_boundary_id;
- paper_epoch_id;
- research run;
- population N;
- evidence status;
- candidate count and states.

It MUST remain visibly non-authoritative.

### 8.5 Operator decision queue

Until a governed producer exists:

`NON DÉPLOYÉ`

No fake decisions or demonstration actions may appear as real data.

### 8.6 Agents, bounties, AIC, and real costs

The product architecture may reserve these cards, but every unavailable block
MUST display `NON DÉPLOYÉ`.

### 8.7 Security, debt, and incidents

Until dedicated governed projections exist, display `NON DÉPLOYÉ`. The
forensic inventory from #287 MUST NOT be silently converted into runtime
truth.

### 8.8 Responsive behavior

At mobile widths:

- cards stack in one column;
- the PAPER return control remains at the top;
- level-one Direction uses no wide horizontal table;
- actions use touch-safe target sizes;
- scientific details move to accordions or secondary pages;
- identity and authority markers remain visible.

## 9. Information available from current APIs

| Endpoint | Currently contractually available |
|---|---|
| `GET /api/operator/v1/snapshot` | snapshot identity, cycle, timestamps, source SHA/evidence, mode, portfolio, decisions, system health, freshness |
| `GET /api/operator/v1/market` | CryptoRadar identity, universe, regime, opportunities, freshness, observational authority |
| `GET /api/operator/v1/ppl-comparison` | epoch, exposed PPL events, position/closed groups, comparison/authority status, freshness |
| `GET /api/operator/v1/financial-reconciliation` | cash, reserved/deployed capital, realized/unrealized PnL status, fees, funding status, lifecycle counts, reconciliation, source/config identities |
| `GET /api/operator/v1/research-lab` | dataset/source boundary/run identities, N, evidence strength, producer metrics, candidates, limitations |

Schema availability does not prove that a current value is populated. The UI
MUST preserve the exact producer status.

## 10. Information that is not deployed

The following have no governed product projection today:

- Agent Registry;
- Bounty Registry;
- operator decision queue;
- proposed-evolution workflow;
- Economy Ledger;
- AIC supply, Treasury, pools, and wallets;
- economy hash-chain state;
- consolidated real costs over 24h/7d/30d;
- unified event center;
- consolidated incidents;
- consolidated security/debt projection;
- Strategy Arena;
- Model Broker.

These blocks display `NON DÉPLOYÉ`.

Scientific metrics whose engine exists but whose evidence is missing use the
producer's exact unavailable status, not `NON DÉPLOYÉ`.

## 11. API contracts

### 11.1 D1–D3

No new endpoint is required to introduce product routes and shells. Existing
GET projections remain unchanged.

### 11.2 Future Direction projection

Before Direction is declared an atomic owner cockpit, define a separate
contract for a possible:

`GET /api/operator/v1/direction`

Minimum rules:

- GET-only;
- versioned schema;
- producer-authored atomic projection;
- generated_at and freshness;
- evidence and provenance per block;
- explicit availability status per block;
- no metric recomputation in React;
- no direct frontend reads of runtime files;
- no PPL writer, exchange client, or secret dependency;
- no mutation method;
- no direct authority to merge, deploy, restart, or accept into an active
  epoch.

This endpoint is outside the D1 PR and requires a separate mission.

## 12. Required tests for implementation phases

### 12.1 Routing

- `/` redirects to `/paper-live`;
- deep-link rendering for `/paper-live`, `/direction`, and `/research`;
- direct refresh works for each product route;
- browser back/forward works;
- PAPER opens Direction;
- Direction returns to PAPER LIVE;
- unknown route behavior is explicit and tested.

### 12.2 Authority and mutation boundary

- Direction and Research issue no mutation request;
- frontend requests remain GET-only;
- no direct JSONL/database/exchange read is introduced;
- Research retains its non-authoritative marker;
- PAPER LIVE never claims exchange execution;
- existing API and health paths never receive SPA fallback.

### 12.3 Semantic truth

- `UNKNOWN != ZERO`;
- `UNRESOLVED != ZERO`;
- `NOT_AVAILABLE != ZERO`;
- future capabilities render `NON DÉPLOYÉ`;
- Direction performs no cross-endpoint scientific recomputation;
- missing governed global health renders `INCONNU`.

### 12.4 Quality

- existing Vitest suite;
- existing cross-stack compatibility tests;
- `npm run build`;
- `npm test`;
- `npm run test:runtime`;
- keyboard and focus tests;
- `aria-current` and landmark labels;
- desktop, tablet, and mobile screenshots;
- before/after visual comparison.

## 13. First PR scope

The D1 PR is documentation-only.

Included:

- this canonical contract;
- route/shell/source/authority matrix;
- Direction level-one design;
- availability rules;
- API requirements;
- test requirements;
- burn-in non-impact proof;
- links to #285, #286, #288, #283, #287, and #284.

Excluded:

- `frontend/src/*`;
- npm dependency changes;
- Operator API changes;
- Python runtime code;
- PPL, FIN, or Research producer code;
- configuration or manifests;
- systemd;
- VPS commands;
- service restart;
- deployment;
- TESTNET/LIVE;
- exchange writes.

## 14. D2 and D3 entry gates

D2 may start only after D1 review confirms:

- routes and redirect policy;
- route library choice;
- safe not-found policy;
- authority and availability vocabulary;
- no-impact boundary.

D3 may start only after D2 proves:

- deep-link and refresh behavior;
- API fallback separation;
- existing-view reuse;
- no mutation path;
- passing navigation tests.

## 15. Non-impact proof for D1

| Protected element | D1 effect |
|---|---|
| runtime source `116634be...` | unchanged |
| active epoch | unchanged |
| config hash | unchanged |
| `PB_MAX_POSITIONS=2` | unchanged |
| PPL authority/ledger | untouched |
| FIN | untouched |
| Advisor process | no command, no restart |
| production systemd | untouched |
| Watchdog | untouched |
| TESTNET/LIVE | untouched |
| exchange | no read/write added |
| Research feedback | no promotion or active-epoch mutation |
| modified source surface | one documentation file only |

## 16. Rollback

Before merge, rollback is branch/PR deletion or PR closure.

After merge, rollback is a documentation-only revert of the contract commit.
No runtime rollback is applicable because D1 changes no executable code,
configuration, service, data, or authority.

## 17. D1 acceptance criteria

D1 may be marked SOURCE CERTIFIED only after:

1. this file is reviewed;
2. PR diff proves documentation-only scope;
3. the base SHA is recorded;
4. no executable/config/runtime file changed;
5. #288 records the PR and verdict;
6. #285 is synchronized;
7. CI status is reported exactly.

Until then, the correct status is:

`WEB_DIR_01_D1_CONTRACT_DEFINED`

The target D1 source verdict is:

`WEB_DIR_01_D1_CONTRACT_SOURCE_CERTIFIED`

There is no D1 runtime verdict because D1 contains no runtime change.
