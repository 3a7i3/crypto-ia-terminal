import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB_DIR_D3_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB_DIR_D3_VISUAL_OUT_DIR || "artifacts/web-dir-d3";
const desktopPath = path.join(outDir, "direction-desktop-1440.png");
const mobilePath = path.join(outDir, "direction-mobile-390.png");

await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function assertNoOverflow(page, label) {
  const geometry = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    geometry.scrollWidth <= geometry.clientWidth + 1,
    `${label} page overflows horizontally: ${geometry.scrollWidth}px > ${geometry.clientWidth}px`,
  );
}

const operatorSnapshot = {
  schema_version: "1.0.0",
  snapshot_id: "visual-snapshot",
  cycle: 42,
  process_instance_id: "visual-instance",
  generated_at_utc: "2026-09-27T20:00:00+00:00",
  source_sha: "116634be0d3c015cce1cfa58be7da7255414fbfd",
  worktree_state: "CLEAN",
  deployment_evidence: {
    status: "VERIFIED",
    source: "deploy_tag",
    evidence_ref: "WEB-DIR-01-D4B",
    observed_at_utc: "2026-09-27T20:00:00+00:00",
  },
  runtime_sha_evidence_status: "VERIFIED",
  portfolio: {
    domain: "portfolio_state",
    observed_at_utc: "2026-09-27T20:00:00+00:00",
    source: "visual-proof",
    freshness: "FRESH",
    status: "OK",
    schema_version: "1.0.0",
    source_version: null,
    evidence: {},
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" },
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "PAPER",
    paper_equity_usd: { value: 1001.8635705815693, semantics: "PRESENT" },
    paper_open_positions_count: { value: 2, semantics: "PRESENT" },
    paper_unrealized_pnl_usd: { value: null, semantics: "UNAVAILABLE" },
    paper_realized_pnl_usd: { value: 0, semantics: "ZERO" },
    real_account_equity_usd: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_free_usd: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_stale: { value: null, semantics: "NOT_APPLICABLE" },
    real_account_last_poll_utc: { value: null, semantics: "UNKNOWN" },
    non_paper_wallet_balance_usd: { value: null, semantics: "NOT_APPLICABLE" },
    capital_x_usd: { value: null, semantics: "NOT_APPLICABLE" },
    open_positions: {
      value: [
        {
          position_id: "visual-btc",
          symbol: "BTCUSDT",
          side: "BUY",
          size_usd: 10,
          entry_price: 50000,
          current_price: { value: 50500, semantics: "PRESENT" },
          current_price_observed_at_utc: "2026-09-27T20:00:00+00:00",
          tp_price: 52000,
          sl_price: 49000,
          tp_sl_source: "original",
          unrealized_pnl_usd: { value: 0.1, semantics: "PRESENT" },
          unrealized_pnl_pct: { value: 1, semantics: "PRESENT" },
          opened_at: Date.parse("2026-09-27T18:00:00+00:00") / 1000,
          regime: { value: "trend", semantics: "PRESENT" },
          restored_without_regime: false,
          personality: "scalper",
          restored: false,
        },
        {
          position_id: "visual-eth",
          symbol: "ETHUSDT",
          side: "SELL",
          size_usd: 10,
          entry_price: 3000,
          current_price: { value: 2970, semantics: "PRESENT" },
          current_price_observed_at_utc: "2026-09-27T20:00:00+00:00",
          tp_price: 2900,
          sl_price: 3050,
          tp_sl_source: "original",
          unrealized_pnl_usd: { value: 0.1, semantics: "PRESENT" },
          unrealized_pnl_pct: { value: 1, semantics: "PRESENT" },
          opened_at: Date.parse("2026-09-27T19:30:00+00:00") / 1000,
          regime: { value: "range", semantics: "PRESENT" },
          restored_without_regime: false,
          personality: "mean_reversion",
          restored: false,
        },
      ],
      semantics: "PRESENT",
    },
    portfolio_status: {
      current_positions: 2,
      hard_position_limit: 2,
      admission_state: "SATURATED",
      positions_by_personality: { scalper: 1, mean_reversion: 1 },
      positions_by_regime: { trend: 1, range: 1 },
    },
  },
  decision_pipeline: {
    domain: "decision_pipeline",
    observed_at_utc: "2026-09-27T20:00:00+00:00",
    source: "visual-proof",
    freshness: "FRESH",
    status: "OK",
    schema_version: "1.0.0",
    source_version: null,
    evidence: {},
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" },
    authority: "OBSERVATIONAL_TELEMETRY",
    stages: [],
    trade_allowed: { value: null, semantics: "UNKNOWN" },
    first_blocker: { value: null, semantics: "UNKNOWN" },
    per_symbol_decisions: [],
  },
  system_health: {
    domain: "system_health",
    observed_at_utc: "2026-09-27T20:00:00+00:00",
    source: "visual-proof",
    freshness: "FRESH",
    status: "OK",
    schema_version: "1.0.0",
    source_version: null,
    evidence: {},
    source_updated_at_utc: { value: null, semantics: "UNKNOWN" },
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
  snapshot_age_s: 2.4,
  freshness_classification: "FRESH",
};

const financialSnapshot = {
  schema_version: "1.0.0",
  product: "FIN02FinancialCockpit",
  domain: "financial_reconciliation",
  authority: "FINANCIAL_OBSERVATION",
  generated_at_utc: "2026-09-27T20:00:00Z",
  reconciliation_id: "r".repeat(64),
  paper_epoch_id: "BURN-IN-EPOCH-01-20260926T064144Z",
  financial_snapshot_id: "s".repeat(64),
  reconciliation_code_sha: "r".repeat(40),
  source_stream_digest: "p".repeat(64),
  last_source_sequence: 3,
  fin_schema_version: 1,
  fin_code_sha: "f".repeat(40),
  source_code_sha: "116634be0d3c015cce1cfa58be7da7255414fbfd",
  config_hash: "9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4",
  financial_model: "PAPER_LINEAR_PRINCIPAL_V1",
  asset: "USDT",
  financial: {
    initial_epoch_capital: "1001.8635705815693",
    cash_available: "981.8435705815693",
    capital_reserved: "20.0",
    capital_deployed: "20.0",
    capital_unresolved: "0",
    gross_realized_price_pnl: "0",
    fees_paid: "0.02",
    funding_net: null,
    funding_status: "NOT_APPLICABLE",
    funding_evidence_ref: null,
    realized_pnl: null,
    known_unrealized_pnl: "0",
    unrealized_pnl: null,
    certified_equity: null,
    evidence_status: "UNRESOLVED",
    reconciliation_status: "UNRESOLVED",
    valuation_as_of: "1790540000.0",
    valuation_statuses: ["UNAVAILABLE"],
    open_position_count: 2,
    settled_position_count: 0,
    unresolved_position_count: 0,
  },
  reconciliation: {
    overall_status: "DIVERGENT",
    as_of: "1790540000.0",
    unresolved_capital: "0",
    unreconciled_capital: null,
    policy: {
      absolute_tolerance: "0.000000000001",
      relative_tolerance: "0",
      stale_after_s: "30",
    },
    ppl_observation_digest: "1".repeat(64),
    simulator_observation_digest: null,
    external_observation_digest: null,
  },
  sources: { ppl: {}, simulator: null, external: null },
  records: [],
  snapshot_age_s: 4.5,
  freshness_classification: "FRESH",
};

const marketSnapshot = {
  schema_version: "1.0.0",
  product: "CryptoRadar",
  domain: "market",
  authority: "OBSERVATIONAL_TELEMETRY",
  mode: "OBSERVATION",
  generated_at_utc: "2026-09-27T20:00:00Z",
  source_updated_at_utc: "2026-09-27T19:59:00Z",
  window_hours: 24,
  min_confidence: 65,
  packets_observed: 86,
  market_regime: "bull_trend",
  universe_size: 33,
  actionable_count: 4,
  watchlist_count: 7,
  top_opportunities: [],
  snapshot_age_s: 8,
  freshness_classification: "FRESH",
};

const researchSnapshot = {
  schema_version: "1.0.0",
  product: "ResearchLabSnapshot",
  domain: "research_lab",
  authority: "RESEARCH_NON_AUTHORITATIVE",
  generated_at_utc: "2026-09-27T20:00:00Z",
  presentation_builder_source_sha: "b".repeat(40),
  research_state: "AVAILABLE",
  provenance: {
    primary_context: {
      dataset_id: "1".repeat(64),
      source_boundary_id: "2".repeat(64),
      paper_epoch_id: "F00-EPOCH-01-20260920T084335Z",
      research_run_id: "3".repeat(64),
      diagnostic_run_id: "4".repeat(64),
      research_source_code_sha: "a".repeat(40),
      research_config_hash: "5".repeat(64),
      presentation_builder_source_sha: "b".repeat(40),
      population_definition: "POSITION_CLOSED_FOR_PERFORMANCE",
      n: 13,
      evidence_status: "COMPLETE",
      statistical_strength: "LOW_SAMPLE",
    },
    source_artifacts: [
      {
        artifact_ref: "diag-a4",
        artifact_type: "RL_DIAG_RESULT",
        sha256: "6".repeat(64),
      },
    ],
  },
  population: {
    population_definition: "POSITION_CLOSED_FOR_PERFORMANCE",
    n: 13,
    evidence_status: "COMPLETE",
    statistical_strength: "LOW_SAMPLE",
  },
  performance: [],
  risk_stability: [],
  costs: [],
  attribution: [],
  candidate_registry: { candidate_count: 0, rows: [] },
  limitations: ["N=13 / LOW_SAMPLE"],
};

const burnInSnapshot = {
  schema_version: "1.0.0",
  product: "BurnInStatusSnapshot",
  domain: "burn_in",
  authority: "PPL_AUTHORITY_PRESENTATION",
  mode: "READ_ONLY",
  generated_at_utc: "2026-09-27T20:00:00Z",
  source_updated_at_utc: "2026-09-27T19:59:58Z",
  paper_epoch_id: "BURN-IN-EPOCH-01-20260926T064144Z",
  epoch_created_at_utc: "2026-09-27T02:41:07Z",
  source_code_sha: "116634be0d3c015cce1cfa58be7da7255414fbfd",
  config_snapshot_hash: "9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4",
  ppl_stream_sha256: "7".repeat(64),
  scientific_t0: {
    status: "PRESENT",
    value_utc: "2026-09-27T03:06:03.086973Z",
    source: "WEB_DIR_01_D1_GOVERNANCE_CONTRACT",
  },
  event_count: 2,
  last_sequence: 2,
  event_counts: {
    EPOCH_CREATED: 1,
    POSITION_OPENED: 1,
    POSITION_CLOSED: 0,
    POSITION_UNRESOLVED: 0,
    RECOVERY_COMPLETED: 0,
  },
  lifecycle_counts: { open: 1, closed: 0, unresolved: 0, total: 1 },
  last_event: {
    sequence: 2,
    event_type: "POSITION_OPENED",
    timestamp_utc: "2026-09-27T19:59:58Z",
    trade_id: "visual-open",
    decision_id: "visual-decision",
  },
  open_lifecycles: [{
    trade_id: "visual-open",
    decision_id: "visual-decision",
    symbol: "CC/USDT",
    side: "LONG",
    principal_usd: 10,
    entry_price: 0.2,
    entry_fee_usd: 0.01,
    opened_sequence: 2,
    opened_at_utc: "2026-09-27T18:00:00Z",
    age_seconds: 7198,
    tp_price: 0.22,
    sl_price: 0.19,
    timeout_at_utc: "2026-09-28T02:00:00Z",
    recovery_eligible_until_utc: "2026-09-28T11:00:00Z",
    deadline_state: "BEFORE_TIMEOUT",
  }],
  lifecycle_history: [{
    trade_id: "visual-open",
    open_decision_id: "visual-decision",
    terminal_decision_id: null,
    symbol: "CC/USDT",
    side: "LONG",
    principal_usd: 10,
    entry_price: 0.2,
    entry_fee_usd: 0.01,
    opened_sequence: 2,
    opened_at_utc: "2026-09-27T18:00:00Z",
    status: "OPEN",
    terminal_sequence: null,
    terminal_at_utc: null,
    exit_price: null,
    exit_fee_usd: null,
    gross_pnl_usd: null,
    net_realized_pnl_usd: null,
    unresolved_reason: null,
    duration_seconds: null,
  }],
  history_order: "OPEN_SEQUENCE_DESC",
  frozen_config: {
    snapshot_schema: "BURN_IN_EXPERIMENT_CONFIG_V1",
    snapshot_sha256: "9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4",
    runtime_source_sha: "116634be0d3c015cce1cfa58be7da7255414fbfd",
    pb_max_positions: "2",
    paper_portfolio_brain_level: "a",
    mexc_sim_max_position_usd: "10",
    mexc_sim_max_age_h: "8",
    paper_lifecycle_authority: "PPL_AUTHORITY",
  },
  finalization: {
    state: "NOT_AVAILABLE",
    reason: "NO_GOVERNED_FINALIZATION_ARTIFACT_SUPPLIED",
  },
  snapshot_age_s: 2,
  freshness_classification: "FRESH",
};

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const apiRequests = [];
  const mutationRequests = [];

  await page.route("**/api/operator/v1/snapshot", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(operatorSnapshot) }),
  );
  await page.route("**/api/operator/v1/financial-reconciliation", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(financialSnapshot) }),
  );
  await page.route("**/api/operator/v1/market", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(marketSnapshot) }),
  );
  await page.route("**/api/operator/v1/research-lab", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(researchSnapshot) }),
  );
  await page.route("**/api/operator/v1/burn-in", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(burnInSnapshot) }),
  );

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") {
      apiRequests.push(`${request.method()} ${url.pathname}`);
    }
    if (!["GET", "HEAD"].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${url.pathname}`);
    }
  });

  const response = await page.goto(`${baseUrl}/direction`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Direction navigation failed: ${response?.status() ?? "no-response"}`);

  await page.getByTestId("direction-shell").waitFor({ state: "visible" });
  await page.getByTestId("direction-authority-strip").waitFor({ state: "visible" });
  await page.getByTestId("direction-global-card").waitFor({ state: "visible" });
  await page.getByTestId("direction-experiment-card").waitFor({ state: "visible" });
  await page.getByTestId("direction-market-card").waitFor({ state: "visible" });
  await page.getByTestId("direction-research-card").waitFor({ state: "visible" });
  await page.getByTestId("direction-burnin-card").waitFor({ state: "visible" });
  const burnInCard = page.getByTestId("direction-burnin-card");
  const burnInText = await burnInCard.innerText();
  for (const required of ["PPL_AUTHORITY_PRESENTATION", "BEFORE_TIMEOUT", "T0 scientifique", "CC/USDT"]) {
    assert(burnInText.includes(required), `U2 Direction burn-in evidence missing: ${required}`);
  }

  const globalCard = page.getByTestId("direction-global-card");
  await globalCard.getByText("PAPER", { exact: true }).waitFor();
  const ownerPulse = page.getByTestId("direction-owner-pulse");
  const ownerPulseText = await ownerPulse.innerText();
  for (const required of ["2 / 2", "SATURATED", "VERIFIED"]) {
    assert(ownerPulseText.includes(required), `U1 owner pulse missing: ${required}`);
  }
  const ownerPositions = page.getByTestId("direction-owner-positions");
  const ownerPositionsText = await ownerPositions.innerText();
  for (const required of ["BTCUSDT", "ETHUSDT", "2h 0m", "30m", "Âge à la capture"]) {
    assert(ownerPositionsText.includes(required), `U1 owner position evidence missing: ${required}`);
  }

  await page.getByTestId("direction-experiment-card").getByText("981.8435705815693 USDT", { exact: true }).waitFor();
  const marketCard = page.getByTestId("direction-market-card");
  const researchCard = page.getByTestId("direction-research-card");
  await marketCard.getByText("OBSERVATIONAL_TELEMETRY", { exact: true }).first().waitFor();
  await marketCard.getByText("Actionable observés", { exact: true }).waitFor();
  await marketCard.getByText(/aucune permission de trade/).waitFor();
  await researchCard.getByText("RESEARCH_NON_AUTHORITATIVE", { exact: true }).waitFor();
  await researchCard.getByText("Population dataset N", { exact: true }).waitFor();
  await researchCard.getByText("RESEARCH NON-AUTORITAIRE", { exact: true }).waitFor();

  const federationNotice = page.getByTestId("direction-federation-notice");
  await federationNotice.getByText("FÉDÉRÉ · NON ATOMIQUE", { exact: true }).waitFor();
  const federationText = await federationNotice.innerText();
  for (const required of ["aucun timestamp global", "aucune fraîcheur globale", "aucun état de santé global dérivé"]) {
    assert(federationText.includes(required), `D4D federation boundary missing: ${required}`);
  }

  const globalProvenance = page.getByTestId("direction-provenance-global");
  const experimentProvenance = page.getByTestId("direction-provenance-experiment");
  const marketProvenance = page.getByTestId("direction-provenance-market");
  const researchProvenance = page.getByTestId("direction-provenance-research");
  const burnInProvenance = page.getByTestId("direction-provenance-burnin");

  for (const [locator, required] of [
    [globalProvenance, ["/api/operator/v1/snapshot", "canonical_advisor_presentation", "AUCUNE AUTORITÉ GLOBALE"]],
    [experimentProvenance, ["/api/operator/v1/financial-reconciliation", "FINANCIAL_OBSERVATION", "FRESH", "4.5s"]],
    [marketProvenance, ["/api/operator/v1/market", "OBSERVATIONAL_TELEMETRY", "FRESH", "8s"]],
    [researchProvenance, ["/api/operator/v1/research-lab", "RESEARCH_NON_AUTHORITATIVE", "NOT_AVAILABLE"]],
    [burnInProvenance, ["/api/operator/v1/burn-in", "PPL_AUTHORITY_PRESENTATION", "FRESH", "2s"]],
  ]) {
    const text = await locator.innerText();
    for (const expected of required) {
      assert(text.includes(expected), `D4D provenance strip missing: ${expected}`);
    }
  }

  const globalDetails = await page.getByTestId("direction-global-card").locator("details").textContent();
  const experimentDetails = await page.getByTestId("direction-experiment-card").locator("details").textContent();
  const researchDetails = await researchCard.locator("details").textContent();
  assert(globalDetails?.includes("visual-snapshot"), "D4D full snapshot identity is not inspectable");
  assert(globalDetails?.includes("visual-instance"), "D4D full process instance identity is not inspectable");
  assert(experimentDetails?.includes("9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4"), "D4D full FIN config hash is not inspectable");
  assert(researchDetails?.includes("1".repeat(64)), "D4D full Research dataset id is not inspectable");
  assert(researchDetails?.includes("2".repeat(64)), "D4D full Research source-boundary id is not inspectable");
  assert(researchDetails?.includes("3".repeat(64)), "D4D full Research run id is not inspectable");
  assert(researchDetails?.includes("4".repeat(64)), "D4D full diagnostic run id is not inspectable");
  assert(researchDetails?.includes("5".repeat(64)), "D4D full Research config hash is not inspectable");
  assert(researchDetails?.includes("a".repeat(40)), "D4D full Research source SHA is not inspectable");
  assert(researchDetails?.includes("b".repeat(40)), "D4D full presentation-builder SHA is not inspectable");

  const shellText = await page.getByTestId("direction-shell").innerText();
  for (const required of [
    "DIRECTION",
    "SURFACE PROPRIÉTAIRE",
    "Synthèse, gouvernance et décisions humaines",
    "PRÉSENTATION",
    "LECTURE SEULE",
    "AUCUNE AUTORITÉ PAPER",
    "ÉTAT GLOBAL · INCONNU",
    "BURN-IN-EPOCH-01-20260926T064144Z",
    "981.8435705815693 USDT",
    "PF · NOT_AVAILABLE",
    "WR · NOT_AVAILABLE",
  ]) {
    assert(shellText.includes(required), `D4D Direction evidence missing: ${required}`);
  }

  const futureCapabilities = page.locator('section[aria-label="Capacités Direction futures"]');
  assert(
    (await futureCapabilities.getByText("NON DÉPLOYÉ", { exact: true }).count()) === 6,
    "Direction must expose exactly six honest future capability placeholders",
  );
  assert(
    (await page.getByTestId("direction-global-card").getByText("NON DÉPLOYÉ", { exact: true }).count()) === 2,
    "Global State must keep Watchdog and critical alerts explicitly NON DÉPLOYÉ",
  );

  const allowedRequests = new Set([
    "GET /api/operator/v1/snapshot",
    "GET /api/operator/v1/financial-reconciliation",
    "GET /api/operator/v1/market",
    "GET /api/operator/v1/research-lab",
    "GET /api/operator/v1/burn-in",
  ]);
  assert(apiRequests.length >= 5, "Direction did not request all five governed sources");
  assert(
    apiRequests.every((request) => allowedRequests.has(request)),
    `Direction requested an endpoint outside D4B/D4C/D4D: ${apiRequests.join(", ")}`,
  );
  assert(
    apiRequests.includes("GET /api/operator/v1/snapshot") &&
      apiRequests.includes("GET /api/operator/v1/financial-reconciliation") &&
      apiRequests.includes("GET /api/operator/v1/market") &&
      apiRequests.includes("GET /api/operator/v1/research-lab") &&
      apiRequests.includes("GET /api/operator/v1/burn-in"),
    `Direction governed sources incomplete: ${apiRequests.join(", ")}`,
  );
  assert(mutationRequests.length === 0, `Direction issued mutation requests: ${mutationRequests.join(", ")}`);

  const returnControl = page.getByTestId("return-paper-live");
  const returnBox = await returnControl.boundingBox();
  assert(returnBox !== null && returnBox.height >= 44, "Direction return control is smaller than 44px");
  assert(await returnControl.getAttribute("href") === "/paper-live", "Direction return target is not /paper-live");

  await assertNoOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(150);
  assert(await returnControl.isVisible(), "mobile Direction return control is not visible");
  assert(await page.getByTestId("direction-authority-strip").isVisible(), "mobile authority strip is not visible");
  assert(await page.getByTestId("direction-federation-notice").isVisible(), "mobile federation notice is not visible");
  assert(await page.getByTestId("direction-provenance-global").isVisible(), "mobile Global provenance strip is not visible");
  assert(await page.getByTestId("direction-provenance-experiment").isVisible(), "mobile Experiment provenance strip is not visible");
  assert(await page.getByTestId("direction-provenance-market").isVisible(), "mobile Market provenance strip is not visible");
  assert(await page.getByTestId("direction-provenance-research").isVisible(), "mobile Research provenance strip is not visible");
  assert(await page.getByTestId("direction-provenance-burnin").isVisible(), "mobile Burn-in provenance strip is not visible");
  const mobileHeaderPosition = await page.locator(".direction-header").evaluate(
    (element) => getComputedStyle(element).position,
  );
  assert(mobileHeaderPosition === "sticky", "mobile Direction header is not sticky");
  const mobileReturnBox = await returnControl.boundingBox();
  assert(mobileReturnBox !== null && mobileReturnBox.height >= 44, "mobile return control is smaller than 44px");
  assert(mobileReturnBox !== null && mobileReturnBox.width <= 390, "mobile return control exceeds viewport");
  await assertNoOverflow(page, "mobile");
  await page.screenshot({ path: mobilePath, fullPage: true });

  console.log(`WEB_DIR_D4D_VISUAL_DESKTOP=${desktopPath}`);
  console.log(`WEB_DIR_D4D_VISUAL_MOBILE=${mobilePath}`);
  console.log("WEB_DIR_D4D_GOVERNED_GETS=PASS");
  console.log("WEB_DIR_D4D_NO_MUTATION_REQUESTS=PASS");
  console.log("WEB_DIR_D4D_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
