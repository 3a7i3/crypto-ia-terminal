import type { PaperOrderEvent } from "../lib/paperOrderRegister";

type Step = Omit<PaperOrderEvent, "orderId" | "sequence" | "at">;

function scenario(number: number, steps: Step[]): PaperOrderEvent[] {
  return steps.map((step, index) => ({
    ...step,
    orderId: `TEST-ORD-${number}`,
    sequence: index + 1,
    at: new Date(Date.UTC(2026, 0, 1, number, index)).toISOString(),
  }));
}

export const paperOrderEvents = [
  ...scenario(1, [
    { kind: "decision", decisionId: "TEST-DEC-1" },
    { kind: "refused", detail: "Limite de risque dépassée." },
  ]),
  ...scenario(2, [
    { kind: "decision", decisionId: "TEST-DEC-2" },
    { kind: "approved" },
    { kind: "submitted" },
    { kind: "cancelled", detail: "Annulation avant toute exécution." },
  ]),
  ...scenario(3, [
    { kind: "decision", decisionId: "TEST-DEC-3" },
    { kind: "approved" },
    { kind: "submitted" },
    { kind: "executed", positionId: "TEST-POS-3" },
    { kind: "updated", positionId: "TEST-POS-3", detail: "Stop relevé." },
    { kind: "closed", positionId: "TEST-POS-3" },
  ]),
  ...scenario(4, [
    { kind: "decision", decisionId: "TEST-DEC-4" },
    { kind: "approved" },
    { kind: "submitted" },
    { kind: "executed", positionId: "TEST-POS-4" },
    { kind: "unresolved", positionId: "TEST-POS-4", detail: "Sortie non documentée." },
  ]),
];
