// Node-native runtime contract; intentionally outside Vitest discovery.
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { createServer } from "./web01_local_frontend_server.mjs";

function listen(server) { return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port))); }
function close(server) { return new Promise((resolve) => server.close(resolve)); }
async function request(port, pathname, method = "GET") {
  const response = await fetch(`http://127.0.0.1:${port}${pathname}`, { method });
  return { status: response.status, text: await response.text(), contentType: response.headers.get("content-type") };
}

test("serves frontend routes but never applies SPA fallback to API paths", async (t) => {
  const distRoot = await mkdtemp(path.join(tmpdir(), "web01g-dist-"));
  await writeFile(path.join(distRoot, "index.html"), "<main>operator</main>");
  await writeFile(path.join(distRoot, "asset.js"), "console.log('asset')");
  const api = http.createServer((req, res) => {
    if (req.url === "/api/operator/v1/market") return res.end('{"market":true}');
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
  const missingApi = await request(appPort, "/api/missing");
  assert.equal(missingApi.status, 404); assert.match(missingApi.text, /API_NOT_FOUND/); assert.doesNotMatch(missingApi.text, /operator/);
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
  const unavailable = await request(appPort, "/api/operator/v1/market");
  assert.equal(unavailable.status, 502); assert.match(unavailable.text, /OPERATOR_API_UNAVAILABLE/);
});
