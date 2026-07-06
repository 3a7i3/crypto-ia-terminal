import type { SystemData } from '../types'
import { pctColor } from '../types'

interface Props {
  data: SystemData | null
  connected: boolean
}

export function Header({ data, connected }: Props) {
  const h = data?.health
  const ts = h ? new Date(h.ts).toLocaleTimeString('en-GB', { hour12: false }) : '--:--:--'

  return (
    <header className="header">
      <span className="header-title">⬡ SDOS TERMINAL v1.0</span>

      {h && (
        <>
          <div className="header-kpi">
            State <span style={{ color: h.system_state === 'NORMAL' ? 'var(--strong)' : 'var(--contradicted)' }}>
              {h.system_state}
            </span>
          </div>
          <div className="header-kpi">
            N=<span>{h.n_trades}</span>
          </div>
          <div className="header-kpi">
            WR=<span style={{ color: pctColor(h.win_rate_pct) }}>{h.win_rate_pct.toFixed(0)}%</span>
          </div>
          <div className="header-kpi">
            PF=<span style={{ color: pctColor(Math.min(h.profit_factor / 3 * 100, 100)) }}>{h.profit_factor.toFixed(2)}</span>
          </div>
          <div className="header-kpi">
            Capital=<span>${h.capital_usd.toFixed(0)}</span>
          </div>
        </>
      )}

      <div className="header-status">
        <div className={`status-dot ${connected ? 'live' : ''}`} />
        <span style={{ color: connected ? 'var(--strong)' : 'var(--contradicted)' }}>
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
        <span style={{ color: 'var(--text-dim)', fontSize: '11px' }}>{ts} UTC</span>
      </div>
    </header>
  )
}
