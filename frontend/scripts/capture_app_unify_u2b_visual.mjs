import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.APP_UNIFY_U2B_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.APP_UNIFY_U2B_VISUAL_OUT_DIR || "artifacts/app-unify-u2b";
const fixturePath = process.env.APP_UNIFY_U2B_FIXTURE || ".cross-stack-fixtures/K_runtime_service.json";
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
if (fixture.http_status !== 200 || !fixture._proof.deployment_evidence_unchanged) throw new Error("Invalid real producer fixture");
await mkdir(out, { recursive: true });
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const clone = () => structuredClone(fixture.body);
const unavailable = (status) => {
  const d = clone();
  d.service = { unit: "crypto-advisor.service", query_status: status, load_state: status === "NOT_FOUND" ? "not-found" : null, active_state: null, sub_state: null, main_pid: null, restart_count: null, exec_main_started_at_utc: null, invocation_id: null };
  d.deployment = { status: "NOT_AVAILABLE", reason: "SERVICE_UNAVAILABLE", source_code_sha: null, evidence_ref: null, observed_at_utc: null, artifact_sha256: null, host_id: null, invocation_id: null };
  return d;
};
const stale = clone(); stale.freshness_classification = "STALE"; stale.snapshot_age_s = 120;
const inactive = clone(); inactive.service.active_state = "inactive"; inactive.service.sub_state = "dead"; inactive.service.main_pid = 0;
const failed = clone(); failed.service.active_state = "failed"; failed.service.sub_state = "failed"; failed.service.main_pid = 0;
const scenarios = [
  { name: "active", body: clone(), expected: ["ÉTAT OBSERVÉ · active", "4321", "NRestarts", "0", "b".repeat(40)] },
  { name: "stale", body: stale, expected: ["ÉTAT ACTUEL · INCONNU", "Preuve périmée", "active", "120s"] },
  { name: "inactive", body: inactive, expected: ["ÉTAT OBSERVÉ · inactive", "dead", "MainPID"] },
  { name: "failed", body: failed, expected: ["ÉTAT OBSERVÉ · failed"] },
  { name: "timeout", body: unavailable("TIMEOUT"), expected: ["ÉTAT ACTUEL · INCONNU", "TIMEOUT", "NOT_AVAILABLE"] },
  { name: "not-found", body: unavailable("NOT_FOUND"), expected: ["NOT_FOUND", "not-found", "NOT_AVAILABLE"] },
  { name: "missing", body: { error_code: "RUNTIME_SERVICE_MISSING" }, status: 503, expected: ["RUNTIME_SERVICE_MISSING", "INCONNU"] },
  { name: "invalid", body: { product: "RuntimeServiceSnapshot" }, expected: ["ERREUR TRANSPORT / CONTRAT", "INCONNU"] },
  { name: "network", abort: true, expected: ["ERREUR TRANSPORT / CONTRAT", "INCONNU"] },
];
const requests = [], errors = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    for (const scenario of scenarios) {
      const page = await browser.newPage({ viewport });
      page.on("pageerror", (error) => errors.push(String(error)));
      page.on("request", (request) => { if (new URL(request.url()).pathname.startsWith("/api/")) requests.push(`${request.method()} ${new URL(request.url()).pathname}`); });
      await page.route("**/api/**", (route) => {
        if (new URL(route.request().url()).pathname === "/api/operator/v1/runtime-service") {
          if (scenario.abort) return route.abort();
          return route.fulfill({ status: scenario.status ?? 200, contentType: "application/json", body: JSON.stringify(scenario.body) });
        }
        return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error_code: "SOURCE_NOT_DEPLOYED" }) });
      });
      const response = await page.goto(`${baseUrl}/paper-live/system`, { waitUntil: "networkidle" });
      assert(response?.ok(), "System navigation failed");
      const card = page.getByTestId("runtime-service-view");
      await card.waitFor();
      const text = await card.innerText();
      for (const value of scenario.expected) assert(text.toLowerCase().includes(value.toLowerCase()), `${scenario.name}/${viewport.width} missing ${value}`);
      if (!scenario.status && !scenario.abort && scenario.name !== "invalid") {
        await card.locator("summary").click();
        assert((await card.innerText()).includes("HOST_SYSTEMD_OBSERVATION"), "Missing host authority");
      }
      const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
      assert(noOverflow, `${scenario.name}/${viewport.width} horizontal overflow`);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `system-${scenario.name}-${viewport.width}.png`), fullPage: true });
      if (scenario.name === "active") {
        await page.goto(`${baseUrl}/direction`, { waitUntil: "networkidle" });
        const directionCard = page.getByTestId("direction-runtime-service-card");
        assert((await directionCard.innerText()).includes("4321"), "Direction host evidence missing");
        assert((await page.getByTestId("direction-federation-notice").innerText()).includes("6 sources"), "Missing independent source declaration");
        assert((await page.getByTestId("direction-global-card").innerText()).includes("ERREUR SOURCE"), "Host evidence hid the missing Advisor source");
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), "Direction overflow");
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(out, `direction-host-${viewport.width}.png`), fullPage: true });
      }
      await page.close();
    }
  }
  assert(errors.length === 0, `Browser errors: ${errors.join(", ")}`);
  assert(requests.includes("GET /api/operator/v1/runtime-service"), "Host GET missing");
  assert(requests.every((request) => request.startsWith("GET /api/operator/v1/")), "Unexpected or mutating API request");
  console.log("APP_UNIFY_U2B_DESKTOP_MOBILE=PASS");
  console.log("APP_UNIFY_U2B_INDEPENDENT_DIRECTION_SYSTEM=PASS");
  console.log("APP_UNIFY_U2B_STALE_MISSING_INVALID_NETWORK=PASS");
  console.log("APP_UNIFY_U2B_NO_MUTATION_REQUESTS=PASS");
} finally { await browser.close(); }
