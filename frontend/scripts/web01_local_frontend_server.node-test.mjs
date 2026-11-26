// Node-native runtime contract; intentionally outside Vitest discovery.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createServer, parseOperatorLogins, readRelayToken, relayAudit, systemdListenFd, isMainEntrypoint, resolveFrontendPort, FRONTEND_PORT, LOOPBACK_HOST, SPOT_RADAR_API_PREFIX, SPOT_RADAR_API_TARGET, UPSTREAM_TIMEOUT_MS } from "./web01_local_frontend_server.mjs";

function listen(server) { return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port))); }
function close(server) { return new Promise((resolve) => server.close(resolve)); }
async function request(port, pathname, method = "GET") {
  const response = await fetch(`http://127.0.0.1:${port}${pathname}`, { method });
  return {
    status: response.status,
    text: await response.text(),
    contentType: response.headers.get("content-type"),
    cacheControl: response.headers.get("cache-control"),
  };
}

test("recognizes direct and symlinked main entrypoints while rejecting imported module paths", async () => {
  const runtimePath = fileURLToPath(new URL("./web01_local_frontend_server.mjs", import.meta.url));
  const importedFromPath = fileURLToPath(import.meta.url);
  const runtimeUrl = pathToFileURL(runtimePath).href;
  const linkRoot = await mkdtemp(path.join(tmpdir(), "web01g-main-link-"));
  const symlinkPath = path.join(linkRoot, "web01_local_frontend_server.mjs");

  await symlink(runtimePath, symlinkPath);

  assert.equal(isMainEntrypoint(runtimePath, runtimeUrl), true, "direct main path must be recognized");
  assert.equal(isMainEntrypoint(symlinkPath, runtimeUrl), true, "symlinked main path must resolve to the same entrypoint");
  assert.equal(isMainEntrypoint(importedFromPath, runtimeUrl), false, "a different importing module must not be treated as main");
});

test("serves frontend routes but never applies SPA fallback to API paths", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  await writeFile(path.join(distRoot, "asset.js"), "console.log('asset')");
  const api = http.createServer((req, res) => {
    if (req.url === "/api/operator/v1/market") return res.end('{"market":true}');
    if (req.url === "/healthz") return res.end('{"ready":true}');
    res.writeHead(404, { "content-type": "application/json" }); res.end('{"error_code":"API_NOT_FOUND"}');
  });
  const apiPort = await listen(api);
  const app = createServer({ port: 0, distRoot, apiTarget: `http://127.0.0.1:${apiPort}` });
  await new Promise((resolve) => app.once("listening", resolve));
  const appPort = app.address().port;
  t.after(async () => { await close(app); await close(api); });

  assert.equal((await request(appPort, "/operator/market")).text, "<main>operator</main>");
  assert.equal((await request(appPort, "/asset.js")).text, "console.log('asset')");
  const proxied = await request(appPort, "/api/operator/v1/market");
  assert.equal(proxied.status, 200); assert.equal(proxied.text, '{"market":true}');
  assert.equal(proxied.cacheControl, "no-store", "runtime API responses must be non-cacheable at the browser boundary");
  const health = await request(appPort, "/healthz");
  assert.equal(health.status, 200); assert.equal(health.cacheControl, "no-store");
  const missingApi = await request(appPort, "/api/missing");
  assert.equal(missingApi.status, 404); assert.match(missingApi.text, /API_NOT_FOUND/); assert.doesNotMatch(missingApi.text, /operator/);
  assert.equal(missingApi.cacheControl, "no-store");
});

test("rejects mutation methods and makes API transport failures explicit", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const app = createServer({ port: 0, distRoot, apiTarget: "http://127.0.0.1:1" });
  await new Promise((resolve) => app.once("listening", resolve));
  const appPort = app.address().port;
  t.after(() => close(app));

  const mutation = await request(appPort, "/api/operator/v1/market", "POST");
  assert.equal(mutation.status, 405); assert.match(mutation.text, /METHOD_NOT_ALLOWED/);
  assert.equal(mutation.cacheControl, "no-store");
  const unavailable = await request(appPort, "/api/operator/v1/market");
  assert.equal(unavailable.status, 502); assert.match(unavailable.text, /OPERATOR_API_UNAVAILABLE/);
  assert.equal(unavailable.cacheControl, "no-store");
});

test("serves WEB-01B PWA assets with explicit safe MIME and update headers", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01b-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  await writeFile(path.join(distRoot, "manifest.webmanifest"), "{}");
  await writeFile(path.join(distRoot, "sw.js"), "self.addEventListener('fetch',()=>{});");
  await writeFile(path.join(distRoot, "pwa-policy.js"), "self.WEB01B_PWA_POLICY={};");
  await writeFile(path.join(distRoot, "icon.png"), Buffer.from([137, 80, 78, 71]));
  const app = createServer({ port: 0, distRoot, apiTarget: "http://127.0.0.1:1" });
  await new Promise((resolve) => app.once("listening", resolve));
  const appPort = app.address().port;
  t.after(() => close(app));

  const manifest = await request(appPort, "/manifest.webmanifest");
  assert.equal(manifest.status, 200);
  assert.equal(manifest.contentType, "application/manifest+json; charset=utf-8");
  assert.equal(manifest.cacheControl, "no-cache");

  const sw = await request(appPort, "/sw.js");
  assert.equal(sw.status, 200);
  assert.equal(sw.contentType, "text/javascript; charset=utf-8");
  assert.equal(sw.cacheControl, "no-cache");

  const policy = await request(appPort, "/pwa-policy.js");
  assert.equal(policy.cacheControl, "no-cache");

  const icon = await request(appPort, "/icon.png");
  assert.equal(icon.contentType, "image/png");
});

// --- request-failure contract (D1) -------------------------------------------------
// Every case below proves two things: the failing request gets a bounded, well-formed
// outcome, and the SAME server still answers the next request. All sockets carry a hard
// timeout and every server/tmp dir is released in t.after, even when an assertion fails.
const BOUND_MS = 4000;

function raw(port, requestLine, extraHeaders = "") {
  return new Promise((resolve) => {
    const socket = net.connect(port, "127.0.0.1");
    let data = "";
    const finish = (reason) => { socket.destroy(); resolve({ data, reason }); };
    socket.setTimeout(BOUND_MS, () => finish("TIMEOUT"));
    socket.on("data", (chunk) => { data += chunk; });
    socket.on("close", () => finish("CLOSED"));
    socket.on("error", () => finish("ERROR"));
    socket.write(`${requestLine} HTTP/1.1\r\nHost: x\r\n${extraHeaders}Connection: close\r\n\r\n`);
  });
}
const statusOf = (r) => Number(r.data.split(" ")[1] ?? 0);
function bodyOf(r) {
  const [head, ...rest] = r.data.split("\r\n\r\n");
  let body = rest.join("\r\n\r\n");
  if (!/transfer-encoding: chunked/i.test(head)) return body;
  let decoded = "";
  while (body.length) {
    const eol = body.indexOf("\r\n");
    const size = parseInt(body.slice(0, eol), 16);
    if (!size) break;
    decoded += body.slice(eol + 2, eol + 2 + size);
    body = body.slice(eol + 2 + size + 2);
  }
  return decoded;
}
const headerOf = (r, name) => (r.data.split("\r\n\r\n")[0].split("\r\n").find((l) => l.toLowerCase().startsWith(`${name}:`)) ?? "").split(": ")[1];

async function harness(t, { populate = async () => {}, apiTarget = "http://127.0.0.1:1" } = {}) {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-fail-"));
  await populate(distRoot);
  const rejections = [];
  const onRejection = (error) => rejections.push(error);
  process.on("unhandledRejection", onRejection);
  const server = createServer({ port: 0, distRoot, apiTarget });
  const port = await new Promise((resolve) => server.once("listening", () => resolve(server.address().port)));
  t.after(async () => {
    process.off("unhandledRejection", onRejection);
    server.closeAllConnections?.();
    await close(server);
    await rm(distRoot, { recursive: true, force: true });
  });
  // A healthy answer that does not depend on dist: the API proxy answers 502 JSON when its target is down.
  const stillServing = async () => {
    const r = await raw(port, "GET /healthz");
    assert.equal(statusOf(r), 502, "server must still answer after the failure");
    assert.equal(JSON.parse(bodyOf(r)).error_code, "OPERATOR_API_UNAVAILABLE");
  };
  return { port, distRoot, rejections, stillServing };
}

test("before headers: missing bundle -> structured no-store 503, server keeps serving", { timeout: 15000 }, async (t) => {
  const h = await harness(t);
  for (const target of ["/", "/machine", "/assets/x.js"]) {
    const r = await raw(h.port, `GET ${target}`);
    assert.equal(statusOf(r), 503, target);
    assert.equal(headerOf(r, "cache-control"), "no-store");
    assert.equal(JSON.parse(bodyOf(r)).error_code, "FRONTEND_ASSET_UNAVAILABLE");
    await h.stillServing();
  }
  assert.deepEqual(h.rejections, [], "no unhandled rejection");
});

test("before headers: stat failure on the fallback (symlink loop) -> 503, server keeps serving", { timeout: 15000 }, async (t) => {
  const h = await harness(t, { populate: async (d) => { await symlink("index.html", path.join(d, "index.html")); } });
  const r = await raw(h.port, "GET /machine");
  assert.equal(statusOf(r), 503);
  assert.equal(headerOf(r, "cache-control"), "no-store");
  await h.stillServing();
  assert.deepEqual(h.rejections, []);
});

test("resolution: undecodable path is not a crash and not a traversal (served as SPA fallback)", { timeout: 15000 }, async (t) => {
  const h = await harness(t, { populate: async (d) => { await writeFile(path.join(d, "index.html"), "<main>operator</main>"); } });
  for (const target of ["/%", "/%00", "/%ff", "/..%2f..%2fetc/passwd", "/a/../../etc/passwd"]) {
    const r = await raw(h.port, `GET ${target}`);
    assert.equal(statusOf(r), 200, target);
    assert.equal(bodyOf(r), "<main>operator</main>", `${target} must only ever yield the SPA shell`);
  }
  await h.stillServing();
  assert.deepEqual(h.rejections, []);
});

test("request target that is not a valid URL -> 400 structured, server keeps serving", { timeout: 15000 }, async (t) => {
  const h = await harness(t);
  const r = await raw(h.port, "GET //");
  assert.equal(statusOf(r), 400);
  assert.equal(headerOf(r, "cache-control"), "no-store");
  assert.equal(JSON.parse(bodyOf(r)).error_code, "INVALID_REQUEST_URL");
  await h.stillServing();
  assert.deepEqual(h.rejections, [], "GET // used to reject inside the handler and kill the process");
});

test("bytes the HTTP parser rejects never reach the handler (proxy path cannot throw ERR_UNESCAPED_CHARACTERS)", { timeout: 15000 }, async (t) => {
  const h = await harness(t);
  const r = await raw(h.port, "GET /api/\u00ff");
  assert.equal(statusOf(r), 400, "rejected by the parser before our code");
  await h.stillServing();
});

test("after headers: read error mid-response closes only that connection", { timeout: 15000 }, async (t) => {
  // index.html is a directory: stat succeeds (so headers go out), createReadStream then fails with EISDIR.
  const h = await harness(t, { populate: async (d) => { await mkdir(path.join(d, "index.html")); } });
  const r = await raw(h.port, "GET /");
  assert.notEqual(r.reason, "TIMEOUT", "connection must be terminated, not left hanging");
  assert.ok(!r.data.includes("operator"), "no partial bundle content");
  await h.stillServing();
  assert.deepEqual(h.rejections, []);
});

test("after headers: upstream API aborts mid-body -> client connection ends, server keeps serving", { timeout: 15000 }, async (t) => {
  const upstream = http.createServer((req, res) => {
    res.writeHead(200, { "content-type": "application/json", "content-length": "1000" });
    res.write("{\"partial\":");
    setTimeout(() => req.socket.destroy(), 50);
  });
  const upstreamPort = await new Promise((resolve) => upstream.listen(0, "127.0.0.1", () => resolve(upstream.address().port)));
  t.after(async () => { upstream.closeAllConnections?.(); await close(upstream); });
  const h = await harness(t, { apiTarget: `http://127.0.0.1:${upstreamPort}` });
  const r = await raw(h.port, "GET /api/operator/v1/snapshot");
  assert.notEqual(r.reason, "TIMEOUT", "client must not hang on a truncated upstream body");
  assert.equal(headerOf(r, "cache-control"), "no-store");
  // The upstream still answers 200-then-abort, so "still serving" is shown on a static-independent 405.
  const after = await raw(h.port, "POST /");
  assert.equal(statusOf(after), 405);
  assert.deepEqual(h.rejections, []);
});

test("HEAD on a failing bundle yields the same governed 503 without a body", { timeout: 15000 }, async (t) => {
  const h = await harness(t);
  const r = await raw(h.port, "HEAD /");
  assert.equal(statusOf(r), 503);
  await h.stillServing();
});

test("WEB-01G port contract: 8181 by default, explicit override strictly validated (M1-C5 F1-b)", () => {
  assert.equal(FRONTEND_PORT, 8181);
  assert.equal(resolveFrontendPort(undefined), 8181);
  for (const ok of [["1024", 1024], ["8182", 8182], ["65535", 65535]]) assert.equal(resolveFrontendPort(ok[0]), ok[1]);
  for (const bad of ["", " ", "0", "80", "1023", "65536", "99999", "-8181", "+8181", "8181.0", "8.181e3", "0x1ff5", "08181", "8181 ", " 8181", "abc", "NaN", "Infinity", "123456"]) {
    assert.throws(() => resolveFrontendPort(bad), /INVALID_CAT_WEB_PORT/, `must refuse ${JSON.stringify(bad)}`);
  }
});

test("WEB-01G entrypoint refuses an invalid CAT_WEB_PORT before listening", async () => {
  const { spawnSync } = await import("node:child_process");
  const entry = fileURLToPath(new URL("./web01_local_frontend_server.mjs", import.meta.url));
  for (const bad of ["0", "70000", "abc", ""]) {
    const run = spawnSync(process.execPath, [entry], { env: { ...process.env, CAT_WEB_PORT: bad }, encoding: "utf8", timeout: 5000 });
    assert.equal(run.status, 2, `exit code for ${JSON.stringify(bad)}`);
    assert.match(run.stderr, /WEB_01G_CONFIG_REFUSED=INVALID_CAT_WEB_PORT/);
    assert.doesNotMatch(run.stdout, /LISTENING/);
  }
});

test("WEB-01G binds loopback only and keeps the declared Radar Spot target and timeout", () => {
  assert.equal(LOOPBACK_HOST, "127.0.0.1");
  assert.equal(SPOT_RADAR_API_PREFIX, "/api/operator/v1/spot-radar/");
  const target = new URL(SPOT_RADAR_API_TARGET);
  assert.equal(target.hostname, "127.0.0.1"); assert.equal(target.port, "18906"); assert.equal(target.protocol, "http:");
  assert.equal(UPSTREAM_TIMEOUT_MS, 10000);
});

test("routes only the Radar Spot prefix to its loopback target, GET/HEAD only, non-cacheable", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const seen = { operator: [], radar: [] };
  const operator = http.createServer((req, res) => { seen.operator.push(`${req.method} ${req.url}`); res.writeHead(200, { "cache-control": "max-age=600" }); res.end('{"from":"operator"}'); });
  const radar = http.createServer((req, res) => { seen.radar.push(`${req.method} ${req.url}`); res.writeHead(200, { "cache-control": "public, max-age=600" }); res.end('{"from":"radar"}'); });
  const operatorPort = await listen(operator); const radarPort = await listen(radar);
  const app = createServer({ port: 0, distRoot, apiTarget: `http://127.0.0.1:${operatorPort}`, spotRadarTarget: `http://127.0.0.1:${radarPort}` });
  await new Promise((resolve) => app.once("listening", resolve));
  assert.equal(app.address().address, "127.0.0.1", "listener must stay on loopback");
  const appPort = app.address().port;
  t.after(async () => { await close(app); await close(operator); await close(radar); });

  const scanner = await request(appPort, "/api/operator/v1/spot-radar/scanner");
  assert.equal(scanner.text, '{"from":"radar"}'); assert.equal(scanner.cacheControl, "no-store");
  const head = await request(appPort, "/api/operator/v1/spot-radar/scanner", "HEAD");
  assert.equal(head.status, 200); assert.equal(head.text, "");
  for (const lookalike of ["/api/operator/v1/spot-radar", "/api/operator/v1/spot-radarX/scanner", "/api/operator/v1/market"]) {
    const other = await request(appPort, lookalike);
    assert.equal(other.text, '{"from":"operator"}', `${lookalike} must stay on the Operator API`);
  }
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    const refused = await request(appPort, "/api/operator/v1/spot-radar/scanner", method);
    assert.equal(refused.status, 405); assert.match(refused.text, /METHOD_NOT_ALLOWED/); assert.equal(refused.cacheControl, "no-store");
  }
  assert.deepEqual(seen.radar, ["GET /api/operator/v1/spot-radar/scanner", "HEAD /api/operator/v1/spot-radar/scanner"], "mutations never reach the Radar Spot API");
  assert.ok(seen.operator.every((line) => line.startsWith("GET ")), "mutations never reach the Operator API");
});

test("Radar Spot transport failure is explicit and non-cacheable", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const app = createServer({ port: 0, distRoot, apiTarget: "http://127.0.0.1:1", spotRadarTarget: "http://127.0.0.1:1" });
  await new Promise((resolve) => app.once("listening", resolve));
  t.after(() => close(app));
  const failed = await request(app.address().port, "/api/operator/v1/spot-radar/scanner");
  assert.equal(failed.status, 502); assert.match(failed.text, /OPERATOR_API_UNAVAILABLE/); assert.equal(failed.cacheControl, "no-store");
});

test("exception unique : POST relayé seulement vers la route de rythme d'agent, corps borné, identité Tailscale vérifiée", async (t) => {
  const seen = [];
  const api = http.createServer((req, res) => {
    let b = ""; req.on("data", (c) => { b += c; });
    req.on("end", () => {
      seen.push({ m: req.method, u: req.url, h: req.headers["x-cat-operator"], who: req.headers["x-cat-operator-identity"] ?? null, ts: req.headers["tailscale-user-login"] ?? null, tok: req.headers["x-cat-relay-token"] ?? null, ct: req.headers["content-type"], b });
      res.writeHead(202, { "content-type": "application/json" }); res.end("{}");
    });
  }).listen(0, "127.0.0.1");
  await new Promise((r) => api.once("listening", r));
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const TOKEN = "ab".repeat(32);
  const app = createServer({ port: 0, distRoot, apiTarget: `http://127.0.0.1:${api.address().port}`, operatorLogins: parseOperatorLogins("Operator@Example.test"), relayToken: TOKEN });
  await new Promise((resolve) => app.once("listening", resolve));
  t.after(() => { close(app); api.close(); });
  const base = `http://127.0.0.1:${app.address().port}/api/operator/v1/agent-invocations/repository-cartographer`;
  const H = { "content-type": "application/json", "x-cat-operator": "schedule" };
  const ok = await fetch(`${base}/schedule`, { method: "POST", headers: { ...H, "tailscale-user-login": "operator@example.test", "x-cat-operator-identity": "forged@example.test", "x-cat-relay-token": "cd".repeat(32) }, body: '{"rhythm":"1h"}' });
  assert.equal(ok.status, 202); assert.equal(ok.headers.get("cache-control"), "no-store");
  assert.deepEqual(seen, [{ m: "POST", u: "/api/operator/v1/agent-invocations/repository-cartographer/schedule", h: "schedule", who: "operator@example.test", ts: null, tok: TOKEN, ct: "application/json", b: '{"rhythm":"1h"}' }],
    "identité réécrite depuis Tailscale, jeton du relais imposé ; valeurs fournies par le client non transmises");
  // identité absente, forgée seule, ou non autorisée : refus au relais, rien n'atteint l'API
  const noId = await fetch(`${base}/schedule`, { method: "POST", headers: H, body: '{"rhythm":"1h"}' });
  assert.equal(noId.status, 401); assert.match(await noId.text(), /OPERATOR_IDENTITY_REQUIRED/);
  assert.equal((await fetch(`${base}/schedule`, { method: "POST", headers: { ...H, "x-cat-operator-identity": "operator@example.test" }, body: '{"rhythm":"1h"}' })).status, 401);
  const other = await fetch(`${base}/schedule`, { method: "POST", headers: { ...H, "tailscale-user-login": "intruder@example.test" }, body: '{"rhythm":"1h"}' });
  assert.equal(other.status, 403); assert.match(await other.text(), /OPERATOR_NOT_AUTHORIZED/);
  for (const p of [`${base}/history`, `${base}/schedule/x`, `${base}`]) {
    assert.equal((await fetch(p, { method: "POST", body: "{}" })).status, 405);
  }
  assert.equal((await fetch(`${base}/schedule`, { method: "PUT", body: "{}" })).status, 405);
  const big = await fetch(`${base}/schedule`, { method: "POST", headers: { ...H, "tailscale-user-login": "operator@example.test" }, body: "x".repeat(1000) }).catch(() => null);
  if (big) assert.equal(big.status, 413);
  assert.equal(seen.length, 1);
});

test("exception unique : sans liste d'opérateurs, aucune écriture n'est relayée", async (t) => {
  let reached = 0;
  const api = http.createServer((req, res) => { reached += 1; res.end("{}"); }).listen(0, "127.0.0.1");
  await new Promise((r) => api.once("listening", r));
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const app = createServer({ port: 0, distRoot, apiTarget: `http://127.0.0.1:${api.address().port}`, operatorLogins: parseOperatorLogins("") });
  await new Promise((resolve) => app.once("listening", resolve));
  t.after(() => { close(app); api.close(); });
  const url = `http://127.0.0.1:${app.address().port}/api/operator/v1/agent-invocations/repository-cartographer/schedule`;
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json", "x-cat-operator": "schedule", "tailscale-user-login": "operator@example.test" }, body: '{"rhythm":"1h"}' });
  assert.equal(r.status, 403); assert.match(await r.text(), /OPERATOR_ALLOWLIST_UNSET/);
  assert.equal(reached, 0);
});

test("journal des refus au relais : une ligne JSON, sans corps ni en-tête", () => {
  const lines = [];
  relayAudit("/api/operator/v1/agent-invocations/repository-cartographer/schedule", null, 401, "OPERATOR_IDENTITY_REQUIRED", (l) => lines.push(l));
  relayAudit("/api/operator/v1/agent-invocations/x/../schedule", "intruder@example.test", 403, "OPERATOR_NOT_AUTHORIZED", (l) => lines.push(l));
  const [a, b] = lines.map((l) => JSON.parse(l));
  assert.deepEqual(Object.keys(a).sort(), ["agent", "event", "http_status", "identity", "reason", "ts"]);
  assert.equal(a.event, "cat.schedule.relay_refusal"); assert.equal(a.agent, "repository-cartographer"); assert.equal(a.identity, null);
  assert.match(a.ts, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  assert.equal(b.agent, null); assert.equal(b.http_status, 403);
});

test("transport relais → API : sans jeton, aucune écriture relayée ; fichier de jeton strict", async (t) => {
  let reached = 0;
  const api = http.createServer((req, res) => { reached += 1; res.end("{}"); }).listen(0, "127.0.0.1");
  await new Promise((r) => api.once("listening", r));
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  const app = createServer({ port: 0, distRoot, apiTarget: `http://127.0.0.1:${api.address().port}`, operatorLogins: parseOperatorLogins("op@example.test"), relayToken: null });
  await new Promise((resolve) => app.once("listening", resolve));
  t.after(() => { close(app); api.close(); });
  const url = `http://127.0.0.1:${app.address().port}/api/operator/v1/agent-invocations/repository-cartographer/schedule`;
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json", "x-cat-operator": "schedule", "tailscale-user-login": "op@example.test" }, body: '{"rhythm":"1h"}' });
  assert.equal(r.status, 403); assert.match(await r.text(), /RELAY_TOKEN_UNSET/);
  assert.equal(reached, 0);

  const dir = await mkdtemp(path.join(tmpdir(), "web01g-token-"));
  const good = path.join(dir, "good"); await writeFile(good, "ab".repeat(32) + "\n", { mode: 0o640 });
  assert.equal(readRelayToken(good), "ab".repeat(32));
  const world = path.join(dir, "world"); await writeFile(world, "ab".repeat(32), { mode: 0o644 });
  assert.equal(readRelayToken(world), null);
  const link = path.join(dir, "link"); await symlink(good, link);
  assert.equal(readRelayToken(link), null);
  const short = path.join(dir, "short"); await writeFile(short, "abc", { mode: 0o600 });
  assert.equal(readRelayToken(short), null);
  assert.equal(readRelayToken(path.join(dir, "absent")), null);
  assert.equal(readRelayToken(""), null);
});

test("activation par socket systemd : seulement si LISTEN_PID désigne ce processus", () => {
  assert.equal(systemdListenFd({ LISTEN_FDS: "1", LISTEN_PID: "42" }, 42), 3);
  assert.equal(systemdListenFd({ LISTEN_FDS: "1", LISTEN_PID: "41" }, 42), null);
  assert.equal(systemdListenFd({ LISTEN_FDS: "2", LISTEN_PID: "42" }, 42), null);
  assert.equal(systemdListenFd({}, 42), null);
});
