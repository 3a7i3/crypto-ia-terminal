# O-02W-PRE-T1-D — Real Capital Boundary Audit

**Mission type:** causal AUDIT (read-heavy investigation + characterization).
**Not a fix.** Zero production logic was modified by this document or its
companion test file.

**Verified base:** `origin/main` = `3cfae266bd9fa005f9db998025bf278046a8a5ca`
(merge commit of PR #133, parents `fe45a2bc6209f5b3a4928483759af4ab46d8e850`
+ `fb432c0394e798be19fe007f452072eb408a0684`), working tree clean, no commits
after it on `origin/main` at audit time. Branch:
`claude/o02w-pre-t1-d-real-capital-boundary-audit`.

**Evidence classes used throughout:** `SOURCE_PROVEN`,
`BEHAVIOR_PROVEN_HERMETIC`, `RUNTIME_UNKNOWN`, `CONTRADICTION_FOUND`,
`NOT_APPLICABLE`.

**Companion test file:**
`tests/test_pre_t1_d_real_capital_boundary.py` (46 hermetic tests, no
network, no secrets, fake exchanges only).

---

## 1. Causal graph of capital provenance

```
                         ┌──────────────────────────────┐
                         │   os.environ (process boot)   │
                         │  EXCHANGE_ID, EXCHANGE_TESTNET │
                         │  {EXCH}_API_KEY/_SECRET         │
                         │  PAPER_TRADING_ENABLED          │
                         │  LIVE_TRADING_CONFIRMED         │
                         │  WALLET_PAPER_CAPITAL           │
                         └───────────────┬────────────────┘
                                          │
                     ExchangeFactory.detect_mode() [SOURCE_PROVEN]
                       -> "live" | "testnet" | "paper"
                        (has_keys AND NOT testnet -> live
                         has_keys AND testnet     -> testnet
                         else                     -> paper)
                                          │
                  ExecutionEngine.from_env() [SOURCE_PROVEN]
                    live = has_api_key AND mode!="paper"
                           AND LIVE_TRADING_CONFIRMED truthy
                                          │
                         ExecutionEngine.__init__(live=...)
                    live=True  -> self._exchange = _init_exchange()
                                  self._mode = detect_mode()  (from ExchangeFactory)
                    live=False -> self._exchange = None, self._mode="paper" (unset)
                                          │
        ┌─────────────────────────────────┴─────────────────────────────────┐
        │                                                                    │
   core/advisor_loop.py bootstrap (line ~3777)                    core/advisor_loop.py per-cycle
   bootstrap_capital_x(exec_engine._exchange)                     refresh (lines 5739-5746)
   -> get_wallet_sync(exchange=exchange)  [creates the singleton  fetch_available_capital()
      if none exists yet; mode resolved from                       -> get_wallet_sync(...)
      EXCHANGE_MODE env, default "paper" — see §3]                    (mode arg IGNORED if
   -> wallet.bootstrap(exchange): fetch_balance(),                     singleton pre-exists,
      X = free USDT if >= MIN_CAPITAL_X else None                      see §3)
                                          │                              │
                         real_capital = exec_engine.fetch_available_capital()  (line 3835, first;
                                          line 5740/5742, refreshed every cycle)
                                          │
              ExecutionEngine.fetch_available_capital() [SOURCE_PROVEN,
                execution_engine.py:229-255]:
                paper_trading_enabled = PAPER_TRADING_ENABLED in {1,true,yes,on}
                wallet_mode = "paper" if paper_trading_enabled else self._mode
                wallet = get_wallet_sync(exchange=self._exchange, mode=wallet_mode)
                return wallet.get_balance()
                                          │
                        WalletSync.get_balance() [SOURCE_PROVEN, wallet_sync.py:166-206]
             mode=="paper": self._base_capital() + _read_ledger_pnl()
                              (_base_capital paper branch = WALLET_PAPER_CAPITAL constant,
                               NEVER self._x, regardless of whether bootstrap() succeeded)
             mode!="paper": cached _last_value (if fresh) OR
                              exchange.fetch_balance() OR
                              _fallback() = _last_value (stale) OR _base_capital()
                              (_base_capital non-paper branch = self._x if set,
                               else WALLET_PAPER_CAPITAL — see §4/H4)
                                          │
                    real_capital  (core/advisor_loop.py, a bare local, reassigned
                                    every cycle — see §5)
                                          │
        ┌──────────────┬──────────────────┬───────────────────┬─────────────────┐
        │              │                  │                    │                 │
  order_size       PortfolioBrain    CapitalAllocationEngine  ExecutiveOverride  P10 CapitalThrottle
  (line 4046,      .update_capital   .update_capital           .update(          (constructed with
  computed ONCE     (line 5743)       (line 5744)                capital_current  WALLET_PAPER_CAPITAL,
  at bootstrap,                                                  =real_capital)   NOT real_capital —
  never                                                           (line 7241)      see §6/H6)
  recomputed —
  see §5/H5)
```

`RealAccountsObserver` (`observability/real_accounts.py`) and
`command_center_bot.py`'s cockpit/Telegram rendering read exchange balances
through their **own** `ccxt` client instances (`_default_client_factory`),
entirely independent of `WalletSync` — **SOURCE_PROVEN**: no import of
`infra.wallet_sync` exists in `observability/real_accounts.py`. This is
Flow 1 in the O-02W-E contract's terminology (§9c); the causal graph above
is Flow 2. The two flows share no code path.

---

## 2. PAPER / TESTNET / REAL_API / UNKNOWN matrix

| Axis | PAPER | TESTNET_API | REAL_API | UNKNOWN |
|---|---|---|---|---|
| `ExchangeFactory.detect_mode()` | no API keys | keys + `EXCHANGE_TESTNET=true` | keys + `EXCHANGE_TESTNET=false` | not a `detect_mode()` output — `NOT_APPLICABLE` there |
| `ExecutionEngine._mode` | `"paper"` (default, unset by `_init_exchange` on failure) | `"testnet"` | `"live"` | never set to this string — `NOT_APPLICABLE` |
| `wallet_mode` passed to `get_wallet_sync()` | forced `"paper"` whenever `PAPER_TRADING_ENABLED` is truthy, **regardless of `self._mode`** | `self._mode` when `PAPER_TRADING_ENABLED` falsy and `_mode=="testnet"` | `self._mode` when `PAPER_TRADING_ENABLED` falsy and `_mode=="live"` | `NOT_APPLICABLE` — no UNKNOWN wallet mode exists in source |
| `WalletSync.get_balance()` numeric source | `WALLET_PAPER_CAPITAL` + ledger PnL | exchange balance (cached/fresh) or fallback (stale cache or `WALLET_PAPER_CAPITAL`) | same mechanism as TESTNET | never returns a sentinel; **`UNKNOWN` numeric value does not exist in this module** — **CONTRADICTION_FOUND** against the presentation-layer's UNKNOWN domain, see §9 |
| `resolve_mode_provenance()` display label (`observability/mode_provenance.py`) | `"PAPER"` (overrides everything when `PAPER_TRADING_ENABLED` truthy) | `"TESTNET_API"` | `"REAL_API"` | any `exec_mode` not in `{"paper","live","testnet"}`, or absent — fails closed **SOURCE_PROVEN** (`mode_provenance.py:44`) |
| Live order execution gate (`_place_live_order`) | always short-circuits to `mode="live_failed", error="blocked_by_paper_gate"` **before any network call**, `BEHAVIOR_PROVEN_HERMETIC` | reaches the exchange call (subject to `self._live`/`self._exchange` also being true) | reaches the exchange call | `NOT_APPLICABLE` |

Live order placement additionally requires `self._live is True` AND
`self._exchange is not None`, which in turn requires
`ExecutionEngine.from_env()`'s **three-way AND**: API keys present, mode
`!= "paper"`, and `LIVE_TRADING_CONFIRMED` truthy (`execution_engine.py:182-202`,
`SOURCE_PROVEN`, exercised by `quant_hedge_ai/agents/execution/test_execution_engine.py::TestFromEnv`).

---

## 3. WalletSync initialization order (H2)

`get_wallet_sync(exchange=None, mode=None)` (`infra/wallet_sync.py:227-244`):

- If the module-global singleton does not exist: creates it with
  `mode = mode or os.getenv("EXCHANGE_MODE", "paper")`.
- If it already exists: an `exchange` argument is attached **retroactively**
  only if the singleton currently has none; a `mode` argument is **silently
  ignored** — there is no code path that mutates `WalletSync._mode` after
  construction (`SOURCE_PROVEN` by inspection; `BEHAVIOR_PROVEN_HERMETIC` via
  `TestH2SingletonConstructionOrder.test_singleton_created_first_retains_its_mode_despite_later_explicit_mode`).

**Actual boot order in `core/advisor_loop.py`:**

1. Line ~3777: `bootstrap_capital_x(exec_engine._exchange)` →
   `get_wallet_sync(exchange=exchange)` (no `mode=` argument) — this is the
   call that **creates** the singleton. Its mode is `EXCHANGE_MODE` env
   (default `"paper"`), **not** derived from `PAPER_TRADING_ENABLED`.
2. Line 3835 (first) and lines 5740-5746 (every cycle thereafter):
   `exec_engine.fetch_available_capital()` → `get_wallet_sync(exchange=self._exchange,
   mode=wallet_mode)` where `wallet_mode` **is** derived from
   `PAPER_TRADING_ENABLED`.

Because step 1 always runs first and always creates the singleton, step 2's
`mode=` argument is a no-op for `.mode` on every subsequent call for the
life of the process — `BEHAVIOR_PROVEN_HERMETIC`
(`TestH2SingletonConstructionOrder.test_bootstrap_capital_x_creates_singleton_before_fetch_available_capital_mode`).

**Practical consequence:** this ordering issue is *masked* rather than
*harmless*, because `get_balance()` itself re-checks `self._mode` on every
call (not a cached decision) and `fetch_available_capital()` always passes
the intended `wallet_mode` — but since the singleton's `.mode` never
actually changes to reflect it, `get_balance()`'s paper/live branch is
driven by whatever `EXCHANGE_MODE` said at first construction, not by
`PAPER_TRADING_ENABLED` on later calls, for any code path that reads
`wallet.mode` directly (e.g. Telegram/cockpit provenance rendering that
calls `get_wallet_sync().mode` rather than recomputing). `.get_balance()`
called with **no explicit mode override** (i.e. as `WalletSync.get_balance()`
is always invoked — it takes no mode parameter) therefore behaves according
to the **singleton's frozen `._mode`**, not the freshly intended one. In the
observed default configuration (`EXCHANGE_MODE` unset → `"paper"`,
`PAPER_TRADING_ENABLED` default `"true"`) both agree, which is why this has
not manifested as a visible defect: the divergence only becomes observable
when `EXCHANGE_MODE` is explicitly set to something other than what
`PAPER_TRADING_ENABLED` would imply (Scenario L, K).

---

## 4. H4 — API-mode fallback chain (fresh / cache / `_x` / paper fallback)

Four distinct values exist and must not be conflated (`SOURCE_PROVEN`,
`wallet_sync.py`):

| Value | What it is | When used |
|---|---|---|
| **fresh** | `exchange.fetch_balance()` result, just fetched | live/testnet, cache expired or `force_refresh=True`, fetch succeeds, `usdt > 0` |
| **cache (`_last_value`)** | last successful fresh value | live/testnet, cache still within `WALLET_CACHE_TTL_S` (default 30s); OR live/testnet fetch fails/raises/returns 0 and a prior successful fetch exists |
| **`_x` (bootstrapped capital)** | value set once via `bootstrap()`/`set_x()` at process start, `>= MIN_CAPITAL_X` | only reached inside `_base_capital()`'s non-paper branch, and only when `_last_value is None` (i.e., no fresh/cached value has ever existed) |
| **paper fallback (`WALLET_PAPER_CAPITAL`)** | the env-configured paper constant | (a) always, in paper mode; (b) in live/testnet mode, whenever `_last_value is None` **and** `_x is None` — i.e. bootstrap never succeeded and no fetch has ever succeeded |

**Confirmed (Scenario F, `BEHAVIOR_PROVEN_HERMETIC`,
`TestScenarioFGHApiFailureFallbacks.test_live_mode_api_error_no_cache_falls_back_to_paper_capital_constant`):**
in live/testnet mode, with no cache and no successful bootstrap, an API
error causes `get_balance()` to return `WALLET_PAPER_CAPITAL` — **a paper
sizing constant silently substituted as a live-mode numeric capital
figure**, with no distinguishing signal to any downstream consumer
(`order_size`, `PortfolioBrain`, `CapitalAllocationEngine`,
`ExecutiveOverride`, the throttle/drawdown computations all receive a plain
`float`).

**Confirmed (Scenario G, `BEHAVIOR_PROVEN_HERMETIC`):** with a prior
successful fetch, a subsequent failure returns the stale cached value
instead — this is the design intent stated in the module docstring
("évite de fabriquer un faux drawdown sur un échec réseau temporaire").

**Confirmed (Scenario H, `BEHAVIOR_PROVEN_HERMETIC`):** a genuine zero
balance (`free.USDT == 0.0`) is rejected by the `if usdt > 0:` guard
(`wallet_sync.py:194`) and falls through to the same fallback chain as an
API error — the caller cannot distinguish "exchange reachable, balance
truly zero" from "exchange unreachable" from the return value alone.

**Contrast (`test_bootstrap_zero_balance_returns_none_not_zero`):**
`bootstrap()` itself does fail closed to `None` (not a substituted number)
when the balance is below `MIN_CAPITAL_X` — this is the one capital-related
entry point in this module that does not silently substitute a number. It
is a one-shot call at process start, not part of the per-cycle refresh
path, so it does not protect the per-cycle `get_balance()` calls above.

This entire mechanism is independently documented, with identical
conclusions, in `docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md`
§9c Flow 2 (Correction E / R1.1), which this audit's hermetic tests now
additionally prove at the unit level rather than by source reading alone.

---

## 5. H5 — Initial behavior vs. refresh behavior

**Initial (bootstrap, `core/advisor_loop.py:3835,4046`):**
`real_capital = exec_engine.fetch_available_capital()` is fetched once, and
`order_size = min(max_order, real_capital * V9_MAX_POSITION_WEIGHT)`
(line 4046) is computed **once**, from that single bootstrap-time value.

**Refresh (per cycle, `core/advisor_loop.py:5739-5746`):**

```python
try:
    fresh_capital = exec_engine.fetch_available_capital()
    if fresh_capital > 0:
        real_capital = fresh_capital
        portfolio_brain.update_capital(real_capital)
        capital_engine.update_capital(real_capital)
except Exception:
    pass
```

`SOURCE_PROVEN` findings:

- `real_capital` (the bare local) **is** reassigned every cycle when
  `fresh_capital > 0`.
- `PortfolioBrain.update_capital()` and `CapitalAllocationEngine.update_capital()`
  **are** called every cycle with the refreshed value — `BEHAVIOR_PROVEN_HERMETIC`
  via `TestScenarioJRefreshPropagation` (both engines' subsequent outputs
  change after `update_capital()`).
- `ExecutiveOverride.update(capital_current=real_capital)` is called
  separately, later in the same cycle (line 7241), using the **already
  refreshed** `real_capital` local from the same cycle — so it does receive
  the fresh value, just via a second call site rather than the block above.
- **`order_size` (the bare local computed once at line 4046) is never
  recomputed anywhere in the main loop.** `grep -n "order_size\s*="` across
  `core/advisor_loop.py` shows exactly one assignment (line 4046); its two
  later uses (lines 6075, 6163) both read the frozen bootstrap-time value
  (`order_size * _sc_state["risk_factor"]`, or as a fallback when
  `CapitalAllocationEngine` output is absent). If `fresh_capital` grows or
  shrinks substantially across a long-running session, the base sizing
  figure feeding `analyze_symbol()` does not track it — only the two
  `update_capital()`-driven engines do.
- `_p10_throttle`, `_p10_kpi.initial_capital`, and the `max_order` ceiling
  derived from `_p10_throttle` at bootstrap (lines 3871-3896) are likewise
  computed once and not refreshed — consistent with §6's finding that P10
  throttle is deliberately pinned, not merely stale.

**Classification:** `CONTRADICTION_FOUND` (documentation claims a single
unified "capital refresh," but three different consumers — `order_size`,
the two `update_capital()`-driven engines, `ExecutiveOverride` — have three
different refresh behaviors: frozen / refreshed-together / refreshed
separately-but-same-cycle).

---

## 6. H6 — CapitalThrottle pinned to `WALLET_PAPER_CAPITAL`

Two unrelated classes share the name `CapitalThrottle`:

- `capital_deployment/capital_throttle.py::CapitalThrottle` — phase-based
  ceiling (F-01..F-05), a **percentage of a `total_capital` figure fixed at
  construction**. This is the "P10" throttle referenced in
  `core/advisor_loop.py`.
- `quant_hedge_ai/agents/risk/capital_throttle.py::CapitalThrottle` — an
  unrelated drawdown-based size-factor throttle (P7), constructed with no
  capital argument at all and driven entirely by `update(capital)` calls
  each cycle (`SOURCE_PROVEN`, line 5253 imports it under the alias
  `_CTCls`, distinct from `_P10ThrottleCls` at line 3862). This second
  class is `NOT_APPLICABLE` to H6.

`core/advisor_loop.py:3871`:

```python
# ADR-0011: base épinglée pour stationnarité du sizing pendant la validation.
_p10_throttle = _P10ThrottleCls(total_capital=_paper_capital, phase=_P10_PHASE)
```

`_paper_capital = float(os.getenv("WALLET_PAPER_CAPITAL", "1000"))`
(line 3779) — this is constructed **unconditionally**, including in the
non-`advisor_only` (live) branch (lines 3889-3896: `max_order =
min(max_order, _p10_throttle.throttled_size(max_order))`).

**Established effect (`BEHAVIOR_PROVEN_HERMETIC`,
`TestH6CapitalThrottlePinnedToPaperCapital`):** the F-01 phase ceiling is
`min(1% of WALLET_PAPER_CAPITAL, 100 EUR)` — entirely independent of
`real_capital`/live exchange balance, by construction. This throttle's
ceiling therefore **cannot grow or shrink with actual live/testnet
capital**; it only changes if `WALLET_PAPER_CAPITAL` or `P10_PHASE` change.

**Not classified as a defect:** the in-source comment explicitly cites
ADR-0011 and "stationnarité du sizing pendant la validation" (sizing
stationarity during validation) as the rationale — this matches
`CLAUDE.md`'s ADR-0007 constitutional rule verbatim: *"Base de sizing
épinglée à `WALLET_PAPER_CAPITAL` jusqu'aux gates de calibration ; tout
sizing dépendant de l'equity est une décision de calibration explicite,
jamais un effet de redémarrage."* This audit therefore classifies H6 as
`SOURCE_PROVEN` intentional design, not `CONTRADICTION_FOUND` — but flags
that its *effect* in the non-`advisor_only` branch is to throttle **live**
order sizes using a **paper** capital ceiling, which is a real
architectural coupling between the two, however deliberately chosen.

---

## 7. Every consumer and its classification

| Consumer | Source location | Classification | Note |
|---|---|---|---|
| `order_size` (base sizing) | `core/advisor_loop.py:4046` | `DECISION_INPUT` | frozen at bootstrap, see §5 |
| `PortfolioBrain._capital` | `portfolio_brain.py:111-117`, wired `advisor_loop.py:5743` | `RISK_INPUT` | refreshed every cycle |
| `CapitalAllocationEngine._capital` | `capital_allocation_engine.py:99-103`, wired `advisor_loop.py:5744` | `RISK_INPUT` / `DECISION_INPUT` | drives Kelly sizing; refreshed every cycle |
| `ExecutiveOverride._capital` / `_metrics.capital_current` | `executive_override.py:168-174`, wired `advisor_loop.py:7241` | `RISK_INPUT` | drives drawdown-based VETO/REDUCE levels; refreshed every cycle, same-cycle as above |
| P10 `CapitalThrottle` (`capital_deployment`) | `advisor_loop.py:3871-3896` | `EXECUTION_LIMIT` | pinned to `WALLET_PAPER_CAPITAL`, not refreshed (§6) |
| P7 `CapitalThrottle` (`quant_hedge_ai.../risk`) | `advisor_loop.py:5253+` | `RISK_INPUT` | drawdown-factor throttle, driven by `.update(capital)` calls, distinct class from P10 (§6) |
| `ExecutionEngine._place_live_order` size clamps (`min_notional`, balance check) | `execution_engine.py:481-534` | `EXECUTION_LIMIT` | reads live balance directly via `self._exchange.fetch_balance()`, independent of `WalletSync` |
| `ExecutionEngine.create_order` `SessionGuard` | `session_guard.py` (imported, not read in full — see §10) | `RISK_INPUT` | session-level drawdown/order-size checks, invoked before every order |
| `RealAccountsObserver` (`observability/real_accounts.py`) | own `ccxt` client, independent of `WalletSync` | `DISPLAY_ONLY` | Flow 1; §9c-confirmed no feedback path exists into sizing/risk (`SOURCE_PROVEN`: no import of it anywhere in the risk/execution modules read for this audit) |
| `aggregate()` (real_accounts.py) | same module | `DISPLAY_ONLY` | feeds "Statut Compte Réel" header text only |
| Command Center bot's capital rendering | `capital_deployment/command_center_bot.py:163-170` | `TELEMETRY_ONLY` | its own docstring explicitly disclaims being a provenance proof; renders `resolve_mode_provenance()`'s label |
| `resolve_mode_provenance()` | `observability/mode_provenance.py` | `TELEMETRY_ONLY` | pure presentation-layer label resolver, fails closed to `UNKNOWN`; does not feed any decision |
| `session_pnl_since_restart()` | `wallet_sync.py:212-220` | `TELEMETRY_ONLY` | explicitly documented as display-only, "never for sizing/risk" (`SOURCE_PROVEN`, docstring + no call site outside Telegram messages found) |
| `WalletSync.initial_capital()` | `wallet_sync.py:208-210` | `RISK_INPUT` | used for ROI%/drawdown% computation per its own docstring — not read in full call-site detail beyond that docstring claim; `RUNTIME_UNKNOWN` for exact consumers (not among the files mandated for full read) |

---

## 8. Contradictions between comments and actual behavior

1. **`advisor_loop.py:3778` `_paper_mode` predicate vs. the decisional
   gate.** `_paper_mode = os.getenv("PAPER_TRADING_ENABLED",
   "true").lower() == "true"` accepts only the literal string `"true"`,
   while the actual decisional gates (`ExecutionEngine._paper_trading_enabled()`,
   `fetch_available_capital()`'s inline check, `resolve_mode_provenance()`)
   all accept `{"1","true","yes","on"}`. `CONTRADICTION_FOUND`,
   `BEHAVIOR_PROVEN_HERMETIC`
   (`TestH3ModePredicateConsistency.test_advisor_loop_bootstrap_predicate_diverges_from_execution_engine`).
   **Scope-limited:** this local variable is used exactly once, to pick
   between two Telegram message strings (STANDBY vs LIVE wording) — it is
   `DISPLAY_ONLY`/`TELEMETRY_ONLY`, not wired into sizing or execution. If
   `PAPER_TRADING_ENABLED=1` (numeric truthy, accepted everywhere else),
   the operator would see a "LIVE" Telegram banner while the system is in
   fact still in PAPER mode for every decisional purpose — a **presentation
   bug**, not a boundary breach, but exactly the class of divergence this
   codebase has already had to fix once before (see
   `tests/test_advisor_loop_balance_provenance.py`'s own docstring
   describing an earlier, now-fixed instance of this same bug pattern in
   `_balance_provenance_from_mode`).

2. **`WalletSync.get_balance()`'s numeric domain vs. the presentation
   layer's `PAPER | REAL_API | TESTNET_API | UNKNOWN` domain.**
   `command_center_bot.py`'s own comment (quoted in §9c of the O-02W-E
   contract) states the provenance label fails closed to `UNKNOWN` on an
   unrecognized mode — true for the **label**
   (`resolve_mode_provenance()`, `SOURCE_PROVEN`), but the **numeric
   capital value** that label is meant to describe never has an `UNKNOWN`
   state: it is always a concrete `float`, sourced per §4's fallback chain.
   `CONTRADICTION_FOUND` only if the two domains are conflated — the O-02W-E
   contract (§9c, R1.1) already corrects this conflation in its own prior
   text; this audit's tests (`TestScenarioKEnvDivergence.test_mode_provenance_label_fails_closed_on_unrecognized_exec_mode`)
   independently confirm both halves of that correction hermetically.

3. **Two same-named `CapitalThrottle` classes** (§6) — not a contradiction
   in behavior, but a naming collision that makes source navigation and any
   future refactor error-prone; documented here as a latent audit risk.

---

## 9. Runtime proof limits (what could NOT be established hermetically)

- **Whether `EXCHANGE_MODE` is ever actually set to a value diverging from
  `PAPER_TRADING_ENABLED` in the deployed VPS `.env`.** §3's masking effect
  only manifests under that divergence; this audit proves the mechanism
  exists in source and under hermetic test, but cannot inspect the VPS's
  live environment (prohibited by mission scope: no VPS access). `RUNTIME_UNKNOWN`.
- **Whether a live/testnet API outage has ever actually triggered the
  paper-capital-substitution path (§4, Scenario F) in production**, versus
  only ever hitting the stale-cache path (Scenario G). Both are proven
  reachable in source and hermetically; which one has occurred historically
  on the VPS is `RUNTIME_UNKNOWN` — would require VPS log access, out of
  scope.
- **`SessionGuard`'s exact drawdown/size checks** (`quant_hedge_ai/agents/risk/session_guard.py`)
  were imported and referenced by `ExecutionEngine` but not among the files
  mandated for full read by this mission; its exact provenance chain for
  the capital figures it uses is `RUNTIME_UNKNOWN` here — flagged for a
  follow-up audit, not fabricated.
- **`WalletSync.initial_capital()`'s full consumer list** beyond its own
  docstring claim (ROI%/drawdown% display) — not traced to every call site;
  `RUNTIME_UNKNOWN`.
- **Whether `capital_deployment/capital_throttle.py`'s P10 throttle or
  `capital_deployment/emergency_stop_manager.py`/`phase_kpi_tracker.py`
  read any capital figure other than the ones documented here** — these
  two modules were imported by `advisor_loop.py` in the same block but not
  among the files mandated for full read; not characterized further here.
- Production VPS behavior (restart timing, actual `.env` contents, real
  exchange responses) is **out of scope by explicit prohibition** in this
  mission and is not claimed anywhere in this document.

---

## 10. Final verdict

Per the mission's own decision rule: *"If an API balance can influence
PAPER, or if paper capital can silently feed live/testnet sizing, the
verdict CANNOT be `BOUNDARY_PROVEN_SAFE`."*

- §1/§2 (H1): no evidence an API balance influences PAPER-mode sizing —
  `PAPER_TRADING_ENABLED` truthy forces `wallet_mode="paper"` inside
  `fetch_available_capital()` on first singleton construction, and paper
  mode's `get_balance()` never calls `exchange.fetch_balance()`
  (`BEHAVIOR_PROVEN_HERMETIC`, exchange call count = 0 in every paper-mode
  test in this suite).
- §4 (H4): **paper capital (`WALLET_PAPER_CAPITAL`) CAN and DOES silently
  feed live/testnet sizing** — Scenario F, `BEHAVIOR_PROVEN_HERMETIC` — any
  time a live/testnet capital fetch fails with no prior cache and no
  successful bootstrap.

Per the mission's decision rule, this single confirmed finding is
sufficient on its own to preclude `BOUNDARY_PROVEN_SAFE`. This is not a
speculative or `RUNTIME_UNKNOWN` finding — it is proven both from source
(`wallet_sync.py:159-206`) and from a hermetic unit test exercising the
exact fallback chain with no network access.

**VERDICT: REMEDIATION_REQUIRED**

This does not mean the current behavior is unauthorized or accidental —
§9c of `docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md` already
identifies this exact mechanism and explicitly defers its resolution to "a
dedicated boundary hardening mission," which this document is a
prerequisite audit for, not a substitute for. The remediation this verdict
calls for is an explicit MASTER/operator decision on whether the
live/testnet fallback-to-paper-capital behavior is acceptable as-is (with
its risk made visible, e.g. a distinct `UNKNOWN`/`DEGRADED` numeric
sentinel instead of a silent paper-capital substitution) or must be
hardened — precisely the decision this mission's brief anticipated and
explicitly prohibited this audit from making unilaterally ("No change to
strategy/risk/sizing/portfolio/execution logic").
