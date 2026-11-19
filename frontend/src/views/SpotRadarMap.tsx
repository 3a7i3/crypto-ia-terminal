import { RadarCandles } from "../components/RadarCandles";
import React,{useEffect,useRef,useState} from "react";
import {fetchRadar,RadarError,type RadarScanner,type RadarHistory,type RadarRow,type Timeframe,type Freshness} from "../lib/spotRadarClient";
import {decimalCompare} from "../lib/intradayClient";
import "../intraday.css";
import "../spot-radar.css";
import { MarketSourceNotice } from "../components/MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
const labels:Record<Freshness,string>={LIVE:"LIVE qualifié",STALE:"STALE · périmée",DISCONNECTED:"DISCONNECTED · déconnecté",UNRESOLVED:"UNRESOLVED · non résolu",SYNTHETIC:"SYNTHETIC · fictif"};
const utc=(s:string|null)=>s?new Date(Number(s)).toISOString().replace("T"," ").replace("Z"," UTC"):"Non disponible";
export const SpotRadarMap:React.FC=()=>{
 const [data,setData]=useState<RadarScanner|null>(null),[error,setError]=useState<string|null>(null),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(""),[filter,setFilter]=useState<"ALL"|Freshness>("ALL"),[list,setList]=useState(false),[selected,setSelected]=useState<string|null>(null);
 const [tf,setTf]=useState<Timeframe>("M5"),[history,setHistory]=useState<RadarHistory|null>(null),[historyError,setHistoryError]=useState<string|null>(null),[now,setNow]=useState(Date.now());
 const receivedAt=useRef(0),historyKey=useRef("");
 const origin=useRef<HTMLButtonElement|null>(null),closeRef=useRef<HTMLButtonElement|null>(null),panel=useRef<HTMLDivElement|null>(null);
 const close=()=>{setSelected(null);origin.current?.focus();};
 useEffect(()=>{const timer=setInterval(()=>setRefresh(n=>n+1),15_000);const age=setInterval(()=>setNow(Date.now()),1000);return()=>{clearInterval(timer);clearInterval(age);};},[]);
 useEffect(()=>{
  const controller=new AbortController();
  fetchRadar("scanner",{},controller.signal).then(d=>{if(!controller.signal.aborted){receivedAt.current=Date.now();setData(d);setError(null);setNow(Date.now());}}).catch(e=>{if(!controller.signal.aborted)setError(e instanceof RadarError?e.code:"TRANSPORT_ERROR");});
  return()=>controller.abort();
 },[refresh]);
 const stateOf=(r:RadarRow):Freshness=>{
  if(data?.evidence_kind==="SYNTHETIC")return "SYNTHETIC";
  const elapsed=Math.max(0,now-receivedAt.current);
  if(error||!data||Number(data.server_time_ms)+elapsed>Number(data.collector.expires_ms)||elapsed>45_000)return "DISCONNECTED";
  if(r.freshness.state==="LIVE"&&r.freshness.age_ms!==null&&r.freshness.age_ms+elapsed>45_000)return "STALE";
  return r.freshness.state;
 };
 const rows=(data?.rows??[]).filter(r=>(r.display_symbol.toUpperCase().includes(query.trim().toUpperCase())||r.identity.native_symbol.includes(query.trim().toUpperCase()))&&(filter==="ALL"||stateOf(r)===filter));
 const detail=data?.rows.find(r=>r.instrument_id===selected);
 useEffect(()=>{if(!selected)return;closeRef.current?.focus();const before=document.body.style.overflow;document.body.style.overflow="hidden";return()=>{document.body.style.overflow=before;};},[selected]);
 useEffect(()=>{
  const controller=new AbortController();const key=selected+":"+tf;if(historyKey.current!==key){setHistory(null);historyKey.current=key;}setHistoryError(null);
  if(detail)fetchRadar("ohlcv",{symbol:detail.identity.native_symbol,timeframe:tf},controller.signal).then(d=>{if(!controller.signal.aborted)setHistory(d);}).catch(e=>{if(!controller.signal.aborted)setHistoryError(e instanceof RadarError?e.code:"TRANSPORT_ERROR");});
  return()=>controller.abort();
 },[selected,tf,data?.snapshot_id]);
 const live=data?.rows.filter(r=>stateOf(r)==="LIVE").length??0;
 return <section className="intraday-desk spot-radar" aria-label="Radar Spot MEXC">
  <header className="intraday-heading"><div><p className="intraday-eyebrow">CAT / MARKET INTELLIGENCE</p><h2>Market Radar · MEXC Spot</h2><p className="intraday-lead">Le marché observé. Chaque chiffre remonte à sa source.</p></div>
   <span className="intraday-proof">{data?.evidence_kind==="SYNTHETIC"?"◆ SYNTHETIC":live>0?"● LIVE qualifié":"○ "+(data?.collector.state??"CONNEXION")}<small>{data?.evidence_kind==="SYNTHETIC"?"Fixture isolée · données fictives":"REST public · lecture seule"}</small></span>
  </header>
  <p className="intraday-disclaimer">Observation uniquement · bulles de taille égale · variation 24 h déclarée par MEXC · aucun score ni autorisation de trading.</p>
  <div className="intraday-controls">
   <label>Rechercher un symbole<input aria-label="Rechercher un symbole Radar" type="search" maxLength={120} value={query} placeholder="BTC, DOGE, ATOM…" onChange={e=>setQuery(e.target.value)}/></label>
   <label>Marché<select aria-label="Marché Radar"><option>Spot · MEXC</option></select></label>
   <label>Fraîcheur<select aria-label="Fraîcheur Radar" value={filter} onChange={e=>setFilter(e.target.value as typeof filter)}><option value="ALL">Tous les états</option>{Object.entries(labels).map(([s,l])=><option key={s} value={s}>{l}</option>)}</select></label>
   <div className="intraday-switch" role="group" aria-label="Affichage Radar"><button type="button" aria-pressed={!list} onClick={()=>setList(false)}>◉ Bulles</button><button type="button" aria-pressed={list} onClick={()=>setList(true)}>≡ Liste</button></div>
   <button type="button" className="intraday-refresh" onClick={()=>setRefresh(n=>n+1)}>Actualiser</button>
  </div>
  {!data&&!error&&<div role="status" className="intraday-loading"><span className="intraday-skeleton"/>Connexion aux observations publiques…</div>}
  {error&&(!data&&marketSourceSetup(error)?<MarketSourceNotice source="Radar Spot" setup={marketSourceSetup(error)!} code={error}/>:<div role="alert" className="intraday-error">API indisponible · {error}. {data?"Dernières valeurs conservées, état DISCONNECTED.":"Aucune donnée présentée comme actuelle."}</div>)}
  {data&&<>
   <div className="intraday-metrics" aria-label="Couverture Radar"><div><strong>{data.observed_instruments} / {data.selected_instruments}</strong><span>Instruments observés / sélectionnés</span></div><div><strong>{live}</strong><span>LIVE qualifiés</span></div><div><strong>{data.collector.state}</strong><span>Collecteur · {data.collector.reason}</span></div><div><strong>{data.rows.reduce((n,r)=>n+r.timeframes.length,0)} / {data.selected_instruments*4}</strong><span>Histoires OHLCV · cible 300 bougies</span></div></div>
   {data.collector.fault_injection&&<p role="status" className="intraday-error">Interruption simulée du laboratoire · aucune panne MEXC n’est affirmée.</p>}
   <div className="intraday-map-head"><h3>{list?"Liste accessible":"Carte des instruments"}</h3><span>{rows.length} instruments · mise à jour ≈ 15 s</span></div>
   <p className="intraday-coverage">Sélection bornée à 30 instruments : BTC, DOGE, ATOM puis volume quote 24 h vérifié. Univers Spot USDT uniquement. Taille égale, sans classement prédictif.</p>
   {!rows.length?<p role="status" className="intraday-empty">Aucun instrument pour ces filtres.</p>:<div className={list?"intraday-list":"intraday-bubbles"} aria-label="Instruments Spot observés">{rows.map((r,i)=>{
    const pct=r.ticker.change_qualified?r.ticker.change_pct_24h:null,sign=pct===null?0:decimalCompare(pct,"0"),fresh=stateOf(r);
    return <button key={r.instrument_id} type="button" className={"intraday-bubble "+(sign>0?"intraday-up":sign<0?"intraday-down":"intraday-neutral")} style={{"--bubble-index":i} as React.CSSProperties} aria-label={r.display_symbol+" · MEXC Spot · "+labels[fresh]} onClick={e=>{origin.current=e.currentTarget;setSelected(r.instrument_id);}}>
     <span className="intraday-bubble-market">MEXC / SPOT</span><strong>{r.base_asset}<small> / USDT</small></strong><span className="intraday-bubble-price">{r.ticker.last_price}</span><span className="intraday-bubble-change">{pct===null?"Non qualifiée":(sign>0?"+":"")+pct+" %"}<small>24 h · fournisseur</small></span><span className={"radar-state radar-"+fresh.toLowerCase()}>{labels[fresh]}</span>
    </button>;
   })}</div>}
   <div className="intraday-legend"><span>↗ Variation positive</span><span>↘ Variation négative</span><span>○ Variation non qualifiée</span><span>Couleur descriptive, sans anticipation.</span></div>
   <details className="intraday-provenance"><summary>Provenance, fraîcheur et limites</summary><dl><dt>Preuve</dt><dd>{data.evidence_kind} · {data.schema_version}</dd><dt>Collecte</dt><dd>{utc(data.collector.last_success_ms)}</dd><dt>Expiration du pilote</dt><dd>{utc(data.collector.expires_ms)}</dd><dt>Source</dt><dd>{data.source.base_url} · {data.source.exchange} · Spot public</dd><dt>Identité scientifique</dt><dd>{data.snapshot_id}</dd><dt>Preuve de sélection</dt><dd>{data.source.selection_sha256}</dd><dt>Horloge exchange</dt><dd>{utc(data.clock.server_ms)} · RTT {data.clock.rtt_ms} ms</dd></dl><p>LIVE exige un timestamp source et une réception de moins de 45 s, une horloge qualifiée et un collecteur actif. La publication seule ne prouve aucune fraîcheur. Le ticker fournit une fenêtre « 24 h » déclarée ; ses openTime / closeTime ne prouvent pas une durée exacte de 24 h. Les bid/ask ont seulement une heure de réception.</p></details>
   {detail&&<div className="intraday-modal-backdrop" onClick={e=>{if(e.target===e.currentTarget)close();}}><div ref={panel} className="intraday-detail" role="dialog" aria-modal="true" aria-labelledby="radar-detail-title" onKeyDown={e=>{
    if(e.key==="Escape"){e.preventDefault();close();}
    if(e.key==="Tab"){const nodes=panel.current?.querySelectorAll<HTMLElement>("button,input,select,summary,[href]");if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
   }}>
    <div className="radar-detail-toolbar"><p className="intraday-eyebrow">{labels[stateOf(detail)]} · MEXC Spot</p><button ref={closeRef} className="intraday-close" type="button" aria-label="Fermer le détail Radar" onClick={close}>Fermer ×</button></div>
    <div className="radar-detail-body"><h3 id="radar-detail-title">{detail.display_symbol}</h3>
    <div className="intraday-detail-price">{detail.ticker.last_price}<small>USDT · dernier prix public</small></div>
    <div className="radar-essential"><span>24 h : {detail.ticker.change_pct_24h??"Non qualifiée"}{detail.ticker.change_pct_24h!==null?" %":""}</span><span>Âge ticker : {detail.freshness.age_ms===null?"inconnu":Math.round((detail.freshness.age_ms+Math.max(0,now-receivedAt.current))/1000)+" s"}</span></div>
    <div className="radar-timeframes" aria-label="Unités de temps du graphique">{(["M5","M15","H1","H4"] as Timeframe[]).map(t=>{const ref=detail.timeframes.find(x=>x.timeframe===t);return <button type="button" key={t} aria-pressed={tf===t} onClick={()=>setTf(t)}>{t}<small>{ref?ref.history_count+" bougies":"En chargement"}</small></button>;})}</div>
    {historyError?<p role="status">Historique indisponible · {historyError}</p>:!history?<p role="status">Chargement du graphique…</p>:<>
    <RadarCandles rows={history.history.rows} symbol={detail.display_symbol} timeframe={tf}/>
    <p className="radar-history-age">Bougies reçues : {utc(history.history.received_ms)} · {history.history.quality} · {history.history.gaps.length} trous · {history.history.rejected} rejets. La réception des bougies est distincte de celle du prix courant.</p>
    <details className="radar-detail-facts"><summary>Valeurs exactes des dernières bougies</summary><div className="radar-bars"><table><caption>Dernières bougies {tf} · valeurs exactes</caption><thead><tr><th>Ouverture UTC</th><th>Clôture</th><th>Volume base</th><th>État observé</th></tr></thead><tbody>{history.history.rows.slice(-5).map(b=><tr key={b.open_ms}><td>{utc(b.open_ms)}</td><td>{b.close}</td><td>{b.base_volume}</td><td>{b.closed?"Clôturée":"Partielle"}</td></tr>)}</tbody></table></div></details></>}
    <details className="radar-detail-facts"><summary>Volumes 24 h et carnet</summary><dl><dt>Volume base / 24 h</dt><dd>{detail.ticker.base_volume_24h} {detail.base_asset}</dd><dt>Volume quote / 24 h</dt><dd>{detail.ticker.quote_volume_24h} USDT · natif</dd><dt>Bid / Ask</dt><dd>{detail.book.bid??"Absent"} / {detail.book.ask??"Absent"} · {detail.book.quality}</dd></dl></details>
    <details className="radar-detail-proof"><summary>Source, fraîcheur et preuves</summary><dl><dt>Instrument natif</dt><dd>MEXC · Spot · {detail.identity.native_symbol}</dd><dt>Timestamp source ticker</dt><dd>{utc(detail.ticker.source_close_ms)}</dd><dt>Réception ticker</dt><dd>{utc(detail.ticker.received_ms)}</dd><dt>Qualification à la lecture</dt><dd>{detail.freshness.age_ms===null?"Inconnu":detail.freshness.age_ms+" ms"} · {detail.freshness.reason}</dd><dt>Identité complète</dt><dd>{detail.instrument_id}</dd><dt>Empreinte du ticker brut</dt><dd>{detail.ticker.raw_sha256}</dd></dl><p>Les bougies closes sont confirmées après la borne + 2 s et une nouvelle lecture. Une donnée affichée ne constitue pas un signal de trading.</p></details>
    <p>Aucun ADX, RSI, régime, score ou signal n’est calculé.</p></div>
   </div></div>}
  </>}
 </section>;
};
