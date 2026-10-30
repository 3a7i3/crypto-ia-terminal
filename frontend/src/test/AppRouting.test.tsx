import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { baseSnapshot } from "./fixtures";
const response = (body: unknown, status = 200) =>
  ({ ok: status === 200, status, json: async () => body }) as Response;
describe("Module workspace routing", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(response(baseSnapshot()));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());
  it("opens one home with six modules and one primary navigation", async () => {
    render(<App />);
    await screen.findByTestId("module-home");
    expect(window.location.pathname).toBe("/direction");
    expect(
      screen
        .getByRole("navigation", { name: "Explorer les modules" })
        .querySelectorAll("article"),
    ).toHaveLength(6);
    expect(
      screen.getAllByRole("navigation", { name: "Modules de la machine" }),
    ).toHaveLength(1);
    expect(screen.queryByText("Ordres & Burn-in")).toBeNull();
    expect(screen.queryByTestId("tab-scores")).toBeNull();
  });
  it("preserves Decisions deep links and its single validated source", async () => {
    window.history.replaceState({}, "", "/paper-live/decisions");
    render(<App />);
    await screen.findByTestId("decisions-view");
    expect(screen.getByTestId("paper-live-shell")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/snapshot", {
      method: "GET",
    });
  });
  it("home reads five sources, shares canonical metadata and never requests burn-in", async () => {
    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(new Set(urls).size).toBe(5);
    expect(urls).toEqual(
      expect.arrayContaining([
        "/api/operator/v1/snapshot",
        "/api/operator/v1/market",
        "/api/operator/v1/financial-reconciliation",
        "/api/operator/v1/research-lab",
        "/api/operator/v1/runtime-service",
      ]),
    );
    expect(urls).not.toContain("/api/operator/v1/burn-in");
    expect(screen.getByTestId("module-home")).not.toHaveTextContent(
      "Capital disponible",
    );
    expect(screen.getByTestId("module-home")).toHaveTextContent(
      "ne certifie pas",
    );
  });
  it("opens the owned source from a home card", async () => {
    render(<App />);
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Explorer les modules" }),
      ).getByRole("link", { name: "Décisions" }),
    );
    await screen.findByTestId("decisions-view");
    expect(window.location.pathname).toBe("/paper-live/decisions");
  });
  it.each([
    ["/paper-live", "/direction"],
    ["/paper-live/overview", "/direction"],
    ["/paper-live/burn-in", "/paper-live/portfolio"],
    ["/paper-live/scores", "/paper-live/system"],
  ])("redirects obsolete %s to %s", async (from, to) => {
    window.history.replaceState({}, "", from);
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe(to));
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("/burn-in")),
    ).toBe(false);
  });
  it("keeps Research non-authoritative and independent", async () => {
    window.history.replaceState({}, "", "/research");
    render(<App />);
    expect(
      screen.getByTestId("research-header-domain-badge"),
    ).toHaveTextContent("RECHERCHE NON AUTORITAIRE");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/research-lab", {
      method: "GET",
    });
    expect(screen.queryByTestId("paper-live-shell")).toBeNull();
  });
  it("unknown routes show their path and never fetch data", () => {
    window.history.replaceState({}, "", "/route-inconnue");
    render(<App />);
    expect(screen.getByTestId("not-found-path")).toHaveTextContent(
      "/route-inconnue",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
