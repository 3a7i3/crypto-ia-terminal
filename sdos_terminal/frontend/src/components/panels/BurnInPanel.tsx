import { useEndpoint } from '../../hooks/useEndpoint'
import type { BurnInData, RegretInvestigationData } from '../../types'
import { SVL, pctColor } from '../../types'

function ProgressRow({ label, value, min }: { label: string; value: number; min: number }) {
  const pct = min > 0 ? Math.min(100, (value / min) * 100) : 0
  const color = pctColor(pct)
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="metric-val" style={{ color }}>{value}/{min}</span>
      <span className="metric-icon">{pct >= 100 ? '✅' : ''}</span>
    </div>
  )
}

function BreakdownList({ title, counts, total }: { title: string; counts: Record<string, number>; total: number }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 10, color: SVL.textDim, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {title}
      </div>
      {entries.map(([key, count]) => {
        const pct = total > 0 ? (count / total) * 100 : 0
        const dominant = pct >= 80
        return (
          <div className="metric-row" key={key}>
            <span className="metric-label" style={{ width: 130 }}>{key}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${pct}%`, background: dominant ? SVL.CONTRADICTED : SVL.EMERGING }} />
            </div>
            <span className="metric-val" style={{ width: 90 }}>{count} ({pct.toFixed(0)}%)</span>
          </div>
        )
      })}
    </div>
  )
}

function RegretInvestigationSection() {
  const { data, loading, error } = useEndpoint<RegretInvestigationData>('/api/regret?regret_type=MISSED_WIN', 60_000)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading regret investigation…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No regret data'}
    </div>
  )

  const weeks = Object.entries(data.by_week)
  const maxWeek = Math.max(1, ...weeks.map(([, c]) => c))
  const topWeek = [...weeks].sort((a, b) => b[1] - a[1])[0]
  const topWeekPct = topWeek && data.n_total > 0 ? (topWeek[1] / data.n_total) * 100 : 0

  return (
    <div className="card">
      <div className="card-title">REGRET INVESTIGATION — {data.regret_type} ({data.n_total})</div>

      {data.n_total === 0 ? (
        <div style={{ color: SVL.textDim, fontSize: 11 }}>Aucun enregistrement pour ce type.</div>
      ) : (
        <>
          <BreakdownList title="Par couche bloqueuse" counts={data.by_layer} total={data.n_total} />
          <BreakdownList title="Par régime" counts={data.by_regime} total={data.n_total} />
          <BreakdownList title="Par score" counts={data.by_score_bin} total={data.n_total} />

          <div style={{ fontSize: 10, color: SVL.textDim, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Par semaine ({weeks.length} semaines · {data.first_evaluated_at?.slice(0, 10)} → {data.last_evaluated_at?.slice(0, 10)})
          </div>
          <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 50 }}>
            {weeks.map(([week, count]) => (
              <div key={week} title={`${week}: ${count}`} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                <div style={{
                  width: '100%',
                  height: `${Math.max(4, (count / maxWeek) * 40)}px`,
                  background: count === topWeek?.[1] ? SVL.CONTRADICTED : SVL.EMERGING,
                  borderRadius: 2,
                }} />
                <span style={{ fontSize: 8, color: SVL.textDim }}>{week.slice(-3)}</span>
              </div>
            ))}
          </div>

          {topWeekPct >= 40 && (
            <div style={{ marginTop: 8, fontSize: 11, color: SVL.DRIFT }}>
              ⚠️ {topWeekPct.toFixed(0)}% concentrés sur {topWeek?.[0]} — possible artefact ponctuel (regime detector ?) plutôt qu'un biais structurel constant.
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function BurnInPanel() {
  const { data, loading, error } = useEndpoint<BurnInData>('/api/burnin', 30_000)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading burn-in…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No burn-in data'}
    </div>
  )

  const goColor = data.go_no_go === 'GO' ? SVL.STRONG : SVL.CONTRADICTED

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-title">BURN-IN — Seuils statisticien (CLAUDE.md)</div>

        <ProgressRow label="Trades"       value={data.trades_count}       min={data.trades_min} />
        <ProgressRow label="Winners"      value={data.wins}               min={data.wins_min} />
        <ProgressRow label="Losers"       value={data.losses}             min={data.losses_min} />
        <ProgressRow label="Missed-Win"   value={data.missed_win_count}   min={data.missed_win_min} />
        <ProgressRow label="Good-Refusal" value={data.good_refusal_count} min={data.good_refusal_min} />

        <div style={{ marginTop: 10, fontSize: 10, color: SVL.textDim }}>
          Par régime ≥ {data.per_regime_min} · Par couche bloqueuse ≥ {data.per_layer_min} — non instrumenté
        </div>
      </div>

      <div className="card">
        <div className="card-title">CALIBRATION</div>
        <div style={{ display: 'flex', gap: 24, fontSize: 12, flexWrap: 'wrap' }}>
          <span>
            État: <strong style={{ color: data.calibration_locked ? SVL.CONTRADICTED : SVL.STRONG }}>
              {data.calibration_locked ? 'LOCKED' : 'UNLOCKED'}
            </strong>
          </span>
          <span>
            CRI: <strong style={{ color: SVL.textDim }}>
              {data.cri === null ? `Unknown (gate ≥ ${data.cri_min})` : `${data.cri}/100`}
            </strong>
          </span>
          <span>
            Go/No-Go: <strong style={{ color: goColor }}>{data.go_no_go}</strong>
          </span>
          <span>
            WR: <strong style={{ color: SVL.text }}>{data.win_rate_pct.toFixed(1)}%</strong>
          </span>
          <span>
            PF: <strong style={{ color: SVL.text }}>{data.profit_factor.toFixed(2)}</strong>
          </span>
        </div>
      </div>

      {(data.blockers.length > 0 || data.warnings.length > 0) && (
        <div className="card">
          <div className="card-title">BLOCKERS / WARNINGS</div>
          {data.blockers.map((b, i) => (
            <div key={`b${i}`} style={{ fontSize: 11, color: SVL.CONTRADICTED, padding: '3px 0' }}>⛔ {b}</div>
          ))}
          {data.warnings.map((w, i) => (
            <div key={`w${i}`} style={{ fontSize: 11, color: SVL.DRIFT, padding: '3px 0' }}>⚠️ {w}</div>
          ))}
        </div>
      )}

      <RegretInvestigationSection />

      <div style={{ fontSize: 10, color: SVL.textDim, textAlign: 'right' }}>
        Généré: {data.generated_at ? new Date(data.generated_at).toISOString().slice(0, 16).replace('T', ' ') : '—'} UTC
      </div>
    </div>
  )
}
