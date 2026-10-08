import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  FinancialHistory,
  AccountingPlot,
} from "../components/FinancialHistory";
import { validAccountingHistory } from "../lib/pplAccountingHistory";
import type { AccountingSample } from "../lib/pplAccountingHistory";
import synthetic from "./fixtures/pplAccountingHistory.synthetic.json";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const fetchHistory = (doc: unknown, status = 200) =>
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(doc), { status })),
  );
describe("PPL accounting charts", () => {
  it("renders published history, stale provenance and allocation without FIN availability", async () => {
    fetchHistory(synthetic);
    render(<FinancialHistory />);
    expect(
      await screen.findByRole("img", {
        name: "Résultat réalisé cumulé aux événements PPL",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Capture périmée/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Capital disponible" }));
    expect(
      screen.getByRole("img", {
        name: "Capital disponible aux événements PPL",
      }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Répartition" }));
    expect(
      screen.getByRole("img", { name: "Répartition du principal comptable" }),
    ).toBeInTheDocument();
    expect(screen.getByText("100 %")).toBeInTheDocument();
  });
  it("does not turn an unavailable source into a zero-valued graph", async () => {
    fetchHistory({ error_code: "HISTORY_NOT_AVAILABLE" }, 503);
    render(<FinancialHistory />);
    await screen.findByText(/HTTP 503/);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("rejects a sequence gap, forged share, nonfinite amount and epochless history", () => {
    for (const mutate of [
      (x: typeof synthetic) => (x.samples[1].sequence = 9),
      (x: typeof synthetic) => (x.allocation.segments[0].share = "0.5"),
      (x: typeof synthetic) => (x.samples[0].realized_pnl = "NaN"),
      (x: typeof synthetic) => (x.paper_epoch_id = ""),
    ]) {
      const d = structuredClone(synthetic);
      mutate(d);
      expect(validAccountingHistory(d)).toBe(false);
    }
    expect(validAccountingHistory(synthetic)).toBe(true);
  });
  it("shows one point instead of inventing a line from one observation", () => {
    const { container } = render(
      <AccountingPlot
        samples={[synthetic.samples[0] as AccountingSample]}
        metric="realized_pnl"
      />,
    );
    expect(container.querySelector("path")).toBeNull();
    expect(container.querySelector("circle")).not.toBeNull();
  });
  it("rejects invalid payload even on HTTP 200", async () => {
    fetchHistory({ samples: [] });
    render(<FinancialHistory />);
    await waitFor(() =>
      expect(screen.getByText(/contrat invalide/)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
