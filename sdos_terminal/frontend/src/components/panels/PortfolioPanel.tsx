import type { PortfolioData } from '../../types'
import { SVL, pctColor } from '../../types'

interface Props { data: PortfolioData }

function KPI({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="kpi-box">
      <div className="kpi-name">{label}</div>
      <div className="kpi-value" style={{ color: color ?? SVL.text }}>{value}</div>
    </div>
  )
}

export function PortfolioPanel({ data: p }: Props) {
  const wrColor = pctColor(p.win_rate_pct)
  const pfColor = pctColor(Math.min(p.profit_factor / 3 * 100, 100))
  const pnlColor = p.total_pnl_usd >= 0 ? SVL.STRONG : SVL.CONTRADICTED

  return (
    <div className="card">
      <div className="card-title">Portfolio</div>
      <div className="kpi-grid">
        <KPI label="TRADES"        value={String(p.n_trades)} />
        <KPI label="WIN RATE"      value={`${p.win_rate_pct.toFixed(1)}%`}   color={wrColor} />
        <KPI label="PROFIT FACTOR" value={p.profit_factor.toFixed(2)}         color={pfColor} />
        <KPI label="TOTAL PnL"     value={`$${p.total_pnl_usd >= 0 ? '+' : ''}${p.total_pnl_usd.toFixed(2)}`} color={pnlColor} />
        <KPI label="MAX DD"        value={`${p.max_drawdown_pct.toFixed(2)}%`} color={SVL.DRIFT} />
        <KPI label="SHARPE"        value={p.sharpe.toFixed(2)} />
        <KPI label="EXPECTANCY"    value={`${p.expectancy_pct >= 0 ? '+' : ''}${p.expectancy_pct.toFixed(3)}%`} />
        <KPI label="CAPITAL"       value={`$${p.capital_usd.toFixed(0)}`} />
      </div>
    </div>
  )
}
