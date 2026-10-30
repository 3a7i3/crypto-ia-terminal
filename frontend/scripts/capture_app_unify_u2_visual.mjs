// The operator retired this app surface. Verify redirects and absence of
// burn-in requests. Its historical view/reader contracts remain tested in
// BurnInStatusView, BurnInHistory and the generated cross-stack J case.
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
const base=process.env.APP_UNIFY_U2_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out=process.env.APP_UNIFY_U2_VISUAL_OUT_DIR || "artifacts/app-unify-u2";
await mkdir(out,{recursive:true});
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


const browser=await chromium.launch({headless:true});
const checks=[];
try{
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:"block"});
  const page=await context.newPage(),requests=[];
  page.on("request",r=>{if(new URL(r.url()).pathname.startsWith("/api/"))requests.push(r.method()+" "+new URL(r.url()).pathname);});
  await page.route("**/api/**",r=>r.fulfill({status:r.request().url().endsWith("/snapshot")?200:503,contentType:"application/json",body:JSON.stringify(r.request().url().endsWith("/snapshot")?canonical:{error_code:"SOURCE_NOT_DEPLOYED"})}));
  for(const [from,to,marker]of [["burn-in","portfolio","portfolio-view"],["scores","system","runtime-service-view"]]){
   await page.goto(base+"/paper-live/"+from,{waitUntil:"networkidle"});await page.getByTestId(marker).waitFor();
   if(new URL(page.url()).pathname!=="/paper-live/"+to)throw new Error("Legacy route did not redirect");
   if(await page.getByTestId("burnin-view").count() || await page.getByTestId("tab-scores").count())throw new Error("Retired UI still exposed");
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw new Error("Overflow");
   await page.screenshot({path:out+"/redirect-"+from+"-"+width+".png",fullPage:true});
  }
  if(requests.some(r=>!r.startsWith("GET ")||r.endsWith("/burn-in")))throw new Error("Retired producer requested");
  checks.push({width,requests,redirects:"PASS"});await context.close();
 }
 await writeFile(out+"/checks.json",JSON.stringify({scope:"RETIRED_UI_REDIRECT_SOURCE_ONLY",checks},null,2));
 console.log("RETIRED_BURNIN_SCORES_REDIRECT_GET_ONLY=PASS");
}finally{await browser.close();}
