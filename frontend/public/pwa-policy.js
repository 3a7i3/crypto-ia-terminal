// WEB-01B cache boundary shared by the production service worker and tests.
// Runtime truth is deliberately outside Service Worker control: if the
// Operator API cannot be reached, fetch() must fail honestly in the React
// clients instead of receiving a cached telemetry response.
(function installWeb01bPwaPolicy(globalScope) {
  "use strict";

  function isRuntimeTruthPath(pathname) {
    return (
      pathname === "/api" ||
      pathname.startsWith("/api/") ||
      pathname === "/healthz" ||
      pathname.startsWith("/healthz/")
    );
  }

  // Fail closed: cache eligibility is an allow-list of known presentation
  // shell resources, never "every same-origin GET except today's API paths".
  // This prevents a future runtime/financial endpoint from becoming cacheable
  // merely because it is introduced outside /api/*.
  function isStaticShellPath(pathname) {
    return (
      pathname === "/manifest.webmanifest" ||
      pathname === "/pwa-policy.js" ||
      pathname.startsWith("/assets/") ||
      pathname.startsWith("/icons/")
    );
  }

  function shouldHandleRequest(request, scopeOrigin) {
    if (!request || request.method !== "GET") return false;

    let url;
    try {
      url = new URL(request.url);
    } catch {
      return false;
    }

    if (url.origin !== scopeOrigin) return false;
    if (isRuntimeTruthPath(url.pathname)) return false;

    // Navigations are shell-only: WEB-01G serves the static React index for
    // frontend routes. Data requests remain excluded by the runtime boundary
    // above and by the static allow-list below.
    if (request.mode === "navigate") return true;
    return isStaticShellPath(url.pathname);
  }

  globalScope.WEB01B_PWA_POLICY = Object.freeze({
    isRuntimeTruthPath,
    isStaticShellPath,
    shouldHandleRequest,
  });
})(self);
