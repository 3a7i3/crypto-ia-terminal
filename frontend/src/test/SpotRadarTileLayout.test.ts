import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Read from disk: Vitest does not serve CSS contents through ?raw.
const read = (name: string) => readFileSync(fileURLToPath(new URL("../" + name, import.meta.url)), "utf8");
const spotRadarCss = read("spot-radar.css");
const radarPolishCss = read("radar-polish.css");
const intradayCss = read("intraday.css");
const tokensCss = read("tokens.css");

// F1-B / M1-B non-regression on the stylesheet contract. jsdom has no layout
// engine, so the geometry itself (no truncation, no clipping, no overlap, touch
// targets) is measured under Chromium by the M1-B harness (outside the repo).
const rules = (css: string) =>
  [...css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}@]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
const spotTileRules = (css: string) => rules(css).filter((r) => /\.spot-radar[^,]*\.intraday-bubble(?![s-])/.test(r.selector));
const ruleFor = (css: string, selector: string) => rules(css).filter((r) => r.selector === selector);
// Top-level rules only: responsive overrides inside @media blocks are allowed.
const topLevel = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, "");

describe("Spot Radar tile stylesheet", () => {
  it("keeps Spot Radar tile geometry in spot-radar.css only", () => {
    expect(spotTileRules(spotRadarCss).length).toBeGreaterThan(5);
    expect(rules(radarPolishCss).length).toBeGreaterThan(20);
    expect(spotTileRules(radarPolishCss)).toEqual([]);
  });

  it("never truncates, ellipses or squeezes symbols and prices", () => {
    const text = spotTileRules(spotRadarCss).find((r) => r.selector.includes("strong") && r.selector.includes(".intraday-bubble-price"));
    expect(text?.body).toMatch(/white-space:normal/);
    expect(text?.body).toMatch(/overflow:visible/);
    expect(text?.body).toMatch(/text-overflow:clip/);
    expect(text?.body).toMatch(/overflow-wrap:anywhere/);
    const children = spotTileRules(spotRadarCss).find((r) => r.selector === ".spot-radar .intraday-bubble>*");
    expect(children?.body).toMatch(/flex-shrink:0/);
    for (const r of spotTileRules(spotRadarCss)) {
      expect(r.body).not.toMatch(/text-overflow:ellipsis|white-space:nowrap|overflow:hidden/);
    }
  });

  it("lets tile height follow content instead of a fixed circle", () => {
    const tile = spotTileRules(spotRadarCss).find((r) => r.selector === ".spot-radar .intraday-bubble");
    expect(tile?.body).toMatch(/height:auto/);
    expect(tile?.body).toMatch(/aspect-ratio:auto/);
    expect(tile?.body).toMatch(/min-height:0/);
    for (const r of spotTileRules(spotRadarCss)) expect(r.body).not.toMatch(/aspect-ratio:1\b/);
  });

  it("leaves the shared Intraday ellipsis rule untouched (Intraday keeps its bubbles)", () => {
    expect(intradayCss).toContain(".intraday-bubble strong,.intraday-bubble-price{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;}");
  });
});

describe("M1-B Market design tokens", () => {
  const tokens = ["--touch-min", "--radar-surface", "--radar-surface-raised", "--radar-border", "--radar-text", "--radar-text-muted", "--radar-live", "--radar-stale", "--radar-disconnected", "--radar-synthetic"];

  it("declares the Market tokens once, in tokens.css", () => {
    for (const t of tokens) {
      expect(tokensCss).toMatch(new RegExp(t + ":\\s*\\S"));
      expect(radarPolishCss).not.toMatch(new RegExp(t + ":"));
      expect(spotRadarCss).not.toMatch(new RegExp(t + ":"));
    }
    expect(tokensCss).toMatch(/--touch-min:\s*44px/);
  });

  it("keeps the freshness colours distinct and token-driven", () => {
    expect(ruleFor(spotRadarCss, ".radar-live")[0]?.body).toBe("color:var(--radar-live)");
    expect(ruleFor(spotRadarCss, ".radar-stale,.radar-unresolved")[0]?.body).toBe("color:var(--radar-stale)");
    expect(ruleFor(spotRadarCss, ".radar-disconnected")[0]?.body).toBe("color:var(--radar-disconnected)");
    expect(ruleFor(spotRadarCss, ".radar-synthetic")[0]?.body).toBe("color:var(--radar-synthetic)");
    const values = ["live", "stale", "disconnected", "synthetic"].map((s) => tokensCss.match(new RegExp("--radar-" + s + ":\\s*(#[0-9a-f]{6})"))?.[1]);
    expect(new Set(values).size).toBe(4);
  });

  it("uses tokens instead of raw opaque colours in the Radar sheets", () => {
    // #rrggbbaa translucent borders are allowed; opaque #rrggbb literals are not.
    expect(spotRadarCss.replace(/\/\*[\s\S]*?\*\//g, "")).not.toMatch(/#[0-9a-f]{6}(?![0-9a-f])/i);
    const radarRules = rules(radarPolishCss).filter((r) => /\.radar-/.test(r.selector));
    for (const r of radarRules) expect(r.body).not.toMatch(/#[0-9a-f]{6}(?![0-9a-f])/i);
  });

  it("defines the Radar chart and timeframes once (no competing definitions)", () => {
    for (const sel of [".radar-chart", ".radar-chart p", ".radar-chart figcaption", ".radar-timeframes", ".radar-timeframes button", ".radar-timeframes small"]) {
      expect(ruleFor(topLevel(radarPolishCss), sel)).toEqual([]);
      expect(ruleFor(topLevel(spotRadarCss), sel)).toHaveLength(1);
    }
  });

  it("keeps Radar and shell controls at the 44 px touch minimum", () => {
    expect(ruleFor(spotRadarCss, ".spot-radar input,.spot-radar select")[0]?.body).toMatch(/min-height:var\(--touch-min\)/);
    expect(ruleFor(radarPolishCss, ".app-brand")[0]?.body).toMatch(/min-height:var\(--touch-min\)/);
    expect(ruleFor(radarPolishCss, ".appearance-heading .icon-button")[0]?.body).toMatch(/min-width:var\(--touch-min\);min-height:var\(--touch-min\)/);
    expect(ruleFor(spotRadarCss, ".radar-timeframes button")[0]?.body).toMatch(/min-height:48px/);
  });

  it("wraps the Radar detail title and price instead of overflowing", () => {
    expect(ruleFor(spotRadarCss, ".spot-radar .intraday-detail h3,.spot-radar .intraday-detail-price")[0]?.body).toMatch(/overflow-wrap:anywhere/);
  });
});
