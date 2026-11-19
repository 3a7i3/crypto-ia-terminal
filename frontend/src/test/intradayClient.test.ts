import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import { webcrypto } from "node:crypto";
import fixture from "./fixtures/intradayS1.json";
import { decimalCompare,fetchIntraday,parseIntradayJson,validateIntraday,MAX_BYTES,TIMEOUT_MS } from "../lib/intradayClient";
const copy=()=>structuredClone(fixture);
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{"content-type":"application/json"}});
beforeEach(()=>{vi.stubGlobal("crypto",webcrypto);});
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});
describe("Intraday client 0.2",()=>{
 it("validates the real three-instrument synthetic contract without decimal conversion",async()=>{
  const f=vi.fn().mockResolvedValue(response(fixture.scanner));vi.stubGlobal("fetch",f);
  const p=await fetchIntraday("scanner");expect(p.evidence_kind).toBe("SYNTHETIC");
  expect("rows" in p&&p.rows[0].values.last).toBe("10");expect(f.mock.calls[0][0]).toBe("/api/operator/v1/intraday/scanner");
 });
 it("accepts overview and health with unresolved synthetic freshness",()=>{
  expect(validateIntraday(fixture.overview,"overview").serving.freshness).toBe("NOT_ASSESSED_SYNTHETIC");
  expect(validateIntraday(fixture.health,"health").evidence_kind).toBe("SYNTHETIC");
 });
 it.each([422,409,503])("keeps structured HTTP %s distinct",async(status)=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response({error_code:"INTRADAY_TEST_ERROR"},status)));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({status,code:"INTRADAY_TEST_ERROR"});
 });
 it("handles FastAPI parameter validation errors",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response({detail:[{msg:"invalid"}]},422)));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({status:422,code:"HTTP_422"});
 });
 it("refuses JSON with duplicate keys, invalid content, BOM or unsafe numbers",()=>{
  for(const raw of ['{"a":1,"a":2}','{"a":NaN}','[]garbage','\ufeff{}','{"n":9007199254740993}']){
   expect(()=>parseIntradayJson(raw)).toThrow();
  }
  expect(parseIntradayJson('{"serving":{"observation_age_s":0.25}}')).toEqual({serving:{observation_age_s:0.25}});
  expect(()=>parseIntradayJson('{"returned_count":1e0}')).toThrow();
 });
 it("refuses malformed UTF-8 and invalid JSON over transport",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(new Uint8Array([255]))));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({code:"INVALID_JSON"});
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("<html>error")));
  await expect(fetchIntraday("scanner")).rejects.toBeInstanceOf(Error);
 });
 it("enforces both declared and streamed byte bounds",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("{}",{headers:{"content-length":String(MAX_BYTES+1)}})));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({code:"RESPONSE_LIMIT"});
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(" ".repeat(MAX_BYTES+1))));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({code:"RESPONSE_LIMIT"});
 });
 it("checks closed fields, counts, unknown provenance and live mislabelling",()=>{
  const unknown=copy();Object.assign(unknown.scanner,{secret:"bad"});
  expect(()=>validateIntraday(unknown.scanner,"scanner")).toThrow();
  const count=copy();count.scanner.returned_count=99;expect(()=>validateIntraday(count.scanner,"scanner")).toThrow();
  const live=copy();live.scanner.serving.freshness="LIVE";expect(()=>validateIntraday(live.scanner,"scanner")).toThrow();
  const field=copy();field.scanner.rows[0].values.last=null as unknown as string;expect(()=>validateIntraday(field.scanner,"scanner")).toThrow();
 });
 it("preserves absent, null and ambiguous zero states",()=>{
  const x=copy();x.scanner.rows[0].values.chg=null as unknown as string;x.scanner.rows[0].field_states.chg="NULL";
  expect(()=>validateIntraday(x.scanner,"scanner")).not.toThrow();
  x.scanner.rows[0].field_states.chg="VALUE";expect(()=>validateIntraday(x.scanner,"scanner")).toThrow();
 });
 it("verifies identity hash including Spot/Swap and snapshot binding",async()=>{
  const x=copy();x.scanner.rows[0].identity.market="swap";
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(x.scanner)));
  await expect(fetchIntraday("scanner")).rejects.toMatchObject({code:"INVALID_CONTRACT"});
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(fixture.scanner)));
  await expect(fetchIntraday("scanner",{snapshot_id:"0".repeat(64)})).rejects.toMatchObject({code:"INVALID_CONTRACT"});
 });
 it("retains snapshot and cursor when paging and verifies server market filter",async()=>{
  const page1={...fixture.scanner,rows:[fixture.scanner.rows[0]],returned_count:1,complete:false,next_cursor:"abc"};
  const page2={...fixture.scanner,rows:[fixture.scanner.rows[1]],returned_count:1};
  const f=vi.fn().mockResolvedValueOnce(response(page1)).mockResolvedValueOnce(response(page2));vi.stubGlobal("fetch",f);
  await fetchIntraday("scanner",{limit:1});await fetchIntraday("scanner",{limit:1,cursor:"abc",snapshot_id:fixture.scanner.snapshot_id});
  expect(f.mock.calls[1][0]).toContain("cursor=abc");expect(f.mock.calls[1][0]).toContain("snapshot_id="+fixture.scanner.snapshot_id);
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(fixture.scanner)));
  await expect(fetchIntraday("scanner",{market:"spot"})).rejects.toMatchObject({code:"INVALID_CONTRACT"});
 });
 it("compares extreme decimal text exactly",()=>{
  expect(decimalCompare("99999999999999999999.00000000000000000001","99999999999999999999")).toBe(1);
  expect(decimalCompare("-0.001","0")).toBe(-1);expect(decimalCompare("-1.23","-1.2300")).toBe(0);
 });
 it("bounds timeout and propagates caller cancellation",async()=>{
  vi.useFakeTimers();
  vi.stubGlobal("fetch",vi.fn((_u,init:RequestInit)=>new Promise((_resolve,reject)=>init.signal?.addEventListener("abort",()=>reject(new Error("aborted"))))));
  const p=fetchIntraday("scanner");const assertion=expect(p).rejects.toMatchObject({code:"TIMEOUT"});
  await vi.advanceTimersByTimeAsync(TIMEOUT_MS+1);await assertion;
  const c=new AbortController();const q=fetchIntraday("scanner",{},c.signal);const cancelled=expect(q).rejects.toMatchObject({code:"ABORTED"});c.abort();await cancelled;
 });
});
