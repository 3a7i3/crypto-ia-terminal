# Canonical Operator API Contract

Mission O-02W-B · Base SHA `5aecc8859efb7dbeb5ba53177a926abaa43097c` ·
2026-09-06 · Documentation/architecture-only mission (no runtime code
changes, no UI, no API deployment, no Telegram, no VPS).

This document is the authoritative source-inspected contract for a future
read-only "operator API" serving the React cockpit (`frontend/`). It
supersedes no code — it constrains what a future implementation mission
(§21, `MINIMUM_IMPLEMENTATION_MISSION`) is allowed to build. Every claim
below is traceable to a file actually read for this mission; where
something does not exist or is not instrumented, it is stated plainly
(`NOT_EXPOSED`, `CONTRACT_EXISTS` / `RUNTIME_PRODUCER_EXISTS` /
`RUNTIME_EXPOSURE_EXISTS` distinctions per domain).

This mission builds directly on **Mission O-01**
(`docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md`,
`observability/operator/*`) — eleven canonical observation domains, a
shared `DomainSnapshot`/`ObservedValue`/`FreshnessStatus` contract, and a
32-metric registry (`docs/observability/METRIC_DICTIONARY.md`). O-01
ships contracts only, no runtime wiring; the "known gaps" it records
(§10 of that document) are carried forward here verbatim where relevant,
not silently re-solved.

Compliance note (per `CLAUDE.md`): Phase II — Validation Scientifique is
in force; this document is measurement/audit/documentation tooling, not
a new feature, indicator, strategy, or decision rule. It proposes zero
new signal, zero new threshold, zero change to `core/advisor_loop.py`,
and zero VPS/Telegram wiring. The STABILIZATION LAB window
(`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`) is
unaffected: nothing here reads or writes runtime state.

---

## 1. CANONICAL_OPERATOR_ARCHITECTURE

### 1.1 Target architecture

```
AUTHORITATIVE MACHINE SOURCES (process-local objects, JSONL ledgers, JSON packs)
   core/advisor_loop.py (analyze_symbol, DecisionPacket producer, execution authority)
   paper_trading/mexc_simulator.py::MexcSimulator._positions   (in-memory, process-local)
   infra/wallet_sync.py::get_wallet_sync()                     (in-memory singleton, process-local)
   paper_trading/recorder.py -> databases/paper_trades.jsonl   (disk, append-only)
   tools/regret_repository.py -> databases/regret_*.jsonl      (disk)
   observability/rejection_store.py -> databases/*.jsonl       (disk)
   observability/system_snapshot.py::SystemSnapshot            (in-memory + periodic JSON dump)
        |
        v
CANONICAL OBSERVABILITY MODULES (existing, wrapped, not duplicated — O-01)
   observability/operator/domains/*.py  compose_*_snapshot()
        |
        v
CANONICAL OPERATOR SNAPSHOT/PROJECTION  (producer-owned, materialized OUTSIDE
   the advisor process's own address space — this is the NEW layer this
   mission specifies; nothing here is implemented yet)
        |
        v
READ-ONLY OPERATOR API  (separate FastAPI process; GET + optional read-only WS)
        |
        v
REACT COCKPIT  (frontend/)
```

### 1.2 Transport options evaluated

The producer process (`core/advisor_loop.py`, or a small in-process
publisher it owns) and the API process are, by construction (§2), two
separate OS processes. The API process cannot read the producer's Python
heap directly. Options considered, per the brief's bounded list:

| Option | Verdict | Rationale |
|---|---|---|
| **Atomic JSON snapshot file (single file, atomic rename)** | **SELECTED** | Matches the pattern already in production use (`observability/system_snapshot.py` -> `SystemSnapshot` JSON dump, consumed today by `visualization/api/system_snapshot_source.py`). Trivially restart-safe (file persists), trivially reproducible (one file = one point-in-time truth), atomic via write-to-tmp + `os.replace()`, zero new daemon, zero new dependency, low overhead (periodic write, not per-request). |
| Multiple domain snapshot files (one JSON per O-01 domain) | REJECTED (as *sole* mechanism) but compatible as an internal detail | O-01's own domain decomposition (§4) argues for per-domain freshness/composition, but multiple files reintroduces the exact "impossible cross-cycle mixture" risk this contract must prevent (§14, ATOMICITY_CONTRACT) unless every file shares one `snapshot_id`/`cycle` and the API refuses to compose across differing ids. Acceptable *inside* the single-envelope option (§1.3) as a serialization detail, not as the transport itself. |
| Append-only event stream + snapshot | REJECTED for this contract's scope | Real value for DECISION_API history (decision packets are already an event-sourced hash chain, §8) and for TRADE_API history (JSONL ledger already is this). Not needed as the *primary* transport for point-in-time domain state — adds operational complexity (offsets, replay, compaction) with no freshness/atomicity benefit over a snapshot file for state that is naturally "current value," not a stream. The existing JSONL ledgers already give append-only history for trades/decisions; no new bus is required to expose them read-only. |
| Local Unix domain socket (advisor process serves a socket, API process is a client) | REJECTED | Requires the advisor process to run a server loop and accept connections — a scope/coupling increase inside `core/advisor_loop.py`, explicitly forbidden by this mission ("do NOT modify advisor_loop.py"). Also reintroduces liveness coupling: if the advisor process stalls mid-request, the API blocks: the opposite of "low runtime overhead" and "read-only web process independent of producer liveness." |
| Loopback read-only HTTP (advisor process exposes an internal HTTP endpoint, API process proxies it) | REJECTED | Same objection as the socket option — it requires the producer process to run an HTTP server, which is new functional surface inside or beside the trading engine, not a passive observer. It also duplicates the API layer this mission is defining one process too early. |
| Other existing safe mechanism (SQLite / shared file-lock DB) | REJECTED for the *hot* live-state path, ACCEPTABLE unchanged for what already uses it | The existing JSONL ledgers (`paper_trades.jsonl`, `regret_*.jsonl`, `black_box.jsonl`) already are this mechanism for historical/append-only data and should be read as-is (§6). Introducing a new SQLite file for *live* snapshot state would be a new storage technology for no benefit over a JSON file already atomic-rename-capable. |

### 1.3 Selected design

**One canonical JSON snapshot file per producer process, atomically
written (tmp file + `os.replace()`), read-only-mounted by the API
process — the same pattern `observability/system_snapshot.py` already
uses, extended with the O-01 domain envelope and the identity/atomicity
fields defined in §14-§15.** The producer (the advisor-loop process, or a
narrow in-process "operator snapshot writer" it calls once per cycle —
not a new decisional component, purely a serializer) is the only writer.
The API process only ever opens the file read-only, never imports
`MexcSimulator`, `WalletSync`, or `core/advisor_loop.py` (§ PROCESS_
BOUNDARY_VERDICT). Historical/ledger data (trades, decisions, regret
events) continues to be read directly from its existing JSONL files by
the API process — those are already cross-process-safe append-only logs
and do not need to be re-published inside the snapshot.

This satisfies every criterion in the brief:
- **Process isolation** — API process never touches producer memory.
- **Reproducibility** — one file = one immutable point-in-time state; a
  copy of the file plus the referenced ledger offsets fully reproduces
  what the operator saw.
- **Freshness** — `generated_at_utc` + per-domain `freshness` (O-01) let
  the API/cockpit compute staleness without guessing.
- **Atomicity** — `os.replace()` on POSIX is atomic; readers never see a
  half-written file; §14 defines the identity fields that let the API
  detect and refuse a torn cross-cycle read even without OS-level torn
  reads (e.g. a slow NFS mount, not applicable to a local VPS disk but
  documented defensively).
- **Restart safety** — file persists across producer restarts; API
  serves the last-known snapshot with its true (aging) freshness rather
  than fabricating a fresh empty one.
- **Read-only web process** — the API process opens no write handle to
  producer state, ever.
- **Low runtime overhead** — one JSON write per cycle (already the
  `SystemSnapshot` pattern's cost profile), no new network service, no
  new message broker.

No new message bus is introduced. This is a deliberate, evidence-backed
minimality choice per the brief's explicit constraint.

---

## 2. PROCESS_BOUNDARY_MAP

### 2.1 `MexcSimulator` (`paper_trading/mexc_simulator.py`)

Read: `paper_trading/mexc_simulator.py` (constructor, `start()`,
`_restore_positions()`, position dict usage throughout).

- `self._positions: dict[str, MexcPosition]` (line 267) is a **plain
  Python dict on the instance** — pure in-process heap state. There is
  exactly one `MexcSimulator` instance created by the advisor runtime
  process; nothing persists `_positions` to disk as a live structure.
- `_restore_positions()` (called from `start()`) rebuilds an
  *approximation* of open positions from `paper_trades.jsonl` (via
  `paper_trading/recorder.py::get_recorder().trades()`) — but only at
  process start, and only entry-side fields (`entry_price`, `tp_price`,
  `sl_price` computed from fixed 4%/2% assumptions, not the live TP/SL
  the original order actually carried — see `_restore_positions()`
  lines ~410-448). **Current price, unrealized PnL, and live TP/SL are
  never persisted** — they exist only as long as the owning process's
  monitor loop (`_monitor_loop`, `_check_positions()`) keeps ticking
  fresh market prices into the in-memory `MexcPosition` objects.
- **Verdict:** a second process instantiating `MexcSimulator()` fresh
  gets `_positions == {}` until (if ever) it independently reconstructs
  approximate entry-side state from the ledger, and even then it has no
  live market price feed of its own wired in this mission's scope — it
  would show `current_price == entry_price` (stale) or nothing at all.
  **This is exactly the failure mode the mission brief warns about**:
  the second process would present empty/wrong state, not the real
  running machine.

### 2.2 `WalletSync` (`infra/wallet_sync.py`)

Read: `infra/wallet_sync.py` (full file, 264 lines) and
`get_wallet_sync()`.

- `_singleton: Optional[WalletSync]` (line 223) is a **module-level
  global in the Python interpreter of whichever process imports
  `infra.wallet_sync`**. A separate OS process runs a separate Python
  interpreter with its own, independently-`None`-initialized
  `_singleton` — `get_wallet_sync()` in that process constructs its
  *own* `WalletSync()`, never the advisor process's instance. Python
  singletons do not cross `fork`-less process boundaries (no shared
  memory here — this is a plain FastAPI process started independently,
  not a fork of the advisor process).
- **Nuance found on inspection (important, non-obvious):** in **paper
  mode**, `get_balance()` (lines 166-191) is *effectively* cross-process
  safe in practice, because it recomputes `self._base_capital() +
  _read_ledger_pnl()` from disk (`_PAPER_CAPITAL` = `WALLET_PAPER_CAPITAL`
  env var, `_read_ledger_pnl()` re-reads `databases/paper_trades.jsonl`
  from scratch every call) rather than returning cached in-memory state.
  A second process's own fresh `WalletSync(mode="paper")` singleton
  would compute the *same* number, **provided it is told `mode="paper"`**
  — `mode` itself is a constructor parameter, not derived from any
  shared state, so the second process must be independently configured
  with the correct mode (§7, MODE_PROVENANCE_CONTRACT).
- In **live/testnet mode**, `_x` (capital X, set once via `bootstrap()`
  against the real exchange API at startup) and the `_last_value`/
  `_last_fetch_ts` cache (TTL `WALLET_CACHE_TTL_S`, default 30s) **are**
  process-local and not derivable without an independent
  `bootstrap()`/API call from the second process — which would be a
  second, uncoordinated read of the same real exchange account (safe
  read-only, but not a reflection of the running advisor's cached
  value, and doubles exchange API load).
- `_paper_session_pnl0` (session baseline, used only by
  `session_pnl_since_restart()`, explicitly "affichage uniquement" per
  the module's own docstring) is inherently per-process-lifetime and
  **must never be treated as canonical** by a second process; it is a
  display-only convenience counter, not sizing input, and is out of
  scope for any cross-process contract.
- **Verdict:** paper-mode `get_balance()` is derivable by re-implementing
  the same disk read (or, simpler and required by this contract, by
  having the producer materialize the already-computed number into the
  snapshot — see §2.3). Live/testnet-mode balance and the boot-time
  capital `X` are **not** safely re-derivable by a second process and
  **must** be materialized by the producer.

### 2.3 What MUST be materialized by the producer process

| State | Process-local? | Materialization required |
|---|---|---|
| `MexcSimulator._positions` (open paper positions, live current_price/unrealized PnL) | YES — pure heap state, live-price-dependent | YES — producer writes the full open-position list (with current mark price at snapshot time) into the canonical snapshot every cycle. |
| `WalletSync.get_balance()` result (paper mode) | Effectively no (re-derivable from disk), but only if `mode` is externally known | YES anyway, for a single point of truth and to avoid the API re-implementing wallet arithmetic (reuse-before-creation, O-01 principle §6) |
| `WalletSync.get_balance()` result (live/testnet mode), `WalletSync.capital_x` | YES — in-memory cache + one-time bootstrap value | YES — mandatory; no safe re-derivation without an independent, uncoordinated exchange API call |
| `WalletSync.mode` | YES — constructor parameter of the process's own singleton | YES — must be carried in the snapshot as explicit provenance (§7) |
| Realized PnL, closed trade history | NO — already disk-resident (`databases/paper_trades.jsonl`, append-only) | NO — API may read the ledger file directly; producer need not re-publish it, though a denormalized summary in the snapshot is convenient (not required for correctness) |
| `DecisionPacket` current/latest state per symbol | YES — held by `core/decision_packet.py`'s in-memory state machine during a decision's lifecycle | YES for "latest live decision"; history is already recoverable from whatever sink persists closed packets (see §8) |
| `SystemSnapshot` (`observability/system_snapshot.py`) | Partially — already periodically dumped to JSON today (`visualization/api/system_snapshot_source.py` reads that dump) | Already solved by the existing pattern; the new canonical snapshot should supersede/wrap it, not duplicate a second competing dump |
| Regret v2 state (`tools/regret_repository.py`) | NO — disk-resident JSONL, `diagnostics()`/`freshness()` are pure reads over files | NO — API may call the same read-only functions directly, in-process, since they do not touch the advisor's live objects |
| Rejection/attrition counts (`observability/rejection_store.py`) | NO — disk-resident | NO — same as above |

---

## 3. SOURCE_TO_EXPOSURE_MATRIX

| Field/domain | Scientific source | Producer process | Current exposure | Target exposure | Cross-process-safe? | Freshness source |
|---|---|---|---|---|---|---|
| Paper open positions (full detail) | `paper_trading/mexc_simulator.py::MexcSimulator._positions` | advisor process only | None (no live API today) | Canonical snapshot, per-cycle | NO (must be materialized, §2.3) | snapshot `generated_at_utc` / cycle |
| Paper equity (paper mode) | `infra/wallet_sync.py::WalletSync.get_balance()` | advisor process (or any process, paper mode only) | `visualization/api/portfolio_api.py` (hardcoded 0.0, defective) | Canonical snapshot | Effectively yes if mode known, but materialize anyway (§2.3) | ledger mtime |
| Real account equity/free/staleness | `observability/real_accounts.py::RealAccountsObserver` | advisor process (poll cadence per notify cycle) | Telegram text block only (never summed with paper — guardrail) | Canonical snapshot, `real_account_*` fields, `NOT_APPLICABLE` if unconfigured | NO for live cache freshness (§2.2) | `RealAccountsObserver` poll timestamp |
| Realized PnL / closed trades | `paper_trading/recorder.py` -> `databases/paper_trades.jsonl` | any process (file read) | None dedicated (portfolio_api.py substitutes open PnL) | Direct ledger read by API, or denormalized in snapshot | YES (append-only JSONL) | file mtime / last CLOSE `ts` |
| DecisionPacket / DecisionObservation (latest, per symbol) | `core/decision_packet.py`, `observability/decision_observation.py` | advisor process | `sdos_terminal/api/app.py::/api/decision/{packet_id}` (DecisionTrace) | Canonical snapshot (latest) + existing trace endpoint (history) | Latest: NO (in-memory during lifecycle); history: depends on packet persistence sink | per-decision `observed_at_utc` |
| Legacy dict pipeline verdict (`trade_allowed`, `blockers`) — actual execution driver | `core/advisor_loop.py::analyze_symbol()` | advisor process | Not exposed over HTTP; drives Telegram/exec only | Canonical snapshot, `decision_pipeline` domain, explicitly labeled AUTHORITY not TELEMETRY | NO | per-cycle |
| Pipeline stage counts (attrition) | `observability/rejection_store.py` | any process (file read) | `visualization/api/pipeline_api.py` (narrow, uses `n_signals = n_refused + n_traded`, flagged non-canonical by this mission) | Canonical snapshot via `observability/operator/domains/attrition.py` vocabulary | YES (disk) | RejectionStore record timestamps |
| Regret v2 state | `tools/regret_repository.py` | any process (file read) | CLI only (`tools/cri_calculator.py`); `BurnInSnapshot` omits freshness (O-01 known gap) | Canonical snapshot via `observability/operator/domains/regret_state.py` | YES (disk) | `last_canonical_evaluated_utc` |
| System health (boot alive, health score) | `observability/system_snapshot.py`, `observability/health_score.py`, `watchdog_vps.py` | advisor process (+ watchdog) | `visualization/api/health_api.py` (partial, `SystemSnapshot`-derived) | Canonical snapshot via `system_health` domain | Boot-alive: NO (process liveness is inherently local, needs a watchdog-style external check); health_score: derivable from `MetricsSnapshot` if persisted | watchdog poll / `MetricsSnapshot` cadence |
| Disk / I-O | DA-01 packs (`workflow_dispatch`-triggered forensic audits) | separate CI job, not the advisor process | None operator-facing (O-01 known gap, carried forward) | Canonical snapshot, `disk_io` domain, `UNAVAILABLE` outside audit windows | YES (artifact files), but on-demand only, not continuous | DA-01 pack timestamp |
| Adaptive learning application counters | `MistakeMemory`, `MetaLearner`/`MetaMemory` | advisor process | `FEATURE_ADAPTIVE_DECISION_FEEDBACK` flag only; no `recommendation_count`/`applied_count` (O-01 `S02_PROVENANCE_DEBT`, unresolved) | Canonical snapshot, fields explicitly `NOT_EXPOSED` per §19 | N/A — not instrumented at all yet | N/A |
| CryptoRadar / market telemetry | `scripts/radar_bot.py`, `scripts/dashboard_api.py` | separate `crypto-radar-bot` process/service | `scripts/dashboard_api.py` (its own token-authed FastAPI, port `DASHBOARD_PORT`) | `MARKET` subrouter/proxy, observational only (§12) | YES if radar's own outputs are disk/HTTP-read, but never treated as execution authority | radar poll cadence |

---

## 4. COMMON_VALUE_CONTRACT

O-01 already ships the value envelope this contract needs
(`observability/operator/contracts.py`). This mission **reuses it
verbatim** rather than inventing a competing shape — per O-01's own
"reuse before creation" principle and the brief's explicit instruction
to reconcile against, not replace, existing vocabulary.

`ObservedValue[T]` (`contracts.py:154-261`):

```
value: Optional[T]
semantics: NullSemantics   # PRESENT | ZERO | FALSE | EMPTY | UNKNOWN |
                           # UNAVAILABLE | STALE | NOT_APPLICABLE
```

`DomainSnapshot` (`contracts.py:327-364`) already carries:
`domain, observed_at_utc, source, source_version, freshness, status,
schema_version, evidence`.

Mapping the brief's requested envelope fields onto what already exists
(no gaps requiring a new field, one naming reconciliation noted):

| Brief's requested field | O-01 equivalent | Note |
|---|---|---|
| `value` | `ObservedValue.value` | direct |
| `status` | `DomainSnapshot.status` (closed vocabulary `OK/DEGRADED/ATTENTION_REQUIRED/UNAVAILABLE`) + `ObservedValue.semantics` for per-field null state | O-01 splits domain-level `status` from field-level `semantics` — this is *more* precise than a single per-field status and is kept |
| `population` (sample size backing a metric, e.g. N trades) | Not a first-class O-01 field; carried today as an explicit `PercentageMetric.denominator`/`.numerator` pair (`contracts.py:286-320`) for ratios, or as a plain int `ObservedValue` for counts | Reused as-is; this contract does not invent a generic `population` field distinct from the already-explicit numerator/denominator pattern |
| `source` | `DomainSnapshot.source` | direct |
| `observed_at_utc` | `DomainSnapshot.observed_at_utc` | direct |
| `source_updated_at_utc` | Not a distinct O-01 field today — `observed_at_utc` conflates "when the domain composer ran" with "when the underlying source last changed." **This contract adds it** as a genuinely new, narrow field on the *snapshot envelope* (§14) because the brief's freshness model (§13) requires distinguishing "we polled at T" from "the source's own last-change time is T-5min." This is a documentation-only addition here — no code exists yet; a future implementation mission must add it to `DomainSnapshot` or an envelope wrapper. |
| `freshness` | `DomainSnapshot.freshness` (`FreshnessStatus`: `FRESH/DEGRADED/STALE/UNKNOWN/NOT_APPLICABLE`) | direct |
| `unit` | `MetricDefinition.unit`/`.value_type` (registry-level, not per-value) | reused; units are a property of the *metric definition*, not repeated on every value instance — avoids redundant per-response payload bloat |
| `authority` | **New concept this mission introduces explicitly** — not an O-01 field. See §8 (`DECISION_API_CONTRACT`) for the authority/telemetry split this must encode: `EXECUTION_AUTHORITY` vs `OBSERVATIONAL_TELEMETRY` vs `SHADOW_CANDIDATE`. Documented here as a required *new* per-field or per-domain tag; not yet implemented in code. |
| `evidence_ref` | `DomainSnapshot.evidence: Mapping[str, Any]` | direct — already a free-form provenance bag per domain |

**Decision:** the future operator API's response envelope = O-01's
`DomainSnapshot.to_dict()` output, augmented with exactly two new
fields not present in O-01 today: `source_updated_at_utc` (§ above) and
`authority` (§8). No other new field is required. This is intentionally
minimal — O-01's vocabulary is sufficient for everything else the brief
asks for.

---

## 5. PORTFOLIO_API_CONTRACT

**Canonical source:** the running `MexcSimulator` instance inside the
advisor process (`paper_trading/mexc_simulator.py`), for open positions
and paper equity's live component; `infra/wallet_sync.py::get_wallet_sync()`
for equity/capital; `observability/real_accounts.py::RealAccountsObserver`
for REAL account fields; `paper_trading/recorder.py` /
`databases/paper_trades.jsonl` for realized PnL and closed history.

**Cross-process materialization strategy (mandatory):** the API process
is explicitly forbidden from `MexcSimulator()` or `WalletSync()`
instantiation of its own (§ PROCESS_BOUNDARY_VERDICT). The advisor
process must, once per cycle, serialize its live `MexcSimulator`
state (via the existing honest-view builder,
`paper_trading/portfolio_status.py::build_portfolio_status()`, which
O-01 already flags `CANONICAL_EXISTING` and "conçu spécifiquement pour
éviter la mésattribution" — reuse this, do not re-derive) into the
canonical snapshot file (§1.3). The API process only ever reads that
file plus the ledger JSONL directly for closed-trade history.

| Field | Source | Exposure target | Notes |
|---|---|---|---|
| `paper_equity_usd` | `WalletSync.get_balance()` (paper mode) | Materialized in snapshot | O-01 `portfolio_state.paper_equity_usd` |
| `paper_open_positions_count` | `MexcSimulator._positions` via `paper_portfolio_view` | Materialized in snapshot | O-01 `portfolio_state.paper_open_positions_count`; `ZERO` if simulator active with no positions, `UNAVAILABLE` if simulator not instantiated |
| `open_positions[]` (list) | `MexcSimulator._positions` | Materialized in snapshot (new — not in O-01's flat scalar model) | See per-position fields below |
| `unrealized_pnl_usd` / `_pct` | `MexcSimulator` position mark-to-market at snapshot time | Materialized in snapshot | O-01 `portfolio_state.paper_unrealized_pnl_usd` |
| `realized_pnl_usd` | Sum of CLOSE events, `paper_trades.jsonl` | API reads ledger directly, or producer denormalizes | O-01 `portfolio_state.paper_realized_pnl_usd` |
| `closed_trade_history[]` | `paper_trading/recorder.py::PaperTradeRecorder.trades()` (closed subset) | API reads ledger directly | See §6 for field list |
| `real_account_equity_usd` | `observability/real_accounts.py` | Materialized in snapshot | `NOT_APPLICABLE` if no real account configured (current stabilization window: none live) |
| `real_account_free_usd` | same | Materialized in snapshot | same |
| `real_account_stale` | same, staleness derived from `RealAccountsObserver` poll cadence | Materialized in snapshot | never silently treated as `False` when unknown — `UNKNOWN` semantics if poll never ran |

**Per-open-position fields** (from `MexcPosition`, `paper_trading/mexc_simulator.py`):

| Field | Available? | Note |
|---|---|---|
| `position_id` | YES (`pos_id`, keyed by ledger `trade_id` on restore, or generated on open) | |
| `symbol` | YES | |
| `side` | YES (`OrderSide`) | |
| `size_usd` (`qty_usd`) | YES | |
| `entry_price` | YES | |
| `current_price` | YES, but **only while the owning process's monitor loop is live** — a restored/second-process view without a fresh price tick would show stale/entry price; must be labeled with its own `observed_at_utc` | |
| `tp_price` / `sl_price` | YES, but on **restore** these are recomputed from a fixed 4%/2% assumption (`_restore_positions()`), not the original order's true TP/SL if it differed — flag this provenance distinction explicitly in the snapshot (`tp_sl_source: "original"` vs `"restored_default"`) | |
| `unrealized_pnl_usd` / `_pct` | YES, computed from `current_price` — inherits the same staleness caveat | |
| `opened_at` | YES (`opened_ts`) | |
| `regime` | PARTIAL — `regime` is attached to the ledger `TradeEvent`/`CompleteTrade` at open time (`paper_trading/recorder.py`), not stored on the live `MexcPosition` object itself (inspected: `MexcPosition` construction in `_restore_positions()` does not set a `regime` attribute) — genuinely attached only via a join back to the ledger by `trade_id`/`symbol`, not on the position object directly. Mark `NOT_EXPOSED` on the position object; `AVAILABLE_VIA_LEDGER_JOIN` if the API performs that join. |
| `personality` | PARTIAL — `MexcPosition.personality` field exists and is set to the literal string `"restored"` on restore (`_restore_positions()` line ~438); its value on a freshly-opened (non-restored) position was not confirmed in this inspection pass (constructor call site for normal opens not fully traced in this mission's time budget) — mark `NEEDS_VERIFICATION`, do not assume it is genuinely populated for live-opened positions without re-reading the open-order path. |

**Forbidden:** the future web API process instantiating `MexcSimulator`
or calling `get_wallet_sync()` and treating the result as the live
machine's state (§ PROCESS_BOUNDARY_VERDICT — this is a hard
constitutional constraint of this contract, not a style preference).

---

## 6. TRADE_API_CONTRACT

**Canonical source:** `paper_trading/recorder.py::PaperTradeRecorder` /
`databases/paper_trades.jsonl` (append-only JSONL, `event: "OPEN"|"CLOSE"`
pairs joined by `trade_id`; schema_version currently `3`). Inspected the
full recorder (`paper_trading/recorder.py`, 250+ lines) and confirmed no
`databases/paper_trades.jsonl` file exists in this checkout (fresh
worktree, no runtime data) — the schema below is from the recorder's
`TradeEvent`/`CompleteTrade` dataclasses, not from sampled live data.

| Brief field | Recorder field | Status |
|---|---|---|
| `trade_id` | `trade_id` | AVAILABLE |
| `symbol` | `symbol` | AVAILABLE |
| `side` | `side` | AVAILABLE |
| `entry` (price) | `entry_price` | AVAILABLE |
| `exit` (price) | `exit_price` (`None` while open) | AVAILABLE |
| `size` | `size_usd` | AVAILABLE |
| `opened_at` | `opened_at` (epoch float) / `opened_iso` | AVAILABLE |
| `closed_at` | `closed_at` / `closed_iso` (`None` while open) | AVAILABLE |
| `duration` | `duration_s` | AVAILABLE (computed at close time from `opened_at`) |
| `realized_pnl_usd` | `pnl_usd` | AVAILABLE (closed trades only) |
| `realized_pnl_pct` | `pnl_pct` | AVAILABLE (closed trades only) |
| `close_reason` | `exit_reason` (from `TradeEvent.reason`) | AVAILABLE |
| `fees` | — | **NOT_EXPOSED** — no fee field anywhere in `TradeEvent`/`CompleteTrade`; `MexcSimulator` applies "slippage and fees MEXC" per its own docstring but the recorder schema does not persist a fee amount. Confirmed by reading the full dataclass field lists (lines 171-234). Must render as `NOT_EXPOSED`, never `0`. |
| `regime` | `regime` | AVAILABLE |
| `score` | `score` (int) | AVAILABLE |
| — (extra, found on inspection) | `mode` (`"futures_demo"\|"paper"\|"live"`) | AVAILABLE — required for MODE_PROVENANCE (§7) |
| — | `order_id` | AVAILABLE (open only) |
| — | `mae_pct` / `mfe_pct` | AVAILABLE (close only, `Optional`) |
| — | `market_context` (27-feature `MarketContext`, schema v2+) | AVAILABLE if schema_version ≥ 2 for that record; `NOT_EXPOSED` for schema v1 records (older ledger lines, backward-compatible read returns `None`) |
| — | `decision_context` (`DecisionContext`: conviction, personality, etc., schema v2+) | Same v1/v2 caveat as above |
| — | `runtime_config_version` (schema v3+) | AVAILABLE for v3 records only |
| `is_open` | `is_open` (bool, `True` for OPEN without matching CLOSE) | AVAILABLE — this is how the trade API distinguishes open vs. closed within the same ledger read, no separate "current positions" call needed for the ledger-derived view (though live mark-to-market still requires §5's MexcSimulator materialization) |
| `is_win` | `is_win` (bool, closed only, `pnl_usd > 0`) | AVAILABLE |

No property in this table is fabricated as zero; any field absent for a
given schema version must render `NOT_EXPOSED` for that record, never a
default numeric.

---

## 7. MODE_PROVENANCE_CONTRACT

Vocabulary (reusing O-02B semantics — confirmed present in repo history
via the merged PR title `o02b/portfolio-provenance-labeling`, base SHA
`5aecc888` includes this merge; the O-02B mode-labeling work is already
in `main`): **`PAPER` / `REAL_API` / `TESTNET_API` / `UNKNOWN`**.

**Rule (non-negotiable):** the API layer must never infer mode from a
frontend literal, a route name, or a variable name such as `real_capital`
— this is exactly the class of bug the O-01 forensic pass already found
(`docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md` §10: "`/kpis`
... mixes paper-derived metrics with a real-capital base with no 'paper'
label"). The variable name `real_capital` appearing anywhere in a data
structure is not evidence of mode; only the producer-established mode
value is.

**How the producer establishes mode:** `infra/wallet_sync.py::WalletSync`
is constructed with an explicit `mode: str = "paper"` parameter
(`WalletSync.__init__`, line ~80) and exposes it via the `.mode` property
(read-only, line ~99). `get_wallet_sync(exchange=None, mode=None)`
resolves the mode once, at first call, from whatever the calling code
(ultimately `core/advisor_loop.py`) passed in — this mission did not
trace the exact call site that determines the string literal
(`"paper"`/`"live"`/`"testnet"`) passed into the very first
`get_wallet_sync()` call of the process, since that is inside
`core/advisor_loop.py`, explicitly off-limits to modify but in-scope to
cite: the mode is a **process-wide constant for the lifetime of the
advisor process**, set at startup, never toggled mid-run by this
contract's design.

**How the API exposes it:** the canonical snapshot (§1.3) must carry
`WalletSync.mode` verbatim as an explicit `mode` field on the portfolio
domain, using the closed `PAPER/REAL_API/TESTNET_API/UNKNOWN` vocabulary
(`UNKNOWN` if the snapshot was generated before the producer's first
successful `get_wallet_sync()` call — never defaulted to `PAPER` by the
API layer's own guess). `MexcPosition`-level `mode` inherited from the
originating `TradeEvent.mode` (`"futures_demo"|"paper"|"live"`, §6) must
be reconciled against the wallet-level mode string, not treated as an
independent second source of truth — a mismatch between the two is
itself a reportable anomaly (`ATTENTION_REQUIRED`), not silently
resolved by preferring one over the other.

---

## 8. DECISION_API_CONTRACT

**EXECUTION AUTHORITY** — `core/advisor_loop.py::analyze_symbol()`,
specifically its **legacy dict pipeline** (`blockers`, `trade_allowed`)
which O-01 already confirmed, by direct citation of
`core/advisor_loop.py:1488`'s own comment, is "the actual execution
driver today." This is the only component in the entire system
authorized to gate a trade (ADR-0007). The operator API must label any
field sourced from this path `authority: "EXECUTION_AUTHORITY"`.

**DECISION TELEMETRY** — two components, both explicitly
**non**-authoritative:

- `DecisionPacket` (`core/decision_packet.py`) — a sealed, hash-chained
  state machine (`StateTransition`, `ReasoningEntry` dataclasses
  confirmed present) tracking a decision's lifecycle
  (`DecisionState` enum). O-01 classifies this `PARTIAL`/"candidate
  track... n'est pas encore le pilote réel de l'exécution." Label:
  `authority: "SHADOW_CANDIDATE"`.
- `BlackBox` (`quant_hedge_ai/agents/intelligence/black_box.py`) —
  `record_decision()`, `record_position_closed()`, `record_halt()`,
  `record_regime_change()` etc. confirmed present (line-numbered above,
  §Research). This is a decision-**outcome**/provenance evidence log,
  not a gate: it records what happened after the authority path already
  decided. Label: `authority: "DECISION_OUTCOME_EVIDENCE"`.

| Field | Source | Authority label |
|---|---|---|
| `packet_id` | `DecisionPacket.packet_id` (UUID, `field(default_factory=uuid.uuid4)`) | SHADOW_CANDIDATE |
| `trace_id` | Not a distinct field found on `DecisionPacket` itself in this pass — `context_id`/`created_cycle_id` exist (lines 402-403) and may serve this role; `governance/decision_trace.py` (consumer, per O-01 `decision_pipeline.decision_packet.consumers`) likely defines the canonical `trace_id` concept — **NEEDS_VERIFICATION against `governance/decision_trace.py`**, not confirmed read in this pass. Mark `PARTIALLY_AVAILABLE` pending that read. | SHADOW_CANDIDATE |
| `symbol` | Present on `DecisionPacket` context (via `context_id` join) and on the legacy pipeline's per-symbol call | Both tracks |
| `side` | `DecisionSide` enum on `DecisionPacket` | SHADOW_CANDIDATE |
| `score` | `confidence_raw` / `adjusted_confidence` (`DecisionPacket`, lines 417-418) | SHADOW_CANDIDATE; legacy pipeline's own `score` is EXECUTION_AUTHORITY |
| `regime` | `MarketRegime` enum on `DecisionPacket`; also present on legacy pipeline / ledger records | Both, label per source |
| `trade_allowed` | Legacy dict pipeline field, `observability/decision_observation.py::DecisionObservation.trade_allowed` (O-01's canonical telemetry reporting field, `decision_pipeline.trade_allowed` metric) | The *terminal verdict that actually executes* is `EXECUTION_AUTHORITY`; `DecisionObservation`'s copy of it is `OBSERVATIONAL_TELEMETRY` (it mirrors the authority verdict for reporting, per O-01's own module description) |
| `first_blocker` | `DecisionObservation.first_blocker` | OBSERVATIONAL_TELEMETRY |
| `all_blockers` | `by_layer_breakdown` in `observability/operator/domains/attrition.py`, backed by `observability/rejection_store.py` | OBSERVATIONAL_TELEMETRY |
| decision outcome (win/loss/etc.) | `BlackBox.record_position_closed()`, ledger `CompleteTrade.is_win` | DECISION_OUTCOME_EVIDENCE |
| timestamps | `DecisionPacket.StateTransition` (per-transition), `BlackBoxEntry` (per-event) | per-source |
| latest decision (per symbol) | Producer must materialize the current `DecisionPacket` state per open/recent symbol into the snapshot — this is in-memory, lifecycle-scoped state, not disk-resident until closed | Materialization required, same rule as §2.3 |
| decision history | Depends on where closed `DecisionPacket`s / `BlackBoxEntry` records are persisted — `BlackBox` writes to `databases/black_box.jsonl` (confirmed referenced in `infra/api/api_server.py`'s `BLACK_BOX` path constant) — this is disk-resident, cross-process-safe, read directly by the API | DECISION_OUTCOME_EVIDENCE, disk-safe |

**Known unresolved measured disagreement** (carried forward from O-01,
not fixed here): `core/advisor_loop.py:6274-6295` measures a
`decision_packet_disagreement_rate` between the SHADOW_CANDIDATE track
and the EXECUTION_AUTHORITY track. This rate itself is a valid,
exposable `decision_pipeline.disagreement_rate` metric (already
registered in O-01) — expose it, but never let it imply DecisionPacket
is authoritative.

---

## 9. PIPELINE_API_CONTRACT

Per the brief: **`n_signals = n_refused + n_traded` must not be reused
as canonical.** Confirmed on inspection this is exactly what
`visualization/api/pipeline_api.py` currently computes (line ~27:
`n_signals = n_refused + n_traded`, with `n_traded = 1 if decision.get("state")
== "ACTIVE" else 0` — a binary flag, not a count, being summed into a
"total signals" figure). This is flagged `PRESENTATION_ONLY`/non-canonical
by this contract, consistent with O-01's `attrition.py` docstring finding
that `activity_tracker.execution_ratio` is "the one metric in the repo
denominated over all signals," i.e. the one legitimate all-signals-wide
ratio already existing — reuse that, not `pipeline_api.py`'s ad hoc sum.

Canonical/instrumented pipeline sources found:
`observability/operator/domains/decision_pipeline.py` (`PIPELINE_STAGES`
tuple, 13 named stages: `authority, signal, meta_strategy, risk_gate,
no_trade_layer, conviction_awareness, portfolio_brain, capital_allocation,
mistake_memory, executive_override, threat_radar, arbitrator, execution`)
and `observability/operator/domains/attrition.py`
(`by_layer_breakdown`, `rejection_rate_over_rejections`,
`execution_ratio`).

| Brief stage | Classification | Evidence |
|---|---|---|
| MARKET OBSERVED | AMBIGUOUS | No dedicated candidate counter upstream of `analyze_symbol()` — O-01's own `decision_pipeline.py` docstring states "UNIVERSE and FEATURES are not separate stages with dedicated candidate counters in the current implementation." |
| CANDIDATES | AMBIGUOUS | Same as above — "happen upstream of `analyze_symbol()` without their own telemetry object." |
| SIGNALS | PARTIALLY_AVAILABLE | `signal` is a named stage in `PIPELINE_STAGES` (`StageObservation` per stage: `input_count`, `output_count`, `rejection_count`, `status`), but O-01's legacy-pipeline `ModuleDescriptor` notes "FILTERS et SIGNALS sont fusionnés dans gate/meta/no-trade plutôt que d'être des étapes nommées séparées" for the actual execution-driving path — the *DecisionObservation* track has the named stage, the *legacy authority* track does not cleanly separate it. |
| META PASS | CANONICALLY_AVAILABLE | `meta_strategy` stage, `StageObservation` |
| FILTER PASS | AMBIGUOUS | Not a distinct named stage in `PIPELINE_STAGES` — folded into `risk_gate`/`no_trade_layer` per the legacy-pipeline module descriptor's own admission. |
| GATE PASS | CANONICALLY_AVAILABLE | `risk_gate` stage (5-condition `GlobalRiskGate` per the pipeline docstring's chain description) |
| RISK PASS | CANONICALLY_AVAILABLE (overlaps GATE PASS — same `risk_gate` stage; the brief's RISK/GATE split does not exist as two separate stages in the code) | `risk_gate` stage |
| PORTFOLIO ADMISSION | CANONICALLY_AVAILABLE | `portfolio_brain` stage (feeds `PortfolioBrain.portfolio_health()` — carries forward O-01's `portfolio_brain_duplicated` known-debt: this stage's counters may inherit the `pos_manager` vs `MexcSimulator` divergence, §5) |
| ORDERS | CANONICALLY_AVAILABLE | `execution` stage, terminal `StageObservation` |
| FILLS | PARTIALLY_AVAILABLE | Not a distinct `PIPELINE_STAGES` entry; fills are implicit in a successful `execution` stage plus the ledger's `OPEN` event — no separate fill-vs-order-sent distinction found (relevant for a simulator with no real exchange fill/reject asymmetry; MexcSimulator's own admission/rejection stub (`_make_rejected_stub`) is closer to a fill-layer signal but was not fully traced for a dedicated counter). |
| REJECTIONS | CANONICALLY_AVAILABLE | `observability/rejection_store.py`, wrapped by `attrition.py`'s `by_layer_breakdown` / `dominant_blocker` / `rejection_rate_over_rejections` — explicitly scoped (per that module's own docstring) to actionable `trade_allowed=False` records with `side in (BUY,SELL,LONG,SHORT)`; HOLD/non-actionable signals are never counted here — **this distinguishes zero rejections (a real, `ZERO`-semantics count) from "rejection tracking not instrumented for this cycle" (`UNAVAILABLE`)** per the brief's requirement. |

`execution_ratio` (`attrition.py`, `PercentageMetric`, all-signals-wide
denominator) is the canonical numerator/denominator pair to use for any
"how many candidates became trades" question — never a manual
`n_refused + n_traded` reconstruction.

---

## 10. SYSTEM_HEALTH_API_CONTRACT

Reuses O-01's domain vocabulary directly, with zero invented composite
score, per the brief. `observability/operator/domains/operator_summary.py`
already implements exactly the "no opaque global health percentage" rule
the brief asks for: `OperatorSummary.status` is `OK`/`ATTENTION_REQUIRED`
(never a number), and `attention_items` names each struggling domain
explicitly by domain id and its own status/freshness — confirmed at
`OPERATOR_OBSERVABILITY_ARCHITECTURE.md` §8 and the
`operator_summary.py` module itself.

Domains to expose, verbatim from O-01's eleven:

| Domain | O-01 module | This contract's exposure |
|---|---|---|
| SYSTEM HEALTH | `system_health.py` — `boot_alive` (process-liveness tier, distinct from) `health_score`/`health_level` (scientific-health tier), `exchange_connectivity_healthy`, `exchange_latency_ms`, `module_statuses` | Expose both tiers separately, never merged into one number |
| MARKET STATE | `market_state.py` | Exposed via §12 MARKET_API_CONTRACT |
| DECISION PIPELINE | `decision_pipeline.py` | §9 |
| ATTRITION | `attrition.py` | §9 |
| PORTFOLIO STATE | `portfolio_state.py` | §5 |
| EXECUTION STATE | `execution_state.py` | Order/execution health (not traced field-by-field in this pass beyond confirming the file exists at 183 lines; defer full field enumeration to the implementation mission, flag `NEEDS_FULL_FIELD_READ`) |
| DATA FRESHNESS | `data_freshness.py` | §13 |
| REGRET STATE | `regret_state.py` | §11 |
| ADAPTIVE PASSIVITY / LEARNING | `adaptive_learning.py` | `decision_feedback_enabled` (FEATURE_ADAPTIVE_DECISION_FEEDBACK) exposed; `recommendation_count`/`applied_count` remain `NOT_EXPOSED` (O-01 `S02_PROVENANCE_DEBT`, unresolved, carried forward — §19) |
| DISK / I-O | `disk_io.py` | On-demand only (DA-01), `UNAVAILABLE` outside audit windows — no continuous producer exists (O-01 known gap) |
| OPERATOR SUMMARY | `operator_summary.py` | Composition-only synthesis of the above ten; never a source of new truth |

---

## 11. REGRET_API_CONTRACT

**Canonical source:** `tools/regret_repository.py` (Regret v2, certified
S-01 architecture per O-01's `regret_state.py` docstring — "does not
redesign Regret"). v1 classification
(`quant_hedge_ai/agents/intelligence/regret_engine.py`) is **LEGACY**,
retired since 2026-07-10 per ADR-0018, and appears only as an explicit
fallback path in `visualization/api/burnin_api.py` — never a silent
substitute for v2 (this contract forbids the future API from defaulting
to v1 output without labeling it `LEGACY_FALLBACK`).

**Field separation:**

| Tier | Fields | Rationale |
|---|---|---|
| **operator-primary** | `v2_active`, `canonical_freshness`, `pending_candidate_count`, `decision_feedback_enabled` (governance flag state) | What an operator needs at a glance: is Regret alive, fresh, and is it (not) feeding decisions |
| **operator-detail** | `canonical_horizon`, `last_event_utc` (producer liveness clock — distinct from) `last_canonical_evaluated_utc` (the real evaluated-on-canonical-horizon freshness clock — O-01 is explicit these must never be conflated), `horizon_status_counts` (`PENDING/MISSING_PRICE/DROPPED/EVALUATED` breakdown), `malformed_count` | Diagnostic depth for someone investigating a stale/degraded state |
| **machine-only** | Raw per-candidate MISSED_WIN/GOOD_REFUSAL classification records, CRI computation internals (`tools/cri_calculator.py`) | Feeds the statistician's N-threshold gates (`CLAUDE.md`'s Règle du statisticien) — not an operator dashboard concern at the per-record level; the CRI *score* itself (0-100) may be operator-detail, but individual regret event records are not a cockpit-facing shape |

`BurnInSnapshot`'s known gap (O-01 §10: omits `tools.regret_repository.
freshness()`, only the CLI sees it) is a defect this contract flags for
the implementation mission to fix by construction — the canonical
snapshot must include `last_canonical_evaluated_utc`-derived freshness,
not silently repeat `BurnInSnapshot`'s omission.

---

## 12. MARKET_API_CONTRACT

No `CryptoRadar` **class** exists in the codebase (searched
system-wide, all `.py` files — zero matches for `class CryptoRadar`).
The brief's "CryptoRadar" refers to the **CryptoRadar product/service**:
`scripts/radar_bot.py` (Telegram bot) and `scripts/dashboard_api.py`
(its own standalone, token-authenticated FastAPI dashboard, title
`"CryptoRadar"`, confirmed at line 16: `app = FastAPI(title="CryptoRadar",
...)`, port `DASHBOARD_PORT` env var, HMAC-token auth already
implemented there).

**Constitutional constraint:** CryptoRadar is **MARKET / observational
telemetry only** — it must never be treated as execution authority
(ADR-0007 applies to it exactly as to every other observer). Nothing in
the inspected `dashboard_api.py`/`radar_bot.py` code path feeds
`core/advisor_loop.py::analyze_symbol()`'s decision; this contract
requires that boundary be preserved by any future integration.

**How it may be incorporated later, without redesigning it:**
- **Reuse existing route semantics as a proxy**: the future operator API
  MAY reverse-proxy read-only GET routes already served by
  `scripts/dashboard_api.py` (it already authenticates and is read-only
  by its own docstring: "LECTURE SEULE") rather than reimplementing its
  data access.
- **Normalized MARKET subrouter**: alternatively, expose a
  `market_state` domain endpoint (O-01's `market_state.py`, already
  covers "is market data fresh and is the exchange reachable") as the
  cockpit-facing MARKET panel, and treat CryptoRadar's own dashboard as
  a separate, unlinked tool rather than merging its output into the
  operator snapshot — avoids coupling two independently-evolving
  surfaces.
- Either path is acceptable; this contract does not mandate one over
  the other, only that CryptoRadar integration, if it happens, is
  additive (a proxy or a subrouter) and never a rewrite of
  `dashboard_api.py`'s existing, working read-only auth/routing.

---

## 13. FRESHNESS_CONTRACT

Reuses O-01's `FreshnessStatus` (`FRESH|DEGRADED|STALE|UNKNOWN|
NOT_APPLICABLE`) and `freshness.py::classify_freshness()` verbatim — "no
timestamp -> UNKNOWN" is already the O-01 rule (`classify_freshness()`
"never invents a threshold: without an evidence-backed `fresh_threshold_s`
/`stale_threshold_s` pair it returns `UNKNOWN`, not a guess").

Per-domain freshness clocks (already domain-specific per O-01 §7, no
single global "snapshot age"):

| Domain | `observed_at`/liveness clock | `source_updated_at` clock | Missing-source behavior | Restart behavior |
|---|---|---|---|---|
| Portfolio (paper) | snapshot `generated_at_utc` | ledger file mtime / last event `ts` | `MexcSimulator` not instantiated -> `UNAVAILABLE`, never `0` positions presented as healthy | Ledger persists; positions restored (approximately, §2.1) at process start — snapshot must reflect `restored_from_ledger: true/false` per position |
| Portfolio (real) | `RealAccountsObserver` poll timestamp | same | No account configured -> `NOT_APPLICABLE` (not `UNAVAILABLE` — it's a deliberate absence, not a failure) | Poll resumes at next cycle; last-known value marked `STALE` if beyond threshold, never silently refreshed as `FRESH` |
| Decision pipeline | per-cycle `DecisionObservation` publication | same | No `DecisionObservation` this cycle for symbol -> `UNKNOWN` | Fresh cycle, no special handling needed (stateless per-cycle) |
| Attrition | `RejectionStore` record timestamps | same | Empty query result -> distinguish **ZERO rejections this window** (`NullSemantics.ZERO`) from **RejectionStore file missing/unreadable** (`UNAVAILABLE`) — never conflate | File persists across restart |
| Regret | `last_canonical_evaluated_utc` (the real clock) vs. `last_event_utc` (producer liveness only — never substituted for the former) | same distinction | No canonical evaluation yet -> `UNKNOWN` | Disk-resident, unaffected by restart |
| System health | watchdog poll cadence (boot tier) / `MetricsSnapshot` cadence (scientific tier) | same | Watchdog unreachable -> `UNAVAILABLE` for boot tier specifically (not silently "unhealthy" merged with scientific tier) | Watchdog is a separate process; its own liveness is a precondition for the boot-alive signal to mean anything |
| Disk/IO | DA-01 pack timestamp | same | Outside an audit window -> `UNAVAILABLE`, never `OK`-by-default | On-demand only; no restart concept applies |
| Market state | exchange/market-pulse tick age | same | Exchange unreachable -> `STALE` or `UNAVAILABLE` per `exchange_connectivity_healthy` | New connection attempted next cycle |

Missing file anywhere in this table -> `UNAVAILABLE`. No timestamp ->
`UNKNOWN`. Neither is ever rendered as `0` or as a healthy default.

---

## 14. ATOMICITY_CONTRACT

The canonical snapshot (§1.3) must carry, at the envelope level (outside
any individual domain, since these are cross-domain consistency
guarantees, not domain facts):

| Field | Purpose |
|---|---|
| `snapshot_id` | Opaque unique id per write (e.g. UUID or monotonically increasing counter) — lets a consumer detect "I am looking at two different snapshots" even if timestamps alone are ambiguous |
| `cycle` | The advisor loop's own cycle counter at the moment of composition — the single most important field for preventing "positions from cycle N + capital from cycle N+1" mixtures, since every domain composed into one snapshot write must share one `cycle` value by construction (the write happens once per cycle, not per domain) |
| `runtime_sha` | The git SHA actually running in the producer process (distinct from `source_sha`/deployed SHA, §15) |
| `process_instance_id` | Identifies *which* advisor process instance produced this (relevant across restarts — a new PID after a restart is a new instance even if `runtime_sha` is unchanged) |
| `generated_at_utc` | Wall-clock write time |

**Consistency expectation:** the API process must refuse to compose a
cockpit view from two files/reads whose `snapshot_id` (or `cycle` +
`process_instance_id` pair) differ, if it ever needs to merge more than
one snapshot read (e.g. a slow client re-polling mid-write — mitigated
primarily by the atomic-rename write pattern in §1.3, but the id fields
are the belt to that suspenders). A single-file, single-read design
(the selected option) makes true cross-cycle mixture structurally
difficult, but a network hiccup or a client caching an old response
must not be silently reconciled against a new one — the client must
treat `snapshot_id` as a version key and discard stale reads outright,
never merge fields across two ids.

---

## 15. RUNTIME_IDENTITY_CONTRACT

| Field | Meaning | Source |
|---|---|---|
| `source_sha` | The git commit the running code was checked out from | `git rev-parse HEAD` at process start, or the deploy tooling's own record (`CLAUDE.md`'s `deploy-YYYYMMDD-HHMM` annotated tags carry the SHA + file list — reuse that convention as the audit trail, do not invent a second one) |
| `runtime_sha` / `deployed_sha` | If separately known — relevant because `CLAUDE.md`'s own documented history (the v2/v3 `CLEAN_DATA_SINCE` incident) shows a real historical case where the deployed code silently diverged from what was believed deployed (the `ssh` `-n` bug in `deploy_vps.sh`) — this field exists specifically so that class of silent divergence is detectable going forward | Deploy tag / `scripts/deploy_vps.sh` audit trail |
| `process_instance_id` | Unique per process lifetime | Generated at process start (e.g. a UUID or `os.getpid()` combined with boot timestamp for uniqueness across PID reuse) |
| `pid` | If safe to expose (host-local FastAPI/cockpit under the operator's own control — this contract treats it as safe within the read-only, non-public deployment model of §16; must not be exposed if the API is ever made publicly reachable without auth) | `os.getpid()` |
| `boot timestamp` | Process start time | Recorded at process start |
| `cycle` | See §14 | advisor loop's own counter |
| `schema_version` | Snapshot schema version — reuse O-01's `contracts.SCHEMA_VERSION` pattern (currently `"1.0.0"`), extended for the envelope-level additions this contract proposes (§4) | `observability/operator/contracts.py::SCHEMA_VERSION` |
| `exposure_epoch_id` | If applicable — maps to `CLAUDE.md`'s "époque" concept (e.g. the `CLEAN_DATA_SINCE_V4` universe-epoch boundary) so a cockpit consumer can tell which experimental epoch the currently-exposed data belongs to, without duplicating that governance logic in the API itself (it should read the same canonical epoch boundary the statistician's tooling reads — `scripts/data_quality.py`'s `CLEAN_DATA_SINCE_ACTIVE` alias — never a locally copied constant, per `CLAUDE.md`'s explicit "jamais copiée localement" rule) | `scripts/data_quality.py::CLEAN_DATA_SINCE_ACTIVE` |

**No secrets.** No API key, no exchange credential, no Telegram token,
no `.env` value beyond the non-secret identity fields above may ever
appear in the snapshot or the API response. This is a hard constraint,
not a recommendation.

---

## 16. SECURITY_READ_ONLY_CONTRACT

The future operator API is **READ-ONLY**, full stop:

- **Allowed:** `GET` endpoints; an optional read-only WebSocket stream
  (server -> client push of snapshot updates, never client -> server
  commands).
- **Forbidden, unconditionally:** any trading control endpoint; any
  strategy/risk/parameter mutation endpoint; file upload of any kind;
  shell/subprocess execution triggered by a request; a restart route;
  any Telegram control (send/edit/delete) triggered by a request. This
  list matches the brief exactly and is non-negotiable per ADR-0007
  (absolute observer passivity) — a "read-only API" that secretly
  exposes one mutating route is not a passive observer, it is a second,
  undocumented decision surface.
- **Auth requirement (contract-level, not implemented here):** if this
  API is ever reachable outside `localhost`/an operator-only network
  boundary, it **must fail closed** — no route responds without
  authentication. `scripts/dashboard_api.py` already demonstrates a
  working pattern in this codebase (HMAC-signed token,
  `DASHBOARD_PASSWORD` env var, `_verify_token()`) that a future
  implementation may reuse rather than invent a new auth scheme
  (REUSE_TRANSPORT_PATTERN, §18). This contract does not implement auth
  — it requires that the implementation mission not ship a publicly
  reachable, unauthenticated instance under any circumstance.

---

## 17. PANEL_REQUIREMENT_MATRIX

"F-00" = the first cockpit release milestone. Minimum contracts required
before F-00, per panel:

| Panel | Minimum contract required before F-00 |
|---|---|
| **GLOBAL** | RUNTIME_IDENTITY_CONTRACT (§15) + ATOMICITY_CONTRACT (§14) + at minimum `operator_summary` domain (§10) — a cockpit cannot render *anything* trustworthy without knowing what snapshot/cycle it is looking at and whether the system considers itself healthy |
| **MARKET** | `market_state` domain (§10/§12), scoped to freshness/connectivity only — full CryptoRadar integration is explicitly SAFE_TO_ADD_AFTER_F00 |
| **PORTFOLIO** | Full §5 PORTFOLIO_API_CONTRACT for paper equity/open positions/realized PnL; REAL account fields may ship as `NOT_APPLICABLE` placeholders if no real account is configured during the stabilization window (current state) |
| **TRADES** | §6 TRADE_API_CONTRACT closed-trade history, ledger-read only — no live position dependency, so this is one of the *cheapest* panels to ship correctly |
| **DECISIONS** | §8's `EXECUTION AUTHORITY` verdict + `first_blocker`/`all_blockers` (attrition) at minimum; full `DecisionPacket` shadow-track detail may ship after F-00 |

| Domain | Classification | Justification |
|---|---|---|
| PIPELINE | REQUIRED_BEFORE_F00 (attrition/rejections subset only) | An operator needs to see *why* trades aren't happening (the single most common operator question); full 13-stage `StageObservation` detail can lag, but `dominant_blocker`/`execution_ratio` cannot |
| RISK | SAFE_TO_ADD_AFTER_F00 | `risk_gate`/`execution_state` domains are diagnostic depth, not a first-cut operator need beyond the authority verdict already required for DECISIONS |
| REGRET | SAFE_TO_ADD_AFTER_F00 | Statistician-facing (CRI/N-thresholds), not an operational go/no-go signal for day-to-day monitoring; `v2_active`/`canonical_freshness` alone (operator-primary tier, §11) could ship early cheaply, but full regret detail is not F-00-critical |
| DATA (freshness) | REQUIRED_BEFORE_F00 (as a cross-cutting concern, not a standalone panel) | Every other panel's numbers are meaningless without a freshness indicator attached — this is not a separate panel to defer, it is a property every other panel's fields must already carry per §13 |
| SYSTEM | REQUIRED_BEFORE_F00 (boot_alive + operator_summary subset only) | An operator must be able to tell "is the machine even running" before anything else matters; full disk_io/module_statuses detail is SAFE_TO_ADD_AFTER_F00 |

This matrix deliberately does not maximize panel count — several O-01
domains (disk_io, adaptive_learning detail, full decision_pipeline stage
breakdown) are explicitly deferred as diagnostic depth rather than F-00
requirements.

---

## 18. EXISTING_STACK_DISPOSITION_MATRIX

| Component | Classification | Justification (from actually reading the file) |
|---|---|---|
| `frontend/` (React cockpit, `frontend/src/{App.tsx,components,hooks,lib,views,types.ts}`) | REUSE_UI_SHELL | This is the target consumer this whole contract exists to feed — the shell (routing, view structure, `types.ts`) is the thing to build the new API *for*, not against. Not read field-by-field in this pass (out of scope — no UI changes per the mission's own constraint), but its existence as the intended consumer is confirmed. |
| `infra/api/api_server.py` | REUSE_TRANSPORT_PATTERN only (its route names are NOT canonical, per the brief's explicit warning) | Confirmed: reads directly from `databases/black_box.jsonl`, `databases/cycle_data.jsonl`, `databases/live_snapshot.json`, `logs/trades.jsonl`, `logs/execution_audit/audit.jsonl`, `databases/mistake_memory.jsonl` — a FastAPI-over-JSONL pattern worth reusing structurally, but its data-loading logic (which files, which fields, what shape) is not canonical merely because the route names are convenient, exactly as the brief warns. Its `BLACK_BOX` path-resolution fix (S-03B item 8, repo-root-relative) is a good precedent to follow, not the semantics of what it returns. |
| `sdos_terminal/api/app.py` | REUSE_TRANSPORT_PATTERN + REUSE_DATA_SEMANTICS (partially) | Explicitly documents itself as "Read-only REST API over the SDOS Data API (visualization/api/). No database writes. No engine modification. Passive observer (ADR-0007)" — the right philosophy, and its route list (`/api/health`, `/api/pipeline`, `/api/portfolio`, `/api/rejections`, `/api/burnin`, `/api/regret`, `/api/decision/{packet_id}`, `/api/system`, plus PNG/WS variants) is a reasonable shape to inherit. But it sits on top of `visualization/api/*.py`, which (next rows) carries known, uncorrected defects — so REUSE the shape, not the current values it returns until those are fixed. |
| `visualization/api/portfolio_api.py` | DO_NOT_REUSE (data semantics) | Confirmed: `n_trades=0, n_wins=0, n_losses=0, win_rate_pct=0.0, profit_factor=0.0, expectancy_pct=0.0, max_drawdown_pct=0.0, sharpe=0.0` are literal hardcoded zeros in the constructor call (8 of the ~10 `PortfolioSnapshot` fields), and `total_pnl_usd=float(portfolio.get("open_pnl_usd", 0.0))` substitutes *open* PnL for *total* PnL — exactly the two defects O-01 already flagged. Must not be treated as canonical until independently fixed; this contract's §5 supersedes it. |
| `visualization/api/health_api.py` | DO_NOT_REUSE (data semantics), REUSE_TRANSPORT_PATTERN acceptable | `_bool_score()` computes a bare `sum(bools)/len(bools)*100` composite — exactly the "invented opaque global health percentage" this contract's §10 forbids. Structurally it is a thin `SystemSnapshot`-mapping function, fine as a pattern; its *pseudo-health-percentage* output must not be reused. |
| `visualization/api/pipeline_api.py` | DO_NOT_REUSE (data semantics) | Confirmed `n_signals = n_refused + n_traded` with `n_traded` being a 0/1 flag from `decision.get("state") == "ACTIVE"`, not an actual trade count — the exact non-canonical pattern §9 forbids reusing. A narrow proxy over `SystemSnapshot.block_stats`, not the 13-stage `PIPELINE_STAGES` model. |
| `scripts/dashboard_api.py` | REUSE_TRANSPORT_PATTERN (auth specifically) | Confirmed working HMAC-token auth (`_make_token()`/`_verify_token()`, `DASHBOARD_PASSWORD` env var) in a read-only (`"LECTURE SEULE"` per its own docstring) FastAPI app — good precedent for §16's auth requirement. Its `CryptoRadar`-specific data semantics are out of this contract's PORTFOLIO/TRADES/DECISIONS scope (see §12 for its disposition as a market-telemetry source instead). |
| `sdos_terminal/frontend/` | Not inspected in this pass (directory existence not confirmed independently of `sdos_terminal/api/app.py`'s presence) — classify NEEDS_VERIFICATION rather than guess | — |
| `risk_dashboard_api.py` | Does not exist at repo root (confirmed: `ls` returned "No such file or directory") | N/A — nothing to classify |
| `api_rest.py` | Does not exist at repo root (confirmed: `ls` returned "No such file or directory") | N/A — nothing to classify |
| `observability/system_snapshot.py` + `visualization/api/system_snapshot_source.py` | REUSE_DATA_SEMANTICS (the underlying `SystemSnapshot` JSON-dump pattern) with an explicit caveat: **`SystemSnapshot != O-01`** — O-01's own architecture doc states this class distinction directly (§10 known gap: "`portfolio_api.py` is defective... `SystemSnapshot != O-01`" is implied by the fact O-01 had to build an entirely parallel domain-snapshot contract rather than just wrapping `SystemSnapshot` fields 1:1). Reuse the *atomic-JSON-dump transport pattern* (§1.3 explicitly models the new canonical snapshot on this), never assume `SystemSnapshot`'s existing field values already satisfy O-01/this contract's semantics without independent field-level certification. | |

---

## 19. NOT_EXPOSED_REGISTER

Fields investigated and found **not currently recorded/instrumented**,
documented explicitly rather than silently omitted:

| Field | Where it was looked for | Finding |
|---|---|---|
| Trade fees | `paper_trading/recorder.py::TradeEvent`/`CompleteTrade` full field list | No fee field in either dataclass; `MexcSimulator` claims to simulate "fees MEXC" in its docstring but the recorder schema does not persist an amount. `NOT_EXPOSED`, never `0`. |
| Adaptive learning `recommendation_count`/`applied_count` | O-01 `adaptive_learning.py` (already documents this gap as `S02_PROVENANCE_DEBT`) | No dedicated counter exists in `MistakeMemory`/`MetaLearner`/`MetaMemory`/`StrategyMemoryStore`/`StrategyRanker`; `recommendation_equals_applied` is a "fixed structural False" by design post-S02, not a measured rate. `NOT_EXPOSED`. |
| `DecisionPacket.trace_id` (as a distinctly-named field) | `core/decision_packet.py` field list (lines 400-437 range inspected) | No field literally named `trace_id` found; `context_id`/`created_cycle_id` are the closest candidates. `PARTIALLY_AVAILABLE`, pending a read of `governance/decision_trace.py` not completed in this pass. |
| Regime/entropy confidence on `SystemSnapshot.market` | O-01 `market_state.py::MODULES` (already documents this gap) | "`RegimePacket` fields exist and are logged but never reach `SystemSnapshot.market`." `NOT_EXPOSED` at the `SystemSnapshot` level; may exist upstream in `RegimePacket` itself (not independently re-verified in this pass beyond citing O-01's finding). |
| Continuous disk/IO operator-facing snapshot | O-01 `disk_io.py::MODULES` (already documents this gap) | DA-01 is `workflow_dispatch`-triggered only, "no operator-facing snapshot (`SystemSnapshot`, `MetricsSnapshot`) carries a disk field today." `UNAVAILABLE` outside audit windows by design, not a bug to fix here. |
| Regret freshness over HTTP | O-01 `regret_state.py::MODULES` (already documents this gap) | `tools/regret_repository.freshness()` exists and is correct but `BurnInSnapshot` omits it; only the CLI (`tools/cri_calculator.py`) sees it today. This contract's §11 requires the implementation mission to close this gap, not perpetuate it. |
| `MexcPosition.personality` for a normally (non-restored) opened position | `paper_trading/mexc_simulator.py` | Confirmed `"restored"` literal on restore path; the live-open code path's value for this field was not independently re-traced to full confirmation within this mission's time budget. `NEEDS_VERIFICATION`, not asserted either way. |
| `MexcPosition.regime` | `paper_trading/mexc_simulator.py` (`_restore_positions()` construction site) | Not set on the `MexcPosition` object itself; only present on the originating ledger `TradeEvent`. `NOT_EXPOSED` on the position object directly; `AVAILABLE_VIA_LEDGER_JOIN` if the API performs an explicit join by `trade_id`/`symbol`. |

---

## 20. CONTRACT RISKS / OPEN QUESTIONS

1. **`DecisionPacket.trace_id` existence and shape** are unresolved
   pending a read of `governance/decision_trace.py` — a future
   implementation mission (or a short follow-up research pass) must
   confirm this before the DECISIONS panel's field list is finalized.
2. **`execution_state.py` domain fields** were confirmed to exist
   (183-line file) but not individually enumerated in this pass —
   flagged `NEEDS_FULL_FIELD_READ` in §10.
3. **`sdos_terminal/frontend/` existence/purpose** relative to the main
   `frontend/` cockpit is unconfirmed — two frontends may or may not
   both be live; this matters for which one the future operator API is
   actually built to serve. Needs an explicit product decision, not an
   engineering guess.
4. **`MexcPosition` live-open `personality`/`regime` population** —
   §19 above; affects whether the PORTFOLIO panel's "personality if
   genuinely attached" field (per the brief) can ship at F-00 or must
   wait.
5. **Restored-position TP/SL provenance labeling** (§5: fixed 4%/2%
   default vs. the position's true original TP/SL) is a real,
   observable data-quality risk for any operator trusting the cockpit's
   TP/SL display after a process restart during the STABILIZATION LAB
   window (2026-09-02 -> 2026-09-16, currently active per `CLAUDE.md`)
   — restarts are explicitly authorized during this window, so this
   risk is live, not hypothetical, for the exact period this contract
   is being written in.
6. **Live/testnet `WalletSync` cross-process safety** (§2.2) has no
   clean re-derivation path short of the producer materializing it —
   if a future implementation mission is tempted to have the API
   process independently `bootstrap()` against the real exchange for
   convenience, that doubles exchange API calls and diverges from the
   advisor's own cached value; this contract explicitly forbids that
   shortcut, but it is worth flagging as a temptation the implementation
   mission should watch for.
7. **CryptoRadar (`scripts/dashboard_api.py`) auth token secret
   (`_SECRET = secrets.token_hex(32)`) is generated fresh per process
   start** (confirmed at module scope, not persisted) — any future
   proxy integration (§12) must account for tokens not surviving a
   `dashboard_api.py` restart; this is CryptoRadar's own existing
   behavior, not something this contract changes, but it constrains
   how a proxy could safely reuse its auth.
8. **`FEATURE_AUTO_CALIBRATION` / regret decision-feedback governance
   path** is explicitly out of this contract's scope (`CLAUDE.md`:
   "Regret's `FEATURE_AUTO_CALIBRATION`/`FEATURE_REGRET_DECISION_
   FEEDBACK` remains a separate governance path, untouched by this
   reconciliation" — quoting O-01 verbatim, still true here); the
   REGRET_API_CONTRACT (§11) only exposes its *state*, never its
   governance.

---

## 21. MINIMUM_IMPLEMENTATION_MISSION

The next implementation mission this contract unblocks (source-only
description, explicitly **no code** in this document):

**Mission scope:** build the **canonical operator snapshot writer** as a
narrow, in-process addition invoked once per advisor loop cycle (not a
new decisional component — a pure serializer with zero decision
authority), materializing exactly the fields enumerated as
"materialization required" in §2.3, §5, §7, §8, using the O-01
`compose_*_snapshot()` functions already shipped
(`observability/operator/domains/*.py`) as the composition layer, and
writing the result via atomic tmp-file-plus-`os.replace()` to a single
canonical JSON path, augmented with the envelope-level identity/atomicity
fields from §14-§15.

**In scope:**
- Wiring real producers (`SystemSnapshot`, `MexcSimulator` via
  `paper_portfolio_view`/`portfolio_status.py`, `WalletSync`,
  `RejectionStore`, `tools/regret_repository.py`, `DecisionObservation`)
  into the O-01 `compose_*_snapshot()` calls — this is exactly the "step
  1" O-01 itself deferred ("a future integration layer... will: 1. read
  already-existing in-memory objects... 2. wrap each value in an
  `ObservedValue`... 3. call the relevant `compose_*_snapshot()`").
- The atomic snapshot writer itself (tmp file + `os.replace()`).
- A separate, new, read-only FastAPI process (or an addition to
  `sdos_terminal/api/app.py` if that shape is confirmed reusable per
  §18) exposing GET routes over the snapshot file plus direct reads of
  the existing JSONL ledgers for history (trades, decisions).
- Auth per §16, reusing `scripts/dashboard_api.py`'s HMAC pattern or
  equivalent.

**Explicitly out of scope for that mission too** (carried forward from
this one): any modification to `core/advisor_loop.py`'s decision logic,
any new signal/indicator/threshold, any Telegram wiring, any VPS
deploy/restart action, any write path from the API back toward the
advisor process. The writer call site inside the advisor loop is
additive instrumentation (read current state, serialize, write file) —
not a change to what the loop decides.

---

## REQUIRED_FIELD_CONTRACT_TABLE

| Field ID | Meaning | Type | Unit | Population | Authority | Null semantics | Zero semantics | Freshness |
|---|---|---|---|---|---|---|---|---|
| `portfolio.paper_equity_usd` | Current simulated equity | float | usd | N/A (scalar) | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if WalletSync unreachable | Genuine `$0` equity is `ZERO`, distinct from unavailable | ledger mtime |
| `portfolio.open_positions[]` | Live paper positions | list[object] | — | count = list length | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if simulator not instantiated | `EMPTY` list if simulator active with zero positions | snapshot `generated_at_utc` |
| `portfolio.open_positions[].current_price` | Live mark price | float | usd | N/A | OBSERVATIONAL_TELEMETRY | `STALE` if no fresh tick since position restore | N/A (price is never legitimately 0) | per-position last tick |
| `portfolio.realized_pnl_usd` | Sum of closed-trade PnL | float | usd | N over closed trades | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if ledger unreadable | `ZERO` if genuinely no closed trades yet | ledger mtime |
| `trade.fees` | Per-trade fee amount | float | usd | N/A | OBSERVATIONAL_TELEMETRY | `NOT_EXPOSED` always (not recorded, §19) | never rendered as 0 | N/A |
| `decision.trade_allowed` (authority copy) | Terminal execution verdict | bool | boolean | N/A | EXECUTION_AUTHORITY | `UNKNOWN` if no cycle ran yet for symbol | `FALSE` is a genuine, meaningful value (blocked) | per-cycle |
| `decision.trade_allowed` (DecisionObservation copy) | Mirrored verdict for reporting | bool | boolean | N/A | OBSERVATIONAL_TELEMETRY | same | same | per-cycle |
| `pipeline.execution_ratio` | All-signals-wide executed/refused ratio | PercentageMetric | pct | numerator=executed, denominator=all evaluated signals | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if `activity_tracker` unreachable | `0%` is a genuine (bad) rate, not absence | per cycle |
| `attrition.dominant_blocker` | Most frequent rejection layer | str (enum-like) | — | over `RejectionStore` window | OBSERVATIONAL_TELEMETRY | `UNKNOWN` if zero rejection records at all | N/A (categorical) | `RejectionStore` record timestamps |
| `regret.canonical_freshness` | Regret v2 evaluated-horizon freshness | FreshnessStatus | enum | N/A | OBSERVATIONAL_TELEMETRY | `UNKNOWN` if no canonical evaluation has ever run | N/A | `last_canonical_evaluated_utc` |
| `system_health.boot_alive` | Process liveness | bool | boolean | N/A | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if watchdog itself unreachable | `FALSE` is genuine (process down) | watchdog poll |
| `system_health.health_score` | Composite scientific health (0-100), NOT a global system percentage — scoped to `MetricsSnapshot` inputs only | float | pct (0-100) | over defined `MetricsSnapshot` inputs | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if `MetricsSnapshot` missing | `0` is a genuine (critical) score | `MetricsSnapshot` cadence |
| `mode` (portfolio/wallet) | PAPER/REAL_API/TESTNET_API/UNKNOWN | enum | — | N/A | provenance metadata, not authority | `UNKNOWN` if snapshot predates first successful mode resolution | N/A (categorical) | process-lifetime constant |
| `snapshot_id` / `cycle` / `runtime_sha` / `process_instance_id` | Identity/atomicity spine | mixed | — | N/A | envelope metadata | never null in a valid snapshot | N/A | write-time |

---

## PROCESS_BOUNDARY_VERDICT

**Can a separate web API safely instantiate and read `MexcSimulator`
directly?**
**NO.** `MexcSimulator._positions` is a plain instance dict
(`paper_trading/mexc_simulator.py:267`), populated only by the advisor
process's own `start()`/`_restore_positions()`/live monitor loop. A
second process's `MexcSimulator()` call creates an independent,
disconnected object whose `_positions` starts empty and can, at best,
partially and staleley reconstruct entry-side fields from the ledger —
never the live mark-to-market state of the actually-running machine.
Confirmed by direct source inspection, not inferred.

**Can a separate process call `get_wallet_sync()` and be guaranteed to
share the runtime advisor singleton?**
**NO.** `infra/wallet_sync.py`'s `_singleton` (line 223) is a
module-level global inside one Python interpreter process. A second OS
process is a second Python interpreter with its own independently-`None`
-initialized `_singleton` — `get_wallet_sync()` there constructs a *new*
`WalletSync` instance, never the advisor process's. This is a structural
property of the OS process model (no shared memory/IPC exists between
these two processes in the current architecture), not a bug that could
be patched without introducing IPC — which this contract deliberately
avoids (§1.2). One practical mitigation exists and is documented (§2.2):
in **paper mode only**, `get_balance()` happens to recompute from disk
each call, so a second process's *own* singleton, configured with the
correct `mode`, would coincidentally compute the same number — but this
is a property of `get_balance()`'s implementation, not a guarantee of
singleton sharing, and does not hold in live/testnet mode at all.

**What state therefore requires materialization by the producer
process?**
1. `MexcSimulator._positions` — full open-position detail, mark-to-market
   at snapshot time (§2.1, §5).
2. `WalletSync` live/testnet-mode balance, cached value, and capital `X`
   (bootstrap result) — no safe cross-process re-derivation exists
   (§2.2).
3. `WalletSync.mode` itself, as explicit provenance metadata (§7) — a
   second process has no way to know which mode the advisor's singleton
   was constructed with without being told.
4. The current/latest `DecisionPacket` state per symbol during its
   in-memory lifecycle (§8) — closed/terminal packets that reach a disk
   sink (e.g. `black_box.jsonl`) do not require this, only the live,
   in-flight state does.
5. Paper-mode `WalletSync.get_balance()` — not strictly *required*
   (re-derivable, §2.2), but materialized anyway by this contract's
   design (§2.3) to give the API one single source of truth instead of
   re-implementing wallet arithmetic in a second place (reuse-before-
   creation, O-01 principle).

Everything else this contract catalogues (realized PnL/closed trades,
Regret v2 state, rejection/attrition counts, `SystemSnapshot`'s existing
JSON-dump fields) is already disk-resident and may be read directly by
the API process without producer materialization, because it never
depended on a single process's live heap in the first place.
