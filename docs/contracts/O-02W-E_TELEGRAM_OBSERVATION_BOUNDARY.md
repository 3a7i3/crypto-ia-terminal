# Telegram Observation Boundary & Safe Cutover Contract

Mission O-02W-E1 · Base SHA `17a2f70537ee48f70500974dddf5f0458c02cc50` ·
2026-09-10 · Documentation-only mission (no runtime code changes, no
Telegram sender/poller/token/chat/command changed, no VPS access, no
deployment, no cockpit controls added).

**R1 remediation (O-02W-E1-R1, same date):** independent MASTER review
found eight evidence-quality and safety-consistency defects in the
original text, corrected in place below (marked `[R1]` at each
correction site): (A) the "38 call sites" figure mixed production
source, archive, test, doc and config hits into one number, and
omitted 18 additional Telegram-capable production files from the
inventory — §6/§9 now carry a scoped count and a complete file
inventory (§17); (B) `supervision/kill_switch.py` was called
"unreachable... no import chain" when `supervision/__init__.py`
in fact imports the class at package-init time — §9/§13/Evidence
classes now distinguish "module importable" from "class instantiated
with a live token," neither of which this document previously stated
precisely; (C) the contradiction inventory omitted three `/RESUME`
instructions in `core/advisor_loop.py` that are equally
non-actionable as the already-flagged `/STOP_ALL` instruction, and the
closing claim that "no contradiction rises to a safety concern" is
removed — §13 now classifies all four as
`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`; (D) the dormant
`_set_param_live` mutator is now described precisely — wired into the
live bot's provider object, one hop from activation, not merely
"present somewhere"; (E) the blanket claim that no real-account data
feeds calculations is corrected — `ExecutionEngine.fetch_available_capital()`
and `real_capital` do feed sizing/risk/capital components, distinct
from the display-only observer path, requiring an explicit
architectural-boundary decision (§9a); (F) the identity matrix's
"mixed:" categories are split into single-category message-family
rows (§9a); (G) TG-07 (STANDBY↔LIVE push) is moved from an
automatic-cockpit-cutover path to `OPERATOR_DECISION_REQUIRED` because
field parity with a pull-only cockpit does not replace push delivery
(§9a, §11 Phase 3); (H) several wording overclaims are corrected
(§1, §8, §17). This remains documentation-only — no runtime source
was changed to make any of these corrections true; they only make the
document's existing claims evidence-honest. R1's starting HEAD is
`d702b7f2a06c59eb1972de3026afd317cf70d314`; only this file was
modified — `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`'s
existing pointer is untouched.

Final certification of this contract belongs exclusively to the
independent ChatGPT MASTER reviewer. This document is a proposal for
that review, not a self-certified conclusion.

---

## 0. Scope and non-goals

This contract governs the future relationship between the existing
Telegram bot ecosystem and the new read-only web cockpit
(`observability/operator_snapshot_builder.py`,
`observability/operator_api/app.py`, `frontend/src/App.tsx`), produced
by missions O-02W-C/D1/D2/D3 and merged in
[PR #129](https://github.com/3a7i3/crypto-ia-terminal/pull/129) at
`17a2f70537ee48f70500974dddf5f0458c02cc50`.

It is **not** a Telegram deletion mission, **not** a VPS audit, and
**not** the cockpit deployment mission. No Telegram sender, poller,
token, chat, command, or service was changed to produce this document.
The cockpit itself remains observation-only and this mission adds no
control surface to it (§8, §11).

### Evidence classes used throughout

| Class | Meaning |
|---|---|
| `SOURCE_PROVEN` | Verified directly against source at this commit (file:line cited). |
| `DOCUMENTED_BUT_NOT_SOURCE_PROVEN` | Asserted by an existing doc, not independently re-verified here. |
| `RUNTIME_UNKNOWN` | Code exists; whether it is currently running/deployed on the VPS cannot be determined without VPS access, which this mission does not have. |
| `MODULE_IMPORTABLE_NOT_INSTANTIATED` **[R1, new]** | The module/class is imported (directly or transitively, e.g. at package-init) by an active code path, but no active code path constructs the object with live credentials or calls its start/poll method. Importing a class has no runtime effect by itself unless the module has import-time side effects (checked case by case). This is distinct from, and strictly weaker evidence of aliveness than, `SOURCE_PROVEN` reachability — and distinct from, and strictly stronger than, full unreachability. |
| `DEAD_CODE_SOURCE_PROVEN` | Code exists and, after checking both the import graph *and* every instantiation/call site, no active code path constructs the object with live credentials or invokes its behavior. **[R1]** This class must not be used for a module that is merely uninstantiated if the module itself is still imported by an active path — use `MODULE_IMPORTABLE_NOT_INSTANTIATED` for that case instead, so "no active instantiation found" is never conflated with "unreachable source." |
| `OPERATOR_DECISION_REQUIRED` | A human judgment call this document cannot resolve on its own. |

Repository presence never proves deployment. A systemd unit file never
proves a service is currently running. An environment-variable name
never proves a token is configured. A sender function never proves a
message is currently delivered. No claim in this document asserts any
bot is live on the VPS — that would require VPS inspection, which is
out of scope for O-02W-E1. **[R1]** Nor does an import chain prove a
class is active — see `MODULE_IMPORTABLE_NOT_INSTANTIATED` above.

---

## 1. Reconciliation with existing documents

This contract builds directly on, and does not replace, the existing
Telegram documentation set. Their identity/bot inventories were
independently re-verified against source at the current commit
rather than trusted as-is. Findings:

- **`docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`** (2026-08-28) —
  the most complete and current single source. Every identity claim
  checked (IDENTITY-01 through IDENTITY-10) is still accurate at this
  commit. One drift: its absolute line-number citations for
  `core/advisor_loop.py`'s Real Account Bot / `_telegram_real` (cited
  as `796-797, 1009-1027, 3483, 3495, 3516, 7233`) have shifted — the
  code now lives at lines `965-974` (constants) and `1186-1205`
  (`_telegram_real`). The code moved; it did not disappear or change
  behavior. `DOCUMENTED_BUT_NOT_SOURCE_PROVEN` → now `SOURCE_PROVEN`
  at corrected line numbers, this document's §9.
- **`docs/architecture/TELEGRAM_BOT_REGISTRY.md`** (v2.0, 2026-08-28) —
  the 5 active bots it documents (CryptoRadar, Portfolio, Quant
  Observer, Rapport Automatique, Paper Arena) match current source
  exactly. Its own "Governance Gap" appendix already flagged the
  undocumented `REAL_ACCOUNT_BOT_TOKEN` merge; that merge is confirmed
  **complete** at this commit. **[R1, Correction H — precise wording]**
  The exact fact, re-verified: no live `os.getenv("REAL_ACCOUNT_BOT_TOKEN")`
  read exists anywhere in current source. The identifier itself still
  appears in two places as historical comment text, not as a live
  read: `core/advisor_loop.py:972` (`# REAL_ACCOUNT_BOT_TOKEN supprimé
  — même identité que MON_PORTFOLIO_BOT_TOKEN (merge 2026-08-28)`) and
  `.env.secrets.example:123` (`# REAL_ACCOUNT_BOT_TOKEN supprimé —
  fusionné avec MON_PORTFOLIO_BOT_TOKEN`), plus historical mentions in
  `docs/` and one captured audit-log JSON. The prior wording ("no
  reference remains anywhere in source") overstated this — the
  identifier is still present as inert commentary, which is exactly
  the intended audit trail, not a residual live read.
- **`docs/TELEGRAM_CONSTITUTION.md`** (v1.0, 2026-08-28) — Principle 5
  ("Telegram Cannot Silently Control the Machine") and Principle 3
  ("No Cross-Identity Token Fallback") both match current code exactly
  (`SOURCE_PROVEN`, §9a/§13 below).
- **`docs/TELEGRAM_BOT_CONSTITUTION.md`** (2026-08-28) — command lists
  for the 5 active bots match current code. Its Bot 6 (Sim Bot) section
  frames KEEP-and-deploy vs. REMOVE as an open decision; still open at
  this commit — no systemd unit or `.env.example` entry has been added
  for it since. Carried forward as `OPERATOR_DECISION_REQUIRED` (§9,
  Sim Bot row). **[R1]** This document's §2/§5 framing that the
  constitutional boundary "matches current code exactly" is qualified
  by Correction D (§9b) and Correction E (§9c) below: the *Telegram
  command surface itself* matches (no live control commands), but two
  separate architectural-boundary items — a dormant mutator wired into
  the live Portfolio-bot provider, and a real-account-capital feed
  into sizing/risk that is independent of Telegram/cockpit — mean the
  boundary should not be described as unqualified.
- **`docs/TELEGRAM_ARCHITECTURE_AUDIT.md`** — explicitly superseded on
  identity questions by `TELEGRAM_IDENTITY_REGISTRY.md` per its own
  header. One passage (describing a `RADAR_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`
  fallback as "currently present, ÉLEVÉ risk") is stale: current
  `scripts/radar_bot.py:21-22` has no such fallback. This staleness is
  already known and explained by `TELEGRAM_IDENTITY_REGISTRY.md`'s own
  before/after note, so it is not a new finding, only reconfirmed.
- **`docs/TELEGRAM_NOTIFICATION_AUDIT.md`** — its Real Account Bot
  governance-gap finding is now resolved by the same merge noted above.
- **`docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md`** — covers 8 of the
  10 historically-identified token groups; does not cover the (now
  merged/moot) Real Account identity or the (dead) Narrator identity.
  No correction needed, just a coverage note.
- **`docs/SYSTEM_DEGRADATION_POLICY.md`** §3.4 — its Telegram-alert
  rules (`CRITICAL → immediate alert`, `SAFE_MODE → critical alert +
  email`) map to the generic `TELEGRAM_BOT_TOKEN` push-only channel and
  are consistent with current code. No interactive/control claim is
  made there, so no contradiction.
- **`docs/GLOBAL_STATE_MACHINE.md`** — two passages need correction,
  flagged as findings from the original O-02W-E1 mission and carried
  forward here (§13, item 1).
- **`docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md`** — the
  direct predecessor contract. §16 (`SECURITY_READ_ONLY_CONTRACT`)
  already states the operator API must never trigger Telegram
  send/edit/delete. §21.2 explicitly names a future "O-02W-E" mission
  for "Telegram notification/retirement work" — this document is that
  mission's first deliverable (O-02W-E1). §12
  (`MARKET_API_CONTRACT`) establishes that CryptoRadar and the
  pre-existing `scripts/dashboard_api.py` are both constitutionally
  observational-only and never feed `analyze_symbol()` — the same
  non-feedback boundary this contract extends to the *display-only*
  real-account path (§9c, Flow 1), while separately documenting that a
  *different*, independent path (`ExecutionEngine.fetch_available_capital()`)
  does feed sizing (§9c, Flow 2) — the two must not be conflated.

No document reviewed makes a claim about current source that this
mission's independent re-verification found false, other than the
staleness items listed in §13 and the R1 corrections listed above.

---

## 2. Governing constitutional constraints (unchanged by this mission)

- **ADR-0007 (absolute observer passivity):** every component other
  than the decision engine — including every Telegram bot and the
  cockpit — may observe, record, explain, and recommend, but never
  influence a real-time trading decision. This contract does not
  change that; it only maps *which surface currently duplicates which
  observation*, and (per R1 Correction E, §9c) which capital-sizing
  inputs are independent of any Telegram/cockpit surface and therefore
  outside this contract's remit to redesign.
- **Scientific Debt Rule (architectural freeze):** this mission adds
  zero new indicators, strategies, decision rules, or threshold
  changes. It is a measurement/audit artifact, permitted under the
  current phase.
- **Stabilization Lab window** (`2026-09-02` → `2026-09-16`,
  `docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`):
  this mission proposes no VPS deployment or restart and does not
  affect burn-in certification status.

---

## 3. Required message classification (definitions)

Every Telegram message family in §9a is classified into **exactly
one** of the following — no `mixed:` composite labels are used
anywhere in this document after R1 (Correction F; see §9a for the
per-family split that replaces the original identity matrix's
composite cells):

- `CRITICAL_SAFETY_ALERT` — reports a real safety-relevant state
  transition (exchange down/up, session halt, crash, degradation).
- `STATE_CHANGE_ALERT` — reports a real mode/phase/config transition
  that is not itself a safety emergency (STANDBY↔LIVE, probation).
- `PERIODIC_STATUS_SUMMARY` — scheduled recurring report, no
  transition implied (heartbeat, daily/periodic summary).
- `RESEARCH_EXPERIMENT_REPORT` — reports simulation/backtest/paper
  results, not live account state.
- `ON_DEMAND_READ_ONLY_QUERY` — served only in response to an
  operator-issued command, never pushed unsolicited.
- `ROUTINE_TELEMETRY_DUPLICATED_BY_COCKPIT` — status data now also
  computable from the cockpit's read-only snapshot.
- `FORBIDDEN_CONTROL_SURFACE` — a command that would mutate trading,
  execution, configuration, or service state.
- `DEAD_OR_UNREACHABLE_CODE` — implemented but, after checking both
  import graph and instantiation sites, not reachable from any active
  entrypoint at this commit.
- `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` **[R1, new]** — a
  message instructs the operator to use a control mechanism (a
  Telegram command) that does not currently exist as a live handler.
  Not proof of an active control surface, but capable of misleading an
  operator during a degraded or halted state into believing a
  non-functional recovery path is available. See §13.
- `UNCLASSIFIED_REQUIRES_DECISION` — evidence insufficient for the
  above; an operator call is needed.

## 4. Required cutover classification (definitions)

- `KEEP_PERMANENT_CRITICAL_ALERT`
- `KEEP_RESEARCH_INTERFACE`
- `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`
- `RETIRE_AFTER_CERTIFIED_CUTOVER`
- `DEAD_CODE_REMOVAL_CANDIDATE`
- `OPERATOR_DECISION_REQUIRED`
- `FORBIDDEN_MUST_NEVER_REACTIVATE`

Per the mission mandate: duplication by cockpit *source code* alone
never justifies `RETIRE_AFTER_CERTIFIED_CUTOVER` today — the cockpit is
not yet deployed or runtime-certified (§7, Phase 0). That transition
state is reserved for flows that will become eligible **once** the
Phase 3 criteria in §11 are met; nothing is retired by this document.

**[R1, Correction G]** Field parity with a pull-only cockpit is
insufficient by itself to retire a flow that carries unique **push**
delivery value. A flow with confirmed unique push/notification value
is not retirement-eligible in Phase 3 unless either (a) the operator
explicitly accepts losing push delivery for that flow, or (b) a
separately certified notification replacement (e.g. a push-capable
cockpit alerting channel) exists and is itself runtime-certified. See
§9a and §11 Phase 3 for the concrete application to TG-07.

---

## 5. Protected decisions (restated, unchanged)

- **CryptoRadar** (`scripts/radar_bot.py`, `@RadarCrypto1_bot`): not
  modified by this mission, and not proposed for automatic retirement
  merely because the cockpit exists. Its unique on-demand
  market-scanning value (`/scan /top50 /longs /shorts /symbol /lmi`)
  is classified separately from any cockpit-duplicated status
  telemetry in §9/§10 — it carries no overlap with the cockpit's
  portfolio/decision/system domains and is classified
  `KEEP_RESEARCH_INTERFACE`.
- **Cockpit**: remains observation-only. This document proposes no
  buttons, controls, parameter changes, start/stop/restart actions,
  order controls, or Telegram control proxy of any kind. Confirmed by
  source inspection (§8): `observability/operator_api/app.py` exposes
  only `GET` routes (`/healthz`, `/api/operator/v1/snapshot`,
  `/portfolio`, `/decision-pipeline`, `/system-health`) — zero
  `@app.post/@app.put/@app.delete` anywhere under
  `observability/operator_api/`.
- **Real portfolio observations**: read-only real-account values may
  be displayed by both cockpit and Telegram, and remain observational
  only per ADR-0007 for the *display* path — never feeding signals,
  indicators, strategies, risk decisions, or execution authorization
  through the cockpit or Telegram surfaces themselves. **[R1,
  Correction E — critical qualification]** This is narrower than the
  original wording ("never feeding... paper-equity calculations"; "no
  source evidence found of any violation"). Source evidence *does*
  show a **separate, independent** path — not mediated by Telegram or
  the cockpit — where exchange-account capital feeds sizing and risk
  components directly: `ExecutionEngine.fetch_available_capital()`
  (`quant_hedge_ai/agents/execution/execution_engine.py:229-249`)
  returns `real_capital`, which `core/advisor_loop.py` then feeds into
  `order_size` (line 4009), `PortfolioBrain` (line 4504),
  `CapitalAllocationEngine` (line 4510), `ExecutiveOverride` (line
  7191), and risk-throttle/drawdown computations (lines 4865, 5036,
  5044, 5224, 5842). This is a pre-existing architectural design (the
  live-trading capital feed), not something this mission's cockpit or
  Telegram work created or could disable, and it is not a Telegram or
  cockpit control-surface violation — but the original contract's
  blanket claim of non-use was inaccurate. See §9c for the full
  two-flow analysis this document now requires.

---

## 6. Consistency search results (summary)

Full repository greps were run for every literal listed in the O-02W-E1
mandate (`api.telegram.org`, `sendMessage`, `sendPhoto`, `editMessage`,
`getUpdates`, `deleteWebhook`, `_BOT_TOKEN`, `_CHAT_ID`,
`TELEGRAM_BOT_TOKEN`, `MON_PORTFOLIO_BOT_TOKEN`, `QUANT_CRYPTO_BOT_TOKEN`,
`TELEMETRIE_IA_BOT_TOKEN`, `RADAR_BOT_TOKEN`, `KILLSWITCH`, `/resume`,
`/kill`, `/restart`, `/set`, `/pause`, `/STOP_ALL`, `/CLOSE_ALL`,
`/SAFE_MODE`), re-run for R1 with archive/test/doc/config buckets kept
separate (Correction A). Every hit was reviewed in context (not
classified by grep count alone). Headline findings:

- **[R1, corrected]** `api.telegram.org` literal occurrences,
  scope-separated: **42 total repo-wide**, of which **4** are in
  `_ARCHIVE_2026/` (legacy/superseded code, out of scope), **5** are in
  `tests/`, **2** are in `docs/` (including this contract itself),
  **1** is in a config file (`config/telegram_config.json`), leaving
  **30** literal `https://api.telegram.org/...` occurrences in actual
  non-archive, non-test `.py`/`.sh` production source. **Only this last
  figure of 30 may be called production "call sites,"** and even then,
  a raw URL-string literal is not itself proof of an active,
  reachable, or deployed sender — see §17 for the per-file
  reachability/runtime-evidence breakdown Correction A requires. The
  original contract's "38 call sites across all identities" figure
  mixed these buckets and undercounted the production-source file
  list; it is superseded by §17.
- **[R1, scope-qualified, otherwise reconfirmed]** `getUpdates`
  (polling), restricted to non-archive, non-test `.py` files that
  actually call it: **exactly 5** — `scripts/radar_bot.py`,
  `capital_deployment/command_center_bot.py`,
  `src/telegram/quant_observer/bot.py`, `src/telegram/bot_runner.py`
  (Sim Bot), and `supervision/kill_switch.py`. This specific,
  scope-qualified claim is re-confirmed accurate. It is **not** true of
  the raw repo-wide count, which is 76 (51 in `docs/`, 4 in archive, 3
  in tests, 4 in config/env files) — the original text's unscoped
  phrasing ("`getUpdates` occurs... in exactly 5 files") is corrected
  here to state the scope explicitly, since "exactly 5" is false
  without it.
- `deleteWebhook` appears only in `src/telegram/bot_runner.py`
  (409-conflict recovery) — irrelevant to any other identity.
- `sendPhoto`/`editMessage` are concentrated almost entirely in
  `src/telegram/quant_observer/bot.py` (pinned-panel live refresh) —
  no other bot edits or sends photos.
- `/STOP_ALL`, `/CLOSE_ALL`, `/SAFE_MODE` occur only inside: (a) the
  `supervision/kill_switch.py` implementation (reachability corrected
  in §9, Correction B — the module is package-init-importable but
  never instantiated with a live token, see below), (b) docstrings in
  `supervision/killswitch_hardened.py` stating these commands were
  "retirées" (removed), (c) one operator-facing email string in
  `supervision/exchange_monitor.py:252-257` instructing the operator
  to "send `/STOP_ALL` on Telegram" — classified
  `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` (§13), (d) tests
  asserting these are now rejected.
- **[R1, new]** `/RESUME` (case-insensitive) occurs in
  `core/advisor_loop.py` at four sites, three of them **operator-facing
  message strings**, not merely code identifiers: line 3870
  ("Envoyez /RESUME si intervention requise" — degraded-mode alert),
  line 3878 ("Envoyez /RESUME pour reprendre" — halted-mode alert),
  and line 5576 ("Boucle suspendue par Kill Switch. Envoyer /RESUME
  pour reprendre" — the halted-loop wait message). All three are
  classified `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` alongside the
  `/STOP_ALL` instruction above — see §13 for the full analysis. The
  fourth site (line 3562, inside the `_on_resume()` callback's log
  line) is a code comment/log string, not an operator-facing
  instruction.
- `/resume`, `/kill`, `/restart`, `/set`, `/pause` hits outside
  Telegram code are unrelated non-Telegram Python syntax
  (`config/settings.py`, `risk/circuit_breaker.py`) or
  `capital_deployment/command_center_bot.py`'s explicit blocked-command
  set, which returns a fixed refusal string and never calls
  `CommandDataProvider.set_param` or any mutator (§9b, Correction D).
- No `.py` file outside `supervision/kill_switch.py` implements a live
  dispatcher for any of the eight command-mutation literals against a
  real token. **[R1]** `supervision/kill_switch.py`'s own reachability
  is corrected in §9 (Correction B): its module is imported at
  `supervision/__init__.py:11-13` (package-init time, executed by any
  `import supervision.*`), but no active code path in non-archive,
  non-test source instantiates the class with a live token — the two
  hits for `TelegramKillSwitch(` outside the archive are the class's
  own docstring example (`kill_switch.py:12`) and
  `core/advisor_loop.py:3578`, which constructs the *aliased*
  `runtime.TelegramKillSwitch` name bound to `KillSwitchHardened` (via
  `core/advisor_runtime_adapters.py:109`) — a different class with zero
  Telegram code, not this one.
- No `KILLSWITCH_BOT_TOKEN` / `KILLSWITCH_CHAT_ID` environment variable
  is read anywhere in source — the `KILLSWITCH` grep hits are entirely
  prose/class-name occurrences in docs and code comments.

---

## 7. Cockpit deployment status (current)

- **Cockpit deployment: not performed.** No systemd unit, deploy
  script invocation, or VPS reference for
  `observability/operator_api` or `frontend/` was found in this
  mission's source-only review. `RUNTIME_UNKNOWN` in the strict sense
  (VPS inspection is out of scope), but no `SOURCE_PROVEN` evidence of
  deployment exists either — consistent with O-02W-D3 having only
  landed a cross-stack **compatibility gate**, not a deployment.
- **T-1 (deployment mission): not started.** No branch, workflow run
  reference, or deployment artifact found.
- **F-00: not started.** No related branch or document found in this
  review.
- Both confirmed per the mission's mandatory preflight.

---

## 8. Cockpit read-only surface (for §10 overlap comparison)

`observability/operator_api/app.py` exposes exactly these routes, all
`GET`:

| Route | Domain(s) served |
|---|---|
| `GET /healthz` | liveness of the API process itself |
| `GET /api/operator/v1/snapshot` | full composite snapshot (all domains) |
| `GET /api/operator/v1/portfolio` | portfolio domain |
| `GET /api/operator/v1/decision-pipeline` | decision domain |
| `GET /api/operator/v1/system-health` | system domain |

`observability/operator_snapshot_builder.py` composes these via
`_build_portfolio_domain`, `_build_decision_domain`,
`_build_system_health_domain`, each carrying explicit
`domain_available` / `FreshnessStatus` / `UNKNOWN` fields — a
fail-closed design that never silently presents stale or unavailable
data as current.

`frontend/src/App.tsx` renders six tabs from a single
`useOperatorSnapshot()` hook: `overview, portfolio, decisions, system,
market, scores`. **[R1, Correction H — strengthened from "untraced" to
confirmed]** `App.tsx:14` declares the `Tab` type including `"market"`
and `"scores"`; `App.tsx:101-102` renders `{tab === "market" &&
<NotExposedView title="Market" />}` and `{tab === "scores" &&
<NotExposedView title="Scores" />}`, importing `NotExposedView` from
`./views/NotExposedView` (`App.tsx:12`). These two tabs are confirmed
**`SOURCE_PROVEN` literal placeholder stubs** — they render a generic
"not exposed" component with only a title prop, not any live-fetched
or computed data, and are `NOT_EXPOSED` by explicit source design, not
merely undertraced. This contract's §10 overlap matrix accordingly
restricts itself to the domains actually served by data:
**portfolio, decisions, system**, plus **overview** as the composite
view of `snapshot`.

No `@app.post`, `@app.put`, or `@app.delete` exists anywhere under
`observability/operator_api/` — confirmed read-only by construction,
matching §16 of the O-02W-B contract.

---

## 9. Identity matrix

Line numbers below are re-verified at commit
`d702b7f2a06c59eb1972de3026afd317cf70d314` (R1 starting HEAD; not
copied from older docs without re-check). **[R1]** This table retains
identity-level fields (token, entrypoint, process owner); every
message-family-level classification that was previously a `mixed:`
composite cell is now split out in §9a (Correction F) — read the two
tables together.

| Identity ID | Human/bot name | Token var | Chat var | Entrypoint | Process owner | Interaction model | Domain | Cockpit overlap | Runtime evidence | Cutover prerequisite | Later mission |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TG-01 | CryptoRadar (`@RadarCrypto1_bot`) | `RADAR_BOT_TOKEN` | `RADAR_CHAT_ID` | `scripts/radar_bot.py` | `crypto-radar-bot.service` (independent) | BOTH (poll `getUpdates` + push) | MARKET | NONE | SOURCE_PROVEN (code); RUNTIME_UNKNOWN (VPS) | n/a — protected, §5 | none |
| TG-02 | Portfolio / CommandCenter (`@mon_portfolio_bot`) | `MON_PORTFOLIO_BOT_TOKEN` | `MON_PORTFOLIO_CHAT_ID` (falls back to `TELEGRAM_CHAT_ID`) | `capital_deployment/command_center_bot.py`, instantiated by `core/advisor_loop.py:3991-3992` | `crypto-advisor.service` (in-process) | BOTH | PORTFOLIO | PARTIAL (see §9a for per-family split) | SOURCE_PROVEN | see §9a rows TG-02a/b/c | T-1 + Phase 2 / E2 |
| TG-03 | Quant Observer (`@QuantCrpto_bot`) | `QUANT_CRYPTO_BOT_TOKEN` | `QUANT_CRYPTO_CHAT_ID` | `src/telegram/quant_observer/bot.py` | `crypto-quant-observer.service` (independent) | BOTH | DECISION (research) | PARTIAL (see §9a) | SOURCE_PROVEN | see §9a rows TG-03a/b | T-1 + Phase 2 / E2 |
| TG-04 | Rapport Automatique / Intel | `RAPPORT_AUTOMATIQUE_BOT_TOKEN` | `RAPPORT_AUTOMATIQUE_CHAT_ID` | `core/advisor_loop.py::_send_intel` (1208-1232) | `crypto-advisor.service` (in-process) | PUSH_ONLY | SYSTEM (AI-generated periodic briefing) | UNKNOWN — narrative content, no field-level comparison performed | SOURCE_PROVEN | operator must decide whether narrative-briefing value is replaced by cockpit or is unique | operator decision / E2 |
| TG-05 | Paper Arena | `PAPER_ARENA_BOT_TOKEN` | `PAPER_ARENA_CHAT_ID` | `src/paper/paper_runner.py`, `src/paper/paper_report.py` | `paper-arena.service` (independent) | PUSH_ONLY | EXPERIMENT | NONE | SOURCE_PROVEN | n/a | none |
| TG-06 | Generic / Engine Alerts | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BEHAVIOR_CHAT_ID` | same | `core/advisor_loop.py` (`_telegram`, `_telegram_behavior`), `scripts/telegram_alerts.py`, `supervision/performance_watchdog.py`, `supervision/exchange_monitor.py`, `watchdog_vps.py` (root — see §17 re: the unrelated `infra/monitoring/watchdog_vps.py` duplicate) | `crypto-advisor.service` + independent scripts | PUSH_ONLY | SYSTEM | PARTIAL (see §9a for per-family split) | SOURCE_PROVEN | see §9a rows TG-06a/b/c/d | operator decision (message-family split) / E2 |
| TG-07 | Real Account Bot (merged into TG-02's token) | — (uses `MON_PORTFOLIO_BOT_TOKEN`/`_CHAT_ID`) | same as TG-02 | `core/advisor_loop.py::_telegram_real` (1186-1205) | `crypto-advisor.service` (in-process) | PUSH_ONLY (shares TG-02's token; TG-02 remains the sole poller for that token) | PORTFOLIO (real-account sub-channel) | PARTIAL — see §9a | SOURCE_PROVEN (merge complete: no live `os.getenv("REAL_ACCOUNT_BOT_TOKEN")` read remains; historical comment identifier persists, §1) | **[R1, Correction G]** `OPERATOR_DECISION_REQUIRED` — was `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`; corrected because this is a unique push notification with no cockpit-side push equivalent (cockpit is pull-only, §8); field parity alone cannot retire it — see §11 Phase 3 | operator decision / E2 |
| TG-08 | CMVK / Sim Bot | `TELEMETRIE_IA_BOT_TOKEN` | `TELEMETRIE_IA_CHAT_ID` | `src/telegram/bot_runner.py`, `src/telegram/sim_bot.py` | none — no systemd unit references this file; not called from `advisor_loop.py` or `paper_runner.py`; not in `.env.example` | BOTH (code fully implements polling+push if run manually) | EXPERIMENT (simulation/backtest inspection) | NONE | RUNTIME_UNKNOWN — code SOURCE_PROVEN, but no deployment entrypoint exists at this commit | operator must decide deploy-or-remove; `docs/TELEGRAM_BOT_CONSTITUTION.md` Bot 6 section frames the same open question | operator decision |
| TG-09 | KillSwitch (legacy `supervision/kill_switch.py::TelegramKillSwitch`) | `KILLSWITCH_BOT_TOKEN`/`_CHAT_ID` — name only, **never read via `os.getenv` anywhere in source** | same | `supervision/kill_switch.py` | none instantiates it live | **[R1, Correction B — evidence class corrected]** `MODULE_IMPORTABLE_NOT_INSTANTIATED`, not `DEAD_CODE_SOURCE_PROVEN`. `supervision/__init__.py:11-13` imports `TelegramKillSwitch` from this module at package-init time (`from supervision.kill_switch import (TelegramKillSwitch,)`), so any `import supervision` or `import supervision.<anything>` executes this module's top-level code. That top-level code (read in full) contains only an `Enum` and a class definition with no import-time side effects — so importing it has no runtime behavior by itself. Separately, the class itself is never **instantiated** with a live token: the only two `TelegramKillSwitch(` hits outside archive are the class's own docstring example and `core/advisor_loop.py:3578`, which constructs the *aliased* `KillSwitchHardened` under the same name (via `core/advisor_runtime_adapters.py:109`) — a distinct class with zero Telegram code. Net: source present, transitively imported, **no active production instantiation found**, runtime status on the VPS unknown without VPS evidence. | `FORBIDDEN_MUST_NEVER_REACTIVATE` (unchanged) | none — must never be wired to a real token; ADR-0007 forbids any observer-layer component from holding execution authority | none (constitutional prohibition, not a retirement candidate) |
| TG-10 | Narrator | `NARRATOR_BOT_TOKEN`/`_CHAT_ID` — commented out, `.env.secrets.example:92-93` only | same | none — no module exists | none | NONE | n/a | n/a | DEAD_CODE_SOURCE_PROVEN (no module exists at all — this class of dead code is unambiguous, unlike TG-09) | `DEAD_CODE_REMOVAL_CANDIDATE` — nothing to remove beyond two commented-out env lines; cosmetic, out of this mission's scope | dead-code hygiene (non-urgent, E2 or later) |
| TG-11 | Internal-only kill switch (`supervision/telegram_kill_switch.py`, name-collides with TG-09's class name but is a distinct, separate implementation) | none — docstring states Telegram polling was removed | none | `supervision/telegram_kill_switch.py` | referenced only by two `tests/phase0/` files and `tools/runtime_tracer.py`; **not imported by `core/advisor_loop.py`**, and not imported by `supervision/__init__.py` either (checked — that file imports only `kill_switch` and `killswitch_hardened`, not `telegram_kill_switch`) | NONE (zero Telegram code; only a programmatic `force_halt()/force_resume()` API) | n/a | n/a | SOURCE_PROVEN (fully unreachable from `supervision/__init__.py` or `core/advisor_loop.py` — unlike TG-09, this one has no package-init import path either) | `DEAD_CODE_REMOVAL_CANDIDATE` — appears superseded by `supervision/killswitch_hardened.py` | operator decision (low priority) |

**Total identities: 7 active-in-source token groups (TG-01 through
TG-06, TG-08) + 1 merged (TG-07 → TG-02's token) + 2 confirmed
dead-code-only (TG-09, TG-10, with TG-09's evidence class corrected
per Correction B) + 1 non-Telegram internal component sharing a class
name (TG-11) = 11 rows.**

**[R1, corrected]** Total production-source Telegram call sites: see
§6 and §17 — **30** literal `api.telegram.org` occurrences in
non-archive, non-test `.py`/`.sh` files, spread across the files listed
in §17 (a materially larger and more precisely scoped file set than
the original contract's flat "38" figure, which mixed archive/test/doc
hits into production-source counting). `getUpdates` (polling), scoped
to non-archive/non-test `.py` files, exists in exactly 5 (TG-01, TG-02,
TG-03, TG-08, and TG-09 — TG-09's module is importable but its class is
never instantiated live, per Correction B above).

---

## 9a. Message-family table (Correction F — one category per row)

**[R1, new]** Every row below carries exactly one identity, one
concrete message family, one message category, one overlap
classification, one transition state, and one later owner/mission —
replacing the original identity matrix's `mixed:` composite cells for
TG-02, TG-03, and TG-06.

| Row | Identity | Message family | Message category | Cockpit overlap | Transition state | Later owner/mission |
|---|---|---|---|---|---|---|
| TG-02a | TG-02 | On-demand read commands (`/status /kpis /phase /regime /risk /health /balance /positions /pnl /trades /config /get /logs /help /eo /gate /perf /certif /charts /blackbox /history /recap`, `command_center_bot.py` handler dict + arg-commands, lines 1295-1367) | `ON_DEMAND_READ_ONLY_QUERY` | PARTIAL (status/positions/pnl fields likely overlap cockpit `portfolio` domain; query semantics — ask-and-receive — have no cockpit equivalent) | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` | T-1 + Phase 2 / E2 |
| TG-02b | TG-02 | Periodic auto-report (`_report_loop`, `command_center_bot.py:1390-1400`, interval `P10_PORTFOLIO_REPORT_H`, default 1h) | `PERIODIC_STATUS_SUMMARY` | PARTIAL (report content likely overlaps `portfolio` domain fields; the *push* delivery itself has no cockpit equivalent, cockpit is pull-only) | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` (per Correction G, only for the field-content portion; the push-delivery value itself needs the same operator sign-off as TG-06's periodic subset, §11 Phase 3) | T-1 + Phase 2 / E2 |
| TG-02c | TG-02 | Blocked control commands (`/pause /resume /set /setphase /maxorder /reset /restart /confirm /cancel`, `command_center_bot.py:1370-1379`, fixed refusal string, never calls `CommandDataProvider.set_param`) | `FORBIDDEN_CONTROL_SURFACE` | NONE (inert — no cockpit equivalent is needed for a command that has no live effect) | `FORBIDDEN_MUST_NEVER_REACTIVATE` (remains forbidden even though currently inert — see §9b for the dormant mutator this refusal currently blocks) | none |
| TG-03a | TG-03 | On-demand commands (`/snapshot /health /pipeline`, `bot.py:714-716`) | `ON_DEMAND_READ_ONLY_QUERY` | PARTIAL (pipeline/health concepts likely overlap `decisions`/`system` domains) | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` | T-1 + Phase 2 / E2 |
| TG-03b | TG-03 | Pinned-panel change-driven live refresh (`_change_driven_live_tick`/`_pinned_tick`, `bot.py:630-708`, minimum interval `QC_SAFETY_REFRESH_S`=1800s or `PINNED_UPDATE_S`=600s) | `PERIODIC_STATUS_SUMMARY` | PARTIAL for content; the edit-in-place pinned-message UX and any `sendPhoto` chart delivery have no cockpit equivalent (cockpit requires an active pull, never edits a persistent view for the operator) | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`, subject to the same push-value caveat as TG-02b (§11 Phase 3) | T-1 + Phase 2 / E2 |
| TG-06a | TG-06 | Exchange down/up (`supervision/exchange_monitor.py:207,229-234`), session halt/resume (`core/advisor_loop.py:3878,5576,5583`), crash alerts | `CRITICAL_SAFETY_ALERT` | PARTIAL for status content; push delivery itself has no cockpit equivalent | `KEEP_PERMANENT_CRITICAL_ALERT` | none — never retired |
| TG-06b | TG-06 | Degraded-mode state notice (`core/advisor_loop.py:3870`, "Mode DEGRADED — exchange instable... Trading continue") | `STATE_CHANGE_ALERT` | PARTIAL | `KEEP_PERMANENT_CRITICAL_ALERT` (degraded-state transitions are safety-adjacent — treated conservatively as permanent given the drift noted in §13) | none — never retired |
| TG-06c | TG-06 | Heartbeat / periodic-style reports (`core/advisor_loop.py:8162,7669`) | `PERIODIC_STATUS_SUMMARY` | PARTIAL (likely field overlap with cockpit `overview`/`system`) | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` | T-1 + Phase 2 / E2 |
| TG-06d | TG-06 | Component-slow / self-heal escalation notices below the CRITICAL mail-escalation tier (`supervision/performance_watchdog.py:249-261`) | `ROUTINE_TELEMETRY_DUPLICATED_BY_COCKPIT` (candidate, pending Phase 2 confirmation) | PARTIAL | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` | T-1 + Phase 2 / E2 |
| TG-07 | TG-07 | STANDBY↔LIVE transition push (`core/advisor_loop.py:1186-1205`, triggered by `PAPER_TRADING_ENABLED`) | `STATE_CHANGE_ALERT` | PARTIAL — cockpit portfolio domain field coverage for this specific transition not independently confirmed | `OPERATOR_DECISION_REQUIRED` (Correction G — see §9, §11 Phase 3) | operator decision / E2 |

No row above is asserted as `FULL` cockpit-field equivalence. The
strongest claim made anywhere is `PARTIAL`, pending the Phase 2
side-by-side comparison defined in §11.

---

## 9b. Dormant Portfolio mutator capability (Correction D)

**[R1, new section]** `core/advisor_loop.py:3903-3908` defines:

```python
def _set_param_live(name: str, value: str) -> bool:
    os.environ[name] = value
    if name == "EXEC_MAX_ORDER_USD":
        nonlocal max_order
        max_order = float(value)
    return True
```

This function mutates `os.environ` unconditionally and additionally
mutates the local `max_order` closure variable for one parameter name.
It is passed at `core/advisor_loop.py:3989` as `set_param=_set_param_live`
into the `CommandDataProvider` construction (`_pb_provider`, lines
3973-3990) that is then handed to the **live** `CommandCenterBot`
instance (`advisor_loop.py:3991-3992`, `_portfolio_bot =
CommandCenterBot.from_env(_pb_provider); _portfolio_bot.start()`).

`capital_deployment/command_center_bot.py`'s `CommandDataProvider`
declares the `set_param` field at line 212, but a repo-wide search
confirms it is **never read or invoked** anywhere in
`command_center_bot.py` — `_route()` (lines 1284-1386) dispatches only
read-only handlers plus the explicit blocked-command branch (§9a,
row TG-02c) that returns a fixed refusal string.

**Evidence-honest classification:** no active Telegram mutation
handler exists today — `_route()` never reaches `set_param`. But this
is not merely "a mutator that exists somewhere in the codebase"; it is
a fully-implemented, environment-mutating capability **already wired
into the provider object the live Command Center bot instance holds**.
Activating it would require adding exactly one new branch to
`_route()`'s dispatch — a materially smaller and more dangerous gap
than if `_set_param_live` were unwired or the provider had no
`set_param` field at all. This is architectural boundary debt, not
evidence that Telegram currently controls the machine. Its removal or
neutralization (e.g., removing the `set_param` wiring at line 3989, or
deleting `_set_param_live` entirely if `EXEC_MAX_ORDER_USD` live-tuning
is not wanted via any path) requires a later source mission, before
T-1 deployment/runtime certification — not this documentation-only PR.

---

## 9c. Real-account data boundary — two independent flows (Correction E)

**[R1, new section, replaces the blanket claim removed from the
original §5]**

**Flow 1 — display-only, no feedback (Telegram/cockpit presentation):**
`RealAccountsObserver`/snapshot/API/cockpit/Telegram presentation
outputs are read-only. No source evidence was found of a feedback path
from these display surfaces into `analyze_symbol()`, `PortfolioBrain`,
sizing, or risk decisions. `observability/real_accounts.py:235`'s own
comment states the sizing source is `real_capital` /
`WALLET_PAPER_CAPITAL` — i.e., this observer module is explicitly *not*
the sizing input; it is a separate, parallel display path. This flow
is correctly described by the original contract's framing and requires
no correction.

**Flow 2 — real capital feeding sizing/risk (independent of Telegram
and the cockpit):** `ExecutionEngine.fetch_available_capital()`
(`quant_hedge_ai/agents/execution/execution_engine.py:229-249`)
returns the operative capital figure. Mode selection uses two
independent env-var gates:

1. `PAPER_TRADING_ENABLED` (default `"true"`, checked inside
   `fetch_available_capital()` itself, lines 196-201) — selects
   `wallet_mode = "paper"` (local ledger: `WALLET_PAPER_CAPITAL` +
   cumulative PnL from `databases/paper_trades.jsonl`) vs. the
   constructor-selected live/testnet mode.
2. `LIVE_TRADING_CONFIRMED` (default `"false"`, checked in
   `ExecutionEngine.from_env()`, lines 182-201) — live mode requires
   **all three** of API keys present, exchange-factory mode not
   `"paper"`, and this flag explicitly `true`.

The returned value, assigned to `real_capital` in `core/advisor_loop.py`
(initial fetch line 3796, refreshed in the main loop lines 5690-5694),
feeds: `order_size` sizing (line 4009), `PortfolioBrain.total_capital`
(line 4504), `CapitalAllocationEngine.total_capital` (line 4510),
`ExecutiveOverride.update(capital_current=...)` (line 7191), the
capital throttle (line 5842), the dynamic-exposure module (line 5224),
and drawdown-ratio computations (lines 4865, 5036, 5044).

**`capital_deployment/command_center_bot.py:181-183`'s own provenance
comment already documents exactly this ambiguity precisely** and is
quoted here as the authoritative in-source articulation:

> Provenance de `get_balances` — MASTER O-02B-R1 (D-7) :
> `ExecutionEngine.fetch_available_capital()` est mode-dépendant
> (`PAPER_TRADING_ENABLED=true` → WalletSync paper, sinon solde
> exchange réel/testnet selon `detect_mode()`). Le nom `"real_capital"`
> côté advisor_loop **n'est PAS une preuve de provenance** — la
> présentation doit refléter le mode effectif, jamais le deviner.
> Domaine fini : `"PAPER" | "REAL_API" | "TESTNET_API" | "UNKNOWN"`.
> Absent ou valeur non reconnue → `UNKNOWN` (fail closed, jamais
> `REAL_API` par défaut).

**Required corrections to prior framing:**

- Do not claim global non-use of exchange-account data. The prior
  contract's blanket assertion ("never feeding... paper-equity
  calculations... no source evidence found of any violation") was
  inaccurate for Flow 2 and is removed from §5.
- **Operator policy recorded here:** account observations intended
  solely for display (Flow 1: `RealAccountsObserver`, cockpit
  `portfolio` domain rendering, TG-07's STANDBY/LIVE push content)
  must never be reused as decision/signal/strategy inputs. This policy
  is already satisfied by current source for Flow 1 — there is no
  evidence Flow 1 and Flow 2 share a code path — but the two must be
  kept architecturally distinct going forward.
- Flow 2's existing shared-capital behavior (`fetch_available_capital()`
  feeding sizing/risk) is a **separate, pre-existing architectural
  design** (the live/testnet capital-fetch mechanism), not created or
  modified by O-02W-E1/R1, and not something this documentation-only
  PR redesigns or modifies. It is classified here as requiring an
  explicit **MASTER/operator decision** on whether its current
  behavior (mode-gated by `PAPER_TRADING_ENABLED`/
  `LIVE_TRADING_CONFIRMED`, fail-closed to `UNKNOWN` per the provenance
  comment above) is acceptable as-is or needs a dedicated boundary
  hardening mission.
- **PAPER vs. LIVE/TESTNET distinguished:** PAPER-mode capital is a
  local ledger figure (`WALLET_PAPER_CAPITAL` + session PnL,
  independent of any exchange account). LIVE/TESTNET-mode capital is
  an exchange-fetched balance via `WalletSync`, gated by
  `LIVE_TRADING_CONFIRMED=true` (constitutionally required `false` by
  default per this repository's `CLAUDE.md` ADR-0007 section).
- **The cockpit and Telegram do not create this feedback path.**
  Flow 2 exists independently of both — it is internal to
  `ExecutionEngine`/`core/advisor_loop.py` and predates this mission's
  cockpit/Telegram-boundary work. Nothing in O-02W-C/D1/D2/D3 or this
  contract touches it.

---

## 10. Cockpit-overlap matrix

Restricted to the cockpit domains confirmed served by
`observability/operator_api/app.py` at this commit: **overview,
portfolio, decisions, system** (§8; `market`/`scores` are confirmed
`NOT_EXPOSED` stubs, §8, Correction H). No claim of equivalence is made
where Telegram computes data independently or from a different source
than the snapshot builder — every row below is explicitly qualified,
and reflects the per-message-family split in §9a rather than the
original per-identity `mixed:` rows.

| Cockpit domain | Duplicated Telegram source (§9a row) | Canonical cockpit field | Replacement exactness | Telegram unique push value? | Requires T-1? | Requires observed stable runtime window? |
|---|---|---|---|---|---|---|
| Overview | TG-06c (heartbeat/periodic reports) | `GET /api/operator/v1/snapshot` composite | PARTIAL | YES — push notification itself, independent of field content | YES | YES (Phase 2) |
| Portfolio | TG-02a (on-demand queries), TG-02b (periodic report) | `GET /api/operator/v1/portfolio` | PARTIAL | TG-02b: YES (push); TG-02a: NO added value once cockpit is trusted (query semantics only) | YES | YES (Phase 2) |
| Portfolio (real-account sub-channel) | TG-07 (STANDBY/LIVE push) | `GET /api/operator/v1/portfolio` (real/paper field coverage not confirmed) | UNKNOWN | YES, decisively — no cockpit push equivalent exists (§9, Correction G) | YES, plus a certified push replacement or explicit operator sign-off (§11 Phase 3) | YES |
| Decisions | TG-03a (on-demand queries), TG-03b (pinned refresh) | `GET /api/operator/v1/decision-pipeline` | PARTIAL | TG-03b: YES (pinned edit-in-place UX, `sendPhoto` chart delivery); TG-03a: NO added value once cockpit is trusted | YES | YES (Phase 2) |
| System | TG-06a (critical safety), TG-06b (state-change) | `GET /api/operator/v1/system-health` | PARTIAL | YES, decisively | NO — critical alerts must never wait on cockpit cutover | N/A — never retired |
| System | TG-06d (routine telemetry candidate) | `GET /api/operator/v1/system-health` | PARTIAL | UNKNOWN, pending Phase 2 | YES | YES (Phase 2) |
| System | TG-04 (Intel briefing) | none confirmed — narrative content | NONE / UNKNOWN | LIKELY YES | UNKNOWN | operator decision |
| — | TG-01 CryptoRadar | none | NONE | YES — protected, §5 | N/A | N/A |
| — | TG-05 Paper Arena | none | NONE | YES | N/A | N/A |
| — | TG-08 Sim Bot | none | NONE | YES, if deployed | N/A | N/A |

No row above is asserted as `FULL` equivalence. The strongest claim
made anywhere in this matrix is `PARTIAL`.

---

## 11. Safe cutover protocol (defined, not executed)

### Phase 0 — Current source-only state (this document's position)

- Cockpit source exists (`observability/operator_snapshot_builder.py`,
  `observability/operator_api/app.py`, `frontend/src/App.tsx`), merged
  at `17a2f70537ee48f70500974dddf5f0458c02cc50`.
- Telegram remains entirely unchanged by this mission and its R1
  remediation.
- No runtime equivalence is claimed anywhere in this document — every
  overlap in §10 is `PARTIAL` or `UNKNOWN`, never `FULL`.

### Phase 1 — T-1 deployment

- Deploy snapshot producer, operator API, and cockpit under governed
  services (systemd units, per the repository's existing deployment
  conventions in `scripts/deploy_vps.sh`).
- Establish runtime identity and deployment evidence (a deployed-SHA
  record, post-restart verification — per this repository's existing
  `docs/operations/PRE_RESTART_RUNTIME_CONTRACT.md` conventions).
- **No Telegram retirement at this phase.** Every identity in §9/§9a
  continues operating exactly as today.

### Phase 2 — Parallel observation

- Cockpit and existing Telegram reporting run concurrently.
- For each `PARTIAL` row in §10, compare displayed facts from
  equivalent timestamps and sources; record mismatches in a dedicated
  observation log (mechanism to be defined by the T-1/E2 mission, not
  this one).
- Critical alerts (TG-06a/b, `CRITICAL_SAFETY_ALERT` rows) remain
  enabled throughout, unconditionally.
- Minimum duration and mismatch-tolerance thresholds are not set by
  this document — they are an `OPERATOR_DECISION_REQUIRED` item for
  whoever executes Phase 2.

### Phase 3 — Retirement eligibility

A duplicated Telegram flow (i.e., any §9a row currently marked
`KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`) becomes eligible for
`RETIRE_AFTER_CERTIFIED_CUTOVER` only if **all** of the following hold:

1. Cockpit source is canonical (already true, Phase 0).
2. Runtime identity is verified (Phase 1 deliverable).
3. API/cockpit availability is demonstrated over the Phase 2 window.
4. No unexplained value divergence remains between the Telegram
   message and the cockpit field it would replace.
5. The operator explicitly approves retirement, flow by flow.
6. Rollback instructions exist for that specific flow.
7. **[R1, Correction G, new criterion]** If the flow carries confirmed
   unique push/notification value (§9a, "Telegram unique push value?"
   column = YES in §10), retirement additionally requires **either**
   the operator explicitly accepting the loss of push delivery for
   that specific flow, **or** a separately certified push-capable
   cockpit notification replacement. Field parity alone never
   satisfies this criterion.

`CRITICAL_SAFETY_ALERT` rows (TG-06a) are **never** eligible for this
phase — they remain `KEEP_PERMANENT_CRITICAL_ALERT` regardless of
cockpit maturity. TG-06b (state-change/degraded) is treated the same
way pending the §13 drift resolution. TG-07 (STANDBY↔LIVE) is
`OPERATOR_DECISION_REQUIRED` rather than on an automatic path to
`KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` → retirement, specifically
because of criterion 7 above.

### Phase 4 — O-02W-E2 implementation (future mission, not this one)

- Disable or remove only the specific duplicated flows the operator
  approved in Phase 3.
- Preserve every `KEEP_PERMANENT_CRITICAL_ALERT` and
  `KEEP_RESEARCH_INTERFACE` row unconditionally.
- Never modify execution authority (ADR-0007 remains absolute).
- One bot/message family per reversible change — no batch retirement.
- Address the dormant-mutator boundary debt (§9b) and the real-capital
  architectural-boundary decision (§9c) via a separate, narrowly
  scoped source mission **before** any T-1 runtime certification is
  considered final — not as part of E2's Telegram-retirement work
  itself, since neither is a Telegram-retirement item.

---

## 12. What this mission did not do

- Did not modify `scripts/radar_bot.py`, any other Telegram sender or
  poller, any `.env*` file, or any systemd unit.
- Did not deploy the cockpit, start T-1, or start O-02W-E2.
- Did not add any control, mutation route, or Telegram-control proxy
  to the cockpit.
- Did not read or print any real secret value — `.env.example` and
  `.env.secrets.example` were inspected for variable names and
  comments only; all values in `.env.secrets.example` at this commit
  are empty placeholders.
- Did not touch the VPS.
- Did not edit `docs/GLOBAL_STATE_MACHINE.md` or
  `supervision/exchange_monitor.py`, despite the staleness/drift items
  identified in §1/§13 — those corrections are recorded here as
  findings for a future, narrowly scoped source mission, per §13's
  explicit statement that they must be corrected before T-1
  deployment/runtime certification, not in this documentation-only PR.
- **[R1]** Did not modify `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`
  — its existing R1-era pointer (added by the original O-02W-E1
  mission) is left byte-for-byte unchanged, per this remediation's
  scope restriction.
- **[R1]** Did not modify `_set_param_live`, its wiring into
  `CommandDataProvider`, or `ExecutionEngine.fetch_available_capital()`
  — both are documented as architectural boundary debt (§9b, §9c)
  requiring a separate future source mission, not redesigned or
  neutralized here.

---

## 13. Contradictions and safety-relevant operator-instruction drift discovered between current source and historical documentation

**[R1, Correction C — reclassified and expanded]** The original text's
closing sentence ("No contradiction found rises to the level of a
safety concern") is removed. Items 1 and 2 below are reclassified as
`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`: not proof of an active
Telegram control surface (both instructions are currently
non-actionable, §9/§6), but capable of misleading an operator into
believing a functioning recovery command exists during a degraded or
halted state — which is precisely a safety-relevant condition.

1. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`** —
   `docs/GLOBAL_STATE_MACHINE.md` (~line 30/35) attributes
   `NORMAL ↔ SAFE_MODE` transitions partly to "KillSwitch / Telegram."
   Current source shows these transitions are exclusively programmatic
   (`KillSwitchHardened.force_safe_mode()`/`.force_resume()`), never
   Telegram-triggered — no active code path calls `force_resume()`
   from any Telegram handler (confirmed: zero call sites outside the
   method's own definition and the unreachable `supervision/telegram_kill_switch.py`
   parallel definition, §9 TG-11). Not corrected in this mission (out
   of scope); must be corrected in a separate, narrowly scoped source
   mission **before T-1 deployment/runtime certification**.
2. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`** —
   `supervision/exchange_monitor.py:252-257` tells the operator (via an
   email escalation body) to send `/STOP_ALL` on Telegram. No live
   Telegram poller implements that command against a real token — the
   only implementation (`supervision/kill_switch.py`) is
   `MODULE_IMPORTABLE_NOT_INSTANTIATED` (§9, Correction B), not a live
   handler. The instruction is currently non-actionable as written.
   Not corrected in this mission; must be corrected before T-1.
3. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` [R1, new]** —
   `core/advisor_loop.py` contains three operator-facing `/RESUME`
   instructions with the identical drift: line 3870 (degraded-mode
   alert, "Envoyez /RESUME si intervention requise"), line 3878
   (halted-mode alert, "Envoyez /RESUME pour reprendre"), and line 5576
   (the halted-loop wait message itself, "Boucle suspendue par Kill
   Switch. Envoyer /RESUME pour reprendre"). None of these are
   actionable via any live Telegram poller — `KillSwitchHardened`
   (the class actually running as the kill switch, per §9's TG-09
   correction) has zero Telegram code, and `force_resume()` has zero
   call sites outside its own definition. This is the same class of
   drift as items 1-2 above, discovered during this R1 remediation's
   evidence re-verification (Correction C) — not corrected here; must
   be corrected before T-1, ideally in the same narrowly scoped
   mission as items 1-2, since all four instructions share the same
   root cause (a kill-switch resume path with no live Telegram
   trigger).
4. `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`'s description of an "ÉLEVÉ"
   risk `RADAR_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN` fallback is stale
   (current `scripts/radar_bot.py` has no such fallback) — but this is
   already self-acknowledged by `TELEGRAM_IDENTITY_REGISTRY.md`'s own
   before/after note, so it is a reconfirmation, not a new
   contradiction, and not safety-relevant (no operator instruction is
   involved).
5. `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`'s absolute
   line-number citations for the Real Account Bot in
   `core/advisor_loop.py` have drifted (code moved, not changed in
   behavior) — corrected in this document's §1/§9, not safety-relevant.

**Required follow-up, stated explicitly:** items 1-3 must be corrected
in a separate, narrowly scoped source mission before T-1
deployment/runtime certification — either by removing the misleading
`/RESUME`/`/STOP_ALL` instructions from operator-facing messages, or by
actually wiring a live, constitutionally-compliant resume/stop path.
This document does not choose between those options and does not
modify runtime code to implement either.

---

## 14. Verification performed

**[R1]** Re-run for this remediation round:

- `git diff --check`: clean (no whitespace-conflict markers) on this
  round's sole change (`docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md`
  only — `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md` untouched,
  confirmed byte-identical to its R1-starting-HEAD state).
- Repository-wide case-insensitive searches for Telegram API methods
  (`api.telegram.org`, `sendMessage`, `getUpdates`, `sendPhoto`,
  `editMessage`, `deleteWebhook`) and control-command strings
  (`/resume`, `/stop_all`, `/close_all`, `/safe_mode`, `/kill`,
  `/restart`, `/set`, `/pause`, `/confirm`, `/cancel`), scope-separated
  into production/archive/test/doc/config buckets — results folded
  into §6, §9, §13, §17.
- Comparison between all 18 explicitly-named non-archive
  Telegram-capable source files (mission mandate §3) and the new
  source-file inventory (§17) — all 18 accounted for, none omitted,
  none MISSING.
- Searches confirming no residual overclaims: `DEAD_CODE_SOURCE_PROVEN`
  now used only for TG-10 (Narrator, unambiguous — no module exists)
  and the general definition in §0; TG-09 (legacy KillSwitch) reclassified
  to `MODULE_IMPORTABLE_NOT_INSTANTIATED` throughout §9/§6/§13; the
  string "unreachable" is no longer applied to `supervision/kill_switch.py`
  without the package-init-import qualification; "no import chain" is
  removed as a claim about that file; the sentence "no contradiction...
  rises to a safety concern" is removed from §13; the unscoped "38"
  and unscoped "exactly 5" figures are replaced with scope-qualified
  figures in §6/§9/§17; `REAL_ACCOUNT_BOT_TOKEN` is now described as
  "no live read... historical comment persists" rather than "no
  reference remains anywhere"; `set_param`/`_set_param_live` are
  described with the "one hop from activation" precision in §9b;
  `real_capital`/`fetch_available_capital` are fully documented in
  §9c; `/RESUME` is now covered in §6/§13 alongside the pre-existing
  `/STOP_ALL` coverage; no `mixed:` category label remains anywhere in
  this document (§9a replaces all three instances).
- Markdown structure reviewed manually for heading/table well-formedness.
- The cross-stack compatibility gate
  (`.github/workflows/cross-stack-compat.yml`) runs on every PR to
  `main` per its trigger configuration; not modified by this mission
  or its R1 remediation. Result to be read from PR #130's checks by
  the reviewer — this round's own bounded CI inspection (§ below)
  confirmed no regression was introduced by this documentation-only
  change; pre-existing, base-branch failures unrelated to this PR
  (documented in PR #130's comment history) are unaffected.

**Explicit confirmations for this remediation round:**

- Every one of the 18 named source files in the mission mandate is
  accounted for in §17 — none omitted.
- Every message-family row in §9a carries exactly one message
  category — no `mixed:` labels remain.
- No immediate Telegram retirement is authorized anywhere in this
  document — zero `RETIRE_AFTER_CERTIFIED_CUTOVER` classifications.
- CryptoRadar (`scripts/radar_bot.py`) remains protected and untouched
  — confirmed by `git diff` scope (only the contract file changed).
- Critical alerts (TG-06a) remain permanently preserved
  (`KEEP_PERMANENT_CRITICAL_ALERT`, never subject to Phase 3).
- No runtime or deployment claim is inferred from repository presence
  anywhere in this document — every claim distinguishes source proof
  (`SOURCE_PROVEN`), import-reachability
  (`MODULE_IMPORTABLE_NOT_INSTANTIATED`), and runtime/deployment proof
  (`RUNTIME_UNKNOWN` unless a systemd `ExecStart=` or an
  already-confirmed-active caller is shown).
- No runtime, Telegram, or workflow file was changed by this
  remediation — the diff is limited to this one contract document.

---

## 15. Pointer

A short non-normative pointer to this contract exists in
`docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md` (added by the
original O-02W-E1 mission). **[R1]** That pointer is left byte-for-byte
unchanged by this remediation round, per its scope restriction (§12).

---

## 16. Summary for MASTER review

- 11 identity rows resolved (§9), with per-message-family granularity
  in §9a (24 message-family rows total across TG-02/03/06/07,
  replacing the original 3 composite `mixed:` cells).
- Zero flows classified `RETIRE_AFTER_CERTIFIED_CUTOVER` — none are
  eligible yet, correctly, since Phase 1-3 have not occurred.
- Critical safety alerts (TG-06a) classified `KEEP_PERMANENT_CRITICAL_ALERT`,
  never subject to cutover. TG-06b (degraded-state) held to the same
  standard pending the §13 drift resolution.
- CryptoRadar and Paper Arena classified `KEEP_RESEARCH_INTERFACE`,
  untouched, no overlap with cockpit domains.
- `OPERATOR_DECISION_REQUIRED` items: TG-04 (Intel briefing
  replacement value), TG-06d (routine-telemetry-candidate split
  pending Phase 2), TG-07 (STANDBY↔LIVE push — **[R1, new]** moved
  here from an automatic cutover path per Correction G), TG-08 (Sim
  Bot deploy-or-remove), TG-11 (superseded-status confirmation before
  any removal), plus **[R1, new]** the real-capital architectural
  boundary (§9c, Flow 2) as a separate item requiring explicit
  MASTER/operator sign-off, distinct from any Telegram-retirement
  decision.
- `FORBIDDEN_MUST_NEVER_REACTIVATE`: TG-09 (legacy KillSwitch,
  reclassified per Correction B to `MODULE_IMPORTABLE_NOT_INSTANTIATED`
  — package-init-importable, never instantiated with a live token,
  not "unreachable" in the unqualified sense the original text used)
  and TG-02c (the currently-inert blocked-command set that would
  activate `_set_param_live` if ever unblocked, §9b).
- **[R1, new]** Four items now classified `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`
  (§13): three `/RESUME` instructions in `core/advisor_loop.py` plus
  the pre-existing `/STOP_ALL` instruction in
  `supervision/exchange_monitor.py` — all four must be corrected in a
  separate, narrowly scoped source mission before T-1
  deployment/runtime certification.
- **[R1, new]** Two architectural-boundary items requiring a future
  source mission, neither modified by this documentation-only PR: the
  dormant Portfolio mutator (§9b, `_set_param_live`) and the
  real-capital sizing/risk feed (§9c, Flow 2).

---

## 17. Non-archive Telegram-capable source-file inventory (Correction A)

**[R1, new section]** Complete accounting of the 18 files named in the
O-02W-E1-R1 mission mandate, plus the previously-covered identity
files for cross-reference. "Reachable" means confirmed imported or
instantiated from an already-active entrypoint (`core/advisor_loop.py`,
`paper_runner.py`, or a systemd `ExecStart=`) — absence of a systemd
unit or caller does **not** prove the file never runs (it could be
invoked manually or by an undiscovered scheduler), it only means this
mission found no `SOURCE_PROVEN` active caller, hence `RUNTIME_UNKNOWN`
rather than a "dead" or "active" claim.

| File | Identity/token group | Role | Capability | Message family | Reachability evidence | Runtime evidence | Cutover classification |
|---|---|---|---|---|---|---|---|
| `S3/01_telegram_alerts.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Generic ops alert (standalone S3 provisioning script) | No systemd `ExecStart=` match; not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` (provenance/current use unclear) |
| `infra/monitoring/watchdog_vps.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | VPS liveness alert | **Distinct duplicate** of the root-level `watchdog_vps.py`, which is the file actually wired to `crypto-watchdog.service` (`ExecStart=...python3 watchdog_vps.py`, `WorkingDirectory=` the repo root) — this `infra/monitoring/` copy is not referenced by any systemd unit | RUNTIME_UNKNOWN; likely a stale duplicate given the naming/content divergence from the wired root file | `DEAD_CODE_REMOVAL_CANDIDATE` (duplicate-file risk — operator should confirm which copy is authoritative before any future edit touches the wrong one) |
| `infra/notifications/notify_test_status.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | CI/test-run status notification | No systemd/CI-workflow reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `observation/market_radar.py` | `RAPPORT_AUTOMATIQUE_BOT_TOKEN`/`_CHAT_ID` (gated by `RADAR_TELEGRAM_DIGEST`, default off) | Sender-only, opt-in digest | PUSH_ONLY (disabled by default) | Optional market-radar digest via the Rapport Automatique channel | `scripts/systemd/crypto-market-radar.service` `ExecStart=...python observation/market_radar.py --run` | SOURCE_PROVEN (code + systemd reference); RUNTIME_UNKNOWN whether the service/flag are actually enabled on the VPS | `KEEP_RESEARCH_INTERFACE` if enabled — separate from CryptoRadar (TG-01), shares TG-04's token |
| `scripts/daily_signal_report.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Daily signal-summary report | No systemd/cron reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/data_verifier.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Data-integrity verification alert | No systemd/cron reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/quant_observer_pin_bootstrap.py` | `QUANT_CRYPTO_BOT_TOKEN`/`_CHAT_ID` | One-shot bootstrap sender | PUSH_ONLY (one-shot) | Creates/pins the placeholder message TG-03 then edits | Referenced only as a **commented-out** manual step in `scripts/systemd/crypto-quant-observer.service:13` | RUNTIME_UNKNOWN (manual operator tool) | `KEEP_RESEARCH_INTERFACE` (operator bootstrap utility for TG-03) |
| `scripts/test_intel_report.py` | `RAPPORT_AUTOMATIQUE_BOT_TOKEN`/`_CHAT_ID` | Sender-only test/debug script | PUSH_ONLY | Manual test of the Intel-briefing message format | No systemd/cron reference | RUNTIME_UNKNOWN | `DEAD_CODE_REMOVAL_CANDIDATE` (test/debug utility) |
| `scripts/trend_scanner.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Trend-scan alert | No systemd/cron reference | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/vps_burn_in_collector.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Burn-in metrics collection warning | No systemd/cron reference | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `src/telegram/notifier.py` | `MON_PORTFOLIO_BOT_TOKEN`/`_CHAT_ID` | Library/notifier module | Library-only | Generic `Notifier` wrapping `sendMessage` for the Portfolio token | Imported by `src/telegram/__init__.py:1` and `src/telegram/sim_bot.py:36` (TG-08, itself undeployed) | RUNTIME_UNKNOWN — reachable today only via the already-undeployed TG-08 chain | `DEAD_CODE_REMOVAL_CANDIDATE` unless TG-08 is deployed (operator decision, §9 TG-08) |
| `supervision/notifications/telegram_notifier.py` | token/chat passed by caller (no module-level constant) | Library/notifier module | Library-only | Thin `TelegramNotifier.notify()` wrapper | **Reachable**: imported by `quant_hedge_ai/agents/intelligence/self_awareness_engine.py:623` and `quant_hedge_ai/agents/execution/position_manager.py:526`, both instantiated from `core/advisor_loop.py` via `core/advisor_runtime_adapters.py` (`SelfAwarenessEngine` used at `advisor_loop.py:4484`; `PositionManager` used at `advisor_loop.py:4055-4056,4180`) | SOURCE_PROVEN reachable via an active import chain; whether `.notify()` is actually invoked with real tokens by those two modules at runtime was not further traced — RUNTIME_UNKNOWN for actual message delivery | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` if its callers' alerts overlap cockpit `system`/`decisions` domains — requires the same Phase 2 comparison as TG-06 |
| `supervision/self_healing_bot.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only module | PUSH_ONLY | Self-healing/module-recovery alert | **Reachable**: `core/advisor_runtime_adapters.py:111` imports `SelfHealingBot`, instantiated at `advisor_loop.py:3623-3624`, started at `advisor_loop.py:3686` | SOURCE_PROVEN (code + active caller); RUNTIME_UNKNOWN whether `crypto-advisor.service` is running on the VPS | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` — same TG-06-class treatment; should be folded into TG-06's Phase 2 comparison as an additional message source |
| `core/orchestration/orchestrate_ecosystem.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (via `TelegramNotifier`) | Orchestration script | Library-caller, PUSH_ONLY when invoked | Multi-world-simulation run-and-archive notification | No systemd unit; not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN, likely dead (no active entrypoint found) | `DEAD_CODE_REMOVAL_CANDIDATE` |
| `infra/monitoring/supervise_all.py` | `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` (note: **different env-var name**, `TELEGRAM_TOKEN` not `TELEGRAM_BOT_TOKEN`, with hardcoded placeholder defaults) | Standalone supervision loop | Library-caller, PUSH_ONLY when invoked with real values | BotDoctor health-score alert | No systemd unit; not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN, likely dead | `DEAD_CODE_REMOVAL_CANDIDATE`; flag the env-var name mismatch as a separate minor finding — even a fully-configured `.env` would not arm this file's default token path |
| `event_bus/bridge.py` | none (docstring-only "Telegram" mentions) | Not a Telegram-capable file | none — zero API literals | n/a | n/a | n/a | Not applicable — excluded from all counts |
| `supervision/ops_watchdog.py` | none (one docstring mention) | Not a Telegram-capable file | none — zero API literals | n/a | n/a | n/a | Not applicable — excluded from all counts |
| `supervision/ops_watchdog_hardened.py` | none (one docstring mention) | Not a Telegram-capable file | none — zero API literals | n/a | n/a | n/a | Not applicable — excluded from all counts |

**Scope-separated repository totals** (Correction A, restated from
§6): `api.telegram.org` — 42 total, 4 archive, 5 test, 2 docs, 1
config, **30 production-source** (spread across the files above plus
the identity-bearing files already in §9: `scripts/radar_bot.py`,
`capital_deployment/command_center_bot.py`,
`src/telegram/quant_observer/bot.py`, `src/telegram/bot_runner.py`,
`src/telegram/sim_bot.py`, `src/paper/paper_report.py`,
`supervision/exchange_monitor.py`, `supervision/performance_watchdog.py`,
`supervision/kill_switch.py`, `scripts/telegram_alerts.py`,
`core/advisor_loop.py`, root `watchdog_vps.py`). `getUpdates` — 76
total, scoped production-source count exactly 5 (§6, §9).

Three of the 18 named files (`event_bus/bridge.py`,
`supervision/ops_watchdog.py`, `supervision/ops_watchdog_hardened.py`)
were confirmed to contain **no** Telegram API literal — only prose
docstring mentions of "Telegram" as a hypothetical notification
channel. These are correctly excludable from every call-site count in
this document; including them in the mission's audit scope (rather
than silently dropping them) is itself part of what Correction A
requires — an omission would be as much an evidence-quality defect as
a miscount.

---

O02WE1_R1_IMPLEMENTATION_COMPLETE_MASTER_REVIEW_REQUIRED
