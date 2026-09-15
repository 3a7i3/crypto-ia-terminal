// WEB-01B source-level PWA safety contract.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = path.join(ROOT, "public");

function pngDimensions(buffer) {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  assert.deepEqual(buffer.subarray(0, 8), signature, "icon must be PNG");
  assert.equal(buffer.toString("ascii", 12, 16), "IHDR");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

async function loadWorkerHarness() {
  const policySource = await readFile(path.join(PUBLIC, "pwa-policy.js"), "utf8");
  const workerSource = await readFile(path.join(PUBLIC, "sw.js"), "utf8");
  const listeners = new Map();
  const cache = {
    addAll: async () => undefined,
    match: async () => undefined,
    put: async () => undefined,
  };
  const self = {
    location: { origin: "https://operator.private.example" },
    clients: { claim: async () => undefined },
    skipWaiting: async () => undefined,
    addEventListener: (type, handler) => listeners.set(type, handler),
  };
  const context = vm.createContext({
    self,
    URL,
    Response,
    Promise,
    Object,
    console,
    importScripts: () => undefined,
    caches: {
      open: async () => cache,
      keys: async () => [],
      delete: async () => true,
    },
    fetch: async () => new Response("static", { status: 200 }),
  });
  vm.runInContext(policySource, context, { filename: "pwa-policy.js" });
  vm.runInContext(workerSource, context, { filename: "sw.js" });
  return { self, listeners };
}

test("manifest is installable and carries the required Chromium icon sizes", async () => {
  const manifest = JSON.parse(await readFile(path.join(PUBLIC, "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.start_url, "/");
  assert.equal(manifest.scope, "/");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.prefer_related_applications, false);
  assert.ok(manifest.name || manifest.short_name);

  const sizes = new Set(manifest.icons.map((icon) => icon.sizes));
  assert.ok(sizes.has("192x192"));
  assert.ok(sizes.has("512x512"));

  for (const size of [192, 512]) {
    const icon = await readFile(path.join(PUBLIC, "icons", `operator-${size}.png`));
    assert.deepEqual(pngDimensions(icon), { width: size, height: size });
  }
});

test("cache policy excludes every Operator API and health request", async () => {
  const { self } = await loadWorkerHarness();
  const policy = self.WEB01B_PWA_POLICY;
  const origin = self.location.origin;

  for (const pathname of [
    "/api",
    "/api/operator/v1/snapshot",
    "/api/operator/v1/market?limit=20",
    "/healthz",
    "/healthz/ready",
  ]) {
    assert.equal(
      policy.shouldHandleRequest({ method: "GET", url: `${origin}${pathname}` }, origin),
      false,
      `${pathname} must remain network-only`,
    );
  }

  assert.equal(policy.shouldHandleRequest({ method: "POST", url: `${origin}/asset.js` }, origin), false);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: "https://example.com/asset.js" }, origin), false);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: `${origin}/assets/app.js` }, origin), true);
});

test("actual service worker fetch listener never calls respondWith for runtime truth", async () => {
  const { self, listeners } = await loadWorkerHarness();
  const fetchListener = listeners.get("fetch");
  assert.equal(typeof fetchListener, "function");

  for (const pathname of ["/api/operator/v1/snapshot", "/api/operator/v1/market", "/healthz"]) {
    let intercepted = false;
    fetchListener({
      request: { method: "GET", url: `${self.location.origin}${pathname}`, mode: "cors" },
      respondWith: () => {
        intercepted = true;
      },
    });
    assert.equal(intercepted, false, `${pathname} must bypass Service Worker interception`);
  }

  let staticIntercepted = false;
  fetchListener({
    request: { method: "GET", url: `${self.location.origin}/assets/app.js`, mode: "cors" },
    respondWith: () => {
      staticIntercepted = true;
    },
  });
  assert.equal(staticIntercepted, true, "same-origin static assets should be shell-cache eligible");
});
