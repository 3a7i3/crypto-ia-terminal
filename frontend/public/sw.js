// WEB-01B private PWA service worker.
// Scientific invariant: cache the static application shell only. Operator API
// and health requests are never intercepted and therefore can never be
// replayed from Cache Storage as if they were current runtime truth.
importScripts("/pwa-policy.js");

const SHELL_CACHE_PREFIX = "crypto-ai-operator-shell-";
const SHELL_CACHE = `${SHELL_CACHE_PREFIX}v1`;
const PRECACHE_URLS = [
  "/",
  "/manifest.webmanifest",
  "/pwa-policy.js",
  "/icons/operator-192.png",
  "/icons/operator-512.png",
];

const policy = self.WEB01B_PWA_POLICY;
if (!policy || typeof policy.shouldHandleRequest !== "function") {
  throw new Error("WEB-01B PWA cache policy unavailable");
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith(SHELL_CACHE_PREFIX) && name !== SHELL_CACHE)
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

async function networkFirstNavigation(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && response.type !== "opaque") {
      await cache.put("/", response.clone());
    }
    return response;
  } catch {
    const shell = await cache.match("/");
    if (shell) return shell;
    return new Response("Operator shell unavailable while disconnected.", {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
}

async function cacheFirstStatic(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok && response.type !== "opaque") {
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  // Returning without respondWith() is deliberate: /api/* and /healthz stay
  // under normal browser networking and are never eligible for Cache Storage.
  if (!policy.shouldHandleRequest(event.request, self.location.origin)) return;

  if (event.request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(event.request));
    return;
  }

  event.respondWith(cacheFirstStatic(event.request));
});
