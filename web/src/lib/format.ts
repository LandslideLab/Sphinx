import type { RequestStatus, RiskLevel } from '../types'

export function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function fmtClock(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export function fmtDuration(sec: number | null): string {
  if (sec === null || sec === undefined) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
  return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m`
}

export const STATUS_LABEL: Record<RequestStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  auto_approved: 'Auto-approved',
  auto_rejected: 'Auto-rejected',
}

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

export const RISK_COLOR: Record<RiskLevel, string> = {
  low: '#22a06b',
  medium: '#e8930c',
  high: '#ea580c',
  critical: '#f43f3f',
}

export function riskBadgeClass(r: RiskLevel): string {
  return `badge risk-${r}`
}

export function frameworkLabel(f: string): string {
  return f.charAt(0).toUpperCase() + f.slice(1)
}
