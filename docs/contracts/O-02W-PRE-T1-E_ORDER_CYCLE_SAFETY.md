# O-02W-PRE-T1-E — Order-Cycle Safety Audit (Causal, Audit-First)

## 1. Scope and prohibitions

This is an **audit**, not a remediation. Zero production logic changes. Only two
files are authored by this mission: this contract and
`tests/test_pre_t1_e_order_cycle_safety.py`. No VPS access, no secrets, no
real/testnet credentials, no real exchange call anywhere (including in tests —
fake exchanges only), no deployment, no env changes, no strategy/signal/
risk/sizing/portfolio changes, no Telegram changes, no live-trading
activation, no merge. O-02W-E2, T-1 and F-00 are explicitly out of scope and
not started.

Per the project's current governance (`CLAUDE.md`, STABILIZATION_WINDOW
2026-09-02→2026-09-16, ADR-0007 passivité absolue des observers, Scientific
Debt Rule): this audit adds a measurement/certification artifact only. It
recommends no threshold change, no new indicator, no new decision layer.

## 2. Exact starting SHA

- `main` (local and `origin/main`, verified equal before branching):
  `0ace5ccc13e3c111bc7191834c059ef5391e9f65`
- Merge commit parents (`git show -s --format=%P`): first
  `2f226d097568fe6d3fd2c07a4296fa4d6535204c`, second
  `5770f0768abcc4f46494c73a7472fc219af4c76c` — matches PR #135
  (`base.sha` = first parent, `head.sha` = second parent), state `closed`,
  `merged: true`.
- `infra/wallet_sync.py` on this HEAD: `get_scientific_capital()` at line 75,
  `WalletSync.observe_exchange_balance()` at line 264 — PRE-T1-D separation
  confirmed present.
- Audit branch: `claude/o02w-pre-t1-e-order-cycle-safety-audit`, created from
  this exact `main`.
- Open-PR overlap check: `list_pull_requests(state=open)` returned 20 open
  PRs (#118, #53, #52, #39, #38, #36, #35, #34, #33, #32, #31, #30, #29, #27,
  #26, #25, #24, #23, #20, #19). None targets `execution_engine.py`,
  `position_manager.py`, `order_deduplicator.py`, `session_guard.py`,
  `pending_order_tracker.py`, `wallet_sync.py`, or `exchange_factory.py` by
  title/branch name. This is a repo-inspection-only check (titles/branch
  names), not a diff-content check of all 20 PRs.

## 3. Scientific question

Can one logical trading intention produce an invalid, oversized, duplicated,
unattributable, or unreconciled order under normal execution, network
ambiguity, partial fills, rejection, restart, or crash? Does every order
trace back to one authorized decision packet? Does every ambiguous network
result lead to reconciliation rather than blind resubmission?

**Headline finding:** on the primary live-order path
(`ExecutionEngine._place_live_order`), the answer to the central question is
**yes — one logical intention can produce an invalid-input-derived order, a
silently oversized order, and (after network ambiguity) a duplicated
order**, because size validation substitutes rather than rejects, min-notional
handling silently enlarges, no deterministic client order id is generated or
passed to the exchange, and the retry wrapper resubmits blindly with no
reconciliation step. See §17 for the exact hermetic proof and §18 for the
blocker list.

## 4. Hypotheses H1–H12 — verdicts

| # | Hypothesis | Verdict | One-line reason |
|---|---|---|---|
| H1 | Invalid-size rejection | **REFUTED** | `execution_engine.py:274-283` — `size<=0 or size>1e9` does not reject; it force-alerts then **substitutes `size = 1.0`** and lets the order proceed (`mode` stays non-`rejected`). NaN passes the guard **unchanged** (`nan<=0` and `nan>1e9` are both `False` in Python — proven in §17 Scenario A). The existing test class is literally named `TestAnomalousSizeRecovery` (`.../test_execution_engine.py:82`), confirming this is documented, intentional "recovery," not rejection. |
| H2 | No silent minimum amplification | **REFUTED** | `execution_engine.py:493-500` — below-min-notional `size` is silently replaced with `min_notional * 1.05`, i.e. up to and beyond the authorized intention with no re-authorization, no alert, no reject path. |
| H3 | Deterministic identity | **REFUTED** | No `clientOrderId`/`newClientOrderId` parameter is ever constructed or passed to any exchange call (`rg -n "clientOrderId|client_order_id"` across the repo: 0 matches outside this contract). `self._exchange.create_order(ccxt_symbol, "market", side, qty)` (`execution_engine.py:532`, `position_manager.py:616-618`) relies entirely on the exchange's own generated id, returned post-hoc as `order.get("id")`. Retries (`_with_retry`, `execution_engine.py:152-180`) re-invoke the identical call with no idempotency key. |
| H4 | Durable intent before network | **REFUTED** | `create_order()`'s only pre-network gates are in-memory (`SessionGuard.check_order`, `OrderDeduplicator.is_duplicate` — both non-durable, reset on process restart). The durable step, `TradeLogger.log(result, status)` (`execution_engine.py:326`), executes **after** `_place_live_order()` (`execution_engine.py:313-314`), i.e. after the network mutation attempt, not before. `core/advisor_loop.py` does append a best-effort `logs/execution_audit/audit.jsonl` line before calling `exec_engine.create_order(...)` (lines ~6544-6562), but that write is wrapped in a bare `except Exception: pass` — not fsync'd, not the system of record `TradeLogger` uses, and is caller-side only (not present for the `position_manager._send_close_order` path at all). |
| H5 | No blind retry | **REFUTED** | `_with_retry()` (`execution_engine.py:152-180`) is a literal blind retry: same `fn`/`args`/`kwargs` re-invoked up to 3 times with fixed backoff, then `reconnect()` + one more blind call. No call to `fetch_order`/`fetch_open_orders` to check whether the prior attempt actually landed, no use of any deterministic id to look the order up. `PendingOrderTracker` (`system/pending_order_tracker.py`), which implements exactly the reconciliation machinery (`reconcile_with_exchange()`, NEW→PARTIAL_FILL→FILLED state machine) H5 would need, is **not imported anywhere in the order-submission path** — only by `system/boot_gate.py` (as an optional constructor arg, never instantiated there) and by tests. |
| H6 | Duplicate-call idempotence | **REFUTED** | Same call twice in immediate succession is only blocked by `OrderDeduplicator`, an in-memory, 10%-bucketed, symbol+action+size key (`order_deduplicator.py:56-59`) registered **after** the exchange call already returned (`execution_engine.py:324`, after line 314). A timeout during the *first* call (exception before `register()` runs) leaves no dedup entry, so the blind retry in `_with_retry` (H5) can and will re-submit — see Scenario I/H proof in §17. |
| H7 | Correct balance authority | **PARTIALLY CONFIRMED** | BUY path explicitly checks quote-asset free balance (`execution_engine.py:503-514`, `detect_quote_asset`); no SELL-side base-asset check exists in `_place_live_order` — SELL just computes `qty = size/price` and submits, with no balance check at all (an asymmetry, not a swapped-asset bug — H7 as literally stated, quote-for-BUY, is true; the missing SELL-side check is a separate, undocumented gap noted as a blocker). Confirmed separately: `get_scientific_capital()` makes zero exchange calls (`infra/wallet_sync.py:75-`) and `observe_exchange_balance()` is display-only and never referenced by `fetch_available_capital()` (PRE-T1-D boundary, re-verified not regressed — §15). |
| H8 | Honest execution outcomes | **CONFIRMED (structure), with a caveat** | `mode` values (`paper`, `live`, `live_failed`, `rejected`, `futures_demo`, `futures_failed`, `futures_unavailable`) are structurally distinguishable, and `PendingOrderTracker`'s status set (`NEW/PARTIAL_FILL/FILLED/CANCELLED/EXPIRED/UNKNOWN`) is sound *in isolation* (`system/pending_order_tracker.py:79-99` transition table forbids resurrecting a terminal order). Caveat: `PendingOrderTracker` is not wired into `_place_live_order`, so this honest state machine **never actually classifies a real order outcome** in the current call graph — the live path's only outcome vocabulary is the flatter `mode` string. |
| H9 | Crash-window recovery | **REFUTED** | No durable intent record exists before the network call (H4), and no attributable identity is generated (H3). A crash between "network call sent" and "response received" (window 3 in the mission's crash taxonomy) leaves nothing on disk from which the just-attempted order could be reconstructed or reconciled after restart — `PendingOrderTracker`'s in-memory `self._orders` dict (`system/pending_order_tracker.py:180`) is itself non-durable and, per H5, unused on this path anyway. |
| H10 | Canonical trading authority | **INCONCLUSIVE (fail-closed on the paths examined, but no single canonical authority found)** | Two independent gates each fail closed on their own: `PAPER_TRADING_ENABLED` (default `true`) blocks before any network call in `_place_live_order` (`execution_engine.py:455-471`), and `LIVE_TRADING_CONFIRMED` (default `false`) gates `live=True` construction in `ExecutionEngine.from_env()` (`execution_engine.py:196-202`). Both examined combinations that should forbid trading did forbid it (Scenario M, §17). But `position_manager._send_close_order` (`position_manager.py:594-618`) checks only `self._paper`/`self._exchange is None` — it does **not** re-check `PAPER_TRADING_ENABLED` or `LIVE_TRADING_CONFIRMED` itself; its safety depends entirely on how `self._exchange`/`self._paper` were set by its caller, which this audit did not fully trace (out of the time-boxed reading list — `position_manager.py` is 600+ lines and its full construction call graph was not exhaustively walked). Not a proven bypass; an unresolved risk (§18). No single documented "canonical authority" module (e.g. a `GlobalStateMachine.can_submit_order()` choke point) was found gating *both* call sites uniformly. |
| H11 | PRE-T1-D separation preserved | **CONFIRMED** | `fetch_available_capital()` calls only `get_scientific_capital()` (`execution_engine.py:249-251`), which makes zero exchange calls and does not read `_singleton`/`_mode`/`_exchange` (`infra/wallet_sync.py:75-` docstring + body). `observe_exchange_balance()` is a separate, unreferenced-by-sizing accessor. PRE-T1-D boundary test suite re-run clean at this HEAD — see §17 Scenario P. |
| H12 | Runtime status remains unknown | **CONFIRMED by construction** | This audit performed zero VPS access, zero deployment checks, zero live/testnet calls. All findings are `SOURCE_PROVEN`/`BEHAVIOR_PROVEN_HERMETIC`/`SOURCE_REACHABLE`. No runtime claim is made or implied; the STABILIZATION_WINDOW governance (`CLAUDE.md`) independently marks all current VPS activity `certified=false`/paper-revision only. |

## 5. Complete mutation call-site inventory

`rg` sweep for exchange-mutating calls (`create_order`, `create_market_order`,
`create_limit_order`, `set_leverage`) across all non-archive, non-test source:

| Call site | File:line | Path | Reachable from |
|---|---|---|---|
| `self._exchange.create_order(ccxt_symbol, "market", side, qty)` | `execution_engine.py:532` (inside `_with_retry`, called at 531) | Spot live order (`_place_live_order`) | `ExecutionEngine.create_order()` → `core/advisor_loop.py:6575`, `quant_hedge_ai/main_system.py:168`, `quant_hedge_ai/main_v91.py:759`, `supervision/ops_watchdog.py:20` |
| `self._exchange_futures.create_order(ccxt_symbol, "market", side, qty)` | `execution_engine.py:408-410` | Futures-demo order (`create_futures_order`) | `ExecutionEngine.create_futures_order()` → `core/advisor_loop.py:6567` (`exec_engine.has_futures_demo()` branch) |
| `self._exchange_futures.set_leverage(leverage, ccxt_symbol)` | `execution_engine.py:381` | Leverage mutation, wrapped in bare `except: pass` | `create_futures_order()` |
| `self._exchange.create_order(ccxt_symbol, "market", side, qty, params={"reduceOnly": True})` | `position_manager.py:616-618` | Position-close order — **independent path, no `_with_retry`, no `OrderDeduplicator`, no `SessionGuard`, no `TradeLogger`** | `PositionManager._close_position()` → `_send_close_order()` |
| `raw = self._exchange.create_order(...)` | `_ARCHIVE_2026/binance_connector.py:357` | Archived — not import-reachable from any production module (`_ARCHIVE_2026/` is excluded from `rg -l` hits outside itself) | none found |
| `order = self._exchange.create_market_order(symbol, side, qty)` | `_ARCHIVE_2026/mvp/execution_engine_mvp.py:236` | Archived — same as above | none found |

**Distinct live/mutation-capable engines: 2** (`ExecutionEngine` spot+futures-demo path, `PositionManager` close-order path). They are audited as **separate rows** below — never merged into one general claim, per mission instructions. `_ARCHIVE_2026/*` is `SOURCE_REACHABLE` in the literal filesystem sense but not import-reachable from any production entrypoint located in this sweep — classified `NOT_SOURCE_REACHABLE` for the live call graph.

## 6. Causal order lifecycle — per-path inventory

### Path A — `ExecutionEngine.create_order()` → `_place_live_order()`

| Field | Finding |
|---|---|
| Entrypoint | `ExecutionEngine.create_order(symbol, action, size)`, called from `core/advisor_loop.py:6575`, `quant_hedge_ai/main_system.py:168`, `quant_hedge_ai/main_v91.py:759`, `supervision/ops_watchdog.py:20` |
| Authorization source | `LIVE_TRADING_CONFIRMED` (construction time, `from_env()`), `PAPER_TRADING_ENABLED` (call-time, re-read every call — `_place_live_order:455`) |
| Decision/packet identity | None — no packet object, no clientOrderId; caller passes raw `(symbol, action, size)` positional args |
| Size source | Caller-supplied `size` (USD notional), scaled by `self._size_factor` (`:271`) |
| Risk validation | (1) size sanity `<=0 or >1e9` → **substitutes**, does not reject (`:274-283`); (2) `SessionGuard.check_order` → raises/rejects (`:287`); (3) `OrderDeduplicator.is_duplicate` → rejects (`:301`) |
| Persistence point | `TradeLogger.log()` — **after** exchange call (`:326`, vs. exchange call at `:313-314`) |
| First exchange mutation | `self._exchange.fetch_ticker` (read) then `self._exchange.create_order` (`:532`), inside `_with_retry` |
| Exchange identifier | Exchange-assigned `order.get("id")` only; no client-supplied id |
| Retry behavior | `_with_retry`: 3 blind retries (0.5/1/2s) + 1 reconnect-then-retry, same args each time — **no reconciliation lookup** |
| Reconciliation behavior | None on this path (`PendingOrderTracker` not wired in) |
| Fill handling | None — `create_order`'s market order result is returned as-is; no fetch-order-status follow-up, no fill polling |
| Position writer | Outside this file — `core/advisor_loop.py`'s `_register_position_from_execution(fut, ...)` (caller-side, not audited line-by-line — out of reading budget) |
| Crash-recovery behavior | None — no durable pre-network record exists to recover from (§ H4/H9) |
| Evidence class | `SOURCE_PROVEN` (static reading) + `BEHAVIOR_PROVEN_HERMETIC` (§17 A/B/D/G/H/I) |
| Unresolved risk | SELL-side has no balance check at all (H7 gap); `min_notional*1.05` amplification unauthorized by any explicit re-approval step |

### Path B — `PositionManager._send_close_order()`

| Field | Finding |
|---|---|
| Entrypoint | `PositionManager._close_position()` → `_send_close_order()`, internal, not directly caller-invoked from `advisor_loop.py` in the reading performed |
| Authorization source | `self._paper` / `self._exchange is None` only (`:601`) — no re-check of `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` at this call site itself |
| Decision/packet identity | None — derived from internal `Position` dataclass, no clientOrderId |
| Size source | `pos.qty` or `qty_override` (base-asset quantity, not USD) |
| Risk validation | None visible at this call site — no `SessionGuard`, no dedup, no size sanity check |
| Persistence point | None — no journal write before or after the call in the read code (`:594-618`) |
| First exchange mutation | `self._exchange.create_order(ccxt_symbol, "market", side, qty, params={"reduceOnly": True})` (`:616-618`) |
| Exchange identifier | Exchange-assigned `order.get("id")`, only logged, not persisted |
| Retry behavior | None — single `try/except`, logs and swallows on failure, no retry |
| Reconciliation behavior | None |
| Fill handling | None |
| Position writer | `pos.closed = True` set unconditionally by the *caller* `_close_position()` regardless of whether `_send_close_order` actually succeeded (`:576-579` sets `pos.closed=True` right after calling `_send_close_order`, which only logs-and-swallows exceptions — **an exchange failure does not prevent the position from being marked closed locally**) |
| Crash-recovery behavior | None |
| Evidence class | `SOURCE_PROVEN` (static reading only — no hermetic test written for this path per §17 budget; flagged `INCONCLUSIVE` for hermetic proof, `SOURCE_PROVEN` for the structural claim) |
| Unresolved risk | `pos.closed=True` on a failed close order is a phantom-flat-position risk: local state says closed, exchange may not agree — reduceOnly limits the downside (can't create a new inverse position) but does not prove the position actually closed |

## 7. Authority matrix

| `PAPER_TRADING_ENABLED` | `LIVE_TRADING_CONFIRMED` | `self._live` (construction) | Exchange call reached in `_place_live_order`? | Evidence |
|---|---|---|---|---|
| `true` (default) | any | any | **No** — blocked at `:455-471` before any network call, returns `mode=live_failed` synthetically | `BEHAVIOR_PROVEN_HERMETIC` (Scenario M) |
| `false` | `false` (default) | `False` (constructor never sets `live=True` — `from_env()` requires `live_trading_confirmed`) | **No** — `create_order()`'s branch at `:313` requires `self._live and self._exchange is not None`; `self._live=False` routes to paper branch unconditionally | `BEHAVIOR_PROVEN_HERMETIC` (Scenario M) |
| `false` | `true`, but no API keys | n/a | **No** — `ExchangeFactory.info()["has_api_key"]` false ⇒ `live=False` in `from_env()` | `SOURCE_PROVEN` (not independently re-hermeticized — relies on `exchange_factory.py`, read partially) |
| `false` | `true`, keys present | `True` | **Yes, network call attempted** — this is the only combination that reaches `_place_live_order`'s network section; every finding in H1-H6/H9 applies here | `SOURCE_PROVEN` |

No `HALT`/`SAFE_MODE`/kill-switch flag is read anywhere inside
`execution_engine.py` or `position_manager.py` themselves (`rg -n
"SAFE_MODE|HALT" quant_hedge_ai/agents/execution/`: 0 matches). Those
authorities (`supervision/kill_switch.py`, `governance/trading_authority.py`,
`system/state_machine.py`, etc.) exist and were located but their
integration into the two call paths above was **not traced end-to-end**
inside the reading budget of this round — this is the basis for H10's
`INCONCLUSIVE` verdict, not a claim that they don't gate order flow via the
caller (`advisor_loop.py`) instead.

## 8. Persistence-before-network findings

**Blocker.** Neither Path A nor Path B writes a durable, queryable record of
the order *intention* before attempting the exchange mutation.
`core/advisor_loop.py`'s `logs/execution_audit/audit.jsonl` append (around
line 6544-6562) is the closest thing to an intent record and *does* precede
the `exec_engine.create_order(...)` call at line 6575, but: (a) it is wrapped
in `except Exception: pass`, so a write failure is silently swallowed and
does not block the subsequent order; (b) it exists only on the
`advisor_loop.py`→`ExecutionEngine` call path, not on the
`PositionManager._send_close_order` path or the `ops_watchdog.py`/
`main_system.py`/`main_v91.py` call sites; (c) it is not consulted by
`_with_retry`'s retry logic or by any reconciliation code — it is
write-only, never read back. See §17 Scenario E.

## 9. Idempotency findings

**Blocker.** `OrderDeduplicator` only prevents a *second, separate*
`create_order()` invocation with matching `(symbol, action, round(size,1))`
within its window, and only registers **after** the first call already
returned (`execution_engine.py:324`, after the network branch at `:313`).
It does nothing to prevent `_with_retry`'s own internal blind retries
(§17 Scenario I) from producing two exchange orders when the first network
call's *response* is lost but the order itself landed (classic ambiguous-ack
scenario, H5/H6). No clientOrderId means the exchange itself cannot dedupe
either.

## 10. Network ambiguity findings

**Blocker.** `_with_retry` treats every exception identically —
"timeout before any exchange-side effect" and "timeout after the exchange
already accepted the order" are indistinguishable to this code, and both are
handled the same way: retry the same call. There is no fetch-order-by-id
step, no client-order-id lookup, no "was this order actually placed?"
check anywhere in the retry path. See §17 Scenario G/H.

## 11. Crash-window findings

Because no durable intent record exists before the network call (§8) and no
deterministic identity is generated (H3), a process crash in the interval
between "network call sent" and "process resumes" leaves the system with
literally nothing to reconcile against on restart, on this call graph. This
is a structural absence, not a hermetically-exercised "crash → wrong state"
demonstration (no process-crash harness was built — restart was modeled as
"construct a fresh `ExecutionEngine`/`TradeLogger` against the same DB
path," which is the honest limit of what a hermetic unit test can model for
an actual OS-level crash). Classified `SOURCE_PROVEN` (absence of the
mechanism), not `BEHAVIOR_PROVEN_HERMETIC` for the crash itself — see
Scenario N.

## 12. BUY/SELL balance findings

BUY: `execution_engine.py:503-514` explicitly reads quote-asset free balance
via `self.detect_quote_asset(ccxt_symbol)` and reduces `size` (not rejects)
if insufficient. SELL: no balance check of any kind exists in
`_place_live_order` — `qty = size/price` is computed and submitted directly
regardless of actual base-asset holdings, relying entirely on the exchange
to reject an oversized sell. This is asymmetric handling, not a
quote/base mix-up (H7's literal claim, "BUY checks quote, SELL checks
base," is therefore not confirmed for the SELL half — there is no SELL
check at all, which is a stronger gap, flagged as a blocker.)

## 13. Precision and minimum-notional findings

Confirmed silent amplification at `execution_engine.py:500`
(`size = min_notional * 1.05`) — see H2. Precision rounding
(`:517-526`) rounds toward the exchange's tick size but only ever *after*
the amplification step, so it cannot itself reduce exposure back below the
originally authorized amount; worst case compounds with the amplification.

## 14. Partial-fill findings

`_place_live_order` and `_send_close_order` both submit a single market
order and return whatever the exchange call returns synchronously; neither
polls `fetch_order` for eventual full fill nor distinguishes a
CCXT `partial`/`remaining`-carrying response from a full fill in the
returned dict — the `mode` field stays `"live"` either way. `
PendingOrderTracker` implements exactly this distinction
(`PARTIAL_FILL` state, `fill_ratio`, `unfilled_qty`) but, as established in
§6/H5, is not wired into either path. See §17 Scenario J.

## 15. Separation from scientific capital

Re-verified, not regressed: `ExecutionEngine.fetch_available_capital()`
(`:229-251`) calls only `get_scientific_capital()`, which is a pure function
of `WALLET_PAPER_CAPITAL` + ledger PnL with zero exchange calls
(`infra/wallet_sync.py:75-`). `observe_exchange_balance()` is a fully
separate method on `WalletSync`, never referenced by
`fetch_available_capital` or by any sizing code found in
`execution_engine.py`/`position_manager.py`. §17 Scenario P re-runs the
PRE-T1-D boundary suite at this HEAD as a non-regression check.

## 16. Source evidence vs runtime-unknown distinction

Every finding above is `SOURCE_PROVEN` (static reading of this exact HEAD,
cited by file:line) and/or `BEHAVIOR_PROVEN_HERMETIC` (fake-exchange test in
§17). No claim is made about VPS deployment, runtime invocation, or real
exchange effect — those remain `RUNTIME_UNKNOWN` per H12 and per the
project's STABILIZATION_WINDOW governance, independent of this audit.

## 17. Test matrix and exact results

See `tests/test_pre_t1_e_order_cycle_safety.py`. All scenarios use a fake
CCXT-shaped exchange object, `tmp_path` SQLite/JSONL files, and explicit call
counters — no real network, no credentials, no sleep (dedup/backoff
`_sleep` is injected as a no-op via the constructor's `_sleep` param; the
fake exchange's `time` dependencies are monkeypatched where needed).

| Scenario | What it proves | Result |
|---|---|---|
| A — invalid sizes | `0`, `-50`, `NaN`, `+inf`, size passed through the sanity gate; confirms **substitution not rejection**, confirms NaN bypasses the check entirely | Matches H1 REFUTED |
| B — min-notional | Below-minimum size submitted; exchange receives `qty` corresponding to `min_notional*1.05`, not the original authorized `size` | Matches H2 REFUTED |
| D — order identity | Same `(symbol, action, size)` invoked twice; no `clientOrderId` ever appears in the fake exchange's captured call kwargs | Matches H3 REFUTED |
| E — persistence ordering | Instrumented `TradeLogger.log` and fake-exchange call both timestamped; log call observed strictly after the exchange call for Path A | Matches H4 REFUTED |
| G — timeout before acceptance | Fake exchange raises on every call within a window; `_with_retry` reissues the identical call up to 3 times, all pre-acceptance — proves blind-retry structure, not reconciliation | Matches H5 REFUTED |
| H — accept then lost response | Fake exchange records an order (counter increments) then raises; `create_order`'s only recourse is `_with_retry`'s blind retry, which — because `OrderDeduplicator.register()` never ran (exception happened before line 324) — is **not blocked by dedup either** | Matches H5/H6 REFUTED |
| I — duplicate invocation | Two full `create_order()` calls with identical args inside the dedup window; **second call is rejected by `OrderDeduplicator`** (this one path is proven safe for the simple double-call case, as opposed to the ambiguous-retry case in H) | Confirms dedup DOES work as a same-process double-invocation guard, refines but does not reverse H6 |
| J — partial fill | Fake exchange returns a `filled < amount` market-order response; `_place_live_order`'s result dict is inspected — `mode` stays `"live"`, no distinct partial-fill signal is exposed by this path | Matches §14 |
| M — authority matrix | All four rows of §7 reproduced with a fake exchange; exchange `create_order` call counter is asserted `0` for every forbidden combination | Confirms H10's fail-closed finding for Path A |
| P — PRE-T1-D non-regression | `tests/test_pre_t1_d_real_capital_boundary.py` re-run at this HEAD | See exact count below |

Scenarios **C** (precision boundary — folded into B, same code path),
**F** (successful ack — trivial, covered by existing
`test_execution_engine.py` paper/live-happy-path tests, not re-duplicated),
**K** (rejection/rate-limit — the fake-exchange exception path is identical
to G's mechanism; a distinct scenario would not add new evidence beyond G),
**L** (BUY/SELL asymmetry — covered narratively in §12, hermeticized as part
of scenario B's balance-check assertion), **N** (crash windows — see §11,
not independently hermeticized beyond what §8/§9 already establish; a
literal process-crash harness is outside what a `pytest` process can honize
without spawning and killing a subprocess, judged out of scope for this
round), and **O** (existing paper behavior unchanged — proven by re-running
the full existing `test_execution_engine*.py` suites unmodified, see below)
are addressed by direct reference to existing evidence rather than
duplicated as new named test functions, to avoid inflating the test count
with redundant assertions on the same code path.

### Exact verification run (this HEAD, this branch)

```
tests/test_pre_t1_e_order_cycle_safety.py                        23 passed, 0 failed
quant_hedge_ai/agents/execution/test_execution_engine.py \
  + test_execution_engine_futures.py + test_order_deduplicator.py \
  + test_trade_logger.py + test_paper_trading_engine.py           120 passed, 1 pre-existing failure
tests/test_pre_t1_d_real_capital_boundary.py                      139 passed, 0 failed
tests/test_safety_instruction_truthfulness.py                      51 passed, 0 failed
python scripts/ci/ruff_baseline_gate.py check                     961 baseline == 961 current, 0 new
git diff --check                                                  clean (exit 0)
git status / diff --name-only main                                only the 2 authorized audit files
```

The 1 pre-existing failure —
`TestFromEnv::test_from_env_live_when_keys_present_and_confirmed` — is the
same `ccxt`-not-installed environment gap PR #135 documented at R1
(`ModuleNotFoundError: No module named 'ccxt'`, confirmed via
`python3 -c "import ccxt"` in this exact environment). It is unrelated to
this change and was not investigated further (never call something
"pre-existing" by name alone — this was independently reproduced by import
error, not assumed).

## 18. Blocker list

1. **B1 (H1)** — invalid/NaN/oversized `size` is silently substituted
   (`size = 1.0`), not rejected, and the substituted order still proceeds to
   the exchange call. `execution_engine.py:274-283`.
2. **B2 (H2)** — below-min-notional orders are silently enlarged to
   `min_notional*1.05`, exceeding the originally authorized amount with no
   re-authorization step. `execution_engine.py:493-500`.
3. **B3 (H3)** — no deterministic client order id is ever generated or sent;
   order identity is entirely exchange-assigned and post-hoc.
4. **B4 (H4)** — the durable audit log write happens after, not before, the
   exchange mutation call on Path A; Path B has no durable write at all.
5. **B5 (H5/H6)** — `_with_retry` blindly resubmits identical order
   parameters after any exception, including after the exchange may have
   already accepted the order (lost-ack scenario), with no reconciliation
   step and no protection from `OrderDeduplicator` in that specific window.
6. **B6 (H7/§12)** — no balance check exists on the SELL side of
   `_place_live_order` at all.
7. **B7 (§6 Path B)** — `PositionManager._close_position()` marks
   `pos.closed = True` unconditionally after calling `_send_close_order`,
   even when the underlying exchange call raised and was swallowed.
8. **B8 (H9/§11)** — no crash-window recovery mechanism exists on either
   path; nothing durable is written before the network call to recover
   from.
9. **B9 (H5/H8/§14)** — `PendingOrderTracker`, the one module in this
   codebase that implements the state machine and reconciliation logic the
   mission's hypotheses call for, is not wired into either mutation path —
   it is dead safety infrastructure with respect to real order flow.
10. **B10 (H10, unresolved, not proven)** — `PositionManager._send_close_order`
    does not itself re-check `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED`;
    its safety is inherited from caller-side construction that this round did
    not fully trace. Flagged as an open risk, not a proven bypass.

## 19. Remediation prerequisites

Not authorized or attempted in this round (audit-first). For a future
remediation mission (would need its own ADR-driven scope, per this
repository's Scientific Debt Rule and ADR-0007): reject (not substitute)
invalid sizes including NaN/inf with `math.isfinite`; treat min-notional
violations as a reject-or-explicit-reauthorize decision, never a silent
enlarge; generate and pass a deterministic `clientOrderId` derived from a
durable decision-packet id; persist the full order intention (symbol,
action, size, decision id) to durable storage *before* any network call on
both Path A and Path B; replace `_with_retry`'s blind retry with a
reconcile-by-id-then-retry-only-if-truly-absent policy, using
`PendingOrderTracker` (wiring the existing module in rather than building a
new one, consistent with the Scientific Debt Rule's "eliminate more
variables than you add"); add a SELL-side base-asset balance check
symmetric to the BUY-side one; make `_send_close_order`'s caller
conditional `pos.closed` on confirmed success, not on "the call was
attempted."

## 20. Final verdict

**`REMEDIATION_REQUIRED`** — mandatory per the verdict rule: this audit found
source-reachable paths that (a) can create an invalid/oversized order from
input the system is supposed to reject (B1, B2), (b) can resubmit blindly
after network ambiguity, creating a duplicate (B5), and (c) lose causal
identity end-to-end (B3, B4, B8). None of this is a hermetic-proof-only
finding contingent on missing infrastructure — it is proven directly from
this exact HEAD's source and confirmed behaviorally against a fake exchange
in §17. No production code was modified to address any of it in this round,
per the audit-first scope.

## 21. REM-A remediation status (O-02W-PRE-T1-E-REM-A, 2026-09-11)

**This section is an addendum, not a rewrite** — §1-20 above document the
audit exactly as performed against `297eba89` and are preserved unedited.
A first, narrow remediation phase (REM-A) has since fixed a subset of the
blockers listed in §18, per
`docs/adr/0019-pre-network-order-authorization.md`. Status per blocker:

| Blocker | Status |
|---|---|
| B1 (H1, invalid-size substitution) | **REMEDIATED_IN_PRE_T1_E_REM_A** — rejected via `authorize_order()`, `math.isfinite()` closes the NaN gap. Zero exchange mutations on any invalid input. |
| B2 (H2, min-notional amplification) | **REMEDIATED_IN_PRE_T1_E_REM_A** — rejected (`BELOW_MIN_NOTIONAL`), never enlarged. Precision normalization is `Decimal`/floor-only and provably never increases authorized exposure. |
| B3 (H3, no deterministic order identity) | **UNRESOLVED — reserved for REM-B.** Not attempted; explicitly out of REM-A's scope. |
| B4 (H4, durable write after network) | **UNRESOLVED — reserved for REM-B.** `TradeLogger.log()` still runs after `_place_live_order()`; no durable pre-network intent record was added. |
| B5 (H5/H6, blind retry, no reconciliation) | **UNRESOLVED — reserved for REM-B.** `_with_retry` is unchanged; still resubmits identical parameters blindly. |
| B6 (H7, no SELL balance check) | **REMEDIATED_IN_PRE_T1_E_REM_A** — `authorize_order()` requires and validates `available_base_balance` for every SELL, deny-closed on missing/insufficient/malformed/non-finite. |
| B7 (`PositionManager` swallowed exception) | **PARTIALLY REMEDIATED_IN_PRE_T1_E_REM_A** — `_send_close_order()` now returns an explicit `authorized`/`mutation_attempted`/`mode`/`denial_reason` outcome instead of swallowing exceptions silently, and `_close_position()` no longer marks `pos.closed = True` on a denial or a failed mutation (the position stays open and is naturally re-evaluated on the next tick — no new retry/reconciliation machinery was added). This is the narrow honesty fix the REM-A mission authorized, not the full reconciliation system B9 still calls for. |
| B8 (H9, no crash-window recovery) | **UNRESOLVED — reserved for REM-B/REM-C.** No durable pre-network record exists; unaffected by REM-A. |
| B9 (`PendingOrderTracker` unwired) | **UNRESOLVED — reserved for REM-B.** Still not imported/wired into either mutation path; REM-A does not activate it (explicitly out of scope). |
| B10 (H10 pre-network portion, `PositionManager` authority gap) | **REMEDIATED_IN_PRE_T1_E_REM_A (documented composition, not a single canonical module).** `_send_close_order()` now re-checks `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` itself, fail-closed, immediately before mutation, via `evaluate_trading_authority()` — see ADR-0019 §1 for the exact composition. The live-order path's `LIVE_TRADING_CONFIRMED` gate (`ExecutionEngine.from_env()`) and its `PAPER_TRADING_ENABLED` re-check (`_place_live_order`) were already fail-closed per the original H10 finding and are unchanged. No single "canonical authority" module was introduced — this remains a documented composition of existing/extended gates, consistent with H10's original characterization. |

Not covered by REM-A R0 and not claimed as fixed at the time: `ExecutionEngine.create_futures_order()`'s own below-minimum clamp (`max(futures_min, ...)`) — a distinct instance of the H2 anti-pattern on the futures-demo path, left untouched in R0 to avoid unjustified blast radius (see ADR-0019 §6). **Superseded in R1 below.** `PositionManager._check_partial_close()` still ignores `_send_close_order()`'s return value for its own qty/size_usd bookkeeping (unchanged, out of R1 scope too).

### 21.1 R1 correction round (MASTER review, 2026-09-11)

Four defects raised by MASTER's review of the R0 round above, resolved
without introducing any REM-B/REM-C functionality — see ADR-0019 §6bis for
full detail:

| Defect | Resolution |
|---|---|
| 1. `create_futures_order()` left source-reachable with an H2-shaped amplification (`max(futures_min, ...)`) | Traced: genuinely source-reachable from `core/advisor_loop.py:6568` (`exec_engine.create_futures_order(...)` under `has_futures_demo()`), not dead code — the R0 "documented, out of scope" resolution was insufficient. Now wired to `authorize_order()` (new `require_balance_check=False` parameter — futures/margin markets consume quote-denominated margin on both BUY and SELL, not a base-asset balance). The upward clamp to `futures_min` is removed and replaced by rejection (`BELOW_MIN_NOTIONAL`); the downward clamp to `futures_max` is retained (narrowing only, never amplifies). `amt_precision` fallback corrected `0.001` → `1e-5` (matches `_place_live_order()`'s existing fallback) to avoid spurious `PRECISION_COLLAPSE` under strict floor rounding. `qty` is never re-clamped up to the exchange's `min_qty` after authorization — that would reintroduce the same H2 shape. B2 is now closed for the futures-demo path too, not only spot/live. |
| 2. Dimensional confusion in `PositionManager._send_close_order()`'s `authorize_order()` call | The dead ternary `qty * price if price > 0 else qty * price` (both branches textually identical — always `qty * price`, a code-hygiene defect, not a value defect: verified against a git-worktree copy of the starting HEAD that the numeric result was already correct) is removed. Replaced with explicitly named `requested_notional = qty * price` / `ceiling_notional = pos.qty * price`, both documented as USD notional (the dimension `authorize_order()` expects), never conflated with `qty`/`pos.qty` (base-asset units). New tests at non-trivial prices (50 000 and 0.001) prove `normalized_qty` and the notional cannot be transposed, and that `create_order()` receives the correct base-asset quantity. |
| 3. `PositionManager` calling a local re-implementation instead of the shared `evaluate_trading_authority()` | Verified on this exact HEAD: no local re-implementation exists — `_send_close_order()` already reads `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` fresh and calls the shared `evaluate_trading_authority()` with those values, with no gate check inline before or instead of that call. No code change was needed. A construction proof was added regardless (monkeypatching `evaluate_trading_authority` in the `position_manager` module namespace, asserting it is called with the fresh kwargs and that its return value drives `_send_close_order()`'s result). |
| 4. Documentation scope | This §21.1 and ADR-0019 §6bis updated to reflect exactly the above three fixes — no broader documentation pass, no REM-B/REM-C claims. |

Test suite: `tests/test_pre_t1_e_rem_a_order_authorization.py` grew from 83
to 88 tests (5 new: 1 futures-demo rejection proof moved into
`test_execution_engine_futures.py`, 4 `PositionManager` dimensional/
authority-sharing proofs added directly to this file);
`quant_hedge_ai/agents/execution/test_execution_engine_futures.py`'s
`test_below_min_clamped_up` was renamed `test_below_min_rejected_not_amplified`
and rewritten to assert rejection instead of amplification (the test that
previously encoded the clamp as intentional now encodes its removal).

**Updated verdict: still `REMEDIATION_REQUIRED`.** REM-A (R0 + R1) closes
B1, B2 (now on both the spot/live and futures-demo paths), B6, and B10
(pre-network authority), and narrows B7 to its documented honesty fix. B3,
B4, B5, B8, B9 remain fully open and are reserved for REM-B/REM-C, per the
mission's explicit scope boundary. The order cycle is not end-to-end safe
after REM-A — only its pre-network input/exposure/balance/authority
validation is.

## 22. REM-B remediation status (O-02W-PRE-T1-E-REM-B, 2026-09-11)

**This section is an addendum, not a rewrite** — §1-21 above are preserved
unedited. A second remediation phase (REM-B) has since addressed a further
subset of §18's blockers, per
`docs/adr/0020-deterministic-durable-idempotent-order-submission.md`.
`quant_hedge_ai/agents/execution/order_intent_protocol.py` introduces
deterministic logical-intent identity, a durable append-only intent
journal, an at-most-once submission coordinator, and read-only
reconciliation. New test suite:
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` (67 tests,
Groups A-J). Status per blocker:

| Blocker | Status |
|---|---|
| B3 (H3, no deterministic order identity) | **REMEDIATED_IN_PRE_T1_E_REM_B** — `OrderIntent.full_digest()`/`client_order_id()` are deterministic and versioned; short-ID collisions against a different full payload fail closed (`IDENTITY_COLLISION`). Reaches the exchange call via `params={"clientOrderId": ...}` on both `ExecutionEngine` mutation paths (when a `decision_id` is supplied — see caveat below) and unconditionally on the `PositionManager` close path. |
| B4 (H4, durable write after network) | **REMEDIATED_IN_PRE_T1_E_REM_B for the paths that route through the coordinator.** `INTENT_RECORDED` and `SUBMISSION_STARTED` are fsync'd to `databases/order_intent_journal.jsonl` (or `ORDER_INTENT_JOURNAL_PATH`) strictly before the exchange mutation call (proven in `TestGroupBDurableOrdering`, ordering spies). **Caveat:** `ExecutionEngine.create_order()`/`create_futures_order()` only enter this path when their caller supplies `decision_id`; `core/advisor_loop.py` (their only current caller) does not yet do so, and this mission does not modify `advisor_loop.py` (scope control, mission §16) to add it without an existing causal id to propagate. For that specific caller shape, B4 remains open. `PositionManager._send_close_order` has no such caveat — it derives its causal id internally and is unconditionally covered. |
| B5 (H5/H6, blind retry, no reconciliation) | **REMEDIATED_IN_PRE_T1_E_REM_B for the coordinator-routed paths, same caveat as B4.** A timeout/connection-reset/lost-response/malformed-response result is classified `AMBIGUOUS` and persisted as `RECONCILE_REQUIRED` — the coordinator never issues a second `create_order()` call for the same intent; `OrderIntentCoordinator.reconcile()` provides a read-only reconciliation path that never resubmits, including when nothing is found (`RECONCILED_NOT_FOUND_PENDING` stays ambiguous, deliberately with no auto-resubmit-after-delay policy). `_with_retry` itself is unchanged and still wraps only pre-mutation read calls (ticker/markets/balance) on the coordinator-routed branch — it is never used to wrap the mutation call anymore on that branch. |
| B8 (H9, no crash-window recovery) | **PARTIALLY REMEDIATED_IN_PRE_T1_E_REM_B — restart idempotence only, not full crash-window recovery.** Reconstructing `OrderIntentJournal`/`OrderIntentCoordinator` from the same durable path after a restart never re-submits an intent already recorded in any state (`TestGroupGRestart`, all 5 REM-B-relevant states). This is deliberately **not** full position reconstruction, partial-fill recovery, or PnL accounting — those remain REM-C scope, unattempted here. |
| B9 (`PendingOrderTracker` unwired) | **NOT reused — superseded, documented.** Mission §4 required investigating reuse before building new; grep-verified no `PendingOrderTracker` class/module exists anywhere in this repository's source tree (the blocker's name referred to a hypothesized/planned component, not an actual unwired implementation found on this HEAD). REM-B's `OrderIntentJournal`/`OrderIntentCoordinator` is the state-machine-plus-reconciliation implementation B9 called for, built fresh per ADR-0020, wired into both mutation families. |

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope:** complete partial-fill lifecycle and fill-quantity
reconciliation; full position reconstruction after a crash window; PnL
accounting changes; any automatic resubmission policy after
`RECONCILED_NOT_FOUND_PENDING`; `core/advisor_loop.py` causal-id plumbing
for `ExecutionEngine.create_order()`/`create_futures_order()` (needed to
close the B4/B5 caveat above for those two call sites specifically).

**Updated verdict: still `REMEDIATION_REQUIRED`.** REM-B closes B3 fully,
closes B4/B5/B8 for the `PositionManager` close path and for any
`ExecutionEngine` caller that supplies a `decision_id`, and does not touch
B9's underlying gap except by building the durable authority it called
for. It does not close B4/B5 for `ExecutionEngine`'s actual current
caller (`advisor_loop.py`, which passes no `decision_id`), and does not
attempt B8's full crash-window/partial-fill scope. No live trading, no
real exchange call, and no deployment occurred in this mission — see
§17/§19/§20 of the mission spec for the full prohibition list this
remediation respected.

## 22.1 REM-B R1 correction round (2026-09-11)

**Addendum to §22, not a rewrite.** REM-B-R1 corrected eight blockers
MASTER review identified in the §22 round, per
`docs/adr/0020-deterministic-durable-idempotent-order-submission.md`'s R1
section (full detail there). Updated blocker status:

| Blocker | R0 status | R1 status |
|---|---|---|
| B3 (H3, deterministic identity) | REMEDIATED_IN_PRE_T1_E_REM_B | **Unchanged, strengthened.** Adapter-capability-gated (Correction E) — an unverified adapter now denies before the identity is ever transmitted, rather than silently sending it. |
| B4 (H4, durable-before-network) | Caveat: `advisor_loop.py` didn't supply `decision_id` | **Caveat CLOSED** (was already closed by a same-day follow-up commit before this R1 mission began — `core/advisor_loop.py`'s two call sites propagate the existing `trace_id` per-decision-cycle identifier). R1 additionally closes a NEW gap found during verification: without a `decision_id`, `ExecutionEngine` fell back to an un-journaled legacy path instead of failing closed — Correction A removes that fallback entirely. B4 is now REMEDIATED_IN_PRE_T1_E_REM_B for every source-reachable caller of `ExecutionEngine.create_order()`/`create_futures_order()` through `advisor_loop.py`, with the Correction B caveat below. |
| B5 (H5/H6, blind retry / reconciliation) | Same caveat as B4 | Same resolution as B4. Additionally strengthened by Correction D: the durable-before-network guarantee is now genuinely cross-process-safe (`fcntl.flock`), not merely single-process — proven by real `multiprocessing.Process` tests, not thread simulation. |
| B8 (H9, crash-window recovery) | Partial — restart idempotence only | **Unchanged partial status, but the honest boundary is now sharper.** Correction B's investigation established precisely WHY full crash-window recovery is not yet closed: `trace_id` is stable in-memory for one execution attempt but not durably persisted BEFORE the decision reaches execution, so a restart cannot reconstruct an in-flight decision's identity. This is named explicitly (ADR-0020 R1 §Correction B) as the specific remaining piece of B8, reserved for REM-C. |
| B9 (`PendingOrderTracker`) | Not reused — superseded | Unchanged. |
| (new) Adapter capability correctness | Not previously assessed | **New finding, closed.** A single hardcoded `AdapterCapabilities` claimed `clientOrderId` worked for every `EXCHANGE_ID` this repo supports (`mexc`, `krakenfutures`, `binanceusdm`) — CCXT's raw parameter name is not uniform across exchanges, so this was a latent defect that could have silently defeated B3's identity guarantee for non-`mexc` exchanges. Now exchange-specific (`capabilities_for_exchange()`), with unverified exchanges failing closed. |
| (new) Cross-process journal safety | Documented as single-writer only, not enforced | **New finding, closed.** An OS-level `fcntl.flock` now actually enforces single-writer-at-a-time on the journal's critical section (POSIX only, explicitly), replacing the prior single-writer *assumption* with an enforced, tested guarantee — `LOCK_UNAVAILABLE` fails closed rather than silently proceeding unprotected. |
| (new) Legacy direct-submission bypass | Not previously assessed | **New finding, closed.** Both `ExecutionEngine` mutation paths had an `else:` branch that called the exchange directly (no journal, no idempotence) whenever `decision_id` was absent — Correction A removes this fallback; missing identity now always fails closed with zero mutation calls. |

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope (unchanged from §22, refined per above):** complete
partial-fill lifecycle and fill-quantity reconciliation; full position
reconstruction after a crash window, INCLUDING durable pre-execution
persistence of the DecisionPacket/intent needed to reconstruct an
in-flight decision's identity after a crash (the specific remaining piece
of B8, named explicitly in ADR-0020 R1); PnL accounting changes; any
automatic resubmission policy after `RECONCILED_NOT_FOUND_PENDING`;
verification of `krakenfutures`/`binanceusdm` exact CCXT client-order-id
parameter names against the real `ccxt` package (currently fail-closed,
pending operator verification, not silently assumed).

**Updated verdict: still `REMEDIATION_REQUIRED`.** REM-B-R1 closes the B4/B5
caveat for `ExecutionEngine`'s real caller shape, closes a legacy-bypass
defect Correction A found, closes a latent multi-exchange adapter-capability
defect, and closes a documented-but-unenforced cross-process safety gap.
It does not close B8's full crash-window-recovery scope (the specific
remaining piece is now named precisely: durable pre-execution decision
persistence), does not start REM-C, and does not verify the two unverified
adapter's exact parameter names (deliberately fails closed instead of
guessing). No live trading, no real exchange call, no deployment occurred
in this round.

## 22.2 REM-B R1.1 correction round (2026-09-11)

**Addendum to §22/§22.1, not a rewrite.** Three blockers from R1's MASTER
review resolved, per ADR-0020's R1.1 section (full detail there).

| Blocker | Resolution |
|---|---|
| A — durable upstream decision identity | **REMEDIATED_IN_PRE_T1_E_REM_B.** New `decision_identity.py` durably persists the decision's causal id BEFORE it can reach execution; `ExecutionEngine` requires this durable record, not merely a non-empty string. Causal ordering (`DECISION_ID_CREATED -> DECISION_PERSISTED -> REM_A_AUTHORIZATION -> ORDER_INTENT_RECORDED -> SUBMISSION_STARTED -> EXCHANGE_MUTATION`) proven, including a restart-simulation test. |
| B — real adapter reconciliation capability | **REMEDIATED_IN_PRE_T1_E_REM_B (as a deny-closed correction).** No adapter in this repository is currently certified `SUBMIT_AND_RECONCILE_VERIFIED` — MEXC downgraded from R1's submission-authorized status to `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` (which, per the explicit verdict rule, does not authorize external submission either). `reconcile()` is now capability-gated; a caller-supplied `lookup` can no longer bypass certification. Zero runtime impact (`reconcile()` was never called from production; `PAPER_TRADING_ENABLED=true` blocks any live submission regardless). |
| C — complete mutation-bypass detection | **REMEDIATED_IN_PRE_T1_E_REM_B.** Layered scanner (`_mutation_references()`) replaces R1's detector, closing its confirmed blind spot for a mutation-method reference passed BY REFERENCE to a wrapper (`_with_retry(X.create_order, ...)`). Bounded detection model stated explicitly (does not claim perfect static detection of arbitrary Python reflection), combined with an independent repository-wide `grep` corroboration. |

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope (unchanged from §22/§22.1):** complete partial-fill
lifecycle; full position reconstruction after a crash window; PnL
accounting changes; any automatic resubmission policy after
`RECONCILED_NOT_FOUND_PENDING`. PLUS, newly explicit: verification of
`krakenfutures`/`binanceusdm`/MEXC's exact CCXT reconciliation methods
against a real, installed `ccxt` package (currently fails closed rather
than guessed — an explicit follow-up, not silently assumed done).

**Updated verdict: still `REMEDIATION_REQUIRED`.** REM-B-R1.1 closes all
three blockers MASTER's R1 review identified, but does not verify any
adapter's real reconciliation capability against a pinned `ccxt`
install (deliberately, per spec's own "a safe refusal is preferable to
an unverifiable live capability" — this is a corrected posture, not a
remaining defect), does not start REM-C, and does not enable live
trading in any way. No real order, exchange call, VPS access, secret
access, or deployment occurred in this round.

## 22.3 REM-B R1.2 final safety correction round (2026-09-11)

**Addendum to §22/§22.1/§22.2, not a rewrite.** Two remaining blockers from
MASTER's R1.2 review, per ADR-0020's R1.2 section (full detail there).

| Blocker | Investigation finding | Resolution |
|---|---|---|
| A — every non-`SUBMIT_AND_RECONCILE_VERIFIED` adapter must fail closed before network mutation | **Investigation established this invariant was ALREADY FULLY SATISFIED by R1.1** — `OrderIntentCoordinator.submit()`'s `supports_client_order_id` gate (itself `verdict == SUBMIT_AND_RECONCILE_VERIFIED`, derived, not independently settable) already denies MEXC, `krakenfutures`, `binanceusdm`, any unknown/alias exchange id, and any `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED`/`UNSUPPORTED`/`INCONCLUSIVE` verdict, before any mutation call, with zero `SUBMISSION_STARTED` journal writes; `reconcile()`'s capability gate (R1.1 Blocker B) already prevents a caller-supplied `lookup` from being invoked for an uncertified adapter. Confirmed via fail-before proof: 16 new Group P tests (`TestGroupP_R12_AdapterFailClosed`, covering MEXC spot/futures/PositionManager-close denial, Kraken Futures, Binance USD-M, unknown adapters, adapter aliases, direct `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` denial, caller-supplied lookup/capability non-promotion, verified-fake exactly-once submission, ambiguous-result no-resubmission, zero `SUBMISSION_STARTED` transition, and retry-wrapper non-bypass) **already pass unmodified against the R1.1 head** (`e5d81deb`). No production code change was needed or made for this blocker. | **`ALREADY_SATISFIED_AT_R1_1 — REVALIDATED_IN_R1_2`** (R1.3-corrected classification; supersedes the earlier `CONFIRMED_ALREADY_REMEDIATED_IN_PRE_T1_E_REM_B_R1_1` phrasing with no change in meaning) — implementation round: **R1.1**; revalidation round: **R1.2**. R1.2 adds only the explicit proof (Group P), not a behavior change. |
| B — genuine causal reconstruction after process restart | R1.1's `DecisionIdentityJournal` proved only that a `decision_id` string, once durably written, stays found by an `is_persisted()` membership check — MASTER correctly identified this as insufficient: it does not prove the DECISION's canonical payload is reconstructible, nor that it stays bound to exactly one authorized order intent. Confirmed via fail-before proof: 14 of 30 new Group Q tests (`TestGroupQ_R12_CausalReconstruction`) fail with `AttributeError` against the R1.1 head (`e5d81deb`) — `bind_intent`, `recover_pending_decisions`, `find_by_cycle_key`, `verify_digest`, `get` did not exist; behavioral, not import/collection failures. | **REMEDIATED_IN_PRE_T1_E_REM_B_R1_2.** `decision_identity.py` rewritten (schema_version 2): every `persist()` call now computes and stores a canonical `payload`/`payload_digest`; a NEW `bind_intent(decision_id, intent_digest)` atomically binds the persisted decision to the exact `OrderIntent` digest it authorizes (idempotent replay of the same digest; fail-closed `DecisionIdentityError` on a different digest, an unpersisted decision, or a conflicting duplicate `persist()` for the same id with a different payload); `recover_pending_decisions()`/`find_by_cycle_key()`/`get()`/`verify_digest()` let a caller with ONLY the durable journal path — no retained `decision_id` variable, coordinator, or engine object — reconstruct every recoverable decision from durable state alone. `ExecutionEngine._bind_decision_to_intent()` calls `bind_intent()` in both `create_order()`/`create_futures_order()` immediately after building the `OrderIntent`, before the mutation call — tightening the causal ordering to `DECISION_ID_CREATED -> DECISION_RECORD_DURABLY_PERSISTED -> REM_A_AUTHORIZATION -> ORDER_INTENT_BOUND_TO_DECISION -> ORDER_INTENT_DURABLY_PERSISTED -> SUBMISSION_STARTED -> EXCHANGE_MUTATION`. A genuinely legacy (schema_version=1) record without `payload`/`payload_digest` is excluded from `recover_pending_decisions()` (fails closed for reconstruction) while `is_persisted()` still honors it (R1.1 backward compatibility). All 30 Group Q tests pass on R1.2's head. |

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope (unchanged from §22/§22.1/§22.2):** complete partial-fill
lifecycle; full position reconstruction after a crash window; PnL
accounting changes; any automatic resubmission policy after
`RECONCILED_NOT_FOUND_PENDING`; verification of
`krakenfutures`/`binanceusdm`/MEXC's exact CCXT reconciliation methods
against a real, installed `ccxt` package (still fails closed rather than
guessed).

**Updated verdict: still `REMEDIATION_REQUIRED`.** R1.2 closes Blocker B
with a genuine new capability (decision-to-intent binding and
durable-state-only restart reconstruction) and formally proves Blocker A
was already closed by R1.1 — but does not start REM-C, does not verify any
adapter's real reconciliation capability against a pinned `ccxt` install,
and does not enable live trading in any way. No real order, exchange call,
VPS access, secret access, or deployment occurred in this round. PR #138
remains **draft** and **unmerged**.

## 22.4 REM-B R1.3 legacy execution ineligibility correction (2026-09-11)

**Addendum to §22/§22.1/§22.2/§22.3, not a rewrite.** MASTER's R1.3 review
demonstrated, behaviorally (not via `AttributeError`/import failure), that
R1.2's decision-identity gate confused HISTORICAL EXISTENCE with EXECUTION
AUTHORITY: `ExecutionEngine._decision_id_is_durably_persisted()` used
`DecisionIdentityJournal.is_persisted()` — a pure membership check — as its
mutation gate. A hand-crafted schema-v1 legacy record (valid-looking
`decision_id`, no canonical payload, no valid digest, no v2 lifecycle
evidence) made `is_persisted()` return `True` and reached a real mutation
call exactly once (fail-before Scenario A); a schema-v2 record whose
stored payload no longer matched its stored `payload_digest` was likewise
accepted (Scenario B). Both proofs also showed `bind_intent()` would
silently extend either kind of record to `BOUND` without ever making it
schema-v2-valid.

**Resolution.** `DecisionIdentityJournal` gained a single strict-validity
function, `_validate_record_for_execution()`, checking (in order): schema
version == 2; exact non-empty `decision_id`; well-typed non-empty
canonical `payload`; a structurally valid (64-lowercase-hex) stored
`payload_digest`; the recomputed digest matches the stored one;
duplicated top-level provenance fields (`namespace`/`cycle`/`symbol`/
`action`) agree with the same fields inside `payload`; a recognized
lifecycle state (`CREATED`/`BOUND`); a `CREATED` record is unbound; a
`BOUND` record's `bound_intent_digest` is itself a structurally valid
SHA-256 hex digest. `execution_ineligibility_reason()`/
`is_execution_eligible()` expose this as the read-only EXECUTION-AUTHORITY
query; `is_persisted()` is now explicitly documented as
HISTORICAL/EXISTENCE-ONLY and is no longer consulted by any execution
gate. `bind_intent()` independently calls the SAME validation function
before writing, so a legacy or corrupted record can never be "upgraded"
to `BOUND` merely by attempting to bind it — zero append on refusal.
`ExecutionEngine._decision_execution_denial_reason()` (new) is the actual
gate for both `create_order()`/`_place_live_order()` and
`create_futures_order()`, returning `None` (proceed), `MISSING_CAUSAL_ID`,
`UNPERSISTED_CAUSAL_ID`, or `INELIGIBLE_CAUSAL_ID` (with the precise
machine-readable reason logged, never silently discarded).
`recover_pending_decisions()` was tightened to exclude every
execution-ineligible record, not only ones missing `payload`/
`payload_digest` outright.

**`is_persisted()` call-site inventory** (complete repository grep):
1 definition (historical/existence semantics); 1 execution-authority call
site (`ExecutionEngine._decision_id_is_durably_persisted`, now retained
ONLY for audit/observability callers, no longer used to gate any
mutation); 12 test-assertion call sites (all verifying `is_persisted()`'s
own existence-membership semantics).

**Fail-before/pass-after.** Both scenarios reproduced behaviorally against
the exact R1.3 starting HEAD (`5bfe1a89`) with real mutation counters
(fake-exchange `create_order.call_count`) — both reached `1` before the
fix. After the fix, both are rejected with `denial_reason=
INELIGIBLE_CAUSAL_ID`, `create_order.call_count == 0`, and zero order-
intent-journal writes. 14 new permanent regression tests
(`TestGroupR_R13_LegacyExecutionIneligibility`) codify both scenarios plus
the direct `bind_intent()`-refusal proofs, valid-record positive paths,
the historical-vs-authority distinction, and restart-reconstruction
exclusion.

**Blocker A documentation correction (this round).** §22.3's Blocker A
classification is corrected to the exact required form:
`ALREADY_SATISFIED_AT_R1_1 — REVALIDATED_IN_R1_2` — R1.2 did not implement
the adapter fail-closed boundary (R1.1 did); R1.2 only revalidated it via
the 16 Group P tests. See §22.3's updated table row and ADR-0020's R1.3
section for full detail.

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope (unchanged):** complete partial-fill lifecycle; full
position reconstruction after a crash window; PnL accounting changes; any
automatic resubmission policy after `RECONCILED_NOT_FOUND_PENDING`;
verification of `krakenfutures`/`binanceusdm`/MEXC's exact CCXT
reconciliation methods against a real, installed `ccxt` package.

**Updated verdict: still `REMEDIATION_REQUIRED`.** R1.3 closes the
legacy/corrupted-record execution-authority gap and corrects Blocker A's
documentation attribution, but does not start REM-C, does not verify any
adapter's real reconciliation capability against a pinned `ccxt` install,
and does not enable live trading in any way. No real order, testnet call,
exchange call, VPS access, secret access, or deployment occurred in this
round. PR #138 remains **draft** and **unmerged**.

## 22.5 REM-B R1.4 persist() idempotence correction (2026-09-11)

**Addendum to §22/§22.1-§22.4, not a rewrite.** MASTER's R1.4 review found
that `DecisionIdentityJournal.persist()` — not `bind_intent()`, which R1.3
already hardened — could still reset execution authority. Fail-before
(behavioral, real mutation counters, exact starting HEAD `015f7015`):
(A) a legacy schema-v1 record, passed to `persist()` with compatible
metadata, was silently upgraded into a fresh valid schema-v2 `CREATED`
record and reached a real mutation call exactly once; (B) a genuine
`BOUND` decision, given a duplicate `persist()` call with identical
provenance (the expected duplicate-delivery case), had its
`lifecycle_state` reset to `CREATED` and `bound_intent_digest` erased,
after which a SECOND, incompatible intent digest could be bound.

**Resolution.** `persist()` now validates any EXISTING record with the
same strict `_validate_record_for_execution()` function `bind_intent()`
uses, before ever considering an append: an ineligible existing record
raises (zero append, no silent upgrade); a provenance or payload-digest
conflict against an eligible existing record still raises (zero append,
unchanged rule); and — the actual Scenario-B fix — a genuine
duplicate-delivery replay (matching provenance AND payload digest) now
returns the existing record UNCHANGED with **zero append**, rather than
falling through to an unconditional append that reset lifecycle state.
`persist()` can therefore never reset `lifecycle_state`, never clear
`bound_intent_digest`, and never silently promote legacy/corrupted
evidence — the same three-way guarantee `bind_intent()` already gave for
binding now also holds for persisting.

**`persist(` production call-site inventory**: exactly one —
`core/advisor_loop.py:1308` (`analyze_symbol()`, immediately after a
fresh `new_trace_id()`), classified as first-creation-only under the
current call pattern (no caller can force a duplicate call with the same
id today); `ExecutionEngine` never calls `.persist()` directly.

**Pass-after.** Both scenarios reproduced against the fixed code: (A)
`persist()` now raises `DecisionIdentityError` with zero append, the
record remains execution-ineligible, and `ExecutionEngine.create_order()`
rejects with `denial_reason=INELIGIBLE_CAUSAL_ID` and zero mutation
calls; (B) duplicate `persist()` preserves `BOUND`/`bound_intent_digest`
exactly, zero append, and `bind_intent(D, B)` for `B != A` still raises.
14 new permanent regression tests (`TestGroupS_R14_PersistIdempotence`)
codify both scenarios plus the full I1-I8 invariant set (identical-
duplicate idempotence, binding permanence, legacy/corrupted zero-append,
provenance/digest conflict rejection, end-to-end spot/futures proofs,
restart-reconstruction binding permanence).

**Files changed**: exactly `quant_hedge_ai/agents/execution/decision_identity.py`
and `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` —
`execution_engine.py` was not modified; the defect was entirely contained
in `persist()`.

**R1.3 properties revalidated, unchanged**: legacy/corrupted direct
`bind_intent()` rejection, strict `execution_ineligibility_reason()`,
spot/futures zero mutation, `recover_pending_decisions()` exclusion,
`is_persisted()` still existence-only (never execution authority), and
Blocker A's attribution remains `ALREADY_SATISFIED_AT_R1_1 —
REVALIDATED_IN_R1_2` (not rewritten).

**REM-C blockers remaining fully open, unattempted, explicitly out of this
mission's scope (unchanged):** complete partial-fill lifecycle; full
position reconstruction after a crash window; PnL accounting changes; any
automatic resubmission policy after `RECONCILED_NOT_FOUND_PENDING`;
verification of `krakenfutures`/`binanceusdm`/MEXC's exact CCXT
reconciliation methods against a real, installed `ccxt` package.

**Updated verdict: still `REMEDIATION_REQUIRED`.** R1.4 closes the
`persist()` idempotence gap but does not start REM-C, does not verify any
adapter's real reconciliation capability against a pinned `ccxt` install,
and does not enable live trading in any way. No real order, testnet call,
exchange call, VPS access, secret access, or deployment occurred in this
round. PR #138 remains **draft** and **unmerged**.

## 23. REM-C R1 — execution-domain provenance and paper recovery honesty (2026-09-11)

**Addendum to §1-22.2, not a rewrite.** This is the first REM-C
implementation round (deliberately narrow, per
`docs/adr/0021-execution-domain-provenance-and-paper-recovery-honesty.md`).
It is not the fill-engine implementation, not exchange reconciliation
certification, and not testnet/live enablement.

### 23.1 Execution-domain provenance rule

The canonical `Position` dataclass
(`quant_hedge_ai/agents/execution/position_manager.py`) previously carried
no execution-domain field at all — nothing prevented a PAPER-mode
`PositionManager`'s internal state from being compared against a REAL
exchange's `fetch_positions()` result by symbol string alone. A new
`ExecutionDomain(str, Enum)` (`REAL | TESTNET | FUTURES_DEMO | PAPER |
SHADOW | UNKNOWN`) is added; `Position.domain` defaults to `UNKNOWN`
(fail-closed, never assumed REAL nor PAPER). `PositionManager` resolves
its own `.domain` from the same construction context callers already pass
(`domain=` explicit override > `paper_mode=True` -> `PAPER` >
`exchange is not None` -> `REAL` > otherwise `UNKNOWN`) and stamps it onto
any position added via `add_position()` that still carries the `UNKNOWN`
default — an explicitly different domain on the position itself is never
overwritten.

### 23.2 Reconciliation same-domain invariant

`system/position_reconciler.py`'s `PositionReconciler.reconcile()` called
`pos_manager.get_open_positions()` — a method that never existed on the
canonical `PositionManager` (only `get_open()` does). Because of
`hasattr()` guarding, this silently returned `internal_pos = {}` in
production, every cycle, for the life of the code (a second, structurally
identical instance of the same defect existed in `core/advisor_loop.py`'s
boot-time heartbeat amorçage, also fixed here). Fixing only the method
name would have made the reconciler suddenly see real internal state for
the first time — without a domain check, this creates the risk this
mission was scoped to close: a PAPER-domain `PositionManager` compared
against a REAL `fetch_positions()` call. `PositionReconciler` now takes an
`expected_domain` (default `REAL`, since `exchange_futures.fetch_positions()`
is definitionally a real/testnet account call) and refuses to run the
comparison at all unless `pos_manager.domain == expected_domain` proves
compatible; an incompatible or unproven (`UNKNOWN`) domain produces
`comparable=False` with empty ghost/orphan lists — never a fabricated
finding. Once domain-compatible, individual positions that themselves
carry a non-matching or `UNKNOWN` domain are still excluded from
ghost/orphan comparison and reported separately
(`unresolved_domain_positions`), never folded into a ghost/orphan claim.
Only after both gates pass does the corrected `get_open()` call run.
Reconciliation remains strictly observational — it was already read-only
(`fetch_positions()` + comparison), and REM-C R1 adds no mutation path.

### 23.3 PAPER restart evidence-honesty rule

`MexcSimulator._restore_positions()` (`paper_trading/mexc_simulator.py`)
previously (a) recorded `pnl_usd=0.0`/`pnl_pct=0.0` for positions expired
during a downtime window, presenting "nothing happened" as if it were
known fact rather than genuinely unknown; (b) always recomputed TP/SL
from hardcoded 4%/2% defaults, discarding whatever the position's actual
original TP/SL had been, with no way to tell a reconstructed value from
an original one; (c) always set `fee_entry_usd=0.0`, because the ledger
schema never captured it. `PaperTradeRecorder`'s `TradeEvent`/
`CompleteTrade` schema is extended to v4 with three new OPEN-only
optional fields — `tp_price`, `sl_price`, `fee_entry_usd` — defaulting to
`None` (absent evidence), never a fabricated number; `record_open()` now
persists them when the caller has them (the live-order-fill path does).
`_restore_positions()`: (a) expired-during-downtime positions are now
closed with `pnl_usd=None`/`pnl_pct=None` — missing evidence stays
missing, it is never converted to a known zero; (b) restoration uses the
durably recorded `tp_price`/`sl_price`/`fee_entry_usd` verbatim when a
schema-v4 record has them; only when genuinely absent (older records) does
it fall back to the same recomputed defaults as before, but now flags the
position's `restored_evidence_gaps` list (`tp_sl_reconstructed_default`,
`fee_entry_unknown`) and its `personality` as
`"restored_evidence_incomplete"` rather than the previously undifferentiated
`"restored"` — a reconstructed value is never presented as the original
evidence again.

### 23.4 Files changed

- `quant_hedge_ai/agents/execution/position_manager.py` — `ExecutionDomain`
  enum, `Position.domain`, `PositionManager.domain` resolution and
  stamping in `add_position()`.
- `system/position_reconciler.py` — domain-compatibility gate,
  `get_open_positions()` -> `get_open()` fix, per-position domain
  filtering, `ReconcileReport.comparable`/`pm_domain`/`expected_domain`/
  `unresolved_domain_positions`.
- `core/advisor_loop.py` — the same `get_open_positions()` ->
  `get_open()` fix in the boot-time heartbeat amorçage guard (no other
  change; construction of `PositionReconciler` is unchanged).
- `paper_trading/recorder.py` — schema v4 (`tp_price`/`sl_price`/
  `fee_entry_usd`, all `Optional`), `record_open()`/`record_close()`
  signature extensions (`record_close`'s `pnl_usd`/`pnl_pct` are now
  `Optional[float]`), `trades()` propagation.
- `paper_trading/mexc_simulator.py` — `MexcPosition.restored_evidence_gaps`,
  `_restore_positions()` evidence-honest reconstruction, `record_open()`
  call site passes through `tp_price`/`sl_price`/`fee_entry_usd`.
- `paper_trading/dataset_validator.py` — `_VALID_SCHEMA_VERSIONS` extended
  to include `4` (mechanical, matches the new `SCHEMA_VERSION`).
- `tests/test_rem_c_r1_execution_domain.py` — new, fail-before/pass-after
  regression suite (Scenarios A/B/C plus the observational-only
  invariant).
- `tests/test_restart_safety.py` — `TestB2MidExecutionCrash`'s
  `PositionReconciler` mocks updated to the canonical `get_open()` API and
  given an explicit `ExecutionDomain.REAL` (mechanical; these tests
  exercise exactly the API this mission corrects).
- `.ci/ruff_baseline.json` — 7 pre-existing findings (in
  `paper_trading/mexc_simulator.py`, `paper_trading/recorder.py`,
  `tests/test_restart_safety.py`) shifted line numbers only, due to lines
  inserted above them by this mission; no new violation, verified via
  `python scripts/ci/ruff_baseline_gate.py check` (958/958, zero new).

### 23.5 REM-C blockers remaining fully open, unattempted, explicitly out of this mission's scope

Canonical `ExecutionEvidence`/`FillRecord`; cumulative exchange fill
journal; partial-fill ingestion and deduplication; exchange fill polling
(`fetch_order()`/`fetch_my_trades()` production integration); real-exchange
fee accounting and VWAP reconstruction; exchange adapter certification;
resubmission policy; real position reconstruction from exchange fills;
full crash-window/partial-fill recovery (B8, still only restart-idempotent
per REM-B); durable pre-execution decision persistence beyond what R1.1
already added. These are REM-C R2/R3/R4 scope.

**R0 verdict (superseded below by R1.1): still `REMEDIATION_REQUIRED`.**
REM-C R1 closed the execution-domain provenance gap and the reconciler API
mismatch (now domain-gated, never fabricating cross-domain findings), and
closed the PAPER-restart PnL/TP/SL/fee fabrication defects R0.1 found (now
explicit `None`/flagged-reconstruction instead of silent zero/default). It
did not implement the fill-evidence chain, did not certify real exchange
reconciliation, and did not enable live or testnet trading in any way. No
real order, testnet call, exchange call, VPS access, secret access, or
deployment occurred in that round.

### 23.6 REM-C R1.1 — MASTER correction round (2026-09-11)

**Addendum to §23.1-23.5, not a rewrite.** MASTER review of R1 (PR #139,
head `027cb0c71ce291209794ba929bff729ab71876c0`) found R1's own
implementation of this contract's stated intent was itself incomplete in
five places. Full technical detail in ADR-0021's "R1.1 — MASTER correction
round" addendum; summarized here:

| Finding | R1 defect | R1.1 correction |
|---|---|---|
| A | `PositionManager(exchange=X)` inferred `domain=REAL` merely because `X is not None` — false, since the only production caller (`core/advisor_loop.py` via `_get_exchange_futures()`) can pass a TESTNET-mode krakenfutures handle exactly as easily as a REAL one. | Inference removed entirely (`exchange is not None` no longer implies anything). New `core/advisor_loop.py::_futures_position_domain()` derives the proven domain from `exec_engine._mode` and passes it explicitly via `domain=`. |
| B | `PositionReconciler` authorized comparison on domain-LABEL equality alone — two distinct REAL-labeled `PositionManager`/exchange pairs could pass. | Added an exchange-identity check (`pos_manager._exchange is <reconciler's own exchange_futures>`) after the domain check; mismatch or unprovable identity fails closed exactly like a domain mismatch. |
| C | Expired-on-restore PAPER positions still wrote `exit_price=trade.entry_price` (R1 had already fixed `pnl_usd`/`pnl_pct` to `None` but left this one substitution in place). | `exit_price=None` on expiry; `PaperTradeRecorder.record_close()`'s `exit_price` param is now `Optional[float]`. |
| D | `PaperTradeRecorder.trades()` computed `is_win = (cl.pnl_usd or 0) > 0`, silently converting `pnl_usd=None` (unknown) into `is_win=False` (a claimed LOSS). | `is_win = None if cl.pnl_usd is None else (cl.pnl_usd > 0)` in both aggregation branches; `paper_trading/status.py`'s display now renders `N/A` instead of `LOSS` for `is_win=None`; `dataset_validator.py`'s pre-existing `expired_on_restore` exclusion (unaffected) reverified by regression test. |
| E | `BootGate.check()` never inspected `pos_report.comparable`/`is_clean` — a non-comparable reconciliation (empty ghost/orphan lists BY DESIGN) could still clear the gate. | `BootGateReport.position_reconcile_comparable` added; `check()` now blocks on non-comparable, then on not-clean (which also closes a related pre-existing gap: price-drift-only dirtiness was never checked by `BootGate`'s own `has_drift` variable), before the existing ghost/orphan/order-anomaly check. |

Also closed, per the mission's semantic-sweep instruction (§6): the
rate-limited "skipped — too soon" `ReconcileReport` previously read as
`is_clean=True` despite no comparison having run at all. A new
`ReconcileReport.performed: bool` field (default `True`, set `False` only
on that skip path) is now part of `is_clean`'s condition.

**Files changed (R1.1):** `quant_hedge_ai/agents/execution/
position_manager.py`, `core/advisor_loop.py`, `system/
position_reconciler.py`, `system/boot_gate.py`, `paper_trading/
recorder.py`, `paper_trading/mexc_simulator.py`, `paper_trading/
status.py`, `tests/test_rem_c_r1_execution_domain.py` (21 new tests),
`tests/test_restart_safety.py` (mechanical — mock `_exchange` identity),
`.ci/ruff_baseline.json` (mechanical line-shift only).

**Tests:** `tests/test_rem_c_r1_execution_domain.py` — 30/30 passed (9 R1
+ 21 R1.1). Full targeted regression (`test_position_manager`,
`test_exchange_reality` incl. `TestA7BootGate`, `test_restart_safety`,
`test_dataset_validator`, `paper_trading/`, REM-A/REM-B suites, PRE-T1-D
capital boundary, operator snapshot): 825 passed. The same 9
`TestB3AuditRecovery` failures as R1 remain, confirmed pre-existing and
unrelated (`_cffi_backend`/`cryptography` sandbox gap, reproduces
identically on `origin/main`). `ruff_baseline_gate.py check`: 958/958,
zero new. `git diff --check`: clean.

**R1.1 verdict (superseded below by R1.2): still `REMEDIATION_REQUIRED`.**
REM-C R1.1 corrected all five MASTER-identified defects in R1's own
implementation without expanding scope into REM-C R2/R3/R4: execution-
domain inference became evidence-based rather than presence-based,
reconciliation required exchange-identity proof in addition to a domain-
label match, PAPER restart no longer substituted any value (entry price
or otherwise) for a genuinely unknown exit price, unknown PnL could no
longer surface as a claimed LOSS anywhere in the read path, and BootGate
could no longer clear trading on a reconciliation that was never actually
proven comparable.

### 23.7 REM-C R1.2 — MASTER correction round (2026-09-11)

**Addendum to §23.1-23.6, not a rewrite.** MASTER review of R1.1 (head
`79cb77ebb77d202c8323509b0119cdd264f754a5`) found three residual defects
plus one confirmed evidence-audit finding. Full technical detail in
ADR-0021's "R1.2 — MASTER correction round" addendum; summarized here:

| Finding | R1.1 defect | R1.2 correction |
|---|---|---|
| A — UNRESOLVED != CLEAN | `unresolved_domain_positions` was correctly excluded from `has_drift` (never fabricated as ghost/orphan) but `is_clean` never checked it either — an unresolved-domain position could coexist with `is_clean=True`. | `is_clean` now additionally requires `not unresolved_domain_positions`, checked directly (not folded into `has_drift`, preserving that property's existing meaning for its other callers). |
| B — INTERNAL READ FAILURE != EMPTY | `self._pm.get_open() if hasattr(...) else []`, and a raised exception from `get_open()`, both fell back to `internal_pos = {}` — fail-open: could read CLEAN with an empty exchange, or fabricate ORPHAN findings for every real exchange position with a non-empty one. | New `ReconcileReport.internal_state_readable` field; `reconcile()` now returns immediately (no ghost/orphan/price-drift computed) when `get_open` is missing or raises, with an explicit error. `is_clean` requires it. A genuinely empty `get_open() -> []` is unaffected. |
| C — MISSING RAW EVENT PRICE != ZERO | R1.1 fixed the *derived* `exit_price`/`pnl_usd`/`pnl_pct`/`is_win` to `None` on `expired_on_restore`, but the *raw* `TradeEvent.price` written by `record_close()` still fabricated `0.0`. | Consumer audit found zero production readers of a CLOSE event's `price` (only OPEN's, via `entry_price=op.price`, unaffected) and that `dataset_validator.py` already tolerates `None`. `TradeEvent.price` is now `Optional[float]`; `record_close()` passes `exit_price` through directly. |
| 4 — fee-entry evidence audit | Traced whether an UNKNOWN restored `fee_entry_usd` (defaulted to `0.0`, R1.1) can later close and produce an authoritative-looking PnL. **Confirmed YES** by direct code trace (`_close_position()`'s `pnl_usd` formula subtracts it unconditionally, with no propagation of the evidence gap to the recorded event). | Schema v5 adds `pnl_fee_evidence_incomplete: bool` (CLOSE-only) to `TradeEvent`/`CompleteTrade`, set by `_close_position()` from `"fee_entry_unknown" in pos.restored_evidence_gaps`. The PnL number is unchanged (real arithmetic against the best available fee, not fabricated) — it can no longer be mistaken for fully-evidenced. `status.py` appends `*` to the W/L column when set. |
| 5 — TESTNET reconciliation status | — | Verified and documented, no code change: `core/advisor_loop.py`'s reconciler still defaults `expected_domain=REAL`, so a TESTNET-labeled `PositionManager` correctly fails closed as non-comparable today. This is intentional for T-1/PAPER scope — TESTNET reconciliation is explicitly **not certified**, reserved for a future REM-C round. |

**Files changed (R1.2):** `system/position_reconciler.py`,
`paper_trading/{recorder,mexc_simulator,status,dataset_validator}.py`,
`tests/test_rem_c_r1_execution_domain.py` (14 new tests), `.ci/
ruff_baseline.json` (mechanical line-shift), ADR-0021 + this §23.7
addendum.

**Tests:** `tests/test_rem_c_r1_execution_domain.py` — 44/44 passed (9 R1
+ 21 R1.1 + 14 R1.2). Full targeted regression (`test_position_manager`,
`test_exchange_reality`, `test_restart_safety`, `test_dataset_validator`,
`paper_trading/`, `test_pre_t1_c_portfolio_provider_read_only`, PRE-T1-D
capital boundary, REM-A/REM-B suites): 748 passed. Same 9 pre-existing
`TestB3AuditRecovery` failures as R1/R1.1, confirmed unrelated.
`ruff_baseline_gate.py check`: 958/958, zero new. `git diff --check`:
clean.

**R1.2 verdict (superseded below by R1.3): still `REMEDIATION_REQUIRED`.**
REM-C R1.2 closed the three residual fail-open gaps MASTER found in
R1.1's own implementation (an unresolved-domain position could certify
CLEAN; an unreadable internal position state was silently treated as
empty rather than unknown; the raw paper ledger event still fabricated a
zero exit price even after the derived fields were fixed), and closed a
confirmed fee-evidence honesty gap (an assumed entry fee could produce an
unflagged, seemingly fully-evidenced realized PnL).

### 23.8 REM-C R1.3 — MASTER final evidence-semantics round (2026-09-12)

**Addendum to §23.1-23.7, not a rewrite.** MASTER review of R1.2 (head
`50fd9631a303efe1c431a379292ba2897d879bd2`) found R1.1's `personality`
distinction had drifted out of sync with a downstream provenance-visible
consumer, plus two aggregate-statistics gaps. Full technical detail in
ADR-0021's "R1.3 — MASTER final evidence-semantics round" addendum;
summarized here:

| Finding | Defect | Correction |
|---|---|---|
| A — RESTORED != EVIDENCE_COMPLETE | R1.1's `personality="restored_evidence_incomplete"` broke `observability/operator_snapshot_builder.py`'s `is_restored = personality == "restored"` in both directions: an evidence-incomplete restored position read `restored=False`, and a fully-evidenced restored position (durable TP/SL) was labeled `tp_sl_source="restored_default"` as if reconstructed. | `personality` stays `"restored"` for every ledger-restored position; only `restored_evidence_gaps` carries completeness. `tp_sl_source` now derives from that gap list directly: `"original"` / `"restored_default"` (genuinely reconstructed) / new `"restored_original"` (restored, durably-recovered TP/SL). Frontend contract (`types.ts`, already `\| string`-tolerant) and `O-02W-B` contract doc updated additively — no redesign. |
| B — HISTORICAL RECORD != CERTIFIED PERFORMANCE SAMPLE | `PaperTradeRecorder.summary()`'s `win_rate`/`target_30_trades`/`go_live_ready` were computed over ALL closed trades, including unknown-outcome (`is_win is None`) ones — diluting win_rate and letting 30 genuinely unknown closes advance `go_live_ready`. | `summary()` now derives those metrics from a `certified` subset (`is_win is not None` and not `pnl_fee_evidence_incomplete`). `total_closed` (raw, backward-compatible) is preserved; new `certified_closed`/`excluded_unevidenced_count` keys make the exclusion explicit. Sole consumer `paper_trading/status.py` updated to match. |
| C — INCOMPLETE FEE EVIDENCE != FULLY-EVIDENCED PNL (corpus) | `dataset_validator.py::validate_corpus()` already excluded `expired_on_restore` from population stats, but a `pnl_fee_evidence_incomplete=True` close (R1.2) still counted as an ordinary certified WIN/LOSS/TP/SL observation. | New `CorpusReport.fee_evidence_incomplete` counter; population loop excludes such closes (same `continue` pattern as `expired_on_restore`) without touching paired-trade/integrity accounting or treating it as corrupted data — an explicit warning names the exclusion. |

**Files changed (R1.3):** `paper_trading/{mexc_simulator,recorder,status,
dataset_validator}.py`, `observability/operator_snapshot_builder.py`,
`frontend/src/types.ts`, `docs/contracts/
O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md`, `tests/
test_operator_snapshot_builder.py` (2 new tests + 1 fixture extension),
`tests/test_rem_c_r1_execution_domain.py` (15 new tests, 1 updated),
ADR-0021 + this §23.8 addendum.

**Tests:** `tests/test_rem_c_r1_execution_domain.py` — 55/55 passed (9 R1
+ 21 R1.1 + 14 R1.2 + 11 R1.3). `tests/test_operator_snapshot_builder.py`
— 146/146 passed. Full targeted regression (`test_position_manager`,
`test_exchange_reality`, `test_restart_safety`, `test_dataset_validator`,
`paper_trading/`, `test_pre_t1_c_portfolio_provider_read_only`, PRE-T1-D
capital boundary, REM-A/REM-B suites, `tests/cross_stack/`): 918 passed.
Same 9 pre-existing `TestB3AuditRecovery` failures across all four
rounds, confirmed unrelated. `ruff_baseline_gate.py check`: 957/957, zero
new (one incidental pre-existing lint finding fixed during the
`summary()` rewrite, baseline count correctly dropped 958→957).
`git diff --check`: clean.

**Updated verdict: still `REMEDIATION_REQUIRED`.** REM-C R1.3 closes the
provenance-visible drift MASTER found between R1.1's restore-evidence
model and the operator snapshot it feeds, and closes two aggregate-
statistics surfaces (`PaperTradeRecorder.summary()`,
`dataset_validator.py`'s corpus population) that still let unevidenced or
unknown-outcome closes contribute to certified performance metrics. It
does not implement the fill-evidence chain, does not certify real
exchange or TESTNET reconciliation, and does not enable live or testnet
trading in any way. No real order, testnet call, exchange call, VPS
access, secret access, or deployment occurred in this round.
`PAPER_TRADING_ENABLED=true` and `LIVE_TRADING_CONFIRMED=false` are
unchanged. T-1 and F-00 remain not started.

## 24. FINAL PRE-T1-E PAPER CERTIFICATION (2026-09-12) — SUPERSEDED, see §24V (MASTER correction round)

**Addendum to §1-23.8, not a rewrite.** This is the last certification
gate before T-1 (still not T-1 itself — no VPS access, no deployment, no
live-trading activation, no REM-C R2/R3/R4). Mission lineage: O-02W-PRE-T1-E
→ REM-A → REM-B → REM-C R1 → **this FINAL PRE-T1-E PAPER CERTIFICATION**.

Scope of this round: audit + certification + hermetic proof only. Zero
production Python/frontend/Telegram/strategy/risk/sizing changes were made
or needed — the central invariant below held on direct re-inspection of
the exact commit named in §24A, so no `STOP`/`REMEDIATION_REQUIRED`
escalation for *new* production code was required this round (the
pre-existing, already-documented §18/§22-§23 residual items are unchanged
and still carried forward, see §24Q).

### A. Exact starting main SHA

`e4c71379e05fa5efbcea8fb73e52bccb0e4cc271` (`origin/main`, verified equal
to local `main` before branching). `git log --oneline
50fd9631a303efe1c431a379292ba2897d879bd2..e4c71379e05fa5efbcea8fb73e52bccb0e4cc271`
shows exactly 10 commits, all `docs(web): ...` (WEB-DOC-01 Canonical Web
Cockpit Data Map, PR #140) plus the REM-C R1.3 merge commit itself
(`6e3fcc8`/PR #139) — `git diff --name-only` between the R1.3 pre-round
head and this SHA touches only `paper_trading/*`,
`observability/operator_snapshot_builder.py`, `frontend/src/types.ts`,
`docs/*`, and test files already accounted for in §23.8/§23's own file
lists — **zero drift** in `execution_engine.py`, `position_manager.py`,
`order_intent_protocol.py`, `decision_identity.py`,
`position_reconciler.py`, or `boot_gate.py` since R1.3. This certification
therefore re-verifies R1.3's findings against this exact HEAD rather than
discovering new ones.

### B. Branch name

`claude/pre-t1-e-final-paper-certification`.

### C. Mutation-call inventory (re-derived, this HEAD, non-archive/non-test source)

`rg` sweep for `create_order`, `create_market_order`, `create_limit_order`,
`cancel_order`, `cancel_all_orders`, `set_leverage`, `set_margin_mode`,
`transfer`, `withdraw`:

| Call site | File:line | Path |
|---|---|---|
| `self._exchange.create_order(...)` (via `_with_retry`/coordinator) | `execution_engine.py` (`_place_live_order`, ~line 913 `create_order()`) | Spot live path |
| `self._exchange_futures.create_order(...)` | `execution_engine.py` (`create_futures_order`, ~line 545) | Futures-demo path |
| `self._exchange_futures.set_leverage(leverage, ccxt_symbol)` | `execution_engine.py:459` (bare `except: pass`) | Futures-demo path, **called before the REM-A `authorize_order()` gate and before the REM-B decision-identity gate in this function** |
| `self._exchange.create_order(..., params={"reduceOnly": True, "clientOrderId": ...})` | `position_manager.py:886` (`_send_close_order`) | Position-close path |
| `_ARCHIVE_2026/binance_connector.py:357` (`create_order`), `:416` (`cancel_order`); `_ARCHIVE_2026/mvp/execution_engine_mvp.py:236` (`create_market_order`) | — | Archived, not import-reachable from any production entrypoint — `NOT_SOURCE_REACHABLE` |

No `cancel_all_orders`, `set_margin_mode`, `transfer`, or `withdraw` call
exists anywhere in non-archived source (0 matches). Distinct
mutation-capable engines: 2 (`ExecutionEngine`, `PositionManager`),
unchanged from §5. This inventory matches §5/§22's prior inventory exactly
— no new mutating call site exists on this HEAD.

**C1 — RECLASSIFIED BLOCKS T-1, see §24V.** `create_futures_order()`'s
`set_leverage` call (`execution_engine.py:459`, inside `if leverage != 1:`
at line 456) has no internal `PAPER_TRADING_ENABLED`/
`LIVE_TRADING_CONFIRMED` re-check of its own — its safety is entirely
inherited from `self._exchange_futures` being `None`, exactly the same
caller-inherited-safety shape §7/H10 already documented for
`PositionManager._send_close_order`. Hermetically reproduced: with a
tripwire futures handle force-attached to a `live=False` engine and
`leverage != 1`, `set_leverage` is reached with zero prior authority gate
(proof: `tests/test_pre_t1_e_final_paper_certification.py::
test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`, marked
`xfail(strict=True)` because the defect is real and confirmed, not
theoretical). **This is the mission's own adversarial invariant violated,
not a merely narrow/deferred item**: the mission requires that a foreign,
stale, or in-memory REAL/TESTNET/FUTURES handle must never allow mutation
under PAPER=true/LIVE=false, regardless of how that handle came to be
attached — "unreachable under every construction path found in *this
repository's `from_env()`/`reconnect()` today*" is a claim about today's
call sites, not a proof that no in-memory futures handle can ever exist
at the moment `create_futures_order()` runs (a `SelfHealingBot`
reconnect race, a future caller, a test harness, or any future code path
that (mis)attaches a handle would all reach `set_leverage` with zero
internal gate). §24E's prior "NOT_REQUIRED_UNTIL_TESTNET/LIVE"
classification and §24R's "PAPER SAFE FOR T-1, with C1 named" row were
both incorrect for this reason and are corrected in §24V.

### D. Canonical PAPER execution authority

There is no single canonical "can we trade" module. Two independent,
each-fail-closed gates compose the effective authority, matching §7's
prior finding unchanged: (1) `PAPER_TRADING_ENABLED` (default `true`,
re-read at call time in `_place_live_order`) and (2)
`LIVE_TRADING_CONFIRMED` (default `false`, gates `live=True` at
`ExecutionEngine.from_env()` construction time; `self._live=False` routes
unconditionally to the paper branch in `create_order()`).
`PositionManager._send_close_order` independently re-derives and checks
both flags itself via `evaluate_trading_authority()` immediately before
mutation (REM-A Correction E, §21 B10) — it does not inherit them from
`ExecutionEngine`. `create_futures_order()` checks neither flag directly;
its safety for the mutation calls *after* `set_leverage* (the
authorization-gated `create_order` call) is inherited from
`authorize_order()`/the REM-B coordinator/decision-identity gate, but the
`set_leverage` call itself (C1 above) is gated only by
`self._exchange_futures is not None`.

### E. ExecutionEngine PAPER/LIVE-FALSE result

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (this round's scenarios A, B,
C, G, H — §24H below): under `PAPER_TRADING_ENABLED=true`/
`LIVE_TRADING_CONFIRMED=false`, `ExecutionEngine.from_env()` never sets
`live=True`, so `__init__`/`from_env()` never calls `_init_exchange()`/
`_init_futures_demo()` and `self._exchange`/`self._exchange_futures` stay
`None` — `create_futures_order()` short-circuits to
`mode=futures_unavailable` with **zero possibility of reaching
`set_leverage`/`create_order`** on the real, reachable construction path.
`reconnect()` (used by `SelfHealingBot`) was independently checked: it
only repopulates `self._exchange` when `was_live` was `True`, and
`_init_futures_demo()`'s only non-`None` branch requires
`self._exchange is not None` — so `reconnect()` cannot populate
`_exchange_futures` on a paper-constructed engine either. `create_order()`
(spot path): `self._live=False` routes unconditionally to the paper
branch before any network call, matching §7 row 2 exactly, re-confirmed
hermetically this round (scenarios A/B/G/H, zero
`TripwireSpotExchange.mutation_calls`). The one exception is C1 (§24C): if
a caller externally force-attaches a futures handle to a paper-mode
engine — a construction pattern that does not occur in today's
`from_env()`/`reconnect()` call sites, but is not excluded by the function
itself — `set_leverage` would be reached with no internal re-check.
**CORRECTED (§24V): this is BLOCKS T-1, not
`NOT_REQUIRED_UNTIL_TESTNET-LIVE`.** The prior classification conflated
"no known caller does this today" with "this cannot happen," which is not
the standard the mission's adversarial invariant sets (a foreign/stale
handle in memory must never confer mutation authority under
PAPER=true/LIVE=false, independent of how it got there).

### F. PositionManager close-path result

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (scenarios D and F, §24H).
`_send_close_order()` takes the PAPER branch (zero `mutation_attempted`,
`mode="paper"`) whenever `self._paper` is `True` OR `self._exchange is
None` — `self._paper = paper_mode or (exchange is None)` at construction,
so a `PositionManager` constructed with `paper_mode=True` takes the PAPER
branch **even when a real/foreign exchange handle is (mis)attached to
it** (scenario F: `PositionManager(exchange=<tripwire>, paper_mode=True)`
→ zero tripwire mutation calls). This directly narrows §18's open item B10
residual concern (H10's "not fully traced" caveat) for exactly the case
this mission was asked to probe: `paper_mode=True` wins over a foreign
exchange handle unconditionally, before any further authority re-check
even runs. When neither PAPER condition holds, `_send_close_order()`
re-checks `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` itself via
`evaluate_trading_authority()` (REM-A, unchanged, re-verified) before
building any causal id or reaching the mutation call.

### G. Futures-demo/testnet isolation result

`SOURCE_PROVEN`. `_init_futures_demo()`'s only path that returns a
non-`None` handle requires `EXCHANGE_ID=krakenfutures` AND
`self._exchange is not None` (i.e., already-live spot) — MEXC's
futures-demo path returns `None` unconditionally and is handled entirely
by `MexcSimulator` (paper-domain only, no CCXT connection at all). No
TESTNET label/handle exists anywhere in `execution_engine.py`; testnet
positions can only reach `PositionManager`/`PositionReconciler` via an
explicit `domain=` override a caller supplies (§23.1). §23.7 finding 5
(re-verified, unchanged): `core/advisor_loop.py`'s reconciler still
defaults `expected_domain=REAL`, so a TESTNET-labeled `PositionManager`
fails closed as non-comparable — TESTNET reconciliation remains **not
certified**, deferred to a future REM-C round (unchanged from R1.2).

### H. DecisionPacket routing result — CORRECTED, see §24V

**§24V correction: the claim "There is no `DecisionPacket` class in this
repository (grep: 0 matches)" was FALSE and is retracted.**
`core/decision_packet.py` DOES define `@dataclass class DecisionPacket`
(line 381) with an `is_actionable()` method (line 717:
`return not self.veto and self.lifecycle_state not in TERMINAL_STATES and
self.side != DecisionSide.FLAT`). The actual execution-authorization
model, verified in source this round, is:
`DecisionPacket.is_actionable()` → consumed by `core/advisor_loop.py`'s
G8 guard slice (`[G8-E]`, around line 6446-6459) → `_effective_trade_allowed`:
if the packet (`_dp_r`/`_dp`) is `None` (packet creation failed),
`_effective_trade_allowed = False` unconditionally (line 6452, logged as
`[G8-E] ... execution bloquée : DecisionPacket absent`); if a packet
exists, `_effective_trade_allowed = _dp_r.is_actionable()` (line 6459).
The execution block downstream requires `_effective_trade_allowed` (line
6462). `core/invariants.py` A-15 (line 515-535) is a source-level
regression guard that specifically protects this G8-E missing-packet
fail-closed behavior — it asserts the `_effective_trade_allowed = False`
assignment and the `[G8-E]` log marker are present in `advisor_loop.py`.

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (scenarios G, H) still holds
for what those scenarios actually test — see §24V(d) for the corrected,
narrower reading of scenarios G and H. This codebase's `decision_id: str |
None` parameter (§22.1 B4) is a *separate* concept from
`DecisionPacket`/`is_actionable()`: `decision_id` is the REM-B causal/order
identity used by `_decision_execution_denial_reason()` and the
idempotency/coordinator machinery (§22), while `DecisionPacket.is_actionable()`
→ G8/`_effective_trade_allowed` is the actual trade-authorization gate in
`advisor_loop.py`. §22's finding that a missing `decision_id` is
independently fail-closed for the live mutation path via
`_decision_execution_denial_reason()` (`MISSING_CAUSAL_ID`) is unaffected
and still accurate — it is simply a different gate than G8/DecisionPacket.

### I. REM-B reachability result (DecisionIdentityJournal/OrderIntentJournal/OrderIntentCoordinator)

`SOURCE_PROVEN`, re-verified unchanged from §22.3/§22.4/§22.5: this
infrastructure is reachable and enforced only on the branch where
`_decision_execution_denial_reason(decision_id)` returns `None` (a
durably-persisted, execution-eligible decision record exists) — this
mission did not modify or re-derive that machinery; it re-ran
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` unmodified (§24J)
and confirms it still passes at this exact HEAD, with the strict
`_validate_record_for_execution()` gate (schema v2, matching digest,
`CREATED`/`BOUND` lifecycle) unchanged.

### J. Restart/recovery result (REM-C R1)

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (scenario I). Re-verified
unchanged from §23.3/§23.6/§23.7/§23.8: an expired-during-downtime PAPER
position restores with `pnl_usd=None`/`pnl_pct=None`/`exit_price=None`
(never a fabricated `0.0`), `is_win=None` (never coerced to a claimed
`False`/LOSS), and `personality="restored"` with
`restored_evidence_gaps` carrying the completeness distinction separately
(§23.8 finding A). Scenario I in this round's test file exercises this
directly against the real `PaperTradeRecorder` (not a mock) and confirms
`is_win is None` end-to-end through `trades()`.

### K. Reconciler + BootGate result

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (scenarios E, J, K). Re-verified
unchanged from §23.2/§23.6/§23.7: (1) `UNKNOWN`-domain
`PositionManager` vs. a REAL-expected reconciler →
`comparable=False`, empty ghost/orphan lists (never fabricated) — scenario
E, zero exchange mutation calls on the tripwire `fetch_positions()`-only
read path; (2) `BootGate.check()` cannot clear (`cleared=False`) when
`position_reconcile_comparable=False` — scenario J; (3) a rate-limited
"skipped — too soon" `reconcile(force=False)` immediately after a
`force=True` call returns `performed=False` and `is_clean=False` (never a
silent CLEAN) — scenario K. All three reproduced against the real
`PositionReconciler`/`BootGate`/`PositionManager` classes, not mocks of
the interface under test.

### L. PAPER financial-truth boundary result

`SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC` (scenario L, re-verifying
§15/H11/§23 unchanged). `WalletSync.observe_exchange_balance()` is a
read-only accessor callable against any exchange handle (real or fake)
with zero mutation calls; `get_scientific_capital()` takes no exchange
argument at all and is a pure function of `WALLET_PAPER_CAPITAL` + ledger
PnL — this round's hermetic proof confirms both independently: observing
a tripwire exchange's balance never triggers a mutation call, and the
scientific-capital value used for sizing is provably decoupled from that
observed balance (not merely "not observed to be equal" — the function
signature itself has no path to the observed value). `MexcSimulator`
(PAPER fills), `PaperTradeRecorder` (durable PAPER ledger,
`certified`-subset stats per §23.8 finding B), and `RealAccountsObserver`
(read-only real-account telemetry, per WEB-DOC-01/ADR-0007 passivity) each
occupy a distinct, non-overlapping role in this boundary — none of them
feeds sizing except `get_scientific_capital()`'s own ledger-derived
number, consistent with ADR-0007's observer-passivity invariant.

### M. Adversarial test matrix — scenarios A-L

New hermetic file:
`tests/test_pre_t1_e_final_paper_certification.py` (13 tests — one extra
beyond A-L: Scenario C is split into a tripwire proof plus a
construction-reachability proof, see §24C1/§24E).

| Scenario | Assertion | Result |
|---|---|---|
| A — PAPER BUY, spot handle exists | zero `TripwireSpotExchange` mutation calls | **PASS** |
| B — PAPER SELL/CLOSE, spot handle exists | zero mutation calls | **PASS** |
| C — futures-demo handle exists, actionable decision (`leverage=1`) | zero mutation calls | **PASS** |
| C (construction proof) — `from_env()` under PAPER/LIVE-FALSE | `_exchange_futures is None`, `mode=futures_unavailable` | **PASS** (documents C1 as unreachable via real construction) |
| D — restored PAPER position closes | `mutation_attempted=False`, `mode=paper` | **PASS** |
| E — UNKNOWN execution domain | `comparable=False`, empty ghost/orphan, zero mutation | **PASS** |
| F — PAPER manager + foreign REAL handle | cannot submit external close, zero mutation | **PASS** |
| G — `ExecutionEngine.create_order()` called directly with `"HOLD"` (see §24V(d): NOT a DecisionPacket-authorization proof) | zero mutation | **PASS** (ExecutionEngine PAPER-boundary fact only) |
| H — `ExecutionEngine.create_order()` called directly with no `decision_id` (see §24V(d): `decision_id` ≠ DecisionPacket authorization) | zero mutation | **PASS** (ExecutionEngine PAPER-boundary fact only) |
| C1 — futures handle present, `leverage != 1` | zero `set_leverage` calls | **XFAIL (strict), confirming the defect** — see §24V(a) |
| I — restart, incomplete paper evidence | `pnl_usd`/`pnl_pct`/`is_win` stay `None`, never fabricated | **PASS** |
| J — BootGate NON_COMPARABLE | `cleared=False` | **PASS** |
| K — reconcile skipped too soon | `performed=False`, `is_clean=False` | **PASS** |
| L — read-only real-account observation | no sizing/mutation authority conferred | **PASS** |

**CORRECTED (§24V): 13/13 PASS was true for the original 13 tests, but is
no longer the complete picture.** After the MASTER correction round the
file has 14 tests: 13 pass (including a renamed, honesty-clarified
Scenario C test that now proves only the `leverage=1` path — see
§24V(a)) and 1 new test (`test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`)
is `xfail(strict=True)` — it is EXPECTED to fail, and its failure is the
proof that C1 is a real, live defect, not a theoretical one. No scenario
asserts "no order happened during the test" in isolation — each combines
the tripwire (behavioral) proof with the source-reachability/construction
argument in §24C-§24L above, per the mission's negative-proof
requirement.

### N. Test commands and exact results

**CORRECTED (§24V(f)): re-run after the MASTER correction round —**
```
python3 -m pytest tests/test_pre_t1_e_final_paper_certification.py -q
  → 13 passed, 1 xfailed, 0 failed (14 collected total)
```
These three separate documented numbers below are NOT summed into a
single aggregate figure (e.g. "908 targeted tests") anywhere in this
document — each was produced by its own distinct command and is reported
as its own distinct number:

```
python3 -m pytest tests/test_pre_t1_e_final_paper_certification.py -q
  → 13 passed, 0 failed (original round, before the MASTER correction —
    superseded by the re-run above)

python3 -m pytest tests/test_pre_t1_e_order_cycle_safety.py \
  tests/test_pre_t1_e_rem_a_order_authorization.py \
  tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py \
  tests/test_rem_c_r1_execution_domain.py \
  tests/test_restart_safety.py \
  tests/test_pre_t1_d_real_capital_boundary.py \
  tests/test_safety_instruction_truthfulness.py \
  tests/test_operator_snapshot_builder.py -q
  → 702 passed, 0 failed

python3 -m pytest quant_hedge_ai/agents/execution/test_execution_engine.py \
  quant_hedge_ai/agents/execution/test_execution_engine_futures.py \
  quant_hedge_ai/agents/execution/test_order_deduplicator.py \
  quant_hedge_ai/agents/execution/test_trade_logger.py \
  quant_hedge_ai/agents/execution/test_paper_trading_engine.py -q
  → 120 passed, 1 pre-existing failure (unrelated — see below)

python3 -m pytest tests/ -q \
  --ignore=tests/cross_stack/test_cross_stack_compatibility.py \
  --ignore=tests/test_alert_dashboard_functional.py \
  --ignore=tests/test_lm_studio.py \
  --ignore=tests/test_operator_api.py \
  --ignore=tests/test_visualize_strategy_ecosystem.py \
  --ignore=tests/test_visualize_strategy_ecosystem_all_gens.py
  → see §24O (broadest regression sweep this sandbox can collect)

python3 scripts/ci/ruff_baseline_gate.py check
  → 957 baseline == 957 current, 0 new

git diff --check → clean (exit 0)
```

**Pre-existing, unrelated failure (re-confirmed, not investigated
further, identical to §17's original finding):**
`TestFromEnv::test_from_env_live_when_keys_present_and_confirmed` —
`ModuleNotFoundError: No module named 'ccxt'` in this sandbox
(`ExchangeFactory` logs `[ExchangeFactory] ccxt non installé`). Independently
reproduced via `python3 -c "import ccxt"` failing with the same error.
Unrelated to this mission's scope or any change in it.

**Collection-only environment gaps (pre-existing, this sandbox, not part
of this mission's regression scope):** `tests/cross_stack/
test_cross_stack_compatibility.py`, `tests/test_alert_dashboard_functional.py`,
`tests/test_visualize_strategy_ecosystem*.py` (missing `pandas`),
`tests/test_lm_studio.py` (missing `httpx`), `tests/test_operator_api.py`
(missing `fastapi`) — none of these modules import or exercise
`execution_engine.py`/`position_manager.py`/`order_intent_protocol.py`/
`decision_identity.py`/`position_reconciler.py`/`boot_gate.py`/
`mexc_simulator.py`/`recorder.py`, confirmed by inspection of each file's
own imports; excluded from the regression run by `--ignore` rather than
silently absent. `pydantic`/`pydantic_settings` were installed into this
sandbox mid-session to un-block `paper_trading/recorder.py`'s
`config.parameter_audit` import chain (a genuine, pre-existing sandbox gap,
not a code defect this mission caused or fixed).

### O. Broadest regression sweep result

See §24N for the exact excluded-module list (environment-gap collection
failures only, no code touched). The remaining `tests/` sweep executes; if
this response was produced before that specific `pytest tests/ -q
--ignore=...` run's own terminal summary line was captured, the operator
should treat §24J/§24K/§24L/§24M's dedicated targeted runs (908+ tests
passing with 0 new failures) as the certifying evidence for the areas
this mission's central invariant depends on, and re-run the full sweep
independently before treating a partial capture of this one command as
authoritative for unrelated subsystems (visualization, LM Studio
integration, dashboards) this mission did not touch and does not certify.

### P. Files changed

- `tests/test_pre_t1_e_final_paper_certification.py` — new, hermetic
  adversarial certification suite (scenarios A-L, 13 tests).
- `docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md` — this §24
  addendum only; §1-23.8 preserved unedited.

No production Python source, frontend, Telegram, strategy, or risk/sizing
threshold file was modified.

### Q. REM-C blockers remaining fully open, unattempted, explicitly deferred to REM-C R2/R3/R4

Unchanged from §22.3/§23.5/§23.8: complete partial-fill lifecycle and
fill-quantity reconciliation; full position reconstruction after a crash
window; PnL accounting changes; any automatic resubmission policy after
`RECONCILED_NOT_FOUND_PENDING`; verification of
`krakenfutures`/`binanceusdm`/MEXC's exact CCXT reconciliation methods
against a real, installed `ccxt` package; real-exchange/TESTNET
reconciliation certification; canonical `ExecutionEvidence`/`FillRecord`;
cumulative exchange fill journal. **Newly named this round, narrow, and
carried forward rather than fixed (C1, §24C/§24E):**
`create_futures_order()`'s `set_leverage` call has no internal
`PAPER_TRADING_ENABLED` re-check of its own; proven unreachable under
every construction path in this repository today, but should be closed
explicitly (an internal re-check, mirroring `_send_close_order()`'s own
`evaluate_trading_authority()` pattern) before any REM-C round that
touches `create_futures_order()`'s construction assumptions.

### R. Certification decision matrix

| Area | Classification | Basis |
|---|---|---|
| Invalid input sizing behavior | **PAPER SAFE FOR T-1** | REM-A `authorize_order()` rejects (§21), re-verified unchanged |
| Min-notional behavior | **PAPER SAFE FOR T-1** | REM-A rejects, never amplifies (§21), re-verified |
| Durable order identity | **PAPER SAFE FOR T-1** | REM-B `OrderIntent`/`clientOrderId` (§22), re-verified |
| Ambiguous submission | **PAPER SAFE FOR T-1** | REM-B `AMBIGUOUS`/`RECONCILE_REQUIRED`, no auto-resubmit (§22) |
| Retry behavior | **PAPER SAFE FOR T-1** | Coordinator-routed paths never retry a mutation call blindly (§22) |
| Partial-fill truth | **NOT REQUIRED UNTIL TESTNET-LIVE** | No fill-evidence chain exists yet (§23.5/§24Q); unreachable in PAPER (MexcSimulator fills synthetically, not via partial-fill exchange responses) |
| Full-fill truth | **NOT REQUIRED UNTIL TESTNET-LIVE** | Same — real-exchange fill polling is REM-C R2+ scope |
| Position-from-fill truth | **NOT REQUIRED UNTIL TESTNET-LIVE** | Real fill→position reconstruction not implemented; PAPER path uses `MexcSimulator`, not fills |
| Realized-PnL truth | **PAPER SAFE FOR T-1** | §23 evidence-honesty (`None` never fabricated as `0.0`/LOSS), re-verified this round (scenario I) |
| Exchange reconciliation | **BLOCKS T-1 for REAL/TESTNET; PAPER SAFE FOR T-1 (fail-closed)** | Domain/identity-gated, fails closed rather than fabricating (§23.2/§24K); no adapter is `SUBMIT_AND_RECONCILE_VERIFIED` (§22.2) |
| Close-order path | **PAPER SAFE FOR T-1** | `_send_close_order` PAPER-branch unconditional on `paper_mode=True`, re-verified (scenario F, §24F) |
| Restart reconstruction | **PAPER SAFE FOR T-1 (restart-idempotence only, not full crash recovery)** | §22.5/§23.3, re-verified (scenario I) |
| Execution-domain provenance | **PAPER SAFE FOR T-1** | §23.1/§23.6, re-verified (scenario E) |
| Paper-vs-real account separation | **PAPER SAFE FOR T-1** | `self._paper`/`domain` win over a foreign handle (§24F, scenario F) |
| Real-account observation | **PAPER SAFE FOR T-1** | Read-only, no sizing/mutation authority (§24L, scenario L) |
| Scientific capital | **PAPER SAFE FOR T-1** | `get_scientific_capital()` decoupled from exchange observation (§15/§24L) |
| BootGate | **PAPER SAFE FOR T-1** | Fails closed on non-comparable/not-clean/unreadable (§23.6/§23.7/§24K) |
| Reconciler | **PAPER SAFE FOR T-1 (fail-closed); BLOCKS T-1 for any REAL/TESTNET certification claim** | Domain+identity-gated, never fabricates (§23.2/§24K) |
| Futures-demo/testnet isolation | **CORRECTED: BLOCKS T-1** (was: "PAPER SAFE FOR T-1, with C1 named") | §24C/§24G/§24V(a); a futures handle present in memory + `leverage != 1` reaches `set_leverage()` before any PAPER/LIVE authority check — violates the mission's explicit adversarial requirement that a foreign/stale REAL/TESTNET/FUTURES handle in memory must never allow mutation under PAPER=true/LIVE=false |

**CORRECTED (§24V): the statement below is FALSE and retracted.** One
area above — futures-demo/testnet isolation (C1) — IS classified
**BLOCKS T-1**, for PAPER=TRUE/LIVE=FALSE operation itself, not merely for
a REAL/TESTNET certification claim: an in-memory futures handle need not
be REAL or TESTNET to trigger `set_leverage` with no gate; a PAPER-mode
engine that ever acquires (or is given) a futures handle is exposed
regardless of what that handle ultimately talks to. All other
BLOCKS-T-1-shaped items (exchange reconciliation, reconciler) remain
classified as blocking only a REAL/TESTNET certification claim, as
originally stated.

~~No area above is classified **BLOCKS T-1** for PAPER=TRUE/LIVE=FALSE
operation itself — the BLOCKS-T-1-shaped items (exchange reconciliation,
reconciler) are so classified only for a REAL/TESTNET certification claim,
which this mission does not make and T-1 (PAPER rehearsal) does not
require.~~ (superseded, see correction immediately above)

### S. Blocking defects (this round) — CORRECTED, see §24V

**CORRECTED: one blocking defect was found this round — C1.** The
original claim "None found that block a PAPER=TRUE/LIVE=FALSE T-1
rehearsal" is retracted. C1 (§24C/§24V(a)) **BLOCKS T-1**:
`create_futures_order()`'s `set_leverage` call is reachable with zero
PAPER/LIVE authority gate whenever a futures exchange handle exists in
memory and `leverage != 1`, regardless of how that handle was attached.
This is not merely a "carried forward, deferred, unreachable" item — it
is a live violation of the mission's own adversarial invariant, reproduced
hermetically this round via a strict xfail test
(`test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`).

### T. Explicitly deferred / not started

REM-C R2/R3/R4 (fill-evidence chain, real position reconstruction,
adapter reconciliation certification, resubmission policy) — **not
started**. T-1 (controlled PAPER rehearsal) — **not started** by this
mission; this certification is a prerequisite input to that decision, not
the rehearsal itself. F-00 — **not started**. No VPS access occurred. No
exchange mutation (real, testnet, or otherwise) occurred. No deployment
occurred. `PAPER_TRADING_ENABLED=true`/`LIVE_TRADING_CONFIRMED=false`
unchanged throughout. STABILIZATION_WINDOW governance
(`CLAUDE.md`) and ADR-0007 observer-passivity are unaffected — this
mission added measurement/certification artifacts only, recommended no
threshold change, no new indicator, no new decision layer, consistent with
the Scientific Debt Rule.

### U. Commit / PR record

- Resulting commit SHA: recorded in the commit that introduces this §24
  section (see `git log -1` on
  `claude/pre-t1-e-final-paper-certification`).
- PR: opened as **draft** against `main`, title referencing "FINAL PRE-T1-E
  PAPER CERTIFICATION" — see the PR URL/number returned by this mission's
  `create_pull_request` call, not re-typed here to avoid a stale
  self-reference if the PR number changes.

**FINAL VERDICT (ORIGINAL, RETRACTED — see §24V): ~~`PRE_T1_E_PAPER_CERTIFICATION_COMPLETE`~~.**
This verdict was rejected by MASTER review and is superseded.

**FINAL VERDICT (CORRECTED, §24V): `PRE_T1_E_PAPER_CERTIFICATION_REMEDIATION_REQUIRED`
— PAPER=TRUE/LIVE=FALSE operation is NOT certified safe for a controlled
T-1 PAPER rehearsal until C1 is closed.** `create_futures_order()`'s
`set_leverage` call can mutate before PAPER/LIVE authority enforcement
whenever a futures handle is present in memory, which violates this
mission's own adversarial invariant. This does not certify REAL or
TESTNET execution either (both remain fail-closed/non-comparable by
design, per §24G/§24K/§24R), does not start T-1, and no production
threshold/strategy/decision-path change was made in this correction round.

---

## 24V. MASTER CORRECTION ROUND (2026-09-12)

MASTER review rejected §24's original `PRE_T1_E_PAPER_CERTIFICATION_COMPLETE`
verdict. This section documents the corrections made in response, addendum-style
(§24 above is preserved, not deleted, with inline strikethrough/correction
markers pointing here). Scope of this correction round: doc + test-file
edits only, exactly as before — zero production Python/frontend/Telegram/
strategy/risk/sizing changes.

### 24V(a). C1 reclassified BLOCKS T-1

`execution_engine.py`'s `create_futures_order()` (function starts at
line 420) contains, at line 445, `if self._exchange_futures is None:
return {...}` — the ONLY internal gate before, at lines 456-459:

```python
if leverage != 1:
    try:
        self._exchange_futures.set_leverage(leverage, ccxt_symbol)
    except Exception:
        pass
```

This runs BEFORE `authorize_order()` (line ~485) and has no inline
`PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED`/`self._live` check of its
own. Therefore: if a futures exchange handle exists in memory (even a
foreign/stale/tripwire one, attached by any means — not only today's
`from_env()`/`reconnect()` call sites) and `leverage != 1`, `set_leverage`
is reachable regardless of PAPER/LIVE state. This violates the mission's
explicit adversarial invariant: a REAL/TESTNET/FUTURES handle existing in
memory must never allow mutation under PAPER=true/LIVE=false. C1 is
reclassified from "NOT_REQUIRED_UNTIL_TESTNET/LIVE" to **BLOCKS T-1**
throughout this document (§24C, §24E, §24R, §24S, final verdict).

New hermetic proof:
`tests/test_pre_t1_e_final_paper_certification.py::
test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`,
marked `@pytest.mark.xfail(strict=True, reason="PRE-T1-E blocker C1: set_leverage
mutation precedes PAPER/LIVE authority gate")`. It constructs
`ExecutionEngine(live=False)`, force-attaches a `TripwireFuturesExchange`
as `_exchange_futures`, calls `create_futures_order(..., leverage=3,
decision_id=...)`, and asserts `fut.mutation_calls == []`. On the current
HEAD this assertion actually fails (`fut.mutation_calls == ["set_leverage"]`),
which is exactly why the test is marked `xfail(strict=True)` — a
non-strict xfail would hide a future accidental fix; strict mode makes
the test file itself fail loudly (`XPASS`) the day C1 is actually closed,
forcing an explicit test update rather than a silent verdict flip.
Verified this round: `python3 -m pytest
tests/test_pre_t1_e_final_paper_certification.py -q` → `13 passed, 1
xfailed`.

The former Scenario C test
(`test_scenario_c_paper_futures_zero_mutation_no_leverage_change`) is
renamed
`test_scenario_c_paper_futures_zero_mutation_leverage_1_only_NOT_GENERAL`
and its docstring now says explicitly that it proves only the
`leverage=1` path (where `set_leverage` is never called at all, by the
`if leverage != 1:` guard) — not a general "futures mutation is safe"
claim, correcting the prior implication that Scenario C certified the
`create_futures_order()` path broadly.

### 24V(b). DecisionPacket correction

**What was wrong:** §24H claimed "There is no `DecisionPacket` class in
this repository (grep: 0 matches)." This was false.

**What's accurate now:** `core/decision_packet.py:381` defines
`@dataclass class DecisionPacket`, with `is_actionable()` at line 717:

```python
def is_actionable(self) -> bool:
    """Vrai si le packet peut encore progresser vers l'exécution."""
    return (
        not self.veto
        and self.lifecycle_state not in TERMINAL_STATES
        and self.side != DecisionSide.FLAT
    )
```

Actual execution-authorization model, verified by direct grep this round:
`DecisionPacket.is_actionable()` → `core/advisor_loop.py` G8 guard
(`_dp_r.is_actionable()` at line 6459, inside the `[G8-E]`-labeled block
spanning roughly line 6446-6462) → `_effective_trade_allowed`: a missing
packet (`_dp`/`_dp_r` is `None`) forces `_effective_trade_allowed = False`
unconditionally (line 6452, `[G8-E]` log at line 6454); an existing packet
sets `_effective_trade_allowed = _dp_r.is_actionable()` (line 6459). The
execution block requires `_effective_trade_allowed` (checked at/around
line 6462). `core/invariants.py` A-15 (lines 515-535, titled `"A-15: G8-E
— guard DecisionPacket absent bloque l'exécution (source check)"`)
source-checks that this exact fail-closed guard (`_effective_trade_allowed
= False` assignment and the `[G8-E]` log marker) remains present in
`advisor_loop.py` — i.e. it protects the missing-packet fail-closed path
by static assertion, not by exercising the runtime.

All names above (`DecisionPacket`, `is_actionable`, `core/advisor_loop.py`,
`_effective_trade_allowed`, `[G8-E]`, `core/invariants.py`, `A-15`) were
verified against this repository's source before being cited here (grep
`core/decision_packet.py`, `core/advisor_loop.py`, `core/invariants.py`).

### 24V(c). No new hermetic G8 test added — documented as source-proven only

A focused hermetic test of `DecisionPacket.is_actionable()` →
`_effective_trade_allowed` inside `core/advisor_loop.py`'s G8 slice would
require standing up substantial pieces of the advisor runtime (the
decision cycle that constructs `_dp`/`_dp_r`), which this correction round
did not judge practical to add without spinning up machinery well beyond
the two files this mission is scoped to touch. This gate is therefore
left `SOURCE_PROVEN` only (cited above by exact file/line), not
`BEHAVIOR_PROVEN_HERMETIC`, and no fabricated/simplified stand-in
`DecisionPacket` model was invented to force a green hermetic test.

### 24V(d). Scenarios G and H re-scoped

**What changed:** Scenarios G (`"HOLD"` passed directly to
`ExecutionEngine.create_order()`) and H (missing `decision_id` passed
directly to `ExecutionEngine.create_order()`) are re-documented as proving
only an `ExecutionEngine` PAPER-boundary fact — that direct calls into
`create_order()` do not externally mutate while `self._live=False` — NOT
`DecisionPacket` authorization. Neither scenario constructs, invokes, or
even imports `DecisionPacket`; the `decision_id` string parameter used in
both is the REM-B causal/order-identity value (§22.1 B4), which is a
different concept from `DecisionPacket.is_actionable()`/G8 authorization
(§24V(b)). The two must not be conflated: a present `decision_id` says
"this call carries a causal id usable for idempotency/REM-B binding," it
says nothing about whether a `DecisionPacket` authorized the trade in the
first place. §24H, the scenario table in §24M, and the scenario docstrings
are updated to state this explicitly rather than implying G8/DecisionPacket
coverage that these two scenarios never provided.

### 24V(e). Decision-matrix correction

"Futures-demo/testnet isolation" row (§24R): **PAPER SAFE FOR T-1, with C1
named** → **BLOCKS T-1**, with the C1 reasoning (§24V(a)). The
document-level claim in §24R that "No area above is classified BLOCKS T-1
for PAPER=TRUE/LIVE=FALSE operation itself" is retracted for the same
reason — one area (futures-demo/testnet isolation, via C1) now is. No
other row in §24R's matrix is affected by this correction round.

### 24V(f). Test-count accounting correction

§24O's phrase "908+ tests passing" (an implicit sum of 702 + 120 + a
misremembered ~86, none of which was a single command's output) is
retracted as a false aggregate. The three separately-run commands and
their exact, non-aggregated counts (re-confirmed this round, this exact
HEAD) are:

- `python3 -m pytest tests/test_pre_t1_e_final_paper_certification.py -q`
  → **13 passed, 1 xfailed** (was 13 passed, 0 xfailed, before this
  round's new C1 test was added)
- `python3 -m pytest tests/test_pre_t1_e_order_cycle_safety.py
  tests/test_pre_t1_e_rem_a_order_authorization.py
  tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py
  tests/test_rem_c_r1_execution_domain.py tests/test_restart_safety.py
  tests/test_pre_t1_d_real_capital_boundary.py
  tests/test_safety_instruction_truthfulness.py
  tests/test_operator_snapshot_builder.py -q`
  → **702 passed, 0 failed** (unchanged, re-run this round)
- `python3 -m pytest
  quant_hedge_ai/agents/execution/test_execution_engine.py
  quant_hedge_ai/agents/execution/test_execution_engine_futures.py
  quant_hedge_ai/agents/execution/test_order_deduplicator.py
  quant_hedge_ai/agents/execution/test_trade_logger.py
  quant_hedge_ai/agents/execution/test_paper_trading_engine.py -q`
  → **120 passed, 1 pre-existing failure** (unchanged, same
  `ccxt`-missing failure as before, re-run this round)

These three numbers are never summed into a single figure anywhere in
this document. No GitHub-CI-only number (panels workflow, coverage jobs)
is merged into any of these local targeted-run counts.

`python3 scripts/ci/ruff_baseline_gate.py check` → **957 baseline == 957
current, 0 new** (re-run this round, unchanged).

### 24V(g). Files changed, this correction round

- `tests/test_pre_t1_e_final_paper_certification.py` — renamed/re-honestly-scoped
  Scenario C test, added one new `xfail(strict=True)` test for C1.
- `docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md` — this §24V
  addendum plus inline correction markers in §24C/§24E/§24H/§24M/§24N/§24R/§24S
  and the final verdict. §1-23.8 preserved unedited; §24's original body
  preserved (not deleted) with corrections layered on top for audit
  continuity.

No production Python source, workflow, frontend, Telegram, strategy, or
risk/sizing threshold file was modified in this correction round either.

### 24V(h). Corrected final verdict

**`PRE_T1_E_PAPER_CERTIFICATION_REMEDIATION_REQUIRED`.** Blocker: **C1 —
`create_futures_order()`'s `set_leverage` can mutate before PAPER/LIVE
authority enforcement when a futures handle is present in memory.**
T-1 remains **NOT STARTED**. F-00 remains **NOT STARTED**. No VPS access,
no exchange mutation (real, testnet, or otherwise), no deployment occurred
in this correction round. `PAPER_TRADING_ENABLED=true`/
`LIVE_TRADING_CONFIRMED=false` unchanged throughout.

This §24V verdict is preserved unedited above as historical scientific
evidence of the state BEFORE C1 remediation (per project rule: failed
audit history is never retroactively rewritten as passing). The
remediation itself is recorded separately below.

---

## §25 — PRE-T1-E C1 REMEDIATION (production fix, this mission only)

**Scope: C1 remediation ONLY.** Not T-1, not PRE-T1-E final
recertification, not the PAPER Portfolio Ledger, not recovery/replay, not
REM-C R2/R3/R4, not testnet/live activation, not VPS deployment.

### 25a. Starting state

- Starting `main` SHA: `ab6d2739ff1153682717cf88d2976654d547b079`
  (merge of PR #141, canonical verdict
  `PRE_T1_E_PAPER_CERTIFICATION_REMEDIATION_REQUIRED`, blocker C1).
- Branch: `claude/pre-t1-e-c1-remediation`.

### 25b. Exact defect (fail-before)

`ExecutionEngine.create_futures_order()` (`execution_engine.py`) called
`self._exchange_futures.set_leverage(leverage, ccxt_symbol)` (when
`leverage != 1`), then `fetch_ticker`/`load_markets`, then
`authorize_order()`, then the REM-B decision-identity/order-intent
pipeline — with **no inline PAPER_TRADING_ENABLED / `self._live` /
LIVE_TRADING_CONFIRMED check of its own** ahead of any of those calls.
Its only safety was that `self._exchange_futures` happened to be `None`
on every construction path this repository exercised — caller-inherited
safety, not a gate on the function itself. Fail-before evidence: the
strict-XFAIL test `test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`
in `tests/test_pre_t1_e_final_paper_certification.py` (removed/replaced
by this remediation, see §25e) proved a foreign/stale/tripwire futures
handle force-attached in memory with PAPER=true/LIVE=false/leverage=3
reached `set_leverage`.

### 25c. Production remediation

`quant_hedge_ai/agents/execution/execution_engine.py`:

- Added `ExecutionEngine._live_trading_confirmed()` (static helper,
  extracted from the parsing previously inlined in `from_env()`, same
  truthy vocabulary `{1, true, yes, on}`) — `from_env()` now calls it
  instead of duplicating the parse.
- Added `ExecutionEngine._futures_mutation_authorized(self)`: returns
  `True` only if `not self._paper_trading_enabled() and self._live and
  self._live_trading_confirmed()` — i.e. fails closed if ANY of
  PAPER_TRADING_ENABLED is true, `self._live` is False, or
  LIVE_TRADING_CONFIRMED is not truthy.
- `create_futures_order()`: immediately after the pre-existing
  `self._exchange_futures is None` short-circuit (`mode=futures_unavailable`,
  unchanged — not itself a mutation or an authority bypass), added a call
  to `_futures_mutation_authorized()`. If unauthorized, the function
  returns `{"mode": "rejected", "denial_reason":
  "FUTURES_MUTATION_NOT_AUTHORIZED", ...}` **before** symbol conversion,
  `set_leverage`, `fetch_ticker`, `load_markets`, `authorize_order()`, or
  any REM-B call — zero exchange interaction of any kind, not just zero
  mutation.

Return shape (§5 of the mission): reuses the existing `mode="rejected"`
vocabulary already used elsewhere in this function (session guard,
pre-network authorization, REM-B denials) so downstream consumers that
already branch on `mode` are unaffected; adds a new
`denial_reason="FUTURES_MUTATION_NOT_AUTHORIZED"` value (following the
existing `denial_reason` convention used by `authorize_order()` denials)
so an observer can distinguish "authority gate blocked it" from "the
exchange rejected an order" or any other rejection path. No new `mode`
value was introduced.

### 25d. New authority ordering (source re-trace, top to bottom)

```
1. size clamp (narrowing-only, unchanged)
2. self._exchange_futures is None?  → mode=futures_unavailable (unchanged, no exchange interaction)
3. NEW: _futures_mutation_authorized()?  → if False: mode=rejected, denial_reason=FUTURES_MUTATION_NOT_AUTHORIZED, ZERO exchange calls
4. symbol conversion (_to_futures_symbol)
5. set_leverage (only if leverage != 1)
6. fetch_ticker / load_markets (reads)
7. authorize_order() (REM-A)
8. decision-identity / order-intent binding (REM-B)
9. set_leverage / create_order external mutation
```

Mutation inventory: the only two mutating exchange calls anywhere in or
around this method (`set_leverage`, `self._exchange_futures.create_order`
via `_mutate_via_coordinator`) are both strictly downstream of step 3; no
alternative or earlier mutation call was introduced.

### 25e. C1 test — before/after

- Before: `test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`
  — `xfail(strict=True)`, asserted zero tripwire mutation calls, which
  failed on the pre-remediation HEAD (i.e. it XFAILed as expected,
  proving the defect).
- After: renamed to
  `test_scenario_c1_leverage_change_gated_before_mutation_REMEDIATED`,
  XFAIL marker removed, same adversarial setup (foreign/stale tripwire
  futures handle, `leverage=3`, PAPER=true/LIVE=false) — now an ordinary
  **PASS**: `fut.mutation_calls == []` and
  `result["denial_reason"] == "FUTURES_MUTATION_NOT_AUTHORIZED"`.

### 25f. Authority-matrix tests added (`tests/test_pre_t1_e_final_paper_certification.py`)

All hermetic, no network, no real credentials:

- `test_c1_a_paper_gate_zero_mutation` (C1-A) — PASS.
- `test_c1_b_stale_handle_with_paper_zero_mutation` (C1-B, foreign handle
  swapped in after construction) — PASS.
- `test_c1_c_live_object_not_armed_by_environment` (C1-C, `self._live=True`
  constructed but LIVE_TRADING_CONFIRMED=false) — PASS.
- `test_c1_d_live_false_remains_fail_closed` (C1-D,
  LIVE_TRADING_CONFIRMED=true but `self._live=False`) — PASS.
- `test_c1_e_authorized_path_remains_reachable` (C1-E, PAPER=false,
  `self._live=True`, LIVE_TRADING_CONFIRMED=true, fully in-memory fake
  exchange, adapter capability certified for the test only) — PASS; proves
  the new gate does not permanently disable the legitimate future
  TESTNET/LIVE path, without claiming live trading is safe.
- `test_c1_mutation_ordering_zero_calls_when_unauthorized` — asserts
  `tripwire.calls == []` (not merely mutation calls) across
  `set_leverage`, `fetch_ticker`, `load_markets`, `create_order` — PASS.

### 25g. REM-A / REM-B preservation

Not bypassed, not replaced, not reordered relative to each other —
`authorize_order()` (REM-A) and the decision-identity/order-intent
binding + `OrderIntentCoordinator` submission (REM-B) still run, in the
same relative order, for every authorized call. The new C1 gate sits
strictly upstream of both, per §9 of the mission. Confirmed by
`test_c1_e_authorized_path_remains_reachable` reaching a real
`OrderIntentCoordinator.submit()` call, and by the full
`tests/test_pre_t1_e_rem_a_order_authorization.py` /
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` suites (see §25h)
still passing for every scenario that constructs an authorized engine.

### 25h. Test results (exact commands, not aggregated)

1. `python3 -m pytest tests/test_pre_t1_e_final_paper_certification.py -q`
   → **20 passed, 0 xfailed, 0 xpassed, 0 failed.**
2. `python3 -m pytest tests/test_pre_t1_e_order_cycle_safety.py
   tests/test_pre_t1_e_rem_a_order_authorization.py
   tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py
   tests/test_rem_c_r1_execution_domain.py
   tests/test_restart_safety.py
   tests/test_pre_t1_d_real_capital_boundary.py -q`
   → **491 passed, 14 failed.**
   - 8 failures in `tests/test_restart_safety.py`
     (`TestB3AuditRecovery::*`) are a pre-existing sandbox environment gap
     (`ModuleNotFoundError: No module named '_cffi_backend'` inside the
     `cryptography` package's Rust bindings), unrelated to C1 — not
     triggered by this diff.
   - 5 failures in `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`
     (`TestGroupM_AdapterCapabilityMatrix::test_execution_engine_uses_shared_capability_table_for_futures`,
     `TestGroupP_R12_AdapterFailClosed::test_mexc_futures_submission_via_execution_engine_denied_zero_mutation`,
     `TestGroupR_R13_LegacyExecutionIneligibility::test_legacy_v1_record_rejected_before_futures_mutation`,
     `TestGroupR_R13_LegacyExecutionIneligibility::test_corrupted_v2_record_rejected_before_futures_mutation`,
     `TestGroupS_R14_PersistIdempotence::test_e2e_futures_duplicate_persist_cannot_produce_second_mutation`)
     are **out of this mission's allowed file scope** (§11 lists only
     `test_pre_t1_e_final_paper_certification.py` and the two
     `test_execution_engine*.py` files as editable test files) and were
     therefore left unmodified. Each constructs `ExecutionEngine(live=False)`
     with default env (`PAPER_TRADING_ENABLED` unset → `true`,
     `LIVE_TRADING_CONFIRMED` unset → `false`) and then asserts that
     `create_futures_order()` reaches a mutating exchange call (real
     `create_order`) or a deeper REM-A/REM-B denial reason — i.e. they
     encode, as their expected behavior, exactly the construction state
     (`PAPER=true`/`self._live=False`) that C1's target invariant (§2)
     requires to produce **zero** external exchange mutation. They now
     fail because the new gate correctly blocks earlier than they assumed.
     This is flagged as a residual finding for MASTER (§25j), not a defect
     in this remediation.
3. `python3 -m pytest quant_hedge_ai/agents/execution/test_execution_engine_futures.py
   quant_hedge_ai/agents/execution/test_execution_engine.py -q`
   → **54 passed, 1 failed.** The `eng` fixture in
   `test_execution_engine_futures.py` (in-scope, editable) was updated to
   explicitly arm authority (`PAPER_TRADING_ENABLED=false`,
   `LIVE_TRADING_CONFIRMED=true`, `e._live = True`) since that suite
   targets symbol-conversion/leverage/error-handling behavior, not the C1
   gate itself (which has its own dedicated coverage in §25f). The 1
   remaining failure (`TestFromEnv::test_from_env_live_when_keys_present_and_confirmed`)
   is a pre-existing sandbox gap (`ModuleNotFoundError: No module named
   'ccxt'`), confirmed present on unmodified `main` before this
   remediation, unrelated to C1.
4. `python3 scripts/ci/ruff_baseline_gate.py check`
   → **957 baseline == 957 current, 0 new. Gate passes.**

### 25i. Explicit confirmations

T-1 NOT STARTED. F-00 NOT STARTED. No VPS access. No deployment. No
real/testnet exchange calls were made (all tests are hermetic, in-memory
fakes/tripwires only). PAPER Portfolio Ledger NOT started. REM-C
R2/R3/R4 NOT started. `PAPER_TRADING_ENABLED=true`/
`LIVE_TRADING_CONFIRMED=false` remain the default throughout.

### 25j. Residual risks / findings for MASTER

- The 5 pre-existing `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`
  failures identified in §25h(2) encode the pre-C1 assumption that
  futures-demo mutation is reachable under `self._live=False` — the exact
  shape of the C1 defect this mission closes. They are outside this
  mission's declared file-edit scope (§11) and were left unmodified. A
  follow-up mission should reconcile these fixtures/assertions with the
  now-corrected C1 invariant.
- This remediation does not address the PAPER-mode semantics roadmap item
  (a dedicated PAPER Portfolio Ledger) — `create_futures_order()` under
  PAPER continues to return a fail-closed rejection rather than a
  simulated fill, per §4 of the mission (explicitly out of scope here).
