// Node-native runtime contract; intentionally outside Vitest discovery.
import assert from "node:assert/strict";
import { mkdtemp, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
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

test("a missing frontend bundle yields a no-store 503 and keeps the process serving", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-empty-dist-"));
  const server = createServer({ port: 0, distRoot });
  const port = await new Promise((resolve) => server.once("listening", () => resolve(server.address().port)));
  t.after(() => close(server));

  const first = await request(port, "/");
  assert.equal(first.status, 503);
  assert.equal(first.cacheControl, "no-store");
  assert.equal(JSON.parse(first.text).error_code, "FRONTEND_ASSET_UNAVAILABLE");

  const second = await request(port, "/machine");
  assert.equal(second.status, 503, "server must still answer after the first failure");
});
