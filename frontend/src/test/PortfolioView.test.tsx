import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PortfolioView } from "../views/PortfolioView";
import { baseSnapshot } from "./fixtures";

describe("PortfolioView", () => {
  it("keeps PAPER and REAL/TESTNET blocks visually separate and never arithmetically combined", () => {
    const snap = baseSnapshot({
      portfolio: {
        ...baseSnapshot().portfolio,
        mode: "REAL_API",
        paper_equity_usd: { value: 1000, semantics: "PRESENT" },
        real_account_equity_usd: { value: 5000, semantics: "PRESENT" },
      },
    });
    render(<PortfolioView snapshot={snap} />);

    const paperBlock = screen.getByTestId("paper-block");
    const realBlock = screen.getByTestId("real-testnet-block");
    expect(paperBlock).toHaveTextContent("1000");
    expect(realBlock).toHaveTextContent("5000");
    // No combined/summed figure (e.g. 6000) appears anywhere in either block.
    expect(paperBlock.textContent).not.toContain("6000");
    expect(realBlock.textContent).not.toContain("6000");
  });

  it("labels real/testnet observation as read-only, never sizing/decision authority", () => {
    render(<PortfolioView snapshot={baseSnapshot()} />);
    expect(screen.getByTestId("real-account-warning")).toHaveTextContent(
      "READ-ONLY ACCOUNT OBSERVATION — NEVER USED FOR SIZING OR DECISION AUTHORITY",
    );
  });

  it("renders open positions from the supplied snapshot without recomputing PnL", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [
        {
          position_id: "p1",
          symbol: "BTCUSDT",
          side: "long",
          size_usd: 100,
          entry_price: 50000,
          current_price: { value: 51000, semantics: "PRESENT" },
          current_price_observed_at_utc: "2026-09-09T00:00:00+00:00",
          tp_price: 52000,
          sl_price: 49000,
          tp_sl_source: "original",
          unrealized_pnl_usd: { value: 20, semantics: "PRESENT" },
          unrealized_pnl_pct: { value: 2, semantics: "PRESENT" },
          opened_at: "2026-09-08T00:00:00+00:00",
          regime: { value: "TREND_BULL", semantics: "PRESENT" },
          restored_without_regime: false,
          personality: "aggressive",
          restored: false,
        },
      ],
    };
    render(<PortfolioView snapshot={snap} />);
    const row = screen.getByTestId("open-position-row");
    expect(row).toHaveTextContent("BTCUSDT");
    expect(row).toHaveTextContent("20");
  });
});
