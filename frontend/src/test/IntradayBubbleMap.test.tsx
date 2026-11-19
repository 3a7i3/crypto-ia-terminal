import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import fixture from "./fixtures/intradayS1.json";
import { IntradayBubbleMap,latestRows } from "../views/IntradayBubbleMap";
import { fetchIntraday,IntradayError,type IntradayRow } from "../lib/intradayClient";
vi.mock("../lib/intradayClient",async(importOriginal)=>{
 const original=await importOriginal<typeof import("../lib/intradayClient")>();
 return {...original,fetchIntraday:vi.fn()};
});
const fetcher=vi.mocked(fetchIntraday);
beforeEach(()=>{fetcher.mockImplementation(async(kind)=>structuredClone(fixture[kind]) as Awaited<ReturnType<typeof fetchIntraday>>);});
afterEach(()=>{vi.clearAllMocks();});
describe("IntradayBubbleMap",()=>{
 it("shows loading, actual identities and explicit synthetic provenance",async()=>{
  render(<IntradayBubbleMap/>);expect(screen.getByRole("status")).toHaveTextContent("Chargement");
  await screen.findByRole("button",{name:/DOGE\/USDT · mexc · spot/});
  expect(screen.getAllByText(/SYNTHETIC/).length).toBeGreaterThan(0);
  expect(screen.getByText("Fraîcheur synthétique")).toBeInTheDocument();
  expect(screen.queryByText(/^LIVE$/)).not.toBeInTheDocument();
  expect(fetcher.mock.calls.filter(c=>c[0]==="scanner")).toHaveLength(1);
 });
 it("opens with a keyboard-activatable button and closes Escape with focus restoration",async()=>{
  render(<IntradayBubbleMap/>);const trigger=await screen.findByRole("button",{name:/DOGE\/USDT · mexc · spot/});
  trigger.focus();fireEvent.click(trigger);
  expect(screen.getByRole("dialog")).toHaveTextContent("LOCAL_CYCLE_START");
  const close=screen.getByRole("button",{name:"Fermer le détail Intraday"});expect(close).toHaveFocus();
  fireEvent.keyDown(close,{key:"Tab"});expect(close).toHaveFocus();
  fireEvent.keyDown(close,{key:"Escape"});expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(trigger).toHaveFocus();
 });
 it("supports an accessible list and resets pagination for combined filters",async()=>{
  render(<IntradayBubbleMap/>);await screen.findByRole("button",{name:/DOGE\/USDT · mexc · spot/});
  fireEvent.click(screen.getByRole("button",{name:"≡ Liste"}));expect(screen.getByLabelText("Liste accessible des instruments")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Rechercher un symbole Intraday"),{target:{value:"ATOM"}});
  fireEvent.change(screen.getByLabelText("Marché Intraday"),{target:{value:"swap"}});
  await waitFor(()=>expect(fetcher).toHaveBeenCalledWith("scanner",expect.objectContaining({query:"ATOM",market:"swap",cursor:undefined}),expect.any(AbortSignal)));
 });
 it("displays API failure and clears old data while reloading",async()=>{
  fetcher.mockRejectedValue(new IntradayError("INTRADAY_NOT_CONFIGURED",503));
  render(<IntradayBubbleMap/>);expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 503");expect(screen.queryByRole("button",{name:/DOGE\/USDT · mexc · spot/})).not.toBeInTheDocument();
 });
 it("displays an honest empty population and unavailable values",async()=>{
  fetcher.mockImplementation(async(kind)=>kind==="scanner"?{...fixture.scanner,rows:[],returned_count:0,matched_observations:0} as Awaited<ReturnType<typeof fetchIntraday>>:structuredClone(fixture[kind]) as Awaited<ReturnType<typeof fetchIntraday>>);
  render(<IntradayBubbleMap/>);expect(await screen.findByText("Aucune observation pour ces filtres.")).toBeInTheDocument();
 });
 it("fails closed when a source is historical instead of synthetic",async()=>{
  fetcher.mockImplementation(async(kind)=>({...fixture[kind],evidence_kind:"HISTORICAL"}) as Awaited<ReturnType<typeof fetchIntraday>>);
  render(<IntradayBubbleMap/>);expect(await screen.findByRole("alert")).toHaveTextContent("SYNTHETIC_REQUIRED");
 });
 it("binds next page to the snapshot and returns to first page",async()=>{
  fetcher.mockImplementation(async(kind,query)=>kind!=="scanner"?structuredClone(fixture[kind]) as Awaited<ReturnType<typeof fetchIntraday>>:query?.cursor?{...fixture.scanner,rows:[fixture.scanner.rows[1]],returned_count:1} as Awaited<ReturnType<typeof fetchIntraday>>:{...fixture.scanner,rows:[fixture.scanner.rows[0]],returned_count:1,next_cursor:"abc",complete:false} as Awaited<ReturnType<typeof fetchIntraday>>);
  render(<IntradayBubbleMap/>);await screen.findByRole("button",{name:/DOGE\/USDT · mexc · spot/});
  fireEvent.click(screen.getByRole("button",{name:"Page suivante"}));
  await waitFor(()=>expect(fetcher).toHaveBeenCalledWith("scanner",expect.objectContaining({cursor:"abc",snapshot_id:fixture.scanner.snapshot_id}),expect.any(AbortSignal)));
  await screen.findByRole("button",{name:/ATOM\/USDT · mexc · swap/});
  fireEvent.click(screen.getByRole("button",{name:"Première page"}));
  await screen.findByRole("button",{name:/DOGE\/USDT · mexc · spot/});
 });
 it("chooses latest observation within the page without merging spot and swap",()=>{
  const row=fixture.scanner.rows[0] as IntradayRow;
  const later={...row,capture_epoch_s:"999"};
  expect(latestRows([row,later])).toHaveLength(1);expect(latestRows([row,later])[0].capture_epoch_s).toBe("999");
  const other={...row,instrument_id:"f".repeat(64),identity:{...row.identity,market:"swap" as const}};
  expect(latestRows([row,other])).toHaveLength(2);
 });
});
