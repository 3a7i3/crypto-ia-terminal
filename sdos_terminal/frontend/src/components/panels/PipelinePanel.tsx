import type { PipelineData } from '../../types'
import { SVL, pctColor } from '../../types'

interface Props { data: PipelineData }

const LAYERS = [
  { key: 'authority',     label: 'Auth' },
  { key: 'market',        label: 'Market' },
  { key: 'meta_strategy', label: 'Meta' },
  { key: 'portfolio',     label: 'Portf.' },
  { key: 'risk',          label: 'Risk' },
  { key: 'execution',     label: 'Exec.' },
]

export function PipelinePanel({ data: p }: Props) {
  const nSig = p.n_signals || 1
  const refusal = p.refusal_breakdown || {}

  const layers = LAYERS.map(({ key, label }) => {
    const refused = refusal[key] ?? 0
    const passPct = refused > 0 ? Math.max(0, 100 - (refused / nSig * 100)) : 100
    return { label, passPct, refused, color: pctColor(passPct) }
  })

  const topRegime = p.regime_distribution
    ? Object.entries(p.regime_distribution).sort((a, b) => b[1] - a[1])[0]
    : null
  const totalRegime = Object.values(p.regime_distribution || {}).reduce((a, b) => a + b, 0) || 1

  return (
    <div className="card">
      <div className="card-title">Decision Pipeline — Cycle {p.cycle}</div>

      <div className="pipeline-layers">
        {layers.map(({ label, passPct, refused, color }) => (
          <div className="pipeline-layer" key={label}>
            <div className="layer-pct" style={{ color }}>{passPct.toFixed(0)}%</div>
            <div className="layer-bar-wrap">
              <div
                className="layer-bar"
                style={{ height: `${passPct}%`, background: color + 'BB' }}
              />
            </div>
            <div className="layer-name">{label}</div>
            {refused > 0 && (
              <div style={{ fontSize: 9, color: SVL.CONTRADICTED }}>−{refused}</div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 10, fontSize: 11, color: SVL.textDim, display: 'flex', gap: 16 }}>
        <span>Signals: <strong style={{ color: SVL.text }}>{p.n_signals}</strong></span>
        <span>Traded: <strong style={{ color: SVL.STRONG }}>{p.n_traded}</strong></span>
        <span>Refused: <strong style={{ color: SVL.CONTRADICTED }}>{p.n_refused}</strong></span>
        <span>Pass: <strong style={{ color: pctColor(p.pass_rate_pct) }}>{p.pass_rate_pct.toFixed(1)}%</strong></span>
        {topRegime && (
          <span style={{ marginLeft: 'auto' }}>
            Regime: <strong style={{ color: SVL.EMERGING }}>
              {topRegime[0]} {(topRegime[1] / totalRegime * 100).toFixed(0)}%
            </strong>
          </span>
        )}
      </div>
    </div>
  )
}
