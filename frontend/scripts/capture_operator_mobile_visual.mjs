// Preview isolé : toutes les API sont synthétiques, aucun accès production.
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
const out = process.env.MOBILE_OUT_DIR ?? 'artifacts/operator-mobile';
const base = process.env.MOBILE_PREVIEW_URL ?? 'http://127.0.0.1:3002';
if (!['127.0.0.1','localhost'].includes(new URL(base).hostname)) throw new Error('Local preview only');
await mkdir(out,{recursive:true});
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH || undefined});
const checks=[], errors=[], requests=[];
const assert=(ok,message)=>{if(!ok)throw new Error(message);checks.push(message);};
try {
 for (const width of [360,390,412,1440]) {
  const page=await browser.newPage({viewport:{width,height:844}});
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))requests.push(`${r.method()} ${new URL(r.url()).pathname}`);});
  for(const [name,path,id] of [['machine','/direction','direction-view'],['finance','/paper-live/finance','financial-reconciliation-view'],['decisions','/paper-live/decisions','decisions-view'],['portfolio','/paper-live/portfolio','portfolio-view'],['overview','/paper-live/overview','overview-view'],['research','/research','research-lab-view'],['burnin','/paper-live/burn-in','burnin-view']]) {
   await page.goto(base+path,{waitUntil:'networkidle'}); await page.getByTestId(id).waitFor();
   assert(await page.getByText('DÉMONSTRATION · DONNÉES FICTIVES',{exact:true}).isVisible(),`${name}/${width}: synthetic label`);
   if(name==='machine') assert(await page.locator('.financial-history').count()===0,`machine/${width}: chart absent`);
   if(name==='decisions') {
    assert(await page.getByLabel('Recherche par symbole').isVisible(),`decisions/${width}: labelled search`);
    await page.getByLabel('Recherche par symbole').focus(); await page.keyboard.press('Tab');
    assert(await page.getByLabel('Décision',{exact:true}).evaluate(e=>e===document.activeElement),`decisions/${width}: keyboard labels`);
    assert(await page.getByLabel('Recherche par symbole').evaluate(e=>e.getBoundingClientRect().height>=44),`decisions/${width}: tactile target`);
    const contrast = await page.evaluate(()=> {
      const luminance=c=>{const a=c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4});return .2126*a[0]+.7152*a[1]+.0722*a[2];};
      return ['tone-ok','tone-reject','tone-unknown','mobile-attention'].map(cls=>{const e=document.createElement('span');e.className=cls;e.style.background='var(--bg-card-soft)';document.body.append(e);const st=getComputedStyle(e),f=luminance(st.color),b=luminance(st.backgroundColor);e.remove();return {cls,ratio:(Math.max(f,b)+.05)/(Math.min(f,b)+.05)};});
    });
    assert(contrast.every(c=>c.ratio>=4.5),`decisions/${width}: semantic contrast AA ${JSON.stringify(contrast)}`);
    await page.getByLabel('Recherche par symbole').fill('NO_MATCH');
    assert(await page.getByTestId('decision-mobile-card').count()===0,`decisions/${width}: no invented result`);
    await page.getByRole('button',{name:'Réinitialiser',exact:true}).click();
    await page.getByText('Vue technique · tableau complet',{exact:true}).click();
   }
   if(name==='overview') assert(await page.locator('.overview-diagnostics[open]').count()===0,`overview/${width}: raw diagnostics closed`);
   const overflow=await page.evaluate(()=>({width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,offenders:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,50)})).slice(0,6)}));
   assert(overflow.width<=overflow.client+1,`${name}/${width}: no horizontal overflow ${JSON.stringify(overflow)}`);
   await page.screenshot({path:`${out}/${name}-${width}.png`,fullPage:true});
  }
  await page.close();
 }
 for(const scenario of ['missing','stale']) {
  const page=await browser.newPage({viewport:{width:360,height:844}});
  await page.context().addCookies([{name:'ux-demo-scenario',value:scenario,url:base}]);
  for(const [name,path] of [['machine','/direction'],['research','/research'],['burnin','/paper-live/burn-in'],['decisions','/paper-live/decisions'],['portfolio','/paper-live/portfolio']]) {
   await page.goto(base+path,{waitUntil:'networkidle'});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),`${scenario}/${name}: no horizontal overflow`);
   if(scenario==='missing' && ['research','burnin'].includes(name))assert(await page.getByTestId('source-availability').isVisible(),`${scenario}/${name}: useful degradation`);
   await page.screenshot({path:`${out}/${scenario}-${name}-360.png`,fullPage:true});
  }
  await page.close();
 }
 assert(errors.length===0,'No browser exception');
 assert(requests.every(r=>r.startsWith('GET /api/operator/v1/')),'Canonical GET only');
 await writeFile(`${out}/checks.json`,JSON.stringify({scope:'SOURCE_PROOF_SYNTHETIC_NOT_RUNTIME',widths:[360,390,412,1440],checks,errors,requests:[...new Set(requests)]},null,2));
 console.log(`MOBILE_VISUAL=PASS (${checks.length} checks)`);
} finally {await browser.close();}
