interface IconProps {
  size?: number
  strokeWidth?: number
  className?: string
}

const base = (size: number, sw: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: sw,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
})

export function QueueIcon({ size = 18, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M3 5h18M3 12h18M3 19h12" />
    </svg>
  )
}

export function DecisionsIcon({ size = 18, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="4.5" />
      <path d="M8 12.2l2.6 2.6L16 9.4" />
    </svg>
  )
}

export function MetricsIcon({ size = 18, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />
    </svg>
  )
}

export function PoliciesIcon({ size = 18, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2.4" />
      <circle cx="8" cy="17" r="2.4" />
    </svg>
  )
}

export function ChevronIcon({ size = 16, className, open }: IconProps & { open?: boolean }) {
  return (
    <svg {...base(size, 2)} className={className}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

export function CheckIcon({ size = 14, className }: IconProps) {
  return (
    <svg {...base(size, 2.4)} className={className}>
      <path d="M4.5 12.5l5 5L19.5 7" />
    </svg>
  )
}

export function XIcon({ size = 14, className }: IconProps) {
  return (
    <svg {...base(size, 2.4)} className={className}>
      <path d="M5 5l14 14M19 5L5 19" />
    </svg>
  )
}

export function ShieldIcon({ size = 14, className }: IconProps) {
  return (
    <svg {...base(size, 1.8)} className={className}>
      <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
    </svg>
  )
}
