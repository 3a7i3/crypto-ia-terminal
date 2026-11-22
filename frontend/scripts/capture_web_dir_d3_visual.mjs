// Current home replaces the historical Direction dashboard. Domain-value and
// legacy burn-in contracts remain covered by unit/cross-stack tests.
// M1-C5 (EO-026, D2): /direction, / and /paper-live open the Market home
// (Radar Spot, decision D-C5); ModuleHome is no longer routed. This proof
// follows the actual navigation: the six module owners are reached through the
// primary module navigation, absence stays explicit (the Radar source states
// its own SOURCE_NOT_DEPLOYED) and the home never duplicates domain data. The
// ModuleHome availability invariants are kept by src/test/ModuleHome.invariants.test.tsx.
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
const base=process.env.WEB_DIR_D3_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out=process.env.WEB_DIR_D3_VISUAL_OUT_DIR || "artifacts/web-dir-d3";
await mkdir(out,{recursive:true});
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
const browser=await chromium.launch({headless:true});
const checks=[];
try {
 for(const width of [1440,820,390,320]) {
  const context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:"block"});
  const page=await context.newPage(),requests=[],errors=[];
  page.on("request",r=>{if(new URL(r.url()).pathname.startsWith("/api/"))requests.push(r.method()+" "+new URL(r.url()).pathname);});
  page.on("pageerror",e=>errors.push(String(e)));
  await page.route("**/api/**",r=>r.fulfill({status:503,contentType:"application/json",body:'{"error_code":"SOURCE_NOT_DEPLOYED"}'}));
  await page.goto(base+"/direction",{waitUntil:"networkidle"});
  await page.waitForURL(/\/paper-live\/market\/radar$/);
  const home=page.getByTestId("market-workspace");await home.waitFor();
  assert(await page.getByTestId("module-home").count()===0,"Unrouted ModuleHome mounted");
  // Six module owners plus the Accueil shortcut, in the single primary navigation.
  if(width<=640)await page.getByRole("button",{name:"Ouvrir les modules"}).click();
  const nav=page.getByRole("navigation",{name:"Modules de la machine"});
  assert(await nav.isVisible(),"Modules inaccessible");
  const links=await nav.getByRole("link").evaluateAll(a=>a.map(e=>[e.textContent.trim(),new URL(e.href).pathname]));
  assert(links.length===7,"Six module owners missing: "+JSON.stringify(links));
  for(const [label,href] of [["Marché","/paper-live/market"],["Décisions","/paper-live/decisions"],["Positions","/paper-live/portfolio"],["Wallet","/paper-live/finance"],["Laboratoire","/research"],["Système","/paper-live/system"]])
   assert(links.some(([text,path])=>text.includes(label)&&path===href),"Module owner missing: "+label+" "+JSON.stringify(links));
  if(width<=640)await page.keyboard.press("Escape");
  // Absence stays explicit: the home source states its own deployment code.
  await page.getByTestId("market-source-not-configured").waitFor();
  assert((await home.innerText()).includes("SOURCE_NOT_DEPLOYED"),"Absence fabricated availability");
  assert(!/Publication disponible|Publication récente/.test(await home.innerText()),"Absence fabricated availability");
  // Vite development runs React StrictMode mount effects twice. Production
  // runs once; the home reads only the Radar Spot source it owns.
  const bootCounts=[...new Set(requests)].map(key=>requests.filter(r=>r===key).length);
  assert(bootCounts.length>=1 && bootCounts.every(n=>n>=1&&n<=2),"Home bounded boot fetches changed: "+JSON.stringify(requests));
  assert(requests.every(r=>r.startsWith("GET /api/operator/v1/spot-radar/")&&!r.endsWith("/burn-in")),"Home reads another owner's source: "+JSON.stringify(requests));
  assert(!/Capital disponible|Burn-in|\bPF\b|Win Rate/.test(await home.innerText()),"Home duplicated domain data");
  for(const [label,theme]of [["Sombre","dark"],["Clair","light"]]){
   await page.getByRole("button",{name:"Paramètres de l’application"}).click();await page.getByRole("radio",{name:label,exact:true}).check();
   assert(await page.locator("html").getAttribute("data-theme")===theme,"Theme control failed");
   await page.keyboard.press("Escape");await page.reload({waitUntil:"networkidle"});
   assert(await page.locator("html").getAttribute("data-theme")===theme,"Theme persistence failed");
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Horizontal overflow");
   await page.screenshot({path:out+"/home-"+theme+"-"+width+".png",fullPage:true});
  }
  assert(!errors.length,errors.join("\n"));checks.push({width,home:"/paper-live/market/radar",module_links:7,home_sources:[...new Set(requests)],theme_persistence:"PASS",page_errors:0});
  await context.close();
 }
 await writeFile(out+"/checks.json",JSON.stringify({scope:"SOURCE_ONLY_SYNTHETIC_NOT_RUNTIME",checks},null,2));
 console.log("MARKET_HOME_MODULE_NAV_LIGHT_DARK_PERSISTENCE_NO_DUPLICATE_TRUTH=PASS");
}finally{await browser.close();}
