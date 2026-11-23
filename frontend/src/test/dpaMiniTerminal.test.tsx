// Bloc du Data Provenance Auditor : même bloc que le cartographe (opérateur, 2026-11-23),
// routes propres, voyant propre, chaîne de provenance dans les bulles.
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const T0 = Date.parse("2026-11-23T01:00:00Z");
const BASE = "/api/operator/v1/agent-invocations";

const dpaSummary = {
  contract: "cat.observation.invocation.v1",
  agent_id: "data-provenance-auditor",
  runner_id: "obs-data-provenance-ro-01",
  mission_id: "f".repeat(64),
  server_observed_at_utc: "2026-11-23T01:00:00Z",
  connection: "AVAILABLE",
  connection_reason: "dernière preuve valide",
  activity: "TERMINE",
  activity_reason: "dernière invocation COMPLETED (verrou libre)",
  life_observed: false,
  lease_until_utc: null,
  last_activity_utc: "2026-11-23T00:30:01Z",
  last_mission_age_s: 1799,
  mission_overdue: false,
  last_result: "PARTIAL",
  last_state: "COMPLETED",
  invocation_id: "a".repeat(32),
  display: { light: "RED", label: "Inactif · fin normale", reason: "dernière invocation terminée", valid_until_utc: "2026-11-23T01:01:30Z" },
  read_only: true,
};

const dpaHistory = {
  contract: "cat.observation.invocation.v1",
  read_only: true,
  connection: "AVAILABLE",
  connection_reason: "historique lu",
  total: 1,
  items: [
    {
      verdict: "VALID",
      reason: null,
      invocation_id: "a".repeat(32),
      started_utc: "2026-11-23T00:30:00Z",
      ended_utc: "2026-11-23T00:30:01Z",
      state: "COMPLETED",
      result_status: "PARTIAL",
      analysed_sha: "766f4fd7d8a797a684c5b89de9fd0e83bc8b74b3",
      content_sha256: "805edd9b".padEnd(64, "0"),
      summary: {
        seen: { sources: 9, imports: 0, calls: 0 },
        found: ["PRODUCER_IDENTIFIED"],
        not_concluded: [{ path: null, line: null, reason: "STORAGE_BINDING_RUNTIME" }],
        write_templates: 0,
        limits: 5,
        errors: [],
        chain: {
          links: 2,
          levels: { INFERRED: 1, PROVEN: 1 },
          hops: [
            { hop: "PRODUCER", level: "PROVEN" },
            { hop: "STORAGE_TO_READER", level: "INFERRED" },
          ],
          inferred: 1,
          runtime_required: 3,
        },
      },
    },
  ],
};

const respond = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("bloc du Data Provenance Auditor", () => {
  it("lit ses propres routes et affiche voyant, chaîne et bouton ⏰", async () => {
    vi.useFakeTimers({ now: T0 });
    const urls: string[] = [];
    vi.stubGlobal("fetch", (u: string) => {
      urls.push(String(u));
      if (u === `${BASE}/data-provenance-auditor`) return respond(dpaSummary);
      if (u === `${BASE}/data-provenance-auditor/history`) return respond(dpaHistory);
      if (u === `${BASE}/data-provenance-auditor/schedule`)
        return respond({ applied: "1h", requested: "1h", next_utc: "2026-11-23T01:30:00Z", connection: "AVAILABLE" });
      return new Promise<Response>(() => undefined);
    });
    const { AgentRegistryLiveForTest } = await import("../views/AgentRegistryView");
    render(<AgentRegistryLiveForTest pollMs={10 * 60_000} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(urls).toEqual(
      expect.arrayContaining([
        `${BASE}/data-provenance-auditor`,
        `${BASE}/data-provenance-auditor/history`,
        `${BASE}/data-provenance-auditor/schedule`,
        `${BASE}/repository-cartographer`,
      ]),
    );
    const dpa = within(screen.getByTestId("live-agent-data-provenance-auditor"));
    expect(dpa.getByRole("heading", { name: "Data Provenance Auditor" })).toBeInTheDocument();
    expect(dpa.getByTestId("miniterm-giro")).toHaveAttribute("data-light", "RED");
    expect(dpa.getByTestId("invocation-activity")).toHaveAttribute("data-light", "RED");
    expect(dpa.getByTestId("miniterm-chain")).toHaveTextContent("PRODUCER PROVEN → STORAGE_TO_READER INFERRED");
    expect(dpa.getByTestId("miniterm-term")).toHaveTextContent("STORAGE_BINDING_RUNTIME");
    expect(dpa.getByTestId("schedule-label")).toHaveTextContent("1 h");
    expect(dpa.getByTestId("schedule-clock")).toBeInTheDocument();
    // Le voyant du profil dans la famille vient de la preuve du DPA, pas de celle du cartographe.
    expect(within(screen.getByTestId("agent-profile-data-provenance-auditor")).getAllByTestId("agent-activity")[0]).toHaveAttribute(
      "data-light",
      "RED",
    );
    // Le cartographe sans réponse reste gris : les deux blocs sont indépendants.
    const carto = within(screen.getByTestId("live-agent-repository-cartographer"));
    expect(carto.getByTestId("miniterm-giro")).toHaveAttribute("data-light", "GRAY");
  });

  it("le bouton ⏰ du DPA dépose sa demande sur sa propre route", async () => {
    vi.useFakeTimers({ now: T0 });
    const posts: { url: string; body: string }[] = [];
    vi.stubGlobal("fetch", (u: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts.push({ url: String(u), body: String(init.body) });
        return Promise.resolve(new Response("{}", { status: 202 }));
      }
      if (String(u).endsWith("/schedule")) return respond({ applied: "1h", next_utc: "2026-11-23T01:30:00Z", connection: "AVAILABLE" });
      return new Promise<Response>(() => undefined);
    });
    const { AgentRegistryLiveForTest } = await import("../views/AgentRegistryView");
    render(<AgentRegistryLiveForTest pollMs={10 * 60_000} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const dpa = within(screen.getByTestId("live-agent-data-provenance-auditor"));
    await act(async () => {
      dpa.getByTestId("schedule-clock").click();
    });
    await act(async () => {
      dpa.getByTestId("schedule-10min").click();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(posts).toEqual([{ url: `${BASE}/data-provenance-auditor/schedule`, body: '{"rhythm":"10min"}' }]);
  });
});
