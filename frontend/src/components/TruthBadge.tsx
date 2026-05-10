import React from 'react'

export type TruthTone = 'green' | 'blue' | 'yellow' | 'red' | 'purple' | 'gray'

interface Props {
  tone: TruthTone
  label: string
  value?: string | number | null
  dot?: boolean
  pulse?: boolean
}

const TONE_MAP: Record<TruthTone, { bg: string; border: string; color: string; glow?: string }> = {
  green:  { bg: 'rgba(0,255,136,0.08)', border: 'rgba(0,255,136,0.22)', color: '#00ff88', glow: 'rgba(0,255,136,0.15)' },
  blue:   { bg: 'rgba(0,240,255,0.08)', border: 'rgba(0,240,255,0.22)', color: '#00f0ff', glow: 'rgba(0,240,255,0.15)' },
  yellow: { bg: 'rgba(255,215,0,0.08)',  border: 'rgba(255,215,0,0.22)',  color: '#ffd700', glow: 'rgba(255,215,0,0.12)' },
  red:    { bg: 'rgba(255,51,102,0.08)', border: 'rgba(255,51,102,0.22)', color: '#ff3366', glow: 'rgba(255,51,102,0.15)' },
  purple: { bg: 'rgba(185,103,255,0.08)', border: 'rgba(185,103,255,0.22)', color: '#b967ff', glow: 'rgba(185,103,255,0.12)' },
  gray:   { bg: 'rgba(74,96,120,0.12)',  border: 'rgba(74,96,120,0.25)',  color: '#4a6078', glow: undefined },
}

const TruthBadge: React.FC<Props> = ({ tone, label, value, dot = true, pulse = false }) => {
  const s = TONE_MAP[tone]
  const display = value != null ? String(value) : '--'
  return (
    <span
      title={`${label}: ${display}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: 4,
        fontSize: '0.65rem',
        fontWeight: 700,
        letterSpacing: '0.06em',
        fontFamily: 'var(--mono)',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        boxShadow: s.glow ? `0 0 8px ${s.glow}` : 'none',
      }}
    >
      {dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: s.color,
            boxShadow: s.glow ? `0 0 6px ${s.color}` : 'none',
            animation: pulse ? 'liveDot 1.5s ease-in-out infinite' : undefined,
            flexShrink: 0,
          }}
        />
      )}
      <span>{label}</span>
      {value != null && (
        <span style={{ opacity: 0.85 }}>{display}</span>
      )}
    </span>
  )
}

export default TruthBadge
