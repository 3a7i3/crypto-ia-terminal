import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

describe("Machine workboard governance boundary", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("opens the dated register without fetching runtime or GitHub", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState({}, "", "/direction/travaux");
    render(<App />);
    expect(screen.getByTestId("machine-workboard")).toBeInTheDocument();
    expect(screen.getByText(/changements GitHub ultérieurs/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Rechercher"), {target:{value:"U8"}});
    expect(screen.getByText("U8 · non certifié")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Rechercher"), {target:{value:"D1-E"}});
    expect(screen.getByText("D1-E · NOT_PROVEN")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("filters without hiding scope and restores the full register", () => {
    window.history.replaceState({}, "", "/direction/travaux");
    render(<App />);
    fireEvent.change(screen.getByLabelText("État"), { target: { value: "paused" } });
    expect(screen.getByText("Agents, bounties et économie AIC")).toBeInTheDocument();
    expect(screen.queryByText("Socle scientifique L0 → L3")).toBeNull();
    fireEvent.change(screen.getByLabelText("Rechercher"), { target: { value: "introuvable" } });
    expect(screen.getByRole("status")).toHaveTextContent("Aucun travail");
    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser" }));
    expect(screen.getByText("Socle scientifique L0 → L3")).toBeInTheDocument();
    expect(screen.getByText(/Collecte non activée/)).toBeInTheDocument();
  });
});
