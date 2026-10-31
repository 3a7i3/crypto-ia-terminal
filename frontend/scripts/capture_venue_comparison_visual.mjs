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
const good=await read("S_market_venues"),stale=await read("S_market_venues_stale"),unresolved=await read("S_market_venues_unresolved"),market=await read("R_market_catalogue");
const cases=[["synthetic",good],["stale",stale],["unresolved",unresolved],["missing",{http_status:503,body:{error_code:"VENUE_COMPARISON_NOT_CONFIGURED"}}],["invalid",{http_status:200,body:{...good.body,execution_authority:true}}]];
let assertions=0;const views=[],errors=[],blocked=[],requests=[];
const assert=(ok,m)=>{assertions++;if(!ok)throw Error(m);};
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,chromiumSandbox:true});
try{
 for(const theme of ["light","dark"])for(const width of [1440,768,393])for(const [name,fixture]of cases){
  const context=await browser.newContext({viewport:{width,height:900},locale:"fr-FR",serviceWorkers:"block"});
  await context.addInitScript(t=>localStorage.setItem("crypto-terminal.theme",t),theme);
  await context.route("**/*",async route=>{
   const q=route.request(),u=new URL(q.url());
   if(u.origin!==origin||!["GET","HEAD"].includes(q.method())){blocked.push(q.method()+" "+u.href);return route.abort();}
   if(u.pathname.startsWith("/api/")){
    requests.push(q.method()+" "+u.pathname);
    const f=u.pathname.endsWith("/venue-comparison")?fixture:u.pathname.endsWith("/market")?market:{http_status:503,body:{error_code:"SYNTHETIC_NOT_AVAILABLE"}};
    return route.fulfill({status:f.http_status,contentType:"application/json",body:JSON.stringify(f.body)});
   }
   const target=q.isNavigationRequest()?path.join(root,"index.html"):path.resolve(root,"."+u.pathname);
   assert(target.startsWith(root+path.sep),"static path remains in build");
   const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".webmanifest":"application/manifest+json"};
   return route.fulfill({status:200,contentType:mime[path.extname(target)]||"application/octet-stream",body:await readFile(target)});
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on("pageerror",e=>errors.push(String(e)));
  await page.goto(origin+"/paper-live/market",{waitUntil:"domcontentloaded"});
  await page.getByTestId("market-opportunity-row").first().waitFor();
  assert(await page.getByRole("tab",{name:"Scanner",exact:true}).getAttribute("aria-selected")==="true","scanner remains default");
  await page.getByRole("tab",{name:"Comparaison des plateformes",exact:true}).click();
  if(name==="missing"||name==="invalid"){
   await page.getByText("Aucune publication de comparaison disponible.",{exact:true}).waitFor();
   assert(await page.getByRole("table").count()===0,"unavailable is not empty numeric table");
   assert((await page.getByTestId("venue-comparison-view").innerText()).includes("disponibilité reste inconnue"),"unknown not zero");
  }else{
   await page.getByTestId("venue-synthetic").waitFor();
   assert(await page.getByTestId("market-opportunity-row").count()===0,"comparison does not duplicate scanner");
   assert(await page.getByTestId("venue-row").count()===4,"one selected instrument with four expected sources");
   assert((await page.getByTestId("venue-comparison-view").innerText()).includes("Exemple synthétique"),"fixture is never runtime proof");
   if(name==="stale")assert((await page.getByRole("status").innerText()).includes("périmée"),"stale visible");
   if(name==="unresolved")assert((await page.getByRole("status").innerText()).includes("indisponible"),"unresolved visible");
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
 assert(!errors.length&&!blocked.length,"no page errors or external/mutation requests");
 assert(requests.every(r=>r.startsWith("GET /api/operator/v1/")),"GET-only artifact reads");
 await writeFile(path.join(out,"checks.json"),JSON.stringify({disposition:"SOURCE_ONLY_SYNTHETIC_VENUE_UI_PASS",assertions,views,errors,blocked,requests:[...new Set(requests)],fixtures_used:true,sandbox:true,service_workers:"blocked",active_api_reached:false,server_started:false},null,2)+"\n");
 console.log("VENUE_COMPARISON_BROWSER_PASS",assertions,views.length);
}catch(error){await writeFile(path.join(out,"checks.json"),JSON.stringify({disposition:"SOURCE_ONLY_SYNTHETIC_VENUE_UI_FAIL",assertions,views,errors,blocked,error:String(error)},null,2)+"\n");throw error;}finally{await browser.close();}
