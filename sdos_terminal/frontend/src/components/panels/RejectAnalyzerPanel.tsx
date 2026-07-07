import { useState } from 'react'
import { useEndpoint } from '../../hooks/useEndpoint'
import { DecisionPacketTrace } from '../DecisionPacketTrace'
import type { RejectionsData, RejectionEventData } from '../../types'
import { SVL } from '../../types'

const LAYER_LABELS: Record<string, string> = {
  authority: 'Authority',
  gate: 'Gate',
  meta_strategy: 'Meta',
  conviction: 'Conviction',
  no_trade: 'No-Trade',
  portfolio: 'Portfolio',
  mistake_memory: 'MistakeMemory',
  executive_override: 'ExecOverride',
  threat_radar: 'ThreatRadar',
  arbitrator: 'Arbitrator',
  decision_packet: 'DecisionPacket',
  protection: 'Protection',
}

function layerLabel(key: string): string { return LAYER_LABELS[key] ?? key }

function BreakdownBar({ layer, count, pct }: { layer: string; count: number; pct: number }) {
  const color = pctToColor(pct)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0' }}>
      <span style={{ width: 110, fontSize: 11, color: SVL.text, flexShrink: 0 }}>{layerLabel(layer)}</span>
      <div className="bar-track" style={{ flex: 1 }}>
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span style={{ width: 70, textAlign: 'right', fontSize: 11, color, fontWeight: 700 }}>
        {pct.toFixed(0)}%
      </span>
      <span style={{ width: 34, textAlign: 'right', fontSize: 10, color: SVL.textDim }}>×{count}</span>
    </div>
  )
}

function pctToColor(pct: number): string {
  if (pct >= 50) return SVL.CONTRADICTED
  if (pct >= 25) return SVL.DRIFT
  if (pct >= 10) return SVL.OPERATIONAL
  return SVL.EMERGING
}

function RejectRow({ event, expanded, onToggle }: {
  event: RejectionEventData
  expanded: boolean
  onToggle: () => void
}) {
  const time = event.ts ? new Date(event.ts).toISOString().slice(11, 19) : '--:--:--'
  return (
    <div style={{ borderBottom: `1px solid ${SVL.border}` }}>
      <div
        onClick={onToggle}
        style={{
          display: 'grid',
          gridTemplateColumns: '70px 90px 44px 130px 1fr 16px',
          gap: 8,
          padding: '6px 8px',
          alignItems: 'center',
          fontSize: 11,
          fontFamily: 'monospace',
          cursor: 'pointer',
        }}
      >
        <span style={{ color: SVL.textDim }}>{time}</span>
        <span style={{ color: SVL.text, fontWeight: 600 }}>{event.symbol}</span>
        <span style={{ color: SVL.textDim }}>{event.side}</span>
        <span style={{
          color: event.trade_allowed ? SVL.STRONG : SVL.CONTRADICTED,
          fontSize: 10,
        }}>
          {event.trade_allowed ? 'AUTORISÉ' : layerLabel((event.first_blocker || '').split('(')[0])}
        </span>
        <span style={{ color: SVL.textDim, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {event.first_blocker_label || '—'}
        </span>
        <span style={{ color: SVL.textDim, textAlign: 'center' }}>{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div style={{ padding: '0 8px 10px' }}>
          <DecisionPacketTrace packetId={event.packet_id} />
        </div>
      )}
    </div>
  )
}

export function RejectAnalyzerPanel() {
  const { data, loading, error } = useEndpoint<RejectionsData>('/api/rejections?days=1&limit=30', 20_000)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading rejections…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No rejection data'}
    </div>
  )

  const layers = Object.entries(data.by_layer).sort((a, b) => b[1] - a[1])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-title">REJECT ANALYZER — {data.days_covered[0]} ({data.n_entries} signaux)</div>
        {layers.length === 0 ? (
          <div style={{ color: SVL.textDim, fontSize: 11, fontFamily: 'monospace' }}>
            Aucun rejet enregistré pour cette période.
          </div>
        ) : (
          <div>
            {layers.map(([layer, count]) => (
              <BreakdownBar key={layer} layer={layer} count={count} pct={data.by_layer_pct[layer] ?? 0} />
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '12px 14px 0' }} className="card-title">
          LAST REJECTS ({data.recent.length})
        </div>
        {data.recent.length === 0 ? (
          <div style={{ padding: 20, color: SVL.textDim, fontFamily: 'monospace', fontSize: 12, textAlign: 'center' }}>
            Aucun événement récent
          </div>
        ) : (
          data.recent.map(e => (
            <RejectRow
              key={e.packet_id}
              event={e}
              expanded={expandedId === e.packet_id}
              onToggle={() => setExpandedId(expandedId === e.packet_id ? null : e.packet_id)}
            />
          ))
        )}
      </div>
    </div>
  )
}
