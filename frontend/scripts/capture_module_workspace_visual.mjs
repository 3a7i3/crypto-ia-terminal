// Source-only preview. All API traffic is intercepted with generated synthetic
// fixtures. UI_PREVIEW_DIST permits inspection without starting any HTTP service.
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
const base = process.env.MODULE_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.MODULE_VISUAL_OUT_DIR || "artifacts/module-workspace";
const fixtureDir = process.env.CROSS_STACK_FIXTURES_DIR || ".cross-stack-fixtures";
const dist = process.env.UI_PREVIEW_DIST ? path.resolve(process.env.UI_PREVIEW_DIST) : null;
const fixtures = {};
for (const [key, file] of Object.entries({
  snapshot:"C_portfolio_semantics", market:"L_scanner", "market-microstructure":"M_microstructure",
  "ppl-comparison":"H_ppl_comparison", "financial-reconciliation":"P_financial_clarity",
  "research-lab":"N_research_publication", "research-strategies":"O_research_strategies",
  "runtime-service":"K_runtime_service", storage:"N_storage", events:"L_events",
})) fixtures[key] = JSON.parse(await readFile(path.join(fixtureDir,file+".json"),"utf8"));
const routes = [
  ["home","/direction","module-home"], ["market","/paper-live/market","market-view"],
  ["decisions","/paper-live/decisions","decisions-view"], ["positions","/paper-live/portfolio","portfolio-view"],
  ["ppl","/paper-live/lifecycle","ppl-comparison-view"], ["finance","/paper-live/finance","financial-reconciliation-view"],
  ["research","/research","research-lab-view"], ["strategies","/research/strategies","strategy-board-view"],
  ["system","/paper-live/system","runtime-service-view"], ["events","/paper-live/events","events-view"],
  ["project","/direction/travaux","machine-workboard"],
];
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const checks=[], errors=[], requests=[], blocked=[];
await mkdir(out,{recursive:true});
// The VM audit defaults to sandboxed Chromium. GitHub's disposable runner
// restricts user namespaces; its existing visual proofs use Playwright's
// default launch policy. Permit that policy only by explicit CI opt-in.
const sandbox = process.env.MODULE_VISUAL_SANDBOX !== "false";
assert(sandbox || process.env.GITHUB_ACTIONS === "true", "Sandbox opt-out is restricted to the disposable GitHub runner");
const browser = await chromium.launch({headless:true,chromiumSandbox:sandbox});
const mime={".js":"text/javascript",".css":"text/css",".html":"text/html",".png":"image/png",".webmanifest":"application/manifest+json"};
async function intercept(context, scenario) {
  await context.route("**/*", async route => {
    const req=route.request(), url=new URL(req.url());
    if (url.origin !== new URL(base).origin || !["GET","HEAD"].includes(req.method())) {blocked.push(req.method()+" "+url.origin+url.pathname);return route.abort();}
    if (url.pathname.startsWith("/api/")) {
      const key=url.pathname.split("/").at(-1);
      assert(key !== "burn-in", "Obsolete burn-in fetch from current app");
      if (scenario === "network") return route.abort();
      if (scenario === "invalid") return route.fulfill({status:200,contentType:"application/json",body:'{"unexpected":"invalid fixture"}'});
      const fixture=fixtures[key];
      const body=fixture ? structuredClone(fixture.body) : {error_code:"SOURCE_NOT_DEPLOYED"};
      if (scenario === "stale" && fixture && "freshness_classification" in body) { body.freshness_classification="STALE";body.snapshot_age_s=86400; }
      return route.fulfill({status:scenario === "missing" || !fixture ? 503 : fixture.http_status,contentType:"application/json",body:JSON.stringify(scenario === "missing" ? {error_code:"SOURCE_NOT_DEPLOYED"} : body)});
    }
    if (!dist) return route.continue();
    const requested=path.resolve(dist,"."+url.pathname);
    assert(requested === dist || requested.startsWith(dist+path.sep),"Preview path escapes dist");
    const target = req.isNavigationRequest() ? path.join(dist,"index.html") : requested;
    try {return route.fulfill({status:200,contentType:mime[path.extname(target)] || "application/octet-stream",body:await readFile(target)});}
    catch {return route.fulfill({status:404,body:"Preview asset absent"});}
  });
}
async function checkLayout(page,label) {
  const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}));
  assert(geometry.scroll<=geometry.width+1,label+": horizontal overflow "+JSON.stringify(geometry));
  checks.push({label,...geometry});
}
async function watermark(page) {
  await page.evaluate(()=>{const e=document.createElement("div");e.textContent="APERÇU SYNTHÉTIQUE · NON DÉPLOYÉ";e.style.cssText="position:fixed;bottom:8px;right:8px;background:#183e3d;color:#fff;padding:5px 9px;font:10px sans-serif;border-radius:4px;z-index:200;pointer-events:none";document.body.append(e);});
}
try {
  for (const theme of ["light","dark"]) for (const width of [1440,820,390]) for (const scenario of ["loaded","missing","stale"]) {
    if(scenario === "missing" && width === 820) continue;
    const context=await browser.newContext({viewport:{width,height:width===390?844:1000},locale:"fr-FR",serviceWorkers:"block"});
    await context.addInitScript(value=>localStorage.setItem("crypto-terminal.theme",value),theme);
    await intercept(context,scenario);
    const page=await context.newPage();page.setDefaultTimeout(10000);
    page.on("pageerror",e=>errors.push(String(e)));
    page.on("request",r=>{if(new URL(r.url()).pathname.startsWith("/api/"))requests.push(r.method()+" "+new URL(r.url()).pathname);});
    for(const [name,route,marker] of routes) {
      if(scenario === "stale" && !["home","market","ppl","finance","system"].includes(name))continue;
      await page.goto(base+route,{waitUntil:"domcontentloaded"});
      if(scenario === "missing" && ["positions","decisions"].includes(name)) await page.getByTestId("no-snapshot").waitFor();
      else await page.getByTestId(marker).waitFor();
      await page.waitForTimeout(120);
      const label=[theme,width,scenario,name].join("-");
      assert(await page.locator("html").getAttribute("data-theme") === theme,label+": wrong theme");
      if(name === "home") {
        assert(await page.locator(".module-card").count()===6,"Home module ownership missing");
        assert(!/Burn-in|Capital disponible|Positions ouvertes/.test(await page.getByTestId(marker).innerText()),"Home repeats detailed metrics");
      }
      if(scenario === "stale" && ["market","ppl","finance"].includes(name)) {
        assert(/périm|STALE|historique/i.test(await page.getByTestId(marker).innerText()),label+": historical warning missing");
      }
      if(name === "market" && scenario === "loaded") {
        assert(await page.locator(".market-table-desktop").isVisible(),label+": scanner table hidden");
        assert(await page.getByTestId("market-opportunity-row").count()>0,label+": scanner rows missing");
        await page.getByLabel("Recherche symbole",{exact:true}).fill("S25");
        await page.getByRole("button",{name:"Détail S25/USDT",exact:true}).click();
        assert(await page.getByTestId("market-symbol-detail").evaluate(e=>e===document.activeElement),label+": detail focus missing");
        await page.keyboard.press("Escape");
        await page.getByRole("button",{name:"Réinitialiser",exact:true}).click();
      }
      if(name === "positions" && scenario === "loaded" && width===390) assert(await page.getByTestId("portfolio-mobile-positions").isVisible(),label+": position cards hidden");
      if(name === "project")assert(await page.locator("tbody tr").count()===8,"Project pagination missing");
      await checkLayout(page,label);await watermark(page);
      await page.screenshot({path:path.join(out,label+".png"),fullPage:true});
      if(name === "home" && scenario === "loaded") {
        if(width===390){await page.getByRole("button",{name:"Ouvrir les modules"}).click();assert(await page.getByRole("navigation",{name:"Modules de la machine"}).isVisible(),"Mobile menu inaccessible");await page.keyboard.press("Escape");}
        await page.getByRole("button",{name:"Paramètres de l’application"}).click();
        const next=theme === "dark" ? "Clair" : "Sombre";
        await page.getByRole("radio",{name:next,exact:true}).check();
        await checkLayout(page,label+"-settings");
        await page.screenshot({path:path.join(out,label+"-settings.png"),fullPage:true});
        await page.keyboard.press("Escape");
        assert(await page.getByRole("button",{name:"Paramètres de l’application"}).evaluate(e=>e===document.activeElement),"Settings focus not restored");
        await page.reload({waitUntil:"domcontentloaded"});
        // addInitScript sets the desired starting theme on navigation, so actual
        // persistence is checked below in a context without that initializer.
      }
    }
    await context.close();console.log(theme,width,scenario,"PASS");
  }
  for(const scenario of ["invalid","network"]) {
    const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:"block"});await intercept(context,scenario);
    const page=await context.newPage();page.on("pageerror",e=>errors.push(String(e)));
    for(const [name,route]of routes.filter(r=>["market","finance","research","positions"].includes(r[0]))) {
      await page.goto(base+route,{waitUntil:"domcontentloaded"});await page.waitForTimeout(200);
      assert(!await page.getByTestId("market-opportunity-row").count(),"Invalid source fabricated rows");
      assert(!await page.getByTestId("open-position-row").count(),"Invalid source fabricated positions");
      await checkLayout(page,scenario+"-"+name);
      await watermark(page);await page.screenshot({path:path.join(out,scenario+"-"+name+".png"),fullPage:true});
    }await context.close();
  }
  const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:"block"});await intercept(context,"missing");
  const page=await context.newPage();await page.goto(base+"/direction");
  await page.getByRole("button",{name:"Paramètres de l’application"}).click();await page.getByRole("radio",{name:"Sombre",exact:true}).check();
  await page.reload();assert(await page.locator("html").getAttribute("data-theme")==="dark","Theme did not persist after reload");
  await page.getByRole("button",{name:"Paramètres de l’application"}).click();await page.getByRole("radio",{name:"Clair",exact:true}).check();
  await page.reload();assert(await page.locator("html").getAttribute("data-theme")==="light","Light theme did not persist after reload");
  const contrast=await page.evaluate(()=>{
    const luminance=c=>{const a=c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return .2126*a[0]+.7152*a[1]+.0722*a[2];};
    return ["light","dark"].flatMap(theme=>{document.documentElement.dataset.theme=theme;return ["--text-pri","--text-sec","--text-muted","--accent","--warn","--danger"].map(token=>{const e=document.createElement("span");e.style.cssText="color:var("+token+");background:var(--bg-card)";document.body.append(e);const s=getComputedStyle(e),f=luminance(s.color),b=luminance(s.backgroundColor);e.remove();return {theme,token,ratio:(Math.max(f,b)+.05)/(Math.min(f,b)+.05)};});});
  });assert(contrast.every(c=>c.ratio>=4.5),"Semantic contrast below AA: "+JSON.stringify(contrast));
  await context.close();
  assert(!errors.length,errors.join("\n"));assert(!blocked.length,"Unexpected requests: "+blocked.join("\n"));
  assert(requests.every(r=>r.startsWith("GET /api/operator/v1/")),"Unexpected mutation");
  await writeFile(path.join(out,"checks.json"),JSON.stringify({scope:"SYNTHETIC_SOURCE_UI_NOT_DEPLOYED",checks,errors,blocked,requests:[...new Set(requests)],contrast,themePersistence:"PASS"},null,2));
  console.log("MODULE_WORKSPACE_LIGHT_DARK_RESPONSIVE_SOURCE_ONLY=PASS",checks.length);
} finally {await browser.close();}
