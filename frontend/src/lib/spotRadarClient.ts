/** S2 public Spot observation. Independent of Intraday 0.2. No producer import. */
import contracts from "./spotRadarSchemas.json";
import {parseIntradayJson, decimalCompare} from "./intradayClient";
export const RADAR_BASE="/api/operator/v1/spot-radar/";
export const RADAR_MAX_BYTES=1_000_000;
export type Freshness="LIVE"|"STALE"|"DISCONNECTED"|"UNRESOLVED"|"SYNTHETIC";
export type Timeframe="M5"|"M15"|"H1"|"H4";
export interface HistoryRef {symbol:string;timeframe:Timeframe;sha256:string;history_count:number;closed_count:number;quality:"COMPLETE"|"PARTIAL";received_ms:string;gap_count:number;rejected:number;duplicates:number;conflicts:number}
export interface RadarRow {
 instrument_id:string;identity:{exchange:"mexc";market:"spot";native_symbol:string};base_asset:string;quote_asset:"USDT";display_symbol:string;data_issue:string|null;
 ticker:{last_price:string;open_price:string;high_price:string;low_price:string;base_volume_24h:string;quote_volume_24h:string;price_change_raw:string;price_change_ratio_raw:string;change_pct_24h:string|null;change_method:string;change_qualified:boolean;volume_qualified:boolean;source_open_ms:string|null;source_close_ms:string|null;received_ms:string;raw_sha256:string};
 book:{bid:string|null;ask:string|null;bid_qty:string|null;ask_qty:string|null;source_ms:null;received_ms:string|null;raw_sha256:string|null;quality:string};
 freshness:{state:Freshness;age_ms:number|null;reason:string};timeframes:HistoryRef[];
}
export interface RadarBase {
 schema_version:"spot-radar/1.0.0";snapshot_id:string;evidence_kind:"PUBLIC_OBSERVED"|"SYNTHETIC";server_time_ms:string;
 source:{exchange:"mexc";market:"spot";transport:"PUBLIC_REST";base_url:"https://api.mexc.com";selection_sha256:string;metadata_sha256:string};
 clock:{server_ms:string;requested_ms:string;received_ms:string;rtt_ms:number};
 collector:{state:"RUNNING"|"DISCONNECTED"|"STOPPED";reason:string;last_success_ms:string|null;last_attempt_ms:string;expires_ms:string;cycles:number;failures:number;request_count:number;fault_injection:boolean;pilot_id:string};
 selected_instruments:number;observed_instruments:number;unavailable:{symbol:string;reason:string}[];
}
export interface RadarScanner extends RadarBase {rows:RadarRow[];returned_count:number;complete:true}
export interface RadarOverview extends RadarBase {states:Record<Freshness,number>;histories_available:number;histories_expected:number}
export interface Bar {open_ms:string;source_close_ms:string;close_boundary_ms:string;open:string;high:string;low:string;close:string;base_volume:string;quote_volume:string;closed:boolean;raw_sha256:string;received_ms:string}
export interface RadarHistory extends RadarBase {history_sha256:string;history:{schema_version:string;identity:RadarRow["identity"];timeframe:Timeframe;rows:Bar[];history_count:number;source_count:number;requested_initial:300;interval_ms:number;received_ms:string;server_ms:string;raw_sha256:string;gaps:{after_ms:string;before_ms:string;missing_bars:number}[];rejected:number;duplicates:number;conflicts:string[];quality:string;closure_observed:string[]}}
export class RadarError extends Error {constructor(public code:string,public status:number|null=null){super(code);this.name="RadarError";}}
type Schema={type?:string;const?:unknown;enum?:unknown[];anyOf?:Schema[];properties?:Record<string,Schema>;required?:string[];additionalProperties?:boolean;items?:Schema;maxItems?:number;minimum?:number;maximum?:number;maxLength?:number;pattern?:string};
const fail=():never=>{throw new RadarError("INVALID_RADAR_CONTRACT");};
/** Supported closed JSON-Schema subset, generated directly from Python definitions. */
export function matches(v:unknown,s:Schema):boolean {
 if(s.anyOf)return s.anyOf.some(x=>matches(v,x));
 if(Object.hasOwn(s,"const")&&v!==s.const)return false;
 if(s.enum&&!s.enum.includes(v))return false;
 if(s.type==="null")return v===null;
 if(s.type==="boolean")return typeof v==="boolean";
 if(s.type==="integer")return typeof v==="number"&&Number.isSafeInteger(v)&&v>=(s.minimum??0)&&v<=(s.maximum??Number.MAX_SAFE_INTEGER);
 if(s.type==="string")return typeof v==="string"&&v.length<=(s.maxLength??1000)&&(!s.pattern||new RegExp(s.pattern).test(v));
 if(s.type==="array")return Array.isArray(v)&&v.length<=(s.maxItems??0)&&v.every(x=>matches(x,s.items!));
 if(s.type==="object"){
  if(!v||typeof v!=="object"||Array.isArray(v))return false;
  const o=v as Record<string,unknown>,p=s.properties??{};
  return s.additionalProperties===false&&(s.required??[]).every(k=>Object.hasOwn(o,k))&&Object.keys(o).every(k=>Object.hasOwn(p,k)&&matches(o[k],p[k]));
 }
 return Object.hasOwn(s,"const")||Boolean(s.enum);
}
export function validateRadar(v:unknown,kind:"scanner"|"overview"|"health"|"ohlcv"):RadarScanner|RadarOverview|RadarHistory {
 if(!matches(v,contracts[kind] as Schema))return fail();
 const data=v as RadarScanner|RadarOverview|RadarHistory;
 if(data.observed_instruments>data.selected_instruments||data.observed_instruments+data.unavailable.length!==data.selected_instruments)return fail();
 if(kind==="scanner"){
  const d=data as RadarScanner,seen=new Set<string>();
  if(d.rows.length!==d.returned_count||d.returned_count>d.observed_instruments)return fail();
  for(const r of d.rows){
   if(seen.has(r.instrument_id))return fail();seen.add(r.instrument_id);
   if((data.evidence_kind==="SYNTHETIC")!==(r.freshness.state==="SYNTHETIC"))return fail();
   if(r.freshness.state==="LIVE"&&data.collector.state!=="RUNNING")return fail();
   if(r.ticker.change_qualified!==(r.ticker.change_pct_24h!==null))return fail();
   if(decimalCompare(r.ticker.last_price,"0")<=0||decimalCompare(r.ticker.base_volume_24h,"0")<0||decimalCompare(r.ticker.quote_volume_24h,"0")<0)return fail();
   if(new Set(r.timeframes.map(x=>x.timeframe)).size!==r.timeframes.length||r.timeframes.some(x=>x.symbol!==r.identity.native_symbol||x.closed_count>x.history_count))return fail();
  }
 }else if(kind==="overview"||kind==="health"){
  const d=data as RadarOverview;
  if(Object.values(d.states).reduce((a,b)=>a+b,0)!==d.observed_instruments||d.histories_expected!==d.selected_instruments*4||d.histories_available>d.histories_expected)return fail();
 }else{
  const h=(data as RadarHistory).history;
  if(h.history_count!==h.rows.length||h.rows.some((b,i)=>i>0&&BigInt(b.open_ms)<=BigInt(h.rows[i-1].open_ms)))return fail();
 }
 return data;
}
export async function fetchRadar<K extends "scanner"|"overview"|"health"|"ohlcv">(kind:K,query:Record<string,string>={},signal?:AbortSignal):Promise<K extends "scanner"?RadarScanner:K extends "ohlcv"?RadarHistory:RadarOverview>{
 const controller=new AbortController(),abort=()=>controller.abort();let timed=false;
 signal?.addEventListener("abort",abort,{once:true});if(signal?.aborted)abort();
 const timer=setTimeout(()=>{timed=true;controller.abort();},10_000);
 try{
  const qs=new URLSearchParams(query);
  const response=await fetch(RADAR_BASE+kind+(qs.size?"?"+qs:""),{method:"GET",signal:controller.signal,cache:"no-store"});
  const length=response.headers.get("content-length");
  if(length!==null&&(!/^\d+$/.test(length)||Number(length)>RADAR_MAX_BYTES))throw new RadarError("RESPONSE_LIMIT");
  if(!response.body)throw new RadarError("INVALID_JSON");
  const reader=response.body.getReader(),chunks:Uint8Array[]=[];let size=0;
  try{while(true){const p=await reader.read();if(p.done)break;size+=p.value.byteLength;if(size>RADAR_MAX_BYTES){await reader.cancel();throw new RadarError("RESPONSE_LIMIT");}chunks.push(p.value);}}finally{reader.releaseLock();}
  const bytes=new Uint8Array(size);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}
  let value:unknown;try{value=parseIntradayJson(new TextDecoder("utf-8",{fatal:true}).decode(bytes));}catch{throw new RadarError("INVALID_JSON");}
  if(!response.ok){const o=value as Record<string,unknown>;throw new RadarError(o&&typeof o.error_code==="string"&&/^[A-Z0-9_]{1,100}$/.test(o.error_code)?o.error_code:"HTTP_"+response.status,response.status);}
  const d=validateRadar(value,kind);
  if(kind==="scanner")for(const r of (d as RadarScanner).rows){
   const raw=JSON.stringify({exchange:r.identity.exchange,market:r.identity.market,native_symbol:r.identity.native_symbol});
   const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(raw))),n=>n.toString(16).padStart(2,"0")).join("");
   if(hash!==r.instrument_id)return fail();
  }
  if(kind==="ohlcv"){const h=(d as RadarHistory).history;if(h.identity.native_symbol!==query.symbol||h.timeframe!==query.timeframe)return fail();}
  return d as K extends "scanner"?RadarScanner:K extends "ohlcv"?RadarHistory:RadarOverview;
 }catch(e){if(e instanceof RadarError)throw e;throw new RadarError(timed?"TIMEOUT":controller.signal.aborted?"ABORTED":"TRANSPORT_ERROR");}
 finally{clearTimeout(timer);signal?.removeEventListener("abort",abort);}
}
