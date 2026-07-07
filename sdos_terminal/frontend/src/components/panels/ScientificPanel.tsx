import { useEndpoint } from '../../hooks/useEndpoint'
import type { ScientificData } from '../../types'
import { SVL, pctColor } from '../../types'

function WaitingCard({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="card" style={{ opacity: 0.6 }}>
      <div className="card-title">{label}</div>
      <div style={{ color: SVL.textDim, fontSize: 12, fontFamily: 'monospace', marginTop: 8 }}>
        {reason}
      </div>
    </div>
  )
}

function KpiRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: `1px solid ${SVL.border}` }}>
      <span style={{ color: SVL.textDim, fontSize: 11, fontFamily: 'monospace' }}>{label}</span>
      <span style={{ color: color || SVL.text, fontSize: 12, fontFamily: 'monospace', fontWeight: 600 }}>{value}</span>
    </div>
  )
}

function LevelBadge({ level }: { level: number }) {
  const colors: Record<number, string> = {
    0: SVL.CONTRADICTED,
    1: SVL.EXPERIMENTAL,
    2: SVL.EMERGING,
    3: SVL.OPERATIONAL,
    4: SVL.STRONG,
  }
  const color = colors[level] ?? SVL.textDim
  return (
    <span style={{
      display: 'inline-block',
      background: color + '22',
      color,
      border: `1px solid ${color}`,
      borderRadius: 4,
      padding: '2px 8px',
      fontSize: 11,
      fontFamily: 'monospace',
      fontWeight: 700,
    }}>
      L{level}
    </span>
  )
}

function CheckRow({ check }: { check: { id: string; status: string; score: number; duration_ms: number } }) {
  const ok = check.status === 'PASS'
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '3px 0' }}>
      <span style={{ color: ok ? SVL.STRONG : SVL.CONTRADICTED, fontSize: 10 }}>{ok ? '✓' : '✗'}</span>
      <span style={{ color: SVL.textDim, fontSize: 10, fontFamily: 'monospace', flex: 1 }}>{check.id}</span>
      <span style={{ color: ok ? SVL.STRONG : SVL.CONTRADICTED, fontSize: 10, fontFamily: 'monospace' }}>
        {check.score.toFixed(0)}%
      </span>
      <span style={{ color: SVL.textDim, fontSize: 9, fontFamily: 'monospace' }}>
        {check.duration_ms.toFixed(0)}ms
      </span>
    </div>
  )
}

export function ScientificPanel() {
  const { data, loading, error } = useEndpoint<ScientificData>('/api/scientific', 60_000)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading scientific state…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No scientific data'}
    </div>
  )

  const hasDecisions = data.n_decisions_production > 0
  const hasKnowledge = data.n_knowledge_entries > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Certification Card */}
      <div className="card">
        <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          OBSERVER CERTIFICATION
          <LevelBadge level={data.certification_level} />
        </div>
        <div style={{ marginTop: 12 }}>
          <KpiRow label="Level Name" value={data.certification_name} />
          <KpiRow label="Instrumentation Index (III)" value={`${data.iii.toFixed(1)}%`}
            color={pctColor(data.iii)} />
          <KpiRow label="Observer Certification Score (OCS)" value={`${data.ocs.toFixed(1)}%`}
            color={pctColor(data.ocs)} />
          <KpiRow label="Decisions in production" value={String(data.n_decisions_production)}
            color={data.n_decisions_production > 0 ? SVL.STRONG : SVL.textDim} />
          <KpiRow label="Certified at"
            value={data.last_cert_at ? new Date(data.last_cert_at).toISOString().replace('T', ' ').slice(0, 16) + ' UTC' : '—'} />
        </div>
        <div style={{
          marginTop: 12,
          padding: '8px 10px',
          background: SVL.EMERGING + '11',
          border: `1px solid ${SVL.EMERGING}44`,
          borderRadius: 4,
          color: SVL.EMERGING,
          fontSize: 11,
          fontFamily: 'monospace',
          lineHeight: 1.5,
        }}>
          {data.cert_decision}
        </div>
      </div>

      {/* IV-LIVE Checks */}
      {data.checks.length > 0 && (
        <div className="card">
          <div className="card-title">IV-LIVE CHECKS ({data.checks.filter(c => c.status === 'PASS').length}/{data.checks.length} PASS)</div>
          <div style={{ marginTop: 8 }}>
            {data.checks.map(c => <CheckRow key={c.id} check={c} />)}
          </div>
        </div>
      )}

      {/* DIP Knowledge State */}
      <div className="card">
        <div className="card-title">DIP KNOWLEDGE LAYER</div>
        <div style={{ marginTop: 12 }}>
          <KpiRow label="Knowledge entries" value={String(data.n_knowledge_entries)}
            color={hasKnowledge ? SVL.STRONG : SVL.textDim} />
          <KpiRow label="Active alerts" value={String(data.n_alerts_active)}
            color={data.n_alerts_active > 0 ? SVL.DRIFT : SVL.textDim} />
          <KpiRow label="Counterfactuals" value={String(data.n_counterfactuals)}
            color={data.n_counterfactuals > 0 ? SVL.OPERATIONAL : SVL.textDim} />
        </div>
        {!hasKnowledge && (
          <div style={{ color: SVL.textDim, fontSize: 11, fontFamily: 'monospace', marginTop: 10 }}>
            Waiting for N≥50 decisions to index first patterns…
          </div>
        )}
      </div>

      {/* Placeholder cards for future layers */}
      <WaitingCard
        label="HYPOTHESIS TRACKER — H1–H6"
        reason="Available after N≥50 decisions (current: 0). Gates: H1 sideways+RSI_oversold, H2 meta_layer effectiveness, H3 regime classifier accuracy."
      />
      <WaitingCard
        label="EVIDENCE TABLE"
        reason="Evidence records appear once DecisionPackets are indexed by DIP (FEATURE_DIP=true required on VPS)."
      />
      <WaitingCard
        label="KNOWLEDGE LIFECYCLE"
        reason="State transitions (EMERGING → OPERATIONAL → STRONG) require N≥100 per hypothesis category."
      />
    </div>
  )
}
