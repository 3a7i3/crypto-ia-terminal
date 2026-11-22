import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CartographerMiniTerminal, parseHistory } from "../agents/invocationHistory";

const summary = { seen: { sources: 4, imports: 43, calls: 981 }, found: ["FLAG_SINGLE_PATH"],
  not_concluded: [{ path: "bbo_pilot.py", line: 1455, reason: "DYNAMIC_CALL_TARGET" }], write_templates: 7, limits: 9, errors: [] };
const item = (id: string, ended: string, sha = "67bdcc05aa") => ({ verdict: "VALID", reason: null, invocation_id: id,
  started_utc: ended, ended_utc: ended, state: "COMPLETED", result_status: "PARTIAL", analysed_sha: "e387318e00", content_sha256: sha, summary });
const raw = (items: unknown[]) => ({ contract: "cat.observation.invocation.v1", read_only: true, connection: "AVAILABLE", connection_reason: "historique lu", total: items.length, items });

describe("mini terminal", () => {
  it("une bulle par rapport, heure en bas, ordre chronologique", () => {
    const h = parseHistory(raw([item("b", "2026-11-22T07:00:00Z"), item("a", "2026-11-22T06:00:00Z")]));
    render(<CartographerMiniTerminal light="RED" lightReason="Inactif" history={h} />);
    const b = screen.getAllByTestId("miniterm-bubble");
    expect(b).toHaveLength(2);
    expect(b[0]).toHaveTextContent("FLAG_SINGLE_PATH");
    expect(b[1]).toHaveTextContent("Identique au précédent");
    expect(screen.getAllByTestId("miniterm-time")).toHaveLength(2);
  });
  it("gyrophare suit le voyant serveur", () => {
    for (const light of ["GREEN", "RED", "GRAY"] as const) {
      const { unmount } = render(<CartographerMiniTerminal light={light} lightReason="x" history={{ status: "LOADING" }} />);
      expect(screen.getByTestId("miniterm-giro")).toHaveAttribute("data-light", light);
      unmount();
    }
  });
  it("une panne de lecture n'est pas une liste vide ; une preuve invalide reste visible", () => {
    expect(parseHistory({}).status).toBe("UNREACHABLE");
    const h = parseHistory(raw([{ verdict: "INVALID", reason: "nom incohérent" }]));
    render(<CartographerMiniTerminal light="GRAY" lightReason="x" history={h} />);
    expect(screen.getByTestId("miniterm-bubble")).toHaveAttribute("data-verdict", "INVALID");
  });
});
