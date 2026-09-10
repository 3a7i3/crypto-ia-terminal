import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SystemView } from "../views/SystemView";
import { baseSnapshot } from "./fixtures";

describe("SystemView", () => {
  it("renders boot_alive=null/UNKNOWN as UNKNOWN, never alive or dead", () => {
    render(<SystemView snapshot={baseSnapshot()} />);
    expect(screen.getAllByTestId("ov-unknown").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^alive$/i)).toBeNull();
    expect(screen.queryByText(/^dead$/i)).toBeNull();
  });

  it("never claims liveness from /healthz semantics", () => {
    render(<SystemView snapshot={baseSnapshot()} />);
    expect(screen.getByTestId("boot-alive-note")).toHaveTextContent("It never claims the advisor is alive.");
  });
});
