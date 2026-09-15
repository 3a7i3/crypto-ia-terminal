# WEB-01B — Private PWA & controlled private access

Status: source implementation / runtime not yet certified  
Mission: GitHub Issue #164  
Baseline: `main@16e8b17b6275612baa9a57367906cb68b2e1c5bb`

## 1. Scope

WEB-01B extends the already certified WEB-01 local read-only Operator Web App into an
installable private PWA. It does **not** change strategy, signal, risk, sizing,
portfolio-decision, execution, exchange, FIN-00, F-00 or burn-in authority.

The local WEB-01 trust boundary remains mandatory:

```text
private authenticated HTTPS transport
        |
        v
127.0.0.1:8181  crypto-operator-web
        |
        | same-origin GET/HEAD /api/* and /healthz
        v
127.0.0.1:8090  crypto-operator-api
```

Neither `8181` nor `8090` may be rebound to `0.0.0.0` or `[::]` for WEB-01B.

## 2. PWA scientific integrity boundary

The service worker may cache only presentation shell resources.

Explicit network-only runtime truth:

- `/api`
- `/api/*`
- `/healthz`
- `/healthz/*`

The service worker returns without `respondWith()` for these paths. Therefore a
canonical snapshot, MARKET snapshot, portfolio state, decision state, system state,
or health response can never be replayed from Cache Storage as if it were current.

When the private transport is unavailable, the static shell may still launch. Live
clients must then report transport/unavailable state. A cached shell is not evidence
that the Operator API or market telemetry is live.

No API key, exchange credential, Telegram token, Tailscale auth key, dashboard
password, or other secret is compiled into the frontend.

## 3. Installability contract

The source provides:

- `manifest.webmanifest`;
- 192x192 and 512x512 PNG icons designed inside the maskable safe area;
- `display: standalone`;
- root `start_url` and scope;
- production-only Service Worker registration;
- periodic Service Worker update checks;
- old-shell cache cleanup on worker activation;
- native WEB-01 server MIME support for the manifest and PNG assets.

The Service Worker is not registered in Vite development mode.

## 4. Private transport selection

Runtime forensic reconnaissance selected **Tailscale Serve** as the WEB-01B transport
candidate. Tailscale Funnel is explicitly forbidden because Funnel is public.

Rationale:

- tailnet-only reachability;
- authenticated tailnet identity / ACL boundary;
- HTTPS termination supplied by Tailscale;
- reverse proxy target remains `http://127.0.0.1:8181`;
- no CORS broadening;
- no frontend credential;
- no public listener added to WEB-01.

Runtime deployment is deliberately separate from source certification.

### Target runtime command

After Tailscale is installed and the node is authenticated into the intended tailnet:

```bash
sudo tailscale serve --bg http://127.0.0.1:8181
```

The actual HTTPS URL and Serve state must be taken from:

```bash
tailscale serve status
```

No `tailscale funnel` command is allowed by this mission.

## 5. Runtime reconnaissance findings kept outside WEB-01B mutation scope

The 2026-09-15 read-only VPS reconnaissance found:

- `127.0.0.1:8181` — certified WEB-01 frontend;
- `127.0.0.1:8090` — certified Operator API;
- `0.0.0.0:8050` — historical `crypto-dashboard.service`;
- `0.0.0.0:8080` — ChartServer embedded in `crypto-advisor.service`.

Host firewall state was permissive (`ufw` inactive, empty nftables ruleset, iptables
INPUT/FORWARD/OUTPUT ACCEPT). An external self-scan observed TCP 22 and TCP 8050
open; TCP 8080 was not observed open in that scan.

The `8050` dashboard has application authentication: runtime evidence showed a
non-empty dashboard password, a login page at `/`, and HTTP 401 for unauthenticated
`/api/status`. Therefore this is **not** classified here as a demonstrated data leak.
It remains a separate network-hardening finding and WEB-01B does not reuse ports
8050/8080.

## 6. Source gates

At minimum:

```bash
cd frontend
npm ci
npm run build
npm test -- --run
npm run test:runtime
```

The WEB-01B runtime contract additionally proves:

- manifest carries 192 and 512 icons;
- icon bytes have exact expected PNG dimensions;
- cache policy rejects `/api`, `/api/*`, `/healthz`, `/healthz/*`;
- actual Service Worker fetch listener does not intercept those runtime paths;
- WEB-01G server continues to proxy API paths without SPA fallback;
- mutation methods remain HTTP 405.

Existing Python cross-stack and Operator API/MARKET gates remain required before
source certification.

## 7. Runtime certification gates

After source certification and governed deployment:

1. `crypto-operator-web.service` still listens only on `127.0.0.1:8181`.
2. `crypto-operator-api.service` still listens only on `127.0.0.1:8090`.
3. Tailscale Serve is tailnet-only and uses HTTPS.
4. Funnel is absent.
5. Real phone/Chromium session can load and install the PWA over HTTPS.
6. Manifest and 192/512 icons are accepted by the browser.
7. Real MARKET still renders through same-origin transport.
8. Canonical snapshot 503 remains honest if still missing.
9. Browser offline/private-link-loss test shows disconnected/unavailable semantics.
10. DevTools/Cache Storage proof shows no `/api/*` or `/healthz` response stored.
11. POST to the WEB-01 API path remains HTTP 405.

Only after all source and runtime gates pass may the mission receive:

```text
WEB_01B_SOURCE_CERTIFIED
WEB_01B_PRIVATE_PWA_RUNTIME_CERTIFIED
```

Until then, WEB-01B remains active and uncertified.

## 8. Rollback

PWA source rollback is a normal Git revert of the WEB-01B source commit.

Private transport rollback:

```bash
sudo tailscale serve reset
sudo tailscale down
```

Rollback must not rebind `8181` or `8090` publicly. Existing WEB-01 local operation
must remain usable on loopback after private transport removal.
