// P6-R1-RV01 — the Spot Radar contract publishes three distinct counts, and the
// universe gate adds a fourth. None of them stands for another:
//   selected_instruments  instruments the pilot selected (observed + unavailable);
//   observed_instruments  instruments the collector actually observed;
//   rows.length           rows returned in this publication (== returned_count ≤ observed);
//   admitted              returned rows admitted by the common universe, known only
//                         once the universe is VERIFIED or VERIFIED_EMPTY (UNKNOWN ≠ 0).
// This module only names and formats the published values; it computes nothing new.
import type { RadarScanner } from "./spotRadarClient";

export interface RadarCounts { selected: number; observed: number; returned: number }

export const radarCounts = (d: Pick<RadarScanner, "selected_instruments" | "observed_instruments" | "rows">): RadarCounts =>
  ({ selected: d.selected_instruments, observed: d.observed_instruments, returned: d.rows.length });

const n = (count: number, singular: string, plural: string) => `${count} ${count > 1 ? plural : singular}`;

/** "27 observés sur 30 sélectionnés · 22 retournés" */
export const radarCountsLabel = (c: RadarCounts) =>
  `${n(c.observed, "observé", "observés")} sur ${n(c.selected, "sélectionné", "sélectionnés")} · ${n(c.returned, "retourné", "retournés")}`;

export const admittedLabel = (count: number) => n(count, "admis", "admis");
export const shownLabel = (count: number) => n(count, "affiché", "affichés");
