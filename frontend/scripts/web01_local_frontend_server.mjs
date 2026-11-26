// WEB-01G local frontend runtime. This server deliberately exposes one local
// read-only presentation surface only: static frontend assets plus GET/HEAD
// proxying to the loopback Operator API. It never reads runtime artifacts.
import { closeSync, constants as fsc, createReadStream, fstatSync, openSync, readSync, realpathSync } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { startPaperBalanceHistory } from "./paper-balance-history.mjs";
import { fileURLToPath } from "node:url";

export const LOOPBACK_HOST = "127.0.0.1";
export const FRONTEND_PORT = 8181;
export const FRONTEND_PORT_ENV = "CAT_WEB_PORT";
export const OPERATOR_API_TARGET = "http://127.0.0.1:8090";
// Radar Spot read API (loopback only). Only this exact path prefix is routed
// there; every other API path keeps the Operator API target.
export const SPOT_RADAR_API_PREFIX = "/api/operator/v1/spot-radar/";
export const SPOT_RADAR_API_TARGET = "http://127.0.0.1:18906";
export const UPSTREAM_TIMEOUT_MS = 10000;

// The contractual port is FRONTEND_PORT. An explicit CAT_WEB_PORT may select
// another unprivileged port; anything else (empty, signed, decimal, leading
// zero, out of 1024-65535) is refused rather than silently replaced.
export function resolveFrontendPort(raw = process.env[FRONTEND_PORT_ENV]) {
  if (raw === undefined) return FRONTEND_PORT;
  if (typeof raw !== "string" || !/^[1-9][0-9]{3,4}$/.test(raw)) throw new Error("INVALID_CAT_WEB_PORT");
  const port = Number(raw);
  if (port < 1024 || port > 65535) throw new Error("INVALID_CAT_WEB_PORT");
  return port;
}

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

export function isMainEntrypoint(entryPath = process.argv[1], moduleUrl = import.meta.url) {
  if (!entryPath) return false;
  try {
    return realpathSync(entryPath) === realpathSync(fileURLToPath(moduleUrl));
  } catch {
    return false;
  }
}

function apiError(response, status, code, message) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify({ error_code: code, error_message: message }));
}

// Exception gouvernée UNIQUE (opérateur, 2026-11-22 07:23Z, ratifiée P6-GOV-01) : demande de rythme
// du Repository Cartographer. Seule écriture relayée ; tout le reste reste GET/HEAD.
// P6-GOV-02 : identité opérateur vérifiée (en-tête posé par `tailscale serve`, liste d'autorisation
// CAT_OPERATOR_LOGINS, non secrète), transmise à l'API sous x-cat-operator-identity ; toute valeur
// fournie par le client sous ce nom est ignorée ; corps > 256 octets refusé avec une réponse 413.
export const AGENT_SCHEDULE_PATH_RE = /^\/api\/operator\/v1\/agent-invocations\/[a-z0-9-]{1,64}\/schedule$/;
export const OPERATOR_IDENTITY_PATH = "/api/operator/v1/operator-identity";
export const SCHEDULE_MAX_BODY = 256;
export const TAILSCALE_LOGIN_HEADER = "tailscale-user-login";
export const IDENTITY_HEADER = "x-cat-operator-identity";
export const RELAY_TOKEN_HEADER = "x-cat-relay-token";
const LOGIN_RE = /^[A-Za-z0-9._%+@-]{1,128}$/;

export function parseOperatorLogins(raw = process.env.CAT_OPERATOR_LOGINS ?? "") {
  return new Set(String(raw).split(",").map((x) => x.trim()).filter((x) => LOGIN_RE.test(x)).map((x) => x.toLowerCase()));
}

// Jeton relais → API (P6-GOV-02-RV) : 64 hex, fichier régulier jamais suivi s'il est un lien,
// illisible par « autres ». Absent ou invalide : null (aucune écriture relayée).
export function readRelayToken(file = process.env.CAT_RELAY_TOKEN_FILE ?? "") {
  if (!file) return null;
  let fd;
  try { fd = openSync(file, fsc.O_RDONLY | fsc.O_NOFOLLOW | fsc.O_NONBLOCK); } catch { return null; }
  try {
    const st = fstatSync(fd);
    if (!st.isFile() || (st.mode & 0o007) !== 0) return null;
    const buf = Buffer.alloc(129);
    const n = readSync(fd, buf, 0, 129, 0);
    const token = buf.subarray(0, n).toString("ascii").trim();
    return /^[0-9a-f]{64}$/.test(token) ? token : null;
  } catch { return null; } finally { closeSync(fd); }
}

// Activation par socket systemd (option P6-GOV-02-RV) : écoute sur le descripteur 3 transmis par
// une unité .socket appartenant à root, au lieu du port en boucle locale.
export function systemdListenFd(env = process.env, pid = process.pid) {
  return env.LISTEN_FDS === "1" && env.LISTEN_PID === String(pid) ? 3 : null;
}

export function tailscaleLogin(request) {
  const v = request.headers[TAILSCALE_LOGIN_HEADER];
  return typeof v === "string" && LOGIN_RE.test(v) ? v.toLowerCase() : null;
}

// Une ligne JSON par refus au relais (journald). Jamais de corps ni d'en-tête brut ; les demandes
// relayées sont journalisées par l'API avec le même identifiant d'opérateur.
export function relayAudit(pathname, identity, status, reason, log = console.error) {
  const agent = (pathname.match(/agent-invocations\/([a-z0-9-]{1,64})\/schedule$/) ?? [])[1] ?? null;
  log(JSON.stringify({ event: "cat.schedule.relay_refusal", ts: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), agent, identity, http_status: status, reason }));
}

function isSchedulePost(request, pathname) {
  return request.method === "POST" && AGENT_SCHEDULE_PATH_RE.test(pathname);
}

function methodAllowed(request, pathname) {
  return request.method === "GET" || request.method === "HEAD" || isSchedulePost(request, pathname);
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

function proxyToOperatorApi(request, response, target, identity = null, onOversize = () => undefined, relayToken = null) {
  const transport = target.protocol === "https:" ? https : http;
  const upstream = transport.request({
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port,
    method: request.method,
    path: request.url,
    headers: {
      host: target.host,
      ...(request.method === "POST"
        ? { "content-type": String(request.headers["content-type"] ?? ""), "x-cat-operator": String(request.headers["x-cat-operator"] ?? "") }
        : {}),
      ...(identity ? { [IDENTITY_HEADER]: identity } : {}),
      ...(relayToken ? { [RELAY_TOKEN_HEADER]: relayToken } : {}),
    },
  }, (upstreamResponse) => {
    const headers = copyProxyHeaders(upstreamResponse.headers);
    // WEB-01B runtime truth must remain network-only from the browser/PWA
    // perspective even when an upstream route omits explicit cache metadata.
    // Override any upstream cache directive at the presentation boundary.
    headers["cache-control"] = "no-store";
    response.writeHead(upstreamResponse.statusCode ?? 502, headers);
    if (request.method === "HEAD") response.end();
    else {
      upstreamResponse.once("error", () => response.destroy());
      upstreamResponse.once("aborted", () => response.destroy());
      upstreamResponse.pipe(response);
    }
  });
  upstream.setTimeout(UPSTREAM_TIMEOUT_MS, () => upstream.destroy(new Error("UPSTREAM_TIMEOUT")));
  upstream.once("error", () => failRequest(response, 502, "OPERATOR_API_UNAVAILABLE", "Local Operator API is unavailable."));
  if (request.method !== "POST") return void request.pipe(upstream);
  let size = 0;
  let refused = false;
  const chunks = [];
  request.on("data", (c) => {
    if (refused) return;
    size += c.length;
    if (size > SCHEDULE_MAX_BODY) { refused = true; upstream.destroy(); onOversize(); return refuseBody(request, response); }
    chunks.push(c);
  });
  request.on("end", () => { if (!refused) upstream.end(Buffer.concat(chunks)); });
}

// 413 avec une réponse lisible, puis fermeture de la connexion (le reste du corps n'est pas lu).
function refuseBody(request, response) {
  if (!response.headersSent) {
    response.writeHead(413, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", connection: "close" });
    response.end(JSON.stringify({ error_code: "BODY_TOO_LARGE", max_bytes: SCHEDULE_MAX_BODY }), () => request.destroy());
  } else request.destroy();
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
    "cache-control": "no-store",
  };
  if (basename === "sw.js" || basename === "pwa-policy.js" || ext === ".webmanifest") {
    headers["cache-control"] = "no-cache";
  }
  response.writeHead(200, headers);
  if (method === "HEAD") return response.end();
  const stream = createReadStream(filename);
  stream.once("error", () => response.destroy());
  stream.pipe(response);
}

// Every request failure becomes a structured answer or a closed connection;
// a handler rejection must never terminate the process (systemd restart loop).
function failRequest(response, status, code, message) {
  if (response.destroyed) return;
  if (response.headersSent) response.destroy();
  else apiError(response, status, code, message);
}

export function createServer({ host = LOOPBACK_HOST, port = FRONTEND_PORT, distRoot = DEFAULT_DIST_ROOT, apiTarget = OPERATOR_API_TARGET, spotRadarTarget = SPOT_RADAR_API_TARGET, balanceHistory, operatorLogins = parseOperatorLogins(), relayToken = readRelayToken(), listenFd = null } = {}) {
  const target = new URL(apiTarget);
  const spotRadar = new URL(spotRadarTarget);
  return http.createServer(async (request, response) => {
    try {
      let url;
      try { url = new URL(request.url ?? "/", `http://${host}`); } catch {
        return failRequest(response, 400, "INVALID_REQUEST_URL", "Request target is not a valid URL.");
      }
      if (!methodAllowed(request, url.pathname)) return apiError(response, 405, "METHOD_NOT_ALLOWED", "WEB-01G accepts GET and HEAD only (sauf demande de rythme d'agent).");
      if (balanceHistory && url.pathname === "/api/operator/v1/paper-balance-history") {
        const period = url.searchParams.get("days") ?? "1";
        if (!["1", "7", "30"].includes(period)) return apiError(response, 400, "INVALID_PERIOD", "Expected 1, 7 or 30 days.");
        response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
        response.end(request.method === "HEAD" ? undefined : JSON.stringify(balanceHistory(Number(period))));
        return;
      }
      if (isSchedulePost(request, url.pathname)) {
        const who = tailscaleLogin(request);
        const refuse = (status, code, message) => { relayAudit(url.pathname, who, status, code); return apiError(response, status, code, message); };
        if (operatorLogins.size === 0) return refuse(403, "OPERATOR_ALLOWLIST_UNSET", "Aucun opérateur autorisé n'est configuré.");
        if (!who) return refuse(401, "OPERATOR_IDENTITY_REQUIRED", "Identité opérateur absente.");
        if (!operatorLogins.has(who)) return refuse(403, "OPERATOR_NOT_AUTHORIZED", "Opérateur non autorisé.");
        if (!relayToken) return refuse(403, "RELAY_TOKEN_UNSET", "Transport relais → API non configuré.");
        const declared = request.headers["content-length"];
        if (declared !== undefined && (!/^[0-9]{1,6}$/.test(declared) || Number(declared) > SCHEDULE_MAX_BODY)) {
          relayAudit(url.pathname, who, 413, "BODY_TOO_LARGE");
          return refuseBody(request, response);
        }
        return proxyToOperatorApi(request, response, target, who, () => relayAudit(url.pathname, who, 413, "BODY_TOO_LARGE"), relayToken);
      }
      if (url.pathname === OPERATOR_IDENTITY_PATH) return proxyToOperatorApi(request, response, target, tailscaleLogin(request), undefined, relayToken);
      if (isApiPath(url.pathname)) {
        const selected = url.pathname.startsWith(SPOT_RADAR_API_PREFIX) ? spotRadar : target;
        return proxyToOperatorApi(request, response, selected);
      }

      const requested = await resolveStaticPath(distRoot, url.pathname);
      // SPA fallback applies only to non-API frontend routes; API paths never
      // reach this branch, including when the Operator API is unavailable.
      await serveFile(response, requested ?? path.join(distRoot, "index.html"), request.method);
    } catch {
      failRequest(response, 503, "FRONTEND_ASSET_UNAVAILABLE", "Frontend bundle is unavailable.");
    }
  }).listen(listenFd === null ? { port, host } : { fd: listenFd });
}

if (isMainEntrypoint()) {
  let port;
  try { port = resolveFrontendPort(); } catch (error) {
    console.error(`WEB_01G_CONFIG_REFUSED=${error.message}`);
    process.exit(2);
  }
  const stateDirectory = process.env.STATE_DIRECTORY;
  const balanceHistory = stateDirectory ? startPaperBalanceHistory(stateDirectory, OPERATOR_API_TARGET) : undefined;
  const listenFd = systemdListenFd();
  createServer({ port, balanceHistory, listenFd }).on("listening", () => console.log(listenFd === null ? `WEB_01G_LOCAL_FRONTEND_LISTENING=${LOOPBACK_HOST}:${port}` : "WEB_01G_LOCAL_FRONTEND_LISTENING=systemd-socket"));
}
