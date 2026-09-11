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
