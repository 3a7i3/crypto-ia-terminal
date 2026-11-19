import {beforeEach,afterEach,describe,it,expect,vi} from "vitest";
import {webcrypto} from "node:crypto";
import {fetchRadar,validateRadar,RadarError} from "../lib/spotRadarClient";
import scanner from "./fixtures/spotRadar-scanner.json";
import overview from "./fixtures/spotRadar-overview.json";
import history from "./fixtures/spotRadar-ohlcv.json";
const copy=()=>structuredClone(scanner);
beforeEach(()=>{vi.stubGlobal("crypto",webcrypto);});
afterEach(()=>vi.unstubAllGlobals());
describe("Spot Radar closed public contract",()=>{
 it("preserves scientific decimal strings and complete identities",()=>{const d=validateRadar(scanner,"scanner");expect(d.schema_version).toBe("spot-radar/1.0.0");expect((d as typeof scanner).rows[0].ticker.last_price).toEqual(scanner.rows[0].ticker.last_price);});
 it("validates overview and closed OHLCV contract",()=>{expect(()=>validateRadar(overview,"overview")).not.toThrow();expect(()=>validateRadar(history,"ohlcv")).not.toThrow();});
 it.each(["unknown","decimal number","identity market","duplicate","synthetic LIVE","incomplete count","history mismatch"])("rejects %s",kind=>{
  const d=copy();if(kind==="unknown")Object.assign(d,{unknown:1});
  if(kind==="decimal number")Object.assign(d.rows[0].ticker,{last_price:3.14});
  if(kind==="identity market")Object.assign(d.rows[0].identity,{market:"swap"});
  if(kind==="duplicate")d.rows[1]=d.rows[0];
  if(kind==="synthetic LIVE")d.evidence_kind="SYNTHETIC";
  if(kind==="incomplete count")d.observed_instruments=1;
  if(kind==="history mismatch")d.rows[0].timeframes[0].symbol="WRONGUSDT";
  expect(()=>validateRadar(d,"scanner")).toThrow(RadarError);
 });
 it("checks cryptographic instrument identity on GET",async()=>{const d=copy();d.rows[0].instrument_id="a".repeat(64);vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify(d))));await expect(fetchRadar("scanner")).rejects.toMatchObject({code:"INVALID_RADAR_CONTRACT"});});
 it.each([422,409,503])("preserves typed HTTP %i",async status=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response('{"error_code":"RADAR_UNAVAILABLE"}',{status})));await expect(fetchRadar("scanner")).rejects.toMatchObject({status,code:"RADAR_UNAVAILABLE"});});
 it("rejects invalid JSON, duplicate keys and oversized responses",async()=>{
  for(const raw of ["bad",'{ "a":1,"a":2}']){vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(raw)));await expect(fetchRadar("scanner")).rejects.toMatchObject({code:"INVALID_JSON"});}
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(" ".repeat(1_000_001))));await expect(fetchRadar("scanner")).rejects.toMatchObject({code:"RESPONSE_LIMIT"});
 });
 it("GETs only the separate same-origin radar",async()=>{const f=vi.fn().mockResolvedValue(new Response(JSON.stringify(scanner)));vi.stubGlobal("fetch",f);await fetchRadar("scanner");expect(f.mock.calls[0][0]).toBe("/api/operator/v1/spot-radar/scanner");expect(f.mock.calls[0][1].method).toBe("GET");});
 it("history response must match requested instrument and timeframe",async()=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify(history))));await expect(fetchRadar("ohlcv",{symbol:"DOGEUSDT",timeframe:"M5"})).rejects.toMatchObject({code:"INVALID_RADAR_CONTRACT"});});
});
