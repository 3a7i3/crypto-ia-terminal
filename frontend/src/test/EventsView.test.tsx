import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { EventsView } from "../views/EventsView";
import { validateEventCenter } from "../lib/eventCenter";

const dir = process.env.CROSS_STACK_FIXTURES_DIR ?? path.resolve(".cross-stack-fixtures");
const fixturePath = path.join(dir, "L_events.json");
// CI generates this through real Python producer/reader/API, never a golden payload.
const hasFixture = fs.existsSync(fixturePath);
if (process.env.CROSS_STACK_FIXTURES_DIR && !hasFixture) throw new Error("Missing generated Event Center fixture in cross-stack gate");
const fixture = () => JSON.parse(fs.readFileSync(fixturePath, "utf8")).body;
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe.skipIf(!hasFixture)("APP-EVENTS-01 Python -> API -> React", () => {
  it("accepts the real contract and displays distinct source coverage and unknown dates", async () => {
    const body = fixture();
    expect(validateEventCenter(body)).toBe(true);
    const fetchMock = vi.fn().mockResolvedValue(response(body));
    vi.stubGlobal("fetch", fetchMock);
    render(<EventsView />);
    await waitFor(() => expect(screen.getAllByTestId("event-row")).toHaveLength(8));
    expect(screen.getByTestId("events-view")).toHaveTextContent("Date inconnue · aucun fuseau déduit");
    expect(screen.getByTestId("events-view")).toHaveTextContent("1 corrections exclues");
    expect(screen.getByTestId("events-view")).toHaveTextContent("journal PPL complet hors périmètre");
    expect(screen.getByTestId("events-view")).not.toHaveTextContent("SECRET_CONTEXT");
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/events", { method: "GET", signal: expect.any(AbortSignal) });
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "ppl_lifecycles" } });
    expect(screen.getAllByTestId("event-row")).toHaveLength(5);
    fireEvent.change(screen.getByLabelText("Sévérité"), { target: { value: "CRITICAL" } });
    expect(screen.getByTestId("events-empty")).toHaveTextContent("filtres");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("works on the actual route even when the Advisor snapshot is missing", async () => {
    window.history.replaceState({}, "", "/paper-live/events");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(url => Promise.resolve(String(url).endsWith("/events") ? response(fixture()) : response({ error_code: "SNAPSHOT_MISSING" }, false))));
    render(<App />);
    await waitFor(() => expect(screen.getAllByTestId("event-row")).toHaveLength(8));
    expect(screen.getByTestId("events-view")).toHaveTextContent("Centre d’événements");
  });

  it("labels stale captures as historical and preserves source uncertainty", async () => {
    const body = fixture(); body.freshness_classification = "STALE"; body.snapshot_age_s = 100;
    body.sources[2].freshness_classification = "STALE"; body.sources[2].source_age_s = 100;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(body)));
    render(<EventsView />);
    await waitFor(() => expect(screen.getByTestId("events-view")).toHaveTextContent("Capture périmée : événements historiques, état actuel inconnu"));
    expect(screen.getByTestId("events-sources")).toHaveTextContent("Fraîcheur source : inconnue");
  });

  it.each([
    (x: any) => { x.authority = "PPL_AUTHORITY"; },
    (x: any) => { x.events.reverse(); },
    (x: any) => { x.events[0].context = { secret: "no" }; },
    (x: any) => { x.sources[0].published_count = true; },
    (x: any) => { x.events[0].occurred_at_utc = "2027-02-30T08:00:00Z"; },
    (x: any) => { x.events[1].event_id = x.events[0].event_id; },
    (x: any) => { x.sources[0].source_age_s = 0; },
    (x: any) => { x.events[0].symbol = "BTC/USDT"; },
  ])("rejects corrupted contract without fallback %#", async mutate => {
    const body = fixture(); mutate(body);
    expect(validateEventCenter(body)).toBe(false);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(body)));
    render(<EventsView />);
    await waitFor(() => expect(screen.getByTestId("events-view")).toHaveTextContent("EVENT_CENTER_CONTRACT_ERROR"));
    expect(screen.queryAllByTestId("event-row")).toHaveLength(0);
  });

  it("removes old events after a failed refresh and never overlaps requests", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(response(fixture())).mockResolvedValue(response({ error_code: "EVENT_CENTER_MISSING" }, false));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<EventsView />);
    await act(async () => {});
    expect(screen.getAllByTestId("event-row")).toHaveLength(8);
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.queryAllByTestId("event-row")).toHaveLength(0);
    expect(screen.getByTestId("events-view")).toHaveTextContent("EVENT_CENTER_MISSING");
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(40_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    let resolve!: (response: Response) => void;
    const slow = vi.fn().mockImplementation(() => new Promise<Response>(r => { resolve = r; }));
    vi.stubGlobal("fetch", slow);
    render(<EventsView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(9_000); });
    expect(slow).toHaveBeenCalledTimes(1);
    await act(async () => { resolve(response(fixture())); });
    expect(screen.getAllByTestId("event-row")).toHaveLength(8);
  });

  it("times out a hanging response and removes the previous successful capture", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(response(fixture())).mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<EventsView />);
    await act(async () => {});
    expect(screen.getAllByTestId("event-row")).toHaveLength(8);
    await act(async () => { await vi.advanceTimersByTimeAsync(29_999); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getAllByTestId("event-row")).toHaveLength(8);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.queryAllByTestId("event-row")).toHaveLength(0);
    expect(screen.getByTestId("events-view")).toHaveTextContent("EVENT_CENTER_TRANSPORT_ERROR");
    expect(fetchMock.mock.calls[1][1].signal.aborted).toBe(true);
  });
});

it("shows transport errors without an empty success or leaked exception", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("SECRET_CONNECTION")));
  render(<EventsView />);
  await waitFor(() => expect(screen.getByTestId("events-view")).toHaveTextContent("EVENT_CENTER_TRANSPORT_ERROR"));
  expect(screen.getByTestId("events-view")).not.toHaveTextContent("SECRET_CONNECTION");
  expect(screen.queryByTestId("events-empty")).toBeNull();
});
