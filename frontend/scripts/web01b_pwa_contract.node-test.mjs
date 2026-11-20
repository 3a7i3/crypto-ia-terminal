// WEB-01B source-level PWA safety contract.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = path.join(ROOT, "public");
const SRC = path.join(ROOT, "src");

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
  const precached = [];
  const cache = {
    addAll: async (urls) => { precached.push(...urls); },
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
  return { self, listeners, precached };
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

test("cache policy excludes runtime truth and only allow-lists known shell resources", async () => {
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
      policy.shouldHandleRequest({ method: "GET", url: `${origin}${pathname}`, mode: "cors" }, origin),
      false,
      `${pathname} must remain network-only`,
    );
  }

  // Fail-closed future boundary: an unknown same-origin GET must not become
  // cacheable merely because it does not currently live below /api/*.
  for (const pathname of ["/future-financial-state.json", "/runtime/telemetry", "/snapshot.json"]) {
    assert.equal(
      policy.shouldHandleRequest({ method: "GET", url: `${origin}${pathname}`, mode: "cors" }, origin),
      false,
      `${pathname} must not be implicitly cacheable`,
    );
  }

  assert.equal(policy.shouldHandleRequest({ method: "POST", url: `${origin}/assets/app.js`, mode: "cors" }, origin), false);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: "https://example.com/assets/app.js", mode: "cors" }, origin), false);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: `${origin}/assets/app.js`, mode: "cors" }, origin), true);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: `${origin}/icons/operator-192.png`, mode: "cors" }, origin), true);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: `${origin}/manifest.webmanifest`, mode: "cors" }, origin), true);
  assert.equal(policy.shouldHandleRequest({ method: "GET", url: `${origin}/operator/market`, mode: "navigate" }, origin), true);
});

test("actual service worker fetch listener never calls respondWith for runtime or unknown data paths", async () => {
  const { self, listeners } = await loadWorkerHarness();
  const fetchListener = listeners.get("fetch");
  assert.equal(typeof fetchListener, "function");

  for (const pathname of [
    "/api/operator/v1/snapshot",
    "/api/operator/v1/market",
    "/healthz",
    "/future-financial-state.json",
  ]) {
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

test("service-worker registration keeps same-session replacement reload armed without first-install reload", async () => {
  const source = await readFile(path.join(SRC, "lib", "pwaRegistration.ts"), "utf8");
  assert.match(source, /let hasSeenController = navigator\.serviceWorker\.controller !== null/);
  assert.match(source, /navigator\.serviceWorker\.addEventListener\("controllerchange"/);
  assert.match(source, /if \(!hasSeenController\) \{\s*hasSeenController = true;\s*return;\s*\}/);
  assert.match(source, /if \(reloadingForUpdate\) return;/);
  assert.match(source, /reloadingForUpdate = true;\s*window\.location\.reload\(\)/);
  assert.match(source, /registration\.update\(\)/);

  const listenerStart = source.indexOf('navigator.serviceWorker.addEventListener("controllerchange"');
  const listenerEnd = source.indexOf("\n\n    try {", listenerStart);
  assert.ok(listenerStart >= 0 && listenerEnd > listenerStart, "controllerchange listener block must be present");
  const listenerBlock = source.slice(listenerStart, listenerEnd);
  assert.doesNotMatch(listenerBlock, /once:\s*true/, "controllerchange listener must survive the first-install claim");
});


test("brand URLs carry content identity and agree across PWA, document, header and precache", async () => {
  const manifest = JSON.parse(await readFile(path.join(PUBLIC, "manifest.webmanifest"), "utf8"));
  const { listeners, precached } = await loadWorkerHarness();
  let installed;
  listeners.get("install")({ waitUntil: (promise) => { installed = promise; } });
  await installed;
  for (const icon of manifest.icons) {
    assert.match(icon.src, /^\/icons\/[^/]+\.png$/, "same-origin flat icon path required");
    const bytes = await readFile(path.join(PUBLIC, icon.src.slice(1)));
    const identity = createHash("sha256").update(bytes).digest("hex").slice(0, 12);
    assert.ok(icon.src.includes(identity), "mutable icon URL must include its content hash to escape an existing cache");
    const size = Number(icon.sizes.split("x")[0]);
    assert.deepEqual(pngDimensions(bytes), { width: size, height: size });
    assert.ok(precached.includes(icon.src), "worker must precache the exact versioned manifest icon");
  }
  const primary = manifest.icons.find((icon) => icon.sizes === "192x192").src;
  const document = await readFile(path.join(ROOT, "index.html"), "utf8");
  for (const rel of ["icon", "apple-touch-icon"]) {
    const match = document.match(new RegExp('rel="' + rel + '"\\s+href="([^"]+)"'));
    assert.equal(match?.[1], primary, rel + " must use the same content-addressed icon");
  }
  const frame = await readFile(path.join(SRC, "shells", "AppFrame.tsx"), "utf8");
  assert.ok(frame.includes('src="' + primary + '"'), "header must use the versioned PWA icon");
});

// M1-D2-PWA: release identity and upgrade/rollback lifecycle proof.
// This identity must change whenever the deployed application shell changes.
const TARGET_SHELL_CACHE = "crypto-ai-operator-shell-cat-footprint-finance-v6-rc1";
const PRIOR_SHELL_CACHE = "crypto-ai-operator-shell-cat-workboard-582-finance-v6";

async function createTransitionHarness(workerSource, buckets) {
  const policySource = await readFile(path.join(PUBLIC, "pwa-policy.js"), "utf8");
  const listeners = new Map();
  const lifecycle = { skipWaiting: 0, claim: 0 };
  const fakeCaches = {
    async keys() { return [...buckets.keys()]; },
    async delete(name) { return buckets.delete(name); },
    async open(name) {
      if (!buckets.has(name)) buckets.set(name, new Map());
      const entries = buckets.get(name);
      return {
        async addAll(urls) { for (const url of urls) entries.set(url, "precached-static-shell"); },
        async match(url) { return entries.get(typeof url === "string" ? url : new URL(url.url).pathname); },
        async put(url, response) { entries.set(url, response); },
      };
    },
  };
  const self = {
    location: { origin: "https://operator.private.example" },
    clients: { async claim() { lifecycle.claim += 1; } },
    async skipWaiting() { lifecycle.skipWaiting += 1; },
    addEventListener(kind, handler) { listeners.set(kind, handler); },
  };
  const context = vm.createContext({
    self, URL, Response, Promise, Object, console,
    importScripts: () => undefined, caches: fakeCaches,
    fetch: async () => new Response("static", { status: 200 }),
  });
  vm.runInContext(policySource, context, { filename: "pwa-policy.js" });
  vm.runInContext(workerSource, context, { filename: "sw.js" });
  async function dispatch(type) {
    let completion;
    listeners.get(type)({ waitUntil: (pending) => { completion = pending; } });
    assert.ok(completion, type + " must call waitUntil");
    await completion;
  }
  return { dispatch, listeners, lifecycle, self };
}

test("Workboard scanner updates the exact shell cache identity and cleans only CAT shell caches", async () => {
  const workerSource = await readFile(path.join(PUBLIC, "sw.js"), "utf8");
  assert.ok(workerSource.includes("cat-footprint-finance-v6-rc1"),
    "the new release must change sw.js bytes and its cache identity");
  assert.ok(!workerSource.includes("cat-workboard-582-finance-v6"),
    "the previous release's cache identity must not be reused");
  const buckets = new Map([
    [PRIOR_SHELL_CACHE, new Map([["/", "old-shell"]])],
    ["other-product-offline-cache", new Map([["/", "keep-this"]])],
  ]);
  const upgraded = await createTransitionHarness(workerSource, buckets);
  await upgraded.dispatch("install");
  assert.ok(buckets.has(TARGET_SHELL_CACHE), "new shell must be precached before activation");
  assert.equal(upgraded.lifecycle.skipWaiting, 1, "updated worker should activate promptly");
  await upgraded.dispatch("activate");
  assert.equal(upgraded.lifecycle.claim, 1, "new worker should claim the open page");
  assert.equal(buckets.has(PRIOR_SHELL_CACHE), false, "old CAT shell cache must be removed");
  assert.ok(buckets.has(TARGET_SHELL_CACHE), "new CAT shell must survive activation");
  assert.ok(buckets.has("other-product-offline-cache"), "unrelated caches must be preserved");

  const fetchListener = upgraded.listeners.get("fetch");
  for (const pathname of ["/api/operator/v1/spot-radar/scanner", "/api/operator/v1/market-flow", "/healthz"]) {
    let intercepted = false;
    fetchListener({
      request: { method: "GET", mode: "cors", url: upgraded.self.location.origin + pathname },
      respondWith() { intercepted = true; },
    });
    assert.equal(intercepted, false, pathname + " must remain network-only after update");
  }

  // Rollback simulation: the former release used this same worker logic and
  // the old cache identity (read-only proof obtained at M1-D1).
  const priorSource = workerSource.replace("cat-footprint-finance-v6-rc1", "cat-workboard-582-finance-v6");
  assert.notEqual(priorSource, workerSource, "rollback must publish different service-worker bytes");
  const rolledBack = await createTransitionHarness(priorSource, buckets);
  await rolledBack.dispatch("install");
  await rolledBack.dispatch("activate");
  assert.equal(rolledBack.lifecycle.skipWaiting, 1);
  assert.equal(rolledBack.lifecycle.claim, 1);
  assert.equal(buckets.has(TARGET_SHELL_CACHE), false, "rollback must remove the new CAT shell cache");
  assert.ok(buckets.has(PRIOR_SHELL_CACHE), "rollback must restore the former CAT shell cache");
  assert.ok(buckets.has("other-product-offline-cache"), "rollback must preserve unrelated caches");
});
