import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// M1-C1-R1 (EO-023) stylesheet contract for the Market tab links. jsdom has no
// layout engine: the rendered 44 × 44 px targets and the unclipped focus ring
// are measured under Chromium by the R1 harness (outside the repo).
const read = (name: string) => readFileSync(fileURLToPath(new URL("../" + name, import.meta.url)), "utf8");
const css = read("market-navigation.css");
const tokens = read("tokens.css");
const marketView = read("views/MarketView.tsx");
const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}@]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
const SCOPE = ".market-workspace-tabs[role=tablist]";

describe("Market navigation stylesheet (M1-C1-R1)", () => {
  it("only targets the Market tab list", () => {
    expect(rules.length).toBeGreaterThan(0);
    for (const r of rules) for (const s of r.selector.split(",")) expect(s.trim().startsWith(SCOPE)).toBe(true);
    expect(css).not.toMatch(/!important/);
  });

  it("gives every tab a 44 px minimum target from the shared touch token", () => {
    const tab = rules.find((r) => r.selector === SCOPE + ">a[role=tab]");
    expect(tab?.body).toMatch(/min-height:var\(--touch-min,44px\)/);
    expect(tab?.body).toMatch(/min-width:var\(--touch-min,44px\)/);
    expect(tab?.body).toMatch(/display:inline-flex/);
    expect(tokens).toMatch(/--touch-min:\s*44px/);
  });

  it("keeps room for the whole 3 px + 4 px focus ring inside the scrollable list", () => {
    const list = rules.find((r) => r.selector === SCOPE);
    const [top, side, bottom] = (list?.body.match(/padding:(\d+)px (\d+)px (\d+)px/) ?? []).slice(1).map(Number);
    for (const v of [top, side, bottom]) expect(v).toBeGreaterThanOrEqual(7);
  });

  it("does not restyle colours, the selected state or the focus ring", () => {
    const properties = rules.flatMap((r) => r.body.split(";").map((d) => d.split(":")[0].trim()).filter(Boolean));
    for (const p of properties) expect(p).not.toMatch(/^(color|background|outline|border|font)/);
  });

  it("is imported by MarketView after the existing Market sheets", () => {
    const venues = marketView.indexOf('import "../market-venues.css";');
    const nav = marketView.indexOf('import "../market-navigation.css";');
    expect(venues).toBeGreaterThan(-1);
    expect(nav).toBeGreaterThan(venues);
  });
});
