import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BurnInHistory } from "../views/BurnInStatusView";
import { BurnInStatistics } from "../components/BurnInStatistics";
import { burnInFixture } from "./burnInFixtures";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe("Complete PPL history", () => {
  it("paginates beyond the event-center cap and can find the oldest identity", () => {
    const s = burnInFixture();
    s.lifecycle_history = Array.from({length: 177}, (_, i) => ({...s.lifecycle_history[0], trade_id: `ORDER-${String(i).padStart(3, "0")}`}));
    render(<BurnInHistory s={s} />);
    expect(screen.getAllByTestId("burnin-history-row")).toHaveLength(20);
    fireEvent.click(screen.getByText("Page suivante"));
    expect(screen.getByRole("status")).toHaveTextContent("Page 2 sur 9");
    fireEvent.change(screen.getByLabelText("Rechercher un ordre"), {target:{value:"ORDER-176"}});
    expect(screen.getAllByTestId("burnin-history-row")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("1 ordres correspondent sur 177");
    expect(screen.getByText("Page suivante")).toBeDisabled();
  });
  it("filters status, side and UTC opening dates without replacing empty results", () => {
    render(<BurnInHistory s={burnInFixture()} />);
    fireEvent.change(screen.getByLabelText("Statut des ordres"), {target:{value:"OPEN"}});
    expect(screen.getAllByTestId("burnin-history-row")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Sens des ordres"), {target:{value:"LONG"}});
    expect(screen.queryAllByTestId("burnin-history-row")).toHaveLength(0);
    expect(screen.getByText("Aucun ordre ne correspond aux filtres.")).toBeVisible();
  });
});
function statistics() {
  const s = burnInFixture();
  return {schema_version:"1.0.0", product:"BurnInDescriptiveStatistics", mode:"READ_ONLY", authority:"PPL_AUTHORITY_PRESENTATION", paper_epoch_id:s.paper_epoch_id, config_snapshot_hash:s.config_snapshot_hash, ppl_stream_sha256:s.ppl_stream_sha256, last_sequence:s.last_sequence, generated_at_utc:s.generated_at_utc, snapshot_age_s:10, freshness_classification:"FRESH", population:{...s.lifecycle_counts,wins:1,losses:0,breakeven:0}, metrics:{net_realized_pnl_usd:"0.98",gross_pnl_usd:"1",closed_fees_usd:"0.02",win_rate_pct:"100",profit_factor:null,average_gain_usd:"0.98",average_loss_usd:null,average_net_pnl_usd:"0.98"}};
}
describe("Published descriptive statistics", () => {
  it("renders values only from a matching source boundary", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>statistics()}));
    render(<BurnInStatistics snapshot={burnInFixture()} />);
    await waitFor(()=>expect(screen.getByText(/1 clôtures/)).toBeVisible());
    expect(screen.getAllByText("Non disponible")).toHaveLength(2);
  });
  it.each([{win_rate_pct:"101"}, {closed_fees_usd:"-1"}, {profit_factor:"-2"}])("rejects invalid metric domains %j", async changes => {
    const body = statistics();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>({...body, metrics:{...body.metrics,...changes}})}));
    render(<BurnInStatistics snapshot={burnInFixture()} />);
    await waitFor(()=>expect(screen.getByRole("status")).toHaveTextContent("frontière différente"));
  });
  it("refuses a different epoch rather than showing plausible numbers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>({...statistics(),paper_epoch_id:"OTHER"})}));
    render(<BurnInStatistics snapshot={burnInFixture()} />);
    await waitFor(()=>expect(screen.getByRole("status")).toHaveTextContent("frontière différente"));
    expect(screen.queryByText("0,98")).toBeNull();
  });
});
