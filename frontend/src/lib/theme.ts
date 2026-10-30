export type Theme = "light" | "dark";
export const THEME_KEY = "crypto-terminal.theme";

export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* Storage can be disabled in private or restricted browsers. */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#101820" : "#f4f6f8");
}

export function saveTheme(theme: Theme): boolean {
  applyTheme(theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
    return true;
  } catch {
    return false;
  }
}
