// WEB-01G local frontend runtime. This server deliberately exposes one local
// read-only presentation surface only: static frontend assets plus GET/HEAD
// proxying to the loopback Operator API. It never reads runtime artifacts.
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const LOOPBACK_HOST = "127.0.0.1";
export const FRONTEND_PORT = 8181;
export const OPERATOR_API_TARGET = "http://127.0.0.1:8090";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_DIST_ROOT = path.join(ROOT, "dist");
const HOP_BY_HOP_HEADERS = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"]);
const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webmanifest", "application/manifest+json; charset=utf-8"],
  [".woff2", "font/woff2"],
]);

function apiError(response, status, code, message) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify({ error_code: code, error_message: message }));
}

function methodAllowed(request) {
  return request.method === "GET" || request.method === "HEAD";
}

function isApiPath(pathname) {
  return pathname === "/api" || pathname.startsWith("/api/") || pathname === "/healthz";
}

function copyProxyHeaders(headers) {
  const safe = {};
  for (const [name, value] of Object.entries(headers)) {
    if (value !== undefined && !HOP_BY_HOP_HEADERS.has(name.toLowerCase())) safe[name] = value;
  }
  return safe;
}

function proxyToOperatorApi(request, response, target) {
  const transport = target.protocol === "https:" ? https : http;
  const upstream = transport.request({
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port,
    method: request.method,
    path: request.url,
    headers: { host: target.host },
  }, (upstreamResponse) => {
    const headers = copyProxyHeaders(upstreamResponse.headers);
    // WEB-01B runtime truth must remain network-only from the browser/PWA
    // perspective even when an upstream route omits explicit cache metadata.
    // Override any upstream cache directive at the presentation boundary.
    headers["cache-control"] = "no-store";
    response.writeHead(upstreamResponse.statusCode ?? 502, headers);
    if (request.method === "HEAD") response.end();
    else upstreamResponse.pipe(response);
  });
  upstream.once("error", () => apiError(response, 502, "OPERATOR_API_UNAVAILABLE", "Local Operator API is unavailable."));
  request.pipe(upstream);
}

async function resolveStaticPath(distRoot, pathname) {
  let decoded;
  try { decoded = decodeURIComponent(pathname); } catch { return null; }
  const candidate = path.resolve(distRoot, `.${decoded}`);
  if (candidate !== distRoot && !candidate.startsWith(`${distRoot}${path.sep}`)) return null;
  try {
    return (await stat(candidate)).isFile() ? candidate : null;
  } catch {
    return null;
  }
}

async function serveFile(response, filename, method) {
  const info = await stat(filename);
  const basename = path.basename(filename);
  const ext = path.extname(filename);
  const headers = {
    "content-type": MIME_TYPES.get(ext) ?? "application/octet-stream",
    "content-length": info.size,
    "x-content-type-options": "nosniff",
  };
  if (basename === "sw.js" || basename === "pwa-policy.js" || ext === ".webmanifest") {
    headers["cache-control"] = "no-cache";
  }
  response.writeHead(200, headers);
  if (method === "HEAD") response.end();
  else createReadStream(filename).pipe(response);
}

export function createServer({ host = LOOPBACK_HOST, port = FRONTEND_PORT, distRoot = DEFAULT_DIST_ROOT, apiTarget = OPERATOR_API_TARGET } = {}) {
  const target = new URL(apiTarget);
  return http.createServer(async (request, response) => {
    const url = new URL(request.url ?? "/", `http://${host}`);
    if (!methodAllowed(request)) return apiError(response, 405, "METHOD_NOT_ALLOWED", "WEB-01G accepts GET and HEAD only.");
    if (isApiPath(url.pathname)) return proxyToOperatorApi(request, response, target);

    const requested = await resolveStaticPath(distRoot, url.pathname);
    // SPA fallback applies only to non-API frontend routes; API paths never
    // reach this branch, including when the Operator API is unavailable.
    await serveFile(response, requested ?? path.join(distRoot, "index.html"), request.method);
  }).listen(port, host);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  createServer().on("listening", () => console.log(`WEB_01G_LOCAL_FRONTEND_LISTENING=${LOOPBACK_HOST}:${FRONTEND_PORT}`));
}
