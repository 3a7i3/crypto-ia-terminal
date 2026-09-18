import React from "react";
import { usePplComparison } from "../lib/pplComparisonClient";
import type {
  PplComparisonClass,
  PplComparisonRecord,
  PplComparisonSnapshot,
} from "../lib/pplComparisonTypes";
import "../ppl-comparison.css";

function raw(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "UNAVAILABLE";
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function relationLabel(row: PplComparisonRecord): string {
  return row.relation.replaceAll("_", " ");
}

function classTone(value: PplComparisonClass): string {
  if (value === "COMPARABLE") return "comparable";
  if (value === "PARTIAL") return "partial";
  return "unresolved";
}

const Metric: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({
  label,
  value,
  hint,
}) => (
  <div className="ppl-metric">
    <span>{label}</span>
    <strong>{value}</strong>
    {hint && <small>{hint}</small>}
  </div>
);

const ValueCell: React.FC<{
  side: "legacy" | "ppl";
  row: PplComparisonRecord;
}> = ({ side, row }) => {
  const source = row[side];
  return (
    <div className="ppl-value">
      <strong>{raw(source.value)}</strong>
      <span>{source.status}</span>
      <details>
        <summary>provenance</summary>
        <code>{source.provenance}</code>
      </details>
    </div>
  );
};

const ComparisonTable: React.FC<{
  rows: PplComparisonRecord[];
  title: string;
  subtitle: string;
}> = ({ rows, title, subtitle }) => (
  <section className="ppl-panel">
    <div className="ppl-section-head">
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <span>{rows.length} evidence rows</span>
    </div>

    {rows.length === 0 ? (
      <div className="ppl-empty">No comparison row is materialized for this scope.</div>
    ) : (
      <>
        <div className="ppl-table-wrap">
          <table className="ppl-table">
            <thead>
              <tr>
                <th>Fact</th>
                <th>Legacy PAPER</th>
                <th>PPL SHADOW</th>
                <th>Relation</th>
                <th>PPL − Legacy</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.comparison_id} data-testid="ppl-comparison-row">
                  <td>
                    <div className="ppl-fact">{row.domain}.{row.field}</div>
                    <span className={`ppl-class ppl-class-${classTone(row.classification)}`}>
                      {row.classification}
                    </span>
                    {row.note && <div className="ppl-note">{row.note}</div>}
                  </td>
                  <td><ValueCell side="legacy" row={row} /></td>
                  <td><ValueCell side="ppl" row={row} /></td>
                  <td>
                    <span className={`ppl-relation ppl-relation-${row.relation.toLowerCase()}`}>
                      {relationLabel(row)}
                    </span>
                    <div className="ppl-rule">{row.comparison_rule}</div>
                  </td>
                  <td className="ppl-delta">
                    {row.delta_ppl_minus_legacy === null
                      ? "NOT COMPARABLE"
                      : raw(row.delta_ppl_minus_legacy)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="ppl-card-list">
          {rows.map((row) => (
            <article className="ppl-comparison-card" key={row.comparison_id}>
              <div className="ppl-card-head">
                <div>
                  <div className="ppl-fact">{row.domain}.{row.field}</div>
                  {row.trade_id && <code>{row.trade_id}</code>}
                </div>
                <span className={`ppl-class ppl-class-${classTone(row.classification)}`}>
                  {row.classification}
                </span>
              </div>
              <div className="ppl-card-values">
                <div>
                  <span>Legacy</span>
                  <strong>{raw(row.legacy.value)}</strong>
                  <small>{row.legacy.status}</small>
                </div>
                <div>
                  <span>PPL</span>
                  <strong>{raw(row.ppl.value)}</strong>
                  <small>{row.ppl.status}</small>
                </div>
              </div>
              <div className="ppl-card-foot">
                <span className={`ppl-relation ppl-relation-${row.relation.toLowerCase()}`}>
                  {relationLabel(row)}
                </span>
                <span>
                  Δ {row.delta_ppl_minus_legacy === null
                    ? "N/A"
                    : raw(row.delta_ppl_minus_legacy)}
                </span>
              </div>
              {row.note && <p className="ppl-note">{row.note}</p>}
            </article>
          ))}
        </div>
      </>
    )}
  </section>
);

const TradeGroups: React.FC<{
  snapshot: PplComparisonSnapshot;
}> = ({ snapshot }) => {
  const records = new Map(snapshot.comparisons.map((row) => [row.comparison_id, row]));
  const groups = [...snapshot.positions, ...snapshot.closed_session];
  if (groups.length === 0) return null;

  return (
    <section className="ppl-panel">
      <div className="ppl-section-head">
        <div>
          <h3>Trade drill-down</h3>
          <p>Identity-linked evidence only; no symbol fallback or reconstructed finance.</p>
        </div>
      </div>
      <div className="ppl-trades">
        {groups.map((group) => (
          <details className="ppl-trade" key={`${group.trade_id}-${group.field_comparison_ids.join("-")}`}>
            <summary>
              <code>{group.trade_id}</code>
              <span>{group.relation.replaceAll("_", " ")}</span>
            </summary>
            <div className="ppl-trade-fields">
              {group.field_comparison_ids.map((id) => {
                const row = records.get(id);
                if (!row) return null;
                return (
                  <div className="ppl-trade-field" key={id}>
                    <span>{row.field}</span>
                    <code>{raw(row.legacy.value)}</code>
                    <span>⇄</span>
                    <code>{raw(row.ppl.value)}</code>
                    <span>{relationLabel(row)}</span>
                  </div>
                );
              })}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
};

export const PplComparisonView: React.FC = () => {
  const state = usePplComparison();

  if (state.status === "loading") {
    return <div className="ppl-panel ppl-state" data-testid="ppl-comparison-view">Loading PPL comparison…</div>;
  }

  if (state.status === "api_error") {
    return (
      <div className="ppl-panel ppl-state ppl-state-error" data-testid="ppl-comparison-view">
        <strong>WEB-02 comparison unavailable</strong>
        <span>{state.error.error_code ?? "UNKNOWN_ERROR"} · {state.error.error_message ?? "no detail"}</span>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div className="ppl-panel ppl-state ppl-state-error" data-testid="ppl-comparison-view">
        <strong>Comparator transport/contract failure</strong>
        <span>{state.message}</span>
      </div>
    );
  }

  const snapshot = state.snapshot;
  const aggregate = snapshot.comparisons.filter((row) => row.trade_id === null);
  const tradeRows = snapshot.comparisons.filter((row) => row.trade_id !== null);
  const stale = snapshot.freshness_classification === "STALE";

  return (
    <div className="ppl-stack" data-testid="ppl-comparison-view">
      <section className="ppl-panel ppl-hero">
        <div className="ppl-hero-row">
          <div>
            <div className="ppl-eyebrow">NON-AUTHORITATIVE SHADOW OBSERVATION</div>
            <h2>Legacy PAPER ⇄ PPL</h2>
            <p>
              Raw source values, explicit comparability, no auto-repair. Legacy PAPER remains authoritative.
            </p>
          </div>
          <div className="ppl-status-block">
            <span className={`ppl-shadow ppl-shadow-${snapshot.shadow_status.toLowerCase()}`}>
              {snapshot.shadow_status}
            </span>
            <span className={`ppl-freshness ${stale ? "stale" : "fresh"}`}>
              {snapshot.freshness_classification} · {Math.round(snapshot.snapshot_age_s)}s
            </span>
          </div>
        </div>

        <div className="ppl-provenance">
          <div><span>Epoch</span><code>{snapshot.paper_epoch_id ?? "UNRESOLVED"}</code></div>
          <div><span>Cycle</span><code>{snapshot.cycle}</code></div>
          <div><span>Source SHA</span><code>{snapshot.source_sha ?? "UNKNOWN"}</code></div>
          <div><span>Authority</span><code>{snapshot.authority}</code></div>
          <div><span>Legacy authority</span><code>{raw(snapshot.legacy_source.authority)}</code></div>
          <div><span>PPL authority</span><code>{raw(snapshot.ppl_source.authority)}</code></div>
        </div>
      </section>

      {!snapshot.comparison_available && (
        <div className="ppl-unavailable" data-testid="ppl-comparison-unavailable">
          Comparison withheld: {snapshot.comparison_unavailable_reason ?? "UNRESOLVED"}.
          No convergence state is inferred.
        </div>
      )}

      <section className="ppl-metrics" aria-label="Comparison evidence summary">
        <Metric label="Evidence rows" value={snapshot.summary.total} />
        <Metric label="Comparable" value={snapshot.summary.comparable} />
        <Metric label="Equal" value={snapshot.summary.equal} hint="relation, not quality score" />
        <Metric label="Different" value={snapshot.summary.different} hint="observable divergence" />
        <Metric label="Partial" value={snapshot.summary.partial} />
        <Metric label="Unresolved" value={snapshot.summary.unresolved} />
      </section>

      {snapshot.comparison_available && (
        <>
          <ComparisonTable
            rows={aggregate}
            title="Accounting & lifecycle"
            subtitle="Only producer-certified comparable facts receive a numeric delta."
          />
          {tradeRows.length > 0 && (
            <ComparisonTable
              rows={tradeRows}
              title="Per-trade evidence"
              subtitle="Trade identity is exact; unsupported finance remains PARTIAL or UNRESOLVED."
            />
          )}
          <TradeGroups snapshot={snapshot} />
        </>
      )}

      <section className="ppl-panel">
        <div className="ppl-section-head">
          <div>
            <h3>PPL event provenance</h3>
            <p>Durable SHADOW events are shown in stored sequence order.</p>
          </div>
          <span>{snapshot.ppl_events.length} events</span>
        </div>
        <div className="ppl-events">
          {snapshot.ppl_events.length === 0 ? (
            <div className="ppl-empty">No PPL event is exposed for the current SHADOW state.</div>
          ) : (
            snapshot.ppl_events.map((event) => (
              <div className="ppl-event" key={event.event_id}>
                <span>#{event.sequence}</span>
                <strong>{event.event_type}</strong>
                <code>{event.trade_id ?? "__EPOCH__"}</code>
                <time>{new Date(event.timestamp * 1000).toISOString()}</time>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
};
