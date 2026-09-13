# OPS-D / LMI-RUNTIME-CERT-01 — Source Remediation

Reference main SHA: `ddd34b4ae325b9852475f043f9b1f6cd1e4c6e23`

## Runtime evidence that triggered remediation

The 2026-09-13 read-only VPS capture demonstrated:

- runtime SHA drift (`dd0d8a5...` instead of reference `ddd34b4...`);
- LMI process healthy enough to produce fresh observations for most of the watchlist;
- 20 requested symbols but 26 states persisted in the sidecar;
- seven historical states outside the current watchlist;
- `USD1USDT` requested but absent from the current MEXC Futures public catalogue;
- repeated `queue stall` warnings for that non-existent Futures instrument;
- `stats.events` progressing as PressureField output, not raw WebSocket event count.

## Remediation

This branch is deliberately narrow:

1. prune sidecar states that leave the current watchlist;
2. prevent late cancelled-task updates from reintroducing removed symbols;
3. distinguish requested, streamable, observed, fresh, stale and unavailable symbols;
4. validate MEXC Futures symbols against fresh public `contract/detail` evidence before opening WebSockets;
5. fail closed for a reconciliation iteration if the public MEXC catalogue itself cannot be obtained;
6. expose explicit coverage semantics through the dashboard adapter;
7. add focused network-free regression tests;
8. document the bounded post-deploy read-only runtime certification capture.

## Scientific boundary

`SOURCE PROOF != RUNTIME PROOF`.

A green/mergeable PR proves only source remediation. Final OPS-D certification still requires deployment of the merged SHA and a bounded VPS observation window.

No changes to strategy/signal semantics, risk, sizing, portfolio authority, PAPER accounting authority, execution, F-00, burn-in, or LIVE authorization.

## Final runtime verdict

Not emitted by this PR. After post-deploy evidence, exactly one verdict is allowed:

- `OPS_D_RUNTIME_CERTIFIED`
- `OPS_D_REMEDIATION_REQUIRED`
