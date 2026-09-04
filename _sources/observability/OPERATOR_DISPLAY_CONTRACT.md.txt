# Operator Display Contract

Mission O-01 · Rules for all future operator interfaces (Telegram,
dashboards, APIs, reports). These rules bind O-02 and any later
presentation adapter; O-01 itself implements none of them — it defines
the contract the adapters must follow.

## The 14 rules

1. **The presentation layer does not recalculate canonical metrics.** A
   percentage, ratio, or status shown to the operator must come from a
   `MetricDefinition`/domain snapshot field, never from ad hoc arithmetic
   in the rendering code. (Forensic counter-example already in the
   codebase: `sim_bot.py`'s `_cmd_compare`/`_cmd_race`/`_cmd_validate`
   each reimplement profit-factor/expectancy aggregation instead of using
   the shared `performance_breakdown.breakdown()` that other commands in
   the same file use — exactly the drift this rule prevents.)
2. **Every displayed metric maps to a `metric_id`.** If a number has no
   entry in `METRIC_DICTIONARY.md`, it does not get displayed until one
   exists — or it is displayed clearly marked `SOURCE_UNRESOLVED`.
3. **Timestamps and freshness are explicit.** Every value with a
   `DatasetFreshness`/domain `freshness` field must render that
   freshness alongside the value — never the number alone.
4. **Unavailable data != zero.** `NullSemantics.UNAVAILABLE`/`UNKNOWN`
   must render as "indisponible"/"inconnu", never as `0` or a blank that
   reads as zero.
5. **Stale data != healthy data.** A `FreshnessStatus.STALE` or
   `DEGRADED` value must carry a visible marker even if the underlying
   number looks fine — a green checkmark is never paired with a stale
   timestamp.
6. **Paper != real.** Any figure sourced from `portfolio_state.paper_*`
   must be visually and textually distinguished from
   `portfolio_state.real_account_*` — never adjacent without a label,
   never summed. This preserves the existing guardrail in
   `observability/real_accounts.py` (see `OPERATOR_OBSERVABILITY_
   ARCHITECTURE.md` §10) and directly targets the `/kpis` ambiguity found
   in `TELEGRAM_BOT_REGISTRY.md`.
7. **Recommendation != applied action.** POST-S02B.1 (PR #111), the
   RECOMMENDED vs APPLIED split is real and code-enforced for
   mistake_memory/strategy_memory/meta_learner/strategy_ranker: whether a
   recommendation is applied to a live decision is governed by
   `config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK` (default
   False, fail-closed), independent of learning/observation which stay
   active unconditionally. `adaptive_learning.recommendation_count`/
   `applied_count` themselves remain `FUTURE_PROVIDER` (S02_PROVENANCE_DEBT
   — no dedicated per-recommendation counter exists yet in the protected
   modules); an adapter must never collapse the two into one figure once
   a counter surface exists, and must not imply today's absence of a
   *counter* means the underlying RECOMMENDED/APPLIED distinction itself
   does not exist — it does, at the flag level (mission §14, reconciled
   O-01R).
8. **Process alive != scientific health.** `system_health.boot_alive`
   and `system_health.health_score` must always render as two distinct
   signals — a green "process alive" indicator must never stand in for
   scientific health.
9. **Regret `MISSED_WIN` != missed executable profit.** Any rendering of
   `regret_state` MISSED_WIN counts must carry the scientific caveat
   from `METRIC_DICTIONARY.md`
   (`regret_state.missed_win_semantic_caveat`) — no guaranteed fill,
   slippage, or risk constraint is implied.
10. **Percentages require an explicit denominator.** Every rendered
    percentage must show or link to its `numerator_label`/
    `denominator_label` (`PercentageMetric`) — never a bare "3% refus".
    (Forensic example this rule targets:
    `visualization/decision_trace_service.py`'s `by_layer_pct` is
    denominated over rejection records only, not all evaluated
    signals — an adapter must say which.)
11. **No opaque global score without a documented formula.** Any
    composite (e.g. `system_health.health_score`) must link to its
    documented weighting (`observability/health_score.py`'s 25/25/20/
    20/10 breakdown) rather than being shown as an unexplained number.
    `OperatorSummary.status` is intentionally `OK`/`ATTENTION_REQUIRED`
    plus named `attention_items` — never a single blended score.
12. **French labels use the Metric Dictionary.** `operator_label_fr` is
    the only source of French wording for a metric — an adapter must not
    invent its own translation.
13. **Severity status originates from canonical rules, not emoji
    choice.** A 🔴/🟡/🟢 (or equivalent) must be derived from the
    snapshot's own `status`/`freshness` fields — never chosen
    independently by the rendering code based on vibes. `status` is a
    closed vocabulary (`contracts.DOMAIN_STATUSES`:
    `OK`/`DEGRADED`/`ATTENTION_REQUIRED`/`UNAVAILABLE`), enforced by
    `DomainSnapshot.__post_init__` — an adapter must not invent a
    healthy-looking status string outside this set, and must not treat
    any member other than `OK` as healthy.
14. **Presentation adapters may format, never reinterpret.** Rounding,
    unit conversion (e.g. bytes -> GB), and locale formatting are
    allowed; changing what a value *means* (e.g. treating `DEGRADED` as
    `FRESH` because "it's probably fine") is not. This applies to
    aggregation too: `OperatorSummary`'s freshness aggregation is an
    explicit severity order (`UNKNOWN > STALE > DEGRADED > FRESH`,
    `NOT_APPLICABLE` excluded from the ordering rather than degrading a
    result) — an adapter composing multiple snapshots must use the same
    precedence, never a shortcut that can silently collapse a degraded
    component into an all-clear.

## Quant Observer O-02 migration contract

Documented here as the already-approved downstream requirement for
`@QuantCrpto_bot` — **not implemented by O-01**:

- One single LIVE message.
- Continuously edit the same message (matches the bot's existing
  change-driven fingerprint mechanism, `bot.py::_change_driven_live_tick`
  — O-02 should extend this pattern, not replace it).
- The message must **not** remain pinned — remove the current pin
  behavior (`scripts/quant_observer_pin_bootstrap.py`).
- Do **not** delete historical messages.
- User-facing labels in French, sourced from `METRIC_DICTIONARY.md`.
- Metrics must be understandable to the operator — replace raw technical
  English with defined French labels and, where useful, a one-line
  definition or link to the dictionary entry.
- Metric definitions must come from the O-01 Metric Dictionary — no
  bot-local redefinition.
- No duplicated computation — every value the panel shows must trace to
  a canonical domain snapshot field, not to bot-side arithmetic.

## Non-goals of this document

This contract does not implement a Telegram sender, a dashboard, or an
API. It does not modify `src/telegram/quant_observer/` or any Telegram
runtime code. It binds whoever builds those next (O-02+).
