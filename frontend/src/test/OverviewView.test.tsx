import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OverviewView } from "../views/OverviewView";
import { baseSnapshot } from "./fixtures";

describe("OverviewView", () => {
  it("visibly presents PREVIOUS_INSTANCE and PRODUCER_RESTARTED", () => {
    const snap = baseSnapshot({
      instance_relation: "PREVIOUS_INSTANCE",
      runtime_state: "LAST_KNOWN",
      stale_reason: "PRODUCER_RESTARTED",
    });
    render(<OverviewView snapshot={snap} />);
    expect(screen.getByTestId("instance-relation")).toHaveTextContent("PREVIOUS_INSTANCE");
    expect(screen.getByTestId("runtime-state")).toHaveTextContent("LAST_KNOWN");
    expect(screen.getByTestId("overview-view")).toHaveTextContent("PRODUCER_RESTARTED");
  });

  it("visibly presents CURRENT_INSTANCE distinctly", () => {
    const snap = baseSnapshot({ instance_relation: "CURRENT_INSTANCE", runtime_state: "CURRENT" });
    render(<OverviewView snapshot={snap} />);
    expect(screen.getByTestId("instance-relation")).toHaveTextContent("CURRENT_INSTANCE");
    expect(screen.getByTestId("runtime-state")).toHaveTextContent("CURRENT");
  });
});
