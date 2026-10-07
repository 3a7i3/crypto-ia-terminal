import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
const base = process.env.MACHINE_LAB_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out =
  process.env.MACHINE_LAB_VISUAL_OUT_DIR || "artifacts/machine-lab-u6";
const fixtures = {};
for (const [endpoint, file] of Object.entries({
  snapshot: "A_minimal_canonical",
  market: "L_scanner",
  "market-microstructure": "M_microstructure",
  "ppl-comparison": "H_ppl_comparison",
  "research-lab": "N_research_publication",
  "research-strategies": "O_research_strategies",
  "financial-reconciliation": "P_financial_clarity",
  "burn-in": "J_burn_in",
  "runtime-service": "K_runtime_service",
}))
  fixtures[endpoint] = JSON.parse(
    await readFile(`.cross-stack-fixtures/${file}.json`, "utf8"),
  );
const assert = (ok, message) => {
  if (!ok) throw new Error(message);
};
assert(
  fixtures["research-strategies"]._proof.immutable_candidate_publisher_invoked,
  "No actual candidate publication fixture",
);
assert(
  fixtures["financial-reconciliation"]._proof.existing_fin_producer_invoked,
  "No actual financial producer fixture",
);
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [],
  requests = [];
try {
  for (const width of [1440, 820, 390]) {
    const page = await browser.newPage({
      viewport: { width, height: width === 390 ? 844 : 1000 },
    });
    page.setDefaultTimeout(10000);
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("request", (r) => {
      if (new URL(r.url()).pathname.startsWith("/api/"))
        requests.push(`${r.method()} ${new URL(r.url()).pathname}`);
    });
    await page.route("**/api/**", (route) => {
      const key = new URL(route.request().url()).pathname.split("/").at(-1);
      const f = fixtures[key];
      return route.fulfill({
        status: f?.http_status ?? 503,
        contentType: "application/json",
        body: JSON.stringify(f?.body ?? { error_code: "SOURCE_NOT_DEPLOYED" }),
      });
    });
    for (const [name, route, testid] of [
      ["machine", "/direction", "direction-view"],
      ["radar", "/paper-live/market", "market-view"],
      ["portfolio", "/paper-live/portfolio", "portfolio-view"],
      ["finance", "/paper-live/finance", "financial-reconciliation-view"],
      ["burn-in", "/paper-live/burn-in", "burnin-view"],
      ["research", "/research", "research-lab-view"],
      ["strategies", "/research/strategies", "strategy-board-view"],
    ]) {
      assert(
        (await page.goto(base + route, { waitUntil: "networkidle" }))?.ok(),
        `${name}: navigation failed`,
      );
      await page.getByTestId(testid).waitFor();
      const spaces = page.getByTestId("space-navigation");
      assert(
        (await spaces.getByRole("link").count()) === 2,
        "Two main spaces missing",
      );
      assert(
        (await spaces.locator('[aria-current="page"]').innerText()).includes(
          route.startsWith("/research") ? "Laboratoire" : "Machine",
        ),
        "Wrong workspace identity",
      );
      assert(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth + 1,
        ),
        `${name}/${width}: page overflow`,
      );
      if (name === "strategies") {
        assert(
          (await page.getByTestId(testid).innerText()).includes(
            "4 ligne(s) publiée(s)",
          ),
          "Published rows missing",
        );
        const area = page.locator(
          ".strategy-table-desktop",
        );
        await area
          .getByRole("button", { name: /Momentum.*Performance.*Satisfait/ })
          .click();
        const detail = page.getByTestId("strategy-detail");
        await detail.waitFor();
        assert(
          (await detail.innerText()).includes("LOW_SAMPLE"),
          "Evidence strength lost",
        );
        assert(
          await detail.evaluate((el) => el === document.activeElement),
          "Criterion did not focus its explanation",
        );
        await detail.screenshot({
          path: path.join(out, `strategy-detail-${width}.png`),
        });
        await detail.getByRole("button", { name: "Fermer la fiche" }).click();
      }
      if (name === "finance") {
        const cash = page
          .locator(".fin-metric")
          .filter({ has: page.getByText("Capital disponible", { exact: true }) });
        const exact =
          fixtures["financial-reconciliation"].body.financial.cash_available;
        await cash.getByText("Valeur exacte").click();
        assert(
          (await cash.locator("code").innerText()) === exact,
          "Exact financial source value lost",
        );
        await cash.getByText("Valeur exacte").click();
        await page.getByText(/^Preuves de réconciliation ·/).click();
        assert(
          await page
            .locator(width === 390 ? ".fin-mobile-records" : ".fin-table-wrap")
            .isVisible(),
          "Wrong financial layout",
        );
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: path.join(out, `${name}-${width}.png`),
        fullPage: true,
      });
      await page.screenshot({
        path: path.join(out, `${name}-viewport-${width}.png`),
      });
    }
    await page.close();
  }
  for (const scenario of ["missing", "invalid", "empty", "network"]) {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    await page.route("**/api/**", (route) => {
      if (scenario === "network") return route.abort();
      const body = structuredClone(fixtures["research-strategies"].body);
      if (scenario === "invalid") body.rows[0].criteria[0].status = "WINNER";
      if (scenario === "empty") {
        body.rows = [];
        body.catalog_state = "EMPTY";
        body.source_artifacts = body.source_artifacts.slice(0, 1);
      }
      return route.fulfill({
        status: scenario === "missing" ? 503 : 200,
        contentType: "application/json",
        body: JSON.stringify(
          scenario === "missing"
            ? { error_code: "RESEARCH_STRATEGY_BOARD_MISSING" }
            : body,
        ),
      });
    });
    await page.goto(base + "/research/strategies", {
      waitUntil: "networkidle",
    });
    assert(
      (await page.getByTestId("strategy-board-view").innerText()).includes(
        scenario === "empty"
          ? "Publication explicitement vide"
          : "Catalogue indisponible",
      ),
      "Missing/invalid source fabricated success",
    );
    assert(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth + 1,
      ),
      `${scenario}: overflow`,
    );
    await page.screenshot({
      path: path.join(out, `strategies-${scenario}-390.png`),
      fullPage: true,
    });
    await page.close();
  }
  assert(errors.length === 0, errors.join("\n"));
  assert(
    requests.every((r) => r.startsWith("GET /api/operator/v1/")),
    "Unexpected mutation or old transport",
  );
  console.log(
    "MACHINE_LAB_U6_READABILITY_TWO_SPACES_CRITERIA_EXACT_FIN_MOBILE_GET_ONLY=PASS",
  );
} finally {
  await browser.close();
}
