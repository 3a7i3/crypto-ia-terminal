import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import { ResearchStrategyBoardView } from "../views/ResearchStrategyBoardView";
import { validateResearchStrategyBoard } from "../lib/researchStrategyValidation";
import { useResearchStrategyBoard } from "../lib/researchStrategyClient";

const file = path.resolve(
  process.env.CROSS_STACK_FIXTURES_DIR ??
    path.resolve(__dirname, "../../.cross-stack-fixtures"),
  "O_research_strategies.json",
);
const fixture = () => JSON.parse(readFileSync(file, "utf-8"));
const response = (body: unknown, status = 200) => ({
  ok: status === 200,
  json: async () => body,
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe.skipIf(!existsSync(file))(
  "strategy board — real Python publisher/builder/GET body",
  () => {
    it("accepts the exact snapshot unchanged and opens the published criterion explanation", async () => {
      const { body, http_status, _proof } = fixture();
      expect(http_status).toBe(200);
      expect(_proof.immutable_candidate_publisher_invoked).toBe(true);
      const before = JSON.stringify(body);
      expect(validateResearchStrategyBoard(body)).toBe(true);
      expect(JSON.stringify(body)).toBe(before);
      const fetcher = vi.fn().mockResolvedValue(response(body));
      vi.stubGlobal("fetch", fetcher);
      render(<ResearchStrategyBoardView />);
      await screen.findByText("4 ligne(s) publiée(s)");
      const row = screen
        .getAllByTestId("strategy-row")
        .find((r) => r.textContent?.includes("Momentum"))!;
      const criterion = within(row).getByRole("button", {
        name: /Momentum.*Performance.*Satisfait/,
      });
      fireEvent.click(criterion);
      const detail = screen.getByTestId("strategy-detail");
      expect(detail).toHaveFocus();
      expect(
        within(detail).getByText(/Verdict synthétique prépublié/),
      ).toBeInTheDocument();
      expect(
        within(detail).getByText(/N=13 · COMPLETE · LOW_SAMPLE/),
      ).toBeInTheDocument();
      expect(
        within(detail).getByText(
          /Étape du registre et activation runtime NOT_AVAILABLE/,
        ),
      ).toBeInTheDocument();
      fireEvent.click(
        within(detail).getByRole("button", { name: "Fermer la fiche" }),
      );
      expect(criterion).toHaveFocus();
      expect(fetcher.mock.calls[0][1].method).toBe("GET");
    });

    it("keeps positive PnL without verdict gray, filters only the published selection", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(response(fixture().body)),
      );
      render(<ResearchStrategyBoardView />);
      await screen.findByText("4 ligne(s) publiée(s)");
      const row = screen
        .getAllByTestId("strategy-row")
        .find((r) => r.textContent?.includes("PnL seul"))!;
      expect(
        within(row).getAllByRole("button", { name: /Non évalué/ }),
      ).toHaveLength(6);
      expect(within(row).getByText("NOT_AVAILABLE")).toBeInTheDocument();
      fireEvent.click(
        within(row).getByRole("button", { name: "PnL seul · sans verdict" }),
      );
      fireEvent.change(screen.getByLabelText("Type de candidat"), {
        target: { value: "CONFIG" },
      });
      expect(screen.queryByTestId("strategy-detail")).not.toBeInTheDocument();
      expect(screen.getByTestId("strategy-empty")).toHaveTextContent(
        "Aucun résultat pour ces filtres",
      );
      fireEvent.change(screen.getByLabelText("Type de candidat"), {
        target: { value: "ALL" },
      });
      const group = fixture().body.rows.find((r: any) => r.ranking).ranking
        .group_id;
      fireEvent.change(screen.getByLabelText("Classement comparable"), {
        target: { value: group },
      });
      expect(screen.getAllByTestId("strategy-row")).toHaveLength(2);
      expect(screen.getAllByTestId("strategy-row")[0]).toHaveTextContent(
        "Momentum",
      );
    });

    it.each([
      "duplicate-rank",
      "cohort",
      "missing-source",
      "unknown-status",
      "unsafe-n",
      "nonfinite",
      "fabricated-pass",
    ])("rejects %s at the frontend boundary", (attack) => {
      const body = fixture().body;
      const ranked = body.rows.filter((r: any) => r.ranking);
      const row = ranked[0];
      if (attack === "duplicate-rank")
        ranked[1].ranking.position = row.ranking.position;
      if (attack === "cohort") row.evaluation.baseline_id = "e".repeat(64);
      if (attack === "missing-source")
        body.source_artifacts = body.source_artifacts.slice(0, 1);
      if (attack === "unknown-status") row.criteria[0].status = "WINNER";
      if (attack === "unsafe-n")
        row.evaluation.metrics[0].n = Number.MAX_SAFE_INTEGER + 1;
      if (attack === "nonfinite") row.evaluation.metrics[0].value = Infinity;
      if (attack === "fabricated-pass")
        body.rows.find((r: any) => !r.evaluation).criteria[0].status = "PASS";
      expect(validateResearchStrategyBoard(body)).toBe(false);
    });

    it("replaces a successful result with an error after a failed refresh", async () => {
      vi.useFakeTimers();
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(response(fixture().body))
        .mockResolvedValue(
          response({ error_code: "RESEARCH_STRATEGY_BOARD_MISSING" }, 503),
        );
      vi.stubGlobal("fetch", fetcher);
      function Probe() {
        const state = useResearchStrategyBoard(100);
        return <p>{state.status}</p>;
      }
      render(<Probe />);
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(screen.getByText("success")).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
      expect(screen.getByText("error")).toBeInTheDocument();
    });
  },
);

describe("strategy board availability", () => {
  it.each([503, 200])(
    "never fabricates rows on missing/invalid payload (%s)",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            response({ error_code: "RESEARCH_STRATEGY_BOARD_MISSING" }, status),
          ),
      );
      render(<ResearchStrategyBoardView />);
      await screen.findByText(/Catalogue indisponible/);
      expect(screen.queryByTestId("strategy-row")).not.toBeInTheDocument();
    },
  );
  it("aborts the only pending request on unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, options) => {
        signal = options.signal;
        return new Promise(() => {});
      }),
    );
    const { unmount } = render(<ResearchStrategyBoardView />);
    await waitFor(() => expect(signal).toBeDefined());
    unmount();
    expect(signal!.aborted).toBe(true);
  });
});
