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

**R1.1 remediation (O-02W-E1-R1.1, same date):** independent MASTER
review found six further evidence-accounting and internal-consistency
defects, corrected in place below (marked `[R1.1]`): (A) the raw
occurrence counts are re-derived with exact, reproducible `git grep`
commands and scope buckets (§6, §17) — `api.telegram.org`: 42 total /
4 archive / 6 test / 2 docs / 1 config / 29 remaining source-script
occurrences, of which 2 are confirmed non-invocation strings
(`S3/06_apply_S3.sh`'s operator instruction, one sanitizer-redaction
line in `src/telegram/quant_observer/bot.py`), leaving 27 occurrences
across 23 files that actually construct/issue a request —
`getUpdates` (case-insensitive): 87 total / 4 archive / 11 test / 51
docs / 4 config / 17 other, with the file-scoped "exactly 5 pollers"
claim retained and now explicitly scope-qualified; (B) three files
previously called "not Telegram-capable" (`event_bus/bridge.py`,
`supervision/ops_watchdog.py`, `supervision/ops_watchdog_hardened.py`)
are corrected to indirect-Telegram-capable via `OpsNotifier` →
`TelegramNotifier`, each with its `from_env()` construction site cited
and its caller status recorded (§17); (C) two source-proven
nonfunctional notifier call sites are added —
`self_awareness_engine.py:626` and `position_manager.py:528` both call
`TelegramNotifier().send(...)`, a signature/method mismatch against the
real `TelegramNotifier(bot_token, chat_id).notify(message)` API,
silently swallowed by `except Exception: pass` — new evidence class
`SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL` (§0, §13); the
SelfAwareness message's own `/RESUME` instruction is added to the
safety-drift inventory (§6, §13), which now totals **five** items, not
four, and distinguishes three presently send-capable advisor messages
from one currently-non-deliverable SelfAwareness message and the
pre-existing `/STOP_ALL` instruction; (D) the real-capital fallback is
corrected from "fail-closed to `UNKNOWN`" to its actual behavior — API
failure falls back to `_last_value`, then to `_base_capital()`
(`_x` or `WALLET_PAPER_CAPITAL`), never to an unknown/undefined
numeric value; only the Command Center *provenance label* (not the
sizing number itself) can resolve to `UNKNOWN` (§9c); (E) internal
count contradictions are fixed — §16 wrongly claimed 24 message-family
rows in §9a where 10 actually exist (§9a, §16); TG-09 is removed from
any "dead-code-only" count given its `MODULE_IMPORTABLE_NOT_INSTANTIATED`
classification (§16); TG-10 (Narrator)'s "no module exists" fact is
now stated without invoking the `DEAD_CODE_SOURCE_PROVEN` definition's
"code exists" clause verbatim (§9, new note); the TG-06 identity-matrix
row's Token var column previously also listed the two chat-identifier
variables (`TELEGRAM_CHAT_ID`, `TELEGRAM_BEHAVIOR_CHAT_ID`) alongside
the actual token (`TELEGRAM_BOT_TOKEN`) — corrected to separate token
from chat columns properly (§9); (F) speculative language ("likely
dead," "likely stale duplicate," "reachable via an active import
chain," "already-active entrypoint") is replaced throughout §17 with
bounded source statements (source caller found/not found, systemd
reference found/not found, runtime status unknown without VPS
evidence), and manual/debug scripts are reclassified
`OPERATOR_DECISION_REQUIRED` rather than assumed dead. R1.1's starting
HEAD is `781825b8ae8d5ccc9204923bcb29477eb6f7c498`; only this file was
modified.

**R1.2 remediation (O-02W-E1-R1.2, same date):** independent MASTER
review found six further defects, corrected in place (marked `[R1.2]`):
(A) `TG-10` (Narrator) used `DEAD_CODE_SOURCE_PROVEN`, whose own
definition requires a confirmed-present implementation — but no
implementation module exists for TG-10 at all. Corrected: new evidence
class `NO_IMPLEMENTATION_SOURCE_PROVEN` applied to TG-10;
`DEAD_CODE_SOURCE_PROVEN` is now defined as currently unused by any
row (§0, §9); (B) `/RESUME` accounting in `core/advisor_loop.py` was
undercounted — `git grep -ni '/resume' <rev> -- core/advisor_loop.py`
returns 11 raw line hits, not 4; corrected to state 11 total, exactly
3 of them operator-facing Telegram strings (3870, 3878, 5576), the
remaining 8 being callbacks/logs/comments/unrelated identifiers, with
the SelfAwareness message recorded as a separate, fourth
operator-facing `/RESUME` string outside `advisor_loop.py` (§6, §13);
(C) safety-drift counting is normalized throughout §6/§13/§16 into
three explicit, non-overlapping units — 4 numbered findings, 5
misleading operator-facing command strings, 2 source-proven
nonfunctional notifier call expressions (only 1 of which carries a
`/RESUME` string) — no longer used interchangeably as "five items"; (D)
runtime/delivery overclaims removed throughout ("actually running as
the kill switch," "are delivered," "functioning push mechanisms," "the
operator receives the message," "active caller," "already-active
entrypoint," "live Command Center bot instance," and similar), replaced
with source-valid-construction-path / source-valid-delivery-attempt-path
language and explicit `RUNTIME_UNKNOWN` framing for actual delivery;
`SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL`'s definition is now
conditional ("if reached, deterministically fails") rather than
asserting the trigger occurs in production; (E)
`infra/notifications/notifications.py` is now read in full and
documented (`_build_notifier()`, `NOTIFIER` import-time construction,
`send_alert()`, `TelegramBotAdapter`, `build_telegram_bot()`; no
non-test/non-archive caller found) rather than left as an
admitted-unread gap (§17); (F) the `TelegramNotifier` citation is
corrected (`__init__` lines 16-18, `.notify()` begins line 20, not
line 18), and this document no longer prescribes
`TelegramNotifier(bot_token, chat_id).notify(message)` as the sole
authorized repair — a future source mission must choose among removal,
routing through an approved facade, or a governed repair, and this
contract does not authorize creating, copying, exposing, or wiring any
Telegram secret to implement any option. R1.2's starting HEAD is
`5149d3f1cfa347f91511ac7216930e170c5be0d8`; only this file was
modified.

**R1.3 remediation (O-02W-E1-R1.3, same date):** independent MASTER
review found four residual defects, corrected in place (marked
`[R1.3]`): (A) TG-10's cutover cell still read `DEAD_CODE_REMOVAL_CANDIDATE`
/ "dead-code hygiene" despite using `NO_IMPLEMENTATION_SOURCE_PROVEN`
as its evidence class — corrected to a new, non-code-implying label
(`CONFIG_PLACEHOLDER_HYGIENE_CANDIDATE` / "comment/configuration
placeholder cleanup"), stating precisely that only two commented-out
env placeholders exist and there is no implementation to retire; (B)
normative (non-historical) occurrences of "active code path," "active
production instantiation," "active caller," "already-active
entrypoint," and equivalents are replaced throughout with bounded
source terminology (named repository entrypoint, non-test/non-archive
importer or caller found/not found, systemd reference present), and
§14's verification bullet now states explicitly that a repository
entrypoint, import chain, construction site, call site, or systemd
reference proves only source/configuration reachability, never
deployment, execution, or delivery; (C) §13's four safety-relevant
findings are each given their own explicit remediation (finding 1: a
documentation/governance correction to `GLOBAL_STATE_MACHINE.md`;
finding 2: remove/replace the `/STOP_ALL` string; finding 3:
remove/replace the three `/RESUME` strings; finding 4: a separate
remove/route/repair decision per broken call expression) rather than
one shared "source mission," and §16's summary is aligned to match;
(D) the closing §13 rule now states explicitly that removing or
rewording a misleading instruction is the safe default, that
implementing any live Telegram control command is *not* authorized by
this mission or any prior remediation round, and what a future
control-surface mission would require (separate MASTER authorization,
an ADR/authority-boundary review, security review,
authentication/replay/audit requirements, dedicated tests) — replacing
the prior "actually wire a live... resume/stop path" phrasing, which
read as authorizing exactly what this rule now forecloses. R1.3's
starting HEAD is `d1b3687ef5dd8f2d9457f76f448d8db343e6e08f`; only this
file was modified.

**R1.4 remediation (O-02W-E1-R1.4, same date):** independent MASTER
review found five further defects, corrected in place (marked
`[R1.4]`): (A) TG-10's cutover classification is corrected from a
code-removal-shaped label to `OPERATOR_DECISION_REQUIRED` — the
identity registry's own IDENTITY-10 narrative
(`docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md:256`) records an
unresolved operational claim (an alleged live/zombie process, PID 504,
and an explicitly unsigned "narrateur retiré" ADR) that repository
source absence cannot settle; every live normative "(dead) Narrator"
characterization is removed; (B) this document no longer claims every
`TELEGRAM_IDENTITY_REGISTRY.md` status label is still accurate — §1
now explicitly discloses that the registry's own `DEAD_CODE` summary
labels for IDENTITY-09 and IDENTITY-10 are superseded by, or in
tension with, this contract's stronger source review and (for
IDENTITY-10) the registry's own narrative section, without this
contract claiming to prove runtime truth or unilaterally retiring the
registry entry; (C) `CONFIG_PLACEHOLDER_HYGIENE_CANDIDATE` — never
part of §4's closed cutover vocabulary — is removed as a live cutover
value (TG-10 now uses `OPERATOR_DECISION_REQUIRED`); a mechanical
comparison confirms every value used in every cutover-classification
cell now appears in §4's seven-value allowlist; (D) residual
runtime-implying terms ("active entrypoint," "active caller," "live
handler," "live credentials," "live token," "live dispatcher," "no
live Telegram handler") are replaced throughout the live normative
text — including the §3 `DEAD_OR_UNREACHABLE_CODE` and
`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` definitions, the
`MODULE_IMPORTABLE_NOT_INSTANTIATED`/`DEAD_CODE_SOURCE_PROVEN`
evidence-class definitions, TG-09's row, and §13's findings 2-3 — with
bounded source statements (no non-test/non-archive import,
construction, or call found; no dispatcher found on the reviewed
canonical source path); legitimate `LIVE`/`TESTNET` trading-mode
labels and function/variable names (e.g. `_set_param_live`) are left
untouched; (E) §13/§16 now state explicitly that the "4 numbered
safety-relevant findings" are items 1-4 of §13's six-entry numbered
list (items 5-6 are not safety-relevant), without altering the
certified totals (4 findings / 5 strings / 2 broken calls, only 1
carrying `/RESUME`). R1.4's starting HEAD is
`6fba05afd851c212fb96bd82a87c3b1e03afc892`; only this file was
modified.

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
| `MODULE_IMPORTABLE_NOT_INSTANTIATED` **[R1, new; wording bounded R1.3]** | A non-test, non-archive `import` statement for this module/class is confirmed present in source (directly, or transitively — e.g. at package-init, so any import of the containing package executes this module's top-level code) — but no non-test, non-archive construction call supplying token credentials, or start/poll method call, was found anywhere in source. Importing a class has no runtime effect by itself unless the module has import-time side effects (checked case by case). This class states two source facts only — an import statement exists, and no construction call was found — not that either the import or a construction call has executed in a deployed process. Distinct from, and a narrower claim than, `SOURCE_PROVEN` reachability — and distinct from, and a broader claim than, full unreachability. |
| `DEAD_CODE_SOURCE_PROVEN` | An implementation (module/class) is confirmed present in source, and after checking both the import graph *and* every instantiation/call site, no non-test, non-archive construction call supplying token credentials, or behavior-invoking call, was found anywhere in source. **[R1]** This class must not be used for a module that is merely uninstantiated if an import statement for the module is still found on a non-test, non-archive path — use `MODULE_IMPORTABLE_NOT_INSTANTIATED` for that case instead, so "no construction call found" is never conflated with "no import found." **[R1.2, definition tightened; wording bounded R1.3]** This class presumes an implementation exists to be checked. It is **not used anywhere in this document as currently written** — the one identity it might have applied to (TG-10, Narrator) has no implementation module at all, so `NO_IMPLEMENTATION_SOURCE_PROVEN` (below) applies instead, a narrower and distinct fact than "implementation exists but no construction call was found." This class remains defined for potential future use (an identity with a confirmed-present implementation and no construction call found anywhere), but no row in §9 currently uses it. |
| `NO_IMPLEMENTATION_SOURCE_PROVEN` **[R1.2, new]** | This mission's searches found configuration/comment placeholders referencing an identity (e.g. a token/chat variable name), but found **no implementation module, class, function, entrypoint, instantiation, or call site** anywhere in non-archive source for that identity. Distinct from `DEAD_CODE_SOURCE_PROVEN` (which requires a confirmed-present implementation that is merely unreachable) — this class instead states that no implementation was found to evaluate reachability of in the first place. Absence of an implementation is not "dead code": there is no code, live or dead, to classify. |
| `SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL` **[R1.1, new; scope tightened R1.2]** | A notification call site is confirmed present in source, and its exact invocation (constructor arguments, method name) is confirmed to not match the callee's real API — so **if** the containing component is running and the triggering condition reaches this expression, the expression deterministically raises an exception before any HTTP request is attempted, caught and discarded by a broad `except Exception` at or near the call site. This class asserts only the deterministic-failure-if-reached fact; it does **not** assert that the containing component is running or that the trigger has ever actually occurred in production — both remain `RUNTIME_UNKNOWN`. Distinct from `DEAD_CODE_SOURCE_PROVEN`/`MODULE_IMPORTABLE_NOT_INSTANTIATED` (which describe whether a code path is ever reached at all) — this class describes what happens *if* it is reached. See §13. |
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
  remains an important, thorough identity inventory, and most of its
  claims (IDENTITY-01 through IDENTITY-10) were re-confirmed accurate
  at this commit. **[R1.4, Correction B — this document no longer
  claims every registry status label is still accurate]** Several
  registry evidence/status labels are now known to be stale or in
  direct tension with this contract's stronger, independently-verified
  source review, and this contract does not silently paper over that:
  - **IDENTITY-09 (KillSwitch)**: the registry's `DEAD_CODE` label
    (its own summary table, `TELEGRAM_IDENTITY_REGISTRY.md:67`, column
    "Status") is superseded by this contract's bounded
    `MODULE_IMPORTABLE_NOT_INSTANTIATED` source evidence (§9, TG-09,
    Correction B of R1) — the class is imported at package-init time,
    a materially different fact than "dead code" states unqualified.
  - **IDENTITY-10 (Narrator)**: the registry's own summary table
    (`TELEGRAM_IDENTITY_REGISTRY.md:67` region, `DEAD_CODE` label)
    conflicts with unresolved runtime/ADR information recorded
    **inside that same registry document** — its own IDENTITY-10
    narrative section (`TELEGRAM_IDENTITY_REGISTRY.md:256-261`)
    describes an alleged live/zombie process (PID 504) and an
    explicitly unsigned retirement ADR, which the registry's own
    top-level `DEAD_CODE` label does not reflect. This contract
    classifies TG-10 `OPERATOR_DECISION_REQUIRED` rather than
    inheriting the registry's `DEAD_CODE` label (§9, TG-10, Correction
    A of R1.4).
  - This contract does **not** claim to prove runtime truth for either
    identity, and does **not** unilaterally retire, correct, or
    supersede the registry entry itself — `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`
    is left byte-for-byte unchanged by every round of this mission
    (§12, §15). The discrepancy between the registry's summary-table
    labels and its own narrative sections (and this contract's source
    review) must be resolved in a future documentation/governance
    update to the registry itself — out of scope for O-02W-E1.
  - Separately, its absolute line-number citations for
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
  command surface itself* matches (no non-test, non-archive dispatcher
  for any control command was found), but two separate
  architectural-boundary items — a dormant mutator wired into the
  Portfolio-bot provider object (§9b), and a real-account-capital feed
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
  merged/moot) Real Account identity or the Narrator identity (TG-10,
  `OPERATOR_DECISION_REQUIRED` per Correction A of R1.4 — not
  characterized here as "dead," since an unresolved runtime/ADR
  question remains open, §9). No correction needed to this coverage
  note beyond removing the prior "(dead)" characterization.
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
- `DEAD_OR_UNREACHABLE_CODE` — implemented, but after checking both the
  import graph and every instantiation/call site, no non-test,
  non-archive import, construction, or call was found on any named
  repository entrypoint at this commit.
- `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` **[R1, new; wording
  bounded R1.4]** — a message instructs the operator to use a control
  mechanism (a Telegram command) for which no dispatcher was found on
  the reviewed canonical source path. Not proof that a control surface
  is deployed or running, but capable of misleading an operator during
  a degraded or halted state into believing a functioning recovery
  path exists. See §13.
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

- **[R1.1, re-derived with reproducible methodology]** `api.telegram.org`
  literal occurrences, counted at R1 starting HEAD
  `d702b7f2a06c59eb1972de3026afd317cf70d314` (immutable, so any
  reviewer can reproduce these exact figures against that commit
  regardless of later pushes to this branch) via
  `git grep -c "api.telegram.org" <rev> -- .`, summed per file, then
  bucketed by path:
  - Total repo-wide: **42**
  - `_ARCHIVE_2026/*`: **4**
  - Test-code (`tests/*`, plus `scripts/test_intel_report.py`, a
    test/debug script located outside `tests/`): **6**
    (`git grep -c "api.telegram.org" <rev> -- 'tests/*' 'scripts/test_*.py'`)
  - `docs/*` (including this contract itself, excluded from any
    normative count below): **2**
  - Config (`config/*`, `.env*`): **1**
  - Remaining non-archive, non-test, non-doc, non-config source/script
    occurrences: **29**
    (`git grep -c "api.telegram.org" <rev> -- . ':!_ARCHIVE_2026/*' ':!tests/*' ':!scripts/test_*.py' ':!docs/*' ':!config/*' ':!.env*'`)

  Of these 29, **2 are confirmed non-invocation string literals, not
  call sites**: `S3/06_apply_S3.sh:50` is an operator setup
  instruction inside a JSON comment (`"2. Envoyer un message au bot,
  puis GET https://api.telegram.org/botTOKEN/getUpdates → chat_id"`),
  never executed as code; and `src/telegram/quant_observer/bot.py:134`
  is a log-sanitizer replacement string (`safe.replace(_API_BASE,
  "https://api.telegram.org/bot***")`) that redacts the token from
  logs, not a request. The remaining **27 occurrences, across 23
  distinct files**, are transport-supporting URL constants or literals
  that a `requests.post`/`urllib.request` call in the same file
  actually uses to issue an HTTP request (verified per-file in §17 and
  in the identity-bearing files already listed in §9/§9a). **Neither
  27 nor 23 should be called "call sites" without this qualification —
  a call site is a place where a request is issued, not merely where
  the URL string appears; §17 gives the per-file reachability/runtime
  evidence this figure alone cannot.** The original O-02W-E1 text's
  unqualified "38 call sites" and R1's "30 production call sites" are
  both superseded by this bucketed accounting; the "38" and "30"
  figures are removed from this document.
- **[R1.1, re-derived]** `getUpdates` (case-insensitive), same
  methodology, `git grep -ic "getUpdates" <rev> -- .`:
  - Total repo-wide: **87**
  - Archive: **4**
  - Test-code (`tests/telegram/*`): **11**
  - `docs/*`: **51**
  - Config/env (`.env.example`, `.env.secrets.example`,
    `config/telegram_config.json`): **4**
  - Other (systemd unit descriptions, source files not otherwise
    bucketed): **17**

  Distinct from this occurrence count: **exactly 5 non-archive,
  non-test Python files perform or implement `getUpdates` polling** —
  `scripts/radar_bot.py`, `capital_deployment/command_center_bot.py`,
  `src/telegram/quant_observer/bot.py`, `src/telegram/bot_runner.py`
  (Sim Bot), and `supervision/kill_switch.py`. This is a **file-count**
  claim, not an occurrence-count claim, and the two must never be
  conflated — the file count is reproducible via
  `git grep -icl "getUpdates" <rev> -- '*.py' ':!_ARCHIVE_2026/*' ':!tests/*'`
  filtered to files that actually implement a polling loop (not merely
  mention the term). Of these five, `supervision/kill_switch.py`'s
  polling code exists but no non-test, non-archive construction call supplying token
  credentials was found (§9, Correction B, `MODULE_IMPORTABLE_NOT_INSTANTIATED`) — its
  `getUpdates` implementation is source-proven present, not
  source-proven active.
- `deleteWebhook` appears only in `src/telegram/bot_runner.py`
  (409-conflict recovery) — irrelevant to any other identity.
- `sendPhoto`/`editMessage` are concentrated almost entirely in
  `src/telegram/quant_observer/bot.py` (pinned-panel live refresh) —
  no other bot edits or sends photos.
- `/STOP_ALL`, `/CLOSE_ALL`, `/SAFE_MODE` occur only inside: (a) the
  `supervision/kill_switch.py` implementation (reachability corrected
  in §9, Correction B — the module is package-init-importable but
  has no non-test, non-archive construction call supplying token credentials, see below), (b) docstrings in
  `supervision/killswitch_hardened.py` stating these commands were
  "retirées" (removed), (c) one operator-facing email string in
  `supervision/exchange_monitor.py:252-257` instructing the operator
  to "send `/STOP_ALL` on Telegram" — classified
  `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` (§13), (d) tests
  asserting these are now rejected.
- **[R1.2, corrected accounting]** `/RESUME` (case-insensitive) occurs
  at **11 raw line hits** in `core/advisor_loop.py`
  (`git grep -ni '/resume' <rev> -- core/advisor_loop.py`, reproducible
  against R1 starting HEAD `d702b7f2a06c59eb1972de3026afd317cf70d314`):
  lines 3560, 3563, 3566, 3571 (callback/log lines inside `_on_resume()`
  — code logging and an internal comment string, not operator-facing
  instructions), 3870, 3878, 5576 (the three operator-facing message
  strings, detailed below), 4486 (a code comment, `# expose pour
  /RESUME callback`), 4556 (a comment listing unrelated identifier
  names, `STOP_TRADING/RESUME_TRADING/REDUCE_RISK`), and 5578, 5580
  (comments describing the wait loop, not messages sent to anyone).
  **Exactly 3 of these 11 are operator-facing Telegram message
  strings**, not merely code identifiers, comments, or log lines: line
  3870 ("Envoyez /RESUME si intervention requise" — degraded-mode
  alert), line 3878 ("Envoyez /RESUME pour reprendre" — halted-mode
  alert), and line 5576 ("Boucle suspendue par Kill Switch. Envoyer
  /RESUME pour reprendre" — the halted-loop wait message). The
  remaining 8 hits must not be counted as operator instructions. A
  separate, fourth operator-facing `/RESUME` string exists **outside**
  `core/advisor_loop.py`, in
  `quant_hedge_ai/agents/intelligence/self_awareness_engine.py:626-629`
  ("SELF-AWARENESS CRITIQUE\nTrading suspendu 24h — dérives
  détectées:...\nEnvoyer /RESUME pour reprendre manuellement."), inside
  `_send_telegram_critical()` — this one is additionally
  `SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL` (§0, §13): the call
  is `TelegramNotifier().send(...)`, which does not match the real
  `TelegramNotifier.__init__(self, bot_token, chat_id)` /
  `.notify(message)` API (§17, Correction F for exact line numbers), so
  *if* this expression is reached at runtime, it deterministically
  fails before any HTTP request is attempted — caught by the enclosing
  `except Exception: pass`. Whether this expression is ever reached in
  production (i.e., whether the containing process runs and the
  triggering condition fires) is `RUNTIME_UNKNOWN`; what is
  `SOURCE_PROVEN` is only that *if* reached, it cannot succeed as
  written. **Total misleading operator-facing command strings: 5** — 1
  `/STOP_ALL` (`supervision/exchange_monitor.py:252-257`) + 4
  `/RESUME` (3 in `advisor_loop.py`, 1 in
  `self_awareness_engine.py`) — see §13 for the full inventory using
  this same unit taxonomy (findings vs. strings vs. broken call
  expressions, not interchangeably).
- `/resume`, `/kill`, `/restart`, `/set`, `/pause` hits outside
  Telegram code are unrelated non-Telegram Python syntax
  (`config/settings.py`, `risk/circuit_breaker.py`) or
  `capital_deployment/command_center_bot.py`'s explicit blocked-command
  set, which returns a fixed refusal string and never calls
  `CommandDataProvider.set_param` or any mutator (§9b, Correction D).
- No `.py` file outside `supervision/kill_switch.py` has a source-wired
  dispatcher for any of the eight command-mutation literals; none was
  found wired to a real token. **[R1]** `supervision/kill_switch.py`'s own reachability
  is corrected in §9 (Correction B): its module is imported at
  `supervision/__init__.py:11-13` (package-init time, executed by any
  `import supervision.*`), but no non-archive, non-test source file
  constructs the class with token credentials — the two
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
| TG-06 | Generic / Engine Alerts | `TELEGRAM_BOT_TOKEN` **[R1.1, corrected — this column previously also listed the two chat variables below]** | `TELEGRAM_CHAT_ID` (default channel), `TELEGRAM_BEHAVIOR_CHAT_ID` (behavior sub-channel, falls back to `TELEGRAM_CHAT_ID` if unset) | `core/advisor_loop.py` (`_telegram`, `_telegram_behavior`), `scripts/telegram_alerts.py`, `supervision/performance_watchdog.py`, `supervision/exchange_monitor.py`, `watchdog_vps.py` (root — see §17 re: the unrelated `infra/monitoring/watchdog_vps.py` duplicate) | `crypto-advisor.service` + independent scripts | PUSH_ONLY | SYSTEM | PARTIAL (see §9a for per-family split) | SOURCE_PROVEN | see §9a rows TG-06a/b/c/d | operator decision (message-family split) / E2 |
| TG-07 | Real Account Bot (merged into TG-02's token) | — (uses `MON_PORTFOLIO_BOT_TOKEN`/`_CHAT_ID`) | same as TG-02 | `core/advisor_loop.py::_telegram_real` (1186-1205) | `crypto-advisor.service` (in-process) | PUSH_ONLY (shares TG-02's token; TG-02 remains the sole poller for that token) | PORTFOLIO (real-account sub-channel) | PARTIAL — see §9a | SOURCE_PROVEN (merge complete: no live `os.getenv("REAL_ACCOUNT_BOT_TOKEN")` read remains; historical comment identifier persists, §1) | **[R1, Correction G]** `OPERATOR_DECISION_REQUIRED` — was `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`; corrected because this is a unique push notification with no cockpit-side push equivalent (cockpit is pull-only, §8); field parity alone cannot retire it — see §11 Phase 3 | operator decision / E2 |
| TG-08 | CMVK / Sim Bot | `TELEMETRIE_IA_BOT_TOKEN` | `TELEMETRIE_IA_CHAT_ID` | `src/telegram/bot_runner.py`, `src/telegram/sim_bot.py` | none — no systemd unit references this file; not called from `advisor_loop.py` or `paper_runner.py`; not in `.env.example` | BOTH (code fully implements polling+push if run manually) | EXPERIMENT (simulation/backtest inspection) | NONE | RUNTIME_UNKNOWN — code SOURCE_PROVEN, but no deployment entrypoint exists at this commit | operator must decide deploy-or-remove; `docs/TELEGRAM_BOT_CONSTITUTION.md` Bot 6 section frames the same open question | operator decision |
| TG-09 | KillSwitch (legacy `supervision/kill_switch.py::TelegramKillSwitch`) | `KILLSWITCH_BOT_TOKEN`/`_CHAT_ID` — name only, **never read via `os.getenv` anywhere in source** | same | `supervision/kill_switch.py` | no non-test, non-archive construction call with token credentials was found | **[R1, Correction B — evidence class corrected]** `MODULE_IMPORTABLE_NOT_INSTANTIATED`, not `DEAD_CODE_SOURCE_PROVEN`. `supervision/__init__.py:11-13` imports `TelegramKillSwitch` from this module at package-init time (`from supervision.kill_switch import (TelegramKillSwitch,)`), so any `import supervision` or `import supervision.<anything>` executes this module's top-level code. That top-level code (read in full) contains only an `Enum` and a class definition with no import-time side effects — so importing it has no runtime behavior by itself. Separately, the class itself has no non-test, non-archive construction call supplying token credentials: the only two `TelegramKillSwitch(` hits outside archive are the class's own docstring example and `core/advisor_loop.py:3578`, which constructs the *aliased* `KillSwitchHardened` under the same name (via `core/advisor_runtime_adapters.py:109`) — a distinct class with zero Telegram code. Net: source present, transitively imported, **no non-test, non-archive construction call with token credentials found**, runtime status on the VPS unknown without VPS evidence. | `FORBIDDEN_MUST_NEVER_REACTIVATE` (unchanged) | none — must never be wired to a real token; ADR-0007 forbids any observer-layer component from holding execution authority | none (constitutional prohibition, not a retirement candidate) |
| TG-10 | Narrator | `NARRATOR_BOT_TOKEN`/`_CHAT_ID` — commented out, `.env.secrets.example:92-93` only | same | none — no implementation module, class, entrypoint, instantiation, or call site was found by this mission's searches | none | NONE | n/a | n/a | `NO_IMPLEMENTATION_SOURCE_PROVEN` (see §0 for definition; this identity does not use `DEAD_CODE_SOURCE_PROVEN`, which presumes an implementation exists) | **[R1.4, corrected — Correction A]** `OPERATOR_DECISION_REQUIRED`. No Narrator implementation was found in the reviewed repository sources — but this does not prove no deployed, orphaned, or externally managed process exists, and no VPS or runtime verification was performed during O-02W-E1. `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md:256` quotes a `.env.secrets.example` comment describing an unresolved operational claim: `"Rôle CODE : AUCUN dans main. Module observability/narrator SUPPRIMÉ du disque, process PID 504 vit en mémoire depuis Aug 24 (zombie DS-002 v2). À tuer proprement — ne PAS renseigner de token ici tant que le code n'est pas restauré ou l'ADR 'narrateur retiré' signé."` — i.e. an alleged live/zombie process (PID 504) and an explicitly unsigned retirement ADR. Repository-source absence cannot settle that runtime question or substitute for the named ADR. Formal retirement cannot be authorized until the runtime claim is resolved (out-of-repo, VPS-side) and the required ADR/governance decision is recorded. Cleanup of the two inert comment/config placeholder lines (`.env.secrets.example:92-93`) is secondary housekeeping, conditional on that decision — see follow-up note below, not itself this identity's cutover classification | operator/governance decision: resolve the PID 504 runtime claim and record the "narrateur retiré" ADR before any retirement or cleanup action; comment/configuration placeholder cleanup may follow once that decision is recorded (non-urgent, E2 or later) |
| TG-11 | Internal-only kill switch (`supervision/telegram_kill_switch.py`, name-collides with TG-09's class name but is a distinct, separate implementation) | none — docstring states Telegram polling was removed | none | `supervision/telegram_kill_switch.py` | referenced only by two `tests/phase0/` files and `tools/runtime_tracer.py`; **not imported by `core/advisor_loop.py`**, and not imported by `supervision/__init__.py` either (checked — that file imports only `kill_switch` and `killswitch_hardened`, not `telegram_kill_switch`) | NONE (zero Telegram code; only a programmatic `force_halt()/force_resume()` API) | n/a | n/a | SOURCE_PROVEN (fully unreachable from `supervision/__init__.py` or `core/advisor_loop.py` — unlike TG-09, this one has no package-init import path either) | `OPERATOR_DECISION_REQUIRED` **[R1.1, corrected]** — this file exposes the same `force_halt()/force_resume()` shape as `supervision/killswitch_hardened.py` and has no found caller, which is consistent with (but not proof of) supersession; confirming actual supersession status requires checking historical commit intent, not something this source-only pass can establish with certainty | operator decision (low priority) — confirm superseded status before any removal |

**Total identities: 7 implemented token groups (TG-01 through
TG-06, TG-08) + 1 merged (TG-07 → TG-02's token) + 1 identity with
**no implementation found at all** (TG-10, `NO_IMPLEMENTATION_SOURCE_PROVEN`
— not "dead code," since there is no code, live or dead, to classify;
only configuration/comment placeholders exist) + 1
`MODULE_IMPORTABLE_NOT_INSTANTIATED` identity that is **not**
"dead-code-only" in the unqualified sense (TG-09 — its module is
imported at package-init time; only its class instantiation is absent,
§9 Correction B) + 1 non-Telegram internal component sharing a class
name (TG-11) = 11 rows. [R1.1/R1.2] TG-09 is explicitly excluded from
any "dead-code-only" count or characterization, and TG-10 is
explicitly excluded from any "dead code" characterization — both would
restate exactly the conflations Corrections A and B exist to remove.**

**[R1.1, corrected]** Total production-source Telegram literal
occurrences and call sites: see §6 and §17 for the full bucketed
accounting — **29** raw `api.telegram.org` occurrences outside
archive/test/docs/config, of which **27** (across **23** files)
actually support a request invocation and **2** are confirmed
non-invocation strings (an operator instruction, a log-sanitizer
line). Neither "38" (original) nor "30" (R1) is used in this document
any longer — see §6 for why both undercounted or miscounted the
relevant buckets. `getUpdates` (polling), scoped to non-archive/non-test
`.py` files that implement a polling loop, exists in exactly 5
(TG-01, TG-02, TG-03, TG-08, and TG-09 — TG-09's module is importable
but no non-test, non-archive construction call for its class was
found, per Correction B above).

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
3973-3990) that is then handed to a `CommandCenterBot` object
constructed and started by the same source path (`advisor_loop.py:3991-3992`,
`_portfolio_bot = CommandCenterBot.from_env(_pb_provider);
_portfolio_bot.start()`) — a source-valid construction and `.start()`
call; whether this code path actually executes in a deployed process
is `RUNTIME_UNKNOWN`.

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
into the provider object the `CommandCenterBot` construction path
above passes to its bot instance**, source-reachable whenever that
construction path executes.
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

**[R1.1, Correction D — the fail-closed behavior above applies only to
the *provenance label*, not to the numeric capital value itself.**
`infra/wallet_sync.py`'s actual `get_balance()` chain (lines 166-201)
does **not** return `UNKNOWN` or any undefined value on API failure —
it returns a float, always:

1. Paper mode (line 177): `self._base_capital() + _read_ledger_pnl()`
   — always a concrete number.
2. Live/testnet mode, cached and fresh (line 183-186): returns
   `self._last_value` if a recent fetch succeeded and force-refresh
   isn't requested.
3. Live/testnet mode, fetch attempted and fails (line 189, and the
   `except` path around line 201): calls `self._fallback()`
   (lines 203-206), which returns `self._last_value` if one exists
   from a prior successful fetch, **or** `self._base_capital()`
   (lines 159-164) — which itself returns `self._x` (a bootstrapped
   live balance) if present, **or `_PAPER_CAPITAL`**
   (`WALLET_PAPER_CAPITAL`, line 48) as the final fallback.

**So a live/testnet API failure produces a stale-but-numeric value
(`_last_value`) or the configured paper-capital constant — never an
`UNKNOWN`/`None`/`NaN` that would halt or flag the sizing calculation
that consumes it.** The `"PAPER" | "REAL_API" | "TESTNET_API" |
"UNKNOWN"` domain quoted above is the **Command Center bot's display
provenance label** (`command_center_bot.py:181-183`) — a separate,
presentation-layer classification of *which mode produced the number
being shown to the operator* — and its fail-closed-to-`UNKNOWN`
behavior describes only that label, not the sizing calculation in
`core/advisor_loop.py`, which always receives and uses a concrete
float from `fetch_available_capital()` regardless of whether the
underlying fetch succeeded, used a cache, or fell back to paper
capital.

**Architectural risk this creates, stated explicitly:** a live/testnet
capital path can silently retain a stale `_last_value` (from an
arbitrarily old successful fetch) or silently substitute the
configured paper-capital constant, while still supplying that number
as a live numeric input to `order_size`, `PortfolioBrain`,
`CapitalAllocationEngine`, `ExecutiveOverride`, and the
throttle/drawdown computations listed above — with no `UNKNOWN` state
propagating to halt or flag any of those consumers. This is a
pre-existing architectural design, not created or modified by this
mission's cockpit/Telegram work, and not fixed here — it requires a
dedicated boundary-hardening decision/mission before T-1
certification, separate from this document's Telegram-cutover scope.

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
  behavior — mode-gated by `PAPER_TRADING_ENABLED`/
  `LIVE_TRADING_CONFIRMED`, with the *display provenance label*
  fail-closing to `UNKNOWN` but the *numeric sizing value itself*
  falling back to stale cached data or paper capital rather than
  halting (corrected wording above) — is acceptable as-is or needs a
  dedicated boundary hardening mission.
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
- **[R1.1]** Did not modify `infra/wallet_sync.py`'s fallback chain
  (`_last_value`/`_fallback`/`_base_capital`, §9c), `event_bus/bridge.py`,
  `supervision/ops_watchdog.py`, `supervision/ops_watchdog_hardened.py`
  (§17), or the two broken `TelegramNotifier().send(...)` call sites in
  `quant_hedge_ai/agents/intelligence/self_awareness_engine.py:626` and
  `quant_hedge_ai/agents/execution/position_manager.py:528` (§13) — all
  are documented as source-proven findings requiring a future,
  narrowly scoped source mission before T-1 certification, not fixed
  in this documentation-only PR.

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
   Telegram-triggered — no non-archive, non-test source file calls
   `force_resume()` from any Telegram handler (confirmed: zero call
   sites outside the method's own definition and the unreachable
   `supervision/telegram_kill_switch.py` parallel definition, §9
   TG-11). **[R1.3, own remediation assigned per Correction C]** This
   is a documentation-accuracy defect in an existing repository
   document, not a code defect — its remediation is a narrowly scoped
   **documentation/governance correction** to
   `docs/GLOBAL_STATE_MACHINE.md` (updating the attributed trigger from
   "KillSwitch / Telegram" to the actual programmatic
   `force_safe_mode()`/`force_resume()` callers), not a source-code
   change and not necessarily the same mission as findings 2-4 below.
   Not corrected in this documentation-only PR (out of scope); should
   be corrected **before T-1 deployment/runtime certification** so the
   deployed system's own documentation is accurate.
2. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`** —
   `supervision/exchange_monitor.py:252-257` tells the operator (via an
   email escalation body) to send `/STOP_ALL` on Telegram. No non-test,
   non-archive Telegram poller implements that command against a real
   token — the only implementation (`supervision/kill_switch.py`) is
   `MODULE_IMPORTABLE_NOT_INSTANTIATED` (§9, Correction B): no
   non-test, non-archive dispatcher for this command was found. The instruction is currently non-actionable as written.
   **[R1.3, own remediation assigned per Correction C]** This finding's
   own remediation: **remove or replace the misleading `/STOP_ALL`
   instruction** in that email body, unless a separately authorized
   control-surface design for a real `/STOP_ALL` path is later approved
   through the process described in §13's closing note below (a
   distinct mission, with its own authorization — this document
   neither proposes nor authorizes that design). Not corrected in this
   documentation-only PR; must be corrected before T-1.
3. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` [R1, wording
   corrected R1.2]** — `core/advisor_loop.py` contains three
   operator-facing `/RESUME` instructions with the identical drift
   (one finding, three strings, per §6/§16's unit taxonomy): line 3870
   (degraded-mode alert, "Envoyez /RESUME si intervention requise"),
   line 3878 (halted-mode alert, "Envoyez /RESUME pour reprendre"), and
   line 5576 (the halted-loop wait message itself, "Boucle suspendue
   par Kill Switch. Envoyer /RESUME pour reprendre"). None of these
   are actionable via any Telegram poller this mission found source
   evidence for — `KillSwitchHardened`
   is the class selected/constructed by the canonical source
   construction path for the kill switch (`core/advisor_runtime_adapters.py:109`
   aliases `TelegramKillSwitch = KillSwitchHardened`, instantiated at
   `advisor_loop.py:3578`); whether that construction path actually
   runs in a deployed process is `RUNTIME_UNKNOWN`. `KillSwitchHardened`'s
   source contains zero Telegram code (confirmed by grep,
   §9/§13 item 1), and `force_resume()` has zero call sites outside its
   own definition — so **even if** the containing process is running,
   no code path connects a Telegram command to `force_resume()`.
   **These three messages have a source-valid delivery-attempt path**
   — each is passed to `advisor_loop.py`'s own `_telegram`/
   `_telegram_behavior` senders (§9a, TG-06), which attempt an HTTP
   `sendMessage` request only when the containing process is running
   and `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (or
   `TELEGRAM_BEHAVIOR_CHAT_ID`) are configured; missing configuration,
   test-mode suppression (`PYTEST_CURRENT_TEST`), HTTP failure, or a
   non-200 response would each independently prevent successful
   delivery, none of which this source-only review can rule in or out.
   Whether any operator has actually received any of these three
   messages in production is `RUNTIME_UNKNOWN`. What is
   `SOURCE_PROVEN` is narrower: the message-construction and
   send-attempt code path exists and is reached whenever the
   triggering degraded/halted condition fires in a running process;
   what is broken, independent of delivery, is that the command named
   in the instruction (`/RESUME`) has no dispatcher this mission found
   on any non-test, non-archive Telegram source path, even if the
   message is received. **[R1.3, own remediation assigned per
   Correction C]** This finding's own remediation: **remove or replace
   only these three misleading `/RESUME` instructions** in
   `core/advisor_loop.py`; this is a distinct fix from finding 2's
   `/STOP_ALL` instruction (different file, different message family)
   and from finding 4's broken notifier call (below) — grouping any of
   the three findings' remediations together would misstate that they
   share a fix, not merely a root symptom (an unwired Telegram resume
   path).
4. **`SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT`
   /
   `SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL` [R1.1, new;
   corrected R1.2]** —
   `quant_hedge_ai/agents/intelligence/self_awareness_engine.py:623-631`
   (`_send_telegram_critical()`) constructs a fourth operator-facing
   `/RESUME` string, separate from and in addition to the three
   `core/advisor_loop.py` strings in item 3: `"SELF-AWARENESS
   CRITIQUE\nTrading suspendu 24h — dérives détectées:\n{msgs}\nEnvoyer
   /RESUME pour reprendre manuellement."`. This one differs in kind
   from item 3's three strings: the call site is
   `TelegramNotifier().send(...)` (line 626), which supplies **zero
   constructor arguments** to a class whose `__init__` requires
   `bot_token` and `chat_id` (`supervision/notifications/telegram_notifier.py:16-18`),
   and calls `.send(...)`, a method that **does not exist** on that
   class (the real method is `.notify(message)`, beginning at line 20
   of the same file). **If** this expression is reached at runtime
   (i.e., the containing process is running and the CRITICAL-drift
   trigger fires), it deterministically raises a `TypeError` on
   construction before any HTTP request is attempted, caught and
   discarded by the enclosing `except Exception: pass` (line 632).
   Whether this expression is ever reached in production is
   `RUNTIME_UNKNOWN` — this document does not claim the trigger has
   occurred or that a message was ever "not delivered" in a specific
   past instance, only that the expression cannot succeed as written
   whenever it is reached. This is a source-proven-nonfunctional broken
   call expression carrying a `/RESUME` instruction; it is **one of
   two** such broken call expressions found (the second, below, carries
   no `/RESUME` text). A second, structurally identical broken call
   expression exists at
   `quant_hedge_ai/agents/execution/position_manager.py:528`
   (`_check_liquidation_defense()`, a liquidation-distance warning, not
   itself carrying a `/RESUME` instruction but sharing the exact same
   `TelegramNotifier().send(...)` defect) — recorded here as the same
   class of finding, distinct message family, and **not counted** among
   the 5 misleading operator-facing command strings (it carries no
   command instruction of its own) — see the unit taxonomy below.
   **[R1.3, own remediation assigned per Correction C]** This finding's
   own remediation is decided **separately** from findings 1-3: for the
   SelfAwareness broken call (and, independently, for the
   structurally-identical PositionManager broken call), a future
   mission must decide among removing the notification, routing it
   through an already-approved notification facade, or repairing the
   call through a governed identity/configuration path — not
   necessarily the same choice, and not necessarily the same mission,
   as finding 3's `/RESUME`-instruction removal/replacement.
5. `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`'s description of an "ÉLEVÉ"
   risk `RADAR_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN` fallback is stale
   (current `scripts/radar_bot.py` has no such fallback) — but this is
   already self-acknowledged by `TELEGRAM_IDENTITY_REGISTRY.md`'s own
   before/after note, so it is a reconfirmation, not a new
   contradiction, and not safety-relevant (no operator instruction is
   involved).
6. `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`'s absolute
   line-number citations for the Real Account Bot in
   `core/advisor_loop.py` have drifted (code moved, not changed in
   behavior) — corrected in this document's §1/§9, not safety-relevant.

**[R1.2, explicit unit taxonomy — do not use these units
interchangeably; R1.4, Correction E — items numbered explicitly]**

- **4 numbered safety-relevant findings** — **items 1-4 of the
  six-entry numbered list above** (items 5-6 are explicitly *not*
  safety-relevant, as their own text states): (1) the historical
  `GLOBAL_STATE_MACHINE.md` contradiction, (2) one `/STOP_ALL`
  operator-facing string, (3) three `core/advisor_loop.py` `/RESUME`
  operator-facing strings sharing one root cause and one remediation,
  (4) one SelfAwareness `/RESUME` operator-facing string carried by a
  broken notifier call expression.
- **5 misleading operator-facing command strings** across those
  findings: 1 × `/STOP_ALL` (finding 2) + 4 × `/RESUME` (3 from finding
  3, 1 from finding 4).
- **2 source-proven nonfunctional notifier call expressions**
  (`SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL`, §0): the
  SelfAwareness call (finding 4, carries a `/RESUME` string) and the
  PositionManager call (`position_manager.py:528`, carries no `/RESUME`
  string — a liquidation-distance warning only). **Only one of these
  two broken call expressions contains a `/RESUME` instruction.**

These three counts (4 findings, 5 strings, 2 broken calls) are not
interchangeable and must not be summarized as "five items" without
specifying which unit.

**[R1.3, per-finding remediation, Correction C]** All four findings
must be corrected before T-1 deployment/runtime certification, but
they do **not** necessarily share one mission, one fix, or one
timeline — each is assigned its own remediation above and restated
here for clarity:

- **Finding 1** (`GLOBAL_STATE_MACHINE.md` contradiction): a narrowly
  scoped **documentation/governance correction** — update the
  attributed trigger to the actual programmatic caller. Not a source
  code change.
- **Finding 2** (`/STOP_ALL` string): **remove or replace** the
  misleading instruction in `supervision/exchange_monitor.py`, unless
  a separately authorized control-surface design for a real
  `/STOP_ALL` path is later approved (see the closing rule below — such
  a design is not proposed or authorized by this contract).
- **Finding 3** (three `core/advisor_loop.py` `/RESUME` strings):
  **remove or replace** only these three misleading instructions — a
  fix distinct from finding 2's.
- **Finding 4** (broken SelfAwareness notifier call, and separately
  the structurally-identical PositionManager call): **this document
  does not prescribe a single specific repair.** A separately
  authorized source mission must decide, for each of the two broken
  call expressions independently, among (a) removing the notification
  entirely, (b) routing it through an already-approved notification
  identity/facade (e.g. the existing `OpsNotifier`/generic
  `TELEGRAM_BOT_TOKEN` channel, if that routing is itself approved), or
  (c) repairing the call through an explicitly governed identity and
  configuration path. **This contract does not authorize creating,
  copying, exposing, or wiring any Telegram secret/token/chat-id value
  to implement any of these options** — that decision and its
  implementation are out of scope for this documentation-only mission.

**[R1.3, closing rule, Correction D]** Removing or rewording a
misleading operator instruction (findings 2 and 3) is the **safe
default** and requires no new authorization beyond the narrowly scoped
correction mission each finding names above. **Implementing any
Telegram command that changes runtime state — including a live
`/RESUME` or `/STOP_ALL` handler — is *not* authorized by O-02W-E1 or
any of its remediation rounds.** Such a control surface, if ever
proposed, would require a separate mission with its own explicit
MASTER authorization, an ADR/authority-boundary review consistent with
ADR-0007, a security review, authentication/replay/audit requirements,
and dedicated tests — none of which this contract performs or
substitutes for. The read-only cockpit (§8) remains control-free and
this document proposes no change to that. `supervision/kill_switch.py`'s
`TelegramKillSwitch` (TG-09, §9) must never be reactivated — see its
`FORBIDDEN_MUST_NEVER_REACTIVATE` classification, unchanged by any
remediation round. This document does not choose among the options
listed above for any finding and does not modify runtime code to
implement any of them.

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
  **[R1.2]** now unused by any row in this document — TG-10 (Narrator)
  uses `NO_IMPLEMENTATION_SOURCE_PROVEN` instead (no module exists at
  all, which is a distinct fact from "implementation exists but is
  unreachable"); TG-09 (legacy KillSwitch) reclassified
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
  (`MODULE_IMPORTABLE_NOT_INSTANTIATED`), and runtime/deployment status
  (`RUNTIME_UNKNOWN` in every case). **[R1.3, Correction B — rule
  stated explicitly]** A named repository entrypoint, import chain,
  construction site, call site, or systemd `ExecStart=` reference
  proves only source or configuration reachability. **None of these
  prove deployment, process execution, trigger occurrence, configured
  credentials, network success, or message delivery** — those remain
  `RUNTIME_UNKNOWN` throughout this document unless independent VPS
  evidence (out of scope for this mission) is obtained. A systemd
  reference is never presented anywhere in this document as sufficient
  proof that the referenced process is actually running.
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
  in §9a (**[R1.1, corrected]** 10 message-family rows total across
  TG-02/03/06/07 — TG-02a/b/c, TG-03a/b, TG-06a/b/c/d, TG-07 —
  replacing the original 3 composite `mixed:` cells; the earlier draft
  of this summary miscounted this as 24, which is corrected here to
  the actual, mechanically-verifiable row count in §9a).
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
  — package-init-importable, no non-test, non-archive construction
  call supplying token credentials found, not "unreachable" in the
  unqualified sense the original text used)
  and TG-02c (the currently-inert blocked-command set that would
  activate `_set_param_live` if ever unblocked, §9b).
- **[R1.2, explicit unit taxonomy — see §13 for full detail]** Four
  numbered `SAFETY_RELEVANT_OPERATOR_INSTRUCTION_DRIFT` findings —
  items 1-4 of §13's six-entry numbered list (items 5-6 are not
  safety-relevant): (1)
  the historical `GLOBAL_STATE_MACHINE.md` contradiction, (2) the
  `/STOP_ALL` instruction in `supervision/exchange_monitor.py`, (3)
  three `/RESUME` instructions in `core/advisor_loop.py` (source-valid
  delivery-attempt path, but non-actionable — no dispatcher found for
  the named command on the reviewed canonical source path), (4) one
  `/RESUME` instruction in
  `self_awareness_engine.py`'s critical-halt notifier, carried by a
  `SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL`. Counted a different
  way: **5 misleading operator-facing command strings** (1 `/STOP_ALL`
  + 4 `/RESUME`) and **2 source-proven nonfunctional notifier call
  expressions** (SelfAwareness, carrying a `/RESUME` string; and
  PositionManager, carrying no `/RESUME` string — a
  liquidation-distance warning only). These three counts are distinct
  and must not be used interchangeably. **[R1.3, corrected]** All four
  findings must be corrected before T-1 deployment/runtime
  certification, but not necessarily by the same mission: finding 1 is
  a documentation/governance correction; findings 2 and 3 are each a
  remove-or-replace fix to a misleading operator-facing string;
  finding 4 requires a separate decision (remove, route through an
  approved facade, or governed repair) for each of its two broken call
  expressions. See §13 for the per-finding remediation.
- **[R1, new]** Two architectural-boundary items requiring a future
  source mission, neither modified by this documentation-only PR: the
  dormant Portfolio mutator (§9b, `_set_param_live`) and the
  real-capital sizing/risk feed (§9c, Flow 2 — **[R1.1]** now
  precisely described as falling back to stale cached data or paper
  capital, never to an `UNKNOWN` numeric value, only the display
  provenance label fail-closes).
- **[R1.1, new]** Three files reclassified from "not Telegram-capable"
  to indirect-Telegram-capable via `OpsNotifier`/`TelegramNotifier`
  (§17, Correction B): `event_bus/bridge.py`, `supervision/ops_watchdog.py`,
  `supervision/ops_watchdog_hardened.py` — none has a non-test,
  non-archive caller found with a construction call using
  `.from_env()`; `event_bus/bridge.py`'s one found caller
  (`quant_hedge_ai/main_v91.py:211`) constructs `SupervisionBridge()`
  without a notifier, i.e. Telegram-disabled on that specific path.

---

## 17. Non-archive Telegram-capable source-file inventory (Correction A)

**[R1, new section]** Complete accounting of the 18 files named in the
O-02W-E1-R1 mission mandate, plus the previously-covered identity
files for cross-reference. **[R1.3, bounded terminology]** "Reachable"
means: a non-test, non-archive `import` statement, instantiation, or
call site was found in `core/advisor_loop.py`, `paper_runner.py`, or a
named repository entrypoint; or a systemd unit reference (`ExecStart=`)
naming the file is present in the repository. None of these prove
deployment, process execution, or that the code has ever run —
absence of a systemd unit or caller does **not** prove the file never
runs (it could be invoked manually or by a scheduler this mission's
searches did not find), and *presence* of a systemd unit or import
site proves only source/configuration reachability, not that the
corresponding process is deployed, running, or has ever executed. This
mission's searches finding no such reference means `RUNTIME_UNKNOWN`
for that file, never a "dead" or "definitely running" claim either
way.

**[R1.1]** Speculative labels used in the R1 draft of this table
("likely dead," "likely a stale duplicate," "reachable via an active
import chain," "already-active entrypoint") are replaced below with
bounded source statements: a systemd/caller search either found a
reference or did not; import reachability is stated as a fact about
the import graph, not as a judgment about whether the code "is" dead;
manual/debug scripts default to `OPERATOR_DECISION_REQUIRED` rather
than `DEAD_CODE_REMOVAL_CANDIDATE` unless this mission found a
specific, positive reason (e.g. a superseding replacement, or an
explicit "removed"/"deprecated" marker in source) to believe removal
is safe.

| File | Identity/token group | Role | Capability | Message family | Reachability evidence | Runtime evidence | Cutover classification |
|---|---|---|---|---|---|---|---|
| `S3/01_telegram_alerts.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Generic ops alert (standalone S3 provisioning script) | Systemd search: no `ExecStart=` match found. Import search: not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `infra/monitoring/watchdog_vps.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | VPS liveness alert | Systemd search: the file actually referenced by `crypto-watchdog.service`'s `ExecStart=...python3 watchdog_vps.py` (`WorkingDirectory=` the repo root) resolves to the **root-level** `watchdog_vps.py`, a separate file with divergent content (confirmed by diff) — no systemd unit's `ExecStart=` names `infra/monitoring/watchdog_vps.py` specifically | RUNTIME_UNKNOWN — source caller not found for this specific file; the naming collision with the wired root file is a distinct, source-proven fact, not a judgment about which is "real" | `OPERATOR_DECISION_REQUIRED` — operator should confirm which of the two files is authoritative before either is edited or removed |
| `infra/notifications/notify_test_status.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | CI/test-run status notification | Systemd/CI-workflow search: no reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `observation/market_radar.py` | `RAPPORT_AUTOMATIQUE_BOT_TOKEN`/`_CHAT_ID` (gated by `RADAR_TELEGRAM_DIGEST`, default off) | Sender-only, opt-in digest | PUSH_ONLY (disabled by default) | Optional market-radar digest via the Rapport Automatique channel | Systemd search: `scripts/systemd/crypto-market-radar.service` `ExecStart=...python observation/market_radar.py --run` — reference found | SOURCE_PROVEN (code + systemd reference); RUNTIME_UNKNOWN whether the service/flag are actually enabled on the VPS | `KEEP_RESEARCH_INTERFACE` if enabled — separate from CryptoRadar (TG-01), shares TG-04's token |
| `scripts/daily_signal_report.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Daily signal-summary report | Systemd/cron search: no reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/data_verifier.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Data-integrity verification alert | Systemd/cron search: no reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/quant_observer_pin_bootstrap.py` | `QUANT_CRYPTO_BOT_TOKEN`/`_CHAT_ID` | One-shot bootstrap sender | PUSH_ONLY (one-shot) | Creates/pins the placeholder message TG-03 then edits | Systemd search: referenced only as a **commented-out** manual step in `scripts/systemd/crypto-quant-observer.service:13` | RUNTIME_UNKNOWN — source states this is a manual operator tool, not evidence either way of use | `OPERATOR_DECISION_REQUIRED` (operator bootstrap utility for TG-03 — a manual/debug script is not automatically a removal candidate) |
| `scripts/test_intel_report.py` | `RAPPORT_AUTOMATIQUE_BOT_TOKEN`/`_CHAT_ID` | Sender-only test/debug script | PUSH_ONLY | Manual test of the Intel-briefing message format | Systemd/cron search: no reference found | RUNTIME_UNKNOWN | **[R1.1, corrected]** `OPERATOR_DECISION_REQUIRED` — this mission found no systemd/cron reference, which is not by itself proof the script is unreachable or safe to remove; a manual/debug script's actual continued utility is an operator judgment, not a source-provable fact |
| `scripts/trend_scanner.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Trend-scan alert | Systemd/cron search: no reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `scripts/vps_burn_in_collector.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only script | PUSH_ONLY | Burn-in metrics collection warning | Systemd/cron search: no reference found | RUNTIME_UNKNOWN | `OPERATOR_DECISION_REQUIRED` |
| `src/telegram/notifier.py` | `MON_PORTFOLIO_BOT_TOKEN`/`_CHAT_ID` | Library/notifier module | Library-only | Generic `Notifier` wrapping `sendMessage` for the Portfolio token | Import search: imported by `src/telegram/__init__.py:1` and `src/telegram/sim_bot.py:36` (TG-08). No import found from `core/advisor_loop.py`, `capital_deployment/command_center_bot.py`, or `src/telegram/quant_observer/bot.py` | RUNTIME_UNKNOWN — TG-08 itself has no non-test, non-archive source caller or systemd reference found (§9 TG-08), so this file's only found import path is, in turn, one this mission cannot confirm executes in any deployed process | `OPERATOR_DECISION_REQUIRED` — tied to the same TG-08 deploy-or-remove decision (§9 TG-08), not independently a removal candidate |
| `supervision/notifications/telegram_notifier.py` | token/chat passed by caller (no module-level constant); `__init__(self, bot_token, chat_id)` at lines 16-18, `.notify(message)` begins line 20 | Library/notifier module | Library-only | Thin `TelegramNotifier.notify()` wrapper | Import search: imported by `quant_hedge_ai/agents/intelligence/self_awareness_engine.py:623` and `quant_hedge_ai/agents/execution/position_manager.py:526`, both constructed from `core/advisor_loop.py` via `core/advisor_runtime_adapters.py` by a source-valid construction path (`SelfAwarenessEngine` used at `advisor_loop.py:4484`; `PositionManager` used at `advisor_loop.py:4055-4056,4180`) | SOURCE_PROVEN: the import statement is on a code path that executes whenever the importing module is imported. **[R1.1, Correction C; wording corrected R1.2]** However, **both actual call sites are `SOURCE_PROVEN_NONFUNCTIONAL_NOTIFICATION_CALL`** (§0): `self_awareness_engine.py:626` and `position_manager.py:528` both call `TelegramNotifier().send(...)` — zero constructor arguments against the `__init__(self, bot_token, chat_id)` signature above, and `.send()`, a method that does not exist on this class (the real method is `.notify(message)`, above). **If** reached at runtime, each deterministically raises before any HTTP request, caught by an enclosing `except Exception: pass`; whether either is ever reached in a deployed, triggering process is `RUNTIME_UNKNOWN`. The module/class itself is not broken — only these two specific call expressions are | `OPERATOR_DECISION_REQUIRED` — a separately authorized source mission must decide, for each call site, among removing the notification, routing it through an already-approved notification identity/facade, or repairing the call through an explicitly governed identity/configuration path; this contract does not authorize creating, copying, exposing, or wiring any Telegram secret to implement any of these options, and does not itself prescribe which option to take |
| `supervision/self_healing_bot.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | Sender-only module | PUSH_ONLY | Self-healing/module-recovery alert | Import search: `core/advisor_runtime_adapters.py:111` imports `SelfHealingBot`, instantiated at `advisor_loop.py:3623-3624`, started at `advisor_loop.py:3686` — source caller found | SOURCE_PROVEN (code + source caller found); RUNTIME_UNKNOWN whether `crypto-advisor.service` is running on the VPS | `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED` — same TG-06-class treatment; should be folded into TG-06's Phase 2 comparison as an additional message source |
| `core/orchestration/orchestrate_ecosystem.py` | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (via `TelegramNotifier`) | Orchestration script | Library-caller, PUSH_ONLY when invoked | Multi-world-simulation run-and-archive notification | Systemd search: no unit found. Import search: not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN — no source caller found; this mission draws no conclusion beyond that absence | `OPERATOR_DECISION_REQUIRED` |
| `infra/monitoring/supervise_all.py` | `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` (note: **different env-var name**, `TELEGRAM_TOKEN` not `TELEGRAM_BOT_TOKEN`, with hardcoded placeholder defaults) | Standalone supervision loop | Library-caller, PUSH_ONLY when invoked with real values | BotDoctor health-score alert | Systemd search: no unit found. Import search: not imported by `advisor_loop.py`/`paper_runner.py` | RUNTIME_UNKNOWN — no source caller found | `OPERATOR_DECISION_REQUIRED`; flag the env-var name mismatch as a separate minor finding — even a fully-configured `.env` would not populate this file's default token path, since it reads a different variable name than every other identity in §9 |
| `event_bus/bridge.py` | none directly — **[R1.1, Correction B, reclassified]** indirect via `OpsNotifier` → `supervision/notifications/telegram_notifier.py::TelegramNotifier` | Bridge/integration module, not a direct sender | Indirect Telegram-capable: `SupervisionBridge.from_env()` (lines 85-94) constructs `OpsNotifier.from_env()`; `_notify()` (line 300) calls `self._notifier.info(...)`, reached from at least 10 internal call sites (lines 122, 136, 151, 166, 184, 204, 218, 230, 258, 269) | Various supervision-event notifications (crash, rejection, halt, etc. — not independently itemized in this pass) | Import/caller search: the only found instantiation site, `quant_hedge_ai/main_v91.py:211`, calls `SupervisionBridge()` with **no arguments** — not `.from_env()` — so that specific path constructs the bridge **without** a notifier (Telegram-disabled on that path, confirmed by the constructor default). No caller of `SupervisionBridge.from_env()` was found in non-archive, non-test source | RUNTIME_UNKNOWN for whether any caller ever uses `.from_env()` in production; the one found caller is confirmed Telegram-disabled | `OPERATOR_DECISION_REQUIRED` — not "not applicable," since indirect Telegram capability is real even though the one found caller doesn't exercise it |
| `supervision/ops_watchdog.py` | none directly — indirect via `OpsNotifier` → `TelegramNotifier` | Standalone supervision loop | Indirect Telegram-capable: `OpsWatchdog.from_env()` (lines 48-52) constructs `OpsNotifier.from_env()`; its crash/rejection/session-halt/staleness/heartbeat paths can call the notifier | Crash/rejection/halt/staleness/heartbeat notifications (not independently itemized) | Systemd search: no unit found. Import search: no caller of `OpsWatchdog.from_env()` or `OpsWatchdog()` found in non-archive, non-test source | RUNTIME_UNKNOWN — no non-test, non-archive construction call found | `OPERATOR_DECISION_REQUIRED` — indirect-capable, no non-test/non-archive caller or systemd reference found; not "not applicable" |
| `supervision/ops_watchdog_hardened.py` | none directly — indirect via `OpsNotifier` → `TelegramNotifier` | Standalone supervision loop (hardened variant) | Indirect Telegram-capable: `HardenedOpsWatchdog.from_env()` (lines 116-121) constructs `OpsNotifier.from_env()` and creates an alert callback | Hardened-watchdog alert notifications (not independently itemized) | Systemd search: no unit found. Import search: no caller of `HardenedOpsWatchdog.from_env()` or `HardenedOpsWatchdog()` found in non-archive, non-test source | RUNTIME_UNKNOWN — no non-test, non-archive construction call found | `OPERATOR_DECISION_REQUIRED` — indirect-capable, no non-test/non-archive caller or systemd reference found; not "not applicable" |

**Intermediary integration nodes** (not independently in the 18-file
mandate, but required context for the three rows above, per
Correction B; both read in full for R1.2, Correction E):

- `supervision/notifications/ops_notifier.py` — `OpsNotifier.from_env()`
  reads `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` and wraps
  `TelegramNotifier`, rate-limited per event type — already covered in
  this document's earlier text as part of the generic-alerts family.
- `infra/notifications/notifications.py` — a separate,
  facade-style notification module, fully read for this remediation.
  It defines: `_build_notifier()` (reads `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` via `os.getenv`; when both are non-empty after
  stripping whitespace, constructs a `TelegramNotifier(token, chat)`
  and adds it to a `MultiNotifier`, also conditionally adding a
  `SlackNotifier` if `SLACK_WEBHOOK_URL` is set); the module-level
  statement `NOTIFIER = _build_notifier()`, which **executes at
  import time** — i.e., merely importing this module runs
  `_build_notifier()`, though with no token configured it constructs
  an empty `MultiNotifier` and performs no network call; `send_alert(message)`,
  a synchronous shortcut calling `NOTIFIER.notify(message)`; and
  `TelegramBotAdapter`, a class whose `__init__` conditionally
  constructs its own `TelegramNotifier` instance (same env-var gate),
  exposing an `active` property and an async `send_message()` that
  calls `self._notifier.notify(text)` when active, with
  `build_telegram_bot()` as its factory function. A repository-wide
  import/reference search (`git grep` for
  `infra.notifications.notifications`, `from infra.notifications.notifications
  import`) at R1 starting HEAD `d702b7f2a06c59eb1972de3026afd317cf70d314`
  found **no importer or caller of this module outside the module
  itself, `_ARCHIVE_2026/`, and `tests/`** — i.e., no non-test,
  non-archive source file imports or calls `send_alert()`,
  `build_telegram_bot()`, or `NOTIFIER` from this module. **Therefore:
  this module's Telegram-sending capability is `SOURCE_PROVEN` at
  import time (the `NOTIFIER` construction always runs on import,
  conditionally arming a real sender if configured), but its actual
  deployed/runtime use — whether anything in the running system
  imports and calls it — is `RUNTIME_UNKNOWN`, since this mission
  found no caller to evaluate in the first place.**

**[R1.2] Scope boundary, stated explicitly:** the 18-row table above
is the mandated file-by-file review required by the O-02W-E1-R1/R1.1/R1.2
mission instructions, and the two intermediary nodes immediately above
were read in full for R1.2. Together these are **not** presented as a
complete inventory of every file in the repository with *transitive*
Telegram capability via `OpsNotifier`/`TelegramNotifier` — a caller of
`OpsNotifier.from_env()` or of `infra.notifications.notifications`
elsewhere in the repository that this mission's specific searches
missed cannot be ruled out. Completeness is claimed only for: the
mandated 18 files, the identity-bearing files already covered in
§9/§9a, and the two intermediary nodes read in full above — not for an
exhaustively audited full transitive graph beyond those.

**Scope-separated repository totals** (Correction A, restated from
§6, all counted at R1 starting HEAD `d702b7f2a06c59eb1972de3026afd317cf70d314`):
`api.telegram.org` — 42 total, 4 archive, 6 test, 2 docs, 1 config,
**29 remaining source/script occurrences** (27 of which, across 23
files, support an actual request invocation — see §6 for the two
excluded non-invocation strings), spread across the files above plus
the identity-bearing files already in §9: `scripts/radar_bot.py`,
`capital_deployment/command_center_bot.py`,
`src/telegram/quant_observer/bot.py`, `src/telegram/bot_runner.py`,
`src/telegram/sim_bot.py`, `src/paper/paper_report.py`,
`supervision/exchange_monitor.py`, `supervision/performance_watchdog.py`,
`supervision/kill_switch.py`, `scripts/telegram_alerts.py`,
`core/advisor_loop.py`, root `watchdog_vps.py`. `getUpdates` — 87
total (case-insensitive), scoped production-source **file** count
exactly 5 (§6, §9).

Three of the 18 named files (`event_bus/bridge.py`,
`supervision/ops_watchdog.py`, `supervision/ops_watchdog_hardened.py`)
contain **no direct** Telegram API literal (`api.telegram.org`,
`sendMessage`, `getUpdates`, etc.) — but **do** have indirect Telegram
capability through the `OpsNotifier`/`TelegramNotifier` chain, per
Correction B above. **[R1.1]** These three are correctly excludable
from the direct-literal counts in §6 (they contribute zero to the
`api.telegram.org`/`getUpdates` raw occurrence totals), but must
**not** be described as "not Telegram-capable" — that characterization
was itself the evidence-quality defect Correction B exists to fix.
Including all three in the mission's audit scope, and correctly
describing their indirect capability rather than silently dropping
them or mislabeling them, is itself part of what Corrections A and B
require.

---

O02WE1_R1_IMPLEMENTATION_COMPLETE_MASTER_REVIEW_REQUIRED
