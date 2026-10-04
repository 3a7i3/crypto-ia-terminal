import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { validateMarketMicrostructureSnapshot } from "../lib/marketMicrostructureValidation";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { microstructureFixture } from "./marketMicrostructureFixtures";

const fixture = path.join(process.env.CROSS_STACK_FIXTURES_DIR ?? path.resolve(__dirname, "../../.cross-stack-fixtures"), "M_microstructure.json");
const load = () => JSON.parse(readFileSync(fixture, "utf8")).body;
afterEach(() => vi.unstubAllGlobals());

it("keeps schema 1.0 readable with explicit missing detail", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => microstructureFixture() }));
  render(<MarketMicrostructureView />);
  await waitFor(() => expect(screen.getAllByText("Détail non publié · schéma 1.0")).toHaveLength(2));
});

describe.skipIf(!existsSync(fixture))("real Python LMI detail → React", () => {
  it("renders exact signed values, zero, missing fields and independent group freshness", async () => {
    const body = load();
    expect(validateMarketMicrostructureSnapshot(body)).toBe(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }));
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getAllByTestId("lmi-detail")).toHaveLength(2));
    const liquidity = screen.getAllByTestId("lmi-detail-liquidity")[0];
    expect(liquidity).toHaveTextContent("STALE");
    expect(liquidity).toHaveTextContent("n’est pas attestée");
    expect(liquidity).toHaveTextContent("-462.375");
    expect(within(liquidity).getByText("Ask ajouté · USD").nextElementSibling).toHaveTextContent(/^0$/);
    expect(screen.getAllByTestId("lmi-detail-flow")[0]).toHaveTextContent("-123.4567");
    expect(screen.getAllByTestId("lmi-detail-resistance")[0]).toHaveTextContent("UNKNOWN");
    expect(screen.getAllByTestId("lmi-detail-liquidity")[1]).toHaveTextContent("groupe non publié");
    expect(screen.getByTestId("microstructure-view")).not.toHaveTextContent("MUST_NOT_ESCAPE");
  });

  it.each(["privacy", "fake-freshness", "bad-ratio", "negative-volume", "fractional-count", "false-evidence", "missing-detail", "legacy-extra"])("rejects %s", (kind) => {
    const body = load(), detail = body.rows[0].detail;
    if (kind === "privacy") detail.liquidity.raw = "private";
    if (kind === "fake-freshness") detail.liquidity.freshness_classification = "FRESH";
    if (kind === "bad-ratio") detail.liquidity.cancellation_rate_bid = 2;
    if (kind === "negative-volume") detail.liquidity.bid_added_usd = -1;
    if (kind === "fractional-count") detail.flow.buy_count = 1.5;
    if (kind === "false-evidence") detail.liquidity.observation_evidence = "BOOK_OBSERVED";
    if (kind === "missing-detail") delete body.rows[0].detail;
    if (kind === "legacy-extra") body.schema_version = "1.0.0";
    expect(validateMarketMicrostructureSnapshot(body)).toBe(false);
  });
});
