"""observability/operator_api — O-02W-D1: minimum read-only canonical
operator API.

This package implements a *separate*, read-only FastAPI transport process
over the already-materialized canonical files produced by O-02W-C
(`databases/operator_snapshot.json`, `databases/operator_runtime_manifest.json`).

It never instantiates `MexcSimulator`/`WalletSync`/`RealAccountsObserver`,
never imports `core.advisor_loop`, never connects to an exchange, never
reads API credentials, and never recomputes any domain value the producer
already materialized (§ PROCESS_BOUNDARY_VERDICT,
docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md).
"""
