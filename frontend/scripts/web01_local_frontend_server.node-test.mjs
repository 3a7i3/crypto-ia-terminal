// Node-native runtime contract; intentionally outside Vitest discovery.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createServer, isMainEntrypoint } from "./web01_local_frontend_server.mjs";

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
