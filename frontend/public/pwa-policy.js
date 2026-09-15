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

  function shouldHandleRequest(request, scopeOrigin) {
    if (!request || request.method !== "GET") return false;

    let url;
    try {
      url = new URL(request.url);
    } catch {
      return false;
    }

    if (url.origin !== scopeOrigin) return false;
    return !isRuntimeTruthPath(url.pathname);
  }

  globalScope.WEB01B_PWA_POLICY = Object.freeze({
    isRuntimeTruthPath,
    shouldHandleRequest,
  });
})(self);
