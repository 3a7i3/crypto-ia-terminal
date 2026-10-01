import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BurnInStatusView } from "../views/BurnInStatusView";
import { burnInFixture } from "./burnInFixtures";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe("APP-UNIFY U2 BurnInStatusView", () => {
  it("renders progression, open deadlines and lifecycle history", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(burnInFixture()));
    vi.stubGlobal("fetch", fetchMock);
    render(<BurnInStatusView />);

    await waitFor(() => expect(screen.getByTestId("burnin-view")).toHaveTextContent("BURN-IN-EPOCH-01"));
    const view = screen.getByTestId("burnin-view");
    for (const value of [
      "BEFORE_TIMEOUT", "Historique des ordres PAPER", "BTC/USDT", "ETH/USDT",
      "SOL/USDT", "0.98", "RECOVERY_PRICE_UNAVAILABLE", "PB_MAX_POSITIONS",
      "PAPER_PORTFOLIO_BRAIN_LEVEL", "NOT_AVAILABLE",
    ]) {
      expect(view).toHaveTextContent(value);
    }
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/burn-in", { method: "GET" });
  });

  it("fails closed on an invalid HTTP 200 body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ product: "BurnInStatusSnapshot" })));
    render(<BurnInStatusView />);
    await waitFor(() => expect(screen.getByTestId("burnin-view")).toHaveTextContent("ERREUR TRANSPORT / CONTRAT"));
  });

  it("surfaces a governed missing-artifact error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ error_code: "BURN_IN_STATUS_MISSING" }, 503)));
    render(<BurnInStatusView />);
    await waitFor(() => expect(screen.getByTestId("burnin-view")).toHaveTextContent("BURN_IN_STATUS_MISSING"));
  });
});
