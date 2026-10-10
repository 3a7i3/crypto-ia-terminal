# PAPER-STRESS-DATA-ELIGIBILITY-01 — D0/D1 scientific source contract

**Mission:** [#404](https://github.com/3a7i3/crypto-ia-terminal/issues/404), parent [#401](https://github.com/3a7i3/crypto-ia-terminal/issues/401).
**Baseline read:** `main@2015a88f10c31e3379b569f864696d62c282b0f0` (PR #403).
**Status:** `SOURCE_DESIGN_ONLY / D0_BYTES_NOT_VERIFIED / D1_CONTRACT_PROPOSED / COUNTERFACTUAL_ELIGIBILITY_NOT_PROVEN`.
**Authority:** NONE. This document is NOT a runtime configuration, activation request, final dataset designation or certification of any live data.

## 1. Strict evidence boundary

- **SOURCE_CAPABILITY**: implementation exists in source and is covered by source tests.
- **HISTORICAL_PROOF**: an earlier governed checkpoint records proof with an explicit scope and timestamp.
- **CURRENT_BYTES_VERIFIED**: a particular immutable Research dataset was actually opened, all bytes/identities re-hashed, and `research_replay.validate_dataset` performed on it in an isolated read-only context.
- **FACTUAL_REPLAY_ELIGIBLE**: a successfully validated dataset can replay its actually observed PPL facts at one boundary.
- **DECISION_POPULATION_ELIGIBLE**: all signal/decision/admission/rejection candidates for a declared interval have epoch-bound causal provenance and reconciled coverage.
- **MARKET_PATH_ELIGIBLE**: causal price/quote/mark/depth paths for the same population and horizons have provable clock alignment and missing/stale policy.
- **COUNTERFACTUAL_PERFORMANCE_ELIGIBLE**: the preceding gates plus an independently reviewed execution/portfolio simulation and statistical/OOS plan pass.

Do not promote one level into the next. `UNKNOWN != ZERO`, `UNRESOLVED != CLOSED`, `SOURCE_PROOF != RUNTIME_PROOF`, `COUNTERFACTUAL != OBSERVED`.

## 2. D0 — historical Research dataset register (no bytes accessed by #404)

| Dataset / input | Historical identifier | Original evidence | Current conclusion |
|---|---|---|---|
| O4 core immutable prefix, 63 PPL events, 32 OPEN, 30 CLOSE | `fdfadabe468a0eaa4b2854e25fa7ccf746ee918b2c9bf7024c7f9fa5a9a5f110` | [#282 O4 created](https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-5923759574), [O4 certified](https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-5923779193) | `HISTORICAL_PROOF`; no fresh bytes/hash verification |
| O6-B enriched 32 OPEN DecisionPackets + 32 DecisionIdentity records | `410955659523d575b14445eebe7aad5525f73152c24e76f14294a015e383c768` | [#282 O6-B/O6-C](https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-5924128455) | `HISTORICAL_PROOF`; covers OPEN only, not all rejected opportunities |
| Shared O4/O6-B authoritative source boundary | `d60d1b73e48d2ff567e62469b96df0799c9711ffc90bd3f24697f17b5d6ac78e` | #282 O4/O6-B | Identity historical, not a live or final boundary |
| O4 original Research export root | `/home/mathieu/rl_burnin_exports/o4-prefix-20261001T025055Z` | #282 O4 created | **Provenance-only path. Do not automatically access/copy/open in source tools.** |
| PAPER-STRESS #403 analytic proof | `input_class=NO_DATASET` | `docs/research/paper_stress_401/source_manifest.json` | 648 analytic risk calculations, **0 independent market observations** |

A valid O4 dataset is expected under `<O4 output root>/datasets/<dataset_id>` from the RL-DATA exporter contract; this is an expected layout, **not a filesystem observation**. O6-B storage location is not established here.
Device/Research storage access in this mission: `NOT_AVAILABLE`. Consequently `CURRENT_BYTES_VERIFIED=false` for both datasets.

## 3. D0 admission checklist (for an explicitly authorized immutable Research copy only)

1. Record source and custody: research root outside PAPER/production, owner/authorization, extraction date, boundary/event-window coverage, immutable provenance and **actual dataset path**. Never infer a path from an ID alone.
2. Read the dataset **read-only** in an isolated Research environment. No `systemctl`, git operations in the production checkout, producer activation, live PPL store opening, credential or exchange access.
3. Require manifest `dataset_id`, `source_boundary_id`, `paper_epoch_id`, source code/config identity and exact component declarations. Verify canonical manifest/boundary identities and **recompute hashes from bytes**, not names/claims.
4. Execute `research_replay.factual.validate_dataset` on the copy; verify PPL sequence, epoch manifest/config binding, component digests, zero duplicates, OPEN/CLOSED/UNRESOLVED semantics, no silent unresolved-as-zero.
5. For two related captures, verify same source boundary from independently validated manifests. Their different dataset IDs are expected when evidence components differ.
6. Compare to #282 historical claims as a cross-check without calling them current runtime facts. Record elapsed time and full tool/code SHA of each re-validation.
7. If a dataset, permission, fingerprint or component is missing: output `BLOCKED` or `NOT_VERIFIED` with reason, never fabricate `PASS`.

## 4. D1 — proposed complete pre-admission population contract (NEW DESIGN, not existing schema)

For each future prospective candidate within an explicitly bounded epoch/window, collect **at source**:

| Group | Required conceptual fields | Intended invariant |
|---|---|---|
| Identity | `paper_epoch_id`, `decision_id`, `trace_id`, `signal_id` (if emitted), source shard/line hash, source/config/policy version | No ambiguous cross-epoch or many-to-many joins; document missing native IDs rather than synthesizing them |
| Causal clock | market-event exchange timestamp, capture timestamp, decision timestamp, admission attempt/outcome timestamp, PPL event timestamp when relevant, clock basis/uncertainty | Ordered causal trace; late/duplicate/out-of-window events are explicit |
| Market candidate | symbol, exchange, side, strategy ID/version, timeframe, regime, score and gates, proposed notional, eligibility reason | Record all evaluated opportunities, not only filled positions |
| Decision/gates | packet status, gate sequence, complete blocker/rejection reasons and order, policy/config identity | No first-blocker substitution for all causes; reject != hypothetical fill |
| Admission | `attempt_id`, `ADMISSION_ATTEMPT`, `ADMISSION_OUTCOME`, write result, rejection code, corresponding decision/trace, event provenance | Zero-or-one outcomes per attempt, duplicate/orphan/unpaired statuses explicit; idempotency must be proven |
| Portfolio before attempt | prior PPL sequence/digest, free cash, reserved principal, open slots, reserved/notional risk, admission level/ceiling | Financial causality: hypothetical cap changes affect subsequent decisions and capacity |
| Result | PPL `trade_id` for actual OPEN if any, OPEN event sequence/time; CLOSE/UNRESOLVED recorded separately | PPL remains authoritative only for actual execution; never produce a PPL event from a rejected signal |
| Data scope | expected number of decision cycles/symbols/time windows, source counters/offsets/gaps, clock and dataset boundaries | Completeness denominator must be measured independently, not inferred from available rows |

The table is a **contract proposal**, not a claim that these fields are present in current `DecisionPackets` or `admission_ledger.jsonl`. Existing `paper_trading/admission_ledger.py` provides ATTEMPT/OUTCOME joined by `attempt_id`, but lacks an independently guaranteed epoch field in its v1 record schema. Existing `research_data/paper_exporter.py` records declared status of `admission_ledger`/`rejection_store` without materializing their full rows; its certified optional materialization selects DecisionPackets/identities linked to **PPL OPEN** events only.

### D1 required joins and failure policies

1. Bind all raw shards to **one** externally corroborated epoch + source/config/boundary identity before joining; no inference from filenames or wall clock alone.
2. Partition by epoch and a closed, explicitly documented observation window. Require an independent expected-population denominator from governed cycle/decision producer evidence, not simply the count of observed records.
3. Deduplicate only when the original event identity and raw fingerprints agree. Conflicting duplicate ID/content -> `BLOCKED_CONFLICT`; missing links -> `UNKNOWN`.
4. Join DecisionPacket/DecisionIdentity via documented `decision_id` + `trace_id`; join admission attempt/outcome via original `attempt_id`; join actual PPL OPEN via authoritative decision/trade linkage. When any link is absent, report unmatched counts and reject coverage certification.
5. Preserve every rejection and its reason, including notional/slot/risk failures. A rejected opportunity has `COUNTERFACTUAL_CANDIDATE` status, **not** observed fill/PnL.
6. Cross-check OPEN counts against PPL projected OPEN facts, all attempt/outcome counts and source cycle counts for the same bounded window; flag logging lag, gaps, late events, ambiguous clocks and unmatched outcome.
7. Avoid leakage: candidate features and regime labels must be available **at the decision time**. Any future observations may only be used as simulated path outcomes, never as decision inputs.
8. Do not assert that the signal tape is exogenous to portfolio state. If cap/sizing changes downstream signal generation, static replay is invalid unless that independence is separately proved.
9. Preserve per-symbol/strategy/time coverage, stratify by regime/horizon and count independent days/clusters separately from number of raw signals.
10. Do not export raw secrets, PII, auth headers or private keys. Require explicit permissions, minimal necessary fields, restrictive read-only Research custody, hashed manifest and no Research -> same-epoch feedback.

## 5. Why D1 alone is insufficient for A/B/C

- **D2 price/market tape:** need synchronized, provenance-bound executable quotes/marks, multi-symbol trajectories through each alternative holding horizon, book/spread/depth and their missing/stale intervals. The presence of `market_data/replay_engine.py` proves parsing capability, **not** that such data exist or are aligned.
- **D3 execution/portfolio model:** deterministic priority of simultaneous candidates, latency/fills/precision, capital reservations, TP/SL/timeouts/recovery and gap behavior, no lookahead, and independent validation against factual PPL baseline.
- **D4 reproducibility:** exact immutable datasets, source/config/model hashes, coverage registry, counterfactual labels and fail-closed validator.
- **D5 statistics:** preregistered paired-day/cluster analysis, independent sample size, OOS embargo/purge and power.
- **D6 gate:** external review of D0-D5, source CI, financial and causal audit. No activation without distinct operator gate after #282 finalization.

The current `src/backtest/engine.py` may liquidate surviving positions at the final dataset bar. Such forced closure must **not** be passed off as a genuine PAPER lifecycle or terminal PPL proof.

## 6. Current decision and protected runtime

```text
D0_HISTORICAL_LOCATORS = IDENTIFIED
D0_DATASET_BYTES_REVALIDATED = NO
D1_CAUSAL_POPULATION_CONTRACT = PROPOSED_SOURCE_ONLY
D1_PRODUCTION_DATA_COMPLETENESS = NOT_PROVEN
D2_MARKET_PATHS = NOT_PROVEN
D3_COUNTERFACTUAL_PORTFOLIO_MODEL = NOT_VALIDATED
A_B_C_FINANCIAL_PERFORMANCE_ELIGIBILITY = INSUFFICIENT_EVIDENCE
PAPER_STRESS_GO = NOT_AUTHORIZED
ACTIVE_BURN_IN_IMMUTABILITY_GUARD_286 = ACTIVE
```

**No operations on Advisor, PPL, FIN, frozen runtime checkout, process, systemd, admission, risk/sizing, TESTNET/LIVE, exchange, or active epoch are authorized. This source-only document is not an export request.**
