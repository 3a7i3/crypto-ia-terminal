# WEB-WORKBOARD-RUNTIME-01 — frontend-only release

Mission #430 ; source #428/#429 ; #286 remains ACTIVE. Operator requested
implementation after seeing the source preview. This is a separate presentation
release, not U8/L4 certification or authorization of PAPER stress/capture.

## Observed preflight, 2026-10-13 UTC

- Web: PID2109096, NRestarts0, direct directory
  `/opt/crypto-ai-terminal/operator/releases/1728b3ad952b87d903ccb7442579000da292b848/frontend`.
- Existing override: `90-ux-fr.conf`. Proxy remains 127.0.0.1:8181 → 8090.
- Advisor: PID882633, NRestarts0, started 2026-09-27 03:03:57 UTC.
- API: PID1941519, NRestarts0, started 2026-10-08 05:38:19 UTC.
- API and Advisor both use `/home/mathieu/crypto_ai_terminal`; never advance it.
- `current` points to 7638475dc1a18340c252cb1ce7bfdc143297c601 and is **not** the
  web working directory. Preserve this link; do not activate through it.
- Private address: `https://crypto-advisor-2.tailfebca3.ts.net/direction/travaux`.
- Connected uid996 chatgpt-ro cannot write releases/units; Desktop Commander
  blocks privileged commands. No config change, elevation or bypass is proposed.

## Concrete scope

Build source head bdca77f9bcf306c17846985faef870844fdd1334 in an isolated clean
checkout. Package only frontend/dist and its builtin Node static server.
No backend source, dependencies, environment or runtime facts are installed.
The current frontend is older: 32 source/test/tool files differ from that served
release, including previous main presentation improvements plus #429.
This release is the reviewed full frontend, not a seven-file runtime hotpatch.
Package/lock hashes match the deployed release. Native server change only adds
correct detection of direct/symlink entrypoint; GET/HEAD and proxy remain fixed.

Package rebuilt 2026-10-13 from the final merged source (main@bdca77f, theme #439 and register #440
included) with `scripts/build_workboard_frontend_package.py`; the previous archive
built from 391266e is superseded and is not evidence for this content. The
builder is deterministic for a given built checkout; it does not install or deploy.

Fresh local npm audit: zero vulnerabilities; production build PASS; eight local
server/PWA boundary tests PASS. This is source proof, not a served bundle claim.

## Required gates

1. #429 merged after final CI; the manifest records the verified merge SHA.
2. Exact-source build and archive SHA plus per-file hashes verified.
3. Fresh web directory unchanged, protected services active, no new drop-in or
   release already occupying the selected paths. Unknown/drift => refuse.
4. Privileged **operator** executes the reviewed activation manually. The agent
   does not execute sudo, obtain credentials or grant itself permissions.
5. Static assets must match served bytes; Advisor/API state and current symlink
   must remain unchanged. Browser proof remains a separate observed result.

The [operator helper](../../scripts/activate_workboard_frontend.py) defaults to
inspect-only. `--activate` requires root and a manifest source-merge receipt.
That receipt records operator-reviewed GitHub state, not an independent signer.
Never invoke activation while a source gate is pending. No cron or auto-deploy.

## Mutation and rollback

Install a fresh root-owned frontend release at releases/<reviewed-source-SHA>.
Add only `99-workboard.conf`, overriding web WorkingDirectory/ExecStart while
keeping its existing protections, private listener and other unit settings.
Reload systemd and restart **only crypto-operator-web.service**.
No existing override is replaced. No current pointer, API, Advisor, data,
strategy, epoch, PPL, FIN, sizing, exchange or Watchdog change.

On observed install failure, remove only this newly created override, reload
and restart web to recover the previous direct release. Keep the new release
for forensic review; an existing release directory causes a future refusal.
Manual rollback is the same removal/reload/web restart, with before/after
protected-service observations. Never restart API or Advisor for rollback.

Verify source manifest and all static asset hashes via loopback. HTTP200 at a
SPA route alone proves neither route content nor runtime certification. Open
the private page in a tailnet client, verify filters and mobile navigation,
and preserve browser evidence before closing the runtime mission.

## Source of the bundle versus source of the tools

Two commits are deliberately separate and must not be conflated:

- **Bundle source** is the frontend commit the archive was built from, pinned as
  `SOURCE_SHA` in the helper and recorded in the manifest: `bdca77f9bcf306c17846985faef870844fdd1334`
  (main after PR #440: workboard register, "Bleu pédagogique" theme #439). It also names
  the release directory. Gateway, ledger or signature changes merged to main
  later do not touch `frontend/` and do not change this pin; advancing it is a
  reviewed change plus a rebuilt, re-hashed package, never automatic.
- **Tools source** is the commit that carries the helper and builder
  (this PR's merge). The operator copies the helper from that commit, checks its
  SHA-256, and never runs `git pull` in the runtime checkout.

Build provenance for the pinned archive: two independent clean worktrees of
bdca77f, each with `npm ci` from the locked graph and `npm run build` (tsc 5.9.3,
vite 8.3.2), Node v22.22.0, npm 10.9.4, Python 3.13 for the builder. Both gave the
same archive SHA-256 `d7c61163651e964f04d06941cc0451b82939177dbdb0d303a953fc9b6caf4f5e`
(9 files, manifest `source_merge_sha` = bdca77f). The earlier pin 46fef27 (archive
57dbdf9d…) is superseded by the register update #440 and is not evidence for this
content. Reproducibility across other Node/npm versions is not claimed. The SHA-256 is a
reported fingerprint until recomputed on the target host from the fetched file.

## Operator procedure (no step here is executed by the agent)

Rights: steps 1-3 need only read access; 4-6 need root on the web host.

1. Fetch the archive and the helper from the reviewed sources, then recompute
   `sha256sum` of both on the host and compare with the values in the PR/report.
   Any difference stops the procedure.
2. Read-only baseline (record the output): `hostname`, `date -u`,
   `systemctl show crypto-operator-web.service crypto-advisor.service crypto-operator-api.service --property=Id,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp`,
   `systemctl show crypto-operator-web.service --property=FragmentPath,WorkingDirectory`,
   `readlink /opt/crypto-ai-terminal/operator/current`. Expected web
   WorkingDirectory is the previous release `1728b3ad...` (not `current`).
3. Inspect only (default mode, no mutation, no root):
   `python3 activate_workboard_frontend.py --archive <archive> --sha256 <archive-sha>`.
   Expect `INSPECT_ONLY_NO_MUTATION`; any `PREVIOUS_RELEASE_OR_OVERRIDE_CHANGED`
   or `WRONG_RELEASE_SCOPE` means stop and report.
4. Operator decision: confirm the manifest `source_merge_sha`, scope
   `FRONTEND_ONLY`, no pending source gate, and the explicit written go.
5. Activate as root, same command plus `--activate`. It creates
   `releases/bdca77f9.../`, writes only `99-workboard.conf`, reloads systemd and
   restarts only `crypto-operator-web.service`, then checks every served asset
   and `/direction/travaux` byte for byte on `127.0.0.1:8181` and compares API and
   Advisor state and the `current` link before/after. Failure removes the new
   override and restarts web on the previous release automatically.
6. Verify: `curl -sI http://127.0.0.1:8181/direction/travaux` (200), open the
   private tailnet page, check the theme, the 29-row table, filters and mobile
   navigation, and keep screenshots. Browser proof stays a separate result.

Manual rollback (root, web only): remove
`/etc/systemd/system/crypto-operator-web.service.d/99-workboard.conf`,
`systemctl daemon-reload`, `systemctl restart crypto-operator-web.service`, then
confirm WorkingDirectory is `1728b3ad...` again and API/Advisor PID and start
time are unchanged. Keep the new release directory for forensics. Rollback is
bounded to that single known previous release; the helper refuses to run if the
previous release or overrides drifted.
