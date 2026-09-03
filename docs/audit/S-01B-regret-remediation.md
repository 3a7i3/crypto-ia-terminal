# S-01B — Regret remediation and scientific hardening

**Reference:** main `7fc5e28ebd0a54841ff6e4b1c13fd017a07f1838`  
**Scope:** repository only; no deployment, VPS, execution, strategy, portfolio,
risk-model, or Quant Observer modification.

## Certified-mode configuration

Regret is passive by default. During burn-in both of these must remain false:

```text
FEATURE_REGRET_DECISION_FEEDBACK=false
FEATURE_AUTO_CALIBRATION=false
```

`FEATURE_AUTO_CALIBRATION=true` alone cannot unlock feedback. The legacy
RegretEngine calculation and the ActivityTracker `REGIME_MISMATCH` path are
both below the master `FEATURE_REGRET_DECISION_FEEDBACK` boundary. Enabling the
master flag is a non-burn-in legacy compatibility action requiring an explicit
restart and separate governance approval.

## Canonical architecture

`DecisionPacket → DecisionObservation → DecisionEventBus → RejectionStore +
RegretScheduler v2 → horizon evidence → tools.regret_repository → offline
scientific consumers`

The cycle-wide price feed is delivered to v2 whether or not RegretEngine v1 is
constructed. RegretEngine v1 and `databases/regret_analysis.jsonl` are retained
as `regret-v1 / historical`; they are not canonical and are never implicitly
combined with regret-v2.

## Measurement interpretation

See MC-001 schema 2. A classification describes favorable or unfavorable
directional endpoint movement after a rejected signal. It does not demonstrate
an executable missed trade or profit. The model excludes transaction costs,
spread, slippage, funding, liquidity, market impact, latency, executable size,
portfolio constraints, and TP/SL path.

## Retention and compatibility

- Existing aggregate regret-v2 JSONL records remain readable.
- New records are one immutable `HORIZON_EVIDENCE` per
  `observation_id + horizon` and preserve deprecated endpoint aliases
  `mfe_pct`/`mae_pct` without reinterpreting historical values.
- RejectionStore schema 2 adds immutable trace and experiment provenance.
- No existing regret-v1, regret-v2, rejection, or spool artifact is deleted.
- Retention/archival policy changes are deferred until runtime volume and
  restore tests provide evidence for safe guarantees.

## Legacy ShadowTracker classification

`scripts/shadow_execution.py` and `S3/03_shadow_execution.py` remain byte-for-byte
identical (SHA-256
`c23581eaffa087d6820322220cdd9eab5729f91bc3c88000702903dab6d62893`). Runtime
imports `scripts.shadow_execution`; `S3/06_apply_S3.sh` also treats the S3 copy
as an installation source. ShadowTracker uses a later closed paper trade on the
same symbol as a proxy and is not scientifically equivalent to RegretScheduler
v2. Because the S3 copy still has a repository dependency, neither copy is
removed in S-01B. Candidate verdict: `REMOVE_AFTER_PROOF`, after the installer
and replay dependencies are retired or migrated and historical reproduction is
tested.

## Runtime evidence deferred to S-01C

Repository tests establish code-path invariants, not live operation. S-01C must
capture: v1-disabled v2 price receipts; BUY and SELL horizon writes; restart
reconciliation; canonical repository freshness; stable packet/trace joins;
zero calls to threshold mutation under certified flags; spool and JSONL volume;
and absence of per-event Regret Telegram traffic.
