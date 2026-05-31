import React from 'react'
import { PerpetualImprovementState, fetchPerpetualImprovement } from '../services/api'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'

const colors = {
  bg: '#0d1726',
  panelBg: 'rgba(13,23,38,0.92)',
  border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff',
  muted: '#97a9c6',
  cyan: '#5ad7ff',
  green: '#39d98a',
  amber: '#f3bb4a',
  red: '#ff7b8f',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
}

const PerpetualPanel: React.FC = () => {
  const [state, setState] = React.useState<PerpetualImprovementState | null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchPerpetualImprovement()
        if (!cancelled) setState(data)
      } catch {
        if (!cancelled) setState(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const events = state?.learning_events ?? []
  const candidates = state?.candidate_experiments ?? []

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Perpetual Improvement
      </h2>

      {loading && !state && <LoadingBar label="Loading perpetual improvement..." />}
      {!loading && !state && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No perpetual improvement data available. The endpoint returned empty.
        </div>
      )}

      {state && (
        <>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
            <TruthBadge
              tone={state.loop_status === 'active' ? 'green' : state.loop_status === 'paused' ? 'yellow' : 'gray'}
              label={state.loop_status ?? 'unknown'}
              dot={false}
            />
            <span style={{ fontSize: 12, color: colors.muted }}>
              {events.length} learning event(s) recorded
            </span>
          </div>

          <div style={panelStyle}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>Learning Events</h3>
            {events.length === 0 ? (
              <div style={{ color: colors.muted, fontSize: 13 }}>No learning events yet.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {events.slice(0, 20).map((ev, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '6px 10px',
                      background: 'rgba(20,32,52,0.6)',
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ color: colors.muted, fontFamily: 'monospace' }}>{ev.ts}</span>
                      <span style={{ color: colors.cyan, fontWeight: 600 }}>{ev.symbol}</span>
                      <span style={{ color: colors.text }}>{ev.event}</span>
                      <span style={{ fontSize: 10, color: colors.amber, border: `1px solid ${colors.amber}30`, padding: '1px 4px', borderRadius: 4 }}>{ev.model}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ ...panelStyle, marginTop: 16 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>Candidate Experiments</h3>
            {candidates.length === 0 ? (
              <div style={{ color: colors.muted, fontSize: 13 }}>No candidate experiments queued.</div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {candidates.map((exp, idx) => (
                  <span
                    key={idx}
                    style={{
                      fontSize: 11,
                      padding: '4px 8px',
                      borderRadius: 4,
                      background: 'rgba(90,215,255,0.08)',
                      color: colors.cyan,
                      border: `1px solid rgba(90,215,255,0.15)`,
                    }}
                  >
                    {exp}
                  </span>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default PerpetualPanel
