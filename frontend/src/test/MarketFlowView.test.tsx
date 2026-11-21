import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MarketFlowView, wholeCellCovered } from "../views/MarketFlowView";
import { fetchMarketFlow } from "../lib/marketFlowClient";
import { parseDecimal } from "../lib/marketFlowExact";

vi.mock("../lib/marketFlowClient", () => ({ fetchMarketFlow: vi.fn() }));
const fetchFlow = vi.mocked(fetchMarketFlow);
afterEach(() => vi.resetAllMocks());

it("garde le composant Flux testable hors navigation Marché", async () => {
  fetchFlow.mockResolvedValue({ status: "api_error", httpStatus: 503, errorCode: "MARKET_FLOW_NOT_CONFIGURED" });
  const { unmount } = render(<MarketFlowView/>);
  const notice = await screen.findByTestId("market-source-not-configured");
  expect(notice).toHaveTextContent("Source Flux non configurée sur ce serveur · HTTP 503 · MARKET_FLOW_NOT_CONFIGURED");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(fetchFlow).toHaveBeenCalledTimes(1);
  unmount();
  expect(fetchFlow.mock.calls[0][0]?.signal?.aborted).toBe(true);
});

it("ignore une réponse tardive après rafraîchissement", async () => {
  let finish!: (result: Awaited<ReturnType<typeof fetchMarketFlow>>) => void;
  fetchFlow.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  fetchFlow.mockResolvedValueOnce({ status: "api_error", httpStatus: 404, errorCode: null });
  render(<MarketFlowView/>);
  fireEvent.click(screen.getByRole("button", { name: "Rafraîchir Flux" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 404");
  expect(fetchFlow.mock.calls[0][0]?.signal?.aborted).toBe(true);
  await act(async () => finish({ status: "transport_error", reason: "TIMEOUT", detail: null }));
  expect(screen.getByRole("alert")).toHaveTextContent("HTTP 404");
});

it("exige la couverture de toute la cellule avant de présenter une absence comme zéro", () => {
  const column = { status: "LIVE" as const, bucket: 0, sample_receipt_ns: "0", bid_cover_floor: "100.25", ask_cover_ceiling: "100.75", bids: [], asks: [] };
  const lo = parseDecimal("100")!;
  const hi = parseDecimal("101")!;
  expect(wholeCellCovered(column, "bids", lo, hi)).toBe(false);
  expect(wholeCellCovered(column, "asks", lo, hi)).toBe(false);
  expect(wholeCellCovered(column, "bids", parseDecimal("100.25")!, hi)).toBe(true);
  expect(wholeCellCovered(column, "asks", lo, parseDecimal("100.75")!)).toBe(true);
  expect(wholeCellCovered({ ...column, bid_cover_floor: null }, "bids", lo, hi)).toBe(true);
});
