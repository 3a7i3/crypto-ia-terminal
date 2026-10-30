import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { applyTheme, readTheme, THEME_KEY } from "../lib/theme";
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});
function open() {
  fireEvent.click(
    screen.getByRole("button", { name: "Paramètres de l’application" }),
  );
}
describe("Appearance is local and accessible", () => {
  it("uses the OS preference initially and ignores invalid stored values", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    localStorage.setItem(THEME_KEY, "not-a-theme");
    expect(readTheme()).toBe("dark");
    localStorage.setItem(THEME_KEY, "light");
    expect(readTheme()).toBe("light");
  });
  it("switches themes, persists across remounts and never calls the network", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AppearanceSettings />);
    open();
    fireEvent.click(screen.getByRole("radio", { name: "Sombre" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    cleanup();
    render(<AppearanceSettings />);
    open();
    expect(screen.getByRole("radio", { name: "Sombre" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Clair" }));
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("closes with Escape and restores focus to the gear", () => {
    render(<AppearanceSettings />);
    open();
    screen.getByRole("radio", { name: "Sombre" }).focus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("heading", { name: "Apparence" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Paramètres de l’application" }),
    ).toHaveFocus();
  });
  it("closes on outside pointer press", () => {
    render(<AppearanceSettings />);
    open();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("heading", { name: "Apparence" })).toBeNull();
  });
  it("keeps working with blocked storage and reports session-only selection", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    render(<AppearanceSettings />);
    open();
    fireEvent.click(screen.getByRole("radio", { name: "Sombre" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("status")).toHaveTextContent("cette session");
  });
  it("synchronizes a preference changed in another tab", () => {
    render(<AppearanceSettings />);
    open();
    localStorage.setItem(THEME_KEY, "dark");
    fireEvent(
      window,
      new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }),
    );
    expect(screen.getByRole("radio", { name: "Sombre" })).toBeChecked();
  });
  it("updates the mobile browser chrome for both themes", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
    applyTheme("dark");
    expect(meta.content).toBe("#101820");
    applyTheme("light");
    expect(meta.content).toBe("#f4f6f8");
    meta.remove();
  });
});
