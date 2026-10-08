import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { baseSnapshot } from "./fixtures";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("WEB-DIR-01-D2 product routing", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResponse(baseSnapshot()));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the compact Machine synthesis from the root", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("direction-view")).toBeInTheDocument());
    expect(window.location.pathname).toBe("/direction");
    expect(screen.getByRole("navigation", { name: "Catégories Machine" })).toBeInTheDocument();
  });

  it("resolves a PAPER LIVE deep link without losing its product shell", async () => {
    window.history.replaceState({}, "", "/paper-live/decisions");
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("decisions-view")).toBeInTheDocument());
    expect(screen.getByTestId("paper-live-shell")).toBeInTheDocument();
    expect(screen.getByTestId("paper-domain-banner")).toHaveTextContent("exécution simulée");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps Direction separate and fetches its seven independent governed sources", async () => {
    window.history.replaceState({}, "", "/direction");
    render(<App />);

    expect(screen.getByTestId("direction-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("paper-live-shell")).toBeNull();
    expect(screen.getByRole("heading", { name: "Machine" })).toBeInTheDocument();
    expect(screen.getAllByText("État, portefeuille et marché")[0]).toBeInTheDocument();
    expect(screen.getByTestId("direction-authority-strip")).toHaveTextContent("PRÉSENTATION");
    expect(screen.getByTestId("direction-authority-strip")).toHaveTextContent("LECTURE SEULE");
    expect(screen.getByTestId("direction-authority-strip")).toHaveTextContent("AUCUNE AUTORITÉ PAPER");
    expect(screen.getByText(/État global inconnu/)).toBeInTheDocument();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7));
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(
      expect.arrayContaining([
        "/api/operator/v1/ppl-accounting-history",
        "/api/operator/v1/snapshot",
        "/api/operator/v1/financial-reconciliation",
        "/api/operator/v1/market",
        "/api/operator/v1/research-lab",
        "/api/operator/v1/burn-in",
        "/api/operator/v1/runtime-service",
      ]),
    );
  });

  it("returns from Direction to PAPER LIVE through the explicit operator control", async () => {
    window.history.replaceState({}, "", "/direction");
    render(<App />);

    const returnControl = screen.getByTestId("return-paper-live");
    expect(returnControl).toHaveAttribute("href", "/paper-live");
    returnControl.focus();
    expect(returnControl).toHaveFocus();
    fireEvent.click(returnControl);

    await waitFor(() => expect(screen.getByTestId("paper-live-shell")).toBeInTheDocument());
    expect(window.location.pathname).toBe("/paper-live");
  });

  it("marks Research as non-authoritative in its independent shell", async () => {
    window.history.replaceState({}, "", "/research");
    render(<App />);

    expect(screen.getByTestId("research-shell")).toBeInTheDocument();
    expect(screen.getByTestId("research-header-domain-badge")).toHaveTextContent(
      "RECHERCHE NON AUTORITAIRE",
    );
    expect(screen.queryByTestId("paper-live-shell")).toBeNull();
    await waitFor(() =>
      expect(screen.getByTestId("research-lab-view")).toHaveTextContent(
        "Erreur de contrat ou de transport du Laboratoire",
      ),
    );
  });

  it("renders an explicit not-found surface and performs no data fetch", () => {
    window.history.replaceState({}, "", "/route-inconnue");
    render(<App />);

    expect(screen.getByTestId("not-found-view")).toBeInTheDocument();
    expect(screen.getByTestId("not-found-path")).toHaveTextContent("/route-inconnue");
    expect(window.location.pathname).toBe("/route-inconnue");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
