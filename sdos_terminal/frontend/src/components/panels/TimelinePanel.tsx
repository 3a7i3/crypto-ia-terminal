import { useState } from 'react'
import { useEndpoint } from '../../hooks/useEndpoint'
import { DecisionPacketTrace } from '../DecisionPacketTrace'
import type { TimelineData, TimelineEvent } from '../../types'
import { SVL } from '../../types'

const STATE_COLORS: Record<string, string> = {
  REJECTED:          SVL.CONTRADICTED,
  EXECUTED:          SVL.STRONG,
  EXECUTION_PENDING: SVL.OPERATIONAL,
  SIGNAL_GENERATED:  SVL.EMERGING,
  CLOSED:            SVL.ARCHIVED,
}

const REGIME_COLORS: Record<string, string> = {
  bull_trend:             SVL.STRONG,
  bear_trend:             SVL.CONTRADICTED,
  sideways:               SVL.EXPERIMENTAL,
  high_volatility_regime: SVL.DRIFT,
  RANGE:                  SVL.EXPERIMENTAL,
  VOLATILE:               SVL.DRIFT,
}

function stateColor(s: string) { return STATE_COLORS[s] ?? SVL.textDim }
function regimeColor(r: string) { return REGIME_COLORS[r] ?? SVL.textDim }

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      background: color + '18', border: `1px solid ${color}44`,
      borderRadius: 6, padding: '6px 14px',
    }}>
      <span style={{ color, fontFamily: 'monospace', fontWeight: 700, fontSize: 18 }}>{value}</span>
      <span style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 10 }}>{label}</span>
    </div>
  )
}

function EventRow({ event, expanded, onToggle }: {
  event: TimelineEvent
  expanded: boolean
  onToggle: () => void
}) {
  const sc = stateColor(event.lifecycle_state)
  const time = event.ts ? new Date(event.ts).toISOString().slice(11, 19) : '--:--:--'
  return (
    <div style={{ borderBottom: `1px solid ${SVL.border}` }}>
      <div
        onClick={onToggle}
        style={{
          display: 'grid',
          gridTemplateColumns: '52px 110px 90px 90px 90px 1fr 16px',
          gap: 6,
          padding: '5px 8px',
          alignItems: 'center',
          fontSize: 11,
          fontFamily: 'monospace',
          cursor: 'pointer',
        }}>
        <span style={{ color: SVL.textDim }}>{time}</span>
        <span style={{
          color: sc,
          background: sc + '18',
          border: `1px solid ${sc}44`,
          borderRadius: 3,
          padding: '1px 5px',
          fontSize: 10,
          textAlign: 'center',
        }}>
          {event.lifecycle_state}
        </span>
        <span style={{ color: SVL.text, fontWeight: 600 }}>{event.symbol}</span>
        <span style={{ color: regimeColor(event.regime), fontSize: 10 }}>{event.regime}</span>
        <span style={{ color: SVL.textDim, fontSize: 10 }}>{event.conviction}</span>
        <span style={{ color: SVL.textDim, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {event.reason || '—'}
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

export function TimelinePanel() {
  const { data, loading, error } = useEndpoint<TimelineData>('/api/timeline', 15_000)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (loading) return (
    <div className="card" style={{ color: SVL.textDim, fontFamily: 'monospace', fontSize: 12 }}>
      Loading timeline…
    </div>
  )

  if (error || !data) return (
    <div className="card" style={{ color: SVL.CONTRADICTED, fontFamily: 'monospace', fontSize: 12 }}>
      {error || 'No timeline data'}
    </div>
  )

  const tradeEvents = data.events.filter(e => e.event_category === 'TRADE')
  const hasTradeEvents = tradeEvents.length > 0
  const displayEvents = hasTradeEvents ? tradeEvents : data.events.slice(0, 50)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Stats row */}
      <div className="card">
        <div className="card-title">DECISION EVENT STREAM</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
          <StatChip label="TOTAL"    value={data.total_packets} color={SVL.EMERGING} />
          <StatChip label="TRADE"    value={data.n_trade}       color={SVL.OPERATIONAL} />
          <StatChip label="REJECTED" value={data.n_rejected}    color={SVL.CONTRADICTED} />
          <StatChip label="EXECUTED" value={data.n_executed}    color={SVL.STRONG} />
          <StatChip label="SYSTEM"   value={data.n_system}      color={SVL.textDim} />
        </div>
        {data.n_executed === 0 && (
          <div style={{
            marginTop: 10,
            color: SVL.DRIFT,
            fontSize: 11,
            fontFamily: 'monospace',
            background: SVL.DRIFT + '11',
            border: `1px solid ${SVL.DRIFT}44`,
            borderRadius: 4,
            padding: '6px 10px',
          }}>
            N=0 executed trades — VPS collecte les données (gate: N≥50)
          </div>
        )}
      </div>

      {/* Event list */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '52px 110px 90px 90px 90px 1fr',
          gap: 6,
          padding: '6px 8px',
          background: SVL.bgPanel,
          borderBottom: `1px solid ${SVL.border}`,
          fontSize: 10,
          fontFamily: 'monospace',
          color: SVL.textDim,
          fontWeight: 700,
        }}>
          <span>TIME</span>
          <span>STATE</span>
          <span>SYMBOL</span>
          <span>REGIME</span>
          <span>CONVICTION</span>
          <span>REASON</span>
        </div>
        {displayEvents.length === 0 ? (
          <div style={{ padding: 20, color: SVL.textDim, fontFamily: 'monospace', fontSize: 12, textAlign: 'center' }}>
            Aucun événement de trading — en attente de N≥1 signal valide
          </div>
        ) : (
          displayEvents.map(e => (
            <EventRow
              key={e.packet_id + e.ts}
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
