import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ModuleHome } from "../views/ModuleHome";
import { MODULES } from "../lib/moduleNavigation";

// M1-C5 (EO-026, D2): /direction, / and /paper-live open the Market home (D-C5)
// and ModuleHome is not routed (it stays in the sources). Its business
// invariants, formerly proven by the WEB-DIR-01 / U2b / U4 / U6 browser proofs
// on /direction, are kept here: six module owners, one card per owner with its
// own source, absence never shown as availability, bounded boot reads, no
// domain value duplicated on the home. LOCAL TEST FIXTURES only.
type Answer = "unavailable" | "network";
function stub(answer: Answer) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input instanceof Request ? input.url : input), "http://127.0.0.1");
    calls.push(`${init?.method ?? "GET"} ${url.pathname}`);
    if (answer === "network") throw new TypeError("network down");
    return new Response(JSON.stringify({ error_code: "SOURCE_NOT_DEPLOYED" }), { status: 503, headers: { "content-type": "application/json" } });
  }));
  return calls;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const OWNERS = MODULES.slice(1);

describe("ModuleHome invariants (unrouted, kept in sources)", () => {
  it("shows one card per module owner and never turns absence into availability", async () => {
    const calls = stub("unavailable");
    const { container } = render(<MemoryRouter><ModuleHome /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("Source indisponible")).toHaveLength(6));
    const cards = container.querySelectorAll(".module-card");
    expect(cards).toHaveLength(6);
    expect(OWNERS).toHaveLength(6);
    OWNERS.forEach((owner, i) => {
      const link = cards[i].querySelector("a");
      expect(link?.getAttribute("href")).toBe(owner.to);
      expect(cards[i]).toHaveTextContent(owner.label);
    });
    expect(screen.queryByText("Publication disponible")).toBeNull();
    // Bounded boot reads: five distinct owned sources (decisions and positions
    // share the canonical projection), GET only, never burn-in.
    const unique = [...new Set(calls)];
    expect(unique.sort()).toEqual([
      "GET /api/operator/v1/financial-reconciliation",
      "GET /api/operator/v1/market",
      "GET /api/operator/v1/research-lab",
      "GET /api/operator/v1/runtime-service",
      "GET /api/operator/v1/snapshot",
    ]);
    expect(calls.every((c) => !c.endsWith("/burn-in"))).toBe(true);
    for (const key of unique) expect(calls.filter((c) => c === key).length).toBeLessThanOrEqual(2);
  });

  it("does not duplicate domain values or host diagnostics on the home", async () => {
    stub("unavailable");
    const { container } = render(<MemoryRouter><ModuleHome /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("Source indisponible")).toHaveLength(6));
    const text = container.textContent ?? "";
    for (const forbidden of [/Capital disponible/, /Burn-in/, /\bPF\b/, /Win Rate/, /Positions ouvertes/, /MainPID/]) expect(text).not.toMatch(forbidden);
  });

  it("a transport failure is never shown as a publication", async () => {
    stub("network");
    render(<MemoryRouter><ModuleHome /></MemoryRouter>);
    await waitFor(() => expect(screen.queryAllByText("Lecture en cours")).toHaveLength(0));
    expect(screen.queryByText("Publication disponible")).toBeNull();
    const states = screen.getAllByText(/^(Source indisponible|Lecture impossible)$/);
    expect(states).toHaveLength(6);
  });
});
