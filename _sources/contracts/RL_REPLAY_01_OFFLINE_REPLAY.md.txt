# RL-REPLAY-01 — Deterministic Offline PAPER Replay Contract

Status: SOURCE CONTRACT V1 / implementation in progress

Parent: #237
Governance: #148
Mission: #239
Depends on: #238 / PR #243

Certified upstream implementation:

`RL_DATA_01_SOURCE_CERTIFIED`

Stack base:

`8ad566de7521402c34a240b14fa9a036893c5ca3`

Certified F00 Research input:

- dataset_id:
  `4ea633a6a4e2ee0bc01a6fe855526d7c42451883ec0b6f3914cf21ea8e91cc8b`
- source_boundary_id:
  `2e6b478cd0cead58c1bcf25c168254b0a63daaa2722c6c108613eb81e283812e`
- PPL SHA-256:
  `50220fdfd4a75d219795db518d77ab6c6574883eb74a6a8db9e26a6d8cf729b2`
- DecisionPacket canonical subset SHA-256:
  `cab875c1a7313c028351edd42410f2e780ecb33e59f3c4e583d566ea8413c170`
- DecisionIdentity canonical subset SHA-256:
  `98aab51a987c49c0f5cf6bd230de98363313bffed8becf2d861248d3579608c9`

---

## 1. Mission

RL-REPLAY-01 creates the canonical Research-side replay boundary over immutable
RL-DATA datasets.

The direction is strictly:

`IMMUTABLE PAPER EXPORT → OFFLINE RESEARCH REPLAY → RESEARCH RESULT`

Never:

`RESEARCH REPLAY → ACTIVE PAPER/PPL MUTATION`

The replay engine is non-authoritative. It reconstructs and derives from
certified facts; it does not create new PAPER facts.

---

## 2. Scientific worlds

RL-REPLAY-01 distinguishes three output classes.

### 2.1 FACTUAL_BASELINE

A deterministic re-projection of facts already present in the immutable dataset.

It may:

- validate the dataset;
- decode PPL events;
- replay the exact lifecycle;
- derive quantities that the certified PPL contract already defines from exact
  stored facts;
- compute Research metrics over that exact population.

It may not:

- regenerate signals;
- invent fills;
- choose a different trade population;
- reinterpret missing evidence as zero.

### 2.2 RESEARCH_DERIVATIVE

A metric or attribution computed from the factual baseline.

Examples:

- N closed trades;
- win rate over closed trades;
- Profit Factor over closed-trade net PnL;
- expectancy over closed-trade net PnL;
- close-to-close realized-equity drawdown.

These are Research outputs, not PAPER authority.

### 2.3 COUNTERFACTUAL

A simulated alternate-world result.

Every counterfactual must:

- declare its method;
- declare its evidence requirements;
- use a distinct candidate/config identity;
- be labelled COUNTERFACTUAL;
- never be presented as observed PAPER fact.

If required evidence is absent, the engine must fail closed with an explicit
status. It must not improvise an alternate world.

---

## 3. Certified RL-DATA v1 evidence boundary

RL-DATA v1 contains:

- authoritative PPL event stream;
- F00 experiment manifest;
- F00 experiment configuration freeze;
- exact F00 DecisionPacket subset;
- exact F00 DecisionIdentity subset.

RL-DATA v1 does not contain a complete certified:

- OHLCV trajectory;
- tick/trade/order-book market trajectory;
- DIP decision graph/store;
- F00-bound Regret population;
- F00-bound RejectionStore population;
- F00-bound AdmissionLedger population;
- persisted FIN event stream;
- valuation/mark-price time series.

Therefore a general strategy/market counterfactual is not reconstructible from
the certified dataset alone.

Missing evidence is not permission to synthesize evidence.

---

## 4. Canonical factual replay kernel

The canonical lifecycle replay kernel is:

- `paper_trading.ledger_events.LedgerEvent`;
- `paper_trading.paper_portfolio_ledger.project()`.

These surfaces are accepted because they are:

- deterministic;
- side-effect free;
- filesystem independent;
- network independent;
- one-epoch fail-closed;
- strict about event ordering, duplicates and illegal transitions;
- explicit about unresolved positions.

The Research layer owns strict dataset decoding and validation around this pure
kernel.

RL-REPLAY must not instantiate a durable PAPER store to replay a Research
dataset.

---

## 5. Existing replay surfaces classification

### REUSABLE

- PPL immutable event model;
- PPL pure `project()` replay.

### ADAPTER_REQUIRED

- FIN `adapt_ppl_stream()` and `project_financial_ledger()`:
  deterministic, but only when an explicit certified `FinancialContext` is
  supplied;
- BT-00 `src.backtest.engine.BacktestEngine`:
  useful no-lookahead lifecycle reference, but it requires market candles and
  strategy execution inputs absent from RL-DATA v1 and contains wall-clock
  metadata;
- `market_data.replay_engine.ReplayEngine`:
  useful only for a future separately-certified Market Observatory dataset;
- `BacktestLab`:
  useful research reference, but simplified/hard-coded and not a canonical
  replay of this PAPER population.

### FORBIDDEN AS CANONICAL RL-REPLAY V1 INPUT/ENGINE

- DIP DecisionReplayEngine;
- DIP CounterfactualEngine;
- legacy `scripts/counterfactual_replay.py`;
- legacy `TradeReplaySystem`.

Reasons include one or more of:

- mutable live stores;
- missing F00 binding;
- absent certified source population;
- wall-clock/UUID identities;
- heuristic joins;
- fabricated/approximate PnL impact;
- missing-value-to-zero behavior.

---

## 6. Dataset validation before replay

A factual replay must validate at minimum:

1. dataset root exists and is a directory;
2. `manifest.json` is valid strict JSON;
3. dataset directory identity equals manifest `dataset_id`;
4. `source_boundary_id` is present;
5. derivation is `PAPER_EXPORT`;
6. source domain is `PAPER`;
7. source authority is `PPL_AUTHORITY`;
8. PPL component status is COMPLETE;
9. authoritative PPL file digest equals manifest digest;
10. authoritative manifest/config digests equal manifest component digests;
11. optional included component digests equal their declared canonical digests;
12. no required component is silently missing;
13. PPL stream parses with no malformed line, duplicate key or non-finite JSON;
14. decoded event count equals declared count;
15. replay validates one exact epoch and contiguous sequence.

Validation failures abort the run before any result publication.

---

## 7. Deterministic Research run identity

One replay run has two identities:

1. immutable source dataset identity;
2. deterministic Research run identity.

The canonical `research_run_identity` document contains:

- replay identity schema version;
- run_kind;
- dataset_id;
- source_boundary_id;
- paper_epoch_id;
- Research replay engine code SHA;
- replay method identifier/version;
- deterministic replay config hash;
- exact population selection;
- source experiment provenance identities needed by the method;
- candidate_config_hash when applicable;
- counterfactual-spec digest when applicable.

Canonical serialization:

- UTF-8 JSON;
- `sort_keys=true`;
- `separators=(",", ":")`;
- `allow_nan=false`;
- SHA-256 over canonical bytes.

Then:

`research_run_id = SHA256(canonical research_run_identity)`

The following must not participate:

- execution timestamp;
- elapsed runtime;
- hostname;
- PID;
- absolute source path;
- absolute output path;
- file mtime;
- terminal/UI metadata.

Required invariant:

same dataset + same replay code + same replay configuration + same population +
same method ⇒ same research_run_id.

---

## 8. Replay configuration identity

The replay configuration must itself be deterministic.

At minimum it identifies:

- replay schema version;
- replay method;
- metric semantic version;
- population policy;
- drawdown definition;
- financial interpretation mode;
- counterfactual mode;
- candidate configuration identity when applicable.

`replay_config_hash` is SHA-256 over canonical JSON.

No runtime environment default may silently alter replay semantics.

---

## 9. Factual lifecycle result

For every trade lifecycle, the baseline result may expose:

- trade_id;
- symbol;
- side;
- OPEN event_id;
- OPEN sequence;
- OPEN timestamp;
- decision_id from OPEN;
- principal;
- entry_price;
- entry_fee;
- schema-v2 replay terms when present;
- resolution status;
- CLOSE or UNRESOLVED event identity when present;
- resolution sequence/timestamp;
- exit_price and exit_fee when closed;
- unresolved reason when unresolved;
- derived gross PnL when closed;
- derived net realized PnL when closed.

No close, price, fee or PnL may be inferred for an unresolved lifecycle.

---

## 10. Terminal factual state

Required terminal fields:

- paper_epoch_id;
- initial_virtual_capital;
- source_event_count;
- last_source_sequence;
- available_cash;
- reserved_principal;
- unresolved_capital;
- realized_pnl;
- fees_paid;
- open_position_count;
- closed_trade_count;
- unresolved_position_count.

For the certified F00 dataset, the replay must reconcile with the already
certified PPL terminal state before source certification can be claimed.

---

## 11. Metric semantics

All metrics here are Research derivatives and must carry provenance.

### 11.1 Population

Unless explicitly stated otherwise, performance metrics operate on
`POSITION_CLOSED` lifecycles only.

UNRESOLVED is not a zero-PnL closed trade.

### 11.2 N

`N = number of closed trade lifecycles`.

### 11.3 Win Rate

`WR = count(net_realized_pnl > 0) / N`.

A zero-PnL trade is not a win.

If `N=0`, status is NOT_AVAILABLE.

### 11.4 Profit Factor

`PF = sum(positive net_realized_pnl) / abs(sum(negative net_realized_pnl))`.

Rules:

- N=0 ⇒ NOT_AVAILABLE;
- no losses + at least one win ⇒ POSITIVE_INFINITY status;
- no wins + losses ⇒ 0 is a valid numeric PF;
- non-finite JSON numbers are forbidden.

Infinity must be represented by an explicit status/value model rather than raw
JSON Infinity.

### 11.5 Expectancy

`expectancy_usd = sum(net_realized_pnl) / N`.

N=0 ⇒ NOT_AVAILABLE.

### 11.6 Drawdown

RL-DATA v1 contains no certified mark-price trajectory.

Therefore V1 must not claim general mark-to-market `MaxDD`.

Allowed V1 metric:

`realized_close_to_close_max_drawdown`

computed from:

initial capital + cumulative closed-trade net realized PnL in source resolution
order.

Its scope must be visible in field name and manifest.

### 11.7 Sharpe

Sharpe is not a required RL-REPLAY v1 factual metric.

It belongs in #248 unless:

- return population;
- observation frequency;
- annualization convention;
- risk-free-rate assumption;
- missing-value treatment

are all explicitly versioned and provenance-bound.

---

## 12. Counterfactual capability matrix

### SUPPORTED NOW

- deterministic factual PPL replay;
- deterministic re-projection of the same factual lifecycle;
- descriptive attribution/filtering that makes no alternate-execution claim.

### ADAPTER_REQUIRED

- deterministic FIN interpretation with explicit certified FinancialContext;
- arithmetic fee-only scenario over observed executions, only if the scenario
  cannot change selection/execution/lifecycle and is labelled COUNTERFACTUAL.

### NOT AVAILABLE FROM RL-DATA V1

- alternate signal generation;
- alternate entry timing;
- alternate exit timing;
- alternate TP/SL/timeout path;
- alternate market-regime path;
- alternate sizing that changes later capital/admission;
- max-position alternate-world PnL;
- rejected-trade opportunity PnL;
- gate-removal PnL;
- DIP graph counterfactual;
- market-impact/slippage counterfactual requiring unseen market observations.

Requests for these capabilities must return an explicit evidence limitation.

---

## 13. Research result manifest

Every published run contains at minimum:

- result schema version;
- research_run_id;
- run_kind;
- run status;
- dataset_id;
- source_boundary_id;
- paper_epoch_id;
- Research code SHA;
- replay_config_hash;
- replay method/version;
- population definition;
- source code/config identities;
- candidate_config_hash when applicable;
- derivation;
- terminal state;
- metric values + semantic/status metadata;
- output component SHA-256 digests;
- explicit evidence limitations;
- generated_at_utc as non-identity provenance.

---

## 14. Target output layout

Logical V1 layout:

```
research_replay/
  runs/
    <research_run_id>/
      manifest.json
      lifecycle.jsonl
      terminal_state.json
      metrics.json
```

The implementation package lives separately from output storage.

Output publication is immutable:

- no overwrite of an existing different run;
- repeated same run identity with identical bytes is a deterministic replay
  proof, not a mutable update.

---

## 15. Runtime/import boundary

Canonical RL-REPLAY source must not import or invoke:

- `paper_trading.durable_event_store.DurableEventStore`;
- `paper_trading.ppl_authority_runtime`;
- Advisor loop/runtime orchestration;
- MexcSimulator mutation paths;
- live execution engine/exchange adapters;
- systemd/service control;
- DIPStore;
- Telegram notifiers;
- HTTP/WebSocket clients.

No module import may:

- create a PAPER lock;
- initialize a live store;
- write a database;
- start a thread;
- inspect process environment to change scientific semantics;
- touch network/runtime services.

---

## 16. Fail-closed doctrine

RL-REPLAY must fail closed on:

- dataset ID mismatch;
- source-boundary mismatch;
- component digest mismatch;
- malformed JSON;
- duplicate JSON keys;
- NaN/Infinity;
- missing required component;
- PPL epoch mismatch;
- PPL sequence gap/regression;
- duplicate event ID;
- illegal lifecycle transition;
- missing OPEN for CLOSE;
- ambiguous trade identity;
- unsupported replay schema;
- attempted unsupported counterfactual;
- attempted result overwrite with different bytes.

---

## 17. Test requirements

Before source certification, isolated tests must prove at minimum:

1. valid RL-DATA fixture loads;
2. corrupted component digest is rejected;
3. malformed JSON is rejected;
4. duplicate JSON keys are rejected;
5. non-finite values are rejected;
6. factual PPL replay is deterministic;
7. event order/lifecycle corruption fails closed;
8. repeated identical run yields same research_run_id;
9. changed dataset changes research_run_id;
10. changed replay config changes research_run_id;
11. generated_at/path/hostname do not change research_run_id;
12. terminal PPL state reconciles;
13. lifecycle outputs are deterministic;
14. PF/WR/expectancy semantics preserve NOT_AVAILABLE;
15. unresolved lifecycle is never counted as zero-PnL close;
16. drawdown is explicitly close-to-close realized drawdown;
17. unsupported market/strategy counterfactual fails closed;
18. no forbidden runtime imports;
19. no source dataset mutation;
20. immutable result publication/no overwrite.

Repository-wide CI follows isolated proof.

---

## 18. Source-only boundary

This mission does not authorize:

- merge of PR #243;
- deployment to the active Advisor runtime;
- PPL/PAPER mutation;
- new epoch;
- burn-in;
- Watchdog activation;
- TESTNET/LIVE;
- exchange writes;
- FIN-03;
- strategy/risk/sizing production changes.

---

## 19. Target verdict

After implementation, isolated tests, deterministic real-dataset replay proof,
source non-perturbation proof and repository CI, the target verdict is:

`RL_REPLAY_01_SOURCE_CERTIFIED`
