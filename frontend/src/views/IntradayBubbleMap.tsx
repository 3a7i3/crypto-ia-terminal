import React, { useEffect, useRef, useState } from "react";
import { decimalCompare, fetchIntraday, IntradayError, type IntradayRow, type Market, type Overview, type ScannerPage } from "../lib/intradayClient";
import "../intraday.css";

type State = { status:"loading" } | { status:"error"; code:string; http:number|null } |
  { status:"ready"; page:ScannerPage; overview:Overview; health:Overview };
export function latestRows(rows: IntradayRow[]): IntradayRow[] {
  const byId=new Map<string,IntradayRow>();
  for(const r of rows) { const prev=byId.get(r.instrument_id); if(!prev || decimalCompare(r.capture_epoch_s,prev.capture_epoch_s)>0) byId.set(r.instrument_id,r); }
  return [...byId.values()].sort((a,b)=>a.instrument_id.localeCompare(b.instrument_id));
}
const stateLabel = (r:IntradayRow,k:"chg"|"last"|"qv"|"sp") => {
  const state=r.field_states[k];
  if(state==="ABSENT") return "Absente";
  if(state==="NULL") return "Valeur null";
  if(state==="LEGACY_ZERO_AMBIGUOUS") return "Zéro legacy ambigu";
  return r.values[k] ?? "Non disponible";
};
export const IntradayBubbleMap:React.FC=()=>{
  const [query,setQuery]=useState(""),[market,setMarket]=useState<Market|undefined>(),[list,setList]=useState(false);
  const [position,setPosition]=useState<{cursor?:string;snapshot_id?:string;number:number}>({number:1});
  const [state,setState]=useState<State>({status:"loading"}),[refresh,setRefresh]=useState(0);
  const [selected,setSelected]=useState<string|null>(null);
  const origin=useRef<HTMLButtonElement|null>(null),closeButton=useRef<HTMLButtonElement|null>(null);
  const panel=useRef<HTMLDivElement|null>(null);
  const close=()=>{setSelected(null);origin.current?.focus();};
  useEffect(()=>{
    const abort=new AbortController(); setState({status:"loading"});setSelected(null);
    const timer=setTimeout(()=>{
      const q={query,market,cursor:position.cursor,snapshot_id:position.snapshot_id,limit:100};
      fetchIntraday("scanner",q,abort.signal).then(async p=>{
        const page=p as ScannerPage;
        const [o,h]=await Promise.all([fetchIntraday("overview",{snapshot_id:page.snapshot_id},abort.signal),fetchIntraday("health",{snapshot_id:page.snapshot_id},abort.signal)]);
        if(abort.signal.aborted)return;
        if(o.evidence_kind!==page.evidence_kind || h.evidence_kind!==page.evidence_kind || (o as Overview).counts.admitted!==page.total_observations) throw new IntradayError("INCONSISTENT_SNAPSHOT");
        if(page.evidence_kind!=="SYNTHETIC") throw new IntradayError("SYNTHETIC_REQUIRED");
        setState({status:"ready",page,overview:o as Overview,health:h as Overview});
      }).catch(e=>{if(!abort.signal.aborted) setState({status:"error",code:e instanceof IntradayError?e.code:"TRANSPORT_ERROR",http:e instanceof IntradayError?e.status:null});});
    },200);
    return ()=>{clearTimeout(timer);abort.abort();};
  },[query,market,position,refresh]);
  useEffect(()=>{if(selected)closeButton.current?.focus();},[selected]);
  const rows=state.status==="ready"?latestRows(state.page.rows):[];
  const detail=rows.find(r=>r.instrument_id===selected);
  const updateFilter=(q:string,m:Market|undefined)=>{setQuery(q);setMarket(m);setPosition({number:1});};
  const fixture=typeof window!=="undefined" && new URLSearchParams(window.location.search).get("intraday_fixture")==="24";
  return <section className="intraday-desk" aria-label="Bulles Intraday">
    <header className="intraday-heading">
      <div><p className="intraday-eyebrow">CAT / MARKET INTELLIGENCE</p><h2>Intraday Bubble Map</h2><p className="intraday-lead">Explorer les instruments, vérifier les observations.</p></div>
      <span className="intraday-proof">◆ SYNTHETIC <small>{fixture?"Fixture isolée · 24 instruments":"Préproduction · données fictives"}</small></span>
    </header>
    <p className="intraday-disclaimer">Observation uniquement · bulles de taille égale · aucune priorité de trading.</p>
    <div className="intraday-controls">
      <label>Rechercher un symbole<input aria-label="Rechercher un symbole Intraday" type="search" value={query} maxLength={120} placeholder="BTC, DOGE, ATOM…" onChange={e=>updateFilter(e.target.value,market)}/></label>
      <label>Marché<select aria-label="Marché Intraday" value={market??""} onChange={e=>updateFilter(query,e.target.value as Market||undefined)}><option value="">Spot et Swap</option><option value="spot">Spot</option><option value="swap">Swap</option></select></label>
      <div className="intraday-switch" role="group" aria-label="Affichage Intraday"><button type="button" aria-pressed={!list} onClick={()=>setList(false)}>◉ Bulles</button><button type="button" aria-pressed={list} onClick={()=>setList(true)}>≡ Liste</button></div>
      <button type="button" className="intraday-refresh" onClick={()=>{setPosition({number:1});setRefresh(n=>n+1);}}>Actualiser</button>
    </div>
    {state.status==="loading" && <div role="status" className="intraday-loading"><span className="intraday-skeleton"/><span>Chargement des observations Intraday…</span></div>}
    {state.status==="error" && <div role="alert" className="intraday-error"><h3>Observations indisponibles</h3><p>{state.http ? "HTTP "+state.http+" · " : ""}{state.code}</p><p>La source n’est pas présentée comme actuelle. Actualiser reprend la publication courante.</p></div>}
    {state.status==="ready" && <>
      <div className="intraday-metrics" aria-label="Couverture de publication">
        <div><strong>{state.page.distinct_instruments}</strong><span>Instruments publiés</span></div>
        <div><strong>{state.page.total_observations}</strong><span>Observations admises</span></div>
        <div><strong>{rows.length}</strong><span>Instruments sur cette page</span></div>
        <div><strong>Non évaluée</strong><span>Fraîcheur synthétique</span></div>
      </div>
      <div className="intraday-map-head"><h3>{list?"Liste des instruments":"Carte des instruments"}</h3><span>Page {position.number} · {state.page.returned_count} / {state.page.matched_observations} observations filtrées</span></div>
      <p className="intraday-coverage">Dernière observation par identité dans la page chargée. {state.page.complete&&position.number===1?"Toutes les observations filtrées sont sur cette page.":"Couverture partielle : cette page ne représente pas tout l’univers filtré."}</p>
      {rows.length===0?<div role="status" className="intraday-empty">Aucune observation pour ces filtres.</div>:
      <div className={list?"intraday-list":"intraday-bubbles"} aria-label={list?"Liste accessible des instruments":"Carte de bulles déterministe"}>
        {rows.map((r,i)=>{
          const change=r.field_states.chg==="VALUE"?r.values.chg:null;
          const sign=change===null?0:decimalCompare(change,"0");
          const direction=change===null?"Variation non qualifiée":sign>0?"Variation positive":sign<0?"Variation négative":"Variation nulle";
          return <button key={r.instrument_id} type="button" className={"intraday-bubble "+(sign>0?"intraday-up":sign<0?"intraday-down":"intraday-neutral")} style={{"--bubble-index":i} as React.CSSProperties}
            aria-label={r.identity.native_symbol+" · "+r.identity.venue+" · "+r.identity.market+" · "+direction}
            onClick={e=>{origin.current=e.currentTarget;setSelected(r.instrument_id);}}>
            <span className="intraday-bubble-market">{r.identity.venue.toUpperCase()} / {r.identity.market==="spot"?"SPOT":"SWAP"}</span>
            <strong>{r.identity.native_symbol}</strong>
            <span className="intraday-bubble-price">{r.values.last}</span>
            <span className="intraday-bubble-change">{change===null?"—":(sign>0?"+":"")+change} <small>{change===null?"Non qualifiée":"variation déclarée"}</small></span>
          </button>;
        })}
      </div>}
      <div className="intraday-legend"><span>↗ Variation positive</span><span>↘ Variation négative</span><span>○ Non qualifiée</span><span>Unité et horizon de variation non attestés.</span></div>
      <nav className="intraday-pagination" aria-label="Pages Intraday"><button type="button" disabled={position.number===1} onClick={()=>setPosition({number:1})}>Première page</button><span>Page {position.number}</span><button type="button" disabled={state.page.next_cursor===null} onClick={()=>setPosition({cursor:state.page.next_cursor??undefined,snapshot_id:state.page.snapshot_id,number:position.number+1})}>Page suivante</button></nav>
      <details className="intraday-provenance"><summary>Provenance et limites de la publication</summary>
        <dl><dt>Preuve</dt><dd>SYNTHETIC · {state.page.snapshot_id}</dd><dt>Version</dt><dd>{state.page.schema_version} · {state.page.provenance.qualification_version}</dd><dt>Publication UTC</dt><dd>{state.page.provenance.published_at_utc??"Non disponible sur cette génération historique"}</dd><dt>Horodatage local as_of</dt><dd>{state.page.provenance.as_of_epoch_s} secondes Unix</dd><dt>Couverture</dt><dd>{state.page.provenance.coverage}</dd><dt>Fraîcheur source</dt><dd>UNRESOLVED · jamais attestée LIVE</dd><dt>Collecteur</dt><dd>{state.health.collector_status}</dd><dt>Validation API</dt><dd>{state.page.validation_scope}</dd></dl>
        <p>Le volume quote peut être natif ou estimé : origine legacy non résolue. Un timestamp de capture locale n’est pas un timestamp exchange. Les valeurs brutes sont préservées sous forme texte.</p>
      </details>
      {detail && <div className="intraday-modal-backdrop" onClick={e=>{if(e.target===e.currentTarget)close();}}>
        <div ref={panel} className="intraday-detail" role="dialog" aria-modal="true" aria-labelledby="intraday-detail-title" onKeyDown={e=>{
          if(e.key==="Escape"){e.preventDefault();close();}
          if(e.key==="Tab"){const nodes=panel.current?.querySelectorAll<HTMLElement>("button,[href],input,select,summary");if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
        }}>
          <button ref={closeButton} type="button" className="intraday-close" aria-label="Fermer le détail Intraday" onClick={close}>Fermer ×</button>
          <p className="intraday-eyebrow">FICHE INSTRUMENT · SYNTHETIC</p><h3 id="intraday-detail-title">{detail.identity.native_symbol}</h3>
          <p>{detail.identity.venue.toUpperCase()} · {detail.identity.market==="spot"?"Spot":"Swap"} · contrat non résolu</p>
          <div className="intraday-detail-price">{detail.values.last}<small>Dernier prix déclaré · unité quote</small></div>
          <dl><dt>Variation déclarée</dt><dd>{stateLabel(detail,"chg")} · unité/horizon non attestés</dd><dt>Volume quote</dt><dd>{stateLabel(detail,"qv")} · natif ou estimé, non résolu</dd><dt>Spread déclaré</dt><dd>{stateLabel(detail,"sp")}</dd><dt>Bid / Ask</dt><dd>{detail.values.bid??"Absent"} / {detail.values.ask??"Absent"}</dd><dt>Capture locale</dt><dd>{detail.capture_epoch_s} secondes Unix · LOCAL_CYCLE_START</dd><dt>Timestamp exchange</dt><dd>Non disponible</dd><dt>Identité</dt><dd>{detail.instrument_id}</dd><dt>Origine venue</dt><dd>{detail.exchange_origin}</dd></dl>
          <p>Aucun indicateur technique ni score n’est calculé dans cette fiche.</p>
        </div>
      </div>}
    </>}
  </section>;
};
