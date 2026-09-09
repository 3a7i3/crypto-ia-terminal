import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ObservedValueView } from "../components/ObservedValueView";

describe("ObservedValueView", () => {
  it("renders ZERO as an observed zero, not missing", () => {
    render(<ObservedValueView ov={{ value: 0, semantics: "ZERO" }} />);
    expect(screen.getByTestId("ov-zero")).toHaveTextContent("0");
  });

  it("renders FALSE as an observed false, not missing", () => {
    render(<ObservedValueView ov={{ value: false, semantics: "FALSE" }} />);
    expect(screen.getByTestId("ov-false")).toHaveTextContent("false");
  });

  it("renders EMPTY distinctly", () => {
    render(<ObservedValueView ov={{ value: [], semantics: "EMPTY" }} />);
    expect(screen.getByTestId("ov-empty")).toBeInTheDocument();
  });

  it("renders UNKNOWN, never as numeric zero", () => {
    render(<ObservedValueView ov={{ value: null, semantics: "UNKNOWN" }} />);
    const el = screen.getByTestId("ov-unknown");
    expect(el).toHaveTextContent("UNKNOWN");
    expect(el).not.toHaveTextContent("0");
  });

  it("renders UNAVAILABLE, never as numeric zero", () => {
    render(<ObservedValueView ov={{ value: null, semantics: "UNAVAILABLE" }} />);
    const el = screen.getByTestId("ov-unavailable");
    expect(el).toHaveTextContent("UNAVAILABLE");
    expect(el).not.toHaveTextContent("0");
  });

  it("renders NOT_APPLICABLE distinctly", () => {
    render(<ObservedValueView ov={{ value: null, semantics: "NOT_APPLICABLE" }} />);
    expect(screen.getByTestId("ov-not-applicable")).toHaveTextContent("NOT_APPLICABLE");
  });

  it("preserves the STALE value and displays a stale warning", () => {
    render(<ObservedValueView ov={{ value: 42, semantics: "STALE" }} />);
    const el = screen.getByTestId("ov-stale");
    expect(el).toHaveTextContent("42");
    expect(screen.getByTestId("ov-stale-badge")).toBeInTheDocument();
  });

  it("fails visibly and safely on an unrecognized semantics value", () => {
    render(<ObservedValueView ov={{ value: 1, semantics: "TOTALLY_INVENTED" as never }} />);
    expect(screen.getByTestId("ov-invalid")).toBeInTheDocument();
  });

  it("fails visibly and safely on a non-ObservedValue input, never crashing", () => {
    render(<ObservedValueView ov={"not-an-observed-value"} />);
    expect(screen.getByTestId("ov-invalid")).toBeInTheDocument();
  });
});
