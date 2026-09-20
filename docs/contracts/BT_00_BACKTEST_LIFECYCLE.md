# BT-00 — Backtest lifecycle contract

## Scope

This contract applies to `src/backtest/engine.py::BacktestEngine` only.

It is an offline research-infrastructure contract. It does not authorize or
modify PAPER/PPL/F00 runtime behavior.

## Historical defect

The pre-no-lookahead engine observed a strategy signal using `close[i]`, then
executed the entry at that same `close[i]` and force-closed at `close[i+1]`.

The historical seed=42 golden:

- total_trades = 10
- total_pnl = 7.6295
- win_rate = 1.0
- final_balance = 10007.6295

reconstructs exactly from that behavior and therefore encodes same-close
lookahead.

The August no-lookahead correction moved entry to `open[i+1]` but preserved
the unconditional pending close. That changed the defective lifecycle to
`open[i+1] -> close[i+1]`, independent of strategy intent.

## Canonical BT-00 semantics

For a signal observed after bar `i` closes:

1. No portfolio mutation may use `close[i]` as its fill.
2. The earliest executable fill is `open[i+1]`.
3. If there is no position for the symbol, the deferred signal opens one.
4. If an existing position has the opposite side, it is closed at
   `open[i+1]` and the new side is opened at the same reachable price.
5. If an existing position already has the requested side, the signal is
   idempotent; its entry price/identity is not overwritten.
6. A position remains open through bars that produce no opposite signal.
7. At finite replay end, any still-open position is liquidated only at the
   final observed close for that symbol so the report contains realized
   outcomes. No synthetic terminal price is allowed.

## Deterministic replay snapshot

For SMA(3,10), 120 seed=42 synthetic candles and initial balance 10,000, the
corrected lifecycle candidate is:

- total_trades = 10
- total_pnl = 8.266
- win_rate = 0.7
- max_drawdown = 0.00038849
- final_balance = 10008.266
- regime = sideways

These numbers become certified only when CI reproduces the golden test without
an xfail.

## Exit criteria

BT-00 is complete only when:

- lifecycle-specific tests pass;
- `TestTier2GoldenSnapshot::test_backtest_matches_golden` passes normally;
- its xfail marker is absent;
- the BT-00 row is absent from `.ci/known_red_tests.md`;
- repository regression/coverage/lint gates pass;
- the Scientific Data Guard remains green;
- no deployment is made to the active F00 runtime.
