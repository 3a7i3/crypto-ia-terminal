# WEB-01G — durable local Operator Web App runtime

## Purpose and boundary

WEB-01G serves the built React cockpit locally at `127.0.0.1:8181` and proxies
only `GET`/`HEAD` `/api/*` and `/healthz` requests to the existing Operator API
at `127.0.0.1:8090`. It is read-only presentation transport. It does not read
`databases/` or runtime artifacts, and it introduces no public listener,
secret, exchange credential, Telegram identity, PWA, trading control, or
authority.

The server is a repository-owned Node script using built-in Node modules only.
It does not use Vite preview, Nginx, Express, a secret file, or a system-wide
dependency. API routes are never eligible for the SPA fallback. If the Operator
API is unavailable, they return explicit `502 OPERATOR_API_UNAVAILABLE` JSON.

`/api/operator/v1/snapshot` may correctly remain `503 SNAPSHOT_MISSING`.
That state is `UNRESOLVED`: it is not converted into a healthy snapshot. MARKET
remains independently reachable through `/api/operator/v1/market`.

## Source acceptance

```bash
cd /home/mathieu/crypto_ai_terminal/frontend
npm ci
npm run build
npm test -- --run
npm run test:runtime

cd ..
pytest -q tests/test_web01g_operator_web_runtime_service.py tests/test_claude_service_matrix.py
systemd-analyze verify scripts/systemd/crypto-operator-web.service
```

## Governed deployment — only after merged-SHA certification

Use an exact merged SHA, never floating `main`:

```bash
cd /home/mathieu/crypto_ai_terminal
git status --short
git fetch --no-tags origin main
git rev-parse HEAD
git rev-parse origin/main
command -v node
ss -ltnp | grep ':8181 ' || true
test ! -e frontend/dist/index.html && echo 'build required' || true

cd frontend && npm ci && npm run build && cd ..
systemd-analyze verify scripts/systemd/crypto-operator-web.service
sudo install -m 0644 scripts/systemd/crypto-operator-web.service /etc/systemd/system/crypto-operator-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-operator-web.service
```

The worktree must be clean and the `8181` port must be free before starting the
new service. No existing service is restarted in this procedure.

## Runtime proof

```bash
systemctl is-active crypto-operator-web.service
systemctl show crypto-operator-web.service -p LoadState -p ActiveState -p SubState -p MainPID -p NRestarts -p Result --no-pager
ss -ltnp | grep ':8181 '
curl -fsSI http://127.0.0.1:8181/
curl -fsS http://127.0.0.1:8181/api/operator/v1/market
curl -sS -o /tmp/web01g-snapshot.json -w '%{http_code}\n' http://127.0.0.1:8181/api/operator/v1/snapshot
curl -sS -o /tmp/web01g-post.json -w '%{http_code}\n' -X POST http://127.0.0.1:8181/api/operator/v1/market
```

Collect browser proof for OVERVIEW, SYSTEM, DECISIONS, PORTFOLIO and MARKET.
For a missing canonical snapshot, the first four must remain explicit
`UNRESOLVED`; MARKET must display only real Operator API provenance, mode and
freshness. Verify the listener is exactly `127.0.0.1:8181`, the POST is `405`,
and no API response becomes SPA HTML.

Restart only the new service for recovery proof:

```bash
sudo systemctl restart crypto-operator-web.service
systemctl show crypto-operator-web.service -p NRestarts -p Result --no-pager
```

## Rollback

Rollback affects only the WEB-01G service and leaves built assets, API,
snapshot artifacts and all historical services untouched:

```bash
sudo systemctl disable --now crypto-operator-web.service
sudo rm /etc/systemd/system/crypto-operator-web.service
sudo systemctl daemon-reload
sudo systemctl reset-failed crypto-operator-web.service || true
```
