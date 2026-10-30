import React from "react";
import { ageFr, fr, utcStampFr } from "../lib/presentationFr";
/** Source-provided age/freshness only. A file is never proof of activity. */
export const PublicationStamp: React.FC<{
  generatedAt: string;
  freshness?: string;
  age?: number | null;
  source: string;
  compact?: boolean;
}> = ({ generatedAt, freshness, age, source, compact = false }) => (
  <div className="publication-stamp">
    <span>{source}</span>
    <time dateTime={generatedAt}>{utcStampFr(generatedAt)}</time>
    <span>
      {!compact && (freshness ? fr(freshness) : "Fraîcheur non qualifiée")}
      {age != null
        ? `${compact ? "Âge publié " : " · âge publié "}${ageFr(age)}`
        : compact
          ? "Ancienneté non qualifiée"
          : ""}
    </span>
  </div>
);
