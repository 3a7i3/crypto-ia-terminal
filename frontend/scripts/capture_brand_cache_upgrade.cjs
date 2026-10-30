// Isolated upgrade proof: loopback fixture assets only; never proxies the Operator API.
const {chromium}=require("playwright");
const http=require("node:http"),fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto"),{execFileSync}=require("node:child_process");
const requiredDist=(name)=>{if(!process.env[name])throw Error(name+" is required");return path.resolve(process.env[name]);};
const old=requiredDist("BRAND_LEGACY_DIST");
const current=requiredDist("BRAND_CURRENT_DIST");
const fixed=process.env.BRAND_FIX_DIST?path.resolve(process.env.BRAND_FIX_DIST):null;
let selected=old;
const out=path.resolve(process.env.BRAND_CACHE_OUT_DIR||"artifacts/brand-cache-upgrade");
fs.mkdirSync(out,{recursive:true});
const hash=b=>crypto.createHash("sha256").update(b).digest("hex");
const snapshot=()=>process.env.BRAND_SERVICE_IDENTITY_CHECK==="true"?execFileSync("systemctl",["show","crypto-operator-api.service","crypto-operator-web.service","-p","Id","-p","MainPID","-p","ActiveEnterTimestamp","-p","NRestarts"],{encoding:"utf8"}):"NOT_REQUESTED_SOURCE_ONLY";
const before=snapshot(),blocked=[],errors=[],requests=[];
const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".webmanifest":"application/manifest+json"};
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,"http://127.0.0.1");
 if(!["GET","HEAD"].includes(req.method)){res.writeHead(405);return res.end()}
 requests.push({path:u.pathname,release:selected});
 if(u.pathname.startsWith("/api/")){res.writeHead(503,{"content-type":"application/json","cache-control":"no-store"});return res.end('{"error_code":"SOURCE_NOT_DEPLOYED"}')}
 if(u.pathname==="/healthz"){res.writeHead(200,{"content-type":"application/json","cache-control":"no-store"});return res.end('{"transport_ready":true}')}
 const workerHeld = fixed && selected===fixed && ["/sw.js","/pwa-policy.js"].includes(u.pathname);
 const staticRoot=workerHeld?old:selected;
 let p=path.resolve(staticRoot,"."+u.pathname);
 if(!p.startsWith(staticRoot+path.sep)||!fs.existsSync(p)||!fs.statSync(p).isFile())p=path.join(staticRoot,"index.html");
 res.writeHead(200,{"content-type":mime[path.extname(p)]||"application/octet-stream","cache-control":"no-store"});
 res.end(req.method==="HEAD"?undefined:fs.readFileSync(p));
});
async function imageHash(page,url){return page.evaluate(async url=>{const b=await(await fetch(url)).arrayBuffer();return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",b))).map(x=>x.toString(16).padStart(2,"0")).join("")},url);}
(async()=>{
 await new Promise(r=>server.listen(0,"127.0.0.1",r));
 const base="http://127.0.0.1:"+server.address().port;
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,args:["--disable-background-networking","--disable-component-update","--no-first-run"]});
 try{
 const context=await browser.newContext({viewport:{width:980,height:2200},serviceWorkers:"allow"});
 await context.route("**/*",route=>{const req=route.request(),url=new URL(req.url());if(url.origin===base&&["GET","HEAD"].includes(req.method()))return route.continue();blocked.push(req.url());return route.abort()});
 const page=await context.newPage();page.on("pageerror",e=>errors.push(String(e)));
 await page.goto(base+"/direction",{waitUntil:"domcontentloaded"});
 await page.evaluate(async()=>{await navigator.serviceWorker.register("/sw.js",{scope:"/"});await navigator.serviceWorker.ready});
 await page.waitForFunction(()=>navigator.serviceWorker.controller!==null);
 const oldHash=hash(fs.readFileSync(path.join(old,"icons/operator-192.png")));
 if(await imageHash(page,"/icons/operator-192.png")!==oldHash)throw Error("Old shell icon not established");
 selected=current;
 await page.goto(base+"/direction",{waitUntil:"domcontentloaded"});
 await page.locator(".app-brand img").waitFor();
 await page.locator(".app-brand img").evaluate(e=>e.decode());
 const cached=await imageHash(page,"/icons/operator-192.png");
 const network=hash(await (await context.request.get(base+"/icons/operator-192.png")).body());
 const expected=hash(fs.readFileSync(path.join(current,"icons/operator-192.png")));
 if(cached!==oldHash||network!==expected||cached===network)throw Error("Warm-cache defect not reproduced");
 await page.screenshot({path:path.join(out,"warm-cache-before.png"),fullPage:false});
 const result={at_utc:new Date().toISOString(),scope:"ISOLATED_SYNTHETIC_LOOPBACK_OLD_TO_CURRENT_SERVICE_WORKER",production_api_contacted:false,sandbox:true,service_workers:"allowed",reproduced:true,cache_key:"/icons/operator-192.png",cached_sha256:cached,old_sha256:oldHash,network_sha256:network,expected_new_sha256:expected,fix_tested:false,blocked,errors};
 if(fixed){
  selected=fixed;
  await page.goto(base+"/direction",{waitUntil:"domcontentloaded"});
  await page.waitForFunction(prefix=>document.querySelector(".app-brand img")?.getAttribute("src")?.includes(prefix),expected.slice(0,12));
  const url=await page.locator(".app-brand img").getAttribute("src");
  await page.locator(".app-brand img").evaluate(e=>e.decode());
  const actual=await imageHash(page,url);
  if(actual!==expected)throw Error("Fixed warm-cache logo mismatch");
  await page.screenshot({path:path.join(out,"warm-cache-after.png"),fullPage:false});
  result.fix_tested=true;result.fixed_src=url;result.fixed_sha256=actual;
  result.old_worker_retained_for_fix=true;result.legacy_cache_retained=(await imageHash(page,"/icons/operator-192.png"))===oldHash;
  if(!result.legacy_cache_retained)throw Error("Regression must preserve the pre-existing legacy cache");
  const manifest=await(await page.request.get(base+"/manifest.webmanifest")).json();
  if(!manifest.icons.every(i=>i.src.startsWith("/icons/operator-agents-")))throw Error("Installable icons not versioned");
  if(!(await page.locator('link[rel="icon"]').getAttribute("href")).includes(expected.slice(0,12)))throw Error("Favicon not versioned");
 }
 if(blocked.length||errors.length)throw Error(JSON.stringify({blocked,errors}));
 if(snapshot()!==before)throw Error("Active services changed during fixture audit");
 result.service_identity_before_and_after=before;
 fs.writeFileSync(path.join(out,fixed?"WARM_CACHE_FIXED.json":"WARM_CACHE_REPRODUCED.json"),JSON.stringify(result,null,2)+"\n");
 console.log(JSON.stringify(result));
 await context.close();
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1});
