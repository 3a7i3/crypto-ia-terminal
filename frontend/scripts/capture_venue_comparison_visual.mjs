import { createRequire } from "node:module";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,"../dist");
const fixtures=process.env.CROSS_STACK_FIXTURES_DIR;
if(!fixtures)throw Error("CROSS_STACK_FIXTURES_DIR required; no fixture skips");
const out=path.resolve(here,"../artifacts/market-venues"),origin="http://127.0.0.1:4173";
const read=async name=>JSON.parse(await readFile(path.join(fixtures,name+".json"),"utf8"));
const good=await read("S_market_venues"),stale=await read("S_market_venues_stale"),unresolved=await read("S_market_venues_unresolved"),market=await read("R_market_catalogue"),pilot=await read("T_market_pilot");
const cases=[["synthetic",good],["pilot",pilot],["expired-between-polls",good],["stale",stale],["unresolved",unresolved],["missing",{http_status:503,body:{error_code:"VENUE_COMPARISON_NOT_CONFIGURED"}}],["invalid",{http_status:200,body:{...good.body,execution_authority:true}}]];
let assertions=0;const views=[],errors=[],blocked=[],requests=[];
const assert=(ok,m)=>{assertions++;if(!ok)throw Error(m);};
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,chromiumSandbox:true});
try{
 for(const theme of ["light","dark"])for(const width of [1440,768,393])for(const [name,fixture]of cases){
  const context=await browser.newContext({viewport:{width,height:900},locale:"fr-FR",serviceWorkers:"block"});
  await context.addInitScript(t=>localStorage.setItem("crypto-terminal.theme",t),theme);
  let comparisonRequests=0;
  await context.route("**/*",async route=>{
   const q=route.request(),u=new URL(q.url());
   if(u.origin!==origin||!["GET","HEAD"].includes(q.method())){blocked.push(q.method()+" "+u.href);return route.abort();}
   if(u.pathname.startsWith("/api/")){
    requests.push(q.method()+" "+u.pathname);
    if(u.pathname.endsWith("/venue-comparison"))comparisonRequests++;
    const f=u.pathname.endsWith("/venue-comparison")?fixture:u.pathname.endsWith("/market")?market:{http_status:503,body:{error_code:"SYNTHETIC_NOT_AVAILABLE"}};
    return route.fulfill({status:f.http_status,contentType:"application/json",body:JSON.stringify(f.body)});
   }
   const target=q.isNavigationRequest()?path.join(root,"index.html"):path.resolve(root,"."+u.pathname);
   assert(target.startsWith(root+path.sep),"static path remains in build");
   const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".webmanifest":"application/manifest+json"};
   return route.fulfill({status:200,contentType:mime[path.extname(target)]||"application/octet-stream",body:await readFile(target)});
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on("pageerror",e=>errors.push(String(e)));
  // M1-C5 (F4): /paper-live/market opens the Scanner view (Radar Spot, M1-C3);
  // the comparison is the addressable view /paper-live/market/venues.
  await page.goto(origin+"/paper-live/market",{waitUntil:"domcontentloaded"});
  await page.waitForURL(/\/paper-live\/market\/radar$/);
  assert(await page.getByRole("tab",{name:"Scanner",exact:true}).getAttribute("aria-selected")==="true","scanner remains default");
  assert(comparisonRequests===0,"inactive comparison view is not read");
  await page.getByRole("tab",{name:"Comparaison des plateformes",exact:true}).click();
  await page.waitForURL(/\/paper-live\/market\/venues$/);
  if(name==="missing"||name==="invalid"){
   await page.getByText("Aucune publication de comparaison disponible.",{exact:true}).waitFor();
   assert(await page.getByTestId("venue-comparison-view").getByRole("table").count()===0,"unavailable is not empty numeric table");
   assert((await page.getByTestId("venue-comparison-view").innerText()).includes("disponibilité reste inconnue"),"unknown not zero");
   // M1-C2: an unconfigured source is shown apart from a contract failure.
   if(name==="missing")assert((await page.getByTestId("market-source-not-configured").innerText()).includes("VENUE_COMPARISON_NOT_CONFIGURED"),"unconfigured source distinct");
   else assert(await page.getByTestId("market-source-not-configured").count()===0,"contract failure is not unconfigured");
  }else{
   await page.getByTestId("venue-synthetic").waitFor();
   assert(await page.getByTestId("market-opportunity-row").count()===0,"comparison does not duplicate scanner");
   assert(await page.getByTestId("venue-row").count()===(name==="pilot"?2:4),"selected instrument retains the explicit expected source roster");
   assert((await page.getByTestId("venue-comparison-view").innerText()).includes("Exemple synthétique"),"fixture is never runtime proof");
   if(name==="expired-between-polls"){
    const before=await page.getByTestId("venue-comparison-view").innerText();
    assert(before.includes("29.97002997 bp"),"exact published metrics present before expiry");
    assert((await page.getByTestId("venue-comparison-view").getByRole("status").innerText()).includes("Publication récente"),"fixture initially fresh");
    await page.waitForFunction(()=>[...document.querySelectorAll('[data-testid="venue-comparison-view"] [role="status"]')].some(e=>e.textContent.includes("périmée")));
    assert(comparisonRequests===1,"expiry happens before any second API response");
    assert((await page.getByTestId("venue-comparison-view").innerText()).includes("29.97002997 bp"),"expiry keeps the original published exact value with its stale state");
   }
   if(name==="pilot"){
    assert((await page.getByTestId("venue-comparison-view").innerText()).includes("29.97002997 bp"),"bounded synthetic pilot reaches the app unchanged");
   }
   if(name==="stale")assert((await page.getByTestId("venue-comparison-view").getByRole("status").innerText()).includes("périmée"),"stale visible");
   if(name==="unresolved")assert((await page.getByTestId("venue-comparison-view").getByRole("status").innerText()).includes("indisponible"),"unresolved visible");
   if(name==="synthetic"){
    assert((await page.getByTestId("venue-comparison-view").innerText()).includes("29.97002997 bp"),"published basis visible");
    await page.getByRole("button",{name:"Détail source MEXC",exact:true}).click();
    const detail=page.getByTestId("venue-source-detail");await detail.waitFor();
    assert(await detail.evaluate(e=>e===document.activeElement),"source detail receives focus");
    assert((await detail.innerText()).includes("Date non disponible")&&(await detail.innerText()).includes("UNRESOLVED_TIMESTAMP_KIND"),"missing book time remains unresolved");
    await page.keyboard.press("Escape");
    assert(await page.getByRole("button",{name:"Détail source MEXC",exact:true}).evaluate(e=>e===document.activeElement),"detail restores focus");
    const usd=good.body.groups.find(g=>g.instrument.quote_asset_id==="USD");
    await page.getByLabel("Instrument observé",{exact:true}).selectOption(usd.instrument_id);
    assert(await page.getByTestId("venue-row").count()===3,"USD not combined with USDT");
    await page.getByLabel("Instrument observé",{exact:true}).selectOption(good.body.groups[0].instrument_id);
    await page.getByLabel("Plateforme de référence",{exact:true}).selectOption("okx");
    const reverse=good.body.groups[0].comparisons.find(p=>p.reference_venue==="okx"&&p.other_venue==="bybit");
    assert((await page.getByTestId("venue-comparison-view").innerText()).includes(reverse.mid_basis_bps+" bp"),"reference uses published reverse pair");
   }
  }
  const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert(geometry.scroll<=geometry.width+1,"no page overflow");
  await page.evaluate(()=>window.scrollTo(0,0));
  const label=theme+"-"+width+"-"+name;await page.screenshot({path:path.join(out,label+".png"),fullPage:true});
  views.push({label,...geometry});
  await context.close();
 }
 // M1-C5 (F4): the four active Market routes, addressed directly. Each selects
 // its own tab, mounts one panel and reads only its own source; CryptoRadar
 // historique is offered nowhere, including through the obsolete ?radar=0.
 const ROUTES=[["radar","Scanner",p=>p.startsWith("/api/operator/v1/spot-radar/")],["venues","Comparaison des plateformes",p=>p==="/api/operator/v1/venue-comparison"||p==="/api/operator/v1/derivatives-stress"],["flow","Flux",p=>p==="/api/operator/v1/market-flow"||p==="/api/operator/v1/derivatives-stress"],["lmi","Microstructure",p=>p==="/api/operator/v1/market-microstructure"]];
 const routeChecks=[];
 for(const [slug,label,own] of ROUTES)for(const suffix of ["",...(slug==="radar"?["?radar=0"]:[])]){
  const context=await browser.newContext({viewport:{width:1440,height:900},locale:"fr-FR",serviceWorkers:"block"});
  const read=[];
  await context.route("**/*",async route=>{
   const q=route.request(),u=new URL(q.url());
   if(u.origin!==origin||!["GET","HEAD"].includes(q.method())){blocked.push(q.method()+" "+u.href);return route.abort();}
   if(u.pathname.startsWith("/api/")){read.push(u.pathname);requests.push(q.method()+" "+u.pathname);return route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({error_code:"SYNTHETIC_NOT_AVAILABLE"})});}
   const target=q.isNavigationRequest()?path.join(root,"index.html"):path.resolve(root,"."+u.pathname);
   assert(target.startsWith(root+path.sep),"static path remains in build");
   const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".webmanifest":"application/manifest+json"};
   return route.fulfill({status:200,contentType:mime[path.extname(target)]||"application/octet-stream",body:await readFile(target)});
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on("pageerror",e=>errors.push(String(e)));
  await page.goto(origin+"/paper-live/market/"+slug+suffix,{waitUntil:"networkidle"});
  assert(await page.getByTestId("market-panel").getAttribute("data-market-view")===slug,slug+": wrong panel");
  assert(await page.getByRole("tabpanel").count()===1,slug+": one mounted panel");
  for(const [other,otherLabel] of ROUTES)assert(await page.getByRole("tab",{name:otherLabel,exact:true}).getAttribute("aria-selected")===String(other===slug),slug+": tab state "+other);
  assert(read.length>0&&read.every(own),slug+": reads only its own source: "+read.join(", "));
  const text=await page.locator("body").innerText();
  assert(!/CryptoRadar historique/i.test(text),slug+suffix+": historical CryptoRadar offered");
  assert(await page.getByTestId("market-scanner-coverage").count()===0&&await page.getByTestId("market-view").count()===0,slug+suffix+": historical scanner mounted");
  if(suffix)assert(!page.url().includes("radar=0"),"obsolete ?radar=0 dropped");
  routeChecks.push({route:"/paper-live/market/"+slug+suffix,reads:[...new Set(read)]});
  await context.close();
 }
 assert(!errors.length&&!blocked.length,"no page errors or external/mutation requests");
 assert(requests.every(r=>r.startsWith("GET /api/operator/v1/")),"GET-only artifact reads");
 await writeFile(path.join(out,"checks.json"),JSON.stringify({disposition:"SOURCE_ONLY_SYNTHETIC_VENUE_UI_PASS",assertions,views,market_routes:routeChecks,errors,blocked,requests:[...new Set(requests)],fixtures_used:true,sandbox:true,service_workers:"blocked",active_api_reached:false,server_started:false},null,2)+"\n");
 console.log("VENUE_COMPARISON_BROWSER_PASS",assertions,views.length);
}catch(error){await writeFile(path.join(out,"checks.json"),JSON.stringify({disposition:"SOURCE_ONLY_SYNTHETIC_VENUE_UI_FAIL",assertions,views,errors,blocked,error:String(error)},null,2)+"\n");throw error;}finally{await browser.close();}
