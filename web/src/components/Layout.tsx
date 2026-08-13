import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { usePendingCount } from '../lib/usePendingCount'

const NAV = [
  { to: '/', label: 'Approval Queue', icon: '◫', end: true },
  { to: '/decisions', label: 'Decision Log', icon: '⌾' },
  { to: '/metrics', label: 'Governance Metrics', icon: '◔' },
  { to: '/policies', label: 'SLA Policies', icon: '⚙' },
]

export function Layout({ children }: { children: ReactNode }) {
  const pending = usePendingCount()
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">S</div>
          <div>
            <div className="brand-name">sphinx</div>
            <div className="brand-sub">HITL Control Plane</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <span className="ico">{n.icon}</span>
              <span>{n.label}</span>
              {n.to === '/' && pending > 0 && <span style={{ marginLeft: 'auto' }} className="badge pending">{pending}</span>}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
