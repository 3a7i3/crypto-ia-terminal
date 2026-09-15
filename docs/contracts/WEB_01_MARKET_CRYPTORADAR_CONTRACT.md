# WEB-01 — MARKET / CryptoRadar Read-Only Bridge Contract

Status: `IMPLEMENTATION_CONTRACT`

Mission: `WEB-01-MARKET`

Base SHA: `8798ad7a983bc6e949ea160619ec9a3ddb6c3f94`

Authority: `OBSERVATIONAL_TELEMETRY` only

## 1. Purpose

Expose the existing CryptoRadar market-discovery product in the read-only
Operator Web App without turning the web stack into a second market engine and
without granting any execution authority to CryptoRadar.

This contract closes the current `NOT_EXPOSED` Market tab while preserving the
O-02W-B §12 MARKET boundary:

```text
DecisionPacket JSONL (existing evidence)
        |
        v
CryptoRadar calculation (existing radar_bot functions)
        |
        v
atomic cryptoradar_market_snapshot.json
        |
        v
Operator API GET /api/operator/v1/market
        |
        v
React MarketView
```

There is no reverse edge.

## 2. Constitutional boundary

The bridge MUST remain read-only and observational.

It MUST NOT:

- call an exchange;
- read exchange/API credentials;
- instantiate or import execution/risk/portfolio authority;
- mutate DecisionPackets or any ledger;
- call `analyze_symbol()`;
- send/edit/delete Telegram messages;
- expose Entry/SL/TP or portfolio state in the MARKET payload;
- infer `trade_allowed`, `is_actionable`, execution readiness, or profitability;
- feed any value back into advisor, strategy, risk, execution, Telegram, or PPL.

The only authority label accepted by this contract is
`OBSERVATIONAL_TELEMETRY`.

## 3. Why MARKET is separate from the canonical advisor snapshot

`observability/operator_snapshot_builder.py` is advisor-owned and provides one
coherent process-local snapshot for portfolio, decision-pipeline and system
health. CryptoRadar is a separate observational product/process whose current
source is the DecisionPacket history.

Forcing CryptoRadar into the advisor-owned snapshot would create a false
process-locality claim and would make the advisor snapshot builder read a
cross-process/history source it does not own. Therefore MARKET uses the
explicit O-02W-B §12 subrouter/bridge exception and has an independent
freshness envelope.

The React application may issue a second GET only while the MARKET view is
mounted. Overview/Portfolio/Decisions/System continue to use the single
canonical `/api/operator/v1/snapshot` request stream unchanged.

## 4. Producer contract

Producer module:

`observability/market_radar_snapshot.py`

It reuses the existing CryptoRadar calculation functions from
`scripts/radar_bot.py`:

- `load_recent_packets()`;
- `compute_symbol_stats()`.

It does not duplicate the ranking algorithm and does not import the Telegram
poll loop or call Telegram.

Default output:

`databases/cryptoradar_market_snapshot.json`

Override:

`RADAR_MARKET_SNAPSHOT_PATH`

The writer MUST use `tmp.write_text(...)` followed by `os.replace(...)` so a
reader observes either the previous complete snapshot or the next complete
snapshot, never a partial JSON document.

A write failure is fail-passive: it is reported to stderr/logging and never
modifies trading/runtime authority.

## 5. Producer cadence

The standalone publisher supports `--once` and a bounded loop. Default loop
cadence is 30 seconds. This is an observability cadence only.

The publisher may be run independently of the Telegram bot and requires no
Telegram token.

## 6. Payload schema

The produced document is:

```json
{
  "schema_version": "1.0.0",
  "product": "CryptoRadar",
  "domain": "market",
  "authority": "OBSERVATIONAL_TELEMETRY",
  "mode": "OBSERVATION",
  "generated_at_utc": "...Z",
  "source_updated_at_utc": "..." ,
  "window_hours": 24,
  "min_confidence": 65.0,
  "packets_observed": 0,
  "market_regime": null,
  "universe_size": 0,
  "actionable_count": 0,
  "watchlist_count": 0,
  "top_opportunities": []
}
```

`source_updated_at_utc` is the newest genuine `created_at` carried by the
observed DecisionPacket records when available; otherwise it is null. It is
never replaced with `generated_at_utc`.

Each `top_opportunities` row contains exactly:

- `symbol`;
- `avg_confidence`;
- `max_confidence`;
- `n_signals`;
- `dominant_side` (`LONG|SHORT|MIXED`);
- `dominance_pct`;
- `regime`.

No Entry/SL/TP field is legal in the MARKET bridge payload.

`actionable_count` is presentation vocabulary inherited from CryptoRadar's
historical UI (`confidence >= min_confidence`). It is NOT an execution
authorization claim and MUST never be mapped to `DecisionPacket.is_actionable`.

`watchlist_count` means symbols with average confidence in `[50,
min_confidence)`. It has no execution meaning.

## 7. Operator API contract

New route:

`GET /api/operator/v1/market`

The Operator API MUST read only the atomic market snapshot. It MUST NOT read
DecisionPacket JSONL directly and MUST NOT import `scripts/radar_bot.py`.

Failure semantics:

- missing artifact -> HTTP 503 `MARKET_SNAPSHOT_MISSING`;
- malformed JSON -> HTTP 503 `MARKET_SNAPSHOT_MALFORMED_JSON`;
- invalid schema/authority/row shape -> HTTP 503
  `MARKET_SNAPSHOT_INVALID_SCHEMA`.

On success the API returns the producer document verbatim plus two
reader-authored transport fields:

- `snapshot_age_s`;
- `freshness_classification` = `FRESH|STALE`.

Freshness is based only on `generated_at_utc`. The default stale threshold is
90 seconds (`RADAR_MARKET_STALE_AFTER_S` may override it). A stale snapshot is
still evidence and therefore remains HTTP 200 with explicit `STALE`; it is not
silently converted to empty/current data.

## 8. Frontend contract

`MarketView` is a real view, replacing the current `NotExposedView` only for
the Market tab. Scores remains `NOT_EXPOSED`.

The frontend MUST validate the MARKET payload before rendering it. It MUST
reject:

- wrong product/domain/authority/mode;
- malformed numeric/string/count fields;
- malformed opportunity rows;
- Entry/SL/TP-shaped fields inside opportunity rows;
- non-`FRESH|STALE` reader freshness.

No invalid HTTP 200 body may be rendered as healthy market state.

The view exposes provenance visibly: authority, window, generated time and
fresh/stale state.

## 9. Runtime / visual acceptance gates

Source/CI acceptance:

1. publisher tests prove deterministic market aggregation and no execution
   fields;
2. atomic snapshot write test passes;
3. Operator API tests prove missing/malformed/invalid/fresh/stale behavior;
4. route table remains GET-only;
5. frontend tests prove Market is no longer `NOT_EXPOSED` and Scores still is;
6. frontend validation rejects execution-shaped MARKET rows;
7. TypeScript build and Vitest suite pass;
8. Python targeted tests and repository CI pass.

Runtime acceptance (VPS/dev runtime):

1. publisher produces a parseable artifact;
2. two consecutive reads never observe partial JSON;
3. `/api/operator/v1/market` returns HTTP 200 and
   `authority=OBSERVATIONAL_TELEMETRY`;
4. artifact/API payload contains no `entry`, `sl`, `tp`, `stop_loss`,
   `take_profit`, secret/token/password key;
5. Market tab displays real producer values and the FRESH/STALE provenance;
6. stopping the publisher eventually yields visible `STALE`, not fabricated
   current values;
7. no advisor/risk/execution/PPL file changes are part of this mission.

## 10. Non-goals

This mission does not deploy the Operator API publicly, redesign CryptoRadar,
retire Telegram, implement Scores, alter the advisor, modify market algorithms,
or authorize burn-in/REAL trading.
