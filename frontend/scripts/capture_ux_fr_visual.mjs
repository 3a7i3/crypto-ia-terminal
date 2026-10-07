import { chromium } from 'playwright';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
const out = process.env.UX_FR_OUT_DIR ?? 'artifacts/ux-fr/after';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const checks = [], errors = [], requests = [];
const assert = (ok, message) => { if (!ok) throw new Error(message); checks.push(message); };
const base = 'http://127.0.0.1:3002';
try {
 for (const width of [1440, 820, 390, 320]) {
  const page = await browser.newPage({ viewport:{ width, height:width < 760 ? 844 : 1000 } });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) requests.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  for (const [name, path, testid] of [
    ['machine','/direction','direction-view'],['radar','/paper-live/market','market-view'],
    ['finance','/paper-live/finance','financial-reconciliation-view'],['portfolio','/paper-live/portfolio','portfolio-view'],
    ['research','/research','research-lab-view'],['strategies','/research/strategies','strategy-board-view'],
    ['comparison','/paper-live/lifecycle','ppl-comparison-view'],
  ]) {
   await page.goto(base + path, {waitUntil:'networkidle'});
   await page.getByTestId(testid).waitFor();
   assert(await page.getByText('DÉMONSTRATION · DONNÉES FICTIVES',{exact:true}).isVisible(), `${name}/${width}: demonstration label`);
   const overflow = await page.evaluate(()=>({width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,offenders:Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,60)})).slice(0,8)}));
   if(overflow.width > overflow.client+1) { await page.screenshot({path:`${out}/overflow-${name}-${width}.png`,fullPage:true}); console.log(overflow); }
   assert(overflow.width <= overflow.client+1, `${name}/${width}: no page overflow`);
   if(name === 'machine') {
    assert(await page.locator('#machine-state').isVisible(),`machine/${width}: state section`);
    assert(await page.locator('.section-evidence[open]').count()===0,`machine/${width}: evidence initially closed`);
    await page.getByRole('link',{name:'Portefeuille et finances',exact:true}).click();
    assert((await page.evaluate(()=>location.hash)) === '#machine-finance',`machine/${width}: category navigation`);
    await page.getByRole('button',{name:'Résultat réalisé fictif',exact:true}).click();
    assert(await page.getByRole('img',{name:'Résultat réalisé fictif de 0 à 12 USDT'}).isVisible(),`machine/${width}: fictitious realized series`);
    await page.getByRole('button',{name:'Portefeuille fictif',exact:true}).click();
   }
   if(name === 'radar') {
    const region = page.getByRole('region',{name:'Scanner CryptoRadar · défilement horizontal'});
    assert(await region.isVisible(),`radar/${width}: one table`);
    assert(await page.locator('.market-opportunity-card').count()===0,`radar/${width}: no duplicated mobile cards`);
    const initial = await page.getByTestId('market-opportunity-row').first().innerText();
    await page.getByLabel('Recherche symbole',{exact:true}).fill('S25');
    assert(await page.getByTestId('market-opportunity-row').count()===1,`radar/${width}: search`);
    const symbol = page.getByRole('button',{name:/Détail S25/});
    await symbol.click();
    assert(await page.getByTestId('market-symbol-detail').evaluate(e=>e===document.activeElement),`radar/${width}: detail focus`);
    await page.keyboard.press('Escape');
    assert(await symbol.evaluate(e=>e===document.activeElement),`radar/${width}: focus returns`);
    await page.getByRole('button',{name:'Réinitialiser'}).click();
    assert((await page.getByTestId('market-opportunity-row').first().innerText())===initial,`radar/${width}: source order preserved`);
    if(width<760) {
     const before = await page.locator('.market-table-symbol').first().boundingBox();
     await region.evaluate(e=>e.scrollLeft=250);
     const after = await page.locator('.market-table-symbol').first().boundingBox();
     assert(Math.abs(before.x-after.x)<2,`radar/${width}: symbol stays fixed`);
     await region.evaluate(e=>e.scrollLeft=0);
    }
   }
   if(name === 'strategies') {
    const area = page.locator('.strategy-table-desktop');
    await area.getByRole('button',{name:/Momentum.*Performance.*Satisfait/}).click();
    assert(await page.getByTestId('strategy-detail').evaluate(e=>e===document.activeElement),`strategies/${width}: detail focus`);
    await page.getByTestId('strategy-detail').screenshot({path:`${out}/strategy-detail-${width}.png`});
    await page.keyboard.press('Escape');
    await page.getByText('Rechercher et filtrer les stratégies',{exact:true}).click();
    await page.getByLabel('Type de candidat',{exact:true}).selectOption('FEATURE');
    assert(await page.getByTestId('strategy-row').count()===0 && await page.getByTestId('strategy-empty').isVisible(),`strategies/${width}: filter has no invented rows`);
    await page.getByLabel('Type de candidat',{exact:true}).selectOption('ALL');
    await page.getByText('Rechercher et filtrer les stratégies',{exact:true}).click();
   }
   if(name === 'finance') {
    const metric = page.locator('.fin-metric').filter({has:page.getByText('Capital disponible',{exact:true})});
    await metric.getByText('Valeur exacte',{exact:true}).click();
    assert((await metric.locator('code').innerText()) === JSON.parse(await readFile(new URL('../.cross-stack-fixtures/P_financial_clarity.json',import.meta.url),'utf8')).body.financial.cash_available,`finance/${width}: exact decimals inspectable`);
    await metric.getByText('Valeur exacte',{exact:true}).click();
    await page.getByText(/^Preuves de réconciliation ·/).click();
    assert(await page.locator(width<760?'.fin-mobile-records':'.fin-table-wrap').isVisible(),`finance/${width}: evidence layout`);
    await page.getByText(/^Preuves de réconciliation ·/).click();
   }
   await page.evaluate(()=>window.scrollTo(0,0));
   // Allow scroll/compositor layers to settle before recording evidence.
   await page.waitForTimeout(150);
   await page.screenshot({path:`${out}/${name}-viewport-${width}.png`});
   await page.screenshot({path:`${out}/${name}-${width}.png`,fullPage:true});
  }
  await page.close();
 }
 for(const scenario of ['stale','missing']) {
  const page = await browser.newPage({viewport:{width:390,height:844}});
  await page.context().addCookies([{name:'ux-demo-scenario',value:scenario,url:base}]);
  for(const path of ['/direction','/paper-live/market','/paper-live/finance','/research/strategies']) {
   await page.goto(base+path,{waitUntil:'networkidle'});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),`${scenario}${path}: no page overflow`);
   if(scenario==='missing') assert(await page.locator('.market-opportunity-row,.strategy-row').count()===0,`${scenario}${path}: no invented rows`);
   await page.screenshot({path:`${out}/${scenario}-${path.split('/').at(-1)}-390.png`,fullPage:true});
  }
  await page.close();
 }
 assert(errors.length===0,'No browser exceptions');
 assert(requests.every(r=>r.startsWith('GET /api/operator/v1/')),'Canonical GET only');
 await writeFile(`${out}/checks.json`,JSON.stringify({data:'DEMONSTRATION_SYNTHETIQUE_AUCUNE_PREUVE_RUNTIME',checks,errors,requests:[...new Set(requests)]},null,2));
 console.log(`UX_FR_VISUAL=PASS (${checks.length} checks)`);
} finally { await browser.close(); }
