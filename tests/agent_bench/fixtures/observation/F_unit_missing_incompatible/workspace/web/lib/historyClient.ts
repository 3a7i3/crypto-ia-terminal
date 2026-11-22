/** FIXTURE_ONLY — client synthétique. */
export const HISTORY_ENDPOINT = "/api/v1/fix-history";
export interface History { schema_version: "fix-history/1.0.0"; generated_at_utc: string }

export async function fetchHistory(): Promise<History> {
  const response = await fetch(HISTORY_ENDPOINT, { method: "GET", cache: "no-store" });
  return (await response.json()) as History;
}
