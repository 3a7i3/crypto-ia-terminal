import Plot from 'react-plotly.js'
import type { HealthData } from '../../types'
import { SVL, pctColor, pctIcon } from '../../types'

interface Props { data: HealthData }

const AXES = ['Observer', 'Dataset', 'Knowledge', 'Evidence', 'Capital', 'Drift']

function HealthBar({ label, pct, rawVal }: { label: string; pct: number; rawVal?: string }) {
  const color = pctColor(pct)
  return (
    <div className="metric-row">
      <div className="metric-label">{label}</div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="metric-val" style={{ color }}>{rawVal ?? `${pct.toFixed(0)}%`}</div>
      <div className="metric-icon">{pctIcon(pct)}</div>
    </div>
  )
}

export function HealthPanel({ data: h }: Props) {
  const driftScore = 100 - h.drift_pct
  const values = [h.observer_pct, h.dataset_pct, h.knowledge_pct, h.evidence_pct, h.capital_pct, driftScore]
  const avgHealth = values.reduce((a, b) => a + b, 0) / values.length
  const radarColor = pctColor(avgHealth)

  const radarTrace = {
    type: 'scatterpolar' as const,
    r: [...values, values[0]],
    theta: [...AXES, AXES[0]],
    fill: 'toself' as const,
    fillcolor: radarColor + '33',
    line: { color: radarColor, width: 2 },
    marker: { color: values.map(pctColor), size: 7 },
    hovertemplate: '%{theta}: %{r:.0f}%<extra></extra>',
  }

  const layout = {
    polar: {
      bgcolor: SVL.bgPanel,
      radialaxis: { range: [0, 100], visible: true, tickfont: { color: SVL.textDim, size: 9 }, gridcolor: SVL.border },
      angularaxis: { tickfont: { color: SVL.text, size: 10, family: 'monospace' }, gridcolor: SVL.border },
    },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    margin: { l: 40, r: 40, t: 10, b: 10 },
    showlegend: false,
    font: { family: 'monospace', color: SVL.text },
  }

  return (
    <div className="card">
      <div className="card-title">
        System Health &nbsp;
        <span className={`state-badge state-${h.system_state}`}>{h.system_state}</span>
        {h.trading_enabled
          ? <span style={{ marginLeft: 8, color: SVL.STRONG, fontSize: 11 }}>Trading ON</span>
          : <span style={{ marginLeft: 8, color: SVL.CONTRADICTED, fontSize: 11 }}>Trading OFF</span>}
      </div>

      <div className="row">
        <div className="col" style={{ maxWidth: 300, minHeight: 260 }}>
          <Plot
            data={[radarTrace]}
            layout={layout}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 260 }}
          />
        </div>
        <div className="col">
          <HealthBar label="Observer"  pct={h.observer_pct} />
          <HealthBar label="Dataset"   pct={h.dataset_pct} />
          <HealthBar label="Knowledge" pct={h.knowledge_pct} />
          <HealthBar label="Evidence"  pct={h.evidence_pct} />
          <HealthBar label="Capital"   pct={h.capital_pct} rawVal={`$${h.capital_usd.toFixed(0)}`} />
          <HealthBar label="~Drift"    pct={driftScore} rawVal={`${h.drift_pct.toFixed(0)}%↓`} />

          {h.top_root_cause && (
            <div style={{ marginTop: 12, padding: '6px 10px', background: SVL.bgCard, borderRadius: 4, fontSize: 11 }}>
              <span style={{ color: SVL.textDim }}>Top Root Cause: </span>
              <span style={{ color: SVL.DRIFT, fontWeight: 'bold' }}>
                {h.top_root_cause} — {h.top_root_cause_pct?.toFixed(0)}%
              </span>
            </div>
          )}

          {h.heartbeat_age_seconds != null && (
            <div style={{ marginTop: 8, fontSize: 10, color: SVL.textDim }}>
              Heartbeat: {(h.heartbeat_age_seconds / 60).toFixed(0)}m ago
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
