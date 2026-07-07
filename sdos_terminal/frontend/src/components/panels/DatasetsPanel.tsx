import { useEndpoint } from '../../hooks/useEndpoint'
import type { DatasetsData, CertRecord } from '../../types'
import { SVL, pctColor } from '../../types'

const LEVEL_COLORS: Record<number, string> = {
  0: SVL.CONTRADICTED,
  1: SVL.EXPERIMENTAL,
  2: SVL.EMERGING,
  3: SVL.OPERATIONAL,
  4: SVL.STRONG,
}

function levelColor(n: number) { return LEVEL_COLORS[n] ?? SVL.textDim }

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: SVL.border, borderRadius: 2 }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
      <span style={{ color, fontFamily: 'monospace', fontSize: 11, minWidth: 38, textAlign: 'right' }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  )
}

function CertCard({ cert, isLatest }: { cert: CertRecord; isLatest: boolean }) {
  const lc = levelColor(cert.level)
  const passed = cert.checks.filter(c => c.status === 'PASS').length
  const total = cert.checks.length
  const date = new Date(cert.generated_at).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'

  return (
    <div className="card" style={{ border: isLatest ? `1px solid ${lc}66` : undefined }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{
          background: lc + '22', border: `1px solid ${lc}`,
          color: lc, fontFamily: 'monospace', fontWeight: 700,
          borderRadius: 4, padding: '2px 10px', fontSize: 12,
        }}>
          L{cert.level}
        </div>
        <div>
          <div style={{ color: SVL.text, fontFamily: 'monospace', fontWeight: 600, fontSize: 13 }}>
            {cert.level_name}
            {isLatest && <span style={{ color: SVL.EMERGING, fontSize: 10, marginLeft: 8 }}>LATEST</span>}
          </div>
          <div style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10 }}>{date}</div>
        </div>
        <div style={{ marginLeft: 'auto', fontFamily: 'monospace', fontSize: 10, color: SVL.textDim }}>
          {cert.certification_id}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <div>
          <div style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10, marginBottom: 3 }}>III</div>
          <ProgressBar pct={cert.iii} color={pctColor(cert.iii)} />
        </div>
        <div>
          <div style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10, marginBottom: 3 }}>OCS</div>
          <ProgressBar pct={cert.ocs} color={pctColor(cert.ocs)} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <span style={{ background: SVL.STRONG + '18', color: SVL.STRONG, border: `1px solid ${SVL.STRONG}44`, borderRadius: 3, padding: '2px 8px', fontFamily: 'monospace', fontSize: 10 }}>
          {cert.n_live_passed} PASS
        </span>
        {cert.n_live_failed > 0 && (
          <span style={{ background: SVL.CONTRADICTED + '18', color: SVL.CONTRADICTED, border: `1px solid ${SVL.CONTRADICTED}44`, borderRadius: 3, padding: '2px 8px', fontFamily: 'monospace', fontSize: 10 }}>
            {cert.n_live_failed} FAIL
          </span>
        )}
        <span style={{ background: SVL.EMERGING + '11', color: SVL.EMERGING, border: `1px solid ${SVL.EMERGING}33`, borderRadius: 3, padding: '2px 8px', fontFamily: 'monospace', fontSize: 10 }}>
          N={cert.n_decisions_production} decisions
        </span>
        <span style={{ background: SVL.textDim + '18', color: SVL.textDim, borderRadius: 3, padding: '2px 8px', fontFamily: 'monospace', fontSize: 10 }}>
          {passed}/{total} checks
        </span>
      </div>

      {cert.decision && (
        <div style={{
          color: SVL.EMERGING, fontFamily: 'monospace', fontSize: 10,
          background: SVL.EMERGING + '0D', border: `1px solid ${SVL.EMERGING}33`,
          borderRadius: 4, padding: '6px 10px', lineHeight: 1.5,
        }}>
          {cert.decision}
        </div>
      )}
    </div>
  )
}

export function DatasetsPanel() {
  const { data, loading, error } = useEndpoint<DatasetsData>('/api/datasets', 60_000)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading certifications…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No certification data'}
    </div>
  )

  const lc = levelColor(data.latest_level)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Summary */}
      <div className="card">
        <div className="card-title">OBSERVER CERTIFICATION HISTORY</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, alignItems: 'center' }}>
          <div style={{
            background: lc + '22', border: `2px solid ${lc}`,
            color: lc, fontFamily: 'monospace', fontWeight: 700,
            borderRadius: 6, padding: '6px 16px', fontSize: 20,
          }}>
            L{data.latest_level}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <div style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10, marginBottom: 3 }}>III</div>
                <ProgressBar pct={data.latest_iii} color={pctColor(data.latest_iii)} />
              </div>
              <div>
                <div style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10, marginBottom: 3 }}>OCS</div>
                <ProgressBar pct={data.latest_ocs} color={pctColor(data.latest_ocs)} />
              </div>
            </div>
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 11, color: SVL.textDim, textAlign: 'right' }}>
            {data.certifications.length} cert{data.certifications.length !== 1 ? 's' : ''}
          </div>
        </div>

        {/* Next gate */}
        <div style={{
          marginTop: 12, color: SVL.DRIFT, fontFamily: 'monospace', fontSize: 11,
          background: SVL.DRIFT + '0D', border: `1px solid ${SVL.DRIFT}33`,
          borderRadius: 4, padding: '6px 10px',
        }}>
          Next gate → L3 : activer FEATURE_DIP=true sur VPS + N≥50 decisions indexées
        </div>
      </div>

      {/* Certification cards */}
      {data.certifications.map((c, i) => (
        <CertCard key={c.certification_id} cert={c} isLatest={i === 0} />
      ))}

      {data.certifications.length === 0 && (
        <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12, textAlign: 'center', padding: 32 }}>
          Aucune certification enregistrée
        </div>
      )}
    </div>
  )
}
