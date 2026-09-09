import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModeBadge } from "../components/ModeBadge";

describe("ModeBadge", () => {
  it.each(["PAPER", "REAL_API", "TESTNET_API", "UNKNOWN"])("renders %s distinctly", (mode) => {
    render(<ModeBadge mode={mode} />);
    expect(screen.getByTestId("mode-badge")).toHaveAttribute("data-mode", mode);
  });

  it("never falls back to PAPER for an unknown/invalid mode value", () => {
    render(<ModeBadge mode={"totally-invalid" as never} />);
    expect(screen.getByTestId("mode-badge")).toHaveAttribute("data-mode", "UNKNOWN");
  });

  it("never falls back to PAPER for a null mode", () => {
    render(<ModeBadge mode={null} />);
    expect(screen.getByTestId("mode-badge")).toHaveAttribute("data-mode", "UNKNOWN");
  });

  it("never relabels REAL_API as LIVE", () => {
    render(<ModeBadge mode="REAL_API" />);
    expect(screen.getByTestId("mode-badge")).toHaveTextContent("REAL_API");
    expect(screen.getByTestId("mode-badge")).not.toHaveTextContent("LIVE");
  });
});
