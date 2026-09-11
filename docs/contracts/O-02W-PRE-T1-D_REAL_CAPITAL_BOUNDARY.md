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
`tests/test_pre_t1_d_real_capital_boundary.py` (58 hermetic tests, no
network, no secrets, fake exchanges only — 46 from the original round, 10
added in R1 (Cases 1-5, §11), plus 2 added in R1.1 (Cases 6-7, §11a) that
call the real `ExecutionEngine.from_env()` classmethod).

**R1.1 evidence-level framework (this round):** every hermetic finding in
this document is now tagged with exactly one of four evidence phrases,
never conflated:
- `REAL_FROM_ENV_PATH_PROVEN_HERMETIC` — a test that actually calls
  `ExecutionEngine.from_env()` (with `ExchangeFactory.create` monkeypatched,
  no network) and observes its genuine construction result. Only §11a
  Cases 6-7 currently carry this tag.
- `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` — the real `WalletSync`/
  `fetch_available_capital()`/`get_balance()` production functions are
  exercised, but `ExecutionEngine._exchange`/`_mode` were assigned directly
  by the test (`eng._exchange = fake; eng._mode = "live"`), not produced by
  `from_env()`. This is what §11 Cases 1-5 (and the original round's
  Scenarios A-K) prove — a real mechanism, with test-injected engine state.
- `SOURCE_REACHABLE_CONFIGURATION` — a combination of env vars that source
  inspection shows is reachable (and, since R1.1, that §11a Case 6 proves
  hermetically through `from_env()` itself) but that no coherent operator
  intent would set simultaneously (`PAPER_TRADING_ENABLED=true` AND
  `LIVE_TRADING_CONFIRMED=true` together).
- `DEPLOYED_RUNTIME_UNKNOWN` — the actual VPS `.env`/process state, never
  established by this audit (§9).

**R1 correction note (this section added on the follow-up round):** the
original round's H1 conclusion ("PAPER is isolated from API balance") was
stated unconditionally. That statement is corrected throughout this document
to `PAPER_ISOLATION_CONDITIONAL_ON_EFFECTIVE_SINGLETON_MODE` — see §1, §3,
§13 and §11 (Case 1-5 results) below. The original H2/H4/H5/H6
findings and their source citations are unchanged and re-verified against
current source as part of this correction; only their framing/classification
and the H1 conclusion are revised. **Runtime scope note:** this entire audit
characterizes code behavior under hermetic test, never the deployed VPS
`.env`/process state — the actual VPS runtime environment-variable
configuration remains `RUNTIME_UNKNOWN` throughout this document, including
after this correction.

**R1.1 correction note (this section added on the second follow-up round):**
R1's §11 Case 1 constructed `ExecutionEngine` directly
(`ExecutionEngine(live=False)` then `eng._exchange = fake_exchange;
eng._mode = "live"`) and the R1 §10a matrix presented that combination
alongside a `LIVE_TRADING_CONFIRMED=false` column, as if it reproduced what
`ExecutionEngine.from_env()` itself would construct. It does not:
`from_env()` only ever attaches a live exchange
(`self._exchange = self._init_exchange()`) when its own three-way AND —
`has_api_key AND mode != "paper" AND LIVE_TRADING_CONFIRMED` — is true; with
`LIVE_TRADING_CONFIRMED=false`, `from_env()` constructs `ExecutionEngine(live=False)`,
which never calls `_init_exchange()` at all, leaving `_exchange=None` and
`_mode="paper"` (the `__init__` default). §11 Case 1's `_mode="live"` +
attached-exchange state, together with `LIVE_TRADING_CONFIRMED=false`, is
therefore a state `from_env()` never produces — this was a mismatch between
what R1's test actually exercised (`PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE`)
and what the matrix's column implied it represented. This round (R1.1)
corrects the mismatch by: (a) introducing the four-way evidence-level
framework above; (b) relabeling every §11 Case 1-5 finding as
`PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` throughout; (c) adding new §11a
Cases 6-7, which call the actual `ExecutionEngine.from_env()` classmethod
(no manual `_exchange`/`_mode` assignment) under, respectively, the
source-reachable-but-operator-incoherent `LIVE_TRADING_CONFIRMED=true` +
`PAPER_TRADING_ENABLED=true` combination and the `LIVE_TRADING_CONFIRMED=false`
contrast; (d) correcting the §10a matrix rows accordingly. No prior finding
about the WalletSync-singleton mode-freezing mechanism itself (§3, §3a) is
withdrawn — that mechanism is real and remains proven; only the claim that
R1's Case 1 reproduced `from_env()`'s own construction is corrected.

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

**Practical consequence (R1-corrected — this is the finding that overturns
the original round's unconditional H1 claim):** `get_balance()` branches
strictly on `self._mode` — the singleton's frozen mode — **not** on the
`wallet_mode` string that `fetch_available_capital()` computed and passed
into `get_wallet_sync(mode=wallet_mode)`. Because that `mode=` argument is
silently discarded once the singleton exists (§3 above), **the entire
paper-vs-live numeric branch actually taken by `get_balance()` is decided by
whichever mode created the singleton first — `EXCHANGE_MODE` at
`bootstrap_capital_x()` time — regardless of what `PAPER_TRADING_ENABLED`
requests on every later call.** Concretely: if `EXCHANGE_MODE=live` (or
`testnet`) and `bootstrap_capital_x()` runs before any `PAPER_TRADING_ENABLED`
check is consulted (the actual `core/advisor_loop.py` order, always), the
singleton stays in `live`/`testnet` mode for the life of the process — so
`get_balance()` takes the live/testnet branch, **queries the real exchange**,
and returns that API-sourced value to `fetch_available_capital()`'s caller,
**even though `PAPER_TRADING_ENABLED=true` and the caller explicitly
requested `wallet_mode="paper"`.** This is proven hermetically through the
real call path in §11 Case 1. In the observed default configuration
(`EXCHANGE_MODE` unset → `"paper"`, `PAPER_TRADING_ENABLED` default `"true"`)
both agree and no leak occurs — the divergence is only observable when
`EXCHANGE_MODE` is explicitly set to something other than what
`PAPER_TRADING_ENABLED` would imply (Scenario L, K; §11 Cases 1-3). This is
**not** merely a display-provenance issue (contrast the original framing):
it changes which numeric branch of `WalletSync.get_balance()` executes and
whether `exchange.fetch_balance()` is actually called — see §4a (H2
reclassification) below.

**Four distinct things this document must never conflate (BLOCKER A):**

1. **Isolation of calculations** — whether the *number* fed into
   sizing/risk originates from the exchange API or from
   `WALLET_PAPER_CAPITAL`. This is what §3/§11 Cases 1-3 characterize, and
   it is **conditional** on the singleton's effective mode, not guaranteed
   by `PAPER_TRADING_ENABLED=true`.
2. **Blocking of network *execution*** — `_place_live_order`'s
   `blocked_by_paper_gate` short-circuit, which reads
   `ExecutionEngine._paper_trading_enabled()` directly (not through the
   frozen singleton) and always fires before any order reaches the network
   when `PAPER_TRADING_ENABLED` is truthy. This gate is **unconditionally
   reliable** for its narrow purpose (no real order is ever sent) —
   `BEHAVIOR_PROVEN_HERMETIC`, §11 Case 1 re-confirms it fires even while
   the API balance leaked into the capital figure in the very same test.
   Blocking execution does **not** prove the capital figure computed
   upstream of that gate was isolated from the API — these are different
   guarantees, proven by different mechanisms, and Case 1 shows they can
   diverge in the same call sequence.
3. **Capital provenance** — which fallback tier (fresh fetch / stale cache
   / `_x` / `WALLET_PAPER_CAPITAL`) actually produced the returned float;
   see §4.
4. **The mode displayed to the operator** — `resolve_mode_provenance()`'s
   label, a separate presentation-layer computation (§8.2) that can itself
   diverge from both (1) and (3).

---

## 3a. H2 reclassification (Correction D) — not a display bug, a branch-selection bug

**R1 correction:** the original round scoped H2 narrowly, alongside H3's
Telegram-banner finding. H2 is reclassified here as its own primary finding,
because it does not just affect what is *displayed* — it determines **which
numeric branch of `WalletSync.get_balance()` actually executes**
(`if self._mode == "paper":` vs. the live/testnet branch that calls
`self._exchange.fetch_balance()`), independent of any display code.

**Both contamination directions are proven, hermetically, through the real
call path (§11):**

1. **API → PAPER direction (§11 Case 1/2):** singleton frozen in
   `live`/`testnet` mode by `bootstrap_capital_x()` (from `EXCHANGE_MODE`),
   then `PAPER_TRADING_ENABLED=true` is requested later —
   `fetch_available_capital()`'s `wallet_mode="paper"` argument is discarded,
   `get_balance()` takes the live/testnet branch, and the real exchange
   balance is returned to a caller that believes it is operating in PAPER
   mode. `exchange.fetch_balance()` **is called** — `BEHAVIOR_PROVEN_HERMETIC`,
   call count asserted directly.
2. **Paper → LIVE/TESTNET direction (§11 Case 3):** singleton frozen in
   `paper` mode (no `EXCHANGE_MODE` set), then `PAPER_TRADING_ENABLED=false`
   is requested later with `ExecutionEngine._mode` set to `live`/`testnet` —
   the paper branch still executes, `WALLET_PAPER_CAPITAL` + ledger PnL is
   returned, and `exchange.fetch_balance()` is **never called**, even though
   a working exchange was available and the engine's own state believed it
   was in live/testnet mode. This connects directly to the original round's
   H4 finding (paper capital silently feeding live/testnet sizing) and to
   H6 (P10 throttle deliberately pinned to paper capital) — H2's paper→live
   direction is the *unintentional*, order-dependent counterpart to H6's
   *intentional*, ADR-0011-documented pinning.

**Secondary consequence, not the primary finding:** displayed provenance
(`resolve_mode_provenance()`, §8.2) can also diverge from the actual
numeric source, because it is computed independently from `exec_mode` and
`paper_trading_enabled` rather than by reading the singleton's true
`._mode`/branch — but this display divergence is downstream of, and
secondary to, the branch-selection effect documented above.

---

## 4. H4 — API-mode fallback chain (value origin vs. internal storage vs. branch executed)

**R1.2 correction (this section rewritten to fix a factual error left
uncorrected by R1.1):** the previous framing of this section ("four
independent fallback levels", `_x`/cache as separate operational tiers) is
replaced below by an explicit three-way distinction, verified against the
real `infra/wallet_sync.py` source:

- **Value origin** — where the number historically came from: `FRESH_API`
  (a `fetch_balance()` call that just succeeded), `BOOTSTRAP_X` (the
  one-shot `bootstrap()`/`set_x()` call at process start), `PAPER_BASE`
  (`WALLET_PAPER_CAPITAL`), or `PAPER_LEDGER_PNL` (paper-mode ledger
  replay).
- **Internal storage** — the field actually holding the value at read time.
  `_x` holds the capital accepted at bootstrap and is never overwritten
  after that (`wallet_sync.py:125`). `_last_value` holds either the
  X-bootstrap value **or** the most recent positive API value obtained
  afterward — `set_x()` writes `self._last_value = self._x` in the same
  call (`wallet_sync.py:126`, comment "fallback live aussi"), and a later
  successful `fetch_balance()` overwrites `_last_value` again
  (`wallet_sync.py:195`). `_x` and `_last_value` are therefore not
  independent channels: after any successful bootstrap, `_last_value` is
  never `None`.
- **Branch actually executed** — which code path `get_balance()`/
  `_fallback()`/`_base_capital()` take. `SOURCE_PROVEN`,
  `wallet_sync.py:159-206`:

```python
def _fallback(self) -> float:
    if self._last_value is not None:
        return self._last_value
    return self._base_capital()

def _base_capital(self) -> float:
    return self._x if self._x is not None else _PAPER_CAPITAL
```

**Real operational chain** (`SOURCE_PROVEN`, verified against current
source):

```
PAPER mode
→ PAPER_BASE + PAPER_LEDGER_PNL

LIVE/TESTNET mode
→ valid TTL cache → _last_value

→ else API attempt
   → positive value → _last_value updated → value returned
   → zero or exception → _fallback()

_fallback()
→ _last_value if not None
→ else _base_capital()

_base_capital() in LIVE/TESTNET
→ _x if not None
→ else PAPER_BASE
```

**Essential qualifier:** in the normal public cycle, a successful bootstrap
calls `set_x()`, which initializes `_x` and `_last_value`
**simultaneously**. The `_base_capital() → _x` branch is therefore
**normally not reached** after a successful public bootstrap, because
`_fallback()` returns `_last_value` first — `_base_capital()`'s `_x` branch
is only ever reached when `_last_value is None`, i.e. when `_x` was set
through some path other than the public `set_x()`/`bootstrap()` call (see
the `INTERNAL_STATE_ONLY_NOT_PRODUCED_BY_PUBLIC_BOOTSTRAP_PATH`
classification below), which no observed production call path produces.

**Consumer-visible provenance:** none of the above is tagged or surfaced to
the caller — `get_balance()` always returns a plain `float`; a consumer
cannot tell from the return value alone whether it came from a fresh fetch,
a cache hit, or the X-bootstrap value replayed through `_last_value` (see
Case 5c/5d below for the sharper zero-vs-error instance of this same
non-distinguishability).

| Value | Storage at read time | When used |
|---|---|---|
| **fresh** | not stored yet; about to become `_last_value` | live/testnet, cache expired or `force_refresh=True`, fetch succeeds, `usdt > 0` |
| **cache / X-bootstrap replay (`_last_value`)** | `_last_value` | live/testnet, cache still within `WALLET_CACHE_TTL_S` (default 30s); OR live/testnet fetch fails/raises/returns 0 **and** `_last_value is not None` (populated either by a prior successful fetch, or by `set_x()` at bootstrap, or both) |
| **`_x`-only branch of `_base_capital()`** | `_x` | only reached when `_last_value is None` — `INTERNAL_STATE_ONLY_NOT_PRODUCED_BY_PUBLIC_BOOTSTRAP_PATH`: not producible by a normal `set_x()`/`bootstrap()` call, since that call sets `_last_value` in the same step; would require manual private-attribute mutation, an undemonstrated state-restore path, a future production change, or internal corruption |
| **paper fallback (`WALLET_PAPER_CAPITAL`)** | module constant `_PAPER_CAPITAL` | (a) always, in paper mode; (b) in live/testnet mode, whenever `_last_value is None` **and** `_x is None` — i.e. bootstrap never succeeded and no fetch has ever succeeded |

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

**R1.2 correction (§11 Case 5b):** R1.1 stated that Case 5b's returned value
was "`_x`, via `_base_capital()`" — this was factually wrong and is
corrected here. `WalletSync.set_x()` (called internally by a successful
`bootstrap()`) seeds `self._last_value = self._x` in the same call
(`wallet_sync.py:126`, comment "fallback live aussi"). So a process that
successfully bootstraps and then experiences an API error does **not**
reach `_base_capital()` at all: `_fallback()` finds `_last_value` is not
`None` (it equals `300.0`, the bootstrapped value) and returns it directly
— `_base_capital()` and its `_x` branch are never called. `_x`'s value is
still the one visible in the result, but only because `_last_value` was
seeded from it at bootstrap time, not because `_base_capital()`'s `_x`
branch executed. The `_x`-only branch of `_base_capital()` is reached only
when `_last_value is None` — a state the public `set_x()`/`bootstrap()`
path never leaves behind, since it always sets both fields together;
producing it requires manual private-attribute mutation, an undemonstrated
state-restore path, a future production change, or internal corruption
(`INTERNAL_STATE_ONLY_NOT_PRODUCED_BY_PUBLIC_BOOTSTRAP_PATH`, see §4 above).
Case 5b (renamed `test_bootstrap_seeded_last_value_is_returned_after_api_failure`)
now proves this directly: it spies on `_base_capital()` and asserts it is
called zero times while still returning `300.0` via `_last_value`. This
does not change the H4 verdict; it corrects which mechanism — `_last_value`
replay, not the `_x` branch of `_base_capital()` — actually produces the
observed value.

**R1 refinement (§11 Case 5c/5d — explicit non-distinguishability finding):**
a genuine zero balance (Scenario H) and an API error (Scenario F/G) are
**not distinguishable from `get_balance()`'s return value, from the outside,
by design** — both fall through to the identical `return self._fallback()`
call with no side channel (no return-value tag, no raised/re-raised
exception, no distinct log field surfaced to the caller) that would let a
caller tell "exchange reachable, balance truly zero" apart from "exchange
unreachable." This is stated here as an explicit, proven finding (§11 Case
5c/5d), not inferred or assumed away — the current implementation genuinely
cannot make this distinction from `WalletSync.get_balance()`'s return type
alone.

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
| `ExecutionEngine.create_order` `SessionGuard` | `session_guard.py` (imported, not read in full — see §9) | `RISK_INPUT` | session-level drawdown/order-size checks, invoked before every order |
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

## 10. Mode-combination matrix (Correction C)

**R1.1 section-numbering correction:** this document previously numbered
sections `9`, `10a`, `11`, then `10` (Final verdict) out of order. Sections
are renumbered here to run sequentially: `10` (this matrix, was `10a`), `11`
(Case 1-5, unchanged number), `12` (new — Case 6-7, `from_env()`), `13`
(Final verdict, was `10`).

Every row is tagged with exactly one of `SOURCE_REACHABLE` (the code path
exists and was read, but not exercised under hermetic test in this file),
`BEHAVIOR_PROVEN_HERMETIC` (a test in `tests/test_pre_t1_d_real_capital_boundary.py`
exercises this exact combination through the real call path), or
`RUNTIME_UNKNOWN` (whether this combination occurs on the deployed VPS is
not established by this audit and is out of scope).

Each row is additionally marked **`INJECTED`** (state assigned directly on
`ExecutionEngine` by the test — `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE`)
or **`FROM_ENV`** (constructed by the real `ExecutionEngine.from_env()` —
`REAL_FROM_ENV_PATH_PROVEN_HERMETIC`) so the construction path is never
ambiguous. Rows 1/2 (R1.1 correction) are `LIVE_TRADING_CONFIRMED=false`
+ `_mode="live"`-with-exchange-attached, a state `INJECTED` tests can
produce but `from_env()` itself never does — see row 8/§12 Case 6 and row 9/§12
Case 7 for what `from_env()` actually constructs in the two configurations
that matter here.

| `PAPER_TRADING_ENABLED` | `EXCHANGE_MODE` (singleton seed) | `ExecutionEngine._mode` | `LIVE_TRADING_CONFIRMED` | exchange present | singleton effective `.mode` | final numeric provenance | API call made | real order blockable | sizing/risk influence | Construction | Tag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| true | live | live | false | yes | **live** (frozen) | exchange balance | **yes** | blocked (`blocked_by_paper_gate`) | **yes — API leaks into "paper" figure** | `INJECTED` — not producible by `from_env()` with `LIVE_TRADING_CONFIRMED=false` (see row 9) | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (§11 Case 1) |
| 1/yes/on | live | live | false | yes | **live** (frozen) | exchange balance | **yes** | blocked | **yes** (same as above, truthy-variant) | `INJECTED` (same caveat as row 1) | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (§11 Case 2) |
| false | (unset → paper) | live/testnet | false | yes | **paper** (frozen) | `WALLET_PAPER_CAPITAL` + ledger PnL | no | allowable (subject to other gates) | **yes — paper capital feeds a live/testnet-requesting caller** | `INJECTED` | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (§11 Case 3) |
| false | live | live | false | no (raises) | live | `WALLET_PAPER_CAPITAL` (fallback, no cache/no `_x`) | attempted, failed | allowable | possible, ambiguous (§4/§11 Case 4) | `INJECTED` | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (§11 Case 4) |
| true | (unset → paper) | — | false | yes (unused) | paper | `WALLET_PAPER_CAPITAL` + ledger PnL | no | blocked | none (H1 holds in this row) | `INJECTED` | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (original round, Scenario A) |
| false | live | live | true | yes | live | exchange balance (fresh/cached) | yes | **allowable — real order can reach the exchange** | full — this is the intended live path | `INJECTED` | `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (original round, `TestFromEnv`, plus §2 live-fetch tests) |
| true | live | live | true | yes | **live** (frozen) | exchange balance | yes | blocked (paper gate overrides `LIVE_TRADING_CONFIRMED`) | yes (same leak as row 1; `LIVE_TRADING_CONFIRMED` does not change `fetch_available_capital()`'s outcome) | `FROM_ENV` — the real `ExecutionEngine.from_env()` classmethod, `ExchangeFactory.create` monkeypatched, no manual `_exchange`/`_mode` assignment | `REAL_FROM_ENV_PATH_PROVEN_HERMETIC` + `SOURCE_REACHABLE_CONFIGURATION` (operator-incoherent: both PAPER_TRADING_ENABLED and LIVE_TRADING_CONFIRMED true) (§12 Case 6) |
| true | (unset → paper) | paper (from_env `__init__` default; `_init_exchange()` never called) | false | **no — `_exchange=None`, `from_env()` never attaches one** | paper | `WALLET_PAPER_CAPITAL` + ledger PnL | no | n/a — `_place_live_order` would also block via the paper gate, but `create_order()`'s own `self._live` check already routes to the paper branch first | none | `FROM_ENV` — the real `ExecutionEngine.from_env()` classmethod; contrast to row 8 | `REAL_FROM_ENV_PATH_PROVEN_HERMETIC` (§12 Case 7) |
| — (any) | — | — | — | — | — (whatever this VPS process's actual boot order/env produced) | — | — | — | — | — | `DEPLOYED_RUNTIME_UNKNOWN` for the deployed VPS in every row above — this matrix proves code-level reachability and hermetic behavior only, never which row is currently active in production (§9) |

---

## 11. Case 1-5 results (R1 combined causal-order tests) — `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE`

All cases below exercise the **real production call chain**
(`bootstrap_capital_x()` → `ExecutionEngine.fetch_available_capital()` →
`WalletSync.get_balance()`), not an isolated `WalletSync.get_balance()`
call, per the mission's requirement. This is a **hermetic reproduction of
the real causal order using the production functions** (the actual
`bootstrap_capital_x`, `get_wallet_sync`, `fetch_available_capital`
functions are imported and called directly) — it is explicitly **not** a
"full `advisor_loop` loop" test: the daemon's main loop function itself is
never instantiated or run. See Correction F.

**R1.1 evidence-level correction:** every case in this section constructs
`ExecutionEngine` directly and assigns `_exchange`/`_mode` on it by hand
(`eng = ExecutionEngine(live=False); eng._exchange = fake_exchange;
eng._mode = "live"`) — this is **not** `ExecutionEngine.from_env()`. All
findings below are therefore tagged `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE`:
the `WalletSync` singleton, `get_wallet_sync()`, and
`fetch_available_capital()` are the real, unmodified production functions,
and the causal order/mode-freezing mechanism they prove is real — but the
`ExecutionEngine` state feeding into them was injected by the test, not
produced by `from_env()`. In particular, Case 1/2's
`LIVE_TRADING_CONFIRMED=false` + `_mode="live"`-with-exchange-attached
combination is a state `from_env()` itself never produces (see the R1.1
correction note above and §11a Case 7 for the actual `from_env()` behavior
under `LIVE_TRADING_CONFIRMED=false`). Do not read any case below as a
reproduction of `from_env()`'s own construction logic — for that, see §11a.

- **Case 1** (`TestR1Case1LiveModeSingletonFreezesDespitePaperFlag`):
  `EXCHANGE_MODE=live`, `PAPER_TRADING_ENABLED=true`, fake exchange
  `free_usdt=13579.0`. Proven: `bootstrap_capital_x()` returns `13579.0`
  (1 exchange call); singleton `.mode == "live"`;
  `eng.fetch_available_capital() == 13579.0` (1 additional exchange call,
  total 2) despite `PAPER_TRADING_ENABLED=true`; `_place_live_order` still
  returns `blocked_by_paper_gate` with 0 further exchange calls. **API
  capital DOES enter the calculation while the execution gate stays
  active** — the two guarantees are independent, as BLOCKER A requires
  this document to state explicitly.
- **Case 2** (`TestR1Case2PaperTruthyVariantsDoNotChangeCase1Outcome`,
  parametrized `"1"`/`"yes"`/`"on"`): identical outcome to Case 1 for all
  three truthy spellings — `fetch_available_capital() == 24680.0` (the
  Case-2 fixture's fake balance) in every sub-case; confirms the leak is
  independent of which truthy string is used.
- **Case 3** (`TestR1Case3PaperSingletonFreezesLiveTestnetRequest`,
  parametrized `"live"`/`"testnet"`): `EXCHANGE_MODE` unset (singleton
  starts `"paper"`), `PAPER_TRADING_ENABLED=false`, `ExecutionEngine._mode`
  set to `"live"`/`"testnet"`, fake exchange `free_usdt=99999.0`. Proven:
  singleton stays `"paper"`; `fetch_available_capital() == 321.0`
  (`WALLET_PAPER_CAPITAL`, exactly the paper fixture value) for **both**
  `"live"` and `"testnet"` requests; exchange call count unchanged from
  before the request (0 additional calls) — the live/testnet request is
  silently ignored and paper capital is used despite a working, queryable
  API.
- **Case 4** (`TestR1Case4LiveErrorNoCacheNoXRealPath`): singleton
  effective mode `"live"`, `PAPER_TRADING_ENABLED=false`, API raises, no
  cache, no successful bootstrap (`wallet.capital_x is None` asserted
  directly before the call). Through the real
  `ExecutionEngine.fetch_available_capital()` path:
  `capital == 42.0` (`WALLET_PAPER_CAPITAL`), exactly 1 failed exchange
  call attempted.
- **Case 5** (`TestR1Case5DistinguishableFallbackSources`, four
  sub-tests):
  - **5a stale cache:** returns the cached `777.0`, not `_x` (`500.0`,
    deliberately also set) or paper (`42.0`) — exchange called exactly
    once total (cache hit skips the second call).
  - **5b bootstrap-seeded `_last_value`:** returns `300.0` (the
    X-bootstrap value, replayed via `_last_value`, **not** via
    `_base_capital()`'s `_x` branch — see the §4 R1.2 correction) rather
    than `42.0` (paper). A successful `bootstrap()` seeds `_last_value =
    _x` in the same call, so `_fallback()` returns `_last_value` directly;
    `_base_capital()` is proven, via a call-count spy, to be invoked zero
    times in this case.
  - **5c/5d zero balance vs. API error:** both return the identical
    `42.0` via the identical `_fallback()` call — proven **not**
    distinguishable from the return value alone, stated as an explicit
    finding (§4 R1 refinement), not conflated as "the same thing" without
    proof: both source exchanges are asserted to have been called exactly
    once, confirming the *only* observable difference is upstream of
    `get_balance()`'s return type.

---

## 12. Case 6-7 results (R1.1 real `ExecutionEngine.from_env()` tests) — `REAL_FROM_ENV_PATH_PROVEN_HERMETIC`

Both cases below call the actual `ExecutionEngine.from_env()` classmethod —
no `ExecutionEngine(live=...)` direct construction, no manual `_exchange`/
`_mode` assignment. `infra.exchange_factory.ExchangeFactory.create` is
monkeypatched to return a fake exchange (no network, no `ccxt` import
required); `ExchangeFactory.info()`/`detect_mode()` run unmodified against
real (fake-valued) env vars, so `from_env()`'s own live/paper decision logic
executes for real.

- **Case 6** (`TestR1_1Case6FromEnvRealConstructionLiveConfirmedPaperEnabled`):
  fake `MEXC_API_KEY`/`MEXC_API_SECRET` present, `EXCHANGE_TESTNET` unset
  (→ `detect_mode()=="live"`), `LIVE_TRADING_CONFIRMED=true`,
  `PAPER_TRADING_ENABLED=true`, `EXCHANGE_MODE=live` (WalletSync singleton
  seed), fake exchange `free_usdt=55555.0`. Proven, through
  `ExecutionEngine.from_env()` itself:
  - `eng._live is True`, `eng._exchange is fake_exchange`, `eng._mode ==
    "live"` — `from_env()` genuinely attached a live exchange (it called
    `_init_exchange()` → `ExchangeFactory.create()`, the monkeypatched
    fake).
  - After `bootstrap_capital_x(exchange=eng._exchange)` (1 exchange call):
    the `WalletSync` singleton is created with `.mode == "live"`.
  - `eng.fetch_available_capital() == 55555.0` (1 further exchange call,
    total 2) despite `PAPER_TRADING_ENABLED=true` — the API balance is
    returned to a caller requesting "paper" wallet_mode, exactly as §3/§11
    Case 1 describe, but this time proven through the real construction
    path rather than injected `_mode`.
  - `eng._place_live_order(...)` still returns `blocked_by_paper_gate`,
    with **zero additional exchange calls** (call count stays at 2) —
    distinguishing the balance-read calls (2, both before the order
    attempt) from the order-attempt calls (0), confirming the order never
    reaches `fetch_ticker`/`fetch_balance`/`create_order`.
  - This proves a `SOURCE_REACHABLE_CONFIGURATION`
    (`PAPER_TRADING_ENABLED=true` AND `LIVE_TRADING_CONFIRMED=true`
    simultaneously — operator-incoherent, since PAPER and LIVE-CONFIRMED
    are not meant to both be asserted) is not merely theoretically
    reachable by source inspection but is **exercised end-to-end through
    `from_env()`** and reproduces the same API-leak-into-PAPER effect as
    §11 Case 1, this time without any test-injected engine state.
- **Case 7** (`TestR1_1Case7FromEnvRealConstructionConfirmedFalseContrast`):
  same fake API keys present, `LIVE_TRADING_CONFIRMED` unset (default
  `"false"`), `PAPER_TRADING_ENABLED=true`, `EXCHANGE_MODE` unset. Proven:
  - `eng._live is False`, `eng._exchange is None`, `eng._mode == "paper"`
    (the `__init__` default — never overwritten, because `_init_exchange()`
    is only called when `live=True`).
  - `ExchangeFactory.create()` is **never invoked** (`create_calls["n"] ==
    0`, tracked directly) — `from_env()`'s own three-way AND short-circuits
    before any exchange construction is attempted.
  - `eng.fetch_available_capital() == 1000.0` (`WALLET_PAPER_CAPITAL`
    fixture value), the fake exchange's `.calls == 0` throughout, and the
    `WalletSync` singleton ends up in `"paper"` mode.
  - This is the honest, hermetically-proven answer to BLOCKER A's required
    contrast: with `LIVE_TRADING_CONFIRMED=false`, the real `from_env()`
    path does **not** attach a live exchange at all — it falls back to the
    `__init__`-default paper state, not to some intermediate testnet state.
    §11 Case 1's `LIVE_TRADING_CONFIRMED=false` + attached-exchange
    combination (the mismatch this round corrects) simply cannot arise from
    `from_env()`.

---

## 13. Final verdict

Per the mission's own decision rule: *"If an API balance can influence
PAPER, or if paper capital can silently feed live/testnet sizing, the
verdict CANNOT be `BOUNDARY_PROVEN_SAFE`."*

**R1-corrected basis** (the original round's "H1 globally proven safe"
language is removed and replaced by the following six enumerated points):

1. **Singleton mode frozen at first call** (§3): `get_wallet_sync()`
   resolves `.mode` only once, at first construction, from `EXCHANGE_MODE`
   (default `"paper"`) — `SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC`.
2. **Later mode requests silently ignored** (§3): any subsequent
   `get_wallet_sync(mode=...)` call's `mode` argument is a no-op once the
   singleton exists — `SOURCE_PROVEN` + `BEHAVIOR_PROVEN_HERMETIC`.
3. **Possible API influence on PAPER-labeled calculations** (§3a direction
   1, §11 Case 1/2, and — through the real `ExecutionEngine.from_env()`
   construction path, no injected state — §12 Case 6): when the singleton
   is frozen `live`/`testnet` before a `PAPER_TRADING_ENABLED=true` request,
   the real exchange balance is returned to that caller —
   `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE` (§11) and, independently,
   `REAL_FROM_ENV_PATH_PROVEN_HERMETIC` (§12 Case 6).
4. **Possible paper-capital influence on LIVE/TESTNET calculations** (§3a
   direction 2, §11 Case 3, and the original round's H4/H6): when the
   singleton is frozen `paper` before a `live`/`testnet`-requesting caller,
   `WALLET_PAPER_CAPITAL` is returned instead — `BEHAVIOR_PROVEN_HERMETIC`.
5. **Ambiguous API fallback between error / zero / cache-or-bootstrap
   replay (`_last_value`) / paper capital** (§4, §11 Case 4/5): error,
   no-cache/no-bootstrap returns paper capital (Case 4); zero balance and
   API error are not distinguishable from the return value (Case 5c/5d);
   a fresh-fetch cache hit and a bootstrap-seeded `_last_value` replay are
   each individually distinguishable and proven so (Case 5a/5b) — the
   latter proven, via a `_base_capital()` call-count spy, to never reach
   the `_x` branch of `_base_capital()` — `BEHAVIOR_PROVEN_HERMETIC`
   throughout.
6. **`order_size` not recomputed after refresh** (§5/H5): `SOURCE_PROVEN`
   by grep (`core/advisor_loop.py`'s sole `order_size =` assignment, line
   4046, never reassigned) — no evidence found of any later recomputation;
   this audit did not find proof otherwise.

**Corrected conclusion replacing the original H1 statement:**
`PAPER_ISOLATION_CONDITIONAL_ON_EFFECTIVE_SINGLETON_MODE` — PAPER-mode
calculations are isolated from the exchange API **only when the singleton's
effective mode is actually `"paper"`** at the time `get_balance()` is
called. `PAPER_TRADING_ENABLED=true` does **not**, by itself, guarantee this
— it guarantees only that a real *order* cannot reach the network (point 2
of BLOCKER A's four-way distinction), which is a narrower and different
guarantee than "the capital figure was never touched by the API" (point 1).
In the process's actual default boot configuration (`EXCHANGE_MODE` unset →
`"paper"`), the two happen to coincide, which is why this had not manifested
as an externally visible defect — but that coincidence is a property of the
default configuration, not a property the code enforces.

**VERDICT: REMEDIATION_REQUIRED** (unchanged from the original round's
top-level verdict; only its documented basis is corrected above).

This does not mean the current behavior is unauthorized or accidental —
§9c of `docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md` already
identifies the H4/paper→live direction and explicitly defers its resolution
to "a dedicated boundary hardening mission," which this document is a
prerequisite audit for, not a substitute for. The remediation this verdict
calls for is an explicit MASTER/operator decision on: (a) whether the
live/testnet fallback-to-paper-capital behavior (point 4/5 above) is
acceptable as-is or must be hardened (e.g. a distinct `UNKNOWN`/`DEGRADED`
numeric sentinel instead of a silent substitution), and (b) whether
`get_wallet_sync()`'s mode-freezing-at-first-call behavior (points 1-3
above) should instead raise/log loudly on a divergent later `mode=` request,
or be resolved by ensuring `bootstrap_capital_x()` and
`fetch_available_capital()` are guaranteed to agree on mode before either
ever runs — precisely the decision this mission's brief anticipated and
explicitly prohibited this audit from making unilaterally ("No change to
strategy/risk/sizing/portfolio/execution logic").

**Runtime honesty note (Correction F):** the actual VPS runtime
environment-variable configuration (whether `EXCHANGE_MODE` is ever set,
and to what) remains `DEPLOYED_RUNTIME_UNKNOWN` — this audit, across all
three rounds, characterizes code behavior under hermetic test, never
deployed state.

**R1.1 addendum — BLOCKER A resolved, verdict unchanged:** §12 Cases 6-7
close the gap this round was opened to close: point 3 above is now proven
both with injected engine state (§11) and through the real
`ExecutionEngine.from_env()` construction path (§12 Case 6), and §12 Case 7
proves the honest contrast — with `LIVE_TRADING_CONFIRMED=false`,
`from_env()` never attaches a live exchange at all, so the mismatched
`LIVE_TRADING_CONFIRMED=false` + attached-exchange state R1's Case 1
originally implied never actually arises in production construction. This
strengthens, but does not change, the verdict below: `frozen order_size`,
the intentionally-pinned P10 `CapitalThrottle` (§6), `RealAccountsObserver`'s
display-only status (§7), and the absence of VPS runtime proof (§9) are all
unchanged and unaffected by this round's correction.

**VERDICT (unchanged): `REMEDIATION_REQUIRED`.**

---

## 14. O-02W-PRE-T1-D REMEDIATION (2026-09-11) — R2, closes this audit's `REMEDIATION_REQUIRED` verdict

**This section does not erase the historical audit above** — §1-§13 remain
the accurate record of what PR #134 found and proved, under the heading
`HISTORICAL_AUDIT_FINDING` throughout this section. This section records
what changed, under `REMEDIATED_IN_PRE_T1_D`, and what now holds, under
`CURRENT_INVARIANT`. Full design rationale:
`docs/adr/0018-scientific-capital-exchange-observation-separation.md`.
Branch: `claude/o02w-pre-t1-d-scientific-capital-separation`.

**Approved policy (verbatim, per mission brief):** *"Scientific/paper
portfolio capital is the sole input to scientific decision, risk and
sizing calculations. Real exchange balances are display-only during the
F-00 scientific phase and must not influence those calculations."*

### 14.1 Architectural change

`infra.wallet_sync.get_scientific_capital()` — a new, standalone module
function — is now the **sole** accessor for decision/sizing/risk capital.
It equals `WALLET_PAPER_CAPITAL + cumulative ledger PnL` (the formula
`WalletSync._base_capital()`/`get_balance()` already used in paper mode —
**unchanged**), makes **zero exchange calls**, and reads no singleton
state, no `EXCHANGE_MODE`, no `PAPER_TRADING_ENABLED`, no
`LIVE_TRADING_CONFIRMED`.

`WalletSync.observe_exchange_balance()` — a new method — is the **sole**
exchange-observation accessor. It returns an `ExchangeBalanceObservation`
(`status` ∈ `FRESH|ZERO|CACHED_FRESH|STALE_CACHE|ERROR|ABSENT`, `value`),
never a bare ambiguous float. `CACHED_FRESH` is a normal within-TTL cache
hit (no API call attempted this invocation); `STALE_CACHE` is reserved for
the case where a refresh WAS attempted (TTL expired, or `force_refresh=True`)
and failed, returning a previously-known value as fallback (R1 correction,
§14.4 below — the initial remediation's cache-hit branch collapsed these
two into `STALE_CACHE` for virtually every cache reuse). It is DISPLAY-ONLY
and is never called from any decisional path (proven structurally, §14.3
invariant 20).

`ExecutionEngine.fetch_available_capital()` — the historical decisional
entry point this audit's §3/§11/§12 characterized — is rewritten to call
`get_scientific_capital()` exclusively. It no longer references
`get_wallet_sync`, `wallet_mode`, `self._exchange`, or `self._mode`.

`core/advisor_loop.py`'s `order_size` (frozen at bootstrap per §5/H5) is
now recomputed every cycle immediately after the scientific-capital
refresh, using the same unchanged formula
(`min(max_order, scientific_capital * V9_MAX_POSITION_WEIGHT)`). The
decisional local variable in this flow was renamed from `real_capital` to
`scientific_capital` (R1 correction, §14.5 below) — naming only, formula
unchanged.

P10 `CapitalThrottle` (`capital_deployment/capital_throttle.py`, §6/H6) is
**unchanged** — still intentionally pinned to `WALLET_PAPER_CAPITAL` per
ADR-0011/ADR-0007; no alternative was needed to satisfy the separation
policy, since P10 was already reading a value structurally identical to
`get_scientific_capital()`'s formula.

`RealAccountsObserver`/`observability/real_accounts.py` (§7, `DISPLAY_ONLY`)
— **unchanged**, already structurally independent.

### 14.2 Defect-by-defect status

| # | Defect (§13 of the historical audit) | Status |
|---|---|---|
| 1 | Singleton mode frozen at first call | `REMEDIATED_IN_PRE_T1_D` — decisional path no longer reads singleton mode |
| 2 | Later mode requests silently ignored | `REMEDIATED_IN_PRE_T1_D` — decisional path no longer requests a mode |
| 3 | API balance can influence PAPER-labeled calculations | `REMEDIATED_IN_PRE_T1_D` — proven by `TestR2ScientificInvariance`/`TestR2DirectionalNonContamination` |
| 4 | Paper capital can influence LIVE/TESTNET-requesting calculations | `REMEDIATED_IN_PRE_T1_D` — no LIVE/TESTNET request reaches the decisional accessor at all now |
| 5 | Live/testnet API error can silently return `WALLET_PAPER_CAPITAL` as exchange evidence | `REMEDIATED_IN_PRE_T1_D` — `observe_exchange_balance()` returns `ERROR`, never a masked paper value |
| 6 | API zero and API failure collapse to the same numeric result | `REMEDIATED_IN_PRE_T1_D` — `ZERO` vs `ERROR` are distinct statuses |
| 7 | `_x`/`_last_value` co-seeded, previously mis-described | `CURRENT_INVARIANT` — classification already corrected in PR #134 (R1.2); untouched by this remediation, and now entirely outside the scientific-capital path regardless |
| 8 | `order_size` can remain frozen after capital changes | `REMEDIATED_IN_PRE_T1_D` — recomputed every cycle, §14.1 |
| 9 | Order-execution gating and capital provenance are independent guarantees | `CURRENT_INVARIANT` — confirmed unchanged, `TestR2ExecutionSafety` (invariants 16-19) |
| 10 | `RealAccountsObserver`/cockpit/Telegram are observational only | `CURRENT_INVARIANT` — confirmed unchanged, no modification required |

### 14.3 Regression proof

`tests/test_pre_t1_d_real_capital_boundary.py` — 94 tests total (the
original 64, with 9 rewritten where their expected result deliberately
demonstrated a now-fixed defect — marked `HISTORICAL_AUDIT_FINDING` /
`REMEDIATED_IN_PRE_T1_D` in their docstrings — plus 30 new tests across
`TestR2ScientificInvariance` (6), `TestR2DirectionalNonContamination` (4),
`TestR2FailureHonesty` (5), `TestR2ExecutionSafety` (4), and
`TestR2StructuralProof` (3), covering all 22 required invariants with
some parametrized). All 94 pass at the remediated HEAD. Before this
remediation (starting HEAD `2f226d09...`), the 9 rewritten tests failed as
expected (they asserted the pre-remediation leak/frozen-state behavior).
`quant_hedge_ai/agents/execution/test_execution_engine_futures.py`'s
`TestFetchAvailableCapital::test_paper_trading_disabled_uses_exchange_balance`
was likewise rewritten for the same reason (same historical-defect class,
outside the two mandated test files but a direct caller of the changed
function).

**RUNTIME_UNKNOWN (unchanged from the historical audit):** the actual VPS
`.env`/process runtime state remains unestablished by this remediation, as
by the original audit — this mission made no VPS changes and no
deployment (per the stabilization-window freeze).

### 14.4 R1 correction (post-review, 2026-09-11)

Two defects found in MASTER review of the initial remediation, fixed on top
of the same branch (no rebase, no history rewrite):

1. **Naming** — the decisional local in `core/advisor_loop.py` assigned
   from `exec_engine.fetch_available_capital()` (feeding `order_size`,
   `portfolio_brain.update_capital()`, `capital_engine.update_capital()`)
   was still named `real_capital`, misleadingly implying a real exchange
   balance post-remediation. Renamed to `scientific_capital` throughout the
   decisional flow of that file (formula unchanged). The one keyword
   argument at the `system.state_integrity` `_integrity_audit.run(...)`
   call site kept its `real_capital=` parameter name (owned by a different,
   out-of-scope module) — only the value passed changed to
   `scientific_capital`.
2. **Cache classification** — `observe_exchange_balance()`'s cache-hit
   branch (`STALE_CACHE if now - self._last_fetch_ts > 0 else FRESH`)
   collapsed virtually every within-TTL cache hit into `STALE_CACHE`, since
   time always advances. A new `CACHED_FRESH` status was added to
   `ExchangeObservationStatus`; the branch now returns `CACHED_FRESH`
   unconditionally for a normal within-TTL cache hit (no API call
   attempted), and `STALE_CACHE` is reserved for the failure-fallback case
   (refresh attempted because TTL expired or `force_refresh=True`, and
   failed). A genuine `ZERO` observation now also populates the cache
   (`_last_value`/`_last_fetch_ts`), same as `FRESH`, so a subsequent
   within-TTL call correctly returns `CACHED_FRESH(0.0)` instead of
   re-hitting the API every time.

**Regression proof:** `tests/test_pre_t1_d_real_capital_boundary.py` grew
from 94 to 139 tests (45 new, in `TestR1CacheStateClassification` and
`TestR1ObservationNeverAffectsScientificCapitalOrSizing`), using a
monkeypatched `time.time` (`_FakeClock`, no `sleep()`) to deterministically
reach and distinguish all 6 `ExchangeObservationStatus` states, confirm
exact fake-exchange call counts per state, and prove none of the 6 states
ever changes `get_scientific_capital()`'s return value or the derived
`order_size`. Fail-before/pass-after: 4 of the new tests fail against the
pre-R1 `infra/wallet_sync.py` (confirmed via `git stash` of that file
alone) and all 139 pass with the fix. Both fixes are naming/display-only —
no sizing formula, threshold, or decisional data changed.

### 14.5 Verdict

**VERDICT: `REMEDIATION_REQUIRED` (§13) is now CLOSED by this section.**
Defects #1-#6 and #8 are `REMEDIATED_IN_PRE_T1_D`; defects #7, #9, #10 were
already `CURRENT_INVARIANT`/acceptable design and remain so, unmodified.
This remediation does not authorize live trading or deployment — see
`docs/adr/0018-scientific-capital-exchange-observation-separation.md` §8.
