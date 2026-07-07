import { useEffect, useState } from 'react'
import type { DecisionPacketData, TraceStepData } from '../types'
import { SVL } from '../types'

function statusColor(status: boolean | null): string {
  if (status === true) return SVL.STRONG
  if (status === false) return SVL.CONTRADICTED
  return SVL.textDim
}

function statusIcon(status: boolean | null): string {
  if (status === true) return '✓'
  if (status === false) return '✗'
  return '–'
}

function StepRow({ step }: { step: TraceStepData }) {
  const color = statusColor(step.status)
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '22px 24px 170px 1fr',
      gap: 8,
      alignItems: 'center',
      padding: '4px 0',
      fontSize: 11,
      fontFamily: 'monospace',
    }}>
      <span style={{ color: SVL.textDim }}>{step.step}</span>
      <span style={{ color, fontWeight: 700 }}>{statusIcon(step.status)}</span>
      <span style={{ color: SVL.text }}>{step.name}</span>
      <span style={{ color: SVL.textDim, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {step.detail}
      </span>
    </div>
  )
}

interface Props { packetId: string }

/** Chaîne causale complète d'une décision — GET /api/decision/{packet_id}.
 *  Partagé entre Reject Analyzer et Timeline pour éviter deux implémentations. */
export function DecisionPacketTrace({ packetId }: Props) {
  const [data, setData] = useState<DecisionPacketData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`/api/decision/${packetId}`)
      .then(r => {
        if (r.status === 404) throw new Error('Trace non disponible dans le RejectionStore')
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<DecisionPacketData>
      })
      .then(json => { if (!cancelled) { setData(json); setError(null) } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [packetId])

  if (loading) return (
    <div style={{ padding: '10px 4px', color: SVL.textDim, fontSize: 11, fontFamily: 'monospace' }}>
      Chargement de la trace…
    </div>
  )

  if (error || !data) return (
    <div style={{ padding: '10px 4px', color: SVL.textDim, fontSize: 11, fontFamily: 'monospace' }}>
      {error || 'Trace indisponible'}
    </div>
  )

  return (
    <div style={{
      padding: '10px 8px',
      background: SVL.bg,
      border: `1px solid ${SVL.border}`,
      borderRadius: 4,
      marginTop: 4,
    }}>
      <div style={{ marginBottom: 6 }}>
        {data.steps.map(s => <StepRow key={s.step} step={s} />)}
      </div>
      <div style={{
        marginTop: 8,
        paddingTop: 8,
        borderTop: `1px solid ${SVL.border}`,
        fontSize: 11,
        fontFamily: 'monospace',
        display: 'flex',
        gap: 16,
        flexWrap: 'wrap',
      }}>
        <span style={{ color: data.trade_allowed ? SVL.STRONG : SVL.CONTRADICTED, fontWeight: 700 }}>
          {data.trade_allowed ? 'AUTORISÉ' : `BLOQUÉ — ${data.first_blocker_label ?? '?'}`}
        </span>
        <span style={{ color: SVL.textDim }}>packet: {data.packet_id.slice(0, 8)}…</span>
        <span style={{ color: SVL.textDim }}>taille base: ${data.base_size_usd.toFixed(2)}</span>
      </div>
    </div>
  )
}
