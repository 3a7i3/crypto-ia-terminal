import React from "react";
import type { Bar, Timeframe } from "../lib/spotRadarClient";
const stamp=(b:Bar)=>new Date(Number(b.open_ms)).toISOString().slice(5,16).replace("T"," ");
/** Optional overrides let a historical, volume-less series (sampled book mids) reuse the chart without
 *  claiming MEXC OHLCV provenance or volumes. Defaults keep the operational Radar rendering unchanged. */
export interface RadarCandlesOptions{volume?:boolean;title?:string;caption?:string;note?:string;label?:string}
export const RadarCandles: React.FC<{rows:Bar[];symbol:string;timeframe:Timeframe|string}&RadarCandlesOptions>=({rows,symbol,timeframe,volume=true,title,caption,note,label})=>{
 const bars=rows.slice(-60);
 if(!bars.length)return <p>Pas de bougies disponibles.</p>;
 const W=720,H=460,left=12,right=124,top=28,bottom=volume?320:390;
 const low=Math.min(...bars.map(b=>Number(b.low))),high=Math.max(...bars.map(b=>Number(b.high)));
 const pad=Math.max((high-low)*.06,Math.abs(high)*.00001,Number.MIN_VALUE),min=low-pad,max=high+pad,span=max-min;
 if(!Number.isFinite(span)||span<=0)return <p>Échelle du graphique indisponible ; valeurs exactes dans le tableau.</p>;
 const y=(v:string)=>bottom-(Number(v)-min)/span*(bottom-top),width=(W-left-right)/bars.length,body=Math.max(1,width*.65);
 const maxV=Math.max(...bars.map(b=>Number(b.base_volume)),1e-100);
 const precision=high>=100?2:high>=1?4:8;
 const price=(v:number)=>v.toLocaleString("fr-FR",{maximumFractionDigits:precision});
 return <figure className="radar-chart"><figcaption><strong>{symbol}</strong><span>{caption??`${timeframe} · ${bars.length} bougies · USDT`}</span></figcaption>
 <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label??`Graphique en chandeliers ${symbol} ${timeframe}, ${bars.length} bougies ; volumes base sous les prix`}>
 <title>{title??`${symbol} ${timeframe} — OHLCV MEXC public ; dernière bougie éventuellement partielle`}</title>
 {[0,.25,.5,.75,1].map(f=>{const yy=top+f*(bottom-top);return <g key={f}><line x1={left} y1={yy} x2={W-right} y2={yy} stroke="#334155"/><text x={W-right+8} y={yy+7} fill="#cbd5e1" fontSize="21">{price(max-f*span)}</text></g>;})}
 {bars.map((b,i)=>{const x=left+(i+.5)*width,o=y(b.open),c=y(b.close),color=Number(b.close)>=Number(b.open)?"#63dbb0":"#fb9292";return <g key={b.open_ms}><title>{stamp(b)} UTC · O {b.open} · H {b.high} · L {b.low} · C {b.close}{volume?` · Volume ${b.base_volume}`:""} · {b.closed?"clôturée":"partielle"}</title><line x1={x} x2={x} y1={y(b.high)} y2={y(b.low)} stroke={color} strokeWidth="1.5"/><rect x={x-body/2} y={Math.min(o,c)} width={body} height={Math.max(1.5,Math.abs(o-c))} fill={b.closed?color:"#152239"} stroke={color}/>{volume&&<rect x={x-body/2} y={394-Number(b.base_volume)/maxV*48} width={body} height={Math.max(.5,Number(b.base_volume)/maxV*48)} fill={color} opacity=".65"/>}</g>;})}
 <text x={left} y="430" fill="#cbd5e1" fontSize="21">{stamp(bars[0])} UTC</text><text x={W-right} y="430" fill="#cbd5e1" fontSize="21" textAnchor="end">{stamp(bars[bars.length-1])} UTC</text>
 </svg><p>{note??"Volumes en unité de base · contour vide : bougie partielle · valeurs exactes dans le tableau."}</p></figure>;
};
