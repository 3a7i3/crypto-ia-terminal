// WEB-01G source E2E: real production build + native local server + browser.
// Playwright is installed transiently by the certification command, not added
// to the production runtime or package manifest.
import { chromium } from "playwright";
import http from "node:http";
import { once } from "node:events";
import { createServer, FRONTEND_PORT } from "./web01_local_frontend_server.mjs";

const observed = (value, semantics = "PRESENT") => ({ value, semantics });
const snapshot = {
  schema_version: "1.0.0", snapshot_id: "web01g-e2e", cycle: 1, process_instance_id: "fixture",
  generated_at_utc: "2026-09-15T00:00:00Z", source_sha: "fixture", worktree_state: "CLEAN",
  deployment_evidence: { status: "VERIFIED", source: "deploy_tag", evidence_ref: "web01g", observed_at_utc: "2026-09-15T00:00:00Z" },
  runtime_sha_evidence_status: "VERIFIED", instance_relation: "CURRENT_INSTANCE", runtime_state: "CURRENT", stale_reason: null,
  snapshot_age_s: 1, freshness_classification: "UNKNOWN",
  portfolio: { domain: "portfolio_state", observed_at_utc: "2026-09-15T00:00:00Z", source: "fixture", freshness: "UNKNOWN", status: "ATTENTION_REQUIRED", schema_version: "1.0.0", source_version: null, evidence: {}, source_updated_at_utc: observed(null, "UNKNOWN"), authority: "OBSERVATIONAL_TELEMETRY", mode: "PAPER", paper_equity_usd: observed(1000), paper_open_positions_count: observed(0, "ZERO"), paper_unrealized_pnl_usd: observed(0, "ZERO"), paper_realized_pnl_usd: observed(0, "ZERO"), real_account_equity_usd: observed(null, "NOT_APPLICABLE"), real_account_free_usd: observed(null, "NOT_APPLICABLE"), real_account_stale: observed(null, "NOT_APPLICABLE"), real_account_last_poll_utc: observed(null, "UNKNOWN"), non_paper_wallet_balance_usd: observed(null, "NOT_APPLICABLE"), capital_x_usd: observed(null, "NOT_APPLICABLE"), open_positions: observed([], "EMPTY") },
  decision_pipeline: { domain: "decision_pipeline", observed_at_utc: "2026-09-15T00:00:00Z", source: "fixture", freshness: "UNKNOWN", status: "ATTENTION_REQUIRED", schema_version: "1.0.0", source_version: null, evidence: {}, source_updated_at_utc: observed(null, "UNKNOWN"), authority: "OBSERVATIONAL_TELEMETRY", stages: [], trade_allowed: observed(null, "UNKNOWN"), first_blocker: observed(null, "UNKNOWN"), per_symbol_decisions: [] },
  system_health: { domain: "system_health", observed_at_utc: "2026-09-15T00:00:00Z", source: "fixture", freshness: "UNKNOWN", status: "ATTENTION_REQUIRED", schema_version: "1.0.0", source_version: null, evidence: {}, source_updated_at_utc: observed(null, "UNKNOWN"), authority: "OBSERVATIONAL_TELEMETRY", boot_alive: observed(null, "UNKNOWN"), health_score: observed(null, "UNAVAILABLE"), health_level: observed(null, "UNKNOWN"), exchange_connectivity_healthy: observed(null, "UNAVAILABLE"), exchange_latency_ms: observed(null, "UNAVAILABLE"), module_statuses: {} },
};
const market = { schema_version: "1.0.0", product: "CryptoRadar", domain: "market", authority: "OBSERVATIONAL_TELEMETRY", mode: "OBSERVATION", generated_at_utc: "2026-09-15T00:00:00Z", source_updated_at_utc: "2026-09-14T23:59:30Z", window_hours: 24, min_confidence: 65, packets_observed: 1, market_regime: "UNKNOWN", universe_size: 1, actionable_count: 1, watchlist_count: 0, top_opportunities: [{ symbol: "BTC/USDT", avg_confidence: 75, max_confidence: 75, n_signals: 1, dominant_side: "LONG", dominance_pct: 100, regime: "UNKNOWN" }], snapshot_age_s: 20, freshness_classification: "FRESH" };

const api = http.createServer((request, response) => {
  const body = request.url === "/api/operator/v1/snapshot" ? snapshot : request.url === "/api/operator/v1/market" ? market : { error_code: "NOT_FOUND" };
  response.writeHead(body.error_code ? 404 : 200, { "content-type": "application/json" }); response.end(JSON.stringify(body));
});
api.listen(0, "127.0.0.1"); await once(api, "listening");
const apiPort = api.address().port;
const frontend = createServer({ port: FRONTEND_PORT, apiTarget: `http://127.0.0.1:${apiPort}` });
await once(frontend, "listening");

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const response = await page.goto(`http://127.0.0.1:${FRONTEND_PORT}/operator/overview`, { waitUntil: "networkidle" });
  if (!response?.ok()) throw new Error(`frontend navigation failed: ${response?.status() ?? "no-response"}`);
  await page.waitForTimeout(100);
  if (!(await page.getByTestId("overview-view").count())) throw new Error(`overview did not render: ${await page.textContent("body")}`);
  for (const [tab, marker] of [["overview", "overview-view"], ["system", "system-view"], ["decisions", "decisions-view"], ["portfolio", "portfolio-view"], ["market", "market-view"]]) {
    await page.getByTestId(`tab-${tab}`).click(); await page.getByTestId(marker).waitFor({ state: "visible" });
  }
  await page.getByTestId("market-opportunity-row").waitFor({ state: "visible" });
  const marketText = await page.getByTestId("market-view").innerText();
  if (!marketText.includes("OBSERVATIONAL_TELEMETRY") || !marketText.includes("OBSERVATION") || !marketText.includes("FRESH")) throw new Error("MARKET provenance/mode/freshness missing");
  const post = await page.evaluate(async () => (await fetch("/api/operator/v1/market", { method: "POST" })).status);
  if (post !== 405) throw new Error(`mutating API request was not rejected: ${post}`);
  console.log("WEB_01G_LOCAL_RUNTIME_BROWSER_E2E=PASS");
} finally { await browser.close(); await new Promise((resolve) => frontend.close(resolve)); await new Promise((resolve) => api.close(resolve)); }
