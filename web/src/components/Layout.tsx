import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { usePendingCount } from '../lib/usePendingCount'
import { DecisionsIcon, MetricsIcon, PoliciesIcon, QueueIcon, ShieldIcon } from './Icons'

const NAV = [
  { to: '/', label: 'Approval Queue', Icon: QueueIcon, end: true },
  { to: '/decisions', label: 'Decision Log', Icon: DecisionsIcon },
  { to: '/metrics', label: 'Governance Metrics', Icon: MetricsIcon },
  { to: '/policies', label: 'SLA Policies', Icon: PoliciesIcon },
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
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <span className="ico"><Icon /></span>
              <span>{label}</span>
              {to === '/' && pending > 0 && <span className="badge pending nav-count">{pending}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="row"><ShieldIcon size={12} /> governance-first HITL</div>
          <div className="row">v0.1 · MCP-native · SDK</div>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
