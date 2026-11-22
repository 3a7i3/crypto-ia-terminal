/** FIXTURE_ONLY — vue synthétique. */
import { fetchHistory } from "../lib/historyClient";

export const HistoryPanel = () => { void fetchHistory(); return null; };
