import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.APP_UNIFY_U2_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.APP_UNIFY_U2_VISUAL_OUT_DIR || "artifacts/app-unify-u2";
const desktopPath = path.join(outDir, "burn-in-desktop-1440.png");
const mobilePath = path.join(outDir, "burn-in-mobile-390.png");
await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
async function noOverflow(page, label) {
  const g = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(g.scrollWidth <= g.clientWidth + 1, `${label} overflow: ${g.scrollWidth} > ${g.clientWidth}`);
}

const canonical = {
  schema_version: "1.0.0",
  snapshot_id: "u2-visual-snapshot",
  cycle: 1,
  process_instance_id: "u2-visual-instance",
  generated_at_utc: "2026-10-01T20:00:00Z",
  source_sha: "1".repeat(40),
  worktree_state: "CLEAN",
  deployment_evidence: { status: "VERIFIED", source: "deploy_tag", evidence_ref: "u2-visual", observed_at_utc: "2026-10-01T19:59:00Z" },
  runtime_sha_evidence_status: "VERIFIED",
  portfolio: {
    domain: "portfolio_state", status: "OK", freshness: "FRESH", schema_version: "1.0.0",
    source: "u2-visual", source_version: null, observed_at_utc: "2026-10-01T20:00:00Z",
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" }, evidence: {},
    authority: "OBSERVATIONAL_TELEMETRY", mode: "PAPER",
    paper_equity_usd: { value: 1000, semantics: "PRESENT" },
    paper_open_positions_count: { value: 1, semantics: "PRESENT" },
    paper_unrealized_pnl_usd: { value: 0, semantics: "ZERO" },
    paper_realized_pnl_usd: { value: 0, semantics: "ZERO" },
    real_account_equity_usd: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_free_usd: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_stale: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_last_poll_utc: { value: null, semantics: "UNKNOWN" },
    non_paper_wallet_balance_usd: { value: null, semantics: "NOT_APPLICABLE" },
    capital_x_usd: { value: null, semantics: "NOT_APPLICABLE" },
    open_positions: { value: [], semantics: "EMPTY" },
    portfolio_status: {
      current_positions: 1, hard_position_limit: 2, admission_state: "OPEN",
      positions_by_personality: {}, positions_by_regime: {},
    },
  },
  decision_pipeline: {
    domain: "decision_pipeline", status: "OK", freshness: "FRESH", schema_version: "1.0.0",
    source: "u2-visual", source_version: null, observed_at_utc: "2026-10-01T20:00:00Z",
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" }, evidence: {},
    authority: "OBSERVATIONAL_TELEMETRY", stages: [],
    trade_allowed: { value: null, semantics: "UNKNOWN" },
    first_blocker: { value: null, semantics: "UNKNOWN" }, per_symbol_decisions: [],
  },
  system_health: {
    domain: "system_health", status: "OK", freshness: "FRESH", schema_version: "1.0.0",
    source: "u2-visual", source_version: null, observed_at_utc: "2026-10-01T20:00:00Z",
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" }, evidence: {},
    authority: "OBSERVATIONAL_TELEMETRY",
    boot_alive: { value: true, semantics: "PRESENT" },
    health_score: { value: null, semantics: "UNAVAILABLE" },
    health_level: { value: "OBSERVED", semantics: "PRESENT" },
    exchange_connectivity_healthy: { value: null, semantics: "UNAVAILABLE" },
    exchange_latency_ms: { value: null, semantics: "UNAVAILABLE" },
    module_statuses: {},
  },
  instance_relation: "CURRENT_INSTANCE",
  runtime_state: "CURRENT",
  stale_reason: null,
  snapshot_age_s: 2,
  freshness_classification: "FRESH",
};

const burnIn = {
  schema_version: "1.0.0",
  product: "BurnInStatusSnapshot",
  domain: "burn_in",
  authority: "PPL_AUTHORITY_PRESENTATION",
  mode: "READ_ONLY",
  generated_at_utc: "2026-10-01T20:00:00Z",
  source_updated_at_utc: "2026-10-01T19:59:50Z",
  paper_epoch_id: "BURN-IN-EPOCH-01-20260926T064144Z",
  epoch_created_at_utc: "2026-09-27T02:41:07Z",
  source_code_sha: "1".repeat(40),
  config_snapshot_hash: "2".repeat(64),
  ppl_stream_sha256: "3".repeat(64),
  scientific_t0: { status: "PRESENT", value_utc: "2026-09-27T03:06:03.086973Z", source: "U2_VISUAL_GOVERNANCE" },
  event_count: 6,
  last_sequence: 6,
  event_counts: { EPOCH_CREATED: 1, POSITION_OPENED: 3, POSITION_CLOSED: 1, POSITION_UNRESOLVED: 1, RECOVERY_COMPLETED: 0 },
  lifecycle_counts: { open: 1, closed: 1, unresolved: 1, total: 3 },
  last_event: { sequence: 6, event_type: "POSITION_UNRESOLVED", timestamp_utc: "2026-10-01T19:59:50Z", trade_id: "trade-unresolved", decision_id: null },
  open_lifecycles: [{
    trade_id: "trade-open", decision_id: "decision-open", symbol: "CC/USDT", side: "LONG",
    principal_usd: 10, entry_price: 0.2, entry_fee_usd: 0.01, opened_sequence: 4,
    opened_at_utc: "2026-10-01T18:00:00Z", age_seconds: 7200, tp_price: 0.22, sl_price: 0.19,
    timeout_at_utc: "2026-10-02T02:00:00Z", recovery_eligible_until_utc: "2026-10-02T11:00:00Z",
    deadline_state: "BEFORE_TIMEOUT",
  }],
  lifecycle_history: [
    {
      trade_id: "trade-unresolved", open_decision_id: null, terminal_decision_id: null,
      symbol: "SOL/USDT", side: "LONG", principal_usd: 10, entry_price: 50, entry_fee_usd: 0.01,
      opened_sequence: 5, opened_at_utc: "2026-10-01T18:10:00Z", status: "UNRESOLVED",
      terminal_sequence: 6, terminal_at_utc: "2026-10-01T18:20:00Z", exit_price: null,
      exit_fee_usd: null, gross_pnl_usd: null, net_realized_pnl_usd: null,
      unresolved_reason: "RECOVERY_PRICE_UNAVAILABLE", duration_seconds: 600,
    },
    {
      trade_id: "trade-open", open_decision_id: "decision-open", terminal_decision_id: null,
      symbol: "CC/USDT", side: "LONG", principal_usd: 10, entry_price: 0.2, entry_fee_usd: 0.01,
      opened_sequence: 4, opened_at_utc: "2026-10-01T18:00:00Z", status: "OPEN",
      terminal_sequence: null, terminal_at_utc: null, exit_price: null, exit_fee_usd: null,
      gross_pnl_usd: null, net_realized_pnl_usd: null, unresolved_reason: null, duration_seconds: null,
    },
    {
      trade_id: "trade-closed", open_decision_id: "decision-btc", terminal_decision_id: "decision-close",
      symbol: "BTC/USDT", side: "LONG", principal_usd: 10, entry_price: 100, entry_fee_usd: 0.01,
      opened_sequence: 2, opened_at_utc: "2026-10-01T17:00:00Z", status: "CLOSED",
      terminal_sequence: 3, terminal_at_utc: "2026-10-01T17:30:00Z", exit_price: 110,
      exit_fee_usd: 0.01, gross_pnl_usd: 1, net_realized_pnl_usd: 0.98,
      unresolved_reason: null, duration_seconds: 1800,
    },
  ],
  history_order: "OPEN_SEQUENCE_DESC",
  frozen_config: {
    snapshot_schema: "BURN_IN_EXPERIMENT_CONFIG_V1", snapshot_sha256: "2".repeat(64),
    runtime_source_sha: "1".repeat(40), pb_max_positions: "2", paper_portfolio_brain_level: "a",
    mexc_sim_max_position_usd: "10", mexc_sim_max_age_h: "8", paper_lifecycle_authority: "PPL_AUTHORITY",
  },
  finalization: { state: "NOT_AVAILABLE", reason: "NO_GOVERNED_FINALIZATION_ARTIFACT_SUPPLIED" },
  snapshot_age_s: 4,
  freshness_classification: "FRESH",
};

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const apiRequests = [];
  const mutations = [];

  await page.route("**/api/operator/v1/snapshot", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(canonical) }),
  );
  await page.route("**/api/operator/v1/burn-in", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(burnIn) }),
  );
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) apiRequests.push(`${request.method()} ${url.pathname}`);
    if (!["GET", "HEAD"].includes(request.method())) mutations.push(`${request.method()} ${url.pathname}`);
  });

  const response = await page.goto(`${baseUrl}/paper-live/burn-in`, { waitUntil: "networkidle" });
  assert(response?.ok(), "Burn-in route failed");
  const view = page.getByTestId("burnin-view");
  await view.waitFor({ state: "visible" });
  const diagnostics = page.getByText("Diagnostics techniques · configuration et provenance", { exact: true });
  assert(!(await diagnostics.evaluate(e => e.parentElement.open)), "raw Burn-in diagnostics must start closed");
  await diagnostics.click();
  const text = await view.innerText();
  for (const required of [
    "Burn-in · observation scientifique", "BURN-IN-EPOCH-01-20260926T064144Z", "BEFORE_TIMEOUT",
    "Historique des ordres PAPER", "BTC/USDT", "CC/USDT", "SOL/USDT",
    "UNRESOLVED", "RECOVERY_PRICE_UNAVAILABLE", "PB_MAX_POSITIONS",
    "PAPER_PORTFOLIO_BRAIN_LEVEL", "NOT_AVAILABLE",
  ]) {
    assert(text.includes(required), `desktop Burn-in evidence missing: ${required}`);
  }
  assert((await page.getByTestId("burnin-history-row").count()) === 3, "desktop history must contain three lifecycle rows");
  assert(await page.locator(".burnin-history-table-wrap").isVisible(), "desktop history table is not visible");
  assert(!(await page.locator(".burnin-history-mobile").isVisible()), "mobile history cards unexpectedly visible on desktop");
  assert(mutations.length === 0, `mutation requests: ${mutations.join(", ")}`);
  assert(apiRequests.includes("GET /api/operator/v1/burn-in"), "burn-in endpoint was not read");
  await noOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(150);
  assert(!(await page.locator(".burnin-history-table-wrap").isVisible()), "desktop table must be hidden on mobile");
  assert(await page.locator(".burnin-history-mobile").isVisible(), "mobile history card container is not visible");
  assert((await page.getByTestId("burnin-history-mobile-row").count()) === 3, "mobile must expose all three lifecycle cards");
  const mobileText = await page.locator(".burnin-history-mobile").innerText();
  for (const required of ["BTC/USDT", "CC/USDT", "SOL/USDT", "0.98", "UNRESOLVED"]) {
    assert(mobileText.includes(required), `mobile history evidence missing: ${required}`);
  }
  assert(await page.getByTestId("tab-burn-in").isVisible(), "mobile Burn-in navigation is not visible");
  await noOverflow(page, "mobile");
  await page.screenshot({ path: mobilePath, fullPage: true });

  console.log(`APP_UNIFY_U2_VISUAL_DESKTOP=${desktopPath}`);
  console.log(`APP_UNIFY_U2_VISUAL_MOBILE=${mobilePath}`);
  console.log("APP_UNIFY_U2_HISTORY_DESKTOP=PASS");
  console.log("APP_UNIFY_U2_HISTORY_MOBILE=PASS");
  console.log("APP_UNIFY_U2_NO_MUTATION_REQUESTS=PASS");
} finally {
  await browser.close();
}
