interface Props {
  page: string
  onNavigate: (page: string) => void
}

const PAGES = [
  { id: 'dashboard', icon: '⬛', label: 'Dashboard' },
  { id: 'burnin',    icon: '🧪', label: 'Burn-in' },
  { id: 'trading',   icon: '📈', label: 'Trading' },
  { id: 'scientific',icon: '🔬', label: 'Scientific' },
  { id: 'health',    icon: '🌡', label: 'Health' },
  { id: 'rejects',   icon: '⛔', label: 'Rejects' },
  { id: 'timeline',  icon: '📜', label: 'Timeline' },
  { id: 'datasets',  icon: '📦', label: 'Datasets' },
  { id: 'config',    icon: '⚙️', label: 'Config' },
]

export function Sidebar({ page, onNavigate }: Props) {
  return (
    <nav className="sidebar">
      <div className="nav-section">OBSERVE</div>
      {PAGES.map(p => (
        <div
          key={p.id}
          className={`nav-item ${page === p.id ? 'active' : ''}`}
          onClick={() => onNavigate(p.id)}
        >
          <span className="nav-icon">{p.icon}</span>
          {p.label}
        </div>
      ))}
      <div className="nav-section" style={{ marginTop: 16 }}>SVA v1.0</div>
      <div className="nav-item" style={{ fontSize: '10px', color: 'var(--text-dim)', cursor: 'default' }}>
        SVL · SOI · VES
      </div>
    </nav>
  )
}
