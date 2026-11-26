// P6-GOV-02 : les refus du serveur (identité, taille, débit) sont nommés ; « inchangé » n'est pas une erreur.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { REFUSAL, useAgentSchedule } from "../agents/agentSchedule";

const URL = "/api/operator/v1/agent-invocations/repository-cartographer/schedule";

function stubPost(status: number) {
  const calls: { method: string; headers: Record<string, string> }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, headers: (init?.headers ?? {}) as Record<string, string> });
    if (method === "POST") return new Response("{}", { status });
    return new Response(JSON.stringify({ requested: null, applied: "1h", next_utc: null, connection: "AVAILABLE" }), { status: 200 });
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("refus du programmateur", () => {
  it.each([401, 403, 413, 415, 422, 429, 503])("HTTP %i → message explicite", async (status) => {
    stubPost(status);
    const { result } = renderHook(() => useAgentSchedule(true, 60_000, URL));
    await act(async () => { await result.current.request("10min"); });
    expect(result.current.error).toBe(REFUSAL[status]);
  });

  it("202 et 200 (inchangé) ne sont pas des erreurs", async () => {
    for (const status of [202, 200]) {
      stubPost(status);
      const { result, unmount } = renderHook(() => useAgentSchedule(true, 60_000, URL));
      await act(async () => { await result.current.request("1h"); });
      expect(result.current.error).toBeNull();
      unmount();
    }
  });

  it("le navigateur n'envoie jamais d'identité : elle vient du réseau de l'opérateur", async () => {
    const calls = stubPost(202);
    const { result } = renderHook(() => useAgentSchedule(true, 60_000, URL));
    await act(async () => { await result.current.request("1h"); });
    const post = calls.find((c) => c.method === "POST");
    expect(post).toBeDefined();
    expect(Object.keys(post!.headers).map((k) => k.toLowerCase()).sort()).toEqual(["content-type", "x-cat-operator"]);
  });

  it("statut inconnu : code HTTP affiché, pas de succès inventé", async () => {
    stubPost(500);
    const { result } = renderHook(() => useAgentSchedule(true, 60_000, URL));
    await act(async () => { await result.current.request("1h"); });
    expect(result.current.error).toBe("demande refusée (HTTP 500)");
  });
});
