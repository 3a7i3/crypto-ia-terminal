// Node-native runtime contract; intentionally outside Vitest discovery.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createServer, isMainEntrypoint, resolveFrontendPort, FRONTEND_PORT, LOOPBACK_HOST, SPOT_RADAR_API_PREFIX, SPOT_RADAR_API_TARGET, UPSTREAM_TIMEOUT_MS } from "./web01_local_frontend_server.mjs";

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
