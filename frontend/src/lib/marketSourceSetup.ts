// M1-C2: presentation-only reading of an API error code. A source that this
// server does not configure or deploy is neither an empty market nor a zero:
// it is shown apart from read, transport and contract failures. No retry,
// no fallback source, no change to any client or API contract.
export type MarketSourceSetup = "NOT_CONFIGURED" | "NOT_DEPLOYED";

export function marketSourceSetup(code: string | null | undefined): MarketSourceSetup | null {
  if (!code) return null;
  if (code === "NOT_CONFIGURED" || code.endsWith("_NOT_CONFIGURED")) return "NOT_CONFIGURED";
  if (code === "SOURCE_NOT_DEPLOYED") return "NOT_DEPLOYED";
  return null;
}
