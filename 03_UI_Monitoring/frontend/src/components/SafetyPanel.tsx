import React from 'react'
import { SafetyState, fetchSafety } from '../types'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'

const colors = {
  bg: '#0d1726',
  panelBg: 'rgba(13,23,38,0.92)',
  border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff',
  muted: '#97a9c6',
  green: '#39d98a',
  amber: '#f3bb4a',
  red: '#ff7b8f',
  cyan: '#5ad7ff',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
  marginBottom: 16,
}

const SafetyPanel: React.FC = () => {
  const [safety, setSafety] = React.useState<SafetyState | null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const r = await fetch(`${''}/api/safety`, { cache: 'no-store' })
        const data = r.ok ? await r.json() : null
        if (!cancelled) setSafety(data)
      } catch {
        if (!cancelled) setSafety(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Safety — Blunt Lock State
      </h2>

      {loading && !safety && <LoadingBar label="Loading safety state..." />}

      {!loading && !safety && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No safety data available. The safety endpoint returned empty.
        </div>
      )}

      {safety && (
        <>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <TruthBadge
              tone={safety.real_money_locked ? 'red' : 'green'}
              label={safety.real_money_locked ? 'REAL MONEY LOCKED' : 'REAL MONEY UNLOCKED'}
              pulse={safety.real_money_locked}
            />
            {safety.lock_reasons.length > 0 && (
              <div style={{ fontSize: 12, color: colors.muted }}>
                Reasons: {safety.lock_reasons.join(', ')}
              </div>
            )}
          </div>

          <div style={panelStyle}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>
              Safety Gates
            </h3>
            {safety.gates.length === 0 ? (
              <div style={{ color: colors.muted, fontSize: 13 }}>No safety gates configured.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {safety.gates.map((gate, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      background: gate.passed ? 'rgba(0,255,136,0.04)' : 'rgba(255,51,102,0.04)',
                      border: `1px solid ${gate.passed ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)'}`,
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span
                        style={{
                          width: 16,
                          height: 16,
                          borderRadius: '50%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: gate.passed ? colors.green : colors.red,
                          color: '#000',
                          fontSize: 10,
                          fontWeight: 800,
                        }}
                      >
                        {gate.passed ? '✓' : '✕'}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{gate.name}</span>
                    </div>
                    <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace' }}>
                      required: {String(gate.required)} | actual: {gate.actual != null ? String(gate.actual) : '--'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default SafetyPanel
