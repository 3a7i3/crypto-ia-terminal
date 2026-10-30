// Current home replaces the historical Direction dashboard. Domain-value and
// legacy burn-in contracts remain covered by unit/cross-stack tests.
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
  assert(await page.locator(".module-card").count()===6,"Six module owners missing");
  assert(await page.getByText("Source indisponible",{exact:true}).count()===6,"Absence fabricated availability");
  assert(requests.length===5 && new Set(requests).size===5,"Home must share canonical source and use five GETs");
  assert(requests.every(r=>r.startsWith("GET /api/operator/v1/")&&!r.endsWith("/burn-in")),"Unexpected request");
  assert(!/Capital disponible|Burn-in|PF|Win Rate/.test(await page.getByTestId("module-home").innerText()),"Home duplicated domain data");
  if(width<=640){await page.getByRole("button",{name:"Ouvrir les modules"}).click();assert(await page.getByRole("navigation",{name:"Modules de la machine"}).isVisible(),"Mobile modules inaccessible");await page.keyboard.press("Escape");}
  for(const [label,theme]of [["Sombre","dark"],["Clair","light"]]){
   await page.getByRole("button",{name:"Paramètres de l’application"}).click();await page.getByRole("radio",{name:label,exact:true}).check();
   assert(await page.locator("html").getAttribute("data-theme")===theme,"Theme control failed");
   await page.keyboard.press("Escape");await page.reload({waitUntil:"networkidle"});
   assert(await page.locator("html").getAttribute("data-theme")===theme,"Theme persistence failed");
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Horizontal overflow");
   await page.screenshot({path:out+"/home-"+theme+"-"+width+".png",fullPage:true});
  }
  assert(!errors.length,errors.join("\n"));checks.push({width,modules:6,unique_sources:5,theme_persistence:"PASS",page_errors:0});
  await context.close();
 }
 await writeFile(out+"/checks.json",JSON.stringify({scope:"SOURCE_ONLY_SYNTHETIC_NOT_RUNTIME",checks},null,2));
 console.log("MODULE_HOME_LIGHT_DARK_PERSISTENCE_NO_DUPLICATE_TRUTH=PASS");
}finally{await browser.close();}
