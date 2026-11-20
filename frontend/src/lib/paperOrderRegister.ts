// Local fixture contract. A future adapter must map authoritative source
// events to these recorded facts and supply a stable sequence per order.
export type PaperOrderEvent = Readonly<{
  orderId: string;
  sequence: number;
  at: string;
  kind: "decision" | "approved" | "refused" | "submitted" | "cancelled"
    | "executed" | "updated" | "closed" | "unresolved";
  decisionId?: string;
  positionId?: string;
  detail?: string;
}>;

export function buildPaperOrderRegister(events: readonly PaperOrderEvent[]) {
  const orders = new Map<string, PaperOrderEvent[]>();
  for (const event of events) {
    const timeline = orders.get(event.orderId) ?? [];
    timeline.push(event);
    orders.set(event.orderId, timeline);
  }

  return [...orders].sort(([a], [b]) => a.localeCompare(b)).map(([id, timeline]) => {
    timeline.sort((a, b) => a.sequence - b.sequence);
    return {
      id,
      timeline,
      lastEvent: timeline[timeline.length - 1],
      findBy: timeline.flatMap(({ decisionId, positionId }) =>
        [decisionId, positionId].filter((value): value is string => value !== undefined)),
    };
  });
}

export function findPaperOrders(register: ReturnType<typeof buildPaperOrderRegister>, query: string) {
  const needle = query.trim().toLowerCase();
  return register.filter(({ id, findBy }) =>
    [id, ...findBy].some(value => value.toLowerCase().includes(needle)));
}
