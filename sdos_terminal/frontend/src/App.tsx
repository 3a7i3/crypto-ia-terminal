import { useState } from 'react'
import { useSDOS } from './hooks/useSDOS'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { HealthPanel } from './components/panels/HealthPanel'
import { PipelinePanel } from './components/panels/PipelinePanel'
import { PortfolioPanel } from './components/panels/PortfolioPanel'
import { ScientificPanel } from './components/panels/ScientificPanel'
import { TimelinePanel } from './components/panels/TimelinePanel'
import { DatasetsPanel } from './components/panels/DatasetsPanel'
import { RejectAnalyzerPanel } from './components/panels/RejectAnalyzerPanel'
import { BurnInPanel } from './components/panels/BurnInPanel'

type Page = 'dashboard' | 'trading' | 'scientific' | 'health' | 'rejects' | 'timeline' | 'datasets' | 'config' | 'burnin'

function LoadingState() {
  return (
    <div style={{ padding: 32, color: 'var(--text-dim)', fontFamily: 'monospace' }}>
      <div style={{ fontSize: 13, marginBottom: 8 }}>Connecting to SDOS Data API…</div>
      <div style={{ fontSize: 11 }}>GET /api/system</div>
    </div>
  )
}

function DashboardPage({ data }: { data: NonNullable<ReturnType<typeof useSDOS>['data']> }) {
  return (
    <>
      <HealthPanel data={data.health} />
      <PipelinePanel data={data.pipeline} />
      <PortfolioPanel data={data.portfolio} />
    </>
  )
}

function HealthPage({ data }: { data: NonNullable<ReturnType<typeof useSDOS>['data']> }) {
  return <HealthPanel data={data.health} />
}

function TradingPage({ data }: { data: NonNullable<ReturnType<typeof useSDOS>['data']> }) {
  return <PortfolioPanel data={data.portfolio} />
}


export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const { data, connected, error } = useSDOS()

  const renderPage = () => {
    if (!data) return <LoadingState />
    switch (page) {
      case 'dashboard':  return <DashboardPage data={data} />
      case 'burnin':     return <BurnInPanel />
      case 'health':     return <HealthPage data={data} />
      case 'trading':    return <TradingPage data={data} />
      case 'scientific': return <ScientificPanel />
      case 'rejects':    return <RejectAnalyzerPanel />
      case 'timeline':   return <TimelinePanel />
      case 'datasets':   return <DatasetsPanel />
      case 'config':     return (
        <div className="card">
          <div className="card-title">Configuration (read-only)</div>
          <pre style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )
    }
  }

  return (
    <div className="terminal">
      <Header data={data} connected={connected} />
      <Sidebar page={page} onNavigate={(p) => setPage(p as Page)} />
      <main className="main">
        {error && (
          <div style={{ padding: '6px 12px', background: '#FF333320', border: '1px solid #FF3333', borderRadius: 4, fontSize: 11, color: '#FF3333' }}>
            {error}
          </div>
        )}
        {renderPage()}
      </main>
    </div>
  )
}
