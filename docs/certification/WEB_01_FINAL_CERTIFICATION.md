# WEB-01 FINAL CERTIFICATION — Operator Web App v1 (local read-only)

Date: 2026-09-15
Repository: `3a7i3/crypto-ia-terminal`
Mission: Issue #162 — `WEB-01 FINAL — Operator Web App v1 local read-only certification`

## Final verdict

`WEB_01_FINAL_CERTIFIED`

This verdict certifies only the **local, read-only Operator Web App v1 chain** described below. It does not certify public/remote exposure, the availability of the canonical operator snapshot, trading profitability, trading algorithms, REAL authority, F-00, burn-in, or the whole repository CI as green.

## 1. Certified identity and baseline

- Required baseline / deployed `main`: `aeebdd1744e54ccc95bd93002af0e3944f4a7618`
- WEB-01G certified functional source HEAD: `ddb70074ac05624a5154bc60230473c0ea15a04d`
- WEB-01G merge/runtime baseline: `aeebdd1744e54ccc95bd93002af0e3944f4a7618`
- Isolated certification worktree: `/tmp/web01-final-cert`
- Certification worktree state at proof time: detached at exact baseline, clean
- `git diff --check`: PASS

The certification record itself is documentation-only. Its PR/merge identity is tracked by GitHub issue/PR metadata rather than used as a functional WEB-01 source identity.

## 2. Certified lineage

| Layer | PR | Certified source HEAD | Merge SHA |
|---|---:|---|---|
| Minimum read-only canonical Operator API | #127 — O-02W-D1 | `c8c45b4dc5ac17caeec63d55b580b62b07c04ce4` | `fd5350f362383e1d4078a26f61af89e736963fb6` |
| Minimum read-only React cockpit | #128 — O-02W-D2 | `27cfbca34a1af48bb9026b67fc025e11bdd50f77` | `44a12d94cc2773771f278d1edb5ce865b48f89dc` |
| Cross-stack compatibility gate | #129 — O-02W-D3 | `0340ea82450bf88f1a62f5b3bb2b001a522a3769` | `17a2f70537ee48f70500974dddf5f0458c02cc50` |
| CryptoRadar read-only MARKET bridge | #157 — WEB-01 MARKET | `7c20c3a95b111845c7ac42276874a2ae2139a700` | `0fbd197f9ec0f24ae9b1cd196c7abf7a745487e0` |
| Continuous MARKET runtime | #158 — WEB-01E | `87fd3b839d2584cfd6418beb01e49b201c9e1bb9` | `cca6892dc7cb4c4b1311d9b63cedb89fade38df8` |
| Durable local Operator API runtime | #159 — WEB-01F | `0369733d56203626501877784f4046f8065e56ee` | `fb9aa5b3f240a04dddd96b5a29a70ee14dd33819` |
| Durable local frontend runtime | #161 / Issue #160 — WEB-01G | `ddb70074ac05624a5154bc60230473c0ea15a04d` | `aeebdd1744e54ccc95bd93002af0e3944f4a7618` |

GitHub ancestry comparisons verified that the merge SHAs for #127, #128, #129, #157, #158 and #159 are ancestors of `aeebdd1744...` with `behind_by=0` and exact merge-base equality. PR #161's merge is identical to the certified `main` baseline. No lineage break was found.

## 3. Certified local architecture

```text
DecisionPacket / CryptoRadar evidence
        |
        v
crypto-market-snapshot.service
        |
        v
cryptoradar_market_snapshot.json
        |
        v
crypto-operator-api.service
127.0.0.1:8090
        |
        v
crypto-operator-web.service
127.0.0.1:8181
        |
        v
React Operator Web App
```

The frontend presentation path uses same-origin `/api/*` / `/healthz` transport through the native WEB-01G server. The local frontend server accepts GET/HEAD for API transport and rejects mutating methods. The frontend does not gain a direct write edge into exchange, strategy, risk, sizing, portfolio or execution authority.

## 4. Source certification evidence

All final source gates were run from the isolated clean worktree at exact SHA `aeebdd1744...`, not from the live production checkout.

### Python bounded WEB-01 gate

Command scope covered:
- `tests/cross_stack/`
- Operator API targeted tests
- MARKET producer/API tests
- WEB-01E/F/G runtime-service contracts

Result:

`193 passed in 6.31s`

### Frontend deterministic install/build/test

The chained command completed through all stages, proving:
- `npm ci`: PASS
- `npm run build`: PASS
- full Vitest run: `223 passed / 7 skipped`
- native WEB-01G runtime contracts: `2 passed / 0 failed`

The 7 skipped tests were the fixture-dependent cross-stack frontend suite. They were not accepted as skipped proof; canonical fixtures were then generated through the real Python producer paths and the exact frontend cross-stack file was executed explicitly.

### Exact producer -> API -> frontend cross-stack proof

Generated with:
- `tests.cross_stack.generate_fixtures`
- `tests.cross_stack.generate_market_fixture`

Then executed `src/test/crossStack.compat.test.tsx` with `CROSS_STACK_FIXTURES_DIR`.

Result: `7 passed / 7`.

Certified scenarios:
- A — exact producer-generated canonical JSON accepted unchanged and canonical cockpit views render;
- B — UNKNOWN mode remains honest and is never defaulted to PAPER;
- C — PAPER vs REAL separation and unavailable price/PnL semantics survive unchanged;
- D — authority mapping accepted exactly, deliberately mutated authority rejected;
- E — previous-instance snapshot shown as `LAST_KNOWN`, never `CURRENT_INSTANCE`;
- F — governed 503 surfaced honestly rather than fabricated into success;
- G — exact CryptoRadar producer/API JSON admitted unchanged and rendered by MARKET.

### systemd source verification

`systemd-analyze verify` was run against:
- `crypto-market-snapshot.service`
- `crypto-operator-api.service`
- `crypto-operator-web.service`

No error was reported against those three units. Two host-level messages were observed and classified outside WEB-01 scope: a permission warning for `netplan-ovs-cleanup.service` and an unsupported `RestartMode` key in the host `snapd.service`.

### Source integrity after gates

- HEAD: `aeebdd1744e54ccc95bd93002af0e3944f4a7618`
- `git status --short`: empty
- `git diff --check`: clean

No test/generator mutation remained in the worktree.

## 5. Real VPS runtime evidence

### Consolidated service state

At final certification witness time:

| Service | MainPID | Result | State |
|---|---:|---|---|
| `crypto-market-snapshot.service` | `2218746` | `success` | `active/running` |
| `crypto-operator-api.service` | `2208782` | `success` | `active/running` |
| `crypto-operator-web.service` | `2224150` | `success` | `active/running` |

### Network boundary

Observed listeners:
- Operator API: `127.0.0.1:8090`
- Operator Web: `127.0.0.1:8181`

No `0.0.0.0` or public frontend/API listener is certified by WEB-01.

### Runtime endpoints

Final consolidated witness:
- `http://127.0.0.1:8090/healthz` -> HTTP `200`
- `http://127.0.0.1:8181/` -> HTTP `200`
- `http://127.0.0.1:8181/api/operator/v1/market` -> HTTP `200`
- `http://127.0.0.1:8181/api/operator/v1/snapshot` -> HTTP `503`

Canonical snapshot body:

```json
{"error_code":"SNAPSHOT_MISSING","error_message":"Canonical snapshot unreadable: MISSING","retries_used":0}
```

This 503 is an explicit scientific state, not a runtime-success substitute.

## 6. Real browser evidence

Real headless Chromium was run against the deployed WEB-01G runtime, not only against component fixtures.

Observed proof:
- `OVERVIEW=UNRESOLVED_OK`
- `SYSTEM=UNRESOLVED_OK`
- `DECISIONS=UNRESOLVED_OK`
- `PORTFOLIO=UNRESOLVED_OK`
- `SNAPSHOT_API_HTTP=503`
- `MARKET_FRESHNESS=FRESH · 5s`
- `MARKET_OPPORTUNITY_ROWS=20`
- `BROWSER_POST_HTTP=405`
- `WEB01_REAL_BROWSER_E2E=PASS`

The browser rendered real MARKET data containing `CryptoRadar`, authority `OBSERVATIONAL_TELEMETRY`, mode `OBSERVATION`, and real freshness semantics. A browser POST to the MARKET route was rejected with HTTP 405.

The E2E harness's final `MARKET_API_HTTP=405` log value was caused by its response collector recording the intentionally issued final POST to the same MARKET URL and overwriting the earlier GET status. Independent real curl evidence established GET MARKET HTTP 200, and successful browser rendering of MARKET provenance/freshness plus 20 rows causally proves successful GET delivery.

## 7. Durability and recovery evidence

WEB-01G installed/source systemd units were proven byte-identical during runtime certification:

`crypto-operator-web.service` SHA256:
`5e9907156c1a6d432b0e171003cb99944e7cfb3d3f4cb098b02f3129025686d7`

The unit was `enabled` and contained no secret-file, exchange credential or Telegram-token wiring.

A controlled restart of **only** `crypto-operator-web.service` was performed:
- pre-restart PID: `2217390`
- post-restart PID: `2224150`
- post-restart: `active/running`, `Result=success`
- listener restored on `127.0.0.1:8181`
- frontend restored HTTP 200
- MARKET restored HTTP 200

No trading/research service was restarted for this recovery proof.

## 8. Read-only and security invariants

Certified within WEB-01 scope:
- frontend listener is loopback-only;
- Operator API listener is loopback-only;
- frontend API proxy accepts only GET/HEAD transport;
- mutating POST is rejected with HTTP 405;
- API paths do not fall through to SPA HTML; an unknown API route returned a real JSON HTTP 404;
- no BUY/SELL/restart/strategy/capital/gate control is introduced by WEB-01;
- no exchange credential, Telegram token, secret store or trading authority is required by the Web presentation path;
- MARKET is `OBSERVATIONAL_TELEMETRY` / `OBSERVATION` only;
- frontend does not directly read runtime database artifacts to bypass the Operator API;
- no strategy, signal, risk, sizing, portfolio-decision or order-execution algorithm was modified by the final-certification mission.

## 9. Scientific truthfulness

The canonical operator snapshot is currently absent/unreadable at the governed path and therefore remains:

`UNRESOLVED / 503 SNAPSHOT_MISSING`

Consequences:
- OVERVIEW, SYSTEM, DECISIONS and PORTFOLIO remain explicitly UNRESOLVED;
- no replacement values are fabricated;
- MARKET remains independently available through its separate certified bridge;
- MARKET freshness is read from its real contract and is not invented by the UI;
- frontend presentation does not become a competing financial/execution source of truth.

This unresolved state does **not** invalidate the WEB-01 local transport/UI certification; it is preserved as scientific debt to be addressed by a separately scoped mission.

## 10. CI attribution

On WEB-01G certified source HEAD `ddb70074...`, the following causal WEB/source gates completed successfully:
- `CI` — success;
  - TEST REGRESSION GATE — success
  - LINT REGRESSION GATE — success
  - COVERAGE REGRESSION BASELINE — success
  - Smoke test — success
- `Frontend CI` — success (frontend tests + production build);
- `Cross-Stack Compatibility Gate` — success, including real producer fixture generation and frontend compatibility test;
- `WEB-01 Market Visual Proof` — success;
- `Generate Panel Screenshots` — success.

Repository CI is **not globally green**. Historical non-causal jobs remained red:
- `Test Dashboards and Panels` — the unit/functional test step succeeded; the later end-to-end panel step failed;
- `Coverage Report` — failure in its coverage test step;
- `Upload coverage to Codecov` — failure in its coverage test step, upload skipped;
- `Upload coverage to Coveralls` — failure in its coverage test step, upload skipped.

These red workflow families pre-existed the bounded WEB-01G/final-certification change and are not silently relabelled green or repaired in this certification-only mission.

Therefore:

`GENERAL_CI = NON_GREEN / PRE_EXISTING_DEBT`

while the causal WEB-01 gates above are certified PASS.

## 11. Explicit unresolved / not certified

The following are deliberately **not** certified by `WEB_01_FINAL_CERTIFIED`:
- canonical operator snapshot availability (`SNAPSHOT_MISSING` remains unresolved);
- public Internet exposure;
- remote DNS/TLS/reverse proxy;
- remote authentication;
- PWA/service worker/offline behavior;
- WEB-01B implementation;
- Telegram retirement;
- trading profitability;
- strategy/signal/risk/sizing/execution correctness beyond the read-only non-authority boundary;
- PPL authority promotion;
- FIN-00 completion;
- F-00 start;
- burn-in authorization;
- REAL trading authorization;
- globally green repository CI.

## 12. Final certification matrix

```text
✅ WEB_01_FINAL_CERTIFIED
✅ WEB_01_LINEAGE_CERTIFIED
✅ WEB_01_SOURCE_GATES_CERTIFIED
✅ WEB_01_CROSS_STACK_CERTIFIED
✅ WEB_01_RUNTIME_CHAIN_CERTIFIED
✅ WEB_01_REAL_BROWSER_CERTIFIED
✅ WEB_01_LOOPBACK_ONLY_CERTIFIED
✅ WEB_01_READ_ONLY_BOUNDARY_CERTIFIED
✅ MARKET_CRYPTORADAR_REAL_DATA_CERTIFIED
🟡 CANONICAL_SNAPSHOT = UNRESOLVED / 503 SNAPSHOT_MISSING
🟡 GENERAL_CI = NON_GREEN / PRE_EXISTING_DEBT
✅ NO_TRADING_RESEARCH_ALGORITHM_MUTATION
```

## 13. Exit decision

WEB-01 Operator Web App v1 is certified as a **durable local read-only operator surface** at the exact runtime baseline `aeebdd1744e54ccc95bd93002af0e3944f4a7618`.

After this certification is merged:
1. roadmap issue #148 may be updated to mark WEB-01 local read-only certification complete;
2. `SNAPSHOT_MISSING` must remain explicitly unresolved;
3. WEB-01B becomes eligible as a separately scoped private-PWA/controlled-remote-access mission, but this certification does not start it;
4. the master roadmap's current FIN-00 blocker toward F-00 is not silently reordered;
5. F-00 remains `NOT STARTED` and burn-in remains `NOT AUTHORIZED` unless a separate governed decision changes those states.
