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

Build source head 46fef27ead49aa99d54acf3310caa31b084134fe in an isolated clean
checkout. Package only frontend/dist and its builtin Node static server.
No backend source, dependencies, environment or runtime facts are installed.
The current frontend is older: 32 source/test/tool files differ from that served
release, including previous main presentation improvements plus #429.
This release is the reviewed full frontend, not a seven-file runtime hotpatch.
Package/lock hashes match the deployed release. Native server change only adds
correct detection of direct/symlink entrypoint; GET/HEAD and proxy remain fixed.

Package rebuilt 2026-10-13 from the final merged source (main@46fef27, theme #439
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
