import { describe, expect, it } from "vitest";
import { validateBurnInStatusSnapshot } from "../lib/burnInStatusValidation";
import { burnInFixture } from "./burnInFixtures";

describe("APP-UNIFY U2 burn-in frontend contract", () => {
  it("accepts a complete governed snapshot", () => {
    expect(validateBurnInStatusSnapshot(burnInFixture())).toBe(true);
  });

  it("rejects a lifecycle count mismatch", () => {
    const value = burnInFixture();
    value.lifecycle_counts.closed = 7;
    expect(validateBurnInStatusSnapshot(value)).toBe(false);
  });

  it("rejects fabricated PnL on UNRESOLVED", () => {
    const value = burnInFixture();
    value.lifecycle_history[0].net_realized_pnl_usd = 0;
    expect(validateBurnInStatusSnapshot(value)).toBe(false);
  });

  it("rejects an invalid OPEN terminal outcome", () => {
    const value = burnInFixture();
    value.lifecycle_history[1].exit_price = 200;
    expect(validateBurnInStatusSnapshot(value)).toBe(false);
  });

  it("rejects config/source identity divergence", () => {
    const value = burnInFixture();
    value.frozen_config.snapshot_sha256 = "4".repeat(64);
    expect(validateBurnInStatusSnapshot(value)).toBe(false);
  });
});
