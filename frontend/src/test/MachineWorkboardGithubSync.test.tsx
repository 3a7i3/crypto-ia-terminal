import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { loadSnapshot, SNAPSHOT_STORAGE_KEY } from "../lib/githubRoadmapReconcile";
import { fakeGithub, sha, type Overrides } from "./githubFake";

const open = (o: Overrides = {}) => {
  const fake = fakeGithub(o);
  vi.stubGlobal("fetch", fake.fetch);
  window.history.replaceState({}, "", "/direction/travaux");
  render(<App />);
  return fake;
};
const refresh = () => fireEvent.click(screen.getByRole("button", { name: "Actualiser depuis GitHub" }));
const track = (id: string, name: string) => row(id).querySelector(`[data-track="${name}"]`)!;
const row = (id: string) => screen.getByText(id, { selector: ".wb-row-id" }).closest("tr")!;

describe("Workboard GitHub sync UI", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("does nothing on open and shows four separate tracks without a snapshot", () => {
    const fake = open();
    expect(fake.calls).toHaveLength(0);
    expect(screen.getByText(/Aucun relevé GitHub/)).toBeInTheDocument();
    const r = row("U8");
    expect(within(r).getByText("Non synchronisé")).toBeInTheDocument();
    expect(within(r).getByText("Non certifié")).toBeInTheDocument();
    expect(within(r).getAllByText("Non renseigné").length).toBe(2);
  });

  it("previews differences first and replaces the displayed snapshot only on confirmation", async () => {
    open();
    refresh();
    const preview = await screen.findByTestId("github-diff");
    expect(preview).toHaveTextContent("Premier relevé");
    expect(loadSnapshot()).toBeNull(); // nothing stored before confirmation
    expect(within(row("FRONTEND-RELEASE")).getByText("Non synchronisé")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remplacer le relevé affiché" }));
    await waitFor(() => expect(screen.queryByTestId("github-diff")).toBeNull());
    expect(loadSnapshot()?.complete).toBe(true);
    const github = track("FRONTEND-RELEASE", "github");
    expect(github).toHaveTextContent("PR #431 · Ouverte");
    expect(github).toHaveTextContent("CI verte");
    expect(github).toHaveTextContent(`@${sha(431).slice(0, 7)}`);
    // Merged PR: GitHub column changes, deployment/certification tracks stay the register's.
    const wb = row("WORKBOARD");
    expect(track("WORKBOARD", "github")).toHaveTextContent("PR #429 · Fusionnée");
    expect(wb.querySelector('[data-track="deployment"]')).toHaveTextContent("Non renseigné");
    expect(wb.querySelector('[data-track="certification"]')).toHaveTextContent("Non renseigné");
    expect(screen.getByText(/objet\(s\) GitHub ouvert\(s\) sans mission/)).toBeInTheDocument();
  });

  it("keeps the last successful snapshot and refuses to apply a partial one", async () => {
    open();
    refresh();
    fireEvent.click(await screen.findByRole("button", { name: "Remplacer le relevé affiché" }));
    await waitFor(() => expect(loadSnapshot()).not.toBeNull());
    const stored = window.localStorage.getItem(SNAPSHOT_STORAGE_KEY);
    cleanup();
    open({ failAt: url => (url.includes("/issues") ? new TypeError("Failed to fetch") : null) });
    // The previous snapshot is rendered from storage right away.
    expect(track("FRONTEND-RELEASE", "github")).toHaveTextContent("PR #431");
    refresh();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Relevé incomplet : non applicable");
    expect(alert).toHaveTextContent("NETWORK");
    expect(alert).toHaveTextContent("Aucune donnée n'a été effacée");
    expect(screen.queryByRole("button", { name: "Remplacer le relevé affiché" })).toBeNull();
    expect(window.localStorage.getItem(SNAPSHOT_STORAGE_KEY)).toBe(stored);
    expect(track("FRONTEND-RELEASE", "github")).toHaveTextContent("PR #431");
  });

  it("shows rate-limit refusal with the quota and spends nothing", async () => {
    const fake = open({ remaining: 2 });
    refresh();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("RATE_LIMIT_INSUFFICIENT");
    expect(alert).toHaveTextContent("Quota : 2/60");
    expect(fake.calls).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("lists field-level differences against the displayed snapshot", async () => {
    open();
    refresh();
    fireEvent.click(await screen.findByRole("button", { name: "Remplacer le relevé affiché" }));
    await waitFor(() => expect(loadSnapshot()).not.toBeNull());
    cleanup();
    open({ prHead: n => (n === 431 ? sha(7777) : sha(n)), checks: head => ({ total_count: 1, check_runs: [{ name: "ci", status: "completed", conclusion: "failure", head_sha: head }] }) });
    refresh();
    const diff = await screen.findByTestId("github-diff");
    expect(within(diff).getAllByText("FRONTEND-RELEASE").length).toBeGreaterThan(0);
    expect(diff).toHaveTextContent("pr.head");
    expect(diff).toHaveTextContent("ci.état");
    expect(diff).toHaveTextContent("FAILURE");
    fireEvent.click(screen.getByRole("button", { name: "Ignorer" }));
    expect(screen.queryByTestId("github-diff")).toBeNull();
    expect(loadSnapshot()!.pulls.find(p => p.number === 431)!.headSha).toBe(sha(431)); // unchanged
  });
});
